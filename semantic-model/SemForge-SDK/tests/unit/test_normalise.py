"""Naming a result after the attribute that owns it."""

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import SH

from semforge.validate import normalise

NGSILD = Namespace('https://uri.etsi.org/ngsi-ld/')
EX = Namespace('https://example.org/')


def test_local_strips_slash_and_hash():
    assert normalise.local(URIRef('https://a/b/name')) == 'name'
    assert normalise.local(URIRef('https://a/b#name')) == 'name'


def test_owner_of_an_attribute_node_is_the_entity():
    graph = Graph()
    node = BNode()
    graph.add((EX.entity, EX.attr, node))
    graph.add((node, NGSILD.hasValue, Literal(1)))

    owner, edge = normalise.owner_and_edge(node, graph)
    assert owner == str(EX.entity)
    assert edge == EX.attr


def test_the_climb_returns_the_edge_closest_to_the_node():
    """A sub-attribute is named after itself, not after its grandparent.

    Returning the outermost edge instead named every nested constraint after
    the attribute containing it.
    """
    graph = Graph()
    outer, inner = BNode(), BNode()
    graph.add((EX.entity, EX.assembly, outer))
    graph.add((outer, EX.bolt, inner))
    graph.add((inner, NGSILD.hasValue, Literal(1)))

    owner, edge = normalise.owner_and_edge(inner, graph)
    assert owner == str(EX.entity)
    assert edge == EX.bolt


def test_value_edges_are_stepped_over():
    """ngsild:hasValue says how a value is stored, not which attribute it is."""
    graph = Graph()
    node = BNode()
    value = BNode()
    graph.add((EX.entity, EX.attr, node))
    graph.add((node, NGSILD.hasValue, value))

    owner, edge = normalise.owner_and_edge(value, graph)
    assert owner == str(EX.entity)
    assert edge == EX.attr


def test_a_cycle_does_not_hang_the_climb():
    graph = Graph()
    a, b = BNode(), BNode()
    graph.add((a, EX.p, b))
    graph.add((b, EX.p, a))
    assert normalise.owner_and_edge(a, graph) == (None, None)


def test_inverse_path_recovers_the_relationship_predicate():
    """( [^ngsild:hasObject] [^ex:hasPart] ) is reported as an unnamed node."""
    graph = Graph()
    first, second = BNode(), BNode()
    graph.add((first, SH.inversePath, NGSILD.hasObject))
    graph.add((second, SH.inversePath, EX.hasPart))
    path = BNode()
    Collection(graph, path, [first, second])

    assert normalise.inverse_predicate(path, graph) == EX.hasPart


def test_inverse_path_ignores_a_sequence_that_is_not_the_two_hop_form():
    graph = Graph()
    first = BNode()
    graph.add((first, SH.inversePath, EX.other))
    path = BNode()
    Collection(graph, path, [first])
    assert normalise.inverse_predicate(path, graph) is None
    assert normalise.inverse_predicate(URIRef('urn:x'), graph) is None


def test_owning_shape_walks_up_to_the_named_shape():
    graph = Graph()
    nested = BNode()
    graph.add((EX.MyShape, SH.property, nested))
    assert normalise.owning_shape(nested, graph) == str(EX.MyShape)


def test_owning_shape_passes_a_named_shape_through():
    assert normalise.owning_shape(EX.MyShape, Graph()) == str(EX.MyShape)


def test_owning_shape_returns_none_when_nothing_encloses_it():
    assert normalise.owning_shape(BNode(), Graph()) is None
