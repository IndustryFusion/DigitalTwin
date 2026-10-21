"""The LSP server: a thin translation of analysis.py into protocol objects.

Nothing here decides anything semantic. That is architecture.md section 8.4 --
the editor layer must not become the semantic engine -- and it is why every
behaviour this exposes is testable without starting a server.

LSP is used where the operation IS an LSP operation: diagnostics, hover,
go-to-definition, find-references, document symbols. Operations with no natural LSP shape would
go on a dedicated channel instead; none are needed yet.
"""

import os
import re

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from .. import __version__
from .analysis import (analyse, definition_at, hover_at, package_root,
                       references_at)
from ..validate import validate_package

SEVERITY = {
    'error': types.DiagnosticSeverity.Error,
    'warning': types.DiagnosticSeverity.Warning,
    'information': types.DiagnosticSeverity.Information,
    'hint': types.DiagnosticSeverity.Hint,
}
WORD = re.compile(r'[A-Za-z_][\w.-]*:?[\w.-]*')
# The term as written, prefix kept: an IRI, a prefixed name (the empty prefix
# included), or a bare JSON-LD term. WORD drops the prefix, which is all
# go-to-definition needs; references cannot, because the prefix is what tells
# iffBaseShacl:CartridgeShape from iffFilterShacl:CartridgeShape.
TOKEN = re.compile(r'<[^<>\s]*>|(?:[A-Za-z_][\w.-]*)?:[\w.-]+|[A-Za-z_@][\w.-]*')

server = LanguageServer('semforge', __version__)
_packages = {}
_published = {}            # root -> uris that were last sent findings
_stamps = {}               # root -> fingerprint the loaded package was read at


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


def _token_at(document, position):
    try:
        line = document.lines[position.line]
    except IndexError:
        return ''
    for match in TOKEN.finditer(line):
        if match.start() <= position.character <= match.end():
            return match.group(0).rstrip('.')
    return ''


def _findings(root):
    """{file: [EditorFinding]}, from the disk cache while nothing changed."""
    from dataclasses import asdict

    from .analysis import EditorFinding
    from .cache import cached, fingerprint

    def compute():
        stamp = fingerprint(root)
        findings, package = analyse(root)
        _packages[root], _stamps[root] = package, stamp
        _watch_renames(root, package)              # a reload like any other
        return {path: [asdict(f) for f in items] for path, items in findings.items()}

    stored, _ = cached(root, 'diagnostics', compute)
    return {path: [EditorFinding(**f) for f in items]
            for path, items in stored.items()}


def _publish(ls, uri):
    """Analyse the package this file belongs to and publish its diagnostics."""
    path = _uri_to_path(uri)
    root = package_root(path)
    if root is None:
        ls.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=uri, diagnostics=[]))
        return
    try:
        findings = _findings(root)
    except Exception as exc:                       # noqa: BLE001
        # A broken package must not silence the server: report the failure as a
        # diagnostic rather than leaving the editor showing a clean file.
        ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
            uri=uri, diagnostics=[types.Diagnostic(
                range=types.Range(types.Position(0, 0), types.Position(0, 1)),
                message=f'semforge could not analyse this package: {exc}',
                severity=types.DiagnosticSeverity.Error, source='semforge')]))
        return

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
                source=f'semforge ({finding.kind})',
                code=finding.code or None,
                # Round-trips through the client untouched: the quick fix
                # reads it back from the diagnostic it was offered on.
                data=finding.data))
        ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
            uri=_path_to_uri(file_path), diagnostics=diagnostics))

    # A file that HAD findings and has none now must be told so: an LSP client
    # keeps the last list it was sent per document, so fixing the last problem
    # in a .jsonld would leave its squiggle standing forever.
    now = {_path_to_uri(path) for path, items in findings.items() if items}
    for stale in _published.get(root, set()) - now:
        ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
            uri=stale, diagnostics=[]))
    _published[root] = now
    _republish_queries(ls)


def _republish_queries(ls):
    """Open SPARQL query documents are checked against the package's terms
    and shapes: when the package changed, so may their squiggles -- a quick
    fix that adds a shape must take the warning it fixed away."""
    from .sparqldocs import is_query

    try:
        open_uris = list(ls.workspace.text_documents)
    except Exception:                              # noqa: BLE001
        return
    for uri in open_uris:
        if is_query(uri):
            _publish_query(ls, uri)


# --- the SPARQL workbench's query documents (semforge-sparql:) ----------------------

def _query_context(uri):
    from .sparqldocs import context
    return context(uri, _package_for, package_root, _uri_to_path)


def _publish_query(ls, uri):
    """Squiggles for a query document, from its text as it is now."""
    from .sparqldocs import diagnostics

    try:
        ctx = _query_context(uri)
        found = diagnostics(ls.workspace.get_text_document(uri).source, ctx) if ctx else []
    except Exception as exc:                       # noqa: BLE001
        found = [types.Diagnostic(
            range=types.Range(types.Position(0, 0), types.Position(0, 1)),
            message=f'semforge could not check this query: {exc}',
            severity=types.DiagnosticSeverity.Warning, source='semforge-sparql')]
    ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
        uri=uri, diagnostics=found))


def _offset(document, position):
    from ..sparql.lexer import offset_of
    return offset_of(document.source, position.line, position.character)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls, params):
    from .sparqldocs import is_query
    if is_query(params.text_document.uri):
        _publish_query(ls, params.text_document.uri)
        return
    _rename_baseline(params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls, params):
    from .sparqldocs import is_query
    if is_query(params.text_document.uri):
        ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
            uri=params.text_document.uri, diagnostics=[]))


@server.feature(types.TEXT_DOCUMENT_COMPLETION,
                types.CompletionOptions(trigger_characters=[':', '?', '$']))
def completion(ls, params):
    from .sparqldocs import completion as complete_query, is_query

    if not is_query(params.text_document.uri):
        return None
    ctx = _query_context(params.text_document.uri)
    if ctx is None:
        return None
    document = ls.workspace.get_text_document(params.text_document.uri)
    return complete_query(document.source, _offset(document, params.position), ctx)


@server.feature(types.TEXT_DOCUMENT_FORMATTING)
def formatting(ls, params):
    from ..sparql.format import FormatError
    from .sparqldocs import formatting as format_query, is_query

    if not is_query(params.text_document.uri):
        return None
    document = ls.workspace.get_text_document(params.text_document.uri)
    try:
        return format_query(document.source)
    except FormatError as exc:
        ls.window_show_message(types.ShowMessageParams(
            type=types.MessageType.Warning, message=f'SemForge: {exc}'))
        return None


