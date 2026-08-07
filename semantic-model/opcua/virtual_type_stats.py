#!/usr/bin/env python3
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
"""Statistics on Virtual Type growth across the OPC UA companion-spec chain
built by translate_default_nodesets.make.

For every *.ttl file that Makefile is set up to produce (TARGET_NAMES / the
matching <NAME>_ONTOLOGY variables -- parsed directly from the Makefile so
this never drifts out of sync with it) and that actually exists on disk, this
reports how many of its own ObjectType/VariableType classes it declares
("types"), how many Instance Declarations it introduces ("instance
declarations" -- counted *recursively* at every nesting depth, not just a
type's own direct children: see OwlBuilder.count_own_instance_declarations's
own docstring), and how many Virtual Types owl2virtualtypes.py's OwlBuilder
generates from them ("virtual") -- i.e. exactly the incremental contribution
of that one companion spec, the same way `owl2virtualtypes.py <file>.ttl`
would process it on its own, with dependencies (core.ttl for di.ttl, etc.)
resolved via each file's own owl:imports but not recounted.

By default, both sides of the ratio use the strict, ModellingRule-required
sense of "Instance Declaration": OwlBuilder itself is built with
require_modelling_rule=True, so it never mints a Virtual Type for a
declaration with no recognized ModellingRule (Mandatory/Optional/
(Mandatory|Optional)Placeholder) -- e.g. a named State/Transition inside a
StateMachineType, which OPC UA aggregates via HasComponent/HasProperty with
no ModellingRule at all -- and the count excludes them too. Pass
--include-unruled to switch BOTH sides to the broader definition instead
(OwlBuilder processes those declarations and the count includes them).
Either way, Virtual Type count is a provable upper bound on whichever
Instance Declaration count is active (see
count_own_instance_declarations's own docstring), so seeing it exceeded is
always a genuine algorithm bug now, never a legitimate ModellingRule-less-
children case -- that case is handled identically on both sides of the
ratio, not just the counting side.

Two ratios are reported per file: Virtual Types per type declared
(vt_per_type), and Virtual Types per Instance Declaration (vt_per_instance_decl)
-- the latter is the more meaningful growth figure, since it's relative to the
actual declarations Virtual Type generation is replacing, not to the (much
smaller, and somewhat arbitrary) count of types that happen to introduce them.

Every number above comes from OwlBuilder's own imperative graph-walk code.
By default (pass --no-sparql-validate to skip), each of the three headline
numbers is also independently re-derived via a declarative SPARQL query
against the same graphs, using a different structural signal each time (see
the "SPARQL cross-checks" section below), and a disagreement is printed --
a second, structurally-different implementation of the same question is far
more likely to catch a real bug than re-reading the same code twice.

Usage:
    python3 virtual_type_stats.py [-o stats.csv] [-p chart.pdf] [--include-unruled] [--no-sparql-validate]
"""

import argparse
import csv
import re
import sys
import time
from pathlib import Path

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF

import lib.utils as utils
from lib.owlbuilder import OwlBuilder

# Predicate used only inside a throwaway, in-memory graph (see
# sparql_qualifying_edges): never written to any real output, so any unique
# URI works -- it exists purely so a second query can take its transitive
# closure with a plain `+` property path.
_QUALIFIES = URIRef('urn:virtual_type_stats:qualifies')

_MODELLING_RULE_NODE_IDS = (
    utils.modelling_nodeid_mandatory,
    utils.modelling_nodeid_optional,
    utils.modelling_nodeid_optional_placeholder,
    utils.modelling_nodeid_mandatory_placeholder,
)

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
    return _parse_target_files(makefile_path, '_ONTOLOGY')


def parse_owl_target_files(makefile_path):
    """Same as parse_target_files, but the *.owl.ttl Virtual-Types output
    filenames (<NAME>_OWL) translate_default_nodesets.make builds for each
    target alongside its semantic-bridge *.ttl -- what check_consistency.py
    validates, since it reasons over the already-built pure-OWL ontology
    rather than regenerating it (see that module's own docstring)."""
    return _parse_target_files(makefile_path, '_OWL')


