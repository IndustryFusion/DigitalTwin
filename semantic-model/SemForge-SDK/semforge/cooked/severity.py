"""Severity: how serious a constraint's result is when it fires.

SHACL's own vocabulary is the model. `sh:Severity` is the class; its three
instances `sh:Violation` (the default: the data does not conform),
`sh:Warning` and `sh:Info` are always offered, whether or not a package
declares them. A package adds its own levels as individuals of `sh:Severity`
or of a class derived from it (`ex:AlarmLevel rdfs:subClassOf sh:Severity`,
and `ex:critical a ex:AlarmLevel`), and may derive further classes from
those. A level is said by its `rdfs:label` -- the word the platform carries
-- or its name.

A class whose individuals a package already uses as severities but which is
not linked to `sh:Severity` (the kms's `base:SeverityClass`) still counts,
and the Problems panel offers to link it.

`sh:severity` may sit on any shape: on a SPARQL constraint, and on each
property shape -- one per attribute constraint here. Absent, SHACL's default
`sh:Violation` applies.
"""

import json
import re

from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH

from ..errors import PackageError
from ..validate.normalise import curie, local

BUILTIN = [
    (SH.Violation, 'violation', 'the data does not conform -- the default'),
    (SH.Warning, 'warning', 'reported; the data still conforms'),
    (SH.Info, 'info', 'for information only'),
]
DEFAULT = SH.Violation


def _graphs(package):
    return (package.knowledge, package.shapes)


def _subclasses_of(package, root):
    """`root` and every class declared below it, transitively."""
    found, todo = {root}, [root]
    while todo:
        cls = todo.pop()
        for graph in _graphs(package):
            for sub in graph.subjects(RDFS.subClassOf, cls):
                if isinstance(sub, URIRef) and sub not in found:
                    found.add(sub)
                    todo.append(sub)
    return found


def _used(package):
    """{severity IRI: number of shapes and constraints naming it}."""
    used = {}
    for value in package.shapes.objects(None, SH.severity):
        if isinstance(value, URIRef):
            used[value] = used.get(value, 0) + 1
    return used


def severity_classes(package):
    """[{iri, term, linked, parent}] -- sh:Severity, the classes derived from
    it, then classes whose individuals are used as severities without being
    linked to it."""
    linked = _subclasses_of(package, SH.Severity)
    out = [{'iri': str(SH.Severity), 'term': 'sh:Severity', 'linked': True, 'parent': ''}]
    for cls in sorted(linked - {SH.Severity}, key=str):
        parent = next((p for g in _graphs(package) for p in g.objects(cls, RDFS.subClassOf)
                       if p in linked), SH.Severity)
        out.append({'iri': str(cls), 'term': curie(package.knowledge, cls), 'linked': True,
                    'parent': curie(package.knowledge, parent) if parent != SH.Severity
                    else 'sh:Severity'})
    unlinked = set()
    for value in _used(package):
        for graph in _graphs(package):
            for cls in graph.objects(value, RDF.type):
                if isinstance(cls, URIRef) and cls not in linked and \
                        cls not in (OWL.NamedIndividual, OWL.Thing, RDFS.Resource):
                    unlinked.add(cls)
    for cls in sorted(unlinked, key=str):
        out.append({'iri': str(cls), 'term': curie(package.knowledge, cls), 'linked': False,
                    'parent': ''})
    return out


def _label(package, iri):
    for graph in _graphs(package):
        value = graph.value(iri, RDFS.label)
        if value is not None:
            return str(value)
    name = local(iri)
    name = re.sub(r'^severity', '', name, flags=re.IGNORECASE) or name
    return name[:1].lower() + name[1:]


def levels(package):
    """Every severity a constraint may name: SHACL's three, then each class's
    individuals. [{iri, term, label, class, builtin, used, note}]."""
    used = _used(package)
    out = [{'iri': str(iri), 'term': 'sh:' + local(iri), 'label': label,
            'class': 'sh:Severity', 'builtin': True,
            'used': used.get(iri, 0), 'note': note}
           for iri, label, note in BUILTIN]
    seen = {str(iri) for iri, _, _ in BUILTIN}
    for cls in severity_classes(package):
        members = set()
        for graph in _graphs(package):
            members |= {s for s in graph.subjects(RDF.type, URIRef(cls['iri']))
                        if isinstance(s, URIRef)}
        for member in sorted(members, key=lambda m: _label(package, m)):
            if str(member) in seen:
                continue
            seen.add(str(member))
            out.append({'iri': str(member), 'term': curie(package.knowledge, member),
                        'label': _label(package, member), 'class': cls['term'],
                        'builtin': False, 'used': used.get(member, 0), 'note': ''})
    return out