@server.feature('semforge/sparqlQuery')
def sparql_query_feature(ls, params):
    """One query's saved text: what a query document opens with."""
    from ..cooked.sparqlbench import holders

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        found = holders(_package_for(root), str(_field(params, 'shape', '') or ''))
        index = int(_field(params, 'holder') or 0)
        if not 0 <= index < len(found):
            return {'ok': False, 'error': 'this shape has no such SPARQL query (any more)'}
        return dict(found[index], ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls, params):
    from .sparqldocs import is_query
    if is_query(params.text_document.uri):
        _publish_query(ls, params.text_document.uri)
        return
    _rename_baseline(params.text_document.uri)
    _publish(ls, params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
def did_save(ls, params):
    from .sparqldocs import is_query
    if is_query(params.text_document.uri):
        return
    _publish(ls, params.text_document.uri)
    root = package_root(_uri_to_path(params.text_document.uri))
    if root is not None:
        _offer_renames(ls, root)


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(ls, params):
    from .sparqldocs import hover as hover_query, is_query

    if is_query(params.text_document.uri):
        ctx = _query_context(params.text_document.uri)
        document = ls.workspace.get_text_document(params.text_document.uri)
        return hover_query(document.source, _offset(document, params.position), ctx) \
            if ctx else None
    root = package_root(_uri_to_path(params.text_document.uri))
    if root is None:
        return None
    package = _package_for(root)
    document = ls.workspace.get_text_document(params.text_document.uri)
    markdown = hover_at(package, _word_at(document, params.position))
    if not markdown:
        return None
    return types.Hover(contents=types.MarkupContent(
        kind=types.MarkupKind.Markdown, value=markdown))


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def definition(ls, params):
    root = package_root(_uri_to_path(params.text_document.uri))
    if root is None:
        return None
    package = _package_for(root)
    document = ls.workspace.get_text_document(params.text_document.uri)
    found = definition_at(package, _word_at(document, params.position))
    if found is None:
        return None
    path, line = found
    return types.Location(
        uri=_path_to_uri(path),
        range=types.Range(types.Position(line - 1, 0),
                          types.Position(line - 1, 0)))


@server.feature(types.TEXT_DOCUMENT_REFERENCES)
def references(ls, params):
    path = _uri_to_path(params.text_document.uri)
    if package_root(path) is None:
        return None
    package = _package_for(package_root(path))
    document = ls.workspace.get_text_document(params.text_document.uri)
    found = references_at(package, _token_at(document, params.position), path,
                          include_declaration=params.context.include_declaration)
    return [types.Location(uri=_path_to_uri(reference.path),
                           range=_range_of(reference))
            for reference in found]


def _range_of(reference):
    line = reference.line - 1
    return types.Range(types.Position(line, reference.column),
                       types.Position(line, reference.column + reference.length))


def _local(iri):
    return str(iri).rstrip('/#').rsplit('/', 1)[-1].rsplit('#', 1)[-1]


def _fixes_for(diagnostic, uri):
    """The quick fixes one sanity diagnostic offers, as client commands.

    Commands rather than workspace edits: "Declare it" needs the author's
    answers (which type carries it, what kind it is), and the removals are
    span edits only the server knows how to make safely. The data each needs
    rode along on the diagnostic when it was published.
    """
    data = diagnostic.data if isinstance(diagnostic.data, dict) else {}
    code = data.get('code', '')
    subject = data.get('subject', '')
    actions = []

    def action(title, command, argument, preferred=False):
        actions.append(types.CodeAction(
            title=title, kind=types.CodeActionKind.QuickFix,
            diagnostics=[diagnostic], is_preferred=preferred,
            command=types.Command(title=title, command=command,
                                  arguments=[argument])))

    if data.get('declare'):
        action(f'Declare {_local(data["declare"])} in the knowledge',
               'semforge.newAttribute',
               {'packageUri': uri, 'iri': data['declare']}, preferred=True)
    if code == 'undeclared-path':
        action(f'Remove this property shape for {_local(subject)}',
               'semforge.removeUse',
               {'uri': uri, 'kind': 'property', 'file': data.get('file'),
                'offset': data.get('offset'), 'label': _local(subject)})
    elif code == 'undeclared-key':
        action(f'Remove {_local(subject)} from this entity',
               'semforge.removeUse',
               {'uri': uri, 'kind': 'key', 'file': _uri_to_path(uri),
                'line': diagnostic.range.start.line + 1, 'iri': subject,
                'label': _local(subject)})
    elif code == 'stale-assert':
        # Left behind by a rename typed into the .ttl: the constraint it
        # meant first, when exactly one shape declares the same one.
        if data.get('suggest'):
            action(f'Rename the assert to {data["suggest"]}', 'semforge.removeUse',
                   {'uri': uri, 'kind': 'retarget', 'file': data.get('file'),
                    'case': data.get('case'), 'index': data.get('index'),
                    'constraint': data['suggest'], 'label': subject,
                    'said': f'the assert now names {data["suggest"]}'}, preferred=True)
        action('Remove this assert', 'semforge.removeUse',
               {'uri': uri, 'kind': 'assert', 'file': data.get('file'),
                'case': data.get('case'), 'index': data.get('index'),
                'label': subject}, preferred=not data.get('suggest'))
    elif code == 'severity-unlinked':
        action(f'Declare {_local(subject)} a kind of sh:Severity', 'semforge.linkSeverityClass',
               {'packageUri': uri, 'cls': subject}, preferred=True)
    elif code in ('observed-at-invalid', 'observed-at-format', 'observed-at-mixed'):
        where = {'packageUri': uri, 'entity': data.get('entity'),
                 'attributePath': data.get('attributePath'), 'file': data.get('file'),
                 'index': data.get('index')}
        if code == 'observed-at-format':
            action(f'Write it as {data.get("observedAt")}', 'semforge.setObservedAt',
                   dict(where, observedAt=data.get('observedAt')), preferred=True)
        else:
            action('Set its time…', 'semforge.setObservedAt', where, preferred=True)
    elif code == 'observed-at-order':
        action('Sort them by time', 'semforge.sortObservations',
               {'packageUri': uri, 'entity': data.get('entity'),
                'attributePath': data.get('attributePath'), 'file': data.get('file'),
                'datasetId': data.get('datasetId', '')}, preferred=True)
    elif code == 'unit-unknown':
        action('Choose the unit…', 'semforge.setUnitCode',
               {'packageUri': uri, 'entity': data.get('entity'),
                'attributePath': data.get('attributePath'), 'file': data.get('file'),
                'datasetId': data.get('datasetId', ''), 'current': data.get('unit')},
               preferred=True)
        action(f'Add {data.get("unit")} as a unit of this package…', 'semforge.newUnit',
               {'packageUri': uri, 'code': data.get('unit')})
    elif code == 'dataset-unregistered':
        action(f'Register a prefix for {data.get("namespace")}…', 'semforge.addNamespace',
               {'packageUri': uri, 'namespace': data.get('namespace')}, preferred=True)
        action('Change the datasetId…', 'semforge.setDatasetId',
               {'packageUri': uri, 'entity': data.get('entity'),
                'attributePath': data.get('attributePath'), 'file': data.get('file'),
                'old': data.get('old')})
    elif code in ('dataset-none', 'dataset-not-iri', 'dataset-duplicate'):
        where = {'packageUri': uri, 'entity': data.get('entity'),
                 'attributePath': data.get('attributePath'), 'file': data.get('file'),
                 'old': data.get('old')}
        if code == 'dataset-none':
            action('Remove "datasetId": "@none" (the default instance has none)',
                   'semforge.setDatasetId', dict(where, new='@none'), preferred=True)
        elif code == 'dataset-not-iri':
            action('Change the datasetId…', 'semforge.setDatasetId', where, preferred=True)
        else:
            action('Give this instance its own datasetId…', 'semforge.setDatasetId',
                   dict(where, index=data.get('index')), preferred=True)
    elif code == 'unused-attribute':
        action(f'Delete {_local(subject)}…', 'semforge.deleteAttribute',
               {'packageUri': uri, 'raw': {'iri': subject}}, preferred=True)
    return actions


@server.feature(types.TEXT_DOCUMENT_CODE_ACTION)
def code_action(ls, params):
    from .sparqldocs import code_actions, is_query

    if is_query(params.text_document.uri):
        ctx = _query_context(params.text_document.uri)
        document = ls.workspace.get_text_document(params.text_document.uri)
        return code_actions(params.text_document.uri, document.source, ctx, params) \
            if ctx else None
    actions = []
    for diagnostic in params.context.diagnostics or []:
        if str(diagnostic.source or '').startswith('semforge'):
            actions += _fixes_for(diagnostic, params.text_document.uri)
    return actions or None


@server.feature('semforge/removeUse')
def remove_use_feature(ls, params):
    """Remove exactly one use, at the place a sanity finding marked."""
    from ..cooked.remove_use import remove_assert, remove_key_at, remove_property_at

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        kind = _field(params, 'kind')
        target = _field(params, 'file')
        note = ''
        if kind == 'property':
            remove_property_at(target, int(_field(params, 'offset')))
        elif kind == 'key':
            remove_key_at(_package_for(root), target, int(_field(params, 'line')),
                          _field(params, 'iri'))
        elif kind == 'assert':
            note = remove_assert(target, _field(params, 'case'),
                                 int(_field(params, 'index')))
        elif kind == 'retarget':
            from ..expect.stale import retarget_assert
            note = retarget_assert(target, _field(params, 'case'),
                                   int(_field(params, 'index')), _field(params, 'constraint'))
        else:
            return {'ok': False, 'error': f'nothing knows how to remove a {kind}'}
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(target))
        return {'ok': True, 'file': target, 'note': note}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


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
    value = getattr(params, name, default)
    # That object is a tuple underneath: a parameter the client did not send
    # and that shares a name with a tuple method -- `index`, `count` -- would
    # come back as the bound method, not as missing.
    return default if callable(value) else value


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


