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
sh:message replaces the generated explanation.

The generated text says which parameter failed, which describes what the
compiler checked rather than what the model got wrong. SHACL lets the author
say the latter, and the OPC UA generator attaches a message to every
ValueRankShape for exactly that reason.

These live here rather than in a kms-constraints fixture because the fixtures
compare `resource, event, severity` and never look at the text -- so a fixture
cannot tell a message that was honoured from one that was dropped.
tests/sql-tests/kms-constraints/test19 pins the alert identities; this pins
what they say.
"""

import os
import tempfile

import rdflib

import lib.shacl_properties_to_sql as props
import lib.utils as utils
from tests.test_connective_parameters import constraint_rows


PREFIXES = {
    'sh': rdflib.Namespace('http://www.w3.org/ns/shacl#'),
    'rdfs': rdflib.Namespace('http://www.w3.org/2000/01/rdf-schema#'),
    'rdf': rdflib.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#'),
    'ngsi-ld': rdflib.Namespace('https://uri.etsi.org/ngsi-ld/'),
    'iff': rdflib.Namespace('https://industry-fusion.com/types/v0.9/'),
    'base': rdflib.Namespace('https://industry-fusion.com/base/v0.9/'),
}

KNOWLEDGE = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
iff:machine a rdfs:Class .
"""

PREAMBLE = """
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
@prefix : <https://industry-fusion.com/shapes/v0.9/> .

"""

MESSAGE_COLUMN = next(index for index, column in enumerate(utils.constraint_table)
                      if 'message' in column)


def compile_shapes(body, tmp_path):
    shapes, knowledge = tmp_path / 'shacl.ttl', tmp_path / 'knowledge.ttl'
    shapes.write_text(PREAMBLE + body)
    knowledge.write_text(KNOWLEDGE)
    cwd = os.getcwd()
    os.chdir(tempfile.mkdtemp())
    try:
        _, (_, _, _, _, postgres) = props.translate(
            str(shapes), str(knowledge), PREFIXES)
    finally:
        os.chdir(cwd)
    return postgres


def messages(compiled):
    return {row[MESSAGE_COLUMN] for row in constraint_rows(compiled)}


DIRECT = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:direct ;
        sh:message "direct must not exceed 100" ;
        sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
                      sh:maxInclusive 100 ] ] .
"""


def test_a_message_reaches_the_constraint(tmp_path):
    assert "'direct must not exceed 100'" in messages(compile_shapes(DIRECT, tmp_path))


def test_no_message_leaves_the_generated_text(tmp_path):
    """NULL is what tells the publish statement to keep its own wording."""
    compiled = compile_shapes(DIRECT.replace(
        'sh:message "direct must not exceed 100" ;', ''), tmp_path)
    assert all('NULL' in message for message in messages(compiled)), \
        'a shape with no sh:message must not invent one'


REFERENCED = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:variable ; sh:node :ScalarDouble ] .

:ScalarDouble a sh:NodeShape ;
    sh:message "ValueRank constraint for valuerank=Scalar" ;
    sh:or ( [ sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
                            sh:datatype xsd:double ] ]
            [ sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
                            sh:datatype xsd:integer ] ] ) .
"""


def test_a_message_travels_through_sh_node(tmp_path):
    """
    This is where the OPC UA generator puts its messages. Resolving sh:node
    used to drop them, leaving an alert whose text named a datatype instead of
    the rank that was violated.
    """
    assert "'ValueRank constraint for valuerank=Scalar'" in \
        messages(compile_shapes(REFERENCED, tmp_path))


def test_the_circuit_node_carries_the_message(tmp_path):
    """
    The connective is what fires for such a shape -- its branches are only
    inputs and are never published -- so the message has to reach the OR row
    or the author's text never appears in an alert.
    """
    rows = constraint_rows(compile_shapes(REFERENCED, tmp_path))
    operation_column = next(i for i, c in enumerate(utils.constraint_table)
                            if 'operation' in c)
    circuit = [row for row in rows if row[operation_column] == "'OR'"]
    assert circuit, 'no OR node was built'
    assert all(row[MESSAGE_COLUMN] == "'ValueRank constraint for valuerank=Scalar'"
               for row in circuit)


def test_disagreeing_members_leave_the_generated_text(tmp_path):
    """Two messages have no single explanation, so neither may be picked."""
    compiled = compile_shapes("""
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:variable ;
        sh:or ( [ sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
                                sh:message "too small" ; sh:minInclusive 5 ] ]
                [ sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
                                sh:message "too big" ; sh:maxInclusive 1 ] ] ) ] .
""", tmp_path)
    operation_column = next(i for i, c in enumerate(utils.constraint_table)
                            if 'operation' in c)
    for row in constraint_rows(compiled):
        if row[operation_column] == "'OR'":
            assert 'NULL' in row[MESSAGE_COLUMN]


def test_publishing_prefers_the_message():
    """
    Every alert, leaf and circuit node alike, is published by this one
    statement -- which is why honouring sh:message there covers all of them.
    """
    assert 'COALESCE(ct.`message`, t.text)' in props.sql_insert_constraint_in_alerts
