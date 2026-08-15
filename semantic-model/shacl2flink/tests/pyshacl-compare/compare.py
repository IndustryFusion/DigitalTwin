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
Validate every kms fixture with pyshacl as well, and compare.

The fixtures say what we EXPECTED; they cannot say what SHACL requires. Every
silent failure found in this compiler so far looked identical from inside: an
alert that never fired is indistinguishable from a constraint that was
satisfied, and a fixture written against the buggy behaviour pins the bug.
An independent implementation is the only thing that can see the difference.

The direction that matters is MISSED -- pyshacl reported a violation and we did
not. That is the silent-failure class. EXTRA is usually this compiler being
stricter, or reporting one alert where pyshacl reports several.

Known, deliberate divergences live in expected-divergences.txt. Anything not
listed there is a finding.
"""

import glob
import os
import sys

import pyshacl
from rdflib import BNode, Graph, URIRef
from rdflib.namespace import RDF, SH

NGSILD = 'https://uri.etsi.org/ngsi-ld/'
# How the attribute's value is reached. pyshacl reports the value path itself;
# we name the attribute that carries it, so these resolve to the parent.
VALUE_PATHS = {NGSILD + p for p in
               ('hasValue', 'hasValueList', 'hasJSON', 'hasObject')}
# Edges that carry no name of their own: they say how a value is stored, not
# which attribute it belongs to. The climb to the owning attribute steps over
# them, including the rdf:first/rdf:rest cells of a list.
TRANSPARENT_EDGES = VALUE_PATHS | {str(RDF.first), str(RDF.rest)}
OBSERVED_AT = URIRef(NGSILD + 'observedAt')
DATASET_ID = URIRef(NGSILD + 'datasetId')
# min/max are one CountConstraintComponent here, two components in SHACL.
COMPONENT_ALIASES = {'MinCountConstraintComponent': 'CountConstraintComponent',
                     'MaxCountConstraintComponent': 'CountConstraintComponent'}


def local(iri):
    return str(iri).rsplit('/', 1)[-1].rsplit('#', 1)[-1]


def owner_and_edge(node, graph, seen=None):
    """The entity owning this node, and the predicate that attaches it.

    The edge wanted is the one closest to the node, not the one closest to the
    entity. We name an alert after the attribute the constraint is on -- for a
    sub-attribute that is `assembly[0] ==> bolt[0]`, and the segment that
    identifies the constraint is `bolt`. Returning the outermost edge instead
    named every nested constraint after its grandparent.

    Edges that only say how a value is stored are stepped over, so a constraint
    on a list element resolves to the attribute holding the list rather than to
    ngsi-ld:hasValueList or to an rdf:rest cell.
    """
    seen = seen or set()
    if isinstance(node, URIRef):
        return str(node), None
    if node in seen:
        return None, None
    seen.add(node)
    for subject, predicate in graph.subject_predicates(node):
        owner, higher = owner_and_edge(subject, graph, seen)
        if owner:
            if str(predicate) in TRANSPARENT_EDGES:
                return owner, higher
            return owner, predicate
    return None, None


def drop_subtree(graph, node, seen=None):
    """Remove a node and everything reachable from it."""
    seen = seen or set()
    if node in seen:
        return
    seen.add(node)
    for predicate, obj in list(graph.predicate_objects(node)):
        graph.remove((node, predicate, obj))
        if isinstance(obj, BNode):
            drop_subtree(graph, obj, seen)


def collapse_updates(data):
    """Keep only the most recent instance of each attribute.

    An NGSI-LD attribute is identified by (entity, name, datasetId), so four
    hasStrength entries differing only in observedAt are four updates of one
    attribute and the attributes table holds one row -- the last. In RDF they
    are four concurrent values, and sh:maxCount 1 reports a violation that
    says nothing about this compiler: it would fire on any entity ever updated
    twice.

    Rather than accept those divergences blindly, hand pyshacl the attribute
    the broker would have kept. Counts then mean the same thing on both sides
    and a real count bug still shows up.

    datasetId is what decides this, and it is in the key. Two instances with
    different datasetIds are two attributes that happen to share a name, not
    one attribute updated twice, and collapsing them would erase a value the
    broker keeps -- hiding any count violation over them. test1/model14 pins
    that: two datasetIds, each updated twice, so the collapse must take 4
    instances to 2 and not to 1. Drop datasetId from the key and it fails.

    Only instances carrying observedAt are collapsed. Repeated values without
    one are not a sequence of updates and are left alone.
    """
    groups = {}
    for subject, predicate, obj in data:
        if not isinstance(obj, BNode):
            continue
        observed = data.value(obj, OBSERVED_AT)
        if observed is None:
            continue
        key = (subject, predicate, data.value(obj, DATASET_ID))
        groups.setdefault(key, []).append((str(observed), obj))
    dropped = 0
    for (subject, predicate, _), instances in groups.items():
        if len(instances) < 2:
            continue
        instances.sort()
        for _, node in instances[:-1]:
            data.remove((subject, predicate, node))
            drop_subtree(data, node)
            dropped += 1
    return dropped


def pyshacl_findings(shapes, knowledge, model):
    # The knowledge belongs in the DATA graph, not in ont_graph. Passing it as
    # ont_graph leaves it invisible to sh:class, so every `sh:class` over a
    # value typed only by the knowledge -- iff:state_OFF a iff:machineState --
    # reports a violation that is not one. That is also what this compiler
    # does: the rdf table it joins against is the knowledge, so the validator
    # has to see the same world.
    data = Graph()
    data.parse(model, format='json-ld')
    collapsed = collapse_updates(data)
    data.parse(knowledge)
    shape_graph = Graph()
    shape_graph.parse(shapes)
    _, report, _ = pyshacl.validate(data, shacl_graph=shape_graph,
                                    advanced=True, inplace=False,
                                    do_owl_imports=False)
    found = set()
    for result in report.objects(None, SH.result):
        focus = report.value(result, SH.focusNode)
        path = report.value(result, SH.resultPath)
        component = local(report.value(result, SH.sourceConstraintComponent))
        owner, edge = owner_and_edge(focus, data)
        if owner is None:
            continue
        # A value path names how to read the attribute; we report the
        # attribute, so climb to the edge that attaches the focus node. A
        # blank node in sh:resultPath is a path expression rather than a
        # predicate -- the ([sh:zeroOrMorePath rdf:rest] rdf:first) that walks
        # a list -- and has no name of its own, so it resolves the same way.
        indirect = str(path) in VALUE_PATHS or isinstance(path, BNode)
        if path is not None and indirect:
            path = edge
        label = local(path) if path is not None else ''
        if not label:
            # A node-level constraint -- sh:sparql is the one we compile --
            # has no path. We name such an alert after the shape it came
            # from, and pyshacl says which shape that was.
            shape = report.value(result, SH.sourceShape)
            if isinstance(shape, URIRef):
                label = local(shape)
        found.add((owner,
                   COMPONENT_ALIASES.get(component, component),
                   label))
    return found, collapsed


def our_findings(testout):
    """Parse a fixture's recorded alerts into the same shape."""
    found = set()
    for line in open(testout):
        line = line.strip()
        if not line:
            continue
        parts = [f.strip().strip("'") for f in line.split("','")]
        parts = [p.strip("'") for p in parts]
        if len(parts) < 2:
            continue
        resource, event = parts[0], parts[1]
        # 'ok' rows are cleared constraints, not findings. Counting them made
        # every satisfied SPARQL rule look like a divergence.
        if len(parts) > 2 and parts[2] == 'ok':
            continue
        component = event.split('(', 1)[0]
        inner = event[event.find('(') + 1:event.rfind(')')]
        # 'parent[0] ==> child[0]' -- the constraint is about the last segment
        segment = inner.split('==>')[-1].strip()
        if segment.endswith(']'):
            segment = segment[:segment.rfind('[')]
        found.add((resource, component, local(segment)))
    return found


