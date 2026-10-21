"""Rule evaluation to a bounded fixpoint, with NGSI-LD update semantics.

sh:rule is architecturally different from every other constraint because it
WRITES, and its output becomes its own input. Three properties follow.

**Rule output is an update, not an addition.** A rule constructing a second
hasWasteclass adds a triple in RDF; as an NGSI-LD update it REPLACES the value
that was there. Without that, every rule that rewrites an existing attribute
manufactures a cardinality violation against its own shape -- which is exactly
the one irreducible entry in shacl2flink's expected-divergences.txt, and exactly
what the corpus reports until this runs.

**Termination comes from the guard, not from the engine.** The kms rules bound
themselves: isUsedFrom writes once under FILTER NOT EXISTS on itself, and waste
class only ever escalates, guarded by FILTER NOT EXISTS over the transitive
higherHazardLevel ordering. A rule whose guard does not actually bound it is a
modelling defect.

**So the bound is declared and its breach is an error.** Hitting the iteration
limit is reported as a package error naming the rules still firing -- never a
silent stop, and never an unbounded loop against a live broker.
"""

from dataclasses import dataclass, field

import pyshacl
from rdflib import BNode, Graph, URIRef

from ..errors import Diagnostic
from ..ngsild.views import DATASET_ID, OBSERVED_AT

DEFAULT_MAX_ITERATIONS = 10


@dataclass
class RuleRun:
    graph: Graph
    iterations: int = 0
    added: int = 0
    replaced: int = 0
    converged: bool = True
    diagnostics: list = field(default_factory=list)


def _attribute_instances(graph):
    """{(entity, predicate, datasetId): {node}} for every attribute instance."""
    found = {}
    for subject, predicate, obj in graph:
        if not isinstance(obj, BNode) or not isinstance(subject, URIRef):
            continue
        found.setdefault((subject, predicate, graph.value(obj, DATASET_ID)),
                         set()).add(obj)
    return found


def _drop(graph, node, seen=None):
    seen = seen if seen is not None else set()
    if node in seen:
        return
    seen.add(node)
    for predicate, obj in list(graph.predicate_objects(node)):
        graph.remove((node, predicate, obj))
        if isinstance(obj, BNode):
            _drop(graph, obj, seen)


def apply_update_semantics(graph, before):
    """A value a rule constructed REPLACES the instance it was derived from.

    `before` is the set of attribute instance nodes present prior to the rule
    pass. Where a rule added an instance for an attribute that already had one,
    the pre-existing instance is removed -- which is what an NGSI-LD update
    does, and what the platform's attributes_view does by dedup.

    Instances that carry an observedAt are left alone: those are a genuine
    observation history, and the current-view collapse already resolves them.
    """
    replaced = 0
    for key, nodes in _attribute_instances(graph).items():
        added = nodes - before.get(key, set())
        if not added or len(nodes) < 2:
            continue
        entity, predicate, _ = key
        for node in nodes - added:
            if graph.value(node, OBSERVED_AT) is not None:
                continue
            graph.remove((entity, predicate, node))
            _drop(graph, node)
            replaced += 1
    return replaced


def run_rules(data_graph, shapes_graph, knowledge_graph=None,
              max_iterations=DEFAULT_MAX_ITERATIONS):
    """Expand rules to a fixpoint. The input graph is never mutated."""
    working = Graph()
    for prefix, namespace in data_graph.namespaces():
        working.bind(prefix, namespace)
    for triple in data_graph:
        working.add(triple)
    if knowledge_graph is not None:
        for triple in knowledge_graph:
            working.add(triple)

    # Same reason as the validator adapter: pyshacl writes into the shapes
    # graph it is handed.
    shapes = Graph()
    for triple in shapes_graph:
        shapes.add(triple)

    run = RuleRun(graph=working)
    for iteration in range(1, max_iterations + 1):
        before_size = len(working)
        before_instances = _attribute_instances(working)

        pyshacl.shacl_rules(working, shacl_graph=shapes,
                            advanced=True, inplace=True, do_owl_imports=False)

        run.replaced += apply_update_semantics(working, before_instances)
        run.iterations = iteration
        added = len(working) - before_size + run.replaced
        if len(working) == before_size:
            run.added = max(run.added, 0)
            return run
        run.added += max(added, 0)
    else:
        run.converged = False
        run.diagnostics.append(Diagnostic(
            code='SF-RULE-001', category='package', severity='error',
            message=(f'rules did not reach a fixpoint within {max_iterations} '
                     f'iterations and are still adding triples. A rule whose '
                     f'guard does not bound it is a modelling defect: check the '
                     f'FILTER NOT EXISTS guards of the sh:rule shapes.')))
    return run
