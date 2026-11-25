#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Which datatypes of value shapes without sh:nodeKind get a row of their own (#1097).

Only what every instance of an attribute has to meet by itself: a connective is
judged over all instances together, so nothing is read out of one that could
alert although every instance conforms.
"""
import random
import re

import pytest
from rdflib import Graph

from lib.shacl_properties_to_sql import (DATATYPE_ONLY, datatype_only_checks,
                                         extract_relationship_node_checks, translate)
from lib.utils import UnsupportedShape

PREFIXES = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
@prefix : <http://example.org/> .
"""
QUERY_PREFIXES = {'sh': 'http://www.w3.org/ns/shacl#', 'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
                  'ngsi-ld': 'https://uri.etsi.org/ngsi-ld/'}
NOT_DOUBLE = 'sh:property [ sh:path ngsild:hasValue ; sh:not [ sh:datatype xsd:double ] ]'


def _datatypes(body):
    g = Graph().parse(data=f'{PREFIXES} :S a sh:NodeShape ; sh:targetClass :C ; {body} .', format='turtle')
    return [','.join(d.rsplit('#', 1)[-1] for d in datatypes.split(','))
            for _, _, datatypes, _, _ in datatype_only_checks(g)]


def _attribute(value_shape):
    return f'sh:property [ sh:path :a ; sh:property [ sh:path ngsild:hasValue ; {value_shape} ] ]'


@pytest.mark.parametrize('value_shape,expected', (
    ('sh:datatype xsd:double', ['double']),
    ('sh:datatype xsd:double ; sh:nodeKind sh:IRIOrLiteral', ['double']),
    ('sh:or ( [ sh:datatype xsd:integer ] [ sh:datatype xsd:double ] )', ['double,integer']),
    ('sh:or ( [ sh:datatype xsd:integer ; sh:minInclusive 0 ] [ sh:datatype xsd:double ] )', ['double,integer']),
    ('sh:and ( [ sh:datatype xsd:integer ] [ sh:datatype xsd:double ] )', ['double', 'integer']),
    ('sh:datatype xsd:double ; sh:not [ sh:hasValue 5 ]', ['double']),
    # nothing every value has to meet
    ('sh:nodeKind sh:Literal ; sh:datatype xsd:double', []),
    ('sh:nodeKind sh:IRI ; sh:datatype xsd:double', []),
    ('sh:or ( [ sh:datatype xsd:string ] [ sh:pattern "^a" ] )', []),
    ('sh:or ( [ sh:datatype xsd:string ] [ sh:property [ sh:path :other ; sh:maxCount 1 ] ] )', []),
    ('sh:not [ sh:datatype xsd:double ]', []),
    ('sh:xone ( [ sh:datatype xsd:integer ] [ sh:nodeKind sh:IRI ] )', []),
    ('sh:property [ sh:path ( [ sh:zeroOrMorePath rdf:rest ] rdf:first ) ; sh:datatype xsd:integer ]', []),
    # a branch that states a node kind is checked by the ordinary extraction
    ('sh:or ( [ sh:nodeKind sh:Literal ; sh:datatype xsd:integer ] [ sh:datatype xsd:double ] )', []),
    ('sh:or ( [ sh:nodeKind sh:IRI ] [ sh:datatype xsd:double ] )', []),
    ('sh:and ( [ sh:nodeKind sh:Literal ; sh:datatype xsd:integer ] [ sh:datatype xsd:double ] )', ['double']),
    # everything conforms to a deactivated shape
    ('sh:deactivated true ; sh:datatype xsd:double', []),
    ('sh:deactivated false ; sh:datatype xsd:double', ['double']),
    ('sh:or ( [ sh:deactivated true ; sh:datatype xsd:integer ] [ sh:datatype xsd:double ] )', []),
    ('sh:and ( [ sh:deactivated true ; sh:datatype xsd:integer ] [ sh:datatype xsd:double ] )', ['double']),
    # the branch that says most counts, and rdf:JSON not at all
    ('sh:or ( [ sh:or ( [ sh:datatype xsd:boolean ] [ sh:datatype xsd:integer ] ) ; sh:datatype xsd:integer ] '
     '[ sh:datatype xsd:string ] )', ['integer,string']),
    ('sh:or ( [ sh:and ( [ sh:or ( [ sh:datatype xsd:boolean ] [ sh:datatype xsd:integer ] ) ] '
     '[ sh:datatype xsd:integer ] ) ] [ sh:datatype xsd:string ] )', ['integer,string']),
    ('sh:datatype rdf:JSON', []),
    ('sh:or ( [ sh:datatype rdf:JSON ] [ sh:datatype xsd:string ] )', []),
    # a branch on another path is about other values
    ('sh:and ( [ sh:path rdf:first ; sh:datatype xsd:integer ] [ sh:datatype xsd:double ] )', ['double']),
    ('sh:or ( [ sh:path rdf:first ; sh:datatype xsd:integer ] [ sh:datatype xsd:double ] )', []),
    ('sh:and ( [ sh:and ( [ sh:path rdf:first ; sh:datatype xsd:integer ] ) ] )', []),
    ('sh:pattern "^a"', [])))
