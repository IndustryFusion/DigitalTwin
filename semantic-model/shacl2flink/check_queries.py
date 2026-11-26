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

import argparse
import json
import sys

import rdflib

from lib.query_check import check


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='Say which SPARQL expressions of the shapes \
cannot be compiled to Flink SQL, and why. Exits 1 if there is one.')
    parser.add_argument('shaclfile', nargs='+', help='Path to the SHACL file(s)')
    parser.add_argument('--json', action='store_true', help='machine-readable output')
    parser.add_argument('--draft', action='store_true',
                        help='check the one expression given as JSON (target, query, kind) on standard input')
    return parser.parse_args(args)


def main(shaclfiles, as_json=False, draft=None):
    graph = rdflib.Graph()
    for path in shaclfiles:
        graph.parse(path)
    problems = check(graph, shaclfiles, draft)
    if as_json:
        print(json.dumps([problem.as_dict() for problem in problems]))
    elif problems:
        print(f'ERROR: {len(problems)} SPARQL expression(s) cannot be compiled to Flink SQL.')
        for number, problem in enumerate(problems, 1):
            print(f'\n{number}) {problem}')
    else:
        print('Every SPARQL expression can be compiled.')
    return 1 if problems else 0


if __name__ == '__main__':
    args = parse_args()
    sys.exit(main(args.shaclfile, args.json, json.load(sys.stdin) if args.draft else None))
