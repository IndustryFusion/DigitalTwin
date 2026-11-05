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
import random
from lib.utils import warnings, print_warning  # Ensure print_warning is imported
from collections import defaultdict
from rdflib import Graph, Namespace
from rdflib.namespace import OWL, RDF
import argparse
from lib.utils import OntologyLoader, NGSILD, UARDF, OPCUA_CORE_NAMESPACE, parse_expanded_nodeid, \
    normalize_namespaceuri
from lib.bindings import Bindings

warnings.filterwarnings("ignore", message=".*anyType is not defined in namespace XSD.*")


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='\
parse nodeset instance and create ngsi-ld model')

    parser.add_argument('mapping', help='Path to the mapping ttl file which contains the IFFMappingsFolder Object.')
    parser.add_argument('-fi', '--folder-id',
                        help='Id of IFFMappingFolder Object. default: %(default)s',
                        required=False,
                        default=42)
    parser.add_argument('-bv', '--binding-version',
                        help='Version of the binding model. default: %(default)s',
                        required=False,
                        default="0.1")
    parser.add_argument('-bn', '--binding-namespace',
                        help='Namespace prefix for binding ontology. default: %(default)s',
                        required=False,
                        default="https://industry-fusion.org/UA/Bindings/")
    parser.add_argument('-b', '--bindings',
                        help='Filename of bindings output file. default: %(default)s',
                        required=False,
                        default='bindings_iffmodel.ttl')
    parser.add_argument('-i', '--instance-file',
                        help='Filename of instances file contating entity Ids.  default: %(default)s',
                        required=False,
                        default='iff_instances.jsonld')
    parser.add_argument('-n', '--iffmapping-namespace',
                        default='https://industry-fusion.org/UA/Mapping/',
                        help='Overwrite Namespace for IFF mapping ontology. default: %(default)s',
                        required=False)
    parser.add_argument('-d', '--debug',
                        help='Help debugging. e.g by setting seed.',
                        required=False,
                        action='store_true')

    parsed_args = parser.parse_args(args)
    return parsed_args


def get_folder(graph, iffmappingns, iffmappingfolder_id):
    """The IFFMappingsFolder node: the node of the IFF mapping namespace with the numeric identifier
    iffmappingfolder_id, identified by its uardf:nodeId (static, or dynamic with server URI)."""
    namespace = str(normalize_namespaceuri(iffmappingns))
    for node, expanded_nodeid in graph.subject_objects(UARDF['nodeId']):
        _, nsu, idt, identifier = parse_expanded_nodeid(expanded_nodeid)
        if idt == 'i' and identifier == str(iffmappingfolder_id) and \
                str(normalize_namespaceuri(nsu or OPCUA_CORE_NAMESPACE)) == namespace:
            return node
    print_warning("warning", f"IFFMappingsFolder i={iffmappingfolder_id} not found in namespace {namespace}. "
                  "Is it a dynamic node and the nodesets were created without --serverUri?")
    sys.exit(1)


def get_bindings(graph, iffmappingns, basens, opcuans, iffmappingfolder_id):
    """
    Get a list of all attribute bindings from the IFF Mappings ontology.

    This function queries an RDF graph to retrieve attribute bindings associated
    with a specific folder ID in the IFF Mappings ontology. The query extracts
    details such as the attribute name, type, logic expression, and entity selector.

        graph (rdflib.Graph): The RDF graph to query.
        iffmappingns (rdflib.Namespace): The namespace for the IFF Mapping ontology.
        basens (rdflib.Namespace): The base namespace for the RDF graph.
        opcuans (rdflib.Namespace): The OPC UA namespace for the RDF graph.
        iffmappingfolder_id (str): The folder ID to filter the query.

    Returns:
        list: A list of query results, where each result contains the following:
            - attributebinding (rdflib.term.URIRef): The URI of the attribute binding.
            - name (rdflib.term.URIRef): The URI of the attribute name.
            - type (rdflib.term.URIRef or None): The URI of the attribute type, if available.
            - logicExpression (rdflib.term.Literal or None): The logic expression, if available.
            - entitySelector (rdflib.term.Literal or None): The entity selector, if available.
    """
    query = """
  SELECT
  ?attributebinding ?name ?type ?logicExpression ?entitySelector
  where {
    ?folder opcua:HasComponent ?attributebinding .
    ?attributebinding opcua:HasComponent ?namenode .
    ?namenode uardf:name "AttributeName" .
    ?namenode base:hasValue ?namestr .
     OPTIONAL{
      ?attributebinding opcua:HasComponent ?typenode .
      ?typenode uardf:name "NGSILDAttributeType" .
      ?typenode base:hasValue ?typeenum .
      ?type a iffmappingns:NGSILDAttribute .
      ?type base:hasValueNode ?typevaluenode .
      ?typevaluenode base:hasEnumValue ?typeenum .
    }
    OPTIONAL{
      ?attributebinding opcua:HasComponent ?lenode .
      ?lenode uardf:name "LogicExpression" .
      ?lenode base:hasValue ?logicExpression .
    }
    OPTIONAL{
      ?attributebinding opcua:HasComponent ?esnode .
      ?esnode uardf:name "EntitySelector" .
      ?esnode base:hasValue ?entitySelector .
    }
    BIND(IRI(?namestr) as ?name)
}
    """
    initNs = {"iffmappingns": iffmappingns, "base": basens, "opcua": opcuans, "uardf": UARDF}
    folder = get_folder(graph, iffmappingns, iffmappingfolder_id)
    result = graph.query(query, initNs=initNs, initBindings={'folder': folder})
    return list(result)