def _view(root, key, compute, params=None):
    """A view's payload, from the disk cache while the package is unchanged.

    With `detail: summary` in the request the tree comes back slimmed
    (editor/slim.py). The full payload is what is cached; the summary is a
    cheap pass over it, so one entry serves both modes.
    """
    from .cache import cached
    from .slim import SLIM

    payload, hit = cached(root, key, compute)
    payload = dict(payload, cached=hit)
    if params is not None and _field(params, 'detail') == 'summary' \
            and key in SLIM and payload.get('roots'):
        payload['roots'] = SLIM[key](payload['roots'], payload)
        payload['detail'] = 'summary'
    return payload


def _package_for(root):
    """The loaded package, reloaded whenever its files changed.

    Keyed on the same fingerprint the disk cache uses: a checkout or an edit
    in another editor changes it just as the server's own writes do, and a
    view must never be computed from a package that is no longer on disk.
    """
    from ..package import load
    from .cache import fingerprint

    stamp = fingerprint(root)
    if _stamps.get(root) != stamp or root not in _packages:
        _packages[root] = load(root)
        _stamps[root] = stamp
        _watch_renames(root, _packages[root])
    return _packages[root]


# A shape renamed by typing in the .ttl leaves its asserts behind. Between two
# reads of a package, a shape vanishing as one saying exactly the same appears
# is that rename; it is kept until the next save offers to carry them along.
_shape_prints = {}
_pending_renames = {}


def _rename_baseline(uri):
    """The shapes as they are on disk now, before the editor's change is saved.

    Views are served from the disk cache, so the package may never be loaded
    before the first save -- and a rename needs a "before" to be seen. Opening
    or first changing a file of the package is the last moment the disk still
    holds it.
    """
    root = package_root(_uri_to_path(uri))
    if root is None or root in _shape_prints:
        return
    try:
        from ..cooked.rename import shape_prints
        package = _package_for(root)
        _shape_prints.setdefault(root, shape_prints(package))
    except Exception:                              # noqa: BLE001 -- a hint, never a failure
        pass


def _watch_renames(root, package):
    from ..cooked.rename import renamed_pairs, shape_prints

    try:
        now = shape_prints(package)
    except Exception:                              # noqa: BLE001 -- a hint, never a failure
        return
    before = _shape_prints.get(root)
    _shape_prints[root] = now
    if before is not None:
        for pair in renamed_pairs(before, now):
            if pair not in _pending_renames.setdefault(root, []):
                _pending_renames[root].append(pair)


def _offer_renames(ls, root):
    """After a save: for each rename typed into the file, what still names
    the old shape, sent to the client to offer carrying it along."""
    from ..cooked.rename import follow_plan

    package = _package_for(root)
    for old, new in _pending_renames.pop(root, []):
        try:
            plan = follow_plan(package, old, new)
        except Exception:                          # noqa: BLE001
            continue
        if plan:
            shapes = package.files('shapes')
            ls.protocol.notify('semforge/shapeRenamed', dict(
                plan, uri=_path_to_uri(shapes[0] if shapes else os.path.join(root, 'shacl.ttl'))))


def _type_hierarchy(package):
    """[{iri, label, parent}] for every entity type, parent '' at the root."""
    from rdflib import URIRef
    from rdflib.namespace import RDFS

    from ..cooked.choices import entity_types

    entries = entity_types(package)[0]
    known = {entry.iri for entry in entries}
    out = []
    for entry in entries:
        parents = sorted(str(p) for p in package.knowledge.objects(
            URIRef(entry.iri), RDFS.subClassOf) if str(p) in known)
        out.append({'iri': entry.iri, 'label': entry.label,
                    'parent': parents[0] if parents else ''})
    return out


@server.feature('semforge/tree')
def cooked_tree(ls, params):
    """The cooked constraint tree for a package."""
    from ..cooked import build_tree

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'roots': [], 'error': 'not a SemForge package'}
    try:
        def compute():
            package = _package_for(root)
            return {'root': root,
                    'roots': [_serialise(node) for node in build_tree(package)],
                    # The hierarchy the summary (Types) tree is drawn as.
                    'types': _type_hierarchy(package)}
        return _view(root, 'constraints', compute, params)
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
        'datasets': list(node.datasets),
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
        return _view(root, 'model', lambda: {
            'root': root,
            'roots': [_serialise_example(n)
                      for n in build_suite(_package_for(root))]}, params)
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


def _serialise_knowledge(node):
    return {
        'kind': node.kind, 'label': node.label, 'detail': node.detail,
        'iri': node.iri, 'definedAt': node.defined_at,
        'shape': node.shape, 'shapeName': node.shape_name,
        'shapeAt': node.shape_at,
        'entity': node.entity, 'entityType': node.entity_type,
        'file': node.file, 'role': node.role,
        'severity': node.severity, 'messages': list(node.messages),
        'children': [_serialise_knowledge(child) for child in node.children],
    }


@server.feature('semforge/init')
def init_package(ls, params):
    """Create a package in a directory, and say what was written.

    The editor asks for this rather than shelling out to the CLI: the scaffold
    is the SDK's business, and a package created by a different code path would
    drift from the one `semforge init` produces.
    """
    from ..package.scaffold import create_package

    target = _uri_to_path(_field(params, 'uri', '')) or _field(params, 'path')
    if not target:
        return {'ok': False, 'error': 'no directory given'}
    try:
        os.makedirs(target, exist_ok=True)
        written = create_package(
            target, name=_field(params, 'name'),
            namespace=_field(params, 'namespace'),
            layout=_field(params, 'layout') or 'grouped')
        package = _package_for(target)
        report = validate_package(package, strict=False)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    _packages.pop(target, None)
    return {'ok': True, 'root': target, 'files': written,
            'open': package.sources['shapes'],
            'constraints': len(report.results),
            'violations': len(report.violations)}


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
        return _view(root, 'knowledge', lambda: {
            'root': root,
            'roots': [_serialise_knowledge(n)
                      for n in build_knowledge(_package_for(root))]}, params)
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


def _serialise_project(node):
    return {
        'kind': node.kind, 'label': node.label, 'detail': node.detail,
        'value': node.value, 'key': node.key, 'doc': node.doc,
        'editable': node.editable, 'definedAt': node.defined_at,
        'severity': node.severity,
        'children': [_serialise_project(child) for child in node.children],
    }


def _cache_row(root):
    from .cache import status

    state = status(root)
    views = len(state['entries'])
    if not views:
        value = 'empty -- the next scan fills it'
    else:
        kib = max(1, round(state['bytes'] / 1024))
        fresh = ('all current' if state['current'] == views
                 else f"{state['current']} of {views} current")
        value = f'{views} view(s) · {kib} KB · {fresh}'
    return {'kind': 'cache', 'label': 'Cache', 'detail':
            'What the views and the Problems panel show, stored per package '
            'and reused while no file of the package (and no SDK file) has '
            'changed. Rescan rebuilds it; deleting it costs only the next '
            'scan.', 'value': value, 'key': '', 'doc': state['path'],
            'editable': False, 'definedAt': '', 'severity': '',
            'children': []}


@server.feature('semforge/cacheStatus')
def cache_status_feature(ls, params):
    from .cache import status

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    return dict(status(root), ok=True, root=root)


@server.feature('semforge/rescan')
def rescan_feature(ls, params):
    """Throw away everything known about the package and analyse it again.

    The escape hatch for the case the fingerprint cannot see -- a change it
    does not track, or a cache somebody distrusts. The views recompute on
    their next request, which the client makes right after.
    """
    from .cache import clear

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    clear(root)
    _packages.pop(root, None)
    _stamps.pop(root, None)
    _publish(ls, _path_to_uri(root))
    return {'ok': True, 'root': root}


@server.feature('semforge/clearCache')
def clear_cache_feature(ls, params):
    """Delete the package's cache; with `contexts`, the downloaded ones too."""
    from .cache import clear

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    freed = clear(root, contexts=bool(_field(params, 'contexts', False)))
    return {'ok': True, 'root': root, 'bytes': freed}


@server.feature('semforge/project')
def project(ls, params):
    """What this package IS: its identity, its settings, what it holds.

    The other three views answer what the package SAYS. Two directories called
    `test` are not the same project, and until this there was nowhere to see
    which one you had open, nor to change anything about it.
    """
    from ..cooked.project import build_project

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'roots': [], 'error': 'not a SemForge package'}
    try:
        payload = _view(root, 'project', lambda: {
            'root': root,
            'roots': [_serialise_project(n)
                      for n in build_project(_package_for(root))]})
        # Added after the cache is read: a row about the cache must never be
        # served FROM it.
        payload['roots'] = payload['roots'] + [_cache_row(root)]
        return payload
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


