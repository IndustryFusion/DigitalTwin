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
"""Compare two semanticbridge2owl.py outputs for isomorphism, ignoring the
ontology header (owl:Ontology/owl:imports/owl:versionIRI/owl:versionInfo).

The header is deliberately excluded: OntologyLoader resolves owl:imports
recursively over the network (following base.ttl's own further imports of the
RDF/RDFS vocabulary documents, etc.), so its exact contents can vary with
network conditions or upstream changes -- comparing it would make these e2e
tests flaky for reasons that have nothing to do with Virtual Type generation,
which is what these tests actually exercise."""

import argparse
import sys

from rdflib import Graph
from rdflib.compare import graph_diff, to_isomorphic
from rdflib.namespace import OWL, RDF


def load_without_ontology_header(path):
    g = Graph()
    g.parse(path, format='turtle')
    for ontology in list(g.subjects(RDF.type, OWL.Ontology)):
        for p, o in list(g.predicate_objects(ontology)):
            g.remove((ontology, p, o))
    return g


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('expected')
    parser.add_argument('actual')
    parser.add_argument('-o', '--output', default='vt-diff.ttl',
                        help='Where to write the diff if graphs differ.')
    args = parser.parse_args()

    expected = load_without_ontology_header(args.expected)
    actual = load_without_ontology_header(args.actual)

    iso_expected = to_isomorphic(expected)
    iso_actual = to_isomorphic(actual)
    if iso_expected == iso_actual:
        print('Graphs are isomorphic (identical, ignoring ontology header).')
        return 0

    print(f'Graphs differ (ignoring ontology header). Diff written to {args.output}.')
    in_both, only_expected, only_actual = graph_diff(iso_expected, iso_actual)
    with open(args.output, 'w') as f:
        print('Triples in expected but not in actual:', file=f)
        for triple in only_expected:
            print(' ', triple, file=f)
        print('\nTriples in actual but not in expected:', file=f)
        for triple in only_actual:
            print(' ', triple, file=f)
    return 1


if __name__ == '__main__':
    sys.exit(main())
