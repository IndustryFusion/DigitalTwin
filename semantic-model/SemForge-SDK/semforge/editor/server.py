"""The LSP server: a thin translation of analysis.py into protocol objects.

Nothing here decides anything semantic. That is architecture.md section 8.4 --
the editor layer must not become the semantic engine -- and it is why every
behaviour this exposes is testable without starting a server.

LSP is used where the operation IS an LSP operation: diagnostics, hover,
go-to-definition, document symbols. Operations with no natural LSP shape would
go on a dedicated channel instead; none are needed yet.
"""

import os
import re

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from .. import __version__
from .analysis import analyse, definition_at, hover_at, package_root

SEVERITY = {
    'error': types.DiagnosticSeverity.Error,
    'warning': types.DiagnosticSeverity.Warning,
    'information': types.DiagnosticSeverity.Information,
    'hint': types.DiagnosticSeverity.Hint,
}
WORD = re.compile(r'[A-Za-z_][\w.-]*:?[\w.-]*')

server = LanguageServer('semforge', __version__)
_packages = {}


def _uri_to_path(uri):
    from urllib.parse import unquote, urlparse
    return unquote(urlparse(uri).path)


def _path_to_uri(path):
    from urllib.request import pathname2url
    return 'file://' + pathname2url(os.path.abspath(path))


def _word_at(document, position):
    try:
        line = document.lines[position.line]
    except IndexError:
        return ''
    for match in WORD.finditer(line):
        if match.start() <= position.character <= match.end():
            return match.group(0).rstrip(':').split(':')[-1] or match.group(0)
    return ''


