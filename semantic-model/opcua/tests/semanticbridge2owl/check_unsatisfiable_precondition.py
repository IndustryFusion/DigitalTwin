#!/usr/bin/env python3
#
# Copyright (c) 2024 Intel Corporation
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
"""Scan a semanticbridge2owl.py output for classes that transitively reach two
classes asserted pairwise disjoint via owl:AllDisjointClasses -- exactly what
a DL reasoner (HermiT/Pellet) would use to derive that the class is
unsatisfiable. No actual reasoner is available in this environment, so this
checks the structural precondition directly instead.

Used both positively (test_vt_contradiction.NodeSet2.owl.ttl *must* have one)
and negatively (the other 4 scenarios must *not* have one -- a sanity check
that Virtual Type generation doesn't produce false-positive contradictions for
legitimate inheritance/override cases).

Usage: check_unsatisfiable_precondition.py --expect-contradiction|--expect-none <ttl-file>
"""
import argparse
import sys

from rdflib import Graph, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS


def transitive_superclasses(g, cls):
    seen = set()
    stack = [cls]
    while stack:
        current = stack.pop()
        for sup in g.objects(current, RDFS.subClassOf):
            if isinstance(sup, URIRef) and sup not in seen:
                seen.add(sup)
                stack.append(sup)
    return seen


def disjoint_sets(g):
    sets = []
    for node in g.subjects(RDF.type, OWL.AllDisjointClasses):
        members_list = g.value(node, OWL.members)
        if members_list is not None:
            sets.append(set(Collection(g, members_list)))
    return sets


def find_contradictions(g):
    disjoint = disjoint_sets(g)
    found = []
    for cls in g.subjects(RDF.type, OWL.Class):
        supers = transitive_superclasses(g, cls) | {cls}
        for pair in disjoint:
            hit = supers & pair
            if len(hit) >= 2:
                found.append((cls, hit))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--expect-contradiction', action='store_true')
    group.add_argument('--expect-none', action='store_true')
    parser.add_argument('ttl_file')
    args = parser.parse_args()

    g = Graph()
    g.parse(args.ttl_file, format='turtle')
    found = find_contradictions(g)

    if args.expect_contradiction:
        if not found:
            print(f'FAIL: expected an unsatisfiable class in {args.ttl_file}, found none.')
            return 1
        for cls, hit in found:
            print(f'OK: {cls} transitively reaches disjoint classes {sorted(hit, key=str)} '
                  '-- a DL reasoner would flag it unsatisfiable.')
        return 0

    if found:
        for cls, hit in found:
            print(f'FAIL: {cls} unexpectedly reaches disjoint classes {sorted(hit, key=str)} '
                  f'in {args.ttl_file} -- false-positive contradiction.')
        return 1
    print(f'OK: no false-positive contradictions in {args.ttl_file}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
