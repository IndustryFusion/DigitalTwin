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

from urllib.parse import urlparse, quote
from rdflib.namespace import RDFS, OWL, RDF
from rdflib import URIRef, Namespace, Graph, Literal, BNode
from rdflib.collection import Collection
from pathlib import Path
import re
import os
import json
from pyld import jsonld
import urllib
import warnings


WARNSTR = {
    'subclass_inconsistency': 'SUBCLASS_INCONSISTENCY',
    'folder_reference_inconsistency': 'FOLDER_INCONSISTENCY',
    'abstract_datatype': "ABSTRACT_DATATYPE",
    'no_default_instance': "NO_DEFAULT_INSTANCE",
    'no_iri_value': "NO_IRI_VALUE",
    'ignored_variable_reference': "IGNORED_VARIABLE_REFERENCE",
    'non_reached_nodes': "NON_REACHED_NODES",
    'ambiguous path match': "AMBIGUOUS_PATH_MATCH",
    'interface_not_subtype_of_interfacetype': "INTERFACE_NOT_SUBTYPE_OF_INTERFACETYPE"
}

NULL_IRI = URIRef('urn:ngsi-ld:null')
query_realtype = """
PREFIX owl: <http://www.w3.org/2002/07/owl#>

SELECT ?nodeclass ?realtype WHERE {
  {
     ?node a ?nodeclass .
  FILTER(?nodeclass != owl:NamedIndividual
      && STRENDS(STR(?nodeclass), "NodeClass")
      && STRSTARTS(STR(?nodeclass), STR(opcua:))
    )
  }
    UNION
  {
    {
      ?node a ?realtype .
      FILTER ((!STRENDS(STR(?realtype), "NodeClass") || !STRSTARTS(STR(?realtype), STR(opcua:))) &&
        ?realtype != owl:NamedIndividual
      )
    }
    UNION
    {
      ?node base:definesType ?realtype .
      ?node a opcua:ObjectTypeNodeClass .
    }
  }
}
"""


modelling_nodeid_optional = 80
modelling_nodeid_mandatory = 78
modelling_nodeid_optional_array = 11508
workaround_instances = ['http://opcfoundation.org/UA/DI/FunctionalGroupType', 'http://opcfoundation.org/UA/FolderType']
NGSILD = Namespace('https://uri.etsi.org/ngsi-ld/')
MACHINERY = Namespace('http://opcfoundation.org/UA/Machinery/')
ngsild_context = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld"


def print_warning(dictid, message):
    warnlabel = WARNSTR.get(dictid)
    if warnlabel is None:
        warnlabel = "GENERAL_WARNING"
    warnstr = f"{warnlabel}: {message}"
    warnings.warn(warnstr)


def dump_graph(g):
    for s, p, o in g:
        print(s, p, o)


def downcase_string(s):
    return s[0].lower() + s[1:]


def isNodeId(nodeId):
    return 'i=' in nodeId or 'g=' in nodeId or 's=' in nodeId


def rdfStringToPythonBool(literal):
    return str(literal).strip().lower() == "true"


def convert_to_json_type(result, basic_json_type):
    if basic_json_type == 'string':
        return str(result)
    if basic_json_type == 'boolean':
        return bool(result)
    if basic_json_type == 'integer':
        return int(result)
    if basic_json_type == 'number':
        return float(result)


def idtype2String(idtype, basens):
    if idtype == basens['numericID']:
        idt = 'i'
    elif idtype == basens['stringID']:
        idt = 's'
    elif idtype == basens['guidID']:
        idt = 'g'
    elif idtype == basens['opaqueID']:
        idt = 'b'
    else:
        idt = 'x'
        print('Warning no idtype found.')
    return idt


def extract_namespaces(graph):
    return {
        str(prefix): {
            '@id': str(namespace),
            '@prefix': True
        } for prefix, namespace in graph.namespaces()}


