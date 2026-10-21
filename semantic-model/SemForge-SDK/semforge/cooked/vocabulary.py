"""Vocabulary classes: the value lists the model draws from, and their care.

A vocabulary class -- MachineState, Wasteclass -- is a closed list of named
values. An attribute constrained `sh:class base:MachineState` must hold one
of them, a SPARQL rule tests for `base:state_ON`, a case writes
`{"@id": "base:state_OFF"}`. So a value is never just a declaration: it is
used in the shapes, in the queries and in the data, and the questions a
vocabulary raises are about those uses -- which value is never exercised,
what a deletion would break, which attributes draw from the list.

`build_vocabulary_page` answers them for one class. The writes keep the
knowledge file's layout: a new class or value is appended as one statement,
a label is changed in place, and a deleted value takes exactly its own
statement with it -- each verified by parsing the result.
"""

import json
import os
import re

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH

from ..errors import PackageError
from ..rdfio import TurtleIndex
from ..validate.normalise import curie, local

NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_.-]*$')
VALUE_LAYER = {'https://uri.etsi.org/ngsi-ld/hasValue',
               'https://uri.etsi.org/ngsi-ld/hasObject'}


# --- which classes are vocabularies -------------------------------------------------

def vocabulary_classes(package):
    """Every declared class that is not an entity type, by IRI."""
    from .choices import classify_classes

    _, knowledge, _ = classify_classes(package)
    return [str(c) for c in knowledge]


def _resolve_class(package, cls):
    wanted = str(cls or '').strip('<>')
    # SHACL's class of severities is a vocabulary every package has -- its
    # three levels are SHACL's own -- and the one a package extends.
    if wanted in (str(SH.Severity), 'sh:Severity'):
        return SH.Severity
    for iri in vocabulary_classes(package):
        if wanted in (iri, curie(package.knowledge, URIRef(iri)), local(iri)):
            return URIRef(iri)
    raise PackageError(f'{cls} is not a vocabulary class in this package')


def _values(package, cls):
    return sorted((s for s in package.knowledge.subjects(RDF.type, cls)
                   if isinstance(s, URIRef)), key=lambda s: local(s).lower())


# --- where things are used -----------------------------------------------------------

def _owning_shape(graph, node):
    """(top-level shape, [sh:path, ...]) for a node inside a shape's body --
    through sh:property, sh:node and the RDF lists of sh:or / sh:and / sh:in."""
    chain, current, seen = [], node, set()
    while not isinstance(current, URIRef):
        if current in seen:
            return None, chain
        seen.add(current)
        path = graph.value(current, SH.path)
        if path is not None and not isinstance(path, Literal):
            chain.insert(0, path)
        parent = next(graph.subjects(SH.property, current), None) or \
            next(graph.subjects(SH.node, current), None)
        if parent is None:
            # A member of an RDF list: walk back to its head, then to the
            # statement that holds the list (sh:or, sh:in, ...).
            cell = next(graph.subjects(RDF.first, current), None)
            while cell is not None and next(graph.subjects(RDF.rest, cell), None) is not None:
                cell = next(graph.subjects(RDF.rest, cell))
            parent = next((s for s, p in graph.subject_predicates(cell)
                           if p != RDF.rest), None) if cell is not None else None
        if parent is None:
            return None, chain
        current = parent
    return current, chain


def _attribute_of(chain):
    for path in chain:
        if isinstance(path, URIRef) and str(path) not in VALUE_LAYER:
            return local(path)
    return ''


def _constrained_by(package, cls, values):
    """[{shape, shapeName, attribute, how}] -- the constraints that draw their
    values from this class (sh:class) or list some of its values (sh:in)."""
    graph = package.shapes
    found = {}
    for holder in graph.subjects(SH['class'], cls):
        shape, chain = _owning_shape(graph, holder)
        if shape is not None:
            found[(str(shape), _attribute_of(chain), 'sh:class')] = None
    wanted = set(values)
    for cell, member in graph.subject_objects(RDF.first):
        if member not in wanted:
            continue
        head = cell
        while next(graph.subjects(RDF.rest, head), None) is not None:
            head = next(graph.subjects(RDF.rest, head))
        for holder in graph.subjects(SH['in'], head):
            shape, chain = _owning_shape(graph, holder)
            if shape is not None:
                found[(str(shape), _attribute_of(chain), 'sh:in')] = None
    return [{'shape': shape, 'shapeName': curie(graph, URIRef(shape)),
             'attribute': attribute, 'how': how}
            for shape, attribute, how in sorted(found)]


