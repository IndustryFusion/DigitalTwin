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

import sys
import argparse
import json
from rdflib import Graph
from rdflib.namespace import RDF, SH, OWL
import lib.utils as utils
from lib.utils import OntologyLoader
from lib.shacl import Validation
from lib.jsonld import nested_json_from_graph

generic_nodes = [RDF.nil]


def main():
    parser = argparse.ArgumentParser(description="SHACL Validation with Shape and Focus Context")
    parser.add_argument("-s", "--shacl", required=False, help="Path to SHACL shapes file", default='shacl.ttl')
    parser.add_argument("-e", "--extra", required=False, help="Path to extra ontology file")
    parser.add_argument("-df", "--data-format", required=False,
                        help="Data file format (e.g., turtle, json-ld, xml). If not provided infered from \
data-file name (.jsonld, .ttl).")
    parser.add_argument('-d', '--debug',
                        help='Debug output',
                        required=False,
                        action='store_true')
    parser.add_argument('-m', '--mode', required=False, default='instance',
                        help='Modes: "instance" to validate instance, "ontology" to validate ontology files.')

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

    args = parser.parse_args()
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
    shapes_graph = Graph(store='Oxigraph')
    shapes_graph.parse(args.shacl, format="turtle")
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
        # Dataformat is json-ld if
    elif args.mode == 'ontology':
        mainontology = next(data_graph.subjects(RDF.type, OWL.Ontology), None)
        if mainontology and not args.no_imports:
            imports = data_graph.objects(mainontology, OWL.imports)
            ontology_loader = OntologyLoader(True)
            ontology_loader.init_imports(imports)
            extra_graph = ontology_loader.get_graph()

    else:
        print("No valid mode selected.")
        sys.exit(1)

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


if __name__ == "__main__":
    main()