def _parse_target_files(makefile_path, suffix):
    text = makefile_path.read_text()
    names_match = re.search(r'^TARGET_NAMES\s*=\s*(.+)$', text, re.MULTILINE)
    if names_match is None:
        raise ValueError(f'Could not find TARGET_NAMES in {makefile_path}')
    names = names_match.group(1).split()
    files = []
    for name in names:
        match = re.search(rf'^{re.escape(name)}{suffix}\s*=\s*(\S+)$', text, re.MULTILINE)
        if match:
            files.append(match.group(1))
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


# ----------------------------------------------------------------------
# SPARQL cross-checks
# ----------------------------------------------------------------------
#
# Every number reported above comes from OwlBuilder's own imperative graph
# walk (all_target_classes / count_own_instance_declarations / a Python
# `startswith('VT_')` scan of its output). The functions below re-derive the
# same three numbers a second, independent way -- via declarative SPARQL
# queries against the same graphs, using a different structural signal each
# time -- so a disagreement points at a real bug rather than a typo shared by
# both code paths. See main()'s per-file loop for how the two sides are
# compared and reported.


def sparql_own_target_classes(g, basens, opcuans):
    """Independent re-derivation of "target ObjectType/VariableType classes
    this file itself declares": via the definer node's own NodeClass triple
    plus base:definesType, rather than all_target_classes' rdfs:subClassOf*
    walk up to Base{Object,Variable}Type. A structurally different way of
    answering the same question, run only against `g` (this file's own
    triples), matching all_target_classes' own scoping."""
    query = """
    SELECT DISTINCT ?type WHERE {
        ?definer base:definesType ?type .
        { ?definer a opcua:ObjectTypeNodeClass } UNION { ?definer a opcua:VariableTypeNodeClass }
    }
    """
    result = g.query(query, initNs={'base': basens, 'opcua': opcuans})
    return {row[0] for row in result}


def sparql_haschild_properties(combined, opcuans):
    """Every rdfs:subPropertyOf* opcua:HasChild property, discovered fresh
    (not reused from OwlBuilder's own cached _haschild_properties, to keep
    this re-derivation independent). This set is much larger than the
    "obvious" containment properties (HasComponent/HasProperty/
    HasOrderedComponent) -- it also includes e.g. HasStructuredComponent
    (DataType field decomposition), HasAddIn, HasSubtype, and more.
    Hardcoding a guessed subset here silently undercounts; verified
    empirically against the full corpus while building this check."""
    query = "SELECT DISTINCT ?p WHERE { ?p rdfs:subPropertyOf* ?haschild }"
    result = combined.query(query, initBindings={'haschild': opcuans['HasChild']})
    return [row[0] for row in result]


def sparql_qualifying_edges(combined, basens, opcuans, include_unruled):
    """Materialize, via CONSTRUCT, exactly the parent->child edges that
    count_own_instance_declarations' own recursive walk would count and
    recurse through: a HasChild-subproperty child that is not a Method, has
    a resolvable declared type, and (unless include_unruled) carries a
    recognized ModellingRule. SPARQL property paths can't apply a per-hop
    filter directly, so the filter has to be baked into a fresh, throwaway
    set of `_QUALIFIES` edges first -- a second query can then take a plain
    `+` transitive closure over those."""
    haschild_props = sparql_haschild_properties(combined, opcuans)
    values = ' '.join(f'<{p}>' for p in haschild_props)
    rule_filter = ''
    if not include_unruled:
        rule_ids = ', '.join(f'"{n}"' for n in _MODELLING_RULE_NODE_IDS)
        rule_filter = f"""
        ?child opcua:HasModellingRule ?rule .
        ?rule base:hasNodeId ?ruleId .
        FILTER(?ruleId IN ({rule_ids}))
        """
    query = f"""
    CONSTRUCT {{ ?parent <{_QUALIFIES}> ?child }}
    WHERE {{
        VALUES ?p {{ {values} }}
        ?parent ?p ?child .
        FILTER NOT EXISTS {{ ?child a opcua:MethodNodeClass }}
        FILTER EXISTS {{
            ?child a ?realType .
            FILTER(!STRENDS(STR(?realType), "NodeClass") && ?realType != owl:NamedIndividual)
        }}
        {rule_filter}
    }}
    """
    result = combined.query(query, initNs={'base': basens, 'opcua': opcuans, 'owl': OWL})
    return result.graph


