"""Current and history views of an NGSI-LD graph (implementation-plan.md H2).

An NGSI-LD attribute is identified by (entity, name, datasetId). Four values of
one attribute differing only in observedAt are four UPDATES of one attribute --
the broker keeps the last. In RDF they are four concurrent values, so
`sh:maxCount 1` reports a violation that says nothing about the data: it would
fire on any entity ever updated twice.

So validation of entity state runs against the CURRENT view, which resolves each
(entity, predicate, datasetId) to its latest instance. Aggregation over an
attribute's observations needs the HISTORY view, which keeps them all.

Neither view is universally safe, which is why the choice is declared per shape
rather than defaulted globally: counts on history are wrong in one direction,
aggregates on current are wrong in the other. The platform draws the same line,
per variable rather than per shape -- attributes_view is a top-1 dedup, and
lib/bgp_translation_utils.replace_attributes_table_expression resolves the
AGGREGATED variables to the raw attributes table while everything else falls
back to the view.

collapse_updates() is ported from shacl2flink/tests/pyshacl-compare/compare.py,
guards intact. Both guards are load-bearing and are pinned by tests:

  * datasetId stays in the key. Two datasetIds are two attributes that happen
    to share a name, not one attribute updated twice, and collapsing across
    them would erase a value the broker keeps -- hiding any real count
    violation over them.
  * only an OLDER instance is dropped. Instances tied on time -- the same
    observedAt, or several without one -- are kept together: they are not a
    sequence of updates, and collapsing them would suppress a GENUINE
    cardinality violation, which is the direction that matters.

"Latest" is the platform's: the attribute view keeps the greatest
COALESCE(observedAt, ts), and the bridge stamps an instance that has no
observedAt (or one that does not parse) with its arrival time. So such an
instance counts as NOW (ngsild/timestamps.py) -- it supersedes every stamped
instance of its datasetId -- and timestamps are compared as points in time,
not as text: `+02:00` and a missing millisecond part order correctly.
"""

from dataclasses import dataclass, field
from enum import Enum

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import RDF

NGSILD = 'https://uri.etsi.org/ngsi-ld/'
OBSERVED_AT = URIRef(NGSILD + 'observedAt')
DATASET_ID = URIRef(NGSILD + 'datasetId')
HAS_VALUE_LIST = URIRef(NGSILD + 'hasValueList')
LIST_PAYLOADS = (HAS_VALUE_LIST, URIRef(NGSILD + 'hasObjectList'))


class DataView(Enum):
    CURRENT = 'current'
    HISTORY = 'history'


@dataclass
class ViewStats:
    """What each transform did.

    Reported on every run on purpose. The view builder is the one component
    that REMOVES data before validation, and a transform that quietly drops a
    value is indistinguishable from a validator that missed one.
    """
    view: DataView
    collapsed: int = 0
    empty_lists: int = 0
    notes: list = field(default_factory=list)


def _drop_subtree(graph, node, seen=None):
    """Remove a node and everything reachable from it."""
    seen = seen if seen is not None else set()
    if node in seen:
        return
    seen.add(node)
    for predicate, obj in list(graph.predicate_objects(node)):
        graph.remove((node, predicate, obj))
        if isinstance(obj, BNode):
            _drop_subtree(graph, obj, seen)


INSTANCE_MARKS = {URIRef(NGSILD + name) for name in (
    'hasValue', 'hasObject', 'hasValueList', 'hasObjectList', 'hasJSON', 'hasLanguageMap',
    'hasVocab')}
INSTANCE_TYPES = {URIRef(NGSILD + name) for name in (
    'Property', 'Relationship', 'GeoProperty', 'ListProperty', 'ListRelationship',
    'JsonProperty', 'LanguageProperty', 'VocabProperty')}


def _is_instance(graph, node):
    """An NGSI-LD attribute instance: a blank node with a payload or a kind."""
    return any((node, mark, None) in graph for mark in INSTANCE_MARKS) or \
        any((node, RDF.type, kind) in graph for kind in INSTANCE_TYPES)


def collapse_updates(graph):
    """Keep only the most recent instance of each (entity, predicate, datasetId)
    -- every instance tied for most recent, so a duplicate still counts.

    Returns the number of instances dropped. Mutates the graph in place.
    """
    from .timestamps import NOW, parse

    groups = {}
    for subject, predicate, obj in graph:
        if not isinstance(obj, BNode) or not _is_instance(graph, obj):
            continue
        observed = graph.value(obj, OBSERVED_AT)
        moment = (parse(str(observed)) if observed is not None else None) or NOW
        key = (subject, predicate, graph.value(obj, DATASET_ID))
        groups.setdefault(key, []).append((moment, obj))

    dropped = 0
    for (subject, predicate, _), instances in groups.items():
        if len(instances) < 2:
            continue
        latest = max(moment for moment, _ in instances)
        for moment, node in instances:
            if moment < latest:
                graph.remove((subject, predicate, node))
                _drop_subtree(graph, node, seen=set())
                dropped += 1
    return dropped


def normalise_empty_lists(graph):
    """Type an empty ListProperty as a well-formed one.

    An empty list is rdf:nil, which is an IRI, so `sh:nodeKind sh:BlankNode` on
    ngsild:hasValueList reports a violation for the sole reason that the list is
    empty. That is an artefact of how RDF spells the empty list, not a defect in
    the data. The empty list is replaced by an empty blank node, which is what a
    ListProperty with no elements means.

    Returns the number of empty lists rewritten.
    """
    rewritten = 0
    for payload in LIST_PAYLOADS:           # a ListRelationship's empty list too
        for subject, obj in list(graph.subject_objects(payload)):
            if obj != RDF.nil:
                continue
            graph.remove((subject, payload, obj))
            graph.add((subject, payload, BNode()))
            rewritten += 1
    return rewritten


def build_view(graph, view=DataView.CURRENT):
    """Return (view graph, stats). The input graph is never mutated."""
    out = Graph()
    for prefix, namespace in graph.namespaces():
        out.bind(prefix, namespace)
    for triple in graph:
        out.add(triple)

    stats = ViewStats(view=view)
    stats.empty_lists = normalise_empty_lists(out)
    if view is DataView.CURRENT:
        stats.collapsed = collapse_updates(out)
    else:
        stats.notes.append('history view: attribute instances kept in full')
    return out, stats
