#!/usr/bin/env python3
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
"""Compose the static export (nodeset2owl.py without --serverUri) and the dynamic exports of any number of
servers (nodeset2owl.py --serverUri --dynamic-only) of a nodeset into one ontology, e.g.

    python3 compose_owl.py di.owl.ttl di.owl.dynamic.urn_example_opcua-server.ttl \\
        -m core.owl.ttl=core.owl.all.ttl -o di.owl.all.ttl
"""

import argparse
import sys
from rdflib import Graph
from lib.composition import compose


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('static', help='Static export (*.owl.ttl).')
    parser.add_argument('dynamic', nargs='*', help='Dynamic exports of the servers (*.owl.dynamic.<server>.ttl).')
    parser.add_argument('-m', '--import-map', nargs='*', default=[], metavar='STATIC=COMPOSED',
                        help='Replace the owl:imports of a file (matched by its file name) of the static export, '
                             'e.g. the static exports of the dependencies by their composed files.')
    parser.add_argument('-o', '--output', required=True, help='Resulting composed file.')
    return parser.parse_args(args)


if __name__ == '__main__':
    args = parse_args()
    import_map = dict(entry.split('=', 1) for entry in args.import_map)
    composed = compose(Graph().parse(args.static), [Graph().parse(d) for d in args.dynamic], import_map)
    composed.serialize(destination=args.output)
    print(f'Composed {args.static} and {len(args.dynamic)} dynamic export(s) into {args.output} '
          f'({len(composed)} triples).')