def get_datatype(graph, node, typenode, templatenode, basens):
    datatype = next(graph.objects(node, basens['hasDatatype']), None)
    if datatype is None:
        if templatenode is not None:
            datatype = next(graph.objects(templatenode, basens['hasDatatype']), None)
        if datatype is None and typenode is not None:
            datatype = next(graph.objects(typenode, basens['hasDatatype']), None)
    return datatype
# def get_datatype(graph, node, typenode, templatenode, basens):
#     datatype = next(graph.objects(node, basens['hasDatatype']), None)
#     if datatype is None:
#         datatype = next(graph.objects(templatenode, basens['hasDatatype']), None)
#         if datatype is None:
#             datatype = next(graph.objects(typenode, basens['hasDatatype']), None)
#     return datatype


def attributename_from_type(type):
    basename = None
    url = urlparse(type)
    if url.path is not None:
        basename = os.path.basename(url.path)
        basename = basename.removesuffix('Type')
    return basename


def normalize_angle_bracket_name(s):
    # Check if there are any angle brackets in the input string
    if '<' in s and '>' in s:
        # Remove everything inside and including the angle brackets
        no_brackets = re.sub(r'<[^>]*>', '', s)

        # If the result is empty, it means the entire name was in brackets like <Tank>
        if no_brackets.strip() == '':
            # Extract the name inside the angle brackets
            base_name = re.sub(r'[<>]', '', s)
            # The pattern should match valid BrowseNames
            pattern = r'[a-zA-Z0-9_-]+'
        else:
            # Otherwise, use the part before the angle brackets
            base_name = no_brackets.strip()
            # Construct a pattern to match the base name followed by valid BrowseName characters
            pattern = re.sub(r'<[^>]*>', r'[a-zA-Z0-9_-]+', s)
    else:
        # If there are no angle brackets, the base name is just the input string itself
        base_name = s
        # Pattern matches exactly the base name
        pattern = re.escape(s)  # Escape any special characters in the base name

    # Return the cleaned base name and the regular expression pattern
    return base_name.strip(), pattern


def contains_both_angle_brackets(s):
    return '<' in s and '>' in s


def get_typename(url):
    result = urlparse(url)
    if result.fragment != '':
        return result.fragment
    else:
        basename = os.path.basename(result.path)
        return basename


def is_subclass(graph, class1, class2):
    """Check if class1 is subclass of class2
        Returns True when class1 is subclass of class2
    Args:
        graph (RDFLIB.Graph): Graph to search on
        class1 (URIRef): subclass to check
        class2 (URIRef): superclass to check
    """
    query = """
        PREFIX base: <https://industryfusion.github.io/contexts/ontology/v0/base/>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        ASK {{
            <{class1}> rdfs:subClassOf* <{class2}>
        }}
    """.format(class1=class1, class2=class2)
    result = graph.query(query)
    return list(result)[0]


def get_common_supertype(graph, class1, class2):
    superclass = None

    # Prepare the query by injecting the class1 and class2 URIs into the query string
    query_common_superclass = """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?commonSuperclass (MIN(?depth1 + ?depth2) AS ?minDepth)
    WHERE {{

      # Find all superclasses of the first class (?class1)
      {{
        SELECT ?superclass1 (COUNT(?mid1) AS ?depth1)
        WHERE {{
            BIND(<{class1}> AS ?class1)
          ?class1 rdfs:subClassOf* ?mid1 .
          ?mid1 rdfs:subClassOf* ?superclass1 .
        }}
        GROUP BY ?superclass1
      }}

      # Find all superclasses of the second class (?class2)
      {{
        SELECT ?superclass2 (COUNT(?mid2) AS ?depth2)
        WHERE {{
          BIND(<{class2}> AS ?class2)
          ?class2 rdfs:subClassOf* ?mid2 .
          ?mid2 rdfs:subClassOf* ?superclass2 .
        }}
        GROUP BY ?superclass2
      }}

      # Find the common superclasses
      FILTER(?superclass1 = ?superclass2)
      BIND(?superclass1 AS ?commonSuperclass)
    }}
    GROUP BY ?commonSuperclass
    ORDER BY ?minDepth
    LIMIT 1
    """.format(class1=class1, class2=class2)  # Inject the URIs into the query

    try:
        result = graph.query(query_common_superclass)
        superclass = list(result)[0]['commonSuperclass']
    except Exception as e:
        print(f"Error: {e}")
        pass
    return superclass


