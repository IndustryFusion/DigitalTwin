"""Constructing NGSI-LD that is legal by construction.

An attribute is not free-form JSON. Its `type` decides which key carries the
payload, and getting that pairing wrong produces something that parses, looks
plausible, and means nothing:

    Property      value       a literal, or {"@id": …} for a vocabulary term
    Relationship  object      an entity IRI, never a literal
    GeoProperty   value       GeoJSON
    JsonProperty  json        arbitrary JSON, opaque to the graph
    ListProperty  valueList   an ordered list

The failure this prevents is a real one from this repo's own history: writing
`{"object": …}` where the model says Property meant a SPARQL rule's join
predicate refused the row, silently, and the tests stayed green because a
constraint that never runs looks exactly like one that passes.

So the builder takes the kind and puts the payload where that kind says it
goes, and refuses a pairing that cannot mean anything.
"""

from collections import OrderedDict

from ..errors import PackageError

PAYLOAD_KEY = {
    'Property': 'value',
    'GeoProperty': 'value',
    'Relationship': 'object',
    'JsonProperty': 'json',
    'ListProperty': 'valueList',
}
KINDS = tuple(PAYLOAD_KEY)
METADATA = ('observedAt', 'unitCode', 'datasetId')


def payload_key(kind):
    try:
        return PAYLOAD_KEY[kind]
    except KeyError:
        raise PackageError(
            f'{kind!r} is not an NGSI-LD attribute type. '
            f'Expected one of: {", ".join(KINDS)}')


def coerce(kind, value):
    """The payload for a kind, refusing what that kind cannot carry."""
    if kind == 'Relationship':
        if isinstance(value, dict):
            target = value.get('object') or value.get('@id')
        else:
            target = value
        if not isinstance(target, str) or not target:
            raise PackageError(
                'a Relationship points at an entity, so its object must be an '
                f'IRI; got {value!r}')
        return target

    if kind == 'ListProperty':
        if not isinstance(value, list):
            raise PackageError(
                f'a ListProperty carries an ordered list; got {value!r}')
        return value

    if kind == 'JsonProperty':
        if not isinstance(value, (dict, list)):
            raise PackageError(
                f'a JsonProperty carries a JSON object or array; got {value!r}')
        return value

    if isinstance(value, dict) and set(value) - {'@id'}:
        raise PackageError(
            'a Property value is a literal or a single {"@id": …} reference; '
            f'got {value!r}')
    return value


def attribute(kind, value, **metadata):
    """One NGSI-LD attribute instance.

    Key order follows how these are written by hand -- type first, then the
    payload -- so a generated attribute sits in the file looking like its
    neighbours rather than announcing itself.
    """
    instance = OrderedDict()
    instance['type'] = kind
    instance[payload_key(kind)] = coerce(kind, value)
    for name in METADATA:
        if metadata.get(name) not in (None, ''):
            instance[name] = metadata[name]
    for name, extra in metadata.items():
        if name not in METADATA and extra is not None:
            instance[name] = extra
    return instance


def entity(identifier, entity_type, context=None, attributes=None):
    """One NGSI-LD entity, with the keys NGSI-LD requires in the usual order."""
    if not identifier:
        raise PackageError('an entity needs an id')
    if not entity_type:
        raise PackageError(f'{identifier}: an entity needs a type')

    out = OrderedDict()
    if context:
        out['@context'] = context
    out['id'] = identifier
    out['type'] = entity_type
    for name, value in (attributes or {}).items():
        out[name] = value
    return out


def kind_for_shape(package, entity_type, attribute_name):
    """What the SHAPES say this attribute should be, or None.

    A value shape constraining ngsild:hasObject means a Relationship; one on
    ngsild:hasValue means a Property. Reading it from the model beats asking
    the author, who is the one person the model is supposed to be helping.
    """
    from rdflib.namespace import SH

    from ..rdfio import property_blocks
    from ..validate.shapes import node_shapes

    index = package.index('shapes')

    wanted = attribute_name.rsplit('/', 1)[-1].split(':')[-1]
    for shape in node_shapes(package.shapes):
        targets = [str(t).rsplit('/', 1)[-1]
                   for t in package.shapes.objects(shape, SH.targetClass)]
        if entity_type and entity_type.split(':')[-1] not in targets:
            continue
        path, block = index.block_for(shape)
        if block is None:
            continue
        for group in property_blocks(index.source_of(path), block):
            if group.path.split(':')[-1] != wanted:
                continue
            for child in group.children:
                if child.path.endswith('hasObject'):
                    return 'Relationship'
                if child.path.endswith('hasValueList'):
                    return 'ListProperty'
                if child.path.endswith('hasJSON'):
                    return 'JsonProperty'
                if child.path.endswith('hasValue'):
                    return 'Property'
    return None