def load_allowlist(path):
    allowed = set()
    if not os.path.exists(path):
        return allowed
    for line in open(path):
        line = line.split('#', 1)[0].strip()
        if line:
            allowed.add(tuple(f.strip() for f in line.split('|')))
    return allowed


def main(root):
    allowlist = load_allowlist(os.path.join(os.path.dirname(__file__),
                                            'expected-divergences.txt'))
    missed_total = extra_total = compared = 0
    misplaced = []
    unrun = []
    collapsed_total = 0
    for testdir in sorted(glob.glob(os.path.join(root, 'kms-constraints', 'test*'))):
        shapes = os.path.join(testdir, 'shacl.ttl')
        knowledge = os.path.join(testdir, 'knowledge.ttl')
        for model in sorted(glob.glob(os.path.join(testdir, 'model*.jsonld'))):
            testout = os.path.join(testdir, 'output',
                                   os.path.basename(model) + '_testout')
            # No recorded alerts means the fixture run did not reach this
            # model -- tests.sh stops at the first diff. Comparing what did
            # run and reporting success would turn a broken suite into a
            # green one, so count it and fail.
            if not os.path.exists(testout):
                unrun.append(f'{os.path.basename(testdir)}/'
                             f'{os.path.basename(model)}')
                continue
            # A <model>_model file supplies the attributes table directly,
            # so the .jsonld beside it is never read and pyshacl would be
            # validating different input than we did. Such a case belongs in
            # sql-cases/, where the table is the declared input and there is
            # no model file to mistake for one. Fail rather than skip: a
            # comparison that quietly drops a model reads as coverage.
            if os.path.exists(model + '_model'):
                misplaced.append(f'{os.path.basename(testdir)}/'
                                 f'{os.path.basename(model)}')
                continue
            compared += 1
            try:
                theirs, collapsed = pyshacl_findings(shapes, knowledge, model)
                collapsed_total += collapsed
            except Exception as exc:                       # noqa: BLE001
                print(f'  !! {testdir}/{os.path.basename(model)}: pyshacl failed: {exc}')
                continue
            ours = our_findings(testout)
            name = f'{os.path.basename(testdir)}/{os.path.basename(model)}'
            for finding in sorted(theirs - ours):
                if ('MISSED', name) + finding in allowlist:
                    continue
                missed_total += 1
                print(f'  MISSED {name}: {finding[0]} {finding[1]}({finding[2]})')
            for finding in sorted(ours - theirs):
                if ('EXTRA', name) + finding in allowlist:
                    continue
                extra_total += 1
                print(f'  EXTRA  {name}: {finding[0]} {finding[1]}({finding[2]})')
    if collapsed_total:
        print(f'--- collapsed {collapsed_total} superseded attribute '
              f'instances: an NGSI-LD attribute is (entity, name, datasetId) '
              f'and keeps its latest value')
    if unrun:
        print(f'  !! {len(unrun)} model(s) had no recorded alerts, so the '
              f'fixture run did not complete: {", ".join(unrun[:5])}'
              f'{" ..." if len(unrun) > 5 else ""}')
    for name in misplaced:
        print(f'  !! {name}: has a {os.path.basename(name)}_model overriding '
              f'the attributes table, so its .jsonld is not the input we '
              f'validated and it cannot be compared. Move it to sql-cases/.')
    print(f'--- compared {compared} models: {missed_total} missed, {extra_total} extra')
    return 1 if missed_total or extra_total or misplaced or unrun \
        else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '.'))