def describe(package, value):
    """A severity value as a reader says it: {iri, label, known}. None is
    SHACL's default, violation."""
    builtin = {str(iri): label for iri, label, _ in BUILTIN}
    if value is None:
        return {'iri': '', 'label': builtin[str(DEFAULT)], 'known': True}
    iri = str(value)
    known = any(level['iri'] == iri for level in levels(package))
    return {'iri': iri, 'label': builtin.get(iri) or _label(package, URIRef(iri)),
            'known': known}


# --- writing ---------------------------------------------------------------------------

def _resolve_level(package, severity):
    if not severity:
        return None
    for level in levels(package):
        if severity in (level['iri'], level['term'], level['label']):
            return URIRef(level['iri'])
    raise PackageError(f'{severity} is not a severity level of this package: SHACL\'s '
                       'violation, warning or info, or an individual of sh:Severity or a '
                       'class derived from it')


def set_severity(package, shape, path=None, holder=None, severity=None):
    """Set (or, with no `severity`, remove) sh:severity on one constraint of
    `shape`: the attribute constraint at `path` (its property shape), or the
    SPARQL constraint at `holder` (its position among the shape's queries).
    Removed, SHACL's default -- violation -- applies. Returns {'file', 'severity'}.
    """
    from .constrain import _add_line, _group_in, _remove_line
    from .knowledge import _turtle_name
    from .tree import _write_verified
    from ..rdfio import set_parameter

    level = _resolve_level(package, severity)
    index = package.index('shapes')
    path_file = index.file_for(URIRef(str(shape)))
    if path_file is None:
        raise PackageError(f'{shape} is not a shape written in this package')
    with open(path_file, encoding='utf-8') as handle:
        text = handle.read()
    if holder is not None:
        from .sparqlbench import _bodies
        bodies, text, path_file = _bodies(package, shape)
        if not 0 <= int(holder) < len(bodies):
            raise PackageError(f'{local(str(shape))} has no SPARQL query {holder}')
        kind, group = bodies[int(holder)]
        if kind != 'constraint':
            raise PackageError('a SPARQL rule derives data; it has no severity')
    elif path:
        group = _group_in(text, str(shape), list(path))
    else:
        raise PackageError('which constraint? an attribute path or a SPARQL query')

    name = _turtle_name(text, SH.severity)
    current = group.parameter(name) or group.parameter('sh:severity')
    if level is None:
        if current is None:
            return {'file': path_file, 'severity': ''}
        updated = _remove_line(text, group, name if group.parameter(name) else 'sh:severity')
    elif current is not None:
        updated = set_parameter(text, group, name if group.parameter(name) else 'sh:severity',
                                _turtle_name(text, level))
    else:
        updated = _add_line(text, group, name, _turtle_name(text, level))
    _write_verified(path_file, updated)
    return {'file': path_file, 'severity': str(level) if level is not None else ''}


def _knowledge_file(package, near=None):
    index = package.index('knowledge')
    if near is not None:
        found = index.file_for(URIRef(near))
        if found:
            return found
    return package.sources['knowledge']


def _namespace(package, near=None):
    """Where a new level or class goes: beside `near`, else beside the
    package's other vocabulary, else its entity namespace."""
    from .knowledge import _namespace_of
    from .vocabulary import vocabulary_classes

    for candidate in ([near] if near else []) + vocabulary_classes(package):
        if candidate and not str(candidate).startswith(str(SH)):
            return _namespace_of(URIRef(candidate))
    from .choices import entity_types
    roots = entity_types(package)[0]
    if roots:
        return _namespace_of(URIRef(roots[0].iri))
    raise PackageError('this package declares nothing to put a severity beside')


NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_-]*')


def _space(package, namespace, near):
    from .knowledge import minting_namespace

    return minting_namespace(package, namespace) if namespace else _namespace(package, near)


def _append(package, path, lines):
    from .tree import _write_verified

    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    _write_verified(path, text.rstrip('\n') + '\n\n' + lines + '\n')


