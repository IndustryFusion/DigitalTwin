"""The NGSI-LD attribute kinds, in one place.

Each kind says where its payload goes: the key in NGSI-LD JSON, and the
predicate that key expands to in RDF -- which is what a SHACL shape nests and
what a SPARQL query reads through:

    Property          value        ngsild:hasValue        a literal, or a vocabulary IRI
    GeoProperty       value        ngsild:hasValue        GeoJSON
    Relationship      object       ngsild:hasObject       an entity IRI
    JsonProperty      json         ngsild:hasJSON         opaque JSON
    ListProperty      valueList    ngsild:hasValueList    an ordered list of values
    ListRelationship  objectList   ngsild:hasObjectList   an ordered list of entities
    LanguageProperty  languageMap  ngsild:hasLanguageMap  strings by language
    VocabProperty     vocab        ngsild:hasVocab        a vocabulary IRI

Every module that needs "which payload goes with which kind" reads it here:
eight hand-kept copies of this list had already drifted apart.
"""

NGSILD = 'https://uri.etsi.org/ngsi-ld/'

# kind -> (JSON key, payload predicate's local name)
KINDS = {
    'Property': ('value', 'hasValue'),
    'GeoProperty': ('value', 'hasValue'),
    'Relationship': ('object', 'hasObject'),
    'JsonProperty': ('json', 'hasJSON'),
    'ListProperty': ('valueList', 'hasValueList'),
    'ListRelationship': ('objectList', 'hasObjectList'),
    'LanguageProperty': ('languageMap', 'hasLanguageMap'),
    'VocabProperty': ('vocab', 'hasVocab'),
}

# The metadata an attribute instance may carry beside its payload.
METADATA = ('observedAt', 'unitCode', 'datasetId')

PAYLOAD_KEY = {kind: key for kind, (key, _) in KINDS.items()}
PAYLOAD_NAME = {kind: name for kind, (_, name) in KINDS.items()}
PAYLOAD_PATH = {kind: NGSILD + name for kind, name in PAYLOAD_NAME.items()}
PAYLOAD_NAMES = tuple(dict.fromkeys(PAYLOAD_NAME.values()))
PAYLOAD_PATHS = frozenset(NGSILD + name for name in PAYLOAD_NAMES)
# Which kinds a payload predicate can belong to (hasValue: Property or GeoProperty).
KINDS_OF_PAYLOAD = {}
for _kind, _name in PAYLOAD_NAME.items():
    KINDS_OF_PAYLOAD.setdefault(_name, []).append(_kind)
# Payloads that are RDF lists: emptiness is rdf:nil.
LIST_PAYLOADS = frozenset(NGSILD + n for n in ('hasValueList', 'hasObjectList'))


def payload_name(kind):
    """'hasValue' for a Property; '' for something that is not a kind."""
    return PAYLOAD_NAME.get(kind, '')


def is_relationship(kind):
    return kind in ('Relationship', 'ListRelationship')