def get_attribute_parameter(graph, iffmappingns, basens, opcuans, iffmappingfolder_id):
    """
        Retrieve a list of attribute bindings from the IFF mappings ontology.

        This function queries an RDF graph to extract attribute bindings and their associated parameters
        from the IFF mappings ontology. It returns a dictionary where the keys are attribute bindings
        and the values are lists of associated parameters.

            graph (rdflib.Graph): The RDF graph to query.
            iffmappingns (rdflib.Namespace): The namespace of the IFF Mapping Ontology.
            basens (rdflib.Namespace): The base namespace for the graph.
            opcuans (rdflib.Namespace): The OPC UA namespace for the graph.
            iffmappingfolder_id (str): The folder ID to filter the query.

        Returns:
            list: A list of dictionaries where each key is an attribute binding and the value is a list
                of associated parameters. Each parameter includes optional logic variables and variable
                details such as identifier type, namespace, and node ID.

        Notes:
            - The query uses SPARQL to extract data from the RDF graph.
            - The function binds the folder ID and namespace to filter the results.
            - Optional parameters such as logic variables and variable details are included if available.
    """
    query = """
  SELECT
  ?attributebinding ?logicVariable ?varnode ?varid ?varns ?datatype
  where {
    ?folder opcua:HasComponent ?attributebinding .
    ?attributebinding opcua:HasComponent ?attributeParameter .
    ?attributeParameter uardf:name ?attributeParameter_bn .
    FILTER(STRSTARTS(?attributeParameter_bn, "AttributeParameter_")) .
      ?attributeParameter opcua:HasComponent ?lvnode .
      ?lvnode uardf:name "LogicVariable" .
      ?lvnode base:hasValue ?logicVariable .
     OPTIONAL{
      ?attributeParameter iffmappingns:HasVariable ?varnode .
      ?varnode uardf:nodeId ?varid .
      ?varnode uardf:namespaceUri ?varnamespace .
      ?varnode base:hasDatatype ?datatype .
    }
  BIND(IRI(?varnamespace) as ?varns)
}

    """
    initNs = {"iffmappingns": iffmappingns, "base": basens, "opcua": opcuans, "uardf": UARDF}
    folder = get_folder(graph, iffmappingns, iffmappingfolder_id)
    result = graph.query(query, initNs=initNs, initBindings={'folder': folder})
    result = list(result)
    # Convert the reult to a dictionary with first element as key
    result_dict = defaultdict(list)
    for row in result:
        key = row[0]
        value = row[1:]
        result_dict[key].append(value)
    return result_dict


def get_entity_type(graph, iffmappingns, basens, opcuans, iffmappingfolder_id):

    query = """
   SELECT
   ?entityType
   where {
    ?folder opcua:HasComponent ?modelInfo .
    ?modelInfo uardf:name "ModelInfo" .
    ?modelInfo opcua:HasComponent ?typenode .
    ?typenode uardf:name "EntityType" .
    ?typenode base:hasValue ?entityTpe .
  BIND(IRI(?entityTpe) as ?entityType)
  }
    """
    initNs = {"iffmappingns": iffmappingns, "base": basens, "opcua": opcuans, "uardf": UARDF}
    folder = get_folder(graph, iffmappingns, iffmappingfolder_id)
    result = graph.query(query, initNs=initNs, initBindings={'folder': folder})
    if len(result) == 0:
        warnings.warning("EntityType not found in the IFFMappingFolder.")
    elif len(result) > 1:
        warnings.warning("Multiple EntityTypes found in the IFFMappingFolder. Using the first one.")
    return list(result)[0][0]


