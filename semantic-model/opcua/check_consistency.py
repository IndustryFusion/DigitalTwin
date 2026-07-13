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
"""Run the HermiT DL reasoner against every pure-OWL ontology this repo's
semanticbridge2owl.py/OwlBuilder produces, to check for genuinely
contradictory OPC UA type constructions -- the actual point of the whole
Part 14 transformation (see semantic_bridge_to_owl.md section 1).

For every *.ttl file translate_default_nodesets.make is set up to produce
(reusing virtual_type_stats.py's own Makefile parsing, so this never drifts
out of sync with it) and that exists on disk, or for an explicit list of ttl
files given on the command line, this:

  1. builds that file's own pure-OWL output via OwlBuilder, exactly as
     semanticbridge2owl.py would, but in-memory (no temp .owl.ttl file needed);
  2. merges in the full, already-computed pure-OWL output of every local
     (file://) dependency it transitively imports -- recursively, cached so a
     dependency shared by several companion specs (core.ttl, di.ttl, ...) is
     classified only once for its own sake and reused thereafter -- giving
     HermiT the same complete picture Protege would see after resolving
     owl:imports, entirely offline;
  3. serializes the merged, header-free result to a temp N-Triples file (NOT
     Turtle: the OWL-API 3.4.3 bundled inside owlready2's HermiT.jar has a
     Turtle parser bug with percent-encoded IRI segments, e.g. the very real
     opcua:has%3CServiceName%3E from an OptionalPlaceholder BrowseName like
     "<ServiceName>" -- N-Triples has no prefixed-name syntax to trip over,
     and is exactly the format owlready2 itself feeds to HermiT);
  4. runs HermiT's classify action (-c) against it and parses the output for
     any class HermiT infers equivalent to owl:Nothing (i.e. unsatisfiable),
     or an outright "Inconsistent ontology" verdict.

Requires `pip install owlready2` (used solely to locate the bundled
HermiT.jar; the actual reasoning is a plain `java -cp ... HermiT ...`
subprocess, not owlready2's own ontology/world API) and a `java` on PATH.

Usage:
    python3 check_consistency.py [-o report.csv] [-q] [name.ttl ...]
"""

import argparse
import csv
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from rdflib import Graph
from rdflib.namespace import OWL

from lib.owlbuilder import OwlBuilder
from virtual_type_stats import (
    MAKEFILE, REPO_ROOT,
    get_namespaces, load_fixed_graph, parse_target_files, resolve_dependencies,
)

try:
    import owlready2
except ImportError:
    sys.exit('check_consistency.py requires owlready2 (used only to locate the bundled HermiT.jar): '
             'pip install owlready2')

_HERMIT_DIR = os.path.join(os.path.dirname(owlready2.__file__), 'hermit')
_HERMIT_CLASSPATH = os.pathsep.join([_HERMIT_DIR, os.path.join(_HERMIT_DIR, 'HermiT.jar')])
_JAVA_MEMORY_MB = 2000

_EQUIVALENT_CLASSES_RE = re.compile(r'^EquivalentClasses\(\s*(.+?)\s*\)$', re.MULTILINE)
_IRI_RE = re.compile(r'<([^>]+)>')
_OWL_NOTHING = 'http://www.w3.org/2002/07/owl#Nothing'

_owl_output_cache = {}


def build_full_owl_output(path):
    """This file's own pure-OWL output, merged with the already-computed full
    output of every local dependency it transitively imports -- recursively,
    cached by path so a shared dependency is only ever built once. This is
    the same picture Protege would see after resolving owl:imports, without
    any of it actually touching the network."""
    key = str(path)
    if key in _owl_output_cache:
        return _owl_output_cache[key]
    g = load_fixed_graph(path)
    basens, opcuans = get_namespaces(path)
    ig = resolve_dependencies(g)
    builder = OwlBuilder(g, basens, opcuans, ig=ig)
    own_out = builder.run(builder.all_target_classes())
    full_out = Graph()
    full_out += own_out
    for imported in g.objects(None, OWL.imports):
        if str(imported).startswith('file://'):
            full_out += build_full_owl_output(Path(str(imported)[len('file://'):]))
    _owl_output_cache[key] = full_out
    return full_out