def add_level(package, cls, name, label='', namespace=None):
    """A new severity level: `name` an individual of `cls` (sh:Severity or a
    class derived from it), labelled `label`. `namespace` (a prefix or an IRI),
    or a prefix written into `name`, chooses where it goes -- never a standard
    vocabulary's. Returns {'iri', 'term'}."""
    from .knowledge import _turtle_name, bind_namespace, split_name

    name, namespace = split_name(name, namespace)

    classes = {c['iri']: c for c in severity_classes(package)}
    wanted = next((c for c in classes.values() if cls in (c['iri'], c['term'])), None)
    if wanted is None:
        raise PackageError(f'{cls} is not sh:Severity or a class derived from it')
    if not NAME.fullmatch(str(name or '')):
        raise PackageError(f'{name!r} is not a name: a letter first, then letters, digits, '
                           '"_" and "-"')
    near = None if wanted['iri'] == str(SH.Severity) else wanted['iri']
    iri = URIRef(_space(package, namespace, near) + name)
    if any((iri, None, None) in g for g in _graphs(package)):
        raise PackageError(f'{name} is already declared')
    path = _knowledge_file(package, near)
    bind_namespace(package, path, iri)
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    parts = [f'{_turtle_name(text, iri)} a {_turtle_name(text, OWL.NamedIndividual)}, '
             f'{_turtle_name(text, URIRef(wanted["iri"]))}']
    if label:
        parts.append(f'    {_turtle_name(text, RDFS.label)} {json.dumps(str(label))}')
    _append(package, path, ' ;\n'.join(parts) + ' .')
    return {'iri': str(iri), 'term': curie(package.knowledge, iri)}


def add_class(package, name, parent=None, namespace=None):
    """A new severity class derived from `parent` (sh:Severity by default, or
    one already derived from it), in `namespace` if given. Returns
    {'iri', 'term'}."""
    from .knowledge import _turtle_name, bind_namespace, split_name

    name, namespace = split_name(name, namespace)

    parent = parent or str(SH.Severity)
    classes = {c['iri']: c for c in severity_classes(package) if c['linked']}
    wanted = next((c for c in classes.values() if parent in (c['iri'], c['term'])), None)
    if wanted is None:
        raise PackageError(f'{parent} is not sh:Severity or a class derived from it')
    if not NAME.fullmatch(str(name or '')) or not name[:1].isupper():
        raise PackageError(f'{name!r} is not a class name: a capital first, then letters, '
                           'digits, "_" and "-"')
    near = None if wanted['iri'] == str(SH.Severity) else wanted['iri']
    iri = URIRef(_space(package, namespace, near) + name)
    if any((iri, None, None) in g for g in _graphs(package)):
        raise PackageError(f'{name} is already declared')
    path = _knowledge_file(package, near)
    bind_namespace(package, path, iri)
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    _append(package, path, f'{_turtle_name(text, iri)} a {_turtle_name(text, OWL.Class)} ;\n'
            f'    {_turtle_name(text, RDFS.subClassOf)} {_turtle_name(text, URIRef(wanted["iri"]))} .')
    return {'iri': str(iri), 'term': curie(package.knowledge, iri)}


def link_class(package, cls):
    """Declare a class already used for severities a kind of sh:Severity."""
    from .knowledge import _turtle_name
    from .tree import _write_verified
    from ..rdfio import TurtleIndex

    iri = URIRef(str(cls))
    path = package.index('knowledge').file_for(iri)
    if path is None:
        raise PackageError(f'{cls} is not declared in the knowledge')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    block = TurtleIndex(text).block_for(str(iri))
    if block is None:
        raise PackageError(f'{cls} is not a statement of its own')
    statement = text[block.start:block.end].rstrip()
    if not statement.endswith('.'):
        raise PackageError(f'{cls}: its statement does not end where expected')
    addition = f' ;\n    {_turtle_name(text, RDFS.subClassOf)} {_turtle_name(text, SH.Severity)} .'
    updated = text[:block.start] + statement[:-1].rstrip() + addition + text[block.start + len(statement):]
    _write_verified(path, updated)
    return {'file': path}


__all__ = ['levels', 'severity_classes', 'describe', 'set_severity', 'add_level',
           'add_class', 'link_class', 'BUILTIN', 'DEFAULT']
