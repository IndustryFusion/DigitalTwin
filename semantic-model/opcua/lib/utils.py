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

from urllib.parse import urlparse
from rdflib.namespace import RDFS, XSD, OWL, RDF
from rdflib import URIRef, Namespace, Graph
from pathlib import Path
import json
import re
import os

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

query_generic_references = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

select ?reference ?target where {
  ?node ?reference ?target .
  ?reference rdfs:subClassOf* opcua:References
}
"""

query_ignored_references = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?subclass WHERE {
  VALUES ?reference {
    opcua:GeneratesEvent
    opcua:HasEventSource
  }
    ?subclass rdfs:subClassOf* ?reference .
}
"""

modelling_nodeid_optional = 80
modelling_nodeid_mandatory = 78
modelling_nodeid_optional_array = 11508
workaround_instances = ['http://opcfoundation.org/UA/DI/FunctionalGroupType', 'http://opcfoundation.org/UA/FolderType']
NGSILD = Namespace('https://uri.etsi.org/ngsi-ld/')


def dump_graph(g):
    for s, p, o in g:
        print(s, p, o)


def downcase_string(s):
    return s[0].lower() + s[1:]


def isNodeId(nodeId):
    return 'i=' in nodeId or 'g=' in nodeId or 's=' in nodeId


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


def get_datatype(graph, node, basens):
    try:
        return next(graph.objects(node, basens['hasDatatype']))
    except:
        return None


def attributename_from_type(type):
    basename = None
    url = urlparse(type)
    if url.path is not None:
        basename = os.path.basename(url.path)
        basename = basename.removesuffix('Type')
    return basename


def get_default_value(datatype):
    if datatype == XSD.integer:
        return 0
    if datatype == XSD.double:
        return 0.0
    if datatype == XSD.string:
        return ''
    if datatype == XSD.boolean:
        return False
    if datatype == RDF.JSON:
        return {'@value': {}, '@type': '@json'}
    if datatype == XSD.dateTime:
        return {'@value': '1970-1-1T00:00:00', '@type': 'xsd.dateTime'}
    print(f'Warning: unknown default value for datatype {datatype}')


def get_value(value, datatype):
    # values can be arrays, so check first for arrays and do later the scalar
    # transformations
    try:
        decoded = json.loads(value)
        if isinstance(decoded, list):
            return decoded
    except:
        pass
    if datatype == XSD.integer:
        return int(value)
    if datatype == XSD.double:
        return float(value)
    if datatype == XSD.string:
        return str(value)
    if datatype == XSD.boolean:
        return bool(value)
    if datatype == RDF.JSON:
        return {'@value': str(value), '@type': '@json'}
    if datatype == XSD.dateTime:
        return {'@value': str(value), '@type': 'xsd:dateTime'}
    return str(value)


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

    def get_all_supertypes(self, g, instancetype, node):
        supertypes = []

        curtype = URIRef(instancetype)
        curnode = node
        try:
            cur_typenode = next(g.objects(URIRef(node), self.basens['definesType']))
        except:
            cur_typenode = None
        if cur_typenode is None:
            # node is not instancetype definition
            cur_typenode = next(g.subjects(self.basens['definesType'], URIRef(curtype)))
            supertypes.append((None, curnode))
            curnode = cur_typenode

        while curtype != self.opcuans['BaseObjectType']:
            supertypes.append((curtype, curnode))
            try:
                curtype = next(g.objects(curtype, RDFS.subClassOf))
                curnode = next(g.subjects(self.basens['definesType'], URIRef(curtype)))
            except:
                break
        return supertypes

    def get_modelling_rule(self, graph, node, shacl_rule, instancetype):
        use_instance_declaration = False
        is_optional = True
        try:
            modelling_node = next(graph.objects(node, self.basens['hasModellingRule']))
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

    def get_generic_references(self, graph, node):
        bindings = {'node': node}
        result = graph.query(query_generic_references, initBindings=bindings, initNs={'opcua': self.opcuans})
        return list(result)

    def get_ignored_references(self, graph):
        result = graph.query(query_ignored_references, initNs={'opcua': self.opcuans})
        first_elements = [t[0] for t in set(result)]
        return first_elements


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
