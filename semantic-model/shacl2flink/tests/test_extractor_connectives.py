#
# Copyright (c) 2026 Intel Corporation
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
End-to-end extractor coverage for the SHACL logical connectives.

Before this was supported, a shape using sh:and / sh:not / sh:xone produced
ZERO constraints and no error -- it was accepted and silently never validated.
These tests exist mainly to keep that from regressing, so they assert both that
the connectives are extracted AND that each one reaches the circuit.
"""

import os
import tempfile

import rdflib
import pytest

import lib.shacl_properties_to_sql as props


SHAPES = """
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .

iff:ConnectiveShape
    a sh:NodeShape ;
    sh:targetClass iff:machine ;

    sh:property [
        sh:path iff:plainState ;
        sh:property [ sh:path <https://uri.etsi.org/ngsi-ld/hasValue> ;
                      sh:minInclusive 10 ] ;
    ] ;

    sh:property [
        sh:path iff:andState ;
        sh:and (
            [ sh:property [ sh:path <https://uri.etsi.org/ngsi-ld/hasValue> ;
                            sh:minInclusive 5 ] ]
            [ sh:property [ sh:path <https://uri.etsi.org/ngsi-ld/hasValue> ;
                            sh:maxInclusive 50 ] ]
        ) ;
    ] ;

    sh:property [
        sh:path iff:notState ;
        sh:not [ sh:property [ sh:path <https://uri.etsi.org/ngsi-ld/hasValue> ;
                               sh:in ( "FORBIDDEN" ) ] ] ;
    ] ;

    sh:property [
        sh:path iff:xoneState ;
        sh:xone (
            [ sh:property [ sh:path <https://uri.etsi.org/ngsi-ld/hasValue> ;
                            sh:minInclusive 100 ] ]
            [ sh:property [ sh:path <https://uri.etsi.org/ngsi-ld/hasValue> ;
                            sh:maxInclusive 10 ] ]
        ) ;
    ] .
"""

KNOWLEDGE = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
iff:machine a rdfs:Class .
"""

PREFIXES = {
    'sh': rdflib.Namespace('http://www.w3.org/ns/shacl#'),
    'rdfs': rdflib.Namespace('http://www.w3.org/2000/01/rdf-schema#'),
    'rdf': rdflib.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#'),
    'ngsi-ld': rdflib.Namespace('https://uri.etsi.org/ngsi-ld/'),
    'iff': rdflib.Namespace('https://industry-fusion.com/types/v0.9/'),
    'base': rdflib.Namespace('https://industry-fusion.com/base/v0.9/'),
}


@pytest.fixture(scope='module')
def extracted(tmp_path_factory):
    """Extract straight from the shapes as written."""
    tmp = tmp_path_factory.mktemp('connectives')
    shapes, knowledge = tmp / 'shacl.ttl', tmp / 'knowledge.ttl'
    shapes.write_text(SHAPES)
    knowledge.write_text(KNOWLEDGE)

    cwd = os.getcwd()
    os.chdir(tempfile.mkdtemp())          # translate() writes into ./output
    try:
        _, (_, _, _, _, postgres) = props.translate(
            str(shapes), str(knowledge), PREFIXES)
    finally:
        os.chdir(cwd)
    return postgres


@pytest.mark.parametrize('operation', ['AND', 'XONE', 'NOT'])
def test_connective_reaches_the_circuit(extracted, operation):
    """Each connective becomes an edge in the constraint combination table."""
    assert f"'{operation}'" in extracted, \
        f'sh:{operation.lower()} produced no {operation} edge -- the shape ' \
        f'would be silently unvalidated'


@pytest.mark.parametrize('path', ['plainState', 'andState', 'notState', 'xoneState'])
def test_every_property_yields_constraints(extracted, path):
    """
    No shape may be silently dropped.

    A property that extracts to nothing is worse than an error: validation
    reports conformant for something it never checked.
    """
    assert path in extracted, f'{path} produced no constraint rows'


def test_not_is_never_published_directly(extracted):
    """
    NOT must own a circuit node even with a single member.

    OR/AND/XONE at arity 1 reduce to 'violated iff the member violated', so
    publishing the member directly is equivalent. NOT does not reduce that way
    -- publishing directly would emit the inner verdict instead of its negation.
    """
    assert "'NOT'" in extracted


def test_connective_operation_mapping():
    sh = rdflib.Namespace('http://www.w3.org/ns/shacl#')
    assert props.connective_operation(sh['or']) == 'OR'
    assert props.connective_operation(sh['and']) == 'AND'
    assert props.connective_operation(sh.xone) == 'XONE'
    assert props.connective_operation(sh['not']) == 'NOT'
    assert props.connective_operation(None) == 'OR'


# The dominant OPC UA shape: a variable is a Property when scalar and a
# ListProperty when an array, so `sh:maxCount 1` above the sh:or means "one
# attribute of EITHER kind".
SPANNING = """
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix iff:  <https://industry-fusion.com/types/v0.9/> .
@prefix :     <https://industry-fusion.com/shapes/v0.9/> .

:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:spanning ; sh:minCount 0 ; sh:maxCount 1 ;
        sh:or ( [ sh:property [ sh:path ngsild:hasValue ;
                                sh:datatype xsd:double ] ]
                [ sh:property [ sh:path ngsild:hasValueList ;
                                sh:datatype xsd:double ] ] ) ] .
"""


def test_disagreeing_branches_produce_no_attribute_type(tmp_path):
    """
    Picking one branch's type would count only that kind of attribute and
    alert on the other -- an array value reported as a missing scalar. The
    count must span both, expressed as carrying no attribute type at all.

    This returned ('hasValue', 'Property') by sorting order before, which is
    an arbitrary choice between two equally valid branches.
    """
    sh = rdflib.Namespace('http://www.w3.org/ns/shacl#')
    g = rdflib.Graph()
    g.parse(data=SPANNING, format='turtle')
    spanning = rdflib.URIRef(
        'https://industry-fusion.com/types/v0.9/spanning')
    prop = next(s for s in g.subjects(sh.path, spanning)
                if (s, sh['or'], None) in g)

    # The guard must be what makes this (None, None): the branches have to
    # actually disagree, otherwise the assertion below passes on an empty set.
    branches = {props.VALUE_PATH_ATTRIBUTE_TYPES[str(path)]
                for clause in props.connective_clauses(g, prop)
                for value_shape in g.objects(clause, sh.property)
                for path in g.objects(value_shape, sh.path)
                if str(path) in props.VALUE_PATH_ATTRIBUTE_TYPES}
    assert len(branches) == 2, \
        f'the fixture no longer exercises disagreeing branches: {branches}'

    assert props.branch_attribute_type(g, prop) == (None, None)


def test_nodekind_check_does_not_test_the_null_sentinel(tmp_path):
    """
    A1 coerces a NULL propertyNodetype to the STRING 'null', so an `IS NOT
    NULL` guard on that column excludes nothing and the check then compares a
    real nodeType against 'null' -- firing NodeKindConstraintComponent on
    every valid value of a type-spanning constraint.
    """
    sql = props.sql_check_property_nodeType
    assert "propertyNodetype` <> 'null'" in sql, \
        'the nodeType check must exclude the sentinel, not NULL'
    assert 'propertyNodetype IS NOT NULL' not in sql
