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
("types"), how many physically-declared Instance Declarations it introduces
("instance declarations" -- a child with a recognized ModellingRule
[Mandatory/Optional/(Mandatory|Optional)Placeholder]; the raw, un-expanded
nodes Virtual Type generation replaces, one per type: no inheritance or
recursive unrolling), and how many Virtual Types semanticbridge2owl.py's
OwlBuilder generates from them ("virtual") -- i.e. exactly the incremental
contribution of that one companion spec, the same way
`semanticbridge2owl.py <file>.ttl` would process it on its own, with
dependencies (core.ttl for di.ttl, etc.) resolved via each file's own
owl:imports but not recounted.

Two ratios are reported per file: Virtual Types per type declared
(vt_per_type), and Virtual Types per Instance Declaration (vt_per_instance_decl)
-- the latter is the more meaningful growth figure, since it's relative to the
actual un-expanded declarations Virtual Type generation is replacing, not to
the (much smaller, and somewhat arbitrary) count of types that happen to
introduce them.

Usage:
    python3 virtual_type_stats.py [-o stats.csv] [-p chart.pdf]
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
# Fallback only, used solely if a file's own @prefix declarations can't be
# found (see detect_namespaces) -- do not rely on these being current. The
# base ontology URI has already changed once in practice (from .../ontology/
# v0/base/ to .../staging/ontology/v0.3/base.ttl), and rdflib namespace
# lookups fail *silently* on a mismatch (every base:*-predicate query just
# finds zero results, no exception raised), so a stale hardcoded guess here
# previously caused every base:definesType/base:instanceOf/etc. lookup to
# silently find nothing -- not a crash, just near-empty output.
BASENS = Namespace('https://industryfusion.github.io/contexts/ontology/v0/base/')
OPCUANS = Namespace('http://opcfoundation.org/UA/')

_graph_cache = {}
_namespace_cache = {}


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


def detect_namespaces(g):
    """Auto-detect this file's own 'base'/'opcua' @prefix declarations
    instead of trusting a hardcoded guess -- see the BASENS/OPCUANS comment
    above for why a stale guess is dangerous here (silent, not a crash)."""
    prefixes = dict(g.namespaces())
    base = prefixes.get('base')
    opcua = prefixes.get('opcua')
    if base is None or opcua is None:
        raise ValueError("Could not find 'base'/'opcua' @prefix declarations in this file")
    return Namespace(str(base)), Namespace(str(opcua))


def load_fixed_graph(path):
    """Parse + restore_type_of_node_iris exactly once per file, cached, so a
    dependency shared by several companion specs (core.ttl, di.ttl, ...) isn't
    reparsed once per downstream file that imports it. The namespaces used
    for restore_type_of_node_iris (and for any later OwlBuilder call on this
    graph) are this file's own, auto-detected -- see get_namespaces."""
    key = str(path)
    if key not in _graph_cache:
        g = Graph()
        g.parse(path)
        basens, opcuans = detect_namespaces(g)
        utils.restore_type_of_node_iris(g, opcuans, basens)
        _graph_cache[key] = g
        _namespace_cache[key] = (basens, opcuans)
    return _graph_cache[key]


def get_namespaces(path):
    """This file's own auto-detected (basens, opcuans) pair -- call
    load_fixed_graph(path) first to populate the cache."""
    return _namespace_cache[str(path)]


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


def filter_for_presentation(rows, min_types):
    """Drop files with a very low or zero own-type count (pure instance
    examples like pumpexample.ttl declare none at all, and contribute
    nothing readable to a chart or summary table) and sort by Virtual Type
    count descending, for consistent presentation ordering across both the
    chart and the table."""
    filtered = [r for r in rows if r[1] >= min_types]
    filtered.sort(key=lambda r: r[3], reverse=True)
    return filtered