def _publish(ls, uri):
    """Analyse the package this file belongs to and publish its diagnostics."""
    path = _uri_to_path(uri)
    root = package_root(path)
    if root is None:
        ls.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=uri, diagnostics=[]))
        return
    try:
        findings, package = analyse(root)
    except Exception as exc:                       # noqa: BLE001
        # A broken package must not silence the server: report the failure as a
        # diagnostic rather than leaving the editor showing a clean file.
        ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
            uri=uri, diagnostics=[types.Diagnostic(
                range=types.Range(types.Position(0, 0), types.Position(0, 1)),
                message=f'semforge could not analyse this package: {exc}',
                severity=types.DiagnosticSeverity.Error, source='semforge')]))
        return

    _packages[root] = package
    for file_path, items in findings.items():
        diagnostics = []
        for finding in items:
            line = max(finding.line - 1, 0)
            diagnostics.append(types.Diagnostic(
                range=types.Range(types.Position(line, 0),
                                  types.Position(line, 200)),
                message=finding.message,
                severity=SEVERITY.get(finding.severity,
                                      types.DiagnosticSeverity.Information),
                source=f'semforge ({finding.kind})'))
        ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
            uri=_path_to_uri(file_path), diagnostics=diagnostics))


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls, params):
    _publish(ls, params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
def did_save(ls, params):
    _publish(ls, params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(ls, params):
    root = package_root(_uri_to_path(params.text_document.uri))
    package = _packages.get(root)
    if package is None:
        return None
    document = ls.workspace.get_text_document(params.text_document.uri)
    markdown = hover_at(package, _word_at(document, params.position))
    if not markdown:
        return None
    return types.Hover(contents=types.MarkupContent(
        kind=types.MarkupKind.Markdown, value=markdown))


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def definition(ls, params):
    root = package_root(_uri_to_path(params.text_document.uri))
    package = _packages.get(root)
    if package is None:
        return None
    document = ls.workspace.get_text_document(params.text_document.uri)
    found = definition_at(package, _word_at(document, params.position))
    if found is None:
        return None
    path, line = found
    return types.Location(
        uri=_path_to_uri(path),
        range=types.Range(types.Position(line - 1, 0),
                          types.Position(line - 1, 0)))


@server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(ls, params):
    from ..rdfio import index_file

    path = _uri_to_path(params.text_document.uri)
    if not path.endswith('.ttl') or not os.path.exists(path):
        return None
    index = index_file(path)
    lines = index.source.splitlines()

    def width(number):
        return len(lines[number]) if 0 <= number < len(lines) else 0

    symbols = []
    for block in index.blocks:
        name = block.raw_subject.strip()
        if not name:
            continue               # a symbol with no name is rejected outright
        first, last = block.start_line - 1, block.end_line - 1
        # The range must CONTAIN the selection range, and a one-line statement
        # made both degenerate: (L,0)-(L,0) around (L,0)-(L,1). The client
        # rejects that and the whole request fails, so the Outline was empty and
        # the log said only "provider FAILED".
        whole = types.Range(types.Position(first, 0),
                            types.Position(last, width(last)))
        subject = types.Range(
            types.Position(first, 0),
            types.Position(first, min(len(name), width(first))))
        symbols.append(types.DocumentSymbol(
            name=name, kind=types.SymbolKind.Class,
            range=whole, selection_range=subject))
    return symbols


# --- the SemForge channel ---------------------------------------------------
#
# Architecture section 8.3: LSP is used where the operation IS an LSP
# operation. A constraint tree and an edit-by-address are not, and forcing them
# through workspace/executeCommand would make them opaque to any other client.
# They get named methods instead.

def _field(params, name, default=None):
    """Read a parameter whichever way pygls handed it over.

    Custom methods have no registered type, so pygls deserialises their params
    into a namedtuple-like object rather than a dict -- and a handler written
    for one shape fails on the other with a TypeError the client never sees.
    """
    if isinstance(params, dict):
        return params.get(name, default)
    return getattr(params, name, default)


def _serialise(node):
    return {
        'kind': node.kind, 'label': node.label, 'detail': node.detail,
        'shape': node.shape, 'path': list(node.path_chain),
        'parameter': node.parameter, 'value': node.value,
        'editable': node.editable,
        'inheritedFrom': node.inherited_from,
        'inheritedClass': node.inherited_class,
        'definedAt': node.defined_at,
        'targetClass': node.target_class,
        'children': [_serialise(child) for child in node.children],
    }


def _package_for(root):
    from ..package import load

    if root not in _packages:
        _packages[root] = load(root)
    return _packages[root]


@server.feature('semforge/tree')
def cooked_tree(ls, params):
    """The cooked constraint tree for a package."""
    from ..cooked import build_tree

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'roots': [], 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        return {'root': root,
                'roots': [_serialise(node) for node in build_tree(package)]}
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


@server.feature('semforge/choices')
def constraint_choices(ls, params):
    """Candidate values for a parameter at one address.

    Computed here rather than in the extension because which classes are
    offerable is an ontology question -- entity types on one side of the
    NGSI-LD encoding, vocabulary classes on the other -- and a hard-coded list
    in JavaScript would drift from the model the moment somebody adds a class.
    """
    from ..cooked.choices import SEARCH_THRESHOLD, choices_for

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'choices': [], 'note': 'not a SemForge package', 'total': 0}
    try:
        package = _package_for(root)
        limit = _field(params, 'limit') or SEARCH_THRESHOLD
        # Fetch the whole ranked set once and cap it here, so `total` is exact
        # without asking twice. total > len(choices) is what tells the client
        # that local filtering is not enough and it must come back as the user
        # types.
        found, note = choices_for(package, list(_field(params, 'path') or []),
                                  _field(params, 'parameter'),
                                  search=_field(params, 'search'))
        total = len(found)
        if total > limit:
            found = found[:limit]
            note = f'showing {limit} of {total}; keep typing to narrow'
        return {'choices': found, 'note': note, 'total': total}
    except Exception as exc:                       # noqa: BLE001
        return {'choices': [], 'note': str(exc), 'total': 0}


def _serialise_example(node):
    return {
        'kind': node.kind, 'label': node.label, 'detail': node.detail,
        'entity': node.entity, 'path': list(node.path), 'value': node.value,
        'editable': node.editable, 'severity': node.severity,
        'messages': list(node.messages),
        'datasetId': node.dataset_id, 'observations': node.observations,
        'attributePath': list(node.attribute_path), 'file': node.file,
        'entityType': node.entity_type,
        # Which cases include this file. The row is editable either way; this is
        # what lets the edit say how far it reaches before making it.
        'sharedBy': list(node.shared_by),
        # Without this the client has no location and selection reveals
        # nothing -- which is how the examples tree looked inert.
        'definedAt': node.defined_at,
        'children': [_serialise_example(child) for child in node.children],
    }


@server.feature('semforge/model')
def model(ls, params):
    """The model as a tree: the declared cases and the scratchpad, annotated
    with what validation says about them."""
    from ..cooked.examples import build_suite

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'roots': [], 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        return {'root': root,
                'roots': [_serialise_example(n)
                          for n in build_suite(package)]}
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


def _serialise_knowledge(node):
    return {
        'kind': node.kind, 'label': node.label, 'detail': node.detail,
        'iri': node.iri, 'definedAt': node.defined_at,
        'shape': node.shape, 'shapeName': node.shape_name,
        'shapeAt': node.shape_at,
        'entity': node.entity, 'entityType': node.entity_type,
        'file': node.file,
        'severity': node.severity, 'messages': list(node.messages),
        'children': [_serialise_knowledge(child) for child in node.children],
    }


@server.feature('semforge/methods')
def methods(ls, params):
    """What this server can answer, and where its code lives.

    An extension newer than the server is invisible otherwise: the new icon is
    there, the request comes back "method not found", and the click does
    nothing. This makes that one line in the doctor.
    """
    import semforge

    try:
        registered = sorted(
            name for name in server.protocol.fm.features
            if name.startswith('semforge/'))
    except Exception:                              # noqa: BLE001
        registered = []
    return {'methods': registered,
            'module': os.path.dirname(os.path.abspath(semforge.__file__)),
            'version': __version__}


@server.feature('semforge/knowledge')
def knowledge(ls, params):
    """The ontology: entity hierarchy and vocabularies, with their joins.

    The third of the three views. What it adds over reading knowledge.ttl is
    where it meets the other two -- which class a shape judges, which terms the
    examples actually use -- so the rows carry both locations.
    """
    from ..cooked.knowledge import build_knowledge

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'roots': [], 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        return {'root': root,
                'roots': [_serialise_knowledge(n)
                          for n in build_knowledge(package)]}
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


@server.feature('semforge/shapeFor')
def shape_for_attribute(ls, params):
    """Where the shape that judges this attribute is declared.

    With `create` set, an absent one is written as an empty property shape: the
    point of the jump is to change the constraint, and there is nothing to
    change when no shape mentions the attribute. The stub is reported as
    created so the client can say so -- it constrains nothing yet, and the
    capability check will call that out.
    """
    from ..cooked.shapelink import ensure_property_shape, find_property_shape

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    entity_type = _field(params, 'entityType') or ''
    attribute = _field(params, 'attribute') or ''
    if not entity_type or not attribute:
        return {'ok': False,
                'error': 'need both an entity type and an attribute name'}
    try:
        package = _package_for(root)
        if _field(params, 'create'):
            found, how = ensure_property_shape(package, entity_type, attribute)
            if how == 'created':
                _packages.pop(root, None)
                _publish(ls, _path_to_uri(package.sources['shapes']))
        else:
            found, how = find_property_shape(package, entity_type,
                                             attribute), 'found'
            if found is None:
                return {'ok': False, 'exists': False,
                        'error': f'no shape constrains {attribute} '
                                 f'on {entity_type}'}
        return {'ok': True, 'how': how, **found}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/valueChoices')
def value_choices_feature(ls, params):
    """What the shape allows as a value for one example attribute.

    Separate from `semforge/choices`: that one answers "what may this SHACL
    parameter say", this one answers "what may this datum be". A sh:class on
    the value slot means the value is an individual of that class, so the
    options are individuals -- or, for a relationship, entity ids.
    """
    from ..cooked.shapelink import value_choices

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'choices': [], 'note': 'not a SemForge package'}
    try:
        package = _package_for(root)
        found, note = value_choices(package,
                                    _field(params, 'entityType') or '',
                                    _field(params, 'attribute') or '',
                                    limit=_field(params, 'limit') or 200,
                                    search=_field(params, 'search'))
        return {'choices': found, 'note': note}
    except Exception as exc:                       # noqa: BLE001
        return {'choices': [], 'note': str(exc)}