def test_datatypes_of_a_value_shape(value_shape, expected):
    assert _datatypes(_attribute(value_shape)) == expected


@pytest.mark.parametrize('connective,expected', (
    ('sh:or ( [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:integer ] ]'
     '        [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] )', ['double,integer']),
    ('sh:and ( [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:integer ] ]'
     '         [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] )', ['double', 'integer']),
    ('sh:and ( [ sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ; sh:datatype xsd:integer ] ]'
     '         [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] )', ['double']),
    ('sh:or ( [ sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ; sh:datatype xsd:integer ] ]'
     '        [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] )', []),
    ('sh:or ( [ sh:deactivated true ; sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:integer ] ]'
     '        [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] )', []),
    ('sh:or ( [ sh:property [ sh:path ngsild:hasValue ; sh:deactivated true ; sh:datatype xsd:integer ] ]'
     '        [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] )', []),
    # a branch on a sub-attribute is about its value
    ('sh:and ( [ sh:path :sub ; sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:integer ] ]'
     '         [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] )', ['double']),
    ('sh:or ( [ sh:path :sub ; sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:integer ] ]'
     '        [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] )', []),
    # what a qualified shape or another path says is not about the value
    ('sh:qualifiedMinCount 1 ; sh:qualifiedValueShape'
     ' [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:integer ] ]', []),
    ('sh:property [ sh:path ngsild:unitCode ; sh:datatype xsd:integer ]', []),
    ('sh:property [ sh:path ngsild:hasValueList ; sh:datatype xsd:integer ]', []),
    # a list has no value of hasValue and satisfies the first branch, a literal the second
    ('sh:or ( [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:integer ] ]'
     '        [ sh:property [ sh:path ngsild:hasValueList ; sh:minCount 1 ] ] )', []),
    ('sh:xone ( [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:integer ] ]'
     '          [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] )', []),
    ('sh:not [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:integer ] ]', [])))
def test_datatypes_under_a_connective_of_the_property_shape(connective, expected):
    assert _datatypes(f'sh:property [ sh:path :a ; {connective} ]') == expected


def test_a_sub_attribute_is_checked_but_not_one_in_a_connective():
    inner = _attribute('sh:datatype xsd:double')
    assert _datatypes(f'sh:property [ sh:path :outer ; {inner} ]') == ['double']
    assert _datatypes(f'sh:property [ sh:path :outer ; sh:or ( [ {inner} ] [ {inner} ] ) ]') == []
    assert _datatypes(f'sh:or ( [ {inner} ] [ sh:property [ sh:path :b ; sh:minCount 1 ] ] )') == []
    assert _datatypes(f'sh:not [ {inner} ]') == []


def test_a_deactivated_property_or_node_shape_or_parent_is_not_checked():
    value = 'sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ]'
    assert _datatypes(f'sh:property [ sh:path :a ; sh:deactivated true ; {value} ]') == []
    assert _datatypes(f'sh:deactivated true ; sh:property [ sh:path :a ; {value} ]') == []
    assert _datatypes('sh:property [ sh:path :a ; sh:deactivated true ; '
                      f'sh:property [ sh:path :b ; {value} ] ]') == []


