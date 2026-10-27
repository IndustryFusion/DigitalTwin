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

"""rdf:JSON: what a JsonProperty's `json` is, and nothing else in NGSI-LD data.

JSON-LD's "@json" makes a JsonProperty's value one rdf:JSON literal. A JSON
object as a Property's `value` or as an item of a `valueList` is expanded
into nodes -- the OPC UA tools write "a list of rdf:JSON values" for JSON
Variables, and that form can never hold.
"""

import shutil

import pytest

from semforge.cooked.choices import choices_for
from semforge.cooked.typepage import value_text
from semforge.sanity import _json_checks

E = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
SHAPES = '''
<https://example.org/JsonShape> a sh:NodeShape ;
    sh:targetClass iffBaseEntities:Filter ;
    sh:property [ sh:path iffBaseEntities:hasSettingsX ;
                  sh:property [ sh:path ngsild:hasJSON ; sh:datatype rdf:JSON ] ] ,
                [ sh:path iffBaseEntities:hasPlainX ;
                  sh:property [ sh:path ngsild:hasValue ; sh:datatype rdf:JSON ] ] ,
                [ sh:path iffBaseEntities:hasChoiceX ;
                  sh:property [ sh:path ngsild:hasValue ;
                                sh:or ( [ sh:datatype xsd:string ] [ sh:datatype rdf:JSON ] ) ] ] ,
                [ sh:path iffBaseEntities:hasListX ;
                  sh:property [ sh:path ngsild:hasValueList ; sh:nodeKind sh:BlankNode ;
                                sh:property [ sh:path ( [ sh:zeroOrMorePath rdf:rest ] rdf:first ) ;
                                              sh:datatype rdf:JSON ] ] ] .
'''
KNOWLEDGE = ''.join(
    f'\n<{E}{name}> a <http://www.w3.org/2002/07/owl#ObjectProperty> ; '
    f'<http://www.w3.org/2000/01/rdf-schema#domain> <{E}Filter> .\n'
    for name in ('hasSettingsX', 'hasPlainX', 'hasChoiceX', 'hasListX'))


@pytest.fixture
def root(tmp_path, corpus):
    root = tmp_path / 'pkg'
    shutil.copytree(corpus.path, root, ignore=shutil.ignore_patterns('.semforge'))
    (root / 'shacl.ttl').write_text((root / 'shacl.ttl').read_text() + SHAPES)
    (root / 'knowledge.ttl').write_text((root / 'knowledge.ttl').read_text() + KNOWLEDGE)
    return root


def test_rdf_json_is_warned_wherever_no_data_can_have_it(root):
    from semforge.package import load

    found = {f.subject.rsplit('/', 1)[-1]: f for f in _json_checks(load(str(root)))}
    # A JsonProperty's json is one: fine.
    assert 'hasSettingsX' not in found
    assert set(found) == {'hasPlainX', 'hasChoiceX', 'hasListX'}
    assert 'on its hasValue' in found['hasPlainX'].message
    assert 'on its hasValue' in found['hasChoiceX'].message
    assert 'on each item of a list' in found['hasListX'].message
    assert {f.code for f in found.values()} == {'json-never-holds'}
    assert {f.severity for f in found.values()} == {'warning'}
    # On the attribute's own line in the shapes file.
    lines = (root / 'shacl.ttl').read_text().splitlines()
    assert 'iffBaseEntities:hasListX' in lines[found['hasListX'].line - 1]


def test_rdf_json_is_offered_and_said(corpus):
    offered, _ = choices_for(corpus, ['iffBaseEntities:hasStrength', 'ngsild:hasValue'],
                             'sh:datatype')
    json = next(c for c in offered if c['value'] == 'rdf:JSON')
    assert "JsonProperty's json" in json['detail']
    assert value_text('Property', {'sh:datatype': 'rdf:JSON'}, []) == 'JSON'


def test_the_value_picker_accepts_rdf_json(root):
    from semforge.cooked.constrain import edit_attribute
    from semforge.package import load

    shape, chain = 'https://example.org/JsonShape', ['iffBaseEntities:hasPlainX']

    def written():
        text = (root / 'shacl.ttl').read_text()
        plain = text[text.index('sh:path iffBaseEntities:hasPlainX'):]
        return plain[:plain.index('] ]')]

    edit_attribute(load(str(root)), shape, chain, value={'datatype': 'xsd:string'})
    assert 'sh:datatype xsd:string' in written()
    # Refused before: "not an XML Schema datatype".
    edit_attribute(load(str(root)), shape, chain, value={'datatype': 'rdf:JSON'})
    assert 'sh:datatype rdf:JSON' in written()


def test_the_value_editor_writes_it_into_a_json_property(root):
    from semforge.cooked.valueforms import edit_value, read_value, say
    from semforge.package import load

    shape, chain = 'https://example.org/JsonShape', ['iffBaseEntities:hasSettingsX']
    edit_value(load(str(root)), shape, chain, {'op': 'addform', 'kind': 'ListProperty'})
    edit_value(load(str(root)), shape, chain, {'op': 'removeform', 'form': 1})
    value = read_value(load(str(root)), (root / 'shacl.ttl').read_text(), shape, chain)
    assert [f.kind for f in value.forms] == ['JsonProperty']
    assert say(value) == 'JSON: JSON'