def _uses(package, value):
    """{data, shapes, queries, knowledge, places} for one value. Declarations
    are not uses; a query mentioning it is reported with its shape."""
    from ..editor.references import references_to

    shape_files = {os.path.abspath(p) for p in package.files('shapes')}
    knowledge_files = {os.path.abspath(p) for p in package.files('knowledge')}
    blocks = {}

    def subject_at(path, line):
        if path not in blocks:
            with open(path, encoding='utf-8') as handle:
                blocks[path] = TurtleIndex(handle.read()).blocks
        return next((b.subject for b in blocks[path]
                     if b.start_line <= line <= b.end_line), '')

    counts = {'data': 0, 'shapes': 0, 'queries': 0, 'knowledge': 0}
    places = []
    for reference in references_to(package, [str(value)]):
        if reference.declaration:
            continue
        where = os.path.abspath(reference.path)
        if where in shape_files:
            kind = 'queries' if reference.quoted else 'shapes'
            owner = subject_at(reference.path, reference.line)
        elif where in knowledge_files:
            kind, owner = 'knowledge', subject_at(reference.path, reference.line)
        else:
            kind, owner = 'data', ''
        counts[kind] += 1
        places.append({'kind': kind, 'at': f'{reference.path}:{reference.line}',
                       'file': os.path.basename(reference.path),
                       'line': reference.line,
                       'owner': curie(package.shapes if kind in ('shapes', 'queries')
                                      else package.knowledge, URIRef(owner))
                       if owner.startswith(('http', 'urn:')) else owner})
    return dict(counts, total=sum(counts.values()), places=places)


def _short(graph, term):
    if isinstance(term, Literal):
        return str(term)
    return curie(graph, term) if isinstance(term, URIRef) else str(term)


# --- the page ----------------------------------------------------------------------

def _spoken(name):
    """A property's local name as words: isValidFor -> valid for."""
    words = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name).lower().split()
    if len(words) > 1 and words[0] in ('is', 'has'):
        words = words[1:]
    return ' '.join(words) or name


def _severity_page(package):
    """sh:Severity as a vocabulary page: SHACL's three levels -- read-only,
    SHACL declares them -- then the package's own, and the classes derived
    from it; drawn from by every constraint that names a severity."""
    from .severity import BUILTIN, DEFAULT, levels

    graph = package.knowledge
    index = package.index('knowledge')
    rows = [{'iri': str(iri), 'name': local(iri), 'term': 'sh:' + local(iri), 'label': label,
             'properties': [], 'uses': _uses(package, iri), 'definedAt': '', 'builtin': True,
             'note': note + (' (the default)' if iri == DEFAULT and 'default' not in note else '')}
            for iri, label, note in BUILTIN]
    for level in levels(package):
        if level['builtin'] or level['class'] != 'sh:Severity':
            continue
        iri = URIRef(level['iri'])
        rows.append({'iri': level['iri'], 'name': local(iri), 'term': level['term'],
                     'label': str(graph.value(iri, RDFS.label) or ''), 'properties': [],
                     'uses': _uses(package, iri), 'definedAt': index.locator(iri) or ''})
    drawn = []
    for node, _ in package.shapes.subject_objects(SH.severity):
        shape, chain = (node, []) if isinstance(node, URIRef) else _owning_shape(package.shapes, node)
        if shape is None:
            shape = next((s for s in package.shapes.subjects(SH.sparql, node)), None)
        if shape is None:
            continue
        drawn.append({'shape': str(shape), 'shapeName': curie(package.shapes, shape),
                      'attribute': ' / '.join(local(p) for p in chain if isinstance(p, URIRef)),
                      'how': 'sh:severity'})
    drawn.sort(key=lambda d: (d['shapeName'], d['attribute']))
    vocabularies = set(vocabulary_classes(package))
    derived = sorted((str(c) for c in graph.subjects(RDFS.subClassOf, SH.Severity)
                      if isinstance(c, URIRef)), key=lambda c: local(c).lower())
    # SHACL's own levels are never "unused": not naming one is no gap.
    unused = [r for r in rows if not r['uses']['total'] and not r.get('builtin')]
    return {
        'iri': str(SH.Severity), 'label': 'Severity', 'term': 'sh:Severity',
        'comment': 'SHACL\'s class of severities: how serious a result is when a constraint '
                   'fires. Its three levels are SHACL\'s own; add levels here, or derive a '
                   'class of your own.',
        'definedAt': '', 'namespace': '', 'severity': True, 'builtin': True,
        'parents': [],
        'subclasses': [{'iri': c, 'label': local(c), 'page': c in vocabularies} for c in derived],
        'values': rows, 'constrainedBy': drawn, 'relations': [],
        'summary': {'values': len(rows), 'unused': len(unused),
                    'inData': sum(1 for r in rows if r['uses']['data']),
                    'constraints': len(drawn)},
    }


