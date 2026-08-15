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
A shape the compiler cannot translate must fail the build.

Every silent failure found in this compiler so far had the same shape: the
build succeeded, a constraint was quietly not compiled, and validation then
reported conformant for something it had never checked. Nothing downstream can
detect that -- an absent alert looks exactly like a satisfied constraint.

These tests pin the opposite behaviour. They matter more than they look: a
checker that stops firing is indistinguishable from a codebase with nothing
left to catch.
"""

import os
import tempfile

import pytest
import rdflib

import lib.shacl_properties_to_sql as props
from lib.utils import UnsupportedShape


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
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
@prefix : <https://industry-fusion.com/shapes/v0.9/> .

"""


def compile_shapes(body, tmp_path):
    shapes, knowledge = tmp_path / 'shacl.ttl', tmp_path / 'knowledge.ttl'
    shapes.write_text(PREAMBLE + body)
    knowledge.write_text(KNOWLEDGE)
    cwd = os.getcwd()
    os.chdir(tempfile.mkdtemp())          # translate() writes into ./output
    try:
        return props.translate(str(shapes), str(knowledge), PREFIXES)
    finally:
        os.chdir(cwd)


# A value shape may carry sh:or -- its branches become members of the circuit
# node for the attribute. This is the supported form and must keep compiling.
VALUE_LEVEL_OR = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:value ;
        sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
            sh:or ( [ sh:minInclusive 100 ] [ sh:maxInclusive 10 ] ) ] ] .
"""

VALUE_LEVEL_XONE = VALUE_LEVEL_OR.replace('sh:or (', 'sh:xone (')
VALUE_LEVEL_AND = VALUE_LEVEL_OR.replace('sh:or (', 'sh:and (')

# A connective inside a BRANCH of a value-level connective -- one level deeper
# than the extractor descends, so its members would contribute nothing.
NESTED_TOO_DEEP = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:deep ;
        sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
            sh:xone ( [ sh:and ( [ sh:minInclusive 5 ] [ sh:maxInclusive 50 ] ) ]
                      [ sh:minInclusive 100 ] ) ] ] .
"""

# A property shape with no value shape anywhere beneath it: it names an
# attribute and then says nothing the compiler can turn into SQL.
NO_CONSTRAINT = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:orphan ; sh:minCount 1 ] .
"""

# A sub-attribute. The parent carries no value shape of its own -- the
# constraint is attributed to the child -- so this must NOT be rejected.
SUB_ATTRIBUTE = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:assembly ;
        sh:property [ sh:path iff:torque ;
            sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
                          sh:maxInclusive 100 ] ] ] .
"""

# One level deeper than MAX_SUBPROPERTY_DEPTH allows. Built from the limit
# rather than written out, so that raising it moves this shape with it -- the
# test is that the limit is enforced, whatever it currently is.


def nested(depth):
    body = ('sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ; '
            'sh:maxInclusive 100 ]')
    for level in reversed(range(depth)):
        body = f'sh:property [ sh:path iff:level{level} ; {body} ]'
    return f':S a sh:NodeShape ; sh:targetClass iff:machine ; {body} .\n'


TOO_DEEP = nested(props.MAX_SUBPROPERTY_DEPTH + 2)


@pytest.mark.parametrize('body,operation', [(VALUE_LEVEL_OR, 'OR'),
                                            (VALUE_LEVEL_XONE, 'XONE'),
                                            (VALUE_LEVEL_AND, 'AND')])
def test_value_level_connective_builds_its_own_node(body, operation, tmp_path):
    """
    A connective inside a value shape must reach the circuit with its OWN
    operator. These were rejected at build time until the value level folded
    separately; before that they were dropped outright.
    """
    _, (_, _, _, _, postgres) = compile_shapes(body, tmp_path)
    assert f"'{operation}'" in postgres, \
        f'a value-level sh:{operation.lower()} produced no {operation} node'


def test_connective_below_the_value_level_fails_the_build(tmp_path):
    """
    Two levels are supported: one on the property shape, one on the value
    shape. A third must be rejected rather than quietly compiled to a single
    constraint with its members missing -- which is what it did before.
    """
    with pytest.raises(UnsupportedShape) as raised:
        compile_shapes(NESTED_TOO_DEEP, tmp_path)
    assert 'sh:and' in str(raised.value)


def test_shape_producing_no_constraint_fails_the_build(tmp_path):
    with pytest.raises(UnsupportedShape) as raised:
        compile_shapes(NO_CONSTRAINT, tmp_path)
    assert 'orphan' in str(raised.value)


def test_sub_attribute_is_not_reported(tmp_path):
    """
    The constraint belongs to the sub-attribute, so the parent legitimately
    produces none. Rejecting it would make the checker unusable on any KMS that
    nests attributes.
    """
    _, (_, _, _, _, postgres) = compile_shapes(SUB_ATTRIBUTE, tmp_path)
    assert 'torque' in postgres


def test_excess_depth_fails_the_build(tmp_path):
    """Previously a warning on stdout, which no build step ever read."""
    with pytest.raises(UnsupportedShape) as raised:
        compile_shapes(TOO_DEEP, tmp_path)
    assert 'depth' in str(raised.value)


def test_every_problem_is_reported_at_once(tmp_path):
    """
    One build should surface all of them. Reporting only the first turns a
    broken KMS into a sequence of rebuilds.
    """
    with pytest.raises(UnsupportedShape) as raised:
        compile_shapes(TOO_DEEP + NO_CONSTRAINT, tmp_path)
    message = str(raised.value)
    assert 'depth' in message and 'orphan' in message


def test_problems_are_not_repeated(tmp_path):
    """
    A shape reachable by several routes, or shared across inherited target
    classes, must be reported once. Otherwise the real problems are buried.
    """
    with pytest.raises(UnsupportedShape) as raised:
        compile_shapes(NO_CONSTRAINT, tmp_path)
    assert str(raised.value).count('orphan') == 1


# NGSI-LD defines value predicates the data pipeline does not build attributes
# for. A shape using one is worse than unchecked: create_ngsild_models emits no
# attribute row, so a count reports "Found 0" for an attribute that is present,
# and any bound on it can never fire.
UNSUPPORTED_VALUE_PATHS = [
    'hasLanguageMap',   # LanguageProperty
    'hasVocab',         # VocabProperty
    'hasObjectList',    # ListRelationship
]


@pytest.mark.parametrize('path', UNSUPPORTED_VALUE_PATHS)
def test_unrepresentable_value_path_fails_the_build(path, tmp_path):
    body = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:label ;
        sh:property [ sh:path ngsild:%s ; sh:nodeKind sh:Literal ] ] .
""" % path
    with pytest.raises(UnsupportedShape) as raised:
        compile_shapes(body, tmp_path)
    assert path in str(raised.value)


@pytest.mark.parametrize('path', ['hasValue', 'hasValueList', 'hasJSON'])
def test_supported_value_paths_still_compile(path, tmp_path):
    """Control: the rejection must name the unrepresentable ones only."""
    body = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:label ;
        sh:property [ sh:path ngsild:%s ; sh:nodeKind sh:Literal ;
                      sh:maxCount 1 ] ] .
""" % path
    _, (_, _, _, _, postgres) = compile_shapes(body, tmp_path)
    assert 'label' in postgres