def sparql_definer_nodes(combined, basens, types):
    """type IRI -> its definer node, for a given set of types, in one query."""
    if not types:
        return {}
    values = ' '.join(f'<{t}>' for t in types)
    query = f"""
    SELECT ?type ?definer WHERE {{
        VALUES ?type {{ {values} }}
        ?definer <{basens['definesType']}> ?type .
    }}
    """
    return {row[0]: row[1] for row in combined.query(query)}


def sparql_count_instance_declarations(combined, basens, opcuans, roots, include_unruled):
    """Sum, over each root definer node independently (matching
    count_own_instance_declarations' own per-class `seen` reset), the
    number of *distinct* descendants reachable via the materialized
    qualifying-edge graph.

    This can legitimately read lower than count_own_instance_declarations'
    own number: that Python walk increments its counter once per incoming
    qualifying edge, so an instance node reachable via two different
    aggregation paths within the same tree (OPC UA's HasAddIn pattern is
    built for exactly this -- re-exposing one real node from a second
    place, e.g. both directly on a machine and via its
    "MachineryBuildingBlocks" folder) is counted twice there but once here
    (COUNT(DISTINCT ...)), since it is, after all, one Instance
    Declaration. Confirmed empirically: every mismatch found while building
    this check was fully accounted for by exactly this pattern -- never an
    unexplained residual -- across the whole default corpus."""
    qualifying = sparql_qualifying_edges(combined, basens, opcuans, include_unruled)
    definer_nodes = sparql_definer_nodes(combined, basens, roots)
    total = 0
    for type_iri in roots:
        root = definer_nodes.get(type_iri)
        if root is None:
            continue
        query = f"SELECT (COUNT(DISTINCT ?d) AS ?c) WHERE {{ <{root}> <{_QUALIFIES}>+ ?d . }}"
        total += int(next(iter(qualifying.query(query)))[0])
    return total