def file_path_to_uri(file_path):
    if str(file_path).startswith('http'):
        return URIRef(str(file_path))
    path = Path(os.path.abspath(str(file_path)))
    return URIRef(path.as_uri())


def create_list(g, arr, datatype):
    if len(arr) == 0:
        return RDF.nil
    literal_list = [Literal(datatype(item)) for item in arr]
    list_start = BNode()
    Collection(g, list_start, literal_list)
    return list_start


def get_type_and_template(g, node, parentnode, basens, opcuans):
    """Derives the type definition and potential template definition

    Args:
        g (RDF Graph): graph to search in
        node (RDFURIRef): node to derive type and template
        parentnode (RDFURIRef): parent
    """
    query_type_and_template = """
    SELECT ?vartypenode ?templatenode WHERE {{
        BIND(<{node}> as ?node)
        BIND(<{parentnode}> as ?parentnode)
        ?node a ?vartype .
        ?vartypenode base:definesType ?vartype .
        FILTER NOT EXISTS{{ ?vartype rdfs:subClassOf opcua:BaseNodeClass}}
        ?node base:hasBrowseName ?browsename .
        OPTIONAL{{
            ?parentnode a ?parenttype .
            ?parenttypenode base:definesType ?parenttype .
            ?parenttypenode opcua:HasComponent ?templatenode .
            ?templatenode base:hasBrowseName ?browsename.
        }}
    }}
    """.format(node=node, parentnode=parentnode)
    result = g.query(query_type_and_template, initNs={'base': basens, 'opcua': opcuans})
    typenode, templatenode = next(iter(result), (None, None))
    return typenode, templatenode


def get_rank_dimensions(graph, node, typenode, templatenode, basens, opcuans):
    value_rank = next(graph.objects(node, basens['hasValueRank']), None)
    array_dimensions = next(graph.objects(node, basens['hasArrayDimensions']), None)
    type_value_rank = next(graph.objects(typenode, basens['hasValueRank']), None) if typenode is not None else None
    type_array_dimensions = next(graph.objects(typenode, basens['hasArrayDimensions']), None) \
        if typenode is not None else None
    template_value_rank = next(graph.objects(templatenode, basens['hasValueRank']), None) \
        if templatenode is not None else None
    template_array_dimensions = next(graph.objects(templatenode, basens['hasArrayDimensions']), None) \
        if templatenode is not None else None
    if value_rank is None:
        if template_value_rank is not None:
            value_rank = template_value_rank
        else:
            value_rank = type_value_rank
    if value_rank is None:
        value_rank = Literal(-1)
    if array_dimensions is None:
        if template_array_dimensions is not None:
            array_dimensions = template_array_dimensions
        else:
            array_dimensions = type_array_dimensions
    return value_rank, array_dimensions


def extract_subgraph(graph, start_node, predicates=None):
    subgraph = Graph()
    visited = set()

    def traverse(node):
        if node in visited:
            return
        visited.add(node)
        # Get all triples where the node is the subject and with predicate match if defined
        pred = predicates.pop(-1) if predicates else None
        for s, p, o in graph.triples((node, pred, None)):
            if p == NGSILD['datasetId'] and str(o).endswith('@none'):
                o = URIRef('@none')
            subgraph.add((s, p, o))
            # Only traverse further if o is a resource (URI or blank node)
            if isinstance(o, (BNode)):
                traverse(o)
    traverse(start_node)
    return subgraph


