"""The link from a piece of data to the shape that judges it.

The two trees describe the same model from opposite ends, and an author moves
between them constantly: this attribute looks wrong, what does the shape say --
and the other way. Without a link that is a manual search through shacl.ttl for
a property shape whose `sh:path` matches.

Three things live here:

  * where the property shape for (type, attribute) is declared;
  * creating an empty one when there is none, so there is somewhere to add
    constraints;
  * what values the shape allows, which is what a value picker should offer.

The empty shape is deliberately incomplete and the capability check says so --
`SF-CAP-004`, a property shape that declares no constraint would compile to
nothing. That is the right report: a stub is a visible TODO, not a finished
shape, and export refuses until something is added to it.
"""

from rdflib import URIRef
from rdflib.namespace import RDF, RDFS, SH

from ..errors import PackageError
from ..rdfio import property_blocks
from ..validate.normalise import curie, local
from ..validate.shapes import node_shapes

VALUE_PATHS = ('ngsild:hasValue', 'ngsild:hasObject', 'ngsild:hasValueList',
               'ngsild:hasJSON')


def _line_of(text, offset):
    return text.count('\n', 0, offset) + 1


def _targets(package, shape):
    return {local(t) for t in package.shapes.objects(shape, SH.targetClass)}


def _type_names(package, entity_type):
    """The type and everything above it, so an inherited shape still matches.

    A shape on Machine governs a Filter's hasState: sh:targetClass reaches
    subclasses, so the jump has to look up the hierarchy or it lands nowhere
    for every inherited attribute.
    """
    wanted = (entity_type or '').split(':')[-1]
    names = {wanted}
    for cls in package.knowledge.subjects(RDF.type, None):
        if local(cls) != wanted:
            continue
        pending = [cls]
        while pending:
            current = pending.pop()
            for parent in package.knowledge.objects(current, RDFS.subClassOf):
                if local(parent) not in names:
                    names.add(local(parent))
                    pending.append(parent)
    for subject, obj in package.knowledge.subject_objects(RDFS.subClassOf):
        if local(subject) == wanted:
            names.add(local(obj))
            pending = [obj]
            while pending:
                current = pending.pop()
                for parent in package.knowledge.objects(current, RDFS.subClassOf):
                    if local(parent) not in names:
                        names.add(local(parent))
                        pending.append(parent)
    return names


def find_property_shape(package, entity_type, attribute):
    """Where (type, attribute) is constrained, or None.

    Returns a dict with the shape, its file:line, whether the shape targets the
    type directly or an ancestor, and the value slot it constrains.
    """
    index = package.index('shapes')
    wanted = attribute.rsplit('/', 1)[-1].split(':')[-1]
    names = _type_names(package, entity_type)
    own = (entity_type or '').split(':')[-1]

    best = None
    for shape in node_shapes(package.shapes):
        targets = _targets(package, shape)
        if not (targets & names):
            continue
        # Which FILE holds it matters as much as which line: a role may be a
        # directory, and the jump has to open the document the shape is in.
        path, block = index.block_for(shape)
        if block is None:
            continue
        text = index.source_of(path)
        for group in property_blocks(text, block):
            if group.path.split(':')[-1] != wanted:
                continue
            slot = next((c.path for c in group.children
                         if c.path in VALUE_PATHS), '')
            found = {
                'shape': str(shape),
                'shapeName': curie(package.shapes, shape),
                'file': path,
                'line': _line_of(text, group.start),
                'inherited': own not in targets,
                'slot': slot,
                'exists': True,
            }
            # A shape targeting the type itself beats one it inherits from.
            if own in targets:
                return found
            best = best or found
    return best


def shape_for_type(package, entity_type):
    """A node shape targeting this type exactly, or None."""
    own = (entity_type or '').split(':')[-1]
    for shape in node_shapes(package.shapes):
        if own in _targets(package, shape):
            return shape
    return None