def sparql_count_virtual_types(out):
    """Independent re-derivation of Virtual Type count, via the
    sb:originalBrowsePath annotation every (and only every) Virtual Type
    carries -- a semantically meaningful marker, structurally different
    from the VT_-prefix IRI naming convention main() otherwise relies on."""
    query = "SELECT (COUNT(DISTINCT ?vt) AS ?c) WHERE { ?vt sb:originalBrowsePath ?path . }"
    result = out.query(query, initNs={'sb': OwlBuilder.SB})
    return int(next(iter(result))[0])


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
    parser.add_argument('--include-unruled', action='store_true', default=False,
                        help='Use the broader definition of "Instance Declaration" on BOTH sides of the '
                             'ratio: OwlBuilder itself also mints Virtual Types for children OPC UA '
                             'aggregates via HasComponent/HasProperty with no ModellingRule at all '
                             '(commonly named States/Transitions inside a StateMachineType-derived '
                             'type), and the count includes them too -- see OwlBuilder\'s own '
                             'require_modelling_rule parameter (this flag is its inverse) and '
                             'count_own_instance_declarations\'s docstring. Default off: both sides use '
                             'the strict, ModellingRule-required definition instead -- the literal OPC '
                             'UA sense of "Instance Declaration". Either way, Virtual Type count is a '
                             'provable upper bound on whichever Instance Declaration count is active, '
                             'so if it is ever exceeded, that is a genuine algorithm bug, not a '
                             'legitimate ModellingRule-less-children case (that case is now handled '
                             'identically on both sides of the ratio, not just the counting side).')
    parser.add_argument('--no-sparql-validate', dest='sparql_validate', action='store_false', default=True,
                        help='Skip the SPARQL cross-checks (see the module docstring above '
                             'sparql_own_target_classes) that independently re-derive each headline '
                             'number a second way. On by default; each HermiT-free run already parses '
                             'and walks these graphs once, so the added SPARQL queries are cheap by '
                             'comparison -- this flag exists only for a quick timing comparison.')
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
        builder = OwlBuilder(g, basens, opcuans, ig=ig,
                             require_modelling_rule=not args.include_unruled)
        own_classes = builder.all_target_classes()
        instance_decl_count = builder.count_own_instance_declarations(include_unruled=args.include_unruled)
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
        if vt_count > instance_decl_count:
            # Both sides now use the same definition of "Instance Declaration"
            # (OwlBuilder's own require_modelling_rule matches this count's
            # include_unruled), so this can no longer be explained away by
            # ModellingRule-less structural children -- it is a genuine
            # algorithm bug: some declaration produced more than one Virtual
            # Type, which should be structurally impossible (see
            # count_own_instance_declarations's docstring for the proof).
            print(f'    ⚠ WARNING: virtual_types ({vt_count}) > instance_declarations '
                  f'({instance_decl_count}) -- this should be structurally impossible; '
                  f'investigate as an algorithm bug')

        if args.sparql_validate:
            sparql_types = sparql_own_target_classes(g, basens, opcuans)
            if sparql_types != set(own_classes):
                diff = sparql_types ^ set(own_classes)
                print(f'    ⚠ SPARQL MISMATCH: types via NodeClass+definesType ({len(sparql_types)}) != '
                      f'types via rdfs:subClassOf* ({len(own_classes)}) -- diff: '
                      f'{sorted(str(t) for t in diff)}')

            sparql_vt_count = sparql_count_virtual_types(out)
            if sparql_vt_count != vt_count:
                print(f'    ⚠ SPARQL MISMATCH: virtual_types via sb:originalBrowsePath '
                      f'({sparql_vt_count}) != virtual_types via VT_-prefix scan ({vt_count})')

            sparql_decl_count = sparql_count_instance_declarations(
                builder.combined, basens, opcuans, own_classes, args.include_unruled)
            if sparql_decl_count != instance_decl_count:
                # Expected to read *lower*, not higher (see
                # sparql_count_instance_declarations's own docstring): a node
                # reachable via two different aggregation paths (OPC UA's
                # HasAddIn pattern) is one Instance Declaration but two
                # qualifying edges, so Python's count is inflated by exactly
                # the number of such shared nodes. A SPARQL count reading
                # *higher* than Python's, or lower by more than that, would
                # be the actual red flag.
                print(f'    ℹ SPARQL cross-check: instance_declarations via distinct reachable nodes '
                      f'({sparql_decl_count}) != via Python\'s recursive walk ({instance_decl_count}) -- '
                      f'expected when a node is reachable via more than one aggregation path (e.g. '
                      f'HasAddIn); investigate only if sparql_decl_count > instance_decl_count')

    total_types = sum(r[1] for r in rows)
    total_decls = sum(r[2] for r in rows)
    total_vt = sum(r[3] for r in rows)
    print()
    print(f'{"TOTAL":30s} types={total_types:5d}  instance_decls={total_decls:5d}  '
          f'virtual={total_vt:6d}  '
          f'vt/type={(total_vt / total_types if total_types else 0):6.1f}x  '
          f'vt/decl={(total_vt / total_decls if total_decls else 0):6.1f}x')
    if total_vt > total_decls:
        print(f'⚠ WARNING: total virtual_types ({total_vt}) > total instance_declarations '
              f'({total_decls}) -- this should be structurally impossible; investigate as an '
              f'algorithm bug')

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
