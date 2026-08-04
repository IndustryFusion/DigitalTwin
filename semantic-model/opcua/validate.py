#!/usr/bin/env python3
#
# Copyright (c) 2025 Intel Corporation
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

from asyncio.log import logger
import os
import sys
import argparse
import json
from pathlib import Path
from rdflib import Graph
from rdflib.namespace import RDF, SH, OWL
import lib.utils as utils
from lib.utils import OntologyLoader
from lib.jsonld import nested_json_from_graph

generic_nodes = [RDF.nil]


def validate_virtual_types(data_path):
    """DL-reasoner (HermiT) consistency check for a *.vt.owl.ttl Virtual-Types
    ontology. This is a fundamentally different validation than modes
    "instance"/"ontology": those ask whether a SHACL shape holds over a data
    or ontology graph; this asks whether the OPC UA type restrictions the
    file encodes are jointly satisfiable, which is what check_consistency.py
    already checks with the real HermiT reasoner (not SHACL). Reuses that
    module's own file-loading/local-owl:imports-merging/HermiT-invocation
    logic directly instead of duplicating it -- that module (not this one)
    is what `make test`'s corpus-wide consistency sweep and
    tests/owl2vt/test.bash's e2e scenarios call directly, so this only ever
    wraps it for a single file, it never reimplements it. The import is
    local/lazy because check_consistency imports owlready2, which -- per its
    own module docstring -- is a deliberate opt-in (LGPL-3.0-or-later,
    incompatible with this repo's default Apache-2.0 dependency set), so
    "instance"/"ontology" mode users must not be forced to have it installed.
    """
    from check_consistency import build_full_owl_output, run_hermit

    path = Path(data_path).resolve()
    if not path.exists():
        print(f"Error: {path} does not exist.")
        sys.exit(1)
    full_out = build_full_owl_output(path)
    status, unsatisfiable, output = run_hermit(full_out)
    conforms = status == 'consistent'
    print("Validation Conforms:", conforms)
    if conforms:
        print("No validation errors found.")
        return
    print("\n=== HermiT DL Consistency Report ===")
    if status == 'unsatisfiable':
        print(f'{len(unsatisfiable)} unsatisfiable class(es) in {path.name}:')
        for cls in unsatisfiable:
            print(f'  {cls}')
    elif status == 'inconsistent':
        print(f'{path.name} is globally inconsistent.')
    else:
        print(f'HermiT failed to run against {path.name} -- raw output:\n{output}')
    sys.exit(1)


def load_shapes(path):
    """Load a SHACL shapes graph from `path`. If it's a directory, every *.shacl.ttl
    file directly within it (non-recursive) is parsed and merged -- SHACL NodeShapes
    are additive (each targets its own classes/properties), so merging can't produce
    spurious conflicts. If it's a single file, it's parsed directly. `*.shacl.ttl` is
    a filename convention, not content-sniffed: every shape file in this repo already
    follows it, matching how `*.owl.ttl`/`*.vt.owl.ttl` are also filename-conventions
    for other pipeline stages, and content-sniffing every .ttl in a directory just to
    decide whether to parse it would cost more (parse-to-decide-whether-to-parse) for
    no real benefit in a directory this project fully curates.

    This is what gives -m ontology a real default: unlike -m instance's shacl.ttl (a
    single file purpose-built for one specific instance document by extractType.py),
    there's no single canonical "the" ontology shapes file -- just a fixed, small set
    of independent structural rules (hasComponent, hasProperty, historizing,
    modellingRule, rankValue, ...) that all apply to any ontology equally. -s can
    still point at one specific file to scope a check to a single rule, or at any
    other directory of *.shacl.ttl files.
    """
    path = Path(path)
    graph = Graph(store='Oxigraph')
    if path.is_dir():
        shape_files = sorted(path.glob('*.shacl.ttl'))
        if not shape_files:
            print(f"Error: no *.shacl.ttl files found under {path}")
            sys.exit(1)
        print(f"Using SHACL shapes from {path}: {', '.join(f.name for f in shape_files)}")
        for shape_file in shape_files:
            graph.parse(shape_file, format="turtle")
    else:
        graph.parse(path, format="turtle")
    return graph