def ensure_property_shape(package, entity_type, attribute):
    """Find the property shape for (type, attribute), creating a stub if absent.

    The stub carries only `sh:path`. That is intentionally not a valid shape --
    the capability check reports it as compiling to nothing -- because an empty
    property shape is a place to put constraints, and pretending otherwise
    would hide the fact that it does not constrain anything yet.
    """
    from ..rdfio import add_property_constraint

    found = find_property_shape(package, entity_type, attribute)
    if found:
        # An inherited shape counts as existing: the constraint IS declared,
        # just further up. Writing a local copy here would be an override, and
        # overriding is a decision with its own command -- doing it silently on
        # a "show me the rule" click would fork the model behind the author's
        # back.
        return found, 'found'

    target = shape_for_type(package, entity_type)
    if target is None:
        raise PackageError(
            f'no shape targets {entity_type}; create one in shacl.ttl first. '
            f'(An attribute cannot be constrained without a shape to hang it '
            f'on, and guessing which shape you meant would be worse than '
            f'asking.)')

    holder = package.index('shapes').file_for(target)
    if holder is None:
        raise PackageError(f'{target} is not in any shapes file')
    updated = add_property_constraint(holder, str(target), attribute, [])
    with open(holder, 'w', encoding='utf-8') as handle:
        handle.write(updated)

    from ..package import load
    fresh = load(package.path)
    again = find_property_shape(fresh, entity_type, attribute)
    if again is None:
        raise PackageError(
            f'added a property shape for {attribute} but cannot find it again')
    return again, 'created'


def value_choices(package, entity_type, attribute, limit=None, search=None):
    """What the shape allows as a value for this attribute.

    A `sh:class` on the value says the value IRI is an INDIVIDUAL of that class,
    so the options are its individuals -- not the classes, which is what a
    constraint editor offers. For a relationship the individuals are entities,
    so existing entity ids of that class are offered instead.
    """
    found = find_property_shape(package, entity_type, attribute)
    if found is None:
        return [], 'no shape constrains this attribute'

    index = package.index('shapes')
    shape = URIRef(found['shape'])
    wanted = attribute.rsplit('/', 1)[-1].split(':')[-1]

    declared = None
    slot = ''
    path, block = index.block_for(shape)
    text = index.source_of(path) if path else ''
    for group in property_blocks(text, block or []):
        if group.path.split(':')[-1] != wanted:
            continue
        for child in group.children:
            if child.path in VALUE_PATHS:
                slot = child.path
                parameter = child.parameters.get('sh:class')
                if parameter:
                    declared = parameter[2].strip()
    if declared is None:
        return [], f'{found["shapeName"]} declares no sh:class for {wanted}'

    expanded = _expand(package, declared)
    if expanded is None:
        return [], f'cannot resolve {declared}'

    if slot.endswith('hasObject'):
        options = _entities_of(package, expanded)
        note = '' if options else f'no entity of type {local(expanded)} exists yet'
    else:
        options = _individuals_of(package, expanded)
        note = '' if options else f'{local(expanded)} has no individuals'

    if search:
        needle = search.strip().lower()
        options = [o for o in options if needle in o['label'].lower()
                   or needle in o['value'].lower()]
    total = len(options)
    if limit and total > limit:
        options = options[:limit]
        note = f'showing {limit} of {total}; keep typing to narrow'
    return options, note


def _expand(package, term):
    if term.startswith('<') and term.endswith('>'):
        return URIRef(term[1:-1])
    prefix, _, name = term.partition(':')
    for bound, namespace in package.shapes.namespaces():
        if bound == prefix:
            return URIRef(str(namespace) + name)
    return None


def _subclasses(package, cls):
    found = {cls}
    pending = [cls]
    while pending:
        for sub in package.knowledge.subjects(RDFS.subClassOf, pending.pop()):
            if sub not in found:
                found.add(sub)
                pending.append(sub)
    return found


def _individuals_of(package, cls):
    out = []
    for member in sorted(_subclasses(package, cls), key=str):
        for individual in sorted(package.knowledge.subjects(RDF.type, member),
                                 key=str):
            if not isinstance(individual, URIRef):
                continue
            label = next(package.knowledge.objects(individual, RDFS.label), None)
            out.append({
                'value': '{"@id": "%s"}' % curie(package.shapes, individual),
                'label': local(individual),
                'detail': f'{local(member)}' + (f' · {label}' if label else ''),
            })
    return out


def _entities_of(package, cls):
    """Entity ids in the package's model that are of this class."""
    names = {local(c) for c in _subclasses(package, cls)}
    out = []
    for subject, obj in package.model.subject_objects(RDF.type):
        if local(obj) in names and str(subject).startswith(('urn:', 'http')):
            out.append({'value': str(subject), 'label': str(subject),
                        'detail': local(obj)})
    return sorted(out, key=lambda o: o['label'])