def get_ngsild_attribute(attribute, iffmappingns):
    """
    Get the NGSILD attribute type from the attribute.

    Attribute is given from iffmappingns namesapce.
    For instance, iffmappingns:Property => ngsi-ld:Property
    This function maps the attribute to its corresponding NGSILD type.
    The mapping is based on the IFF Mapping ontology.
    The mapping is done by replacing the prefix with the NGSILD prefix.
    The NGSILD prefix is defined in the NGSILD ontology.
    Args:
        attribute (str): The attribute to get the NGSILD type for.

    Returns:
        str: The NGSILD attribute type.
    """
    if str(attribute).startswith(str(iffmappingns)):
        if attribute.endswith("Property"):
            return NGSILD.Property
        elif attribute.endswith("Relationship"):
            return NGSILD.Relationship
        elif attribute.endswith("ListProperty"):
            return NGSILD.ListProperty
        elif attribute.endswith("JsonProperty"):
            return NGSILD.JsonProperty
    return None


def create_bindings_rdf(g, basens, bindingns, attributes, parameters, entity_type, binding_version, entities_graph):
    """
    Create an RDF graph for the OPC UA bindings structure.

    Args:
        bindings (list): List of attribute bindings retrieved from the RDF graph.
        parameters (list): List of attribute parameters associated with the bindings.
        entity_type (URIRef): The entity type URI.
        iffmappingns (Namespace): The namespace for the IFF Mapping ontology.

    Returns:
        rdflib.Graph: An RDF graph representing the OPC UA bindings structure.
    """
    # Get id of rdf node with entitiy_type
    entity_id = next(entities_graph.subjects(RDF.type, entity_type), None)
    if entity_id is None:
        raise ValueError("Entity ID not found in the entities graph.")

    bindings = Bindings(bindingns, basens)
    for attribute in attributes:
        binding_uri = bindings.create_attribute_binding(entity_id, attribute[1], attribute[3], binding_version)
        # Add parameters if available
        if attribute[0] in parameters:
            for param in parameters[attribute[0]]:
                bindings.add_map_to_attribute(g, binding_uri, param[0], param[1], basens.OPCUAConnector)
    return bindings.get_binding_graph()


if __name__ == '__main__':
    args = parse_args()
    mappingname = args.mapping
    bindingsname = args.bindings
    iffmapping_namespace = Namespace(args.iffmapping_namespace)
    iffmappingsfolder_id = args.folder_id
    bindingns = args.binding_namespace
    binding_version = args.binding_version
    if args.debug:
        random.seed(0)

    g = Graph(store='Oxigraph')
    g.parse(mappingname)
    # get all owl imports
    mainontology = next(g.subjects(RDF.type, OWL.Ontology), None)
    if mainontology is None:
        print_warning("warning", "No main ontology found in the mapping file. Exiting.")
        sys.exit(1)
    imports = g.objects(mainontology, OWL.imports)
    ontology_loader = OntologyLoader(True)
    ontology_loader.init_imports(imports)
    g += ontology_loader.get_graph()

    entities = Graph(store='Oxigraph')
    entities.parse(args.instance_file)

    basens = next(Namespace(uri) for prefix, uri in list(g.namespaces()) if prefix == 'base')
    opcuans = next(Namespace(uri) for prefix, uri in list(g.namespaces()) if prefix == 'opcua')
    bindings = get_bindings(g, iffmapping_namespace, basens, opcuans, iffmappingsfolder_id)
    parameters = get_attribute_parameter(g, iffmapping_namespace, basens, opcuans, iffmappingsfolder_id)
    entity_type = get_entity_type(g, iffmapping_namespace, basens, opcuans, iffmappingsfolder_id)

    # transform bindings parameters and entity_type to opcua bindings as described here:
    # https://github.com/IndustryFusion/DigitalTwin/blob/main/semantic-model/dataservice/README.md

    # Create the RDF graph for the bindings
    bindings_rdf = create_bindings_rdf(g=g,
                                       basens=basens,
                                       bindingns=bindingns,
                                       attributes=bindings,
                                       parameters=parameters,
                                       entity_type=entity_type,
                                       binding_version=binding_version,
                                       entities_graph=entities)

    # Output the RDF graph to a file
    bindings_rdf.serialize(destination=bindingsname, format="turtle")

    print(f"RDF graph for bindings written to {bindingsname}")
