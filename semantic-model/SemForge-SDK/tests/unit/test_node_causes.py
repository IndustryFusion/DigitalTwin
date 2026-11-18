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
"""A node shape applied to a relationship's object: the violation belongs to the referring entity's
relationship, and its cause (pyshacl's sh:detail) names what the node shape found on the referenced entity."""

import json
import os
import shutil

from click.testing import CliRunner
from rdflib import Graph

from semforge.cli import cli
from semforge.validate.adapters import pyshacl_adapter
from semforge.validate.results import Cause

SHAPES = '''
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ngsi-ld: <https://uri.etsi.org/ngsi-ld/> .
@prefix ex: <http://example.org/> .

ex:OwnerTypeShape a sh:NodeShape ;
    sh:targetClass ex:OwnerType ;
    sh:property [ sh:path ex:hasLink ;
        sh:property [ sh:path ngsi-ld:hasObject ; sh:class ex:LinkType ; sh:node ex:LinkDeclarationShape ] ] .

ex:LinkDeclarationShape a sh:NodeShape ;
    sh:property [ sh:path ex:hasLevel ; sh:minCount 1 ] ;
    sh:property [ sh:path ex:hasMode ; sh:minCount 1 ] .
'''


def data(link_attributes=''):
    return Graph().parse(data=f'''
@prefix ngsi-ld: <https://uri.etsi.org/ngsi-ld/> .
@prefix ex: <http://example.org/> .
<urn:owner:1> a ex:OwnerType ;
    ex:hasLink [ a ngsi-ld:Relationship ; ngsi-ld:hasObject <urn:link:1> ] .
<urn:link:1> a ex:LinkType {link_attributes} .
''', format='turtle')


def run(graph):
    return pyshacl_adapter.run(graph, Graph().parse(data=SHAPES, format='turtle'))


def test_the_violation_belongs_to_the_referring_relationship_and_names_its_causes():
    results = run(data())
    assert len(results) == 1
    result = results[0]
    assert (result.resource, result.attribute, result.component) == \
        ('urn:owner:1', 'hasLink', 'NodeConstraintComponent')
    assert [(c.resource, c.attribute, c.component) for c in result.cause] == [
        ('urn:link:1', 'hasLevel', 'MinCountConstraintComponent'),
        ('urn:link:1', 'hasMode', 'MinCountConstraintComponent')]
    assert all(c.message for c in result.cause)


def test_the_cause_is_not_part_of_the_identity():
    result = run(data())[0]
    assert result.key() == ('urn:owner:1', 'hasLink', 'NodeConstraintComponent',
                            'http://example.org/OwnerTypeShape')


def test_a_conforming_referenced_entity_gives_no_result():
    attributes = ('; ex:hasLevel [ a ngsi-ld:Property ; ngsi-ld:hasValue 1 ] '
                  '; ex:hasMode [ a ngsi-ld:Property ; ngsi-ld:hasValue 2 ]')
    assert run(data(attributes)) == []


def test_results_without_detail_have_no_cause():
    graph = data()
    graph.remove((None, None, None))
    graph.parse(data='''
@prefix ex: <http://example.org/> .
<urn:owner:1> a ex:OwnerType .
''', format='turtle')
    results = run(graph)
    assert len(results) == 1 and results[0].component == 'MinCountConstraintComponent' or results == []
    assert all(result.cause == () for result in results)


def test_cause_is_a_value():
    assert Cause('r', 'a', 'C', 'm') == Cause('r', 'a', 'C', 'm')


def test_a_node_shape_applied_to_a_relationship_object_is_reached_by_the_referenced_entities():
    from types import SimpleNamespace
    from rdflib import URIRef
    from semforge.cooked.shapepage import _reach

    shapes = Graph().parse(data=SHAPES, format='turtle')
    package = SimpleNamespace(shapes=shapes, knowledge=Graph())
    graph = data()
    graph.parse(data='@prefix ex: <http://example.org/> . <urn:link:2> a ex:LinkType .', format='turtle')
    assert _reach(package, URIRef('http://example.org/LinkDeclarationShape'), graph) == {'urn:link:1'}
    # The applying shape still reaches its own focus nodes, unchanged
    assert _reach(package, URIRef('http://example.org/OwnerTypeShape'), graph) == {'urn:owner:1'}


def test_the_explanation_names_the_cause():
    from semforge.cooked.casepage import _explain

    explained = _explain(run(data())[0])
    assert explained['text'] == ('hasLink: the referenced entity does not conform to the declaration: '
                                 'urn:link:1 hasLevel is required but missing; '
                                 'urn:link:1 hasMode is required but missing')
    assert [c['attribute'] for c in explained['causes']] == ['hasLevel', 'hasMode']


DECLARATIONS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'corpus', 'declarations'))


def test_the_declarations_package_is_clean_and_its_cases_hold():
    from semforge.package import load
    from semforge.expect.vocabulary import undeclared_attributes

    # No key inside an @context counts as an attribute: they are prefixes
    assert undeclared_attributes(load(DECLARATIONS)) == []
    result = CliRunner().invoke(cli, ['test', DECLARATIONS])
    assert result.exit_code == 0, result.output


def broken_copy(tmp_path):
    """The declarations package, its model's referenced entity without Level."""
    package = tmp_path / 'declarations'
    shutil.copytree(DECLARATIONS, package, symlinks=False)
    model = package / 'model-instance.jsonld'
    entities = json.loads(model.read_text())
    del entities[1]['ex:hasLevel']
    model.write_text(json.dumps(entities, indent=2))
    return package


def test_the_problems_panel_names_the_cause_on_the_owning_entity(tmp_path):
    from semforge.cooked.casepage import located_violations
    from semforge.package import load
    from semforge.validate.orchestrator import validate_package

    package = load(str(broken_copy(tmp_path)))
    found = located_violations(package, validate_package(package))
    # On the owning entity's relationship row, not on the referenced entity (which conforms to its type)
    assert [(f['entity'], f['attribute']) for f in found] == [('urn:owner:1', 'hasLink')]
    assert found[0]['text'] == ('hasLink: the referenced entity does not conform to the declaration: '
                                'urn:link:1 hasLevel is required but missing')


def test_validate_prints_the_cause_under_a_node_violation(tmp_path):
    package = broken_copy(tmp_path)
    result = CliRunner().invoke(cli, ['validate', str(package)])
    assert result.exit_code == 1, result.output
    assert 'NodeConstraintComponent' in result.output
    assert 'cause: urn:link:1  MinCountConstraintComponent(hasLevel)' in result.output