def test_only_a_targeted_class_and_a_plain_path_are_checked():
    inner = 'sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ]'
    for path in ('[ sh:alternativePath ( :a :b ) ]', '[ sh:inversePath :a ]', '( :a :b )', '[ sh:zeroOrMorePath :a ]'):
        assert _datatypes(f'sh:property [ sh:path {path} ; {inner} ]') == []
    for target in ('sh:targetNode :n', 'sh:targetSubjectsOf :p', 'sh:targetObjectsOf :p'):
        g = Graph().parse(data=f'{PREFIXES} :S a sh:NodeShape ; {target} ; sh:property [ sh:path :a ; {inner} ] .',
                          format='turtle')
        assert datatype_only_checks(g) == []


def test_a_recursive_shape_ends():
    g = Graph().parse(data=f'''{PREFIXES} :S a sh:NodeShape ; sh:targetClass :C ; sh:property :P .
        :P sh:path :a ; sh:property :P , [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] .''', format='turtle')
    assert len(datatype_only_checks(g)) == 1


@pytest.mark.parametrize('connective', ('and', 'or'))
@pytest.mark.parametrize('level', ('value', 'property'))
def test_a_connective_that_leads_back_to_its_shape_ends(connective, level):
    if level == 'value':
        recursive = (f'sh:property :V . :V sh:path ngsild:hasValue ; sh:datatype xsd:double ; sh:{connective} ( :A ) . '
                     f':A sh:datatype xsd:integer ; sh:{connective} ( :B ) . '
                     f':B sh:datatype xsd:string ; sh:{connective} ( :A )')
    else:
        recursive = (f'sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ; sh:{connective} ( :A ) . '
                     ':A sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:integer ] ; '
                     f'sh:{connective} ( :B ) . '
                     ':B sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:string ] ; '
                     f'sh:{connective} ( :A )')
    g = Graph().parse(data=f'''{PREFIXES} :S a sh:NodeShape ; sh:targetClass :C ; sh:property :P .
        :P sh:path :a ; {recursive} .''', format='turtle')
    # A and B lead back to each other, so neither reads the other
    assert sorted(row[2].rsplit('#', 1)[-1] for row in datatype_only_checks(g)) == ['double', 'integer']


def test_a_connective_of_its_own_shape_ends():
    for connective in ('and', 'or'):
        assert _datatypes(_attribute('sh:datatype xsd:double') + f' . :S sh:{connective} ( :S )') == ['double']
        g = Graph().parse(data=f'''{PREFIXES} :S a sh:NodeShape ; sh:targetClass :C ; sh:property [ sh:path :a ;
            sh:property :V ] . :V sh:path ngsild:hasValue ; sh:datatype xsd:double ; sh:{connective} ( :V ) .''',
                          format='turtle')
        assert len(datatype_only_checks(g)) == 1


def test_shared_branches_are_read_once():
    """Two references each, sixty levels down: 2^60 ways, sixty shapes."""
    levels = 60
    chain = ' . '.join(f':N{n} sh:and ( :N{n + 1} :N{n + 1} ) ; sh:or ( :N{n + 1} :N{n + 1} )' for n in range(levels))
    g = Graph().parse(data=f'''{PREFIXES} :S a sh:NodeShape ; sh:targetClass :C ; sh:property [ sh:path :a ;
        sh:property [ sh:path ngsild:hasValue ; sh:and ( :N0 ) ] ] . {chain} . :N{levels} sh:datatype xsd:double .''',
                      format='turtle')
    assert len(datatype_only_checks(g)) == 1


def test_shared_property_shapes_beyond_the_depth_limit_are_visited_once():
    levels = 40
    chain = ' . '.join(f':P{n} sh:path :p ; sh:property :P{n + 1} , :Q{n + 1} . '
                       f':Q{n} sh:path :q ; sh:property :P{n + 1} , :Q{n + 1}' for n in range(levels))
    g = Graph().parse(data=f'''{PREFIXES} :S a sh:NodeShape ; sh:targetClass :C ; sh:property :P0 . {chain} .
        :P{levels} sh:path :p ; sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] .
        :Q{levels} sh:path :q .''', format='turtle')
    assert {len(paths) for _, paths, _, _, _ in datatype_only_checks(g)} == {levels + 1}


