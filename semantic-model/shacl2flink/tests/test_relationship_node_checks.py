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

"""
A node shape applied to the object of a relationship (openspec gh-985-instance-declaration-shapes).

`sh:node` on the `ngsi-ld:hasObject` value shape constrains the entity the relationship refers to. It is
taken out of sh:node substitution and compiled as a shape targeting a synthetic class per owning class
and relationship; its circuit tops feed a NODE row, which raises the alert on the owning entity. The
SQLite behaviour is pinned by tests/sql-tests/sql-cases/relationship-node-checks.
"""

import os
import tempfile

import pytest
import rdflib
from rdflib import RDF, URIRef
from rdflib.namespace import SH

import lib.shacl_properties_to_sql as props
from lib.utils import UnsupportedShape

PREFIXES = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
@prefix ex: <https://example.org/node/> .
"""

KNOWLEDGE = PREFIXES + """
ex:Owner a rdfs:Class .
ex:SpecialOwner rdfs:subClassOf ex:Owner .
ex:Link a rdfs:Class .
"""

LEVEL = """ sh:property [ sh:path ex:hasLevel ; sh:minCount 1 ; sh:nodeKind sh:BlankNode ;
        sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ; sh:datatype xsd:double ] ] """


def owner_shape(object_shape='sh:class ex:Link ; sh:node ex:LinkDeclarationShape'):
    return PREFIXES + f"""
ex:OwnerShape a sh:NodeShape ;
    sh:targetClass ex:Owner ;
    sh:property [ sh:path ex:hasLink ; sh:nodeKind sh:BlankNode ;
        sh:property [ sh:path ngsild:hasObject ; {object_shape} ] ] .
