"""The cardinality suite: implementation-plan.md section 5.1.

The view builder is the one component that REMOVES data before validation, so
these tests pin both directions. It must remove the spurious violation, and it
must be incapable of removing a real one.
"""

from rdflib import BNode, Graph, Literal, Namespace, URIRef

from semforge.ngsild import DataView, build_view, collapse_updates
from semforge.validate.orchestrator import validate_raw

NGSILD = Namespace('https://uri.etsi.org/ngsi-ld/')
EX = Namespace('https://example.org/')
STRENGTH = URIRef('https://industryfusion.github.io/contexts/example/v0/base_entities/hasStrength')
FILTER1 = URIRef('urn:filter:1')


def _instances(graph, subject, predicate):
    return list(graph.objects(subject, predicate))


def test_1_collapse_keeps_the_latest_value(model_graph):
    """urn:filter:1 has four hasStrength instances; the broker keeps 0.6."""
    assert len(_instances(model_graph, FILTER1, STRENGTH)) == 4

    current, stats = build_view(model_graph, DataView.CURRENT)
    remaining = _instances(current, FILTER1, STRENGTH)
    assert len(remaining) == 1
    assert stats.collapsed == 3

    value = current.value(remaining[0], NGSILD.hasValue)
    assert float(value) == 0.6, 'collapse kept an instance, but not the latest one'


def test_2_without_the_collapse_the_count_constraint_fires(corpus, model_graph):
    """The guard: nobody can delete the normaliser and still see green.

    On the history view the four updates are four concurrent RDF values, so
    maxCount 1 reports a violation -- on data that is correct, and on a shape
    that is correct. It would fire on any entity ever updated twice.
    """
    history = validate_raw(model_graph, corpus.shapes, corpus.knowledge,
                           view=DataView.HISTORY)
    offending = [r for r in history.violations
                 if r.resource == str(FILTER1)
                 and r.attribute == 'hasStrength'
                 and 'Count' in r.component]
    assert offending, 'expected a spurious cardinality violation on the history view'

    current = validate_raw(model_graph, corpus.shapes, corpus.knowledge,
                           view=DataView.CURRENT)
    assert not [r for r in current.violations
                if r.resource == str(FILTER1) and r.attribute == 'hasStrength'], \
        'the collapse should have removed the spurious cardinality violation'


def _two_datasets_each_updated_twice():
    graph = Graph()
    for dataset, values in (('urn:ds:a', [('1', '2024-01-01T00:00:00.000Z'),
                                          ('2', '2024-01-01T00:00:01.000Z')]),
                            ('urn:ds:b', [('3', '2024-01-01T00:00:00.000Z'),
                                          ('4', '2024-01-01T00:00:01.000Z')])):
        for value, observed in values:
            node = BNode()
            graph.add((EX.entity, EX.attr, node))
            graph.add((node, NGSILD.hasValue, Literal(value)))
            graph.add((node, NGSILD.observedAt, Literal(observed)))
            graph.add((node, NGSILD.datasetId, URIRef(dataset)))
    return graph


def test_3_datasetid_stays_in_the_collapse_key():
    """4 instances over 2 datasetIds collapse to 2, not to 1.

    Drop datasetId from the key and two attributes that merely share a name
    become one -- which HIDES any real count violation across them.
    """
    graph = _two_datasets_each_updated_twice()
    assert len(_instances(graph, EX.entity, EX.attr)) == 4

    dropped = collapse_updates(graph)
    remaining = _instances(graph, EX.entity, EX.attr)
    assert dropped == 2
    assert len(remaining) == 2

    kept = sorted(str(graph.value(n, NGSILD.hasValue)) for n in remaining)
    assert kept == ['2', '4'], 'each datasetId should keep its own latest value'


def test_4_instances_without_observedat_are_never_collapsed():
    """Repeated values with no timestamp are not an update sequence.

    This is the direction that matters: the normaliser must not be able to
    suppress a GENUINE cardinality violation.
    """
    graph = Graph()
    for value in ('1', '2'):
        node = BNode()
        graph.add((EX.entity, EX.attr, node))
        graph.add((node, NGSILD.hasValue, Literal(value)))

    dropped = collapse_updates(graph)
    assert dropped == 0
    assert len(_instances(graph, EX.entity, EX.attr)) == 2


def test_5_history_view_keeps_every_instance(model_graph):
    """A shape declaring history sees all four observations, not one."""
    history, stats = build_view(model_graph, DataView.HISTORY)
    assert len(_instances(history, FILTER1, STRENGTH)) == 4
    assert stats.collapsed == 0


def test_the_input_graph_is_never_mutated(model_graph):
    before = len(model_graph)
    build_view(model_graph, DataView.CURRENT)
    build_view(model_graph, DataView.HISTORY)
    assert len(model_graph) == before
