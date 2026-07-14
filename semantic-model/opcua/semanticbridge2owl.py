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
"""Transform a Semantic Bridge ttl (Part 5 / nodeset2owl.py output, e.g.
core.ttl or a companion spec like di.ttl) into a pure OWL ontology (Part 14 of
semantic_bridge_to_owl.md).

What this actually does, in order:

1. Parses the input ttl and undoes the base:instanceOf rewrite that Part 5
   applies to Object instance declarations, so Object and Variable
   declarations can be read uniformly.
2. Resolves the input's own owl:imports (e.g. di.ttl importing core.ttl) by
   loading each imported dependency into a *separate* graph, used only to
   resolve cross-file references -- a companion spec's types routinely
   subclass or aggregate a core type directly. Dependencies are never
   rescanned for Virtual Types and never copied into the output: if core.ttl
   was already processed into core.owl.ttl, this run only derives Virtual
   Types for di.ttl's *own* new types, and the output owl:imports the
   dependency's own already-generated pure-OWL file instead of duplicating it.
3. For every ObjectType/VariableType class the input file itself declares (or
   only the ones named via --roots), walks its Effective Declaration Tree --
   its own declared children plus everything inherited from its supertype
   (which may live in an imported dependency), with local overrides taking
   precedence -- and generates one "Virtual Type" class per (owning type,
   BrowsePath) pair, per semantic_bridge_to_owl.md sections 6-11.
4. Attaches an allValuesFrom restriction wherever a declaration occurs, plus
   a minQualifiedCardinality restriction for Mandatory declarations (sections
   13-16; someValuesFrom is deliberately not used -- see lib/owlbuilder.py),
   a symbolic
   ValueRank class and a Datatype restriction on Variable declarations
   (sections 17-18), and drops every Instance Declaration node from the
   output (section 19).
5. Copies over the class hierarchy (owl:Class/rdfs:subClassOf) and
   semantic-bridge property declarations (owl:ObjectProperty/
   rdfs:subPropertyOf) that the input file itself introduces (not its
   dependencies') unchanged, and writes an ontology header whose owl:imports
   point at each dependency's own pure-OWL sibling file.

The result contains no opcua:nodei*/di:nodei* declaration nodes at all -- only
classes, subclass edges, object properties and restrictions -- and is meant to
be loaded in Protégé (which will itself resolve owl:imports to pull in any
dependency) and classified with HermiT to check for OPC UA type constructions
that are structurally contradictory (e.g. an override that narrows a
component to an incompatible type or datatype).

Caveat: the real OPC UA core nodeset contains a small number of genuinely
self-referential types (e.g. DictionaryEntryType declares a placeholder child
typed as DictionaryEntryType itself, for arbitrarily nested dictionaries).
Virtual Types are now only minted where a declaration's own content actually
changes (a type override, ValueRank/Datatype change, or local structural
extension beyond the nominal type -- see get_cdt's docstring in
lib/owlbuilder.py), so self-reference is naturally a non-issue in the common
case (the placeholder's declared type doesn't change anything, so no new VT
-- and no recursion -- is ever needed for it); a `_cdt_computing` guard in
get_cdt still exists as a safety net against pathological cycles.

Example:

    # Full core.ttl (~600 types): takes roughly 10s and produces on the
    # order of 10k Virtual Type classes / ~10MB of ttl.
    python3 semanticbridge2owl.py core.ttl -o core.owl.ttl

    # di.ttl declares `owl:imports <file:///.../core.ttl>` itself, so this
    # auto-loads core.ttl for cross-referencing, but only derives Virtual
    # Types for di.ttl's own new types, and its output owl:imports
    # core.owl.ttl (run the line above first so that file actually exists):
    python3 semanticbridge2owl.py di.ttl -o di.owl.ttl

    # Fast first look, scoped to just the types you care about:
    python3 semanticbridge2owl.py core.ttl --roots PumpType,MotorType \\
        -o /tmp/pump.owl.ttl
"""

import os
import sys
import argparse
import time

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF

import lib.utils as utils
from lib.owlbuilder import OwlBuilder


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(
        description='Transform a Semantic Bridge ttl into a pure OWL ontology.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    parser.add_argument('input', help='Path to the Semantic Bridge ttl file, e.g. core.ttl or di.ttl')
    parser.add_argument('-o', '--output', help='Resulting file.', default=None)
    parser.add_argument('-i', '--inputs', nargs='*', default=None,
                        help='Additional already-processed dependency ttl file(s)/URL(s) to import, on '
                             'top of whatever this file\'s own owl:imports already declare (which are '
                             'resolved automatically for file:// locations). Use this only if a '
                             'dependency can\'t be auto-resolved, e.g. a remote URL not available '
                             'locally.')
    parser.add_argument('-b', '--baseOntology',
                        help='Namespace of the base terms, e.g. \
                        https://industryfusion.github.io/contexts/ontology/v0/base/',
                        required=False,
                        default='https://industryfusion.github.io/contexts/ontology/v0/base/')
    parser.add_argument('-u', '--opcuaNamespace', help='OPC UA namespace, e.g. http://opcfoundation.org/UA/',
                        required=False, default='http://opcfoundation.org/UA/')
    parser.add_argument('--roots', help='Comma-separated list of type local names to scope Virtual Type '
                                        'generation to (e.g. "PumpType,MotorType"), instead of every '
                                        'ObjectType/VariableType the input file itself declares. Useful '
                                        'for a first, fast test run before processing the whole file.',
                        required=False, default=None)
    parser.add_argument('--no-disjoint-valuerank', dest='disjoint_valuerank', action='store_false',
                        default=True,
                        help='Do not declare the ValueRank symbolic classes pairwise disjoint.')
    parser.add_argument('--require-modelling-rule', action='store_true', default=False,
                        help='Skip a declaration entirely (no Virtual Type, no restriction, nothing '
                             'nested inside it visited either) unless it carries a recognized '
                             'ModellingRule (Mandatory/Optional/(Mandatory|Optional)Placeholder) -- '
                             'the strict OPC UA sense of "Instance Declaration". Default off: every '
                             'Object/Variable child is processed regardless, including e.g. named '
                             'States/Transitions inside a StateMachineType-derived type, which OPC UA '
                             'aggregates via HasComponent/HasProperty with no ModellingRule at all. '
                             'Use this to get a Virtual Type count that lines up 1:1 with a strict '
                             'Instance Declaration count -- see virtual_type_stats.py\'s own '
                             '--include-unruled, which is this flag\'s inverse.')
    parser.add_argument('-q', '--quiet', action='store_true', default=False,
                        help='Suppress per-root progress output.')
    return parser.parse_args(args)


def owl_sibling_path(ttl_path):
    stem = ttl_path[:-len('.ttl')] if ttl_path.endswith('.ttl') else ttl_path
    return f'{stem}.owl.ttl'


def file_uri_to_path(uri):
    if str(uri).startswith('file://'):
        return str(uri)[len('file://'):]
    return None


if __name__ == '__main__':
    args = parse_args()
    input_path = args.input
    output_path = args.output
    if output_path is None:
        output_path = owl_sibling_path(input_path)

    basens = Namespace(args.baseOntology)
    opcuans = Namespace(args.opcuaNamespace)

    start = time.monotonic()
    print(f'Parsing {input_path} ...')
    g = Graph(store='Oxigraph')
    g.parse(input_path)

    # Auto-discover this file's own owl:imports (e.g. di.ttl declaring
    # `owl:imports <file:///.../core.ttl>`), plus anything explicitly given via
    # -i/--inputs, and load them all (recursively, following *their* own
    # owl:imports too) into a separate dependency graph via the existing
    # OntologyLoader used by the Part-5 pipeline.
    discovered_imports = [str(o) for o in g.objects(None, OWL.imports)]
    explicit_imports = args.inputs or []
    all_imports = discovered_imports + [i for i in explicit_imports if i not in discovered_imports]
    loader = utils.OntologyLoader(verbose=not args.quiet)
    if all_imports:
        print(f'Resolving imports: {all_imports}')
        loader.init_imports(all_imports)
    ig = loader.get_graph()

    builder = OwlBuilder(g, basens, opcuans, disjoint_valuerank=args.disjoint_valuerank, ig=ig,
                         require_modelling_rule=args.require_modelling_rule)
    roots = None
    if args.roots is not None:
        roots = [opcuans[name.strip()] for name in args.roots.split(',') if name.strip()]
        print(f'Restricting Virtual Type generation to: {[str(r) for r in roots]}')
    else:
        own_count = len(builder.all_target_classes())
        print(f'No --roots given: generating Virtual Types for all {own_count} '
              'ObjectType/VariableType classes this file itself declares (not its imports). '
              'This can take a while on the full core.ttl (~600 types); pass --roots to scope '
              'a faster first look.')

    def report_progress(index, total, root):
        if args.quiet:
            return
        if index == 1 or index % 25 == 0 or index == total:
            elapsed = time.monotonic() - start
            print(f'  [{index}/{total}] ({elapsed:.1f}s elapsed) {root}')

    print('Building Virtual Types and restrictions ...')
    out = builder.run(roots, progress=report_progress)

    # Ontology header: same IRI/versionIRI/versionInfo as the input, but with
    # owl:imports rewritten to point at each dependency's own pure-OWL sibling
    # file (e.g. core.ttl -> core.owl.ttl) instead of the raw semantic bridge
    # file, and non-file:// imports (e.g. the generic base.ttl) carried over
    # unchanged since those aren't Part-14-processed dependencies.
    ontology_iri = next(g.subjects(RDF.type, OWL.Ontology), None)
    if ontology_iri is not None:
        out.add((ontology_iri, RDF.type, OWL.Ontology))
        for p in (OWL.versionIRI, OWL.versionInfo):
            for o in g.objects(ontology_iri, p):
                out.add((ontology_iri, p, o))
        for imported in loader.visited_files:
            local_path = file_uri_to_path(imported)
            if local_path is None:
                out.add((ontology_iri, OWL.imports, URIRef(imported)))
                continue
            sibling = owl_sibling_path(local_path)
            if not os.path.exists(sibling):
                print(f'Warning: dependency {local_path} has not been processed into {sibling} yet -- '
                      f'run semanticbridge2owl.py on it first, or this owl:imports will 404.')
            out.add((ontology_iri, OWL.imports, URIRef(f'file://{sibling}')))

    elapsed = time.monotonic() - start
    print(f'Writing {len(out)} triples to {output_path} ({elapsed:.1f}s elapsed) ...')
    out.serialize(destination=output_path, format='turtle')
    print(f'Done in {time.monotonic() - start:.1f}s.')