def test_a_datatype_below_the_depth_limit_fails_the_build(tmp_path):
    """Also where the ordinary extraction, which climbs one parent of a shared shape, does not get so deep."""
    shacl, knowledge = tmp_path / 'shacl.ttl', tmp_path / 'knowledge.ttl'
    shacl.write_text(f'''{PREFIXES} :S a sh:NodeShape ; sh:targetClass :C ; sh:property :P , :A .
        :A sh:path :a ; sh:property [ sh:path :b ; sh:property [ sh:path :c ; sh:property :P ] ] .
        :P sh:path :p ; sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] .''')
    knowledge.write_text(f'{PREFIXES} :C a rdfs:Class .')
    with pytest.raises(UnsupportedShape, match='subproperty depth 4'):
        translate(str(shacl), str(knowledge), QUERY_PREFIXES)


@pytest.mark.parametrize('other,expected', (('', 1), ('sh:deactivated true ;', 0)))
def test_a_declaration_applied_twice_is_checked_while_one_site_applies_it(other, expected):
    g = Graph().parse(data=f'''{PREFIXES}
        :S a sh:NodeShape ; sh:targetClass :C ;
            sh:property [ sh:path :rel ; sh:deactivated true ; sh:property [ sh:path ngsild:hasObject ; sh:node :D ] ] ,
                        [ sh:path :rel ; {other} sh:property [ sh:path ngsild:hasObject ; sh:node :D ] ] .
        :D a sh:NodeShape ; sh:property [ sh:path :a ;
            sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] .''', format='turtle')
    extract_relationship_node_checks(g)
    assert len(datatype_only_checks(g)) == expected


@pytest.mark.parametrize('owner,prop,value,expected', (
    ('', '', '', 1), ('sh:deactivated true ;', '', '', 0),
    ('', 'sh:deactivated true ;', '', 0), ('', '', 'sh:deactivated true ;', 0)))
def test_a_declaration_applied_by_a_deactivated_shape_is_not_checked(owner, prop, value, expected):
    g = Graph().parse(data=f'''{PREFIXES}
        :S a sh:NodeShape ; sh:targetClass :C ; {owner} sh:property [ sh:path :rel ; {prop}
            sh:property [ sh:path ngsild:hasObject ; {value} sh:node :D ] ] .
        :D a sh:NodeShape ; sh:property [ sh:path :a ;
            sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] .''', format='turtle')
    extract_relationship_node_checks(g)
    assert len(datatype_only_checks(g)) == expected


def test_two_builds_give_the_same_rows():
    shapes = f'{PREFIXES} :S a sh:NodeShape ; sh:targetClass :C ; ' + ' ; '.join(
        f'sh:property [ sh:path :{path} ; sh:message "{message}" ; '
        f'sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:{datatype} ] ]'
        for path in 'ab' for message in ('one', 'two', 'three') for datatype in ('double', 'integer')) + ' .'
    builds = []
    for _ in range(5):
        # the statements in another order and with other blank node labels
        lines = Graph().parse(data=shapes, format='turtle').serialize(format='nt').splitlines()
        random.shuffle(lines)
        builds.append(datatype_only_checks(Graph().parse(data='\n'.join(lines), format='nt')))
    assert len(builds[0]) == 12
    assert all(build == builds[0] for build in builds)


def test_the_members_of_a_connective_keep_their_row(tmp_path):
    """Not a datatype row: sh:not of a datatype gives the verdict it gave before."""
    shacl = tmp_path / 'shacl.ttl'
    knowledge = tmp_path / 'knowledge.ttl'
    shacl.write_text(f'{PREFIXES} :S a sh:NodeShape ; sh:targetClass :C ;'
                     f' sh:property [ sh:path :a ; {NOT_DOUBLE} ] , '
                     '[ sh:path :b ; sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ] .')
    knowledge.write_text(f'{PREFIXES} :C a rdfs:Class .')
    sqlite = translate(str(shacl), str(knowledge), QUERY_PREFIXES)[0]
    rows = re.findall(r'INSERT[^;]*constraint_table[^;]*VALUES[^;]*;', sqlite)
    assert sum(row.count(f"'{DATATYPE_ONLY}'") for row in rows) == 1
