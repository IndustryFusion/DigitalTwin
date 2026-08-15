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
sh:node is an indirection, not a constraint of its own.

The OPC UA generator writes its ValueRank constraints once as a named shape and
points at them from every variable. Nothing downstream understands that, so
before these tests a referencing property shape reached the extractor carrying
no value shape at all.

The property that matters is equivalence: resolving the reference must produce
what writing the constraints inline would have produced, and nothing else.
tests/sql-tests/kms-constraints/test16 pins that end to end against test15's
models; these pin the rewrite itself, including the cases it must refuse.
"""

import rdflib
import pytest
from rdflib.namespace import SH

import lib.shacl_properties_to_sql as props
from lib.utils import UnsupportedShape


PREAMBLE = """
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix iff:  <https://industry-fusion.com/types/v0.9/> .
@prefix :     <https://industry-fusion.com/shapes/v0.9/> .

"""


def graph(body):
    g = rdflib.Graph()
    g.parse(data=PREAMBLE + body, format='turtle')
    return g


REFERENCE = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:variable ; sh:maxCount 1 ;
                  sh:node :ScalarDouble ] .

:ScalarDouble a sh:NodeShape ;
    sh:message "a scalar double" ;
    sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ;
                  sh:nodeKind sh:Literal ] .
"""


def test_referenced_constraints_land_on_the_referring_shape():
    g = graph(REFERENCE)
    props.expand_node_shapes(g)

    prop = next(g.subjects(SH.path,
                           rdflib.URIRef(
                               'https://industry-fusion.com/types/v0.9/variable')))
    value_shapes = list(g.objects(prop, SH.property))
    assert len(value_shapes) == 1
    assert next(g.objects(value_shapes[0], SH.path)) == \
        rdflib.URIRef('https://uri.etsi.org/ngsi-ld/hasValue')
    assert next(g.objects(value_shapes[0], SH.datatype)) == \
        rdflib.URIRef('http://www.w3.org/2001/XMLSchema#double')


def test_the_reference_itself_is_gone():
    """A leftover sh:node would be re-expanded on any later pass."""
    g = graph(REFERENCE)
    props.expand_node_shapes(g)
    assert not list(g.subject_objects(SH.node))


def test_the_referenced_shape_is_removed():
    """
    An untargeted shape left in the graph still answers graph-wide queries.
    That is not cosmetic: its orphaned value shapes were picked up as
    constraints in their own right, and a hasValueList count that belonged
    under hasVariable was published as a top-level one -- firing on every
    valid scalar.
    """
    g = graph(REFERENCE)
    props.expand_node_shapes(g)
    scalar = rdflib.URIRef('https://industry-fusion.com/shapes/v0.9/ScalarDouble')
    assert not list(g.predicate_objects(scalar))


def test_a_targeted_shape_is_kept():
    """It is a real node shape that happens to also be referenced."""
    g = graph(REFERENCE.replace(
        ':ScalarDouble a sh:NodeShape ;',
        ':ScalarDouble a sh:NodeShape ; sh:targetClass iff:other ;'))
    props.expand_node_shapes(g)
    scalar = rdflib.URIRef('https://industry-fusion.com/shapes/v0.9/ScalarDouble')
    assert list(g.objects(scalar, SH.property))


TWO_REFERENCES = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:one ; sh:node :ScalarDouble ] ,
                [ sh:path iff:two ; sh:node :ScalarDouble ] .

:ScalarDouble a sh:NodeShape ;
    sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] .
"""


def test_each_reference_gets_its_own_copy():
    """
    Sharing the blank nodes would give both properties the same clause nodes,
    and the circuit builder keys its groups on those -- so two attributes
    would collide into one set of constraints.
    """
    g = graph(TWO_REFERENCES)
    props.expand_node_shapes(g)

    value_shapes = set()
    for name in ('one', 'two'):
        prop = next(g.subjects(SH.path, rdflib.URIRef(
            f'https://industry-fusion.com/types/v0.9/{name}')))
        shapes = list(g.objects(prop, SH.property))
        assert len(shapes) == 1, f'{name} did not receive the constraints'
        value_shapes.add(shapes[0])
    assert len(value_shapes) == 2, 'both references share one value shape'


CONFLICTING_CONNECTIVE = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:variable ;
        sh:or ( [ sh:property [ sh:path ngsild:hasValue ; sh:minInclusive 5 ] ]
                [ sh:property [ sh:path ngsild:hasValue ; sh:maxInclusive 1 ] ] ) ;
        sh:node :Either ] .

:Either a sh:NodeShape ;
    sh:or ( [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] ]
            [ sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:integer ] ] ) .
"""


def test_two_connectives_on_one_node_are_refused():
    """
    connective_clauses() yields the branches of EVERY connective on a node as
    one set, so conjoining two sh:or lists reads as a single wider sh:or --
    an AND of two disjunctions silently becoming one disjunction. Strictly
    weaker, and invisible in the output, so it must fail the build instead.
    """
    with pytest.raises(UnsupportedShape) as raised:
        props.expand_node_shapes(graph(CONFLICTING_CONNECTIVE))
    assert 'weaken' in str(raised.value)


CONFLICTING_PARAMETER = """
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:variable ; sh:maxCount 1 ; sh:node :Wider ] .

:Wider a sh:NodeShape ; sh:maxCount 5 ;
    sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] .
"""


def test_two_values_of_one_parameter_are_refused():
    with pytest.raises(UnsupportedShape) as raised:
        props.expand_node_shapes(graph(CONFLICTING_PARAMETER))
    assert 'maxCount' in str(raised.value)


def test_a_self_reference_is_refused():
    with pytest.raises(UnsupportedShape) as raised:
        props.expand_node_shapes(graph("""
:S a sh:NodeShape ; sh:targetClass iff:machine ; sh:node :S .
"""))
    assert 'cycle' in str(raised.value)


def test_a_cycle_is_refused():
    """
    Named as a cycle, not as a self-reference. One round of expansion turns
    A -> B -> A into a self-reference on A, so reporting what expansion sees
    would send the author looking at the wrong shape.
    """
    with pytest.raises(UnsupportedShape) as raised:
        props.expand_node_shapes(graph("""
:S a sh:NodeShape ; sh:targetClass iff:machine ; sh:node :A .
:A a sh:NodeShape ; sh:node :B .
:B a sh:NodeShape ; sh:node :A .
"""))
    assert 'cycle' in str(raised.value)


def test_deactivated_is_refused():
    """
    Dropping it would switch constraints back on that the author switched
    off; copying it would switch off the referring shape's own ones too.
    """
    with pytest.raises(UnsupportedShape) as raised:
        props.expand_node_shapes(graph("""
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:variable ; sh:node :Off ] .
:Off a sh:NodeShape ; sh:deactivated true ;
    sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] .
"""))
    assert 'deactivated' in str(raised.value)


def test_a_chain_of_references_resolves():
    g = graph("""
:S a sh:NodeShape ; sh:targetClass iff:machine ;
    sh:property [ sh:path iff:variable ; sh:node :A ] .
:A a sh:NodeShape ; sh:node :B .
:B a sh:NodeShape ;
    sh:property [ sh:path ngsild:hasValue ; sh:datatype xsd:double ] .
""")
    props.expand_node_shapes(g)
    prop = next(g.subjects(SH.path, rdflib.URIRef(
        'https://industry-fusion.com/types/v0.9/variable')))
    value_shape = next(g.objects(prop, SH.property))
    assert next(g.objects(value_shape, SH.datatype)) == \
        rdflib.URIRef('http://www.w3.org/2001/XMLSchema#double')