def write_pdf_report(rows, pdf_path, min_types):
    """Render a two-page PDF suitable for dropping straight into a slide
    deck: page 1 is a two-panel bar chart (counts on a log scale, both
    ratios on a linear scale), page 2 is the same data as a plain summary
    table with a TOTAL row. Both pages use the same filtered/sorted file
    list (see filter_for_presentation)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    plotted = filter_for_presentation(rows, min_types)
    names = [r[0].removesuffix('.ttl') for r in plotted]
    types = [r[1] for r in plotted]
    instance_decls = [r[2] for r in plotted]
    virtual = [r[3] for r in plotted]
    vt_per_type = [r[4] for r in plotted]
    vt_per_decl = [r[5] for r in plotted]

    with PdfPages(pdf_path) as pdf:
        x = range(len(plotted))
        width = 0.27

        fig, (ax_counts, ax_ratios) = plt.subplots(2, 1, figsize=(14, 9))

        ax_counts.bar([i - width for i in x], types, width, label='Types declared')
        ax_counts.bar(list(x), instance_decls, width, label='Instance Declarations')
        ax_counts.bar([i + width for i in x], virtual, width, label='Virtual Types')
        ax_counts.set_yscale('log')
        ax_counts.set_ylabel('count (log scale)')
        ax_counts.set_title('Virtual Type growth across the OPC UA companion-spec corpus')
        ax_counts.legend()
        ax_counts.set_xticks(list(x))
        ax_counts.set_xticklabels(names, rotation=45, ha='right')

        ax_ratios.bar([i - width / 2 for i in x], vt_per_type, width, label='Virtual Types per type')
        ax_ratios.bar([i + width / 2 for i in x], vt_per_decl, width,
                      label='Virtual Types per Instance Declaration')
        ax_ratios.set_ylabel('ratio (x)')
        ax_ratios.set_xticks(list(x))
        ax_ratios.set_xticklabels(names, rotation=45, ha='right')
        ax_ratios.legend()

        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        col_labels = ['File', 'Types', 'Instance Decls', 'Virtual Types', 'VT/Type', 'VT/Decl']
        cell_text = [[name, str(t), str(d), str(v), f'{vpt:.1f}x', f'{vpd:.1f}x']
                     for name, t, d, v, vpt, vpd
                     in zip(names, types, instance_decls, virtual, vt_per_type, vt_per_decl)]
        total_types, total_decls, total_vt = sum(types), sum(instance_decls), sum(virtual)
        cell_text.append(['TOTAL', str(total_types), str(total_decls), str(total_vt),
                          f'{(total_vt / total_types if total_types else 0):.1f}x',
                          f'{(total_vt / total_decls if total_decls else 0):.1f}x'])

        fig2, ax2 = plt.subplots(figsize=(11, 0.4 * len(cell_text) + 1.5))
        ax2.axis('off')
        ax2.set_title('Virtual Type growth summary', pad=20)
        table = ax2.table(cellText=cell_text, colLabels=col_labels, loc='center', cellLoc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.5)
        for (row, _col), cell in table.get_celld().items():
            if row == 0 or row == len(cell_text):
                cell.set_text_props(weight='bold')
        fig2.tight_layout()
        pdf.savefig(fig2)
        plt.close(fig2)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-o', '--output', help='Optional CSV file to also write the results to.',
                        default=None)
    parser.add_argument('-p', '--pdf', help='Optional PDF file to render a summary chart+table to '
                                            '(page 1: chart, page 2: table).',
                        default=None)
    parser.add_argument('--min-types', type=int, default=3,
                        help='Minimum own-type count a file needs to appear in the PDF chart/table '
                             '(default: 3) -- the CSV/console output always includes every file.')
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
        basens, opcuans = get_namespaces(path)
        ig = resolve_dependencies(g)
        builder = OwlBuilder(g, basens, opcuans, ig=ig)
        own_classes = builder.all_target_classes()
        instance_decl_count = builder.count_own_instance_declarations()
        out = builder.run(own_classes)
        vt_count = sum(1 for c in out.subjects(RDF.type, OWL.Class)
                       if str(c).split('/')[-1].startswith('VT_'))
        elapsed = time.monotonic() - start
        vt_per_type = vt_count / len(own_classes) if own_classes else 0.0
        vt_per_decl = vt_count / instance_decl_count if instance_decl_count else 0.0
        rows.append((name, len(own_classes), instance_decl_count, vt_count,
                     vt_per_type, vt_per_decl, elapsed))
        print(f'{name:30s} types={len(own_classes):5d}  instance_decls={instance_decl_count:5d}  '
              f'virtual={vt_count:6d}  vt/type={vt_per_type:6.1f}x  vt/decl={vt_per_decl:6.1f}x  '
              f'({elapsed:.1f}s)')

    total_types = sum(r[1] for r in rows)
    total_decls = sum(r[2] for r in rows)
    total_vt = sum(r[3] for r in rows)
    print()
    print(f'{"TOTAL":30s} types={total_types:5d}  instance_decls={total_decls:5d}  '
          f'virtual={total_vt:6d}  '
          f'vt/type={(total_vt / total_types if total_types else 0):6.1f}x  '
          f'vt/decl={(total_vt / total_decls if total_decls else 0):6.1f}x')

    if args.output:
        with open(args.output, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['file', 'types', 'instance_declarations', 'virtual_types',
                             'vt_per_type', 'vt_per_instance_declaration', 'seconds'])
            for name, types, decls, vt, vt_per_type, vt_per_decl, elapsed in rows:
                writer.writerow([name, types, decls, vt, f'{vt_per_type:.2f}',
                                 f'{vt_per_decl:.2f}', f'{elapsed:.1f}'])
        print(f'\nWrote {args.output}')

    if args.pdf:
        write_pdf_report(rows, args.pdf, args.min_types)
        print(f'Wrote {args.pdf}')


if __name__ == '__main__':
    sys.exit(main())
