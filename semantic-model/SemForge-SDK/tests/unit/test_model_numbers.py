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

"""Plain numbers as JSON-LD 1.1 types them (#958, semforge-sdk/model-numbers).

The reference is shacl2flink's table of test vectors, which shacl2flink's
own reading is tested against too: one table, two implementations.
"""

import json
import os
import shutil

import pytest
import rdflib
from rdflib import XSD

from semforge.rdfio.numbers import as_jsonld_numbers
from semforge.rdfio.relative import BASE, for_rdflib

VECTORS = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                       'shacl2flink', 'tests', 'jsonld-number-vectors.json')
with open(VECTORS, encoding='utf-8') as _handle:
    TABLE = json.load(_handle)['vectors']

PROPERTY = 'http://example.org/p'


@pytest.mark.parametrize('vector', TABLE, ids=[v['json'] for v in TABLE])
def test_a_value_has_the_type_json_ld_gives_it(tmp_path, vector):
    document = json.loads('{"@id": "urn:x:1", "%s": %s}' % (PROPERTY, vector['json']))
    graph = rdflib.Graph()
    graph.parse(data=json.dumps(for_rdflib(document, str(tmp_path / 'm.jsonld'))),
                format='json-ld', base=BASE)
    [value] = list(graph.objects(None, rdflib.URIRef(PROPERTY)))
    assert (value.datatype or XSD.string) == XSD[vector['datatype']], vector['json']
    if 'number' in vector:
        assert value.toPython() == vector['number']


def test_the_bound_and_the_declared_type():
    assert isinstance(as_jsonld_numbers(80.0), int)
    assert isinstance(as_jsonld_numbers(1e21), float)
    declared = {'@value': 80.0, '@type': 'xsd:double'}
    assert as_jsonld_numbers(declared) is declared
    context = {'@version': 1.0}
    assert as_jsonld_numbers({'@context': context, 'v': 2.0}) == {'@context': context, 'v': 2}


# --- the scenarios of semforge-sdk/model-numbers ---------------------------

E = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
SHAPES = '''
<https://example.org/NumberShape> a sh:NodeShape ;
    sh:targetClass iffBaseEntities:Filter ;
    sh:property [ sh:path iffBaseEntities:hasDoubleX ;
                  sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] .
'''
KNOWLEDGE = (f'\n<{E}hasDoubleX> a <http://www.w3.org/2002/07/owl#ObjectProperty> ; '
             f'<http://www.w3.org/2000/01/rdf-schema#domain> <{E}Filter> .\n')
VALUES = {
    'urn:numbers:plain-whole-dot': 80.0,
    'urn:numbers:declared-whole': {'@value': 80, '@type': 'http://www.w3.org/2001/XMLSchema#double'},
    'urn:numbers:plain-1e21': 1e21,
}


@pytest.fixture
def root(tmp_path, corpus):
    root = tmp_path / 'pkg'
    shutil.copytree(corpus.path, root, ignore=shutil.ignore_patterns('.semforge'))
    (root / 'shacl.ttl').write_text((root / 'shacl.ttl').read_text() + SHAPES)
    (root / 'knowledge.ttl').write_text((root / 'knowledge.ttl').read_text() + KNOWLEDGE)
    model = root / 'model-instance.jsonld'
    entities = json.loads(model.read_text())
    context = entities[0]['@context']
    entities += [{'@context': context, 'id': iri, 'type': 'iffBaseEntities:Filter',
                  'iffBaseEntities:hasDoubleX': {'type': 'Property', 'value': value}}
                 for iri, value in VALUES.items()]
    model.write_text(json.dumps(entities))
    return root


def test_semforge_reports_what_the_standard_and_shacl2flink_report(root):
    from semforge.package import load
    from semforge.validate import validate_package

    flagged = {v.resource for v in validate_package(load(str(root)), strict=False).violations
               if v.component == 'DatatypeConstraintComponent' and v.resource in VALUES}
    assert flagged == {'urn:numbers:plain-whole-dot'}