def build_vocabulary_page(package, cls):
    """The payload the vocabulary page renders. Reads only."""
    graph = package.knowledge
    cls = _resolve_class(package, cls)
    if cls == SH.Severity:
        return _severity_page(package)
    index = package.index('knowledge')
    values = _values(package, cls)
    vocabularies = set(vocabulary_classes(package))
    from .choices import classify_classes
    entities = {str(c) for c in classify_classes(package)[0]}

    rows = []
    for value in values:
        label = graph.value(value, RDFS.label)
        # `name` is what a reader says (base:isValidFor -> valid for); an
        # entity type as the object opens its type page.
        properties = [{'property': _short(graph, p), 'value': _short(graph, o),
                       'name': _spoken(local(p)), 'shortValue': local(o) if isinstance(o, URIRef)
                       else str(o),
                       'link': str(o) if str(o) in vocabularies else '',
                       'type': str(o) if str(o) in entities else ''}
                      for p, o in sorted(graph.predicate_objects(value), key=str)
                      if p not in (RDF.type, RDFS.label)]
        uses = _uses(package, value)
        rows.append({
            'iri': str(value), 'name': local(value), 'term': curie(graph, value),
            'label': str(label) if label is not None else '',
            'properties': properties, 'uses': uses,
            'definedAt': index.locator(value) or ''})

    constrained = _constrained_by(package, cls, values)
    relations = []
    from .choices import domains_of

    shared = {s for s in graph.subjects(RDFS.domain, None) if cls in domains_of(graph, s)}
    for prop in sorted(shared | set(graph.subjects(RDFS.range, cls)), key=str):
        named = domains_of(graph, prop)
        target = graph.value(prop, RDFS.range)
        relations.append({'name': curie(graph, prop), 'iri': str(prop),
                          'domain': ' or '.join(_short(graph, d) for d in named),
                          'range': _short(graph, target) if target is not None else '',
                          'definedAt': index.locator(prop) or ''})
    parents = [str(p) for p in graph.objects(cls, RDFS.subClassOf) if isinstance(p, URIRef)]
    children = [str(c) for c in graph.subjects(RDFS.subClassOf, cls) if isinstance(c, URIRef)]
    comment = graph.value(cls, RDFS.comment) or graph.value(cls, RDFS.label)

    unused = [r['name'] for r in rows if not r['uses']['total']]
    from .severity import severity_classes
    severity = any(c['iri'] == str(cls) and c['linked'] for c in severity_classes(package))
    return {
        'iri': str(cls), 'label': local(cls), 'term': curie(graph, cls),
        # A class of severity levels: derived classes are made from its page.
        'severity': severity,
        'comment': str(comment) if comment is not None else '',
        'definedAt': index.locator(cls) or '',
        'namespace': _namespace(cls),
        'parents': [{'iri': p, 'label': local(p), 'page': p in vocabularies}
                    for p in parents],
        'subclasses': [{'iri': c, 'label': local(c), 'page': c in vocabularies}
                       for c in sorted(children, key=lambda c: local(c).lower())],
        'values': rows, 'constrainedBy': constrained, 'relations': relations,
        'summary': {'values': len(rows), 'unused': len(unused),
                    'inData': sum(1 for r in rows if r['uses']['data']),
                    'constraints': len(constrained)},
    }


# --- the writes ----------------------------------------------------------------------

def _namespace(iri):
    text = str(iri)
    cut = max(text.rfind('#'), text.rfind('/'))
    return text[:cut + 1] if cut >= 0 else text


def _check_name(name):
    name = str(name or '').strip()
    if not NAME.match(name):
        raise PackageError(f'"{name}" is not a usable name: letters, digits, '
                           f'"_", "-" and ".", starting with a letter')
    return name