def dump_without_prefixes(g, format='turtle'):
    data = g.serialize(format=format)
    if isinstance(data, bytes):
        data = data.decode("utf-8")

    if format == 'json-ld':
        # For JSON-LD, flatten the document to resolve blank nodes
        jdata = json.loads(data)
        flattened = jsonld.flatten(jdata)
        data = json.dumps(flattened, indent=2)
    elif format == 'turtle':
        # For Turtle, filter out lines that define prefixes
        data = "\n".join(
            line for line in data.splitlines()
            if not line.strip().startswith(("@prefix", "PREFIX"))
        )
    return data


def get_contentclass(contentclass, value, g, basens):
    query_instance = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?instance WHERE {{
        bind(<{type}> as ?type)
        bind({value} as ?value)
        ?instance a ?type .
        ?instance base:hasValueNode ?valueNode .
        ?valueNode base:hasEnumValue ?value .
        ?valueNode base:hasValueClass ?type .
    }}
    """.format(value=value, type=contentclass)
    result = g.query(query_instance,
                     initNs={'base': basens})
    foundclass = None
    if len(result) > 0:
        foundclass = list(result)[0].instance
    return foundclass


def quote_url(uri):
    return quote(uri)


def merge_attributes(instance, attributes):
    for key in attributes:
        instance[key] = attributes[key]


class RdfUtils:
    def __init__(self, basens, opcuans):
        self.basens = basens
        self.opcuans = opcuans

    def isNodeclass(self, type):
        nodeclasses = [self.opcuans['BaseNodeClass'],
                       self.opcuans['DataTypeNodeClass'],
                       self.opcuans['ObjectNodeClass'],
                       self.opcuans['ObjectTypeNodeClass'],
                       self.opcuans['ReferenceTypeNodeClass'],
                       self.opcuans['VariableNodeClass'],
                       self.opcuans['VariableNodeClass']]
        result = bool([ele for ele in nodeclasses if (ele == type)])
        return result

    def isObjectNodeClass(self, type):
        return type == self.opcuans['ObjectNodeClass']

    def isObjectTypeNodeClass(self, type):
        return type == self.opcuans['ObjectTypeNodeClass']

    def isVariableNodeClass(self, type):
        return type == self.opcuans['VariableNodeClass']

    def get_type(self, g, node):
        try:
            bindings = {'node': node}
            results = list(g.query(query_realtype, initBindings=bindings,
                                   initNs={'opcua': self.opcuans, 'base': self.basens}))
            nodeclass = None
            type = None
            for result in results:
                if result[0] is not None:
                    nodeclass = result[0]
                elif result[1] is not None:
                    type = result[1]
            return (nodeclass, type)
        except:
            print(f"Warning: Could not find nodeclass of class node {node}. This should not happen")
            return None, None

    def get_interfaces(self, g, node):
        """Get all interfaces with their corresponding typenodes

           Cannot be done with a query since the order matters
        Args:
            g (Graph): Graph which contains the interface node
            node (URIRef): typenode to start scanning

        Returns:
            : [(URIRef type, URIRef node)]: type, node (instance declaration/type), type
        """
        interface_node = next(g.objects(node, self.opcuans['HasInterface']), None)
        if interface_node is None:
            return []

        supertypes = []
        curtype = None
        curnode = interface_node
        curtype = next(g.objects(curnode, self.basens['definesType']), None)
        while curtype != self.opcuans['BaseInterfaceType'] and curtype is not None:
            if curtype == self.opcuans['BaseObjectType']:
                warnmsg = f"Interface added to {node} is not subtype of BaseInterfaceType."
                print_warning('interface_not_subtype_of_interfacetype', warnmsg)
                break
            supertypes.append((curtype, curnode))
            curtype = next(g.objects(curtype, RDFS.subClassOf), None)
            curnode = next(g.subjects(self.basens['definesType'], curtype), None)
        return supertypes

    def get_all_supertypes_and_interfaces(self, g, instancetype, node):
        """Find the supertypes and interfaces to build the Fully Inherited Instance Declaration Hierarchy

           This can not be implemented by a sparql query since the order of the results is important
        Args:
            g (Graph): Graph containing the type and interface hierarchy
            instancetype (URIRef): The type to create the list of supertypes/interfaces
            node (URIRef): type node or instance declaration

        Returns:
            [(URIRef type, URIRef node)]: type, node (instance declaration/type)
        """
        supertypes = []

        curtype = URIRef(instancetype)
        curnode = node
        cur_typenode = next(g.objects(URIRef(node), self.basens['definesType']), None)
        if cur_typenode is None:
            # node is not instancetype definition
            cur_typenode = next(g.subjects(self.basens['definesType'], URIRef(curtype)))
            supertypes.append((None, curnode))
            interfaces = self.get_interfaces(g, curnode)
            supertypes += interfaces
            curnode = cur_typenode

        while curtype != self.opcuans['BaseObjectType'] and curtype is not None:
            supertypes.append((curtype, curnode))
            interfaces = self.get_interfaces(g, curnode)
            supertypes += interfaces
            curtype = next(g.objects(curtype, RDFS.subClassOf), None)
            if curtype is None:
                continue
            curnode = next(g.subjects(self.basens['definesType'], curtype), None)
        return supertypes

    def get_modelling_rule(self, graph, node, shacl_rule, instancetype):
        use_instance_declaration = False
        is_optional = True
        try:
            modelling_node = next(graph.objects(node, self.opcuans['HasModellingRule']))
            modelling_rule = next(graph.objects(modelling_node, self.basens['hasNodeId']))
            if int(modelling_rule) == modelling_nodeid_optional or str(instancetype) in workaround_instances:
                is_optional = True
            elif int(modelling_rule) == modelling_nodeid_mandatory:
                is_optional = False
            elif int(modelling_rule) == modelling_nodeid_optional_array:
                is_optional = True
                use_instance_declaration = True
        except:
            pass
        if shacl_rule is not None:
            shacl_rule['optional'] = is_optional
            shacl_rule['array'] = use_instance_declaration
        return is_optional, use_instance_declaration

    def get_all_subreferences(self, graph, node, reference):
        """Get non-hierarchical references

        Args:
            graph (Graph)): Graph to search in
            node (URIRef): Node to start searching
            reference (URIRef): Reference superclass

        Returns:
            list(URIRef): List of References found for the node
        """
        query_generic_references = """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        select ?reference ?target where {
            ?node ?reference ?target .
            ?reference rdfs:subClassOf* ?superclass .
        }
        """
        bindings = {'node': node, 'superclass': reference}
        result = graph.query(query_generic_references, initBindings=bindings, initNs={'opcua': self.opcuans})
        results = []
        if len(result) > 0:
            results = list(result)
        return results

    def get_ignored_references(self, graph):
        query_ignored_references = """
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

            SELECT ?subclass WHERE {
                VALUES ?reference {
                    opcua:GeneratesEvent
                    opcua:HasEventSource
                    opcua:HasModellingRule
                    opcua:HasInterface
                }
                    ?subclass rdfs:subClassOf* ?reference .
            }
            """
        result = graph.query(query_ignored_references, initNs={'opcua': self.opcuans})
        first_elements = [t[0] for t in set(result)]
        return first_elements

    def get_machinery_nodes(self, g):
        query_machines = """
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?machine ?type WHERE {
                ?machine_folder a opcua:FolderType .
                ?machine_folder base:hasNamespace machinery:MACHINERYNamespace .
                ?machine_folder base:hasNodeId "1001" .
                OPTIONAL{?machine_folder opcua:Organizes ?machine .}
                OPTIONAL{?machine_folder opcua:HasComponent ?machine .}
                ?machine a ?type .
                FILTER NOT EXISTS { ?type rdfs:subClassOf* opcua:BaseNodeClass .}
            }
        """
        result = g.query(query_machines,
                         initNs={'base': self.basens, 'machinery': MACHINERY, 'opcua': self.opcuans})
        foundmachines = None
        if len(result) > 0:
            foundmachines = list(result)
        return foundmachines

    def get_object_types_from_namespace(self, g, entity_namespace):
        query_instance = """
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT distinct ?type WHERE {{
            bind("{prefix}" as ?prefix)
            ?x a opcua:ObjectNodeClass .
            FILTER(STRSTARTS(STR(?x), ?prefix))
            ?x a ?type .
            FILTER NOT EXISTS{{?type rdfs:subClassOf* opcua:BaseNodeClass}}
        }}
        """.format(prefix=str(entity_namespace))
        result = g.query(query_instance,
                         initNs={'opcua': self.opcuans})
        foundtypes = None
        if len(result) > 0:
            foundtypes = [elem[0] for elem in list(result)]
        return foundtypes

    def generate_node_id(self, graph, rootentity, node, id):
        try:
            node_id = next(graph.objects(node, self.basens['hasNodeId']))
            idtype = next(graph.objects(node, self.basens['hasIdentifierType']))
            rootns = next(graph.objects(rootentity, self.basens['hasNamespace']))
            rootnsuri = next(graph.objects(rootns, self.basens['hasUri']))
            ns = next(graph.objects(node, self.basens['hasNamespace']))
            nsuri = next(graph.objects(ns, self.basens['hasUri']))
        except:
            node_id = 'unknown'
        idt = idtype2String(idtype, self.basens)
        quoted_node_id = urllib.parse.quote(node_id)
        if id is not None and str(nsuri) == str(rootnsuri):
            quoted_id = urllib.parse.quote(id, safe='/:')
            result = f'{nsuri}{quoted_id}:{idt}{quoted_node_id}'
        else:
            result = f'{nsuri}{idt}{quoted_node_id}'
        return result


class OntologyLoader:
    def __init__(self, verbose=False):
        self.ig = Graph()
        self.loaded_ontologies = set()  # Track loaded ontology IRIs
        self.visited_files = set()  # Track visited files/URLs
        self.verbose = verbose

    def init_imports(self, base_ontologies):
        for file in base_ontologies:
            self.load_ontology(file)

    def get_graph(self):
        return self.ig

    def load_ontology(self, ontology):
        ontology_str = str(ontology)

        # Check if the file has already been visited
        if ontology_str in self.visited_files:
            return

        # Load the ontology into a temporary graph
        hgraph = Graph()
        hgraph.parse(ontology)
        self.visited_files.add(ontology_str)

        # Find the ontology URI (subject of type owl:Ontology)
        ontology_iri = None
        for s in hgraph.subjects(RDF.type, OWL.Ontology):
            ontology_iri = str(s)  # Convert to string for comparison
            break

        # If the ontology has an IRI, use it to track loaded ontologies
        if ontology_iri and ontology_iri in self.loaded_ontologies:
            return

        # If no IRI is found, fall back to using the file/URL location
        if ontology_iri is None:
            ontology_iri = ontology_str

        # Add the ontology IRI to the loaded set
        self.loaded_ontologies.add(ontology_iri)

        # Add triples to the main graph
        if self.verbose:
            print(f"Importing {ontology_iri} from url {ontology}.")
        self.ig += hgraph

        # Find owl:imports and load them recursively
        for imported_ontology in hgraph.objects(None, OWL.imports):
            imported_ontology_str = str(imported_ontology)
            if imported_ontology_str not in self.loaded_ontologies and imported_ontology_str not in self.visited_files:
                self.load_ontology(imported_ontology)