def run_hermit(graph):
    """Serialize graph to N-Triples and run HermiT's classify action against
    it. Returns (status, unsatisfiable_classes, raw_output), where status is
    one of 'consistent', 'unsatisfiable', 'inconsistent', 'error'."""
    with tempfile.NamedTemporaryFile(suffix='.nt', delete=False) as tmp:
        tmp_path = tmp.name
    try:
        graph.serialize(destination=tmp_path, format='nt', encoding='utf-8')
        cmd = ['java', f'-Xmx{_JAVA_MEMORY_MB}M', '-cp', _HERMIT_CLASSPATH,
               'org.semanticweb.HermiT.cli.CommandLine', '-c', f'file://{tmp_path}']
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout + result.stderr

        if 'Inconsistent ontology' in output:
            return 'inconsistent', [], output
        if result.returncode != 0:
            return 'error', [], output

        unsatisfiable = set()
        for match in _EQUIVALENT_CLASSES_RE.finditer(output):
            members = _IRI_RE.findall(match.group(1))
            if _OWL_NOTHING in members:
                unsatisfiable.update(m for m in members if m != _OWL_NOTHING)
        if unsatisfiable:
            return 'unsatisfiable', sorted(unsatisfiable), output
        return 'consistent', [], output
    finally:
        os.unlink(tmp_path)


def check_file(name, path):
    start = time.monotonic()
    full_out = build_full_owl_output(path)
    status, unsatisfiable, output = run_hermit(full_out)
    elapsed = time.monotonic() - start
    return status, unsatisfiable, elapsed, len(full_out)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='*',
                        help='Explicit semantic bridge ttl file(s) to check instead of the whole '
                             'translate_default_nodesets.make corpus.')
    parser.add_argument('-o', '--output', help='Optional CSV file to also write the results to.',
                        default=None)
    parser.add_argument('-q', '--quiet', action='store_true', default=False,
                        help='Only print files with issues and the final summary.')
    args = parser.parse_args()

    if args.files:
        targets = [(Path(f).name, Path(f).resolve()) for f in args.files]
    else:
        targets = [(name, REPO_ROOT / name) for name in parse_target_files(MAKEFILE)]

    rows = []
    for name, path in targets:
        if not path.exists():
            if not args.quiet:
                print(f'{name:30s} -- not present on disk, skipping')
            continue
        status, unsatisfiable, elapsed, size = check_file(name, path)
        rows.append((name, status, unsatisfiable, elapsed, size))
        if status == 'consistent':
            if not args.quiet:
                print(f'{name:30s} OK  consistent  ({size} triples, {elapsed:.1f}s)')
        elif status == 'unsatisfiable':
            print(f'{name:30s} FAIL  {len(unsatisfiable)} unsatisfiable class(es)  '
                  f'({size} triples, {elapsed:.1f}s)')
            for cls in unsatisfiable:
                print(f'    {cls}')
        elif status == 'inconsistent':
            print(f'{name:30s} FAIL  globally inconsistent ontology  ({size} triples, {elapsed:.1f}s)')
        else:
            print(f'{name:30s} ERROR  HermiT failed to run -- see output above')

    print()
    ok = sum(1 for r in rows if r[1] == 'consistent')
    bad = [r for r in rows if r[1] != 'consistent']
    print(f'{ok}/{len(rows)} ontologies consistent.')
    if bad:
        print('Ontologies with issues: ' + ', '.join(r[0] for r in bad))

    if args.output:
        with open(args.output, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['file', 'status', 'unsatisfiable_classes', 'seconds', 'triples'])
            for name, status, unsatisfiable, elapsed, size in rows:
                writer.writerow([name, status, '|'.join(unsatisfiable), f'{elapsed:.1f}', size])
        print(f'\nWrote {args.output}')

    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
