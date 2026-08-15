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
Zero is a constraint value, not a missing one.

rdflib.Literal(0) is falsy. Any parameter extracted with `if row.x` instead of
`if row.x is not None` therefore read a bound of 0 as "no bound given" and left
the constraint out of the build entirely. "at most zero errors" and "must not
be present" are ordinary things to write, and neither was enforced -- with
nothing reported at build time, which is indistinguishable from a model that
conforms.

tests/sql-tests/kms-constraints/test21 pins the same thing end to end. These
pin each parameter on its own, so a regression names the one that broke.
"""

import os
import tempfile

import pytest
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
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .
@prefix : <https://industry-fusion.com/shapes/v0.9/> .

"""

VALUE_SHAPE = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:v ;
        sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ;
                      sh:{parameter} {value} ] ] .
"""

COUNT_SHAPE = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:v ; sh:{parameter} {value} ;
        sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ] ] .
"""


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


def column_of(name):
    return next(index for index, column in enumerate(utils.constraint_table)
                if name in column)


def compiled_value(compiled, parameter):
    column = column_of(parameter)
    return {row[column] for row in constraint_rows(compiled)}


@pytest.mark.parametrize('template,parameter', [
    (VALUE_SHAPE, 'maxInclusive'),
    (VALUE_SHAPE, 'minInclusive'),
    (VALUE_SHAPE, 'maxExclusive'),
    (VALUE_SHAPE, 'minExclusive'),
    (VALUE_SHAPE, 'maxLength'),
    (VALUE_SHAPE, 'minLength'),
    (COUNT_SHAPE, 'maxCount'),
])
def test_a_bound_of_zero_survives_the_build(template, parameter, tmp_path):
    body = template.replace('{parameter}', parameter).replace('{value}', '0')
    assert "'0'" in compiled_value(compile_shapes(body, tmp_path), parameter), \
        f'sh:{parameter} 0 produced no constraint -- the shape would be ' \
        f'accepted and that bound never checked'


@pytest.mark.parametrize('template,parameter', [
    (VALUE_SHAPE, 'maxInclusive'),
    (VALUE_SHAPE, 'maxExclusive'),
    (COUNT_SHAPE, 'maxCount'),
])
def test_a_nonzero_bound_still_survives(template, parameter, tmp_path):
    """Control: the zero case must differ from the absent case, not from this."""
    body = template.replace('{parameter}', parameter).replace('{value}', '7')
    assert "'7'" in compiled_value(compile_shapes(body, tmp_path), parameter)