@server.feature('semforge/setValue')
def set_example_value(ls, params):
    """Change one value in the example, then re-validate.

    Re-publishing afterwards is the point: the reason to edit data here rather
    than in the JSON is to watch the verdict move.
    """
    from ..cooked.examples import set_value

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        path, old, new = set_value(package, _field(params, 'entity'),
                                   list(_field(params, 'path') or []),
                                   _field(params, 'value'),
                                   file=_field(params, 'file'))
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(package.sources['shapes']))
        return {'ok': True, 'file': path, 'old': old, 'new': new}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addObservation')
def add_observation_feature(ls, params):
    """Append an observation to one attribute's series."""
    from ..cooked.examples import add_observation

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        path, count = add_observation(
            package, _field(params, 'entity'),
            list(_field(params, 'attributePath') or []),
            _field(params, 'datasetId'), _field(params, 'value'),
            _field(params, 'observedAt'), file=_field(params, 'file'))
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(package.sources['shapes']))
        return {'ok': True, 'file': path, 'count': count}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addAttribute')
def add_attribute_feature(ls, params):
    """Add an attribute, with the kind the shapes say it should be."""
    from ..cooked.examples import add_attribute

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        path, kind = add_attribute(
            package, _field(params, 'entity'), _field(params, 'name'),
            kind=_field(params, 'kind'), value=_field(params, 'value'),
            file=_field(params, 'file'),
            observedAt=_field(params, 'observedAt'),
            datasetId=_field(params, 'datasetId'))
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(package.sources['shapes']))
        return {'ok': True, 'file': path, 'kind': kind}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addEntity')
