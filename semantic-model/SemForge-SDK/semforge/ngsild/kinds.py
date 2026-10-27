#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

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


# The prefixes NGSI-LD is written under: SemForge's `ngsild:`, and the
# `ngsi-ld:` of the core @context, which the OPC UA tools use.
PREFIXES = ('ngsild', 'ngsi-ld')


def payload_of(text):
    """'hasValue' for a payload predicate as a shapes file spells it --
    `ngsild:hasValue`, `ngsi-ld:hasValue` or the full IRI -- else ''.

    Text-level readers compared paths with the `ngsild:` spelling only, and
    every `ngsi-ld:hasObject` of the OPC UA shapes was read as a
    sub-attribute named hasObject.
    """
    text = str(text or '').strip()
    if text.startswith('<') and text.endswith('>'):
        text = text[1:-1]
    if text.startswith(NGSILD):
        name = text[len(NGSILD):]
    elif ':' in text and text.split(':', 1)[0] in PREFIXES:
        name = text.split(':', 1)[1]
    else:
        return ''
    return name if name in PAYLOAD_NAMES else ''


class PayloadSpellings:
    """`path in VALUE_PATHS` for text-level readers: true for every spelling
    payload_of() knows. Iterates as the `ngsild:` spellings SemForge writes."""

    def __contains__(self, text):
        return bool(payload_of(text))

    def __iter__(self):
        return iter(f'ngsild:{name}' for name in PAYLOAD_NAMES)


SPELLINGS = PayloadSpellings()
