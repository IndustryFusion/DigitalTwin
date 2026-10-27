#
# Copyright (c) 2026 IndustryFusion Foundation
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

"""Run each view's shapes against that view's data, then merge.

pyshacl evaluates ONE graph, so a shape that reads an attribute's history and a
shape that reads its current state cannot share a run. They are partitioned by
declared view and merged afterwards.
"""

from rdflib import Graph, URIRef

from ..errors import Diagnostic, DiagnosticSet
from ..ngsild import DataView, build_view
from . import normalise
from . import shapes as shape_views
from .adapters import pyshacl_adapter
from .applicable import enumerate_pairs
from .results import Report, Result, Status


def _attributes_of(graph, entity):
    """The local names of every attribute an entity has: its own, its
    attributes' sub-attributes (NGSI-LD attributes are blank nodes), and
    the attributes pointing at it (an inverse path names one of those)."""
    from rdflib import BNode

    names, seen, todo = set(), set(), [entity]
    while todo:
        node = todo.pop()
        if node in seen:
            continue
        seen.add(node)
        for predicate, value in graph.predicate_objects(node):
            names.add(normalise.local(predicate))
            if isinstance(value, BNode):
                todo.append(value)
    # Pointed at: a relationship reaches its object through the attribute's
    # node (hasCartridge [ hasObject <cartridge> ]), so the attribute's name
    # is one step further back.
    for source, predicate in graph.subject_predicates(entity):
        names.add(normalise.local(predicate))
        if isinstance(source, BNode):
            names.update(normalise.local(p) for _, p in graph.subject_predicates(source))
    return names


def validate_graphs(data_graph, shapes_graph, knowledge_graph=None, strict=True,
                    rules=True, cut=True, only=None, near=True):
    """Validate one already-loaded package. Returns a Report.

    `only` -- a set of shape IRIs (str) -- evaluates just those shapes: the
    editor's incremental revalidation (editor/incremental.py). Rules still run
    with every shape, since they rewrite the data all shapes see.

    Rules are expanded first, with NGSI-LD update semantics applied between
    iterations. pyshacl's advanced mode would run them too, but as pure triple
    ADDITION -- which makes every rule that rewrites an existing attribute
    manufacture a cardinality violation against its own shape.
    """
    if knowledge_graph is not None and isinstance(shapes_graph, Graph):
        from .readset import knowledge_for
        from .readset import near as reachable

        # Only what this data can reach (readset.near): a test case of one
        # entity spent 2.2 s copying 31,356 knowledge triples it never touched.
        reduced = reachable(shapes_graph, knowledge_graph, data_graph) if near else None
        if reduced is not None:
            knowledge_graph = reduced
        elif cut:
            # Else only what some constraint can read (readset.knowledge_for):
            # the rest is carried through rules, view and pyshacl for nothing
            # -- 217,582 triples where 31,356 are read, on the OPC UA pumps.
            knowledge_graph = knowledge_for(shapes_graph, knowledge_graph)

    diagnostics = DiagnosticSet()
    for diagnostic in shape_views.check_declarations(shapes_graph):
        diagnostics.add(diagnostic)
    if strict:
        diagnostics.fail_loud(
            'ERROR: the following shapes declare a data view their body '
            'contradicts, and would be evaluated over the wrong instances:')

    if rules:
        from ..rules import run_rules
        run = run_rules(data_graph, shapes_graph, knowledge_graph)
        data_graph = run.graph
        for diagnostic in run.diagnostics:
            diagnostics.add(diagnostic)
        if strict:
            diagnostics.fail_loud('ERROR: rule evaluation did not terminate:')

    report = Report(diagnostics=list(diagnostics))
    report.rule_iterations = run.iterations if rules else 0
    expected = set()
    unmapped = []

    for view, view_shapes in sorted(shape_views.partition(shapes_graph).items(),
                                    key=lambda item: item[0].value):
        if only is not None:
            # An anonymous shape cannot be told apart between two versions:
            # it is always evaluated again.
            view_shapes = [s for s in view_shapes
                           if not isinstance(s, URIRef) or str(s) in only]
            if not view_shapes:
                continue
        graph, stats = build_view(data_graph, view)
        report.view_stats.append(stats)
        subset = shape_views.subgraph_for(shapes_graph, view_shapes)

        violations = pyshacl_adapter.run(graph, subset, knowledge_graph, view=view.value)
        report.results.extend(violations)

        pairs, inapplicable = enumerate_pairs(
            shapes_graph, graph, knowledge_graph, shapes=view_shapes)
        expected |= pairs

        # A shape whose target matched nothing is reported, not omitted: a
        # shape that silently stopped matching anything has no other symptom.
        for shape, declared in inapplicable:
            for attribute, component in declared:
                report.results.append(Result(
                    resource='', attribute=attribute, component=component,
                    shape=shape, severity='info',
                    status=Status.NOT_APPLICABLE, view=view.value,
                    shape_curie=normalise.curie(shapes_graph, shape)))

    # Subtract what fired from what should have been evaluated. What is left
    # conformed -- and can now be SAID to have conformed, rather than inferred
    # from silence.
    fired = {r.key() for r in report.results if r.status is Status.VIOLATED}
    present = {}
    for resource, attribute, component, shape in sorted(expected - fired):
        if resource not in present:
            present[resource] = _attributes_of(data_graph, URIRef(resource))
        report.results.append(Result(
            resource=resource, attribute=attribute, component=component,
            shape=shape, severity='info', status=Status.CONFORMANT,
            shape_curie=normalise.curie(shapes_graph, shape),
            vacuous=bool(attribute) and attribute.split('.')[0] not in present[resource]))

    # The drift check. A reported result the enumerator did not predict means
    # the enumerator is wrong, and an enumerator that quietly under-counts turns
    # V1 into decoration.
    for key in sorted(fired - expected):
        unmapped.append(key)
        report.diagnostics.append(Diagnostic(
            code='SF-ENUM-001', category='internal', severity='error',
            subject=key[3],
            message=(f'{key[0]} {key[2]}({key[1]}) was reported by pyshacl but '
                     f'the applicable-set enumerator did not predict it; '
                     f'conformance for this shape cannot be trusted')))

    report.complete = not unmapped
    return report


def validate_package(package, strict=True):
    """Validate a loaded Package."""
    return validate_graphs(package.model, package.shapes, package.knowledge,
                           strict=strict)


def validate_raw(data_graph, shapes_graph, knowledge_graph=None,
                 view=DataView.CURRENT):
    """Validate every shape against one named view, ignoring declarations.

    Used by tests that need to show what a view does -- notably that the
    cardinality violation is real without the collapse and gone with it.
    """
    graph, stats = build_view(data_graph, view)
    report = Report()
    report.view_stats.append(stats)
    shapes = shapes_graph if isinstance(shapes_graph, Graph) else Graph().parse(shapes_graph)
    report.results.extend(pyshacl_adapter.run(
        graph, shapes, knowledge_graph, view=view.value))
    return report