def add_entity_feature(ls, params):
    """Append a legal NGSI-LD entity to an example file."""
    from ..cooked.examples import add_entity

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        path, count = add_entity(
            package, _field(params, 'id'), _field(params, 'entityType'),
            file=_field(params, 'file'))
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(package.sources['shapes']))
        return {'ok': True, 'file': path, 'count': count}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/kinds')
def kinds(ls, params):
    from ..ngsild.build import KINDS

    return {'kinds': list(KINDS)}


@server.feature('semforge/setConstraint')
def set_constraint(ls, params):
    """Apply one cooked edit, then re-analyse so diagnostics follow it."""
    from ..cooked import apply_edit, remove_constraint

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        shape = _field(params, 'shape')
        chain = list(_field(params, 'path') or [])
        parameter = _field(params, 'parameter')
        if _field(params, 'remove'):
            path, changed = remove_constraint(package, shape, chain, parameter)
        else:
            path, changed = apply_edit(package, shape, chain, parameter,
                                       str(_field(params, 'value')))
        _packages.pop(root, None)                  # the file changed underneath
        _publish(ls, _path_to_uri(path))
        return {'ok': True, 'file': path, 'bytesChanged': changed}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/override')
def override(ls, params):
    """Declare an inherited constraint explicitly on the subtype's own shape.

    Reports the EFFECT before doing anything, because SHACL has no override:
    the new constraint is conjoined with the inherited one, so it can tighten
    and cannot relax. `check` alone returns the verdict without writing.
    """
    from ..cooked.tree import override_constraint, override_effect

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}

    parameter = _field(params, 'parameter')
    value = str(_field(params, 'value'))
    effect = override_effect(parameter, _field(params, 'inheritedValue'), value)
    if _field(params, 'check'):
        return {'ok': True, 'effect': effect}
    if effect in ('weaker', 'same') and not _field(params, 'force'):
        return {'ok': False, 'effect': effect,
                'error': ('SHACL conjoins constraints, so this would be '
                          'evaluated alongside the inherited one rather than '
                          'instead of it -- it cannot relax it.')}
    try:
        package = _package_for(root)
        path, how = override_constraint(
            package, _field(params, 'targetShape'),
            list(_field(params, 'path') or []), parameter, value)
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(path))
        return {'ok': True, 'effect': effect, 'file': path, 'how': how}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'effect': effect, 'error': str(exc)}


def main():
    server.start_io()


if __name__ == '__main__':
    main()
