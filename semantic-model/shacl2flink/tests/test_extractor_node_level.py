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
Connectives attached directly to a NodeShape.

These group whole shapes rather than the values of one path, so their branches
may each constrain a different property -- something no single sh:path can
express. They are built by walking the shape graph, because a SPARQL property
path can reach the leaves but cannot report the tree that groups them.
"""

import os
import tempfile

import pytest
import rdflib
from rdflib.namespace import SH

import lib.shacl_properties_to_sql as props


# "Either the temperature is at most 50, OR there is a coolant" -- a
# disjunction ACROSS two different properties.
SHAPES = """
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iff: <https://industry-fusion.com/types/v0.9/> .

iff:CutterShape
    a sh:NodeShape ;
    sh:targetClass iff:machine ;
    sh:or (
        [ sh:property [ sh:path iff:hasTemp ;
                        sh:property [ sh:path <https://uri.etsi.org/ngsi-ld/hasValue> ;
                                      sh:maxInclusive 50 ] ] ]
        [ sh:property [ sh:path iff:hasCoolant ;
                        sh:property [ sh:path <https://uri.etsi.org/ngsi-ld/hasValue> ;
                                      sh:minCount 1 ] ] ]
    ) .
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


def _extract(shapes_ttl, tmp_path):
    shapes, knowledge = tmp_path / 'shacl.ttl', tmp_path / 'knowledge.ttl'
    shapes.write_text(shapes_ttl)
    knowledge.write_text(KNOWLEDGE)
    cwd = os.getcwd()
    os.chdir(tempfile.mkdtemp())          # translate() writes into ./output
    try:
        _, (_, _, _, _, postgres) = props.translate(
            str(shapes), str(knowledge), PREFIXES)
    finally:
        os.chdir(cwd)
    return postgres


@pytest.fixture(scope='module')
def extracted(tmp_path_factory):
    return _extract(SHAPES, tmp_path_factory.mktemp('nodelevel'))


def test_node_level_or_builds_a_circuit(extracted):
    """A sh:or on the NodeShape becomes an OR node, not nothing."""
    assert "'OR'" in extracted, \
        'node-level sh:or produced no OR edge -- the shape would be ' \
        'silently unvalidated'


def test_both_branch_properties_are_extracted(extracted):
    """Each branch constrains a different property; both must be reached."""
    assert 'hasTemp' in extracted
    assert 'hasCoolant' in extracted


def test_branch_properties_do_not_publish_on_their_own(extracted):
    """
    A property absorbed into a node-level connective must not raise its own
    alert -- otherwise 'temperature too high' fires even when the coolant
    branch satisfies the disjunction.
    """
    publishes = extracted.count("'PUBLISH'")
    ors = extracted.count("'OR'")
    assert ors >= 2, 'expected the two branches wired into an OR'
    # one PUBLISH per (inherited target class), for the OR root only
    assert publishes < ors, \
        'branch properties appear to be published individually'


def test_cycle_is_rejected_not_silently_ignored(tmp_path):
    """
    A cyclic shape graph has no finite circuit and Flink SQL has no fixpoint,
    so this must fail loudly at build time rather than emit something wrong.
    """
    graph = rdflib.Graph()
    graph.parse(data=SHAPES)
    shape = rdflib.URIRef('https://industry-fusion.com/types/v0.9/CutterShape')
    # make the shape contain itself
    graph.add((shape, SH['not'], shape))
    ctx = {'checks': [], 'combination': [], 'next_id': 0, 'property_top': {},
           'consumed': set(), 'memo': {}, 'stack': set()}
    with pytest.raises(props.ShapeCycle):
        props.walk_shape(graph, shape, 'iff:machine', ctx)
