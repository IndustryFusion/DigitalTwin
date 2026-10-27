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

"""The pyshacl adapter.

Two things here are not obvious and both were learned the expensive way in
shacl2flink/tests/pyshacl-compare/compare.py:

* The knowledge graph belongs in the DATA graph, not in ont_graph. Passed as
  ont_graph it is invisible to sh:class, so every sh:class over a value typed
  only by the knowledge -- `iff:state_OFF a iff:MachineState` -- reports a
  violation that is not one. The validator has to see the same world the
  constraints are written against.

* advanced=True. SHACL-AF is what sh:rule and sh:sparql need, and the kms
  shapes are mostly those.
"""

import pyshacl
from rdflib import Graph
from rdflib.namespace import SH

from .. import normalise
from ..results import Result, Status


def _private_copy(shapes_graph):
    """pyshacl's own copy of a shapes graph, made once per graph.

    What pyshacl writes into it are the same axioms on every run, so a copy it
    has written into before validates exactly as a fresh one -- and copying the
    21,276 triples of the OPC UA pump shapes cost 0.6 s per validation. The
    graph given here is never edited (validate/shapes.subgraph_for keeps one
    per shape set, frozen). Kept only with a frozen graph (rdfio/frozen.py):
    any other is copied every time.
    """
    from ...rdfio.frozen import derived

    def copy():
        shapes = Graph()
        for prefix, namespace in shapes_graph.namespaces():
            shapes.bind(prefix, namespace)
        for triple in shapes_graph:
            shapes.add(triple)
        return shapes
    return derived(shapes_graph, 'pyshacl_copy', copy)


def run(data_graph, shapes_graph, knowledge_graph=None, view='current'):
    """Validate and return normalised Results (violations only).

    A SHACL engine reports violations and nothing else, so every Result here is
    VIOLATED. Establishing which constraints were evaluated and CONFORMED is the
    applicable-set enumerator's job (H1, M2) -- deliberately not faked here,
    because a conformant status this function cannot justify would be exactly
    the silence invariant V1 forbids.
    """
    data = Graph()
    for triple in data_graph:
        data.add(triple)
    if knowledge_graph is not None:
        for triple in knowledge_graph:
            data.add(triple)

    # pyshacl MUTATES the shapes graph it is given -- it injects RDFS axioms
    # such as `owl:Class rdfs:subClassOf rdfs:Class` into it. Handing it the
    # package's own graph makes that graph drift: a cached package accumulates
    # them, and a semantic diff between a validated and an unvalidated copy of
    # the same file reports changes that are not in either file.
    shapes = _private_copy(shapes_graph)

    # `data` is this call's own copy: pyshacl need not clone it again.
    _, report, _ = pyshacl.validate(
        data, shacl_graph=shapes,
        advanced=True, inplace=True, do_owl_imports=False)

    results = []
    for node in report.objects(None, SH.result):
        focus = report.value(node, SH.focusNode)
        path = report.value(node, SH.resultPath)
        component = normalise.local(report.value(node, SH.sourceConstraintComponent))
        source = report.value(node, SH.sourceShape)
        shape = normalise.owning_shape(source, shapes, report)
        curie = normalise.curie(shapes, shape)
        severity = normalise.local(report.value(node, SH.resultSeverity) or SH.Violation)
        message = report.value(node, SH.resultMessage)

        resource, attribute = normalise.attribute_name(
            focus, path, data, shapes, report)
        attribute = normalise.layered(attribute, path, component)
        if resource is None:
            # Cannot be attributed to an entity. Never silently dropped: it is
            # reported as NOT_EVALUATED so it still appears in the report.
            results.append(Result(
                resource=str(focus), attribute='', component=component,
                shape=shape or '',

                severity=severity, status=Status.NOT_EVALUATED,
                message=str(message or ''), view=view, shape_curie=curie))
            continue

        results.append(Result(
            resource=resource, attribute=attribute or '',
            component=component,
            shape=shape or '',
            severity=severity, status=Status.VIOLATED,
            message=str(message or ''), view=view, shape_curie=curie))
    return results