"""


SHAPES = owner_shape() + f"""
ex:LinkDeclarationShape a sh:NodeShape ; {LEVEL} .
"""

NAMESPACES = {
    'sh': rdflib.Namespace('http://www.w3.org/ns/shacl#'),
    'rdfs': rdflib.Namespace('http://www.w3.org/2000/01/rdf-schema#'),
    'rdf': rdflib.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#'),
    'ngsi-ld': rdflib.Namespace('https://uri.etsi.org/ngsi-ld/'),
    'ex': rdflib.Namespace('https://example.org/node/'),
}
OWNER = 'https://example.org/node/Owner'
SPECIAL = 'https://example.org/node/SpecialOwner'
LINK = 'https://example.org/node/hasLink'


def graph(shapes):
    g = rdflib.Graph()
    g.parse(data=shapes, format='turtle')
    g.parse(data=KNOWLEDGE, format='turtle')
    return g


def translate(shapes, tmp_path):
    (tmp_path / 'shacl.ttl').write_text(shapes)
    (tmp_path / 'knowledge.ttl').write_text(KNOWLEDGE)
    cwd = os.getcwd()
    os.chdir(tempfile.mkdtemp())          # translate() writes into ./output
    try:
        return props.translate(str(tmp_path / 'shacl.ttl'), str(tmp_path / 'knowledge.ttl'), NAMESPACES)
    finally:
        os.chdir(cwd)


def rejection(shapes, tmp_path):
    with pytest.raises(UnsupportedShape) as error:
        translate(shapes, tmp_path)
    return str(error.value)


# --- extraction (task 2.2) ---------------------------------------------------------------

def test_the_reference_is_cloned_onto_a_synthetic_class_per_owning_class():
    g = graph(SHAPES)
    checks, problems = props.extract_relationship_node_checks(g)
    assert problems == []
    assert [(c['shape'], c['relationship'], c['classes'], c['severity']) for c in checks] == [
        ('https://example.org/node/LinkDeclarationShape', LINK,
         [str(props.node_check_class(OWNER, LINK)), str(props.node_check_class(SPECIAL, LINK))], 'warning')]
    # The reference is gone, and with it the declaration shape nothing else uses
    assert list(g.subject_objects(SH.node)) == []
    assert (URIRef('https://example.org/node/LinkDeclarationShape'), None, None) not in g
    # The clone is an ordinary node shape on the synthetic classes, with the declaration's constraints
    clone = next(g.subjects(SH.targetClass, props.node_check_class(OWNER, LINK)))
    assert (clone, RDF.type, SH.NodeShape) in g
    assert [str(p) for p in g.objects(next(g.objects(clone, SH.property)), SH.path)] == \
        ['https://example.org/node/hasLevel']


def test_a_node_level_sh_node_is_left_to_substitution():
    shapes = PREFIXES + f"""
ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ; sh:node ex:Common .
ex:Common a sh:NodeShape ; {LEVEL} .
"""
    g = graph(shapes)
    assert props.extract_relationship_node_checks(g) == ([], [])
    assert (URIRef('https://example.org/node/OwnerShape'), SH.node, URIRef('https://example.org/node/Common')) in g


def test_a_declaration_shape_with_a_target_of_its_own_stays():
    g = graph(SHAPES + 'ex:LinkDeclarationShape sh:targetClass ex:Link .\n')
    props.extract_relationship_node_checks(g)
    assert (URIRef('https://example.org/node/LinkDeclarationShape'), SH.targetClass, None) in g


def test_the_severity_is_the_relationship_shape_s():
    shapes = SHAPES.replace('sh:property [ sh:path ex:hasLink ;',
                            'sh:property [ sh:path ex:hasLink ; sh:severity ex:Critical ;') + \
        'ex:Critical rdfs:label "critical" .\n'
    checks, _ = props.extract_relationship_node_checks(graph(shapes))
    assert checks[0]['severity'] == 'critical'


# --- the compiled rows, edges and statements (task 2.4) -----------------------------------

def test_the_tops_feed_a_node_row_that_publishes(tmp_path):
    _, (statementsets, _, _, _, postgres) = translate(SHAPES, tmp_path)
    assert postgres.count("'NODE'") == 2 + 2             # two node rows, one NODE edge into each
    # the owner's own class check, one row per owning class, and the two node rows
    assert postgres.count("'PUBLISH'") == 2 + 2
    # relationship, property, the two over the node focus, the node statement, the publication
    assert len(statementsets) == 6
    node_statement = statementsets[4]
    assert 'NodeConstraintComponent(' in node_statement and 'LISTAGG' not in node_statement
    assert node_statement.count('MAX(CASE WHEN pos = ') == 1   # one member, one text slot
    for focused in statementsets[2:4]:
        assert 'FROM node_focus AS A JOIN' in focused


def test_a_package_without_node_checks_compiles_as_before(tmp_path):
    shapes = owner_shape('sh:class ex:Link')
    _, (statementsets, _, _, _, postgres) = translate(shapes, tmp_path)
    assert len(statementsets) == 3 and "'NODE'" not in postgres
    assert not any('node_focus' in statement for statement in statementsets)


def test_the_text_has_one_slot_per_member_of_the_largest_node_row():
    sqlite, yaml = props.create_relationship_node_sql(3)
    for sql in (sqlite, yaml):
        assert [f'pos = {slot} ' in sql for slot in (1, 2, 3, 4)] == [True, True, True, False]
    assert 'CURRENT_TIMESTAMP' in sqlite and 'CURRENT_TIMESTAMP' not in yaml


# --- rejections (task 2.3) ---------------------------------------------------------------

def test_a_property_shape_directly_underneath_has_object_fails_the_build(tmp_path):
    message = rejection(owner_shape('sh:class ex:Link ; ' + LEVEL), tmp_path)
    assert 'has a property shape directly underneath ngsi-ld:hasObject' in message
    assert '<https://example.org/node/OwnerShape> sh:path <https://example.org/node/hasLink>' in message


def test_a_second_relationship_hop_fails_the_build(tmp_path):
    shapes = owner_shape() + """
ex:LinkDeclarationShape a sh:NodeShape ;
    sh:property [ sh:path ex:hasNext ; sh:nodeKind sh:BlankNode ;
        sh:property [ sh:path ngsild:hasObject ; sh:node ex:FurtherShape ] ] .
ex:FurtherShape a sh:NodeShape ; """ + LEVEL + ' .\n'
    message = rejection(shapes, tmp_path)
    assert '<https://example.org/node/LinkDeclarationShape> applies sh:node to the object of a further ' \
        'relationship' in message


@pytest.mark.parametrize('inner', ['urn:a:inner', 'urn:z:inner'])
@pytest.mark.parametrize('targeted', [False, True])
def test_a_second_hop_is_rejected_whichever_reference_comes_first(inner, targeted):
    # References are processed in the order of their value shapes; the inner one sorting before or after the owner's
    # must not decide whether the outer declaration is judged with its second hop. A declaration shape with a target
    # of its own is no exception.
    shapes = PREFIXES + f"""
ex:OwnerShape a sh:NodeShape ;
    sh:targetClass ex:Owner ;
    sh:property [ sh:path ex:hasLink ; sh:nodeKind sh:BlankNode ;
        sh:property <urn:m:owner> ] .