def _append(path, lines, iri):
    """Append one statement and prove it parses and declares `iri`."""
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    statement = ' ;\n'.join(lines) + ' .\n'
    updated = text + ('' if text.endswith('\n') else '\n') + '\n' + statement
    graph = Graph().parse(data=updated, format='turtle')
    if (URIRef(iri), None, None) not in graph:
        raise PackageError(f'{local(iri)} did not come out declared; nothing written')
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(updated)
    return len(updated[:len(updated) - len(statement)].splitlines()) + 1


def default_namespace(package, near=None):
    """Where a new vocabulary term goes unless told otherwise.

    Beside `near` (the class it belongs to or derives from); a level of
    sh:Severity in the package's own vocabulary namespace, never SHACL's;
    with nothing near, the namespace most of the package's vocabulary uses.
    """
    if near:
        cls = _resolve_class(package, near)
        if cls != SH.Severity:
            return _namespace(cls)
        from .severity import _namespace as severity_namespace
        return severity_namespace(package)
    spaces = [_namespace(c) for c in vocabulary_classes(package)
              if not c.startswith(str(SH))]
    if not spaces:
        raise PackageError('name a namespace: this package has no vocabulary '
                           'class to take one from')
    return max(set(spaces), key=spaces.count)


def vocabulary_namespaces(package, near=None):
    """Where a new vocabulary term may live, the likeliest first: the default
    (see `default_namespace`), then the namespaces that already hold
    vocabulary, then the package's others. Standard vocabularies and the
    shapes' own namespace are never offered."""
    from ..package.prefixes import STANDARD, names_by_namespace
    from .knowledge import node_shapes

    try:
        default = default_namespace(package, near)
    except PackageError:
        default = ''
    held = {}
    terms = set(vocabulary_classes(package)) | {
        str(s) for s in package.knowledge.subjects(RDF.type, OWL.NamedIndividual)
        if isinstance(s, URIRef)}
    for term in terms:
        held[_namespace(term)] = held.get(_namespace(term), 0) + 1
    standard = set(STANDARD.values())
    shapes_only = {_namespace(shape) for shape in node_shapes(package.shapes)} - set(held)
    out = []
    names = names_by_namespace(package.path)
    for space, prefix in names.items():
        if space in standard or not prefix or (space in shapes_only and space != default):
            continue
        out.append({'prefix': prefix, 'namespace': space, 'terms': held.get(space, 0),
                    'default': space == default})
    if default and default not in names:
        out.append({'prefix': '', 'namespace': default, 'terms': held.get(default, 0),
                    'default': True})
    out.sort(key=lambda e: (not e['default'], -e['terms'], e['prefix']))
    return out


def _space_for(package, namespace, near=None):
    from .knowledge import minting_namespace

    return minting_namespace(package, namespace) if namespace \
        else default_namespace(package, near)


def add_vocabulary_class(package, name, namespace=None, parent=None, label=''):
    """Declare a new vocabulary class: `ns:Name a owl:Class`, optionally
    under another vocabulary class and with a label. `namespace` (a prefix or
    an IRI), or a prefix written into `name`, chooses where it goes."""
    from .knowledge import _turtle_name, bind_namespace, split_name

    name, namespace = split_name(name, namespace)
    name = _check_name(name)
    if parent:
        parent = _resolve_class(package, parent)
    space = _space_for(package, namespace, parent)
    iri = URIRef(space + name)
    if (iri, None, None) in package.knowledge:
        raise PackageError(f'{curie(package.knowledge, iri)} is already declared')

    index = package.index('knowledge')
    path = (index.file_for(parent) if parent is not None else None) or \
        package.sources['knowledge']
    bind_namespace(package, path, iri)
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    lines = [f'{_turtle_name(text, iri)} a {_turtle_name(text, OWL.Class)}']
    if parent is not None:
        lines.append(f'    {_turtle_name(text, RDFS.subClassOf)} {_turtle_name(text, parent)}')
    if label:
        lines.append(f'    {_turtle_name(text, RDFS.label)} {json.dumps(label)}')
    line = _append(path, lines, iri)
    return {'iri': str(iri), 'term': curie(package.knowledge, iri),
            'file': path, 'line': line}


