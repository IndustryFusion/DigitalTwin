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

import sys
import os
import xmlschema
from rdflib import Graph, URIRef
import argparse
from lib.nodesetparser import NodesetParser
import lib.utils as utils


# uardf meta ontology, local file for now
DEFAULT_UARDF_ONTOLOGY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uardf.ttl')


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='\
parse nodeset and create RDF-graph <nodeset2.xml>')

    parser.add_argument('nodeset2', help='Path to the nodeset2 file')
    parser.add_argument('-i', '--inputs', nargs='*', help='<Required> add dependent nodesets as ttl')
    parser.add_argument('-o', '--output', help='Resulting file.', default="result.owl.ttl")
    parser.add_argument('-n', '--namespace', help='Overwriting namespace of target ontology, e.g. \
                        http://opcfoundation.org/UA/Pumps/', required=False)
    parser.add_argument('-v', '--versionIRI', help='VersionIRI of ouput ontology, e.g. http://example.com/v0.1/UA/ ',
                        required=False)
    parser.add_argument('-b', '--baseOntology', help='Ontology containing the base terms, e.g. \
                        https://industryfusion.github.io/contexts/ontology/v0/base/',
                        required=False, default='https://industryfusion.github.io/contexts/ontology/v0/base/')
    parser.add_argument('-burl', '--baseOntologyURL', help='Ontology URL , e.g. \
                        https://industryfusion.github.io/contexts/staging/ontology/v0/base.ttl',
                        required=False,
                        default='https://industryfusion.github.io/contexts/staging/ontology/v0/base.ttl')
    parser.add_argument('--uardfOntology', help='Location of the uardf meta ontology (node classes and '
                        'identification properties, http://opcfoundation.org/rdf/uacore#) which is imported '
                        'by the output, e.g. a local file or URL.', required=False, default=DEFAULT_UARDF_ONTOLOGY)
    parser.add_argument('-u', '--opcuaNamespace', help='OPCUA Core namespace, e.g. http://opcfoundation.org/UA/',
                        required=False, default='http://opcfoundation.org/UA/')
    parser.add_argument('-p', '--prefix', help='Prefix for added ontolgoy, e.g. "pumps"', required=True)
    parser.add_argument('-t', '--typesxsd', help='Schema for value definitions, e.g. Opc.Ua.Types.xsd',
                        default='https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/\
Schema/Opc.Ua.Types.xsd')
    parser.add_argument('--import-indirect-dependencies',
                        action="store_true",
                        default=False, help='Import not only direct dependencies but also indirect dependencies.')
    parser.add_argument('--disable-semantic-bridge', required=False, action='store_true',
                        help='Disable adding semantic bridge between OPC UA and Containment/Domain ontology terms.')
    parser.add_argument('--enforce-opcua-type-semantic', required=False, action='store_true',
                        help='Enforce OPC UA type semantics, instead of uardf:hasTypeDefinition. This can create '
                             'instance validation problems.')
    parser.add_argument('--defaultLocale', required=False, default='en',
                        help='Locale of LocalizedText (DisplayName, Description, values) without Locale.')
    parser.add_argument('-s', '--serverUri', required=False, default=None,
                        help='Server URI (svu) used to identify dynamic nodes, e.g. urn:example:server. '
                             'Without it, dynamic nodes are not exported.')
    parser.add_argument('--dynamic-only', required=False, action='store_true',
                        help='Export only the server specific (dynamic) part, including references between static '
                             'and dynamic nodes. Requires --serverUri. Together with the export without '
                             '--serverUri (static part) it composes the full export. The export gets its own '
                             'ontology IRI per server: <ontology> + base64url(svu=<serverUri>).')
    parser.add_argument('--strict-classification', required=False, action='store_true',
                        help='Classify static/dynamic nodes strictly by the standard rules R3 (NamespaceMetadata '
                             'rule) and R5 (default fallback: types and instance declarations static, instances '
                             'dynamic). Disables the heuristic override R1 (instance-with-Variables) and the '
                             'heuristic fallback R4 (definition fallback), see README.')
    parser.add_argument('--classification-report', required=False, default=None,
                        help='Write the nodes which the heuristics classify differently than the standard rules '
                             '(static -> dynamic and dynamic -> static) to this TSV file.')
    parser.add_argument('--dynamic-imports', nargs='*', required=False, default=[],
                        help='With --dynamic-only: additional owl:imports of the dynamic export, which are not read '
                             'as inputs, e.g. the static export of the same nodeset and the dynamic exports of its '
                             'dependencies.')
    parsed_args = parser.parse_args(args)
    if parsed_args.dynamic_only and parsed_args.serverUri is None:
        parser.error('--dynamic-only requires --serverUri')
    if parsed_args.dynamic_imports and not parsed_args.dynamic_only:
        parser.error('--dynamic-imports requires --dynamic-only')
    return parsed_args


# Namespaces defined for RDF usage
rdf_ns = {
}
# Contains the mapping from opcua-ns-index to ns
opcua_ns = ['http://opcfoundation.org/UA/']


known_ns_classes = {
    'http://opcfoundation.org/UA/': URIRef('http://opcfoundation.org/UA/OPCUANamespace')}
unknown_ns_prefix = "ns"
versionIRI = None
ontology_name = None
imported_ontologies = []
aliases = {}
nodeIds = [{}]
typeIds = [{}]
ig = Graph(store="Oxigraph")  # graph from inputs
g = Graph(store="Oxigraph")  # graph wich is currently created
known_references = []  # triples of all references (id, namespace, name)


if __name__ == '__main__':
    args = parse_args()
    opcua_nodeset = args.nodeset2
    opcua_inputs = args.inputs if args.inputs is not None else []
    for input in opcua_inputs:
        if os.path.basename(input) == input:
            input = f'{os.getcwd()}/{input}'
        imported_ontologies.append(URIRef(input))
    base_ontology_found = False
    for ontology in imported_ontologies:
        if utils.v_major_equivalent(str(ontology), args.baseOntologyURL):
            base_ontology_found = True
            break
    if not base_ontology_found:
        imported_ontologies.append(URIRef(args.baseOntologyURL))
    uardf_ontology = URIRef(args.uardfOntology)
    if uardf_ontology not in imported_ontologies:
        imported_ontologies.append(uardf_ontology)
    opcua_output = args.output
    prefix = args.prefix
    data_schema = xmlschema.XMLSchema(args.typesxsd)
    versionIRI = URIRef(args.versionIRI) if args.versionIRI is not None else None
    nodesetparser = NodesetParser(args,
                                  opcua_nodeset,
                                  opcua_inputs,
                                  versionIRI,
                                  data_schema,
                                  imported_ontologies,
                                  not args.import_indirect_dependencies)
    print("Parsing nodesets and build OWL graph ...")
    nodesetparser.parse()
    if args.classification_report is not None:
        nodesetparser.write_classification_report(args.classification_report)
    if not args.disable_semantic_bridge:
        print("Adding semantic relationships...")
        nodesetparser.add_semantic_bridge()
    if args.dynamic_only:
        nodesetparser.restrict_to_dynamic_nodes(args.dynamic_imports)
    print("Writing graph to file ...")
    nodesetparser.write_graph(opcua_output)
    print(f"Done. Output written to: {opcua_output}")
