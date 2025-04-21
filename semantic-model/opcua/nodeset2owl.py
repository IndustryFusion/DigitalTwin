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


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='\
parse nodeset and create RDF-graph <nodeset2.xml>')

    parser.add_argument('nodeset2', help='Path to the nodeset2 file')
    parser.add_argument('-i', '--inputs', nargs='*', help='<Required> add dependent nodesets as ttl')
    parser.add_argument('-o', '--output', help='Resulting file.', default="result.ttl")
    parser.add_argument('-n', '--namespace', help='Overwriting namespace of target ontology, e.g. \
                        http://opcfoundation.org/UA/Pumps/', required=False)
    parser.add_argument('-v', '--versionIRI', help='VersionIRI of ouput ontology, e.g. http://example.com/v0.1/UA/ ',
                        required=False)
    parser.add_argument('-b', '--baseOntology', help='Ontology containing the base terms, e.g. \
                        https://industryfusion.github.io/contexts/ontology/v0/base/',
                        required=False, default='https://industryfusion.github.io/contexts/ontology/v0/base/')
    parser.add_argument('-burl', '--baseOntologyURL', help='Ontology URL , e.g. \
                        https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl',
                        required=False,
                        default='https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl')
    parser.add_argument('-u', '--opcuaNamespace', help='OPCUA Core namespace, e.g. http://opcfoundation.org/UA/',
                        required=False, default='http://opcfoundation.org/UA/')
    parser.add_argument('-p', '--prefix', help='Prefix for added ontolgoy, e.g. "pumps"', required=True)
    parser.add_argument('-t', '--typesxsd', help='Schema for value definitions, e.g. Opc.Ua.Types.xsd',
                        default='https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/\
Schema/Opc.Ua.Types.xsd')
    parser.add_argument('--import-indirect-dependencies',
                        action="store_true",
                        default=False, help='Import not only direct dependencies but also indirect dependencies.')
    parsed_args = parser.parse_args(args)
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
ig = Graph()  # graph from inputs
g = Graph()  # graph wich is currently created
known_references = []  # triples of all references (id, namespace, name)


if __name__ == '__main__':
    args = parse_args()
    opcua_nodeset = args.nodeset2
    if args.inputs is not None:
        opcua_inputs = args.inputs
        for input in args.inputs:
            if os.path.basename(input) == input:
                input = f'{os.getcwd()}/{input}'
            imported_ontologies.append(URIRef(input))
    if args.baseOntologyURL not in imported_ontologies:
        imported_ontologies.append(URIRef(args.baseOntologyURL))
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
    nodesetparser.parse()
    nodesetparser.write_graph(opcua_output)