def main():
    parser = argparse.ArgumentParser(description="SHACL Validation with Shape and Focus Context")
    parser.add_argument("-s", "--shacl", required=False,
                        help="Path to a SHACL shapes file, or a directory of *.shacl.ttl files "
                             "to merge. Defaults to shacl.ttl for -m instance (extractType.py's "
                             "per-instance-type output); for -m ontology, defaults to the "
                             "validation/ontology/ directory (every structural rule file, merged). "
                             "Pass a single file explicitly to scope -m ontology to one rule.",
                        default=None)
    parser.add_argument("-e", "--extra", required=False, help="Path to extra ontology file")
    parser.add_argument("-df", "--data-format", required=False,
                        help="Data file format (e.g., turtle, json-ld, xml). If not provided infered from \
data-file name (.jsonld, .ttl).")
    parser.add_argument('-d', '--debug',
                        help='Debug output',
                        required=False,
                        action='store_true')
    parser.add_argument('-m', '--mode', required=False, default='instance',
                        help='Modes: "instance" to validate instance, "ontology" to validate ontology '
                             'files, "vt" to check a *.vt.owl.ttl Virtual-Types ontology for logical '
                             'consistency via the HermiT DL reasoner.')

    parser.add_argument("data", help="Path to RDF data file to validate")
    parser.add_argument('-st', '--strict', required=False, action='store_true',
                        help='Use strict, non accelerated SPARQL query.')
    parser.add_argument('-x', '--extended', required=False, action='store_true',
                        help='Use eXtended output with detailed context.')
    parser.add_argument('-ni', '--no-imports', required=False, action='store_true',
                        help='No imports of dependent ontologies.')
    parser.add_argument('-so', '--sparql-only', required=False, action='store_true',
                        help='Only apply sparql-rules')
    parser.add_argument('-ns', '--no_sparql', required=False, action='store_true',
                        help='Only apply sparql-rules')
    parser.add_argument('-me', '--merge-entity', required=False, help="Merge entity graph into the data graph"
                        " (experimental)", action='store_true')

    args = parser.parse_args()

    if args.mode == 'vt':
        validate_virtual_types(args.data)
        return

    if args.mode not in ('instance', 'ontology'):
        print("No valid mode selected.")
        sys.exit(1)

    if args.shacl is None:
        if args.mode == 'instance':
            args.shacl = 'shacl.ttl'
        else:  # ontology
            args.shacl = Path(__file__).resolve().parent / 'validation' / 'ontology'

    # Load RDF data (Data Graph)

    data_graph = Graph(store='Oxigraph')
    if args.data_format is None:
        if args.data.endswith('.jsonld'):
            args.data_format = 'json-ld'
        elif args.data.endswith('ttl'):
            args.data_format = 'ttl'
        else:
            print(f"Error: No default data-format given and cannot infer it from filename {args.data}")
            exit(1)
    data_graph.parse(args.data, format=args.data_format)
    # Load SHACL shapes (Shapes Graph)
    shapes_graph = load_shapes(args.shacl)
    extra_graph = Graph(store='Oxigraph')
    if args.mode == 'instance':
        # Load extra ontology if provided
        # if no extras given, default to entities.ttl
        if args.extra is None:
            args.extra = 'entities.ttl'
        extra_graph.parse(args.extra, format="turtle")
        # instance validation must be strict
        # There should be no mix between ontologies and instances
        args.strict = True
        # Experimental: load all owl imports of the entity files
        if args.merge_entity is True:
            entityontology = next(extra_graph.subjects(RDF.type, OWL.Ontology), None)
            if entityontology is not None:
                imports = extra_graph.objects(entityontology, OWL.imports)
                ontology_loader = OntologyLoader(True)
                ontology_loader.init_imports(imports)
                extra_graph += ontology_loader.get_graph()
            else:
                logger.warning(f'No ontology found in entity file {args.extra}. No imports will be loaded.')
    else:  # args.mode == 'ontology', the only remaining possibility -- checked above
        mainontology = next(data_graph.subjects(RDF.type, OWL.Ontology), None)
        if mainontology and not args.no_imports:
            imports = data_graph.objects(mainontology, OWL.imports)
            ontology_loader = OntologyLoader(True)
            ontology_loader.init_imports(imports)
            extra_graph = ontology_loader.get_graph()

    if args.merge_entity is True:
        os.environ["PYSHACL_USE_FULL_MIXIN"] = "true"
    from lib.shacl import Validation  # late import needed to respect the environment variable for pySHACL full mixin
    validation = Validation(shapes_graph, data_graph, extra_graph, args.strict,
                            args.sparql_only, args.no_sparql, args.debug)
    # Run SHACL validation
    conforms, results_graph, results_text = validation.shacl_validation()
    print("Validation Conforms:", conforms)
    if conforms:
        print("No validation errors found.")
        return

    print("\n=== SHACL Validation Report ===")
    print(results_text)
    if args.mode == 'instance' and args.extended is True:
        print("\n=== Validation Issues with Context ===")
        for idx, result in enumerate(results_graph.subjects(RDF.type, SH.ValidationResult)):
            focus_node = results_graph.value(result, SH.focusNode)
            source_shape = results_graph.value(result, SH.sourceShape)
            result_message = results_graph.value(result, SH.resultMessage)
            severity = results_graph.value(result, SH.resultSeverity)
            value_node = results_graph.value(result, SH.value)
            shape_name, paths = validation.find_shape_name(source_shape)
            if focus_node not in generic_nodes:
                entity_id, predicates = validation.find_entity_id(focus_node)
            else:
                entity_id, predicates = (focus_node, None)

            validation_nr = f'Validation error {idx + 1}'
            print(validation_nr)
            print("-" * len(validation_nr))
            print(f'Message: {result_message}')
            print(f'Severity: {severity}')
            print(f'Value Node: {value_node}')
            source_shape_subgraph = utils.extract_subgraph(shapes_graph, source_shape)
            print(utils.dump_without_prefixes(source_shape_subgraph))
            print(f'Source Shape (SHACL Rule which triggered the validation error): {shape_name}=>' +
                  '=>'.join(map(str, reversed(paths))))
            if predicates is not None and len(predicates) > 0:
                predicates_copy = predicates.copy()
                focus_node_subgraph = utils.extract_subgraph(data_graph, entity_id, predicates_copy)
                print(f'Focus Node (Entity which triggered the validation error): {entity_id}=>' +
                      '=>'.join(map(str, reversed(predicates))))
                result = nested_json_from_graph(focus_node_subgraph, root=None)
                print(json.dumps(result, indent=2))
            else:
                print(f'Focus Node (Entity which triggered the validation error): {entity_id}. More details \
cannot be determined. Check Source Shape for detailed path.')
    sys.exit(1)


if __name__ == "__main__":
    main()