def add_value(package, cls, name, label='', namespace=None):
    """Add a value to a vocabulary: `ns:name a owl:NamedIndividual, Class`,
    in the class's file -- and its namespace, as the kms writes its values,
    unless `namespace` (or a prefix written into `name`) says otherwise."""
    from .knowledge import _turtle_name, bind_namespace, split_name

    cls = _resolve_class(package, cls)
    name, namespace = split_name(name, namespace)
    name = _check_name(name)
    if cls == SH.Severity:
        # A level of SHACL's class goes in the package's namespace, not SHACL's.
        from .severity import add_level
        made = add_level(package, 'sh:Severity', name, label, namespace)
        path = package.index('knowledge').file_for(URIRef(made['iri'])) or \
            package.sources['knowledge']
        return dict(made, file=path, line=1)
    iri = URIRef(_space_for(package, namespace, cls) + name)
    if (iri, None, None) in package.knowledge:
        raise PackageError(f'{curie(package.knowledge, iri)} is already declared')
    index = package.index('knowledge')
    path = index.file_for(cls) or package.sources['knowledge']
    bind_namespace(package, path, iri)
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    lines = [f'{_turtle_name(text, iri)} a {_turtle_name(text, OWL.NamedIndividual)},'
             f'\n        {_turtle_name(text, cls)}']
    if label:
        lines.append(f'    {_turtle_name(text, RDFS.label)} {json.dumps(label)}')
    line = _append(path, lines, iri)
    return {'iri': str(iri), 'term': curie(package.knowledge, iri),
            'file': path, 'line': line}


LABEL = re.compile(r'(rdfs:label\s+)("(?:[^"\\]|\\.)*"(?:@[A-Za-z-]+)?)')


def set_value_label(package, value, label):
    """Change (or add, or with '' remove) a value's rdfs:label, in place."""
    from .knowledge import _turtle_name

    value = URIRef(str(value).strip('<>'))
    index = package.index('knowledge')
    path = index.file_for(value)
    if path is None:
        raise PackageError(f'{local(value)} is not declared in a knowledge file')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    block = TurtleIndex(text).block_for(str(value))
    statement = block.text(text)
    labels = list(LABEL.finditer(statement))
    if len(labels) > 1:
        raise PackageError(f'{local(value)} has {len(labels)} labels; edit them '
                           f'in the .ttl')
    if labels:
        found = labels[0]
        if label:
            statement = statement[:found.start(2)] + json.dumps(label) + \
                statement[found.end(2):]
        else:
            # Take the label and the ';' that joins it to the statement.
            before = statement[:found.start()].rstrip()
            after = statement[found.end():].lstrip()
            if before.endswith(';'):
                before = before[:-1].rstrip()
                statement = before + (' ' + after if after.startswith('.') else
                                      ' ;\n    ' + after.lstrip(';').lstrip())
            else:
                statement = before + ' ' + after.lstrip(';').lstrip()
    elif label:
        body = statement.rstrip()
        if not body.endswith('.'):
            raise PackageError(f'cannot find the end of {local(value)}\'s statement')
        statement = body[:-1].rstrip() + \
            f' ;\n    {_turtle_name(text, RDFS.label)} {json.dumps(label)} .'
    else:
        return {'file': path, 'changed': False}
    updated = text[:block.start] + statement + text[block.end:]
    graph = Graph().parse(data=updated, format='turtle')
    got = [str(o) for o in graph.objects(value, RDFS.label)]
    if got != ([label] if label else []):
        raise PackageError('the label did not come out as written; nothing changed')
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(updated)
    return {'file': path, 'changed': True}


def remove_value(package, value, force=False):
    """Delete a value's declaration. Refused while anything uses it, unless
    `force`: a use left behind names an undeclared term, which the editor
    then reports. Returns {'file', 'left': uses still pointing at it}."""
    from .remove_attribute import _knowledge_without

    value = URIRef(str(value).strip('<>'))
    uses = _uses(package, value)
    if uses['total'] and not force:
        where = ', '.join(sorted({f"{p['file']}:{p['line']}" for p in uses['places']})[:5])
        raise PackageError(f'{local(value)} is used in {uses["total"]} place(s) '
                           f'({where}); confirm to delete it anyway')
    for path in package.files('knowledge'):
        updated = _knowledge_without(path, str(value))
        if updated is not None:
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(updated)
            return {'file': path, 'left': uses['total']}
    raise PackageError(f'{local(value)} is not declared in a knowledge file')