@server.feature('semforge/setSetting')
def set_setting(ls, params):
    """Write one setting into semforge.yaml, keeping the file's comments.

    Line-based rather than a YAML round-trip: the comments are most of that
    file -- a paragraph above each key saying what it decides -- and a
    round-trip drops every one of them.
    """
    from ..package import config

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    key = _field(params, 'key', '')
    if key not in {entry[0] for entry in config.SPEC}:
        return {'ok': False, 'error': f'{key} is not an editable setting'}
    try:
        where, line = config.set_value(root, key, _field(params, 'value', ''))
    except OSError as exc:
        return {'ok': False, 'error': str(exc)}
    _packages.pop(root, None)                      # it must be re-read
    return {'ok': True, 'file': where, 'line': line,
            'uri': _path_to_uri(where)}


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
    from ..cooked.shapelink import other_entities, value_choices

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
        answer = {'choices': found, 'note': note}
        if _field(params, 'relationship'):
            # Any entity may be the target; the shape's are listed first.
            file = _field(params, 'file') or None
            inside = file and os.path.abspath(file).startswith(os.path.abspath(root) + os.sep)
            answer['others'] = other_entities(package, [c['value'] for c in found],
                                              file if inside else None)
        return answer
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


def _instance_write(ls, params, write):
    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        made = write(package)
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(package.sources['shapes']))
        return dict(made, ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addInstance')
def add_instance_feature(ls, params):
    """Another instance of an attribute, under a new datasetId."""
    from ..cooked.examples import add_instance

    return _instance_write(ls, params, lambda package: add_instance(
        package, _field(params, 'entity'), list(_field(params, 'attributePath') or []),
        _field(params, 'datasetId'), file=_field(params, 'file')))


@server.feature('semforge/setObservedAt')
def set_observed_at_feature(ls, params):
    """One instance's observedAt -- set, changed, or (empty) removed."""
    from ..cooked.examples import set_observed_at

    return _instance_write(ls, params, lambda package: set_observed_at(
        package, _field(params, 'entity'), list(_field(params, 'attributePath') or []),
        _field(params, 'index', 0) or 0, _field(params, 'observedAt', '') or '',
        file=_field(params, 'file')))


@server.feature('semforge/sortObservations')
def sort_observations_feature(ls, params):
    """One datasetId's observations in time order, the latest last."""
    from ..cooked.examples import sort_observations

    return _instance_write(ls, params, lambda package: sort_observations(
        package, _field(params, 'entity'), list(_field(params, 'attributePath') or []),
        _field(params, 'datasetId', '') or '', file=_field(params, 'file')))


@server.feature('semforge/setDatasetId')
def set_dataset_id_feature(ls, params):
    """Change one instance's datasetId (every observation of it)."""
    from ..cooked.examples import set_dataset_id

    return _instance_write(ls, params, lambda package: set_dataset_id(
        package, _field(params, 'entity'), list(_field(params, 'attributePath') or []),
        _field(params, 'old'), _field(params, 'new'), file=_field(params, 'file'),
        index=_field(params, 'index', None)))


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
            # A sub-attribute: the address of the attribute instance it hangs
            # off, as the Model-view row carries it.
            under=list(_field(params, 'under') or []) or None,
            dataset=_field(params, 'underDataset') or None,
            observedAt=_field(params, 'observedAt'),
            datasetId=_field(params, 'datasetId'),
            unitCode=_field(params, 'unitCode') or None)
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


@server.feature('semforge/entityTypes')
def entity_types_feature(ls, params):
    """Every type an entity may be given, as the KNOWLEDGE declares it.

    The editor offers these and nothing else. A type typed by hand is the
    quietest way to break a model -- no shape targets it, so every constraint
    stays silent and the entity reads as validated.
    """
    from ..cooked.choices import entity_types
    from ..cooked.constrain import own_shape

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'types': [], 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        found, hierarchy = entity_types(package)
        if hierarchy is None:
            return {'types': [], 'root': '',
                    'error': 'this package has no entity hierarchy: no shape '
                             'declares an sh:targetClass and semforge.yaml '
                             'declares no entityRoot.'}
        return {'root': hierarchy,
                'types': [{'iri': t.iri, 'term': t.term, 'label': t.label,
                           'parent': t.parent, 'shape': t.shape,
                           # `shape` is the nearest judging shape, inherited
                           # or not; a NEW attribute belongs in its own one.
                           'ownShape': own_shape(package, t.iri) or '',
                           'instances': t.instances, 'isRoot': t.is_root}
                          for t in found]}
    except Exception as exc:                       # noqa: BLE001
        return {'types': [], 'error': str(exc)}


@server.feature('semforge/addEntityType')
def add_entity_type_feature(ls, params):
    """Declare a new entity type in the knowledge, beneath an existing one.

    The way a missing type becomes usable: it is added to the ontology first,
    and the entity is typed with it afterwards.
    """
    from ..cooked.knowledge import add_entity_type

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        made = add_entity_type(package, _field(params, 'name'),
                               _field(params, 'parent'))
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(package.sources['shapes']))
        return dict(made, ok=True, uri=_path_to_uri(made['file']))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addNamespace')
def add_namespace_feature(ls, params):
    """Define a namespace name for the whole package.

    Prefixes are a package-wide table, agreed once. Until this there was no way
    to add to it from the editor at all -- you found semforge.yaml and typed.
    """
    from ..package.prefixes import add_namespace

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = add_namespace(root, _field(params, 'prefix'),
                             _field(params, 'namespace'))
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(_package_for(root).sources['shapes']))
        return dict(made, ok=True, uri=_path_to_uri(made['file']))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/removeNamespace')
def remove_namespace_feature(ls, params):
    """Drop a name from the package's table, unless something needs it.

    A name that is IN USE is not removed on the first ask, even when removing
    it is safe: the answer comes back as a question, with what binds it and
    why it is safe, and the editor asks before trying again with `force`.
    """
    from ..package.prefixes import plan_removal, remove_namespace

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        force = bool(_field(params, 'force', False))
        plan = plan_removal(root, _field(params, 'prefix'), package=package)
        if not plan['removable']:
            return {'ok': False, 'error': plan['reason']}
        if plan['in_use'] and not force:
            return {'ok': False, 'confirm': True, 'detail': plan['reason'],
                    'prefix': plan['prefix'],
                    'files': plan.get('usage', {}).get('files', []),
                    'terms': plan.get('usage', {}).get('terms', 0)}
        gone = remove_namespace(root, _field(params, 'prefix'),
                                package=package, force=True)
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(package.sources['shapes']))
        return {'ok': True, 'prefix': gone['prefix'],
                'namespace': gone['namespace'], 'file': gone['file'],
                'line': gone['line'], 'survivesAs': gone.get('survives_as', ''),
                'survivesVia': gone.get('survives_via', ''),
                'uri': _path_to_uri(gone['file'])}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/deletionPlan')
def deletion_plan_feature(ls, params):
    """What deleting this package would take with it. Deletes nothing.

    The editor does the deleting, because it can move a directory to the trash
    rather than unlinking it. What it cannot do is read the package: which of
    those files are the package, which are somebody's, and whether git has any
    of them.
    """
    from ..package.removal import plan_deletion

    target = _uri_to_path(_field(params, 'uri', '')) or _field(params, 'path', '')
    root = package_root(target) or target
    plan = plan_deletion(root)
    return {
        'ok': not plan.error, 'error': plan.error, 'path': plan.path,
        'name': plan.name, 'files': plan.files, 'bytes': plan.bytes,
        'strangers': plan.strangers, 'nested': plan.nested,
        'inGit': plan.in_git, 'tracked': plan.tracked,
        'untracked': plan.untracked, 'warnings': plan.warnings,
    }