<urn:m:owner> sh:path ngsild:hasObject ; sh:class ex:Link ; sh:node ex:LinkDeclarationShape .
ex:LinkDeclarationShape a sh:NodeShape ; {'sh:targetClass ex:Link ;' if targeted else ''}
    sh:property [ sh:path ex:hasNext ; sh:nodeKind sh:BlankNode ; sh:property <{inner}> ] .
<{inner}> sh:path ngsild:hasObject ; sh:node ex:FurtherShape .
ex:FurtherShape a sh:NodeShape ; """ + LEVEL + ' .\n'
    checks, problems = props.extract_relationship_node_checks(graph(shapes))
    assert checks == []
    assert any(p.startswith('<https://example.org/node/LinkDeclarationShape> applies sh:node to the object of '
                            'a further relationship') for p in problems), problems
    assert not any('FurtherShape' in p for p in problems), problems


def test_a_declaration_shape_without_constraints_fails_the_build(tmp_path):
    shapes = owner_shape() + 'ex:LinkDeclarationShape a sh:NodeShape .\n'
    message = rejection(shapes, tmp_path)
    assert '<https://example.org/node/LinkDeclarationShape> is applied to the object of ' \
        '<https://example.org/node/OwnerShape> sh:path <https://example.org/node/hasLink> but produced no ' \
        'constraint' in message


def test_a_relationship_without_an_owning_target_fails_the_build(tmp_path):
    shapes = SHAPES.replace('sh:targetClass ex:Owner ;', '')
    message = rejection(shapes, tmp_path)
    assert 'is not a property of a node shape with sh:targetClass' in message


@pytest.mark.parametrize('inner, expected', [
    ('sh:sparql [ sh:select "SELECT $this WHERE { }" ]', 'holds an sh:sparql constraint'),
    ('sh:not [ sh:property [ sh:path ex:hasLevel ; sh:minCount 1 ] ]', 'uses sh:not or sh:xone'),
    ('sh:property [ sh:path ( [ sh:inversePath ngsild:hasObject ] [ sh:inversePath ex:hasLink ] ) ; '
     'sh:maxCount 1 ]', 'constrains an inverse path'),
])
def test_forms_the_referenced_entity_cannot_be_checked_with_fail_the_build(inner, expected):
    g = graph(owner_shape() + f'ex:LinkDeclarationShape a sh:NodeShape ; {inner} .\n')
    checks, problems = props.extract_relationship_node_checks(g)
    assert checks == []
    assert [expected in problem for problem in problems] == [True]
    assert problems[0].startswith('<https://example.org/node/LinkDeclarationShape>')


# --- what only a Flink deployment showed (both measured on a live cluster) ---------------

# Words Flink's parser (Calcite) reserves that read naturally as column names. `member` is one (MEMBER OF):
# the statement set failed to deploy with `Encountered "member"`, while SQLite accepted it.
CALCITE_RESERVED = {'member', 'value', 'position', 'current', 'range', 'row', 'rows', 'window', 'result',
                    'language', 'user', 'system', 'time', 'timestamp', 'date', 'end', 'count', 'element',
                    'match', 'measures', 'pattern', 'partition', 'order', 'offset', 'fetch', 'next', 'role'}


def test_the_node_statements_name_nothing_flink_reserves():
    import re
    statements = [props.create_relationship_node_sql(2)[1], props.node_focus(True)['focus_ctes']]
    for sql in statements:
        unquoted = re.sub(r"'[^']*'|`[^`]*`|/\*.*?\*/", ' ', sql)     # literals, quoted names, hints are fine
        # Names, not keywords: what an alias introduces and what a qualified reference reads (`AS member`,
        # `NM.member` is how it broke). COUNT(*) and CASE ... END are keywords used as keywords.
        names = {w.lower() for w in re.findall(r'\bAS\s+([A-Za-z_]+)|\.([A-Za-z_]+)', unquoted, re.I) for w in w if w}
        assert names & CALCITE_RESERVED == set(), sql
        assert 'memberid' in {n.lower() for n in re.findall(r'\bAS\s+([A-Za-z_]+)', sql)} or 'node_focus' in sql


def test_the_node_focus_does_not_join_the_constraint_rows():
    # Flink pushed the focus's GROUP BY below a join with the node rows and the STATE_TTL pin of those rows did not
    # follow: the check answered nothing once the job was older than the state TTL. The bases' pinned join on the
    # target class does the filtering instead.
    ctes = props.node_focus(True)['focus_ctes']
    assert 'constraint_table' not in ctes and "'NODE'" not in ctes
    assert "STATE_TTL('O' = '0d', 'RL' = '0d')" in ctes and "STATE_TTL('node_focus_join' = '0d')" in ctes
