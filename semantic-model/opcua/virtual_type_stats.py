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
"""Statistics on Virtual Type growth across the OPC UA companion-spec chain
built by translate_default_nodesets.make.

For every *.ttl file that Makefile is set up to produce (TARGET_NAMES / the
matching <NAME>_ONTOLOGY variables -- parsed directly from the Makefile so
this never drifts out of sync with it) and that actually exists on disk, this
reports how many of its own ObjectType/VariableType classes it declares
("original") and how many Virtual Types semanticbridge2owl.py's OwlBuilder
generates for them ("virtual") -- i.e. exactly the incremental contribution of
that one companion spec, the same way `semanticbridge2owl.py <file>.ttl` would
process it on its own, with dependencies (core.ttl for di.ttl, etc.) resolved
via each file's own owl:imports but not recounted.

Usage:
    python3 virtual_type_stats.py [-o stats.csv]
"""

import argparse
import csv
import re
import sys
import time
from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import OWL, RDF

import lib.utils as utils
from lib.owlbuilder import OwlBuilder

REPO_ROOT = Path(__file__).parent
MAKEFILE = REPO_ROOT / 'translate_default_nodesets.make'
BASENS = Namespace('https://industryfusion.github.io/contexts/ontology/v0/base/')
OPCUANS = Namespace('http://opcfoundation.org/UA/')

_graph_cache = {}


def parse_target_files(makefile_path):
    """Extract the ordered list of *.ttl output filenames this Makefile
    produces, straight from its own TARGET_NAMES and <NAME>_ONTOLOGY
    variables, so this script can't drift out of sync with the Makefile."""
    text = makefile_path.read_text()
    names_match = re.search(r'^TARGET_NAMES\s*=\s*(.+)$', text, re.MULTILINE)
    if names_match is None:
        raise ValueError(f'Could not find TARGET_NAMES in {makefile_path}')
    names = names_match.group(1).split()
    files = []
    for name in names:
        ontology_match = re.search(rf'^{re.escape(name)}_ONTOLOGY\s*=\s*(\S+)$', text, re.MULTILINE)
        if ontology_match:
            files.append(ontology_match.group(1))
    return files


def load_fixed_graph(path):
    """Parse + restore_type_of_node_iris exactly once per file, cached, so a
    dependency shared by several companion specs (core.ttl, di.ttl, ...) isn't
    reparsed once per downstream file that imports it."""
    key = str(path)
    if key not in _graph_cache:
        g = Graph()
        g.parse(path)
        utils.restore_type_of_node_iris(g, OPCUANS, BASENS)
        _graph_cache[key] = g
    return _graph_cache[key]


def resolve_dependencies(g):
    """Follow this file's own owl:imports recursively, merging every file://
    dependency into one `ig` graph via the load_fixed_graph cache. Non-file
    imports (e.g. the generic base.ttl) are skipped -- they contribute no OPC
    UA types to virtualize."""
    ig = Graph()
    seen = set()

    def visit(local_path):
        nonlocal ig
        if local_path in seen:
            return
        seen.add(local_path)
        dep_graph = load_fixed_graph(local_path)
        ig += dep_graph
        for imported in dep_graph.objects(None, OWL.imports):
            if str(imported).startswith('file://'):
                visit(str(imported)[len('file://'):])

    for imported in g.objects(None, OWL.imports):
        if str(imported).startswith('file://'):
            visit(str(imported)[len('file://'):])
    return ig


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-o', '--output', help='Optional CSV file to also write the results to.',
                        default=None)
    args = parser.parse_args()

    target_files = parse_target_files(MAKEFILE)
    rows = []
    for name in target_files:
        path = REPO_ROOT / name
        if not path.exists():
            print(f'{name:30s} -- not present on disk, skipping')
            continue
        start = time.monotonic()
        g = load_fixed_graph(path)
        ig = resolve_dependencies(g)
        builder = OwlBuilder(g, BASENS, OPCUANS, ig=ig)
        own_classes = builder.all_target_classes()
        out = builder.run(own_classes)
        vt_count = sum(1 for c in out.subjects(RDF.type, OWL.Class)
                       if str(c).split('/')[-1].startswith('VT_'))
        elapsed = time.monotonic() - start
        ratio = vt_count / len(own_classes) if own_classes else 0.0
        rows.append((name, len(own_classes), vt_count, ratio, elapsed))
        print(f'{name:30s} original={len(own_classes):5d}  virtual={vt_count:6d}  '
              f'ratio={ratio:6.1f}x  ({elapsed:.1f}s)')

    total_orig = sum(r[1] for r in rows)
    total_vt = sum(r[2] for r in rows)
    print()
    print(f'{"TOTAL":30s} original={total_orig:5d}  virtual={total_vt:6d}  '
          f'ratio={(total_vt / total_orig if total_orig else 0):6.1f}x')

    if args.output:
        with open(args.output, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['file', 'original_types', 'virtual_types', 'ratio', 'seconds'])
            for name, orig, vt, ratio, elapsed in rows:
                writer.writerow([name, orig, vt, f'{ratio:.2f}', f'{elapsed:.1f}'])
        print(f'\nWrote {args.output}')


if __name__ == '__main__':
    sys.exit(main())