@server.feature('semforge/attributes')
def attributes_feature(ls, params):
    """The attributes an entity of this type may carry, as the knowledge says.

    `rdfs:domain` is the join, and it is inherited: a Plasmacutter carries what
    a Cutter carries and what a Machine carries. Attributes the package
    declares without a domain come back separately rather than being hidden --
    a package may simply not have said.

    With `parent`, it answers the other question instead: which attributes may
    nest INSIDE that one. Sub-attributes are excluded from the entity answer,
    because an entity does not carry them -- `hasTrust` belongs inside
    `hasFilter`, and offering it on a Filter would put it where no shape looks.
    """
    from ..cooked.choices import attributes_for, sub_attributes_for

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'attributes': [], 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)

        def out(entry, scoped):
            return {'iri': entry.iri, 'term': entry.term, 'label': entry.label,
                    'kind': entry.kind, 'domain': entry.domain,
                    'parents': list(entry.parents),
                    'carrierKind': entry.carrier_kind,
                    'comment': entry.comment, 'constrained': entry.constrained,
                    'definedAt': entry.defined_at, 'scoped': scoped}

        # A sub-attribute hangs off an ATTRIBUTE, so it is asked for by naming
        # that attribute rather than an entity type -- and where it may appear
        # is read from the shapes, which is the only place that says it.
        parent = _field(params, 'parent', '')
        if parent:
            return {'parent': parent,
                    'attributes': [out(e, True)
                                   for e in sub_attributes_for(package, parent)]}

        if _field(params, 'all'):
            from ..cooked.choices import attribute_terms
            return {'attributes': [out(e, bool(e.domain_iri))
                                   for e in attribute_terms(package)
                                   if e.ngsild]}
        mine, open_ended = attributes_for(package,
                                          _field(params, 'entityType', ''))
        return {'attributes': [out(e, True) for e in mine] +
                              [out(e, False) for e in open_ended]}
    except Exception as exc:                       # noqa: BLE001
        return {'attributes': [], 'error': str(exc)}


@server.feature('semforge/addAttributeTerm')
def add_attribute_term_feature(ls, params):
    """Declare a new attribute in the knowledge, carried by an entity type."""
    from ..cooked.knowledge import add_attribute_term

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        made = add_attribute_term(package, _field(params, 'name'),
                                  _field(params, 'kind'),
                                  _field(params, 'domain'),
                                  label=_field(params, 'label', ''),
                                  namespace=_field(params, 'namespace') or None)
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(package.sources['shapes']))
        return dict(made, ok=True, uri=_path_to_uri(made['file']))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/attributeNamespaces')
def attribute_namespaces_feature(ls, params):
    """Where a new attribute may live; the carrying type's namespace first."""
    from ..cooked.knowledge import attribute_namespaces

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'namespaces': [], 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        return {'namespaces': attribute_namespaces(
            package, _field(params, 'domain', ''))}
    except Exception as exc:                       # noqa: BLE001
        return {'namespaces': [], 'error': str(exc)}


@server.feature('semforge/attributeRemovalPlan')
def attribute_removal_plan_feature(ls, params):
    """Everything deleting an attribute would touch. Writes nothing."""
    from ..cooked.remove_attribute import plan_attribute_removal

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        plan = plan_attribute_removal(package, _field(params, 'attribute'))
        return dict(plan.as_dict(root), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/removeAttribute')
def remove_attribute_feature(ls, params):
    """Delete an attribute and its removable dependents, all or nothing.

    `force` is the author's yes to the plan they were shown; without it an
    attribute in use is refused, so a client that skipped the plan cannot
    delete more than it displayed.
    """
    from ..cooked.remove_attribute import remove_attribute, remove_declaration

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        # `declarationOnly`: the declaration goes, every use stays.
        remove = remove_declaration if _field(params, 'declarationOnly') \
            else remove_attribute
        plan, notes = remove(package, _field(params, 'attribute'),
                             force=bool(_field(params, 'force', False)))
        _packages.pop(root, None)
        for path in package.files('shapes'):
            _publish(ls, _path_to_uri(path))
        return dict(plan.as_dict(root), ok=True, notes=notes)
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
        if _field(params, 'add'):
            # Add a constraint the attribute does not carry yet (or replace one
            # it does), on the attribute node or on its value.
            from ..cooked.tree import add_constraint

            done = add_constraint(package, shape, chain, parameter,
                                  # An sh:in list arrives as a list of items.
                                  _field(params, 'value') if isinstance(
                                      _field(params, 'value'), list)
                                  else str(_field(params, 'value')),
                                  _field(params, 'layer', 'value') or 'value')
            _packages.pop(root, None)
            _publish(ls, _path_to_uri(done['file']))
            return dict(done, ok=True)
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


@server.feature('semforge/attributeOptions')
def attribute_options_feature(ls, params):
    """The attributes that may be added to a shape, each with its state.

    `free` ones can be added; `here` and `inherited` ones are listed anyway, so
    the picker can say WHY an attribute the author expected is not offered
    rather than leaving them to wonder whether it was declared at all.
    """
    from ..cooked.constrain import (attribute_options, shape_targets,
                                    sub_attribute_options)

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'options': [], 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        shape = _field(params, 'shape')
        parent_path = list(_field(params, 'parentPath') or [])
        if parent_path:
            # Inside an attribute: what may nest there, and the attribute
            # itself as the carrier a NEW sub-attribute is declared for.
            return {'options': sub_attribute_options(package, shape, parent_path),
                    'targets': [parent_path[-1]], 'carrier': parent_path[-1]}
        # The targets let the picker's "New attribute..." declare the new term
        # for the type this shape judges, without asking again.
        return {'options': attribute_options(package, shape),
                'targets': shape_targets(package, shape)}
    except Exception as exc:                       # noqa: BLE001
        return {'options': [], 'error': str(exc)}


@server.feature('semforge/addAttributeConstraint')
def add_attribute_constraint_feature(ls, params):
    """Add an attribute to a shape as a complete two-layer property shape.

    `shape` names the shape; `entityType` instead means that type's OWN shape,
    which is what a flow that starts from a type rather than a tree row has.
    """
    from ..cooked.constrain import (add_attribute_constraint,
                                    add_sub_attribute_constraint, own_shape)

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        shape = _field(params, 'shape')
        if not shape:
            entity_type = _field(params, 'entityType', '')
            shape = own_shape(package, entity_type)
            if shape is None:
                return {'ok': False,
                        'error': f'no shape targets {entity_type} itself, so '
                                 f'there is nowhere to constrain it'}
        parent_path = list(_field(params, 'parentPath') or [])
        if parent_path:
            made = add_sub_attribute_constraint(
                package, shape, parent_path, _field(params, 'attribute'),
                required=bool(_field(params, 'required', False)),
                datatype=_field(params, 'datatype') or None,
                value_class=_field(params, 'valueClass') or None)
            _packages.pop(root, None)
            _publish(ls, _path_to_uri(made['file']))
            return dict(made, ok=True, uri=_path_to_uri(made['file']))
        made = add_attribute_constraint(
            package, shape, _field(params, 'attribute'),
            required=bool(_field(params, 'required', False)),
            datatype=_field(params, 'datatype') or None,
            value_class=_field(params, 'valueClass') or None,
            extend_domain=bool(_field(params, 'extendDomain', False)))
        _packages.pop(root, None)                  # the file changed underneath
        _publish(ls, _path_to_uri(made['file']))
        if made.get('domainAdded'):
            for path in _package_for(root).files('knowledge'):
                _publish(ls, _path_to_uri(path))
        return dict(made, ok=True, uri=_path_to_uri(made['file']))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/attributePlaces')
def attribute_places_feature(ls, params):
    """Where an attribute is constrained: each shape and sh:path chain."""
    from ..cooked.constrain import attribute_places

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'places': [], 'error': 'not a SemForge package'}
    try:
        return {'places': attribute_places(_package_for(root),
                                           _field(params, 'attribute'))}
    except Exception as exc:                       # noqa: BLE001
        return {'places': [], 'error': str(exc)}


