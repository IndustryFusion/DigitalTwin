from rdflib import Graph, Namespace, BNode, Literal
from rdflib.collection import Collection
from rdflib.namespace import SH
from shacl_normalization import wrap_property_or

EX = Namespace("http://example.org/")


def g_to_triples(g):
    return set(g.triples((None, None, None)))


def test_no_or_only_path():
    g = Graph()
    prop = BNode()
    g.add((EX.shape, SH.property, prop))
    g.add((prop, SH.path, EX.foo))
    triples_before = g_to_triples(g)
    wrap_property_or(g)
    # Should remain unchanged
    assert g_to_triples(g) == triples_before


def test_no_or_with_extras():
    g = Graph()
    prop = BNode()
    g.add((EX.shape, SH.property, prop))
    g.add((prop, SH.path, EX.foo))
    g.add((prop, SH.minCount, Literal(1)))
    g.add((prop, SH.maxCount, Literal(2)))
    wrap_property_or(g)
    # prop should now have only path and sh:or
    assert (prop, SH.path, EX.foo) in g
    or_lists = list(g.objects(prop, SH['or']))
    assert len(or_lists) == 1
    # The or list should have one member, which has minCount and maxCount
    members = list(Collection(g, or_lists[0]))
    assert len(members) == 1
    inner = members[0]
    assert (inner, SH.minCount, Literal(1)) in g
    assert (inner, SH.maxCount, Literal(2)) in g


def test_or_with_extras():
    g = Graph()
    prop = BNode()
    g.add((EX.shape, SH.property, prop))
    g.add((prop, SH.path, EX.foo))
    g.add((prop, SH.minCount, Literal(1)))
    # Add an OR with two branches
    branch1 = BNode()
    branch2 = BNode()
    g.add((branch1, SH.path, EX.bar))
    g.add((branch2, SH.path, EX.baz))
    or_list = BNode()
    Collection(g, or_list, [branch1, branch2])
    g.add((prop, SH['or'], or_list))
    wrap_property_or(g)
    # minCount should be propagated to both branches
    assert (branch1, SH.minCount, Literal(1)) in g
    assert (branch2, SH.minCount, Literal(1)) in g
    # prop should no longer have minCount
    assert not (prop, SH.minCount, Literal(1)) in g


def test_or_with_no_extras():
    g = Graph()
    prop = BNode()
    g.add((EX.shape, SH.property, prop))
    g.add((prop, SH.path, EX.foo))
    # Add an OR with one branch
    branch = BNode()
    g.add((branch, SH.path, EX.bar))
    or_list = BNode()
    Collection(g, or_list, [branch])
    g.add((prop, SH['or'], or_list))
    triples_before = g_to_triples(g)
    wrap_property_or(g)
    # Should remain unchanged
    assert g_to_triples(g) == triples_before


def test_nested_property_shape():
    g = Graph()
    outer = BNode()
    inner = BNode()
    g.add((EX.shape, SH.property, outer))
    g.add((outer, SH.path, EX.outer))
    g.add((outer, SH.property, inner))
    g.add((inner, SH.path, EX.inner))
    g.add((inner, SH.minCount, Literal(1)))
    wrap_property_or(g)
    # inner should now have only path and sh:or
    or_lists = list(g.objects(inner, SH['or']))
    assert len(or_lists) == 1
    members = list(Collection(g, or_lists[0]))
    assert len(members) == 1
    inner_branch = members[0]
    assert (inner_branch, SH.minCount, Literal(1)) in g
