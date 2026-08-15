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
Constraint parameters written BESIDE a connective must survive, and must stay
outside it.

`sh:minCount 1` next to `sh:xone (...)` is a conjunction: the attribute must be
present AND its value must satisfy exactly one branch. It is compiled as its own
published constraint, so violating either raises an alert and the connective
keeps exactly the arity the shape declared.

This used to be rewritten by a normalisation pass before extraction, and both
outcomes were wrong and silent: the parameter vanished when the property node
carried no value shape, or became one more MEMBER of the connective when it did
-- turning XONE(a, b) into XONE(a, b, minCount). Shapes are now read as written.
"""

import os
import re
import tempfile

import rdflib
import pytest

import lib.shacl_properties_to_sql as props
import lib.utils as utils


HAS_VALUE = '<https://uri.etsi.org/ngsi-ld/hasValue>'

SHAPES = f"""
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .

iff:ParamShape
    a sh:NodeShape ;
    sh:targetClass iff:machine ;

    # xone with NO inner value shape on the node -- the parameters used to be
    # dropped outright here.
    sh:property [
        sh:path iff:xoneState ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:xone (
            [ sh:property [ sh:path {HAS_VALUE} ; sh:minInclusive 100 ] ]
            [ sh:property [ sh:path {HAS_VALUE} ; sh:maxInclusive 10 ] ]
        ) ;
    ] ;

    # The other failure mode: a value shape IS present on the node, so the
    # parameters were not dropped -- they were absorbed as a THIRD member of
    # the xone, silently turning 'exactly one of two' into 'exactly one of
    # three'.
    sh:property [
        sh:path iff:xoneValueState ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:property [ sh:path {HAS_VALUE} ; sh:nodeKind sh:Literal ] ;
        sh:xone (
            [ sh:property [ sh:path {HAS_VALUE} ; sh:minInclusive 100 ] ]
            [ sh:property [ sh:path {HAS_VALUE} ; sh:maxInclusive 10 ] ]
        ) ;
    ] ;

    # sh:not, single member, same question.
    sh:property [
        sh:path iff:notState ;
        sh:minCount 1 ;
        sh:not [ sh:property [ sh:path {HAS_VALUE} ; sh:in ( "FORBIDDEN" ) ] ] ;
    ] ;

    # sh:or gets no special treatment any more. Its parameters become an
    # independent constraint too, which is equivalent to the distribution the
    # old normaliser performed: (A and C) or (B and C) == (A or B) and C.
    sh:property [
        sh:path iff:orState ;
        sh:minCount 1 ;
        sh:or (
            [ sh:property [ sh:path {HAS_VALUE} ; sh:minInclusive 100 ] ]
            [ sh:property [ sh:path {HAS_VALUE} ; sh:maxInclusive 10 ] ]
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
def compiled(tmp_path_factory):
    """Extract straight from the shapes as written."""
    tmp = tmp_path_factory.mktemp('connective_params')
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


# Column positions in the generated constraint_table INSERT. Substring matching
# is not good enough here: a row whose *id* is '1' contains "'1'," just as a row
# whose minCount is 1 does, which silently turns a dropped parameter into a
# passing test.
#
# Read off the schema rather than written down. These were literals until
# raising the subproperty depth limit added a path column and shifted
# everything after it -- at which point the tests read minCount out of the
# wrong field and failed for a reason that had nothing to do with connectives.
def column_of(name):
    return next(index for index, column in enumerate(utils.constraint_table)
                if name in column)


MIN_COUNT_COLUMN = column_of('minCount')
MAX_COUNT_COLUMN = column_of('maxCount')


def constraint_rows(compiled):
    """
    One field list per constraint_table row, aligned with the schema.

    Splitting on `), (` looks like it separates rows, but it also matches
    inside one: `CAST (NULL as TEXT), CAST (` is the same text. Rows came back
    with fields sliced apart and differing lengths, and the column indices
    below were tuned to that -- landing on the right field by luck rather than
    by position. Tracking quotes and nesting instead makes the index mean what
    it says.
    """
    line = next(ln for ln in compiled.split('\n') if 'constraint_table' in ln)
    values = line[line.index('VALUES') + len('VALUES'):].rstrip(';')

    rows, fields, current, depth, quoted = [], [], '', 0, False
    for character in values:
        if quoted:
            current += character
            quoted = character != "'"
        elif character == "'":
            current += character
            quoted = True
        elif character == '(':
            depth += 1
            if depth == 1:
                fields, current = [], ''
            else:
                current += character
        elif character == ')':
            depth -= 1
            if depth == 0:
                fields.append(current.strip())
                rows.append(fields)
                current = ''
            else:
                current += character
        elif character == ',' and depth == 1:
            fields.append(current.strip())
            current = ''
        elif depth >= 1:
            current += character
    return rows


def rows_for_path(compiled, path):
    return [f for f in constraint_rows(compiled) if any(path in x for x in f)]


def members_of(compiled, operation):
    """Ids feeding the given circuit operation, from the combination table."""
    line = next(ln for ln in compiled.split('\n')
                if 'constraint_combination_table' in ln)
    return re.findall(rf"\('(\d+)','{operation}','\d+'\)", line)


@pytest.mark.parametrize('path', ['xoneState', 'xoneValueState', 'notState'])
def test_parameters_beside_a_connective_are_compiled(compiled, path):
    """The count parameters must produce a constraint row of their own."""
    rows = rows_for_path(compiled, path)
    assert rows, f'{path} produced no constraint rows at all'
    with_counts = [f for f in rows if f[MIN_COUNT_COLUMN] == "'1'"]
    assert with_counts, \
        f"sh:minCount beside the connective on {path} produced no row -- " \
        f'the shape would be accepted and that parameter never checked'


def test_lifted_parameters_do_not_join_the_connective(compiled):
    """
    Each XONE must keep exactly the two branches its shape declared.

    A third member changes the operator's truth table: 'exactly one of two' is
    not 'exactly one of three', so every focus node would be judged against a
    constraint nobody wrote. Two xone shapes are declared, so there are two
    circuit nodes with two members each.
    """
    members = members_of(compiled, 'XONE')
    assert len(members) == 4, \
        f'expected 2 xone nodes with 2 members each, got {len(members)} edges'


def test_not_keeps_its_single_member(compiled):
    assert len(members_of(compiled, 'NOT')) == 1


def test_or_is_treated_like_every_other_connective(compiled):
    """
    sh:or keeps its two branches and gets its parameters as a separate
    constraint, exactly like sh:and/sh:xone/sh:not.

    The old normaliser instead distributed them into each branch. That is
    logically the same -- (A and C) or (B and C) == (A or B) and C -- but it
    made sh:or the one connective handled differently, and folded the parameter
    into the OR's alert instead of raising its own.
    """
    assert len(members_of(compiled, 'OR')) == 2
    or_rows = rows_for_path(compiled, 'orState')
    # two branches, one independent parameter constraint, and the OR circuit
    # node -- which now carries the path in its eventName and so matches here
    assert len(or_rows) == 4, \
        'expected 2 branches, one parameter constraint and the OR node'
    with_counts = [f for f in or_rows if f[MIN_COUNT_COLUMN] == "'1'"]
    assert len(with_counts) == 1, \
        'the minCount beside sh:or should be exactly one constraint of its own'