@server.feature('semforge/typePage')
def type_page_feature(ls, params):
    """Everything about one entity type, for the type page. Cached per type."""
    from ..cooked.typepage import build_type_page

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    entity_type = str(_field(params, 'entityType', '') or '')
    key = 'type-' + re.sub(r'[^A-Za-z0-9_.-]+', '_', entity_type)[-120:]
    try:
        page = _view(root, key, lambda: {
            'page': build_type_page(_package_for(root), entity_type)})
        return dict(page['page'], ok=True, root=root, cached=page['cached'])
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/shapePage')
def shape_page_feature(ls, params):
    """Everything about one shape, whatever it targets. Cached per shape."""
    from ..cooked.shapepage import build_shape_page

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    shape = str(_field(params, 'shape', '') or '')
    key = 'shape-' + re.sub(r'[^A-Za-z0-9_.-]+', '_', shape)[-120:]
    try:
        page = _view(root, key, lambda: {
            'page': build_shape_page(_package_for(root), shape)})
        return dict(page['page'], ok=True, root=root, cached=page['cached'])
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/vocabularyPage')
def vocabulary_page_feature(ls, params):
    """One vocabulary class: its values, their uses, what draws from it."""
    from ..cooked.vocabulary import build_vocabulary_page

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    cls = str(_field(params, 'cls', '') or '')
    key = 'vocab-' + re.sub(r'[^A-Za-z0-9_.-]+', '_', cls)[-120:]
    try:
        page = _view(root, key, lambda: {
            'page': build_vocabulary_page(_package_for(root), cls)})
        return dict(page['page'], ok=True, root=root, cached=page['cached'])
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/vocabularyClasses')
def vocabulary_classes_feature(ls, params):
    """Every vocabulary class, for a picker."""
    from rdflib import URIRef

    from ..cooked.vocabulary import vocabulary_classes
    from ..validate.normalise import curie, local

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'classes': [], 'error': 'not a SemForge package'}
    package = _package_for(root)
    return {'classes': [{'iri': c, 'label': local(c),
                         'term': curie(package.knowledge, URIRef(c))}
                        for c in sorted(vocabulary_classes(package),
                                        key=lambda c: local(c).lower())]}


def _vocabulary_write(params, write):
    """Run one vocabulary write; the views re-read it from the changed files."""
    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        result = write(_package_for(root))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    return dict(result, ok=True)


@server.feature('semforge/addVocabularyClass')
def add_vocabulary_class_feature(ls, params):
    from ..cooked.vocabulary import add_vocabulary_class

    return _vocabulary_write(params, lambda package: add_vocabulary_class(
        package, _field(params, 'name', ''), _field(params, 'namespace', None),
        _field(params, 'parent', None), _field(params, 'label', '') or ''))


@server.feature('semforge/addVocabularyValue')
def add_vocabulary_value_feature(ls, params):
    from ..cooked.vocabulary import add_value

    return _vocabulary_write(params, lambda package: add_value(
        package, _field(params, 'cls', ''), _field(params, 'name', ''),
        _field(params, 'label', '') or '', _field(params, 'namespace', None) or None))


@server.feature('semforge/vocabularyNamespaces')
def vocabulary_namespaces_feature(ls, params):
    """Where a new vocabulary term may live; the usual place first. `near` is
    the class it belongs to or derives from, if any."""
    from ..cooked.vocabulary import vocabulary_namespaces

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'namespaces': [], 'error': 'not a SemForge package'}
    try:
        return {'namespaces': vocabulary_namespaces(
            _package_for(root), _field(params, 'near', '') or None)}
    except Exception as exc:                       # noqa: BLE001
        return {'namespaces': [], 'error': str(exc)}


@server.feature('semforge/setValueLabel')
def set_value_label_feature(ls, params):
    from ..cooked.vocabulary import set_value_label

    return _vocabulary_write(params, lambda package: set_value_label(
        package, _field(params, 'value', ''), _field(params, 'label', '') or ''))


@server.feature('semforge/removeVocabularyValue')
def remove_vocabulary_value_feature(ls, params):
    from ..cooked.vocabulary import remove_value

    return _vocabulary_write(params, lambda package: remove_value(
        package, _field(params, 'value', ''), bool(_field(params, 'force', False))))


@server.feature('semforge/attributeTestOptions')
def attribute_test_options_feature(ls, params):
    """What a test for one attribute of a type can prove."""
    from ..expect.attributecase import attribute_test_options

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        found = attribute_test_options(_package_for(root),
                                       _field(params, 'entityType', ''),
                                       list(_field(params, 'path', []) or []))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    return dict(found, ok=True)


@server.feature('semforge/newAttributeTest')
def new_attribute_test_feature(ls, params):
    """Write a test for one attribute: valid, or one constraint firing."""
    from ..expect.attributecase import new_attribute_test

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = new_attribute_test(_package_for(root), _field(params, 'entityType', ''),
                                  list(_field(params, 'path', []) or []),
                                  str(_field(params, 'purpose', '') or ''),
                                  str(_field(params, 'name', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    return dict(made, ok=True)


@server.feature('semforge/testCaseOptions')
def test_case_options_feature(ls, params):
    """What New test case… can offer: suites, shapes, cases, entities, files."""
    from ..expect.addcase import case_options

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return dict(case_options(_package_for(root)), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addTestCase')
def add_test_case_feature(ls, params):
    """Write and declare a test case, then run it once."""
    from ..expect.addcase import add_test_case

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = add_test_case(_package_for(root), _field(params, 'suite', ''),
                             _field(params, 'expect', 'valid'),
                             _field(params, 'start', 'empty'),
                             str(_field(params, 'source', '') or ''),
                             str(_field(params, 'name', '') or ''),
                             str(_field(params, 'description', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    return dict(made, ok=True)


@server.feature('semforge/units')
def units_feature(ls, params):
    """Every unit the package can say -- the curated Rec 20 set and its own --
    matching `query` when given, and the quantities they measure. With `shape`
    and `path`, also the units that attribute's shape allows; with
    `entityType` and `attribute`, those of the attribute on that type."""
    from ..cooked.units import attribute_units, quantities, search_units

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        answer = {'ok': True, 'units': search_units(package, _field(params, 'query', '') or ''),
                  'quantities': quantities(package), 'allowed': [], 'required': False}
        shape, path = _field(params, 'shape'), list(_field(params, 'path') or [])
        entity_type, attribute = _field(params, 'entityType'), _field(params, 'attribute')
        if shape and path:
            allowed = attribute_units(package, shape, path)
            answer.update(allowed=allowed['codes'], required=allowed['required'])
        elif entity_type and attribute:
            from ..cooked.typepage import build_type_page

            page = build_type_page(package, entity_type)
            row = next((r for r in page.get('attributes', []) if attribute in
                        (r['term'], r['attribute'], r['label'])), None)
            if row is not None:
                answer.update(allowed=row.get('units', []),
                              required=row.get('unitRequired', False))
        return answer
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addUnit')
def add_unit_feature(ls, params):
    """A unit of the package's own, in its knowledge."""
    from ..cooked.units import add_unit

    return _package_write(ls, params, lambda package: add_unit(
        package, _field(params, 'code', ''), _field(params, 'name', ''),
        _field(params, 'quantity', ''), _field(params, 'symbol', '') or '',
        _field(params, 'namespace', None) or None))


@server.feature('semforge/setUnits')
def set_units_feature(ls, params):
    """Which units an attribute's instances may say, in its shape."""
    from ..cooked.units import set_units

    return _package_write(ls, params, lambda package: set_units(
        package, _field(params, 'shape'), list(_field(params, 'path') or []),
        list(_field(params, 'codes') or []), bool(_field(params, 'required', False))))


@server.feature('semforge/setUnitCode')
def set_unit_code_feature(ls, params):
    """One instance's unitCode in the data -- every observation of it."""
    from ..cooked.units import set_unit_code

    return _instance_write(ls, params, lambda package: set_unit_code(
        package, _field(params, 'entity'), list(_field(params, 'attributePath') or []),
        _field(params, 'datasetId', '') or '', _field(params, 'code', '') or '',
        file=_field(params, 'file')))


@server.feature('semforge/severityLevels')
def severity_levels_feature(ls, params):
    """The severity levels a constraint may name, and the classes they come from."""
    from ..cooked.severity import levels, severity_classes

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        return {'ok': True, 'levels': levels(package), 'classes': severity_classes(package)}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/setSeverity')
def set_severity_feature(ls, params):
    """Set (or clear) sh:severity on an attribute constraint or a SPARQL constraint."""
    from ..cooked.severity import set_severity

    holder = _field(params, 'holder', None)
    query = _field(params, 'query', '')

    def write(package):
        index = holder
        if index is None and query:
            # The shape page knows its queries by their text, not their place.
            from ..cooked.sparqlbench import holders
            index = next((h['index'] for h in holders(package, _field(params, 'shape', ''))
                          if h['query'].strip() == str(query).strip()), None)
            if index is None:
                raise ValueError('that SPARQL query is not on the shape any more')
        return set_severity(
            package, _field(params, 'shape', ''), list(_field(params, 'path', []) or []) or None,
            int(index) if index is not None else None, _field(params, 'severity', '') or None)

    return _package_write(ls, params, write)


@server.feature('semforge/addSeverityLevel')
def add_severity_level_feature(ls, params):
    """A new severity level: an individual of sh:Severity or a class derived from it."""
    from ..cooked.severity import add_level

    return _package_write(ls, params, lambda package: add_level(
        package, _field(params, 'cls', ''), _field(params, 'name', ''),
        _field(params, 'label', ''), _field(params, 'namespace', None) or None))


@server.feature('semforge/addSeverityClass')
def add_severity_class_feature(ls, params):
    """A new severity class, derived from sh:Severity or a class derived from it."""
    from ..cooked.severity import add_class

    return _package_write(ls, params, lambda package: add_class(
        package, _field(params, 'name', ''), _field(params, 'parent', '') or None,
        _field(params, 'namespace', None) or None))


@server.feature('semforge/linkSeverityClass')
def link_severity_class_feature(ls, params):
    """Declare a class already used for severities a kind of sh:Severity."""
    from ..cooked.severity import link_class

    return _package_write(ls, params, lambda package: link_class(
        package, _field(params, 'cls', '')))


@server.feature('semforge/removeCaseValue')
def remove_case_value_feature(ls, params):
    """Remove an attribute -- or one instance, observation or metadata key of
    it -- from an entity in a case or the model."""
    from ..cooked.examples import remove_value

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        done = remove_value(_package_for(root), _field(params, 'entity', ''),
                            list(_field(params, 'path', []) or []),
                            _field(params, 'file', '') or None,
                            _field(params, 'dataset', None))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    _packages.pop(root, None)
    _publish(ls, _path_to_uri(done['file']))
    return dict(done, ok=True)


@server.feature('semforge/deleteCasePlan')
def delete_case_plan_feature(ls, params):
    """What deleting a case (or a whole suite) removes, and the evidence it costs."""
    from ..expect.deletecase import delete_plan

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return dict(delete_plan(_package_for(root), _field(params, 'case', ''),
                                _field(params, 'suite', '')), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/deleteCase')
def delete_case_feature(ls, params):
    """Delete a case (its file and its entry), or a whole suite."""
    from ..expect.deletecase import delete_cases

    return _package_write(ls, params, lambda package: delete_cases(
        package, _field(params, 'case', ''), _field(params, 'suite', '')))


@server.feature('semforge/cloneCase')
def clone_case_feature(ls, params):
    """A copy of a case in its suite -- expecting the opposite, or the same --
    then run once."""
    from ..expect.addcase import clone_case

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = clone_case(_package_for(root), _field(params, 'case', ''),
                          _field(params, 'expect', 'opposite'),
                          str(_field(params, 'name', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    _packages.pop(root, None)
    return dict(made, ok=True)


@server.feature('semforge/modelPage')
def model_page_feature(ls, params):
    """The model data as cards, each entity with its violations; edited like
    a case. Cached like every view, so a reopen is cheap."""
    from ..cooked.casepage import build_model_page

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        page = _view(root, 'model-page', lambda: {'page': build_model_page(_package_for(root))})
        return dict(page['page'], ok=True, root=root, cached=page['cached'])
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/newCase')
def new_case_feature(ls, params):
    """Start a case that makes a shape fire (the shape page's New case…)."""
    from ..expect.newcase import new_case

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = new_case(_package_for(root), str(_field(params, 'shape', '') or ''),
                        str(_field(params, 'name', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    return dict(made, ok=True)


@server.feature('semforge/addShape')
def add_shape_feature(ls, params):
    """Write a new node shape with one target; constraints come from its page."""
    from ..cooked.shapes import add_shape

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = add_shape(_package_for(root), _field(params, 'name', ''),
                         _field(params, 'targetKind', ''), _field(params, 'target', ''),
                         _field(params, 'namespace', None))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    _packages.pop(root, None)
    _publish(ls, _path_to_uri(made['file']))
    return dict(made, ok=True)


def _target_write(ls, params, write):
    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        done = write(_package_for(root))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    _packages.pop(root, None)
    _publish(ls, _path_to_uri(done['file']))
    return dict(done, ok=True)


@server.feature('semforge/sparqlBench')
def sparql_bench_feature(ls, params):
    """The SPARQL workbench: one query of a shape, the data it runs over.
    Not cached: it is opened to be changed."""
    from ..cooked.sparqlbench import MAIN, bench_page

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        page = bench_page(_package_for(root), str(_field(params, 'shape', '') or ''),
                          _field(params, 'index'), _field(params, 'source') or MAIN,
                          _field(params, 'query'), _field(params, 'kind'))
        return dict(page, ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/sparqlRun')
def sparql_run_feature(ls, params):
    """Run an edited query the way validation would. Writes nothing."""
    from ..cooked.sparqlbench import MAIN, run_query

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return run_query(_package_for(root), str(_field(params, 'shape', '') or ''),
                         _field(params, 'index') or 0, _field(params, 'source') or MAIN,
                         str(_field(params, 'query', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/sparqlInspect')
def sparql_inspect_feature(ls, params):
    """The query taken apart, text untouched: every variable of every row its
    WHERE makes, and which FILTER part dropped the rows it dropped."""
    from ..cooked.sparqlbench import MAIN, inspect

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return inspect(_package_for(root), str(_field(params, 'shape', '') or ''),
                       _field(params, 'index') or 0, _field(params, 'source') or MAIN,
                       str(_field(params, 'query', '') or ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/sparqlSave')
def sparql_save_feature(ls, params):
    """Write the edited query over the one the workbench opened."""
    from ..cooked.sparqlbench import save_query

    return _target_write(ls, params, lambda package: save_query(
        package, str(_field(params, 'shape', '') or ''), _field(params, 'index') or 0,
        str(_field(params, 'query', '') or ''), str(_field(params, 'expected', '') or '')))


@server.feature('semforge/sparqlRemovalPlan')
def sparql_removal_plan_feature(ls, params):
    """What removing one SPARQL query would take with it: asked first."""
    from ..cooked.sparqlbench import removal_plan

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        shape = str(_field(params, 'shape', '') or '')
        return dict(removal_plan(package, shape, _holder_index(package, shape, params)), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/sparqlRemove')
def sparql_remove_feature(ls, params):
    """Remove one SPARQL constraint or rule -- and, when asked, the asserts
    no remaining query could satisfy."""
    from ..cooked.sparqlbench import remove_holder

    shape = str(_field(params, 'shape', '') or '')
    return _target_write(ls, params, lambda package: remove_holder(
        package, shape, _holder_index(package, shape, params),
        str(_field(params, 'expected', '') or ''), bool(_field(params, 'dropAsserts'))))


def _holder_index(package, shape, params):
    """Which of a shape's queries: by its text when the page knows it (pages
    list them in graph order, not file order), else by `holder`."""
    from ..cooked.sparqlbench import holders, pick
    from ..errors import PackageError

    found = holders(package, shape)
    if not found:
        raise PackageError('this shape has no SPARQL query')
    return pick(found, _field(params, 'holder'), _field(params, 'query'),
                _field(params, 'kind'))['index']


@server.feature('semforge/addSparqlConstraint')
def add_sparql_constraint_feature(ls, params):
    """+ SPARQL constraint: a skeleton that fires on nothing, to be written in
    the workbench."""
    from ..cooked.sparqlbench import add_constraint

    return _target_write(ls, params, lambda package: add_constraint(
        package, str(_field(params, 'shape', '') or ''), str(_field(params, 'message', '') or '')))


@server.feature('semforge/addTarget')
def add_target_feature(ls, params):
    """One more thing a shape selects (the shape page's + Target)."""
    from ..cooked.shapes import add_target

    return _target_write(ls, params, lambda package: add_target(
        package, _field(params, 'shape', ''), _field(params, 'targetKind', ''),
        _field(params, 'target', '')))


@server.feature('semforge/removeTarget')
def remove_target_feature(ls, params):
    """One target off a shape (the shape page's Remove)."""
    from ..cooked.shapes import remove_target

    return _target_write(ls, params, lambda package: remove_target(
        package, _field(params, 'shape', ''), _field(params, 'targetKind', ''),
        _field(params, 'value', '')))


@server.feature('semforge/mergePlan')
def merge_plan_feature(ls, params):
    """The shapes one may be merged into, and -- given one -- what it would do."""
    from ..cooked.merge import candidates, plan

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        package = _package_for(root)
        shape = _field(params, 'shape', '')
        into = _field(params, 'into', '')
        if not into:
            return {'ok': True, 'candidates': candidates(package, shape)}
        found = plan(package, shape, into)
        return {'ok': True, 'said': found['said'], 'asserts': found['asserts'],
                'name': found['name'], 'intoName': found['intoName']}
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/mergeShape')
def merge_shape_feature(ls, params):
    """Fold one shape into another with the same targets."""
    from ..cooked.merge import merge_shape

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        done = merge_shape(_package_for(root), _field(params, 'shape', ''),
                           _field(params, 'into', ''))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    _packages.pop(root, None)
    for path in _package_for(root).files('shapes'):
        _publish(ls, _path_to_uri(path))
    return dict(done, ok=True)


@server.feature('semforge/renameShapePlan')
def rename_shape_plan_feature(ls, params):
    """What renaming a shape would change, or why it cannot be renamed so."""
    from ..cooked.rename import rename_plan

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return dict(rename_plan(_package_for(root), _field(params, 'shape', ''),
                                _field(params, 'name', '')), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


def _package_write(ls, params, write):
    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        done = write(_package_for(root))
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}
    _packages.pop(root, None)
    # SemForge's own rename carried everything along, as asked: the shapes
    # it changed are the new baseline, not a rename to offer again.
    _shape_prints.pop(root, None)
    _pending_renames.pop(root, None)
    for path in _package_for(root).files('shapes'):
        _publish(ls, _path_to_uri(path))
    return dict(done, ok=True)


@server.feature('semforge/shapeAt')
def shape_at_feature(ls, params):
    """The node shape whose name is under the cursor -- what F2 renames.

    The range is the name's local part (`StateOnCutterShape` of
    `iffBaseShacl:StateOnCutterShape`, the whole `<IRI>` when written out),
    so the rename box shows what is being renamed. A term inside a string --
    a SPARQL body -- is not offered: the rename carries those along anyway.
    """
    from rdflib import URIRef
    from rdflib.namespace import RDF, SH

    from ..rdfio.turtle_index import terms

    uri = _field(params, 'uri', '')
    root = package_root(_uri_to_path(uri))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        document = ls.workspace.get_text_document(uri)
        text = document.source
    except Exception:                              # noqa: BLE001 -- not open: read it
        with open(_uri_to_path(uri), encoding='utf-8') as handle:
            text = handle.read()
    line, character = int(_field(params, 'line', 0)), int(_field(params, 'character', 0))
    package = _package_for(root)
    for term in terms(text):
        if term.quoted or term.line - 1 != line or \
                not term.column <= character <= term.column + len(term.raw):
            continue
        if (URIRef(term.iri), RDF.type, SH.NodeShape) not in package.shapes:
            break
        start = term.column + (term.raw.index(':') + 1 if not term.raw.startswith('<') else 0)
        return {'ok': True, 'shape': term.iri, 'placeholder': _local(term.iri),
                'range': {'start': {'line': line, 'character': start},
                          'end': {'line': line, 'character': term.column + len(term.raw)}}}
    return {'ok': False, 'error': 'F2 renames a shape: put the cursor on its name'}


@server.feature('semforge/followRename')
def follow_rename_feature(ls, params):
    """Carry along what a shape renamed in the .ttl left behind: its asserts,
    residues pinned under the old name, and (asked) its suite folder."""
    from ..cooked.rename import follow_rename

    return _package_write(ls, params, lambda package: follow_rename(
        package, _field(params, 'shape', ''), _field(params, 'newIri', ''),
        suite=bool(_field(params, 'suite', False))))


@server.feature('semforge/renameShape')
def rename_shape_feature(ls, params):
    """Rename a shape everywhere it is named: .ttl, asserts, residues, suite."""
    from ..cooked.rename import rename_shape

    return _package_write(ls, params, lambda package: rename_shape(
        package, _field(params, 'shape', ''), _field(params, 'name', ''),
        suite=bool(_field(params, 'suite', False))))


@server.feature('semforge/renameCase')
def rename_case_feature(ls, params):
    """Rename a test case's file, and the entries that name it."""
    from ..cooked.rename import rename_case

    return _package_write(ls, params, lambda package: rename_case(
        package, _field(params, 'case', ''), _field(params, 'name', '')))


@server.feature('semforge/deleteShapePlan')
def delete_shape_plan_feature(ls, params):
    """What deleting a shape would remove, or why it cannot be deleted."""
    from ..cooked.shapedelete import delete_plan

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        return dict(delete_plan(_package_for(root), _field(params, 'shape', '')), ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/deleteShape')
def delete_shape_feature(ls, params):
    """Delete a shape; with `asserts`, the asserts naming it; with `cases`,
    the cases that assert nothing else."""
    from ..cooked.shapedelete import delete_shape

    return _package_write(ls, params, lambda package: delete_shape(
        package, _field(params, 'shape', ''), asserts=bool(_field(params, 'asserts', False)),
        cases=bool(_field(params, 'cases', False))))


@server.feature('semforge/renameSuite')
def rename_suite_feature(ls, params):
    """Rename a suite folder, and the includes that reach into it."""
    from ..cooked.rename import rename_suite

    return _package_write(ls, params, lambda package: rename_suite(
        package, _field(params, 'suite', ''), _field(params, 'name', '')))


@server.feature('semforge/shapes')
def shapes_feature(ls, params):
    """Every named shape with its target in words, for the Shapes view."""
    from ..cooked.shapes import build_shapes

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'roots': [], 'error': 'not a SemForge package'}
    try:
        return _view(root, 'shapes', lambda: {
            'root': root, 'roots': build_shapes(_package_for(root))}, params)
    except Exception as exc:                       # noqa: BLE001
        return {'roots': [], 'error': str(exc)}


@server.feature('semforge/editAttribute')
def edit_attribute_feature(ls, params):
    """Change an attribute's presence or what its value must be (type page)."""
    from ..cooked.constrain import edit_attribute

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        counts, value = _field(params, 'counts'), _field(params, 'value')
        made = edit_attribute(_package_for(root), _field(params, 'shape'),
                              list(_field(params, 'path') or []),
                              presence=_field(params, 'presence') or None,
                              value={k: _field(value, k) for k in ('kind', 'datatype', 'valueClass')
                                     if _field(value, k) is not None} if value else None,
                              # A nested object arrives as pygls's Object too.
                              counts={'min': _field(counts, 'min'), 'max': _field(counts, 'max')}
                              if counts else None)
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(made['file']))
        return dict(made, ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/removeProperty')
def remove_property_feature(ls, params):
    """Take one attribute's property shape out of one shape."""
    from ..cooked.constrain import remove_property_group

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = remove_property_group(_package_for(root), _field(params, 'shape'),
                                     list(_field(params, 'path') or []))
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(made['file']))
        return dict(made, ok=True)
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/casePage')
def case_page_feature(ls, params):
    """One test case: its claims, whether they hold, its data. Cached."""
    from ..cooked.casepage import build_case_page

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    case = str(_field(params, 'case', '') or '')
    key = 'case-' + re.sub(r'[^A-Za-z0-9_.-]+', '_', case)[-120:]
    try:
        page = _view(root, key, lambda: {
            'page': build_case_page(_package_for(root), case)})
        return dict(page['page'], ok=True, root=root, cached=page['cached'])
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/health')
def health_feature(ls, params):
    """The package health page: figures, and what needs attention first."""
    from ..cooked.health import build_health

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        page = _view(root, 'health', lambda: {'page': build_health(_package_for(root))})
        result = dict(page['page'], ok=True, root=root, cached=page['cached'])
        # The cache figures are read live: a page about the cache must not be
        # served from it.
        from .cache import status
        state = status(root)
        result['tiles'] = dict(result['tiles'], cacheViews=len(state['entries']),
                               cacheCurrent=state['current'])
        return result
    except Exception as exc:                       # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


@server.feature('semforge/addAssert')
def add_assert_feature(ls, params):
    """Assert a firing a case did not claim (the case page's "Assert it")."""
    from ..expect.store import add_assert

    root = package_root(_uri_to_path(_field(params, 'uri', '')))
    if root is None:
        return {'ok': False, 'error': 'not a SemForge package'}
    try:
        made = add_assert(_package_for(root), _field(params, 'case'),
                          _field(params, 'constraint'),
                          _field(params, 'resource', '') or '')
        _packages.pop(root, None)
        _publish(ls, _path_to_uri(made['file']))
        return dict(made, ok=True)
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
