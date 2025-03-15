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

from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import OWL, RDF, RDFS
import xml.etree.ElementTree as ET
import urllib
import lib.utils as utils
import json

query_namespaces = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?uri ?prefix ?ns WHERE {
    ?ns rdf:type base:Namespace .
    ?ns base:hasUri ?uri .
    ?ns base:hasPrefix ?prefix .
}
"""
query_nodeIds = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?nodeId ?uri ?node WHERE {
    ?node rdf:type/rdfs:subClassOf opcua:BaseNodeClass .
    ?node base:hasNodeId ?nodeId .
    ?node base:hasNamespace ?ns .
    ?ns base:hasUri ?uri .
}
"""
query_types = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?nodeId ?uri ?type WHERE {
  {?type rdfs:subClassOf* opcua:BaseDataType .
   ?node base:definesType ?type .
   ?node base:hasNodeId ?nodeId .
   ?node base:hasNamespace ?ns .
   ?ns base:hasUri ?uri .
  }
  UNION
  {?type rdfs:subClassOf* opcua:BaseObjectType .
   ?node base:definesType ?type .
   ?node base:hasNodeId ?nodeId .
   ?node base:hasNamespace ?ns .
   ?ns base:hasUri ?uri .
  }
   UNION
  {?type rdfs:subClassOf* opcua:BaseVariableType .
   ?node base:definesType ?type .
   ?node base:hasNodeId ?nodeId .
   ?node base:hasNamespace ?ns .
   ?ns base:hasUri ?uri .
  }
   UNION
  {?type rdfs:subClassOf* opcua:References .
   ?node base:definesType ?type .
   ?node base:hasNodeId ?nodeId .
   ?node base:hasNamespace ?ns .
   ?ns base:hasUri ?uri .
  }
}
"""
query_references = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?id ?namespaceUri ?name
WHERE {
  ?subclass rdfs:subClassOf* <http://opcfoundation.org/UA/References> .
  ?node base:definesType ?subclass .
  ?node base:hasNodeId ?id .
  ?node base:hasNamespace ?ns .
  ?ns base:hasUri ?namespaceUri .
  ?node base:hasBrowseName ?name .
}
"""
basic_types = ['String', 'Boolean', 'Byte', 'SByte', 'Int16', 'UInt16', 'Int32', 'UInt32', 'Uin64', 'Int64', 'Float',
               'DateTime', 'Guid', 'ByteString', 'Double', 'Number']
basic_types_map = {'String': 'string',
                   'Boolean': 'boolean',
                   'Byte': 'integer',
                   'SByte': 'integer',
                   'Int16': 'integer',
                   'UInt16': 'integer',
                   'Int32': 'integer',
                   'UInt32': 'integer',
                   'UInt64': 'integer',
                   'Int64': 'integer',
                   'Float': 'number',
                   'DateTime': 'string',
                   'Guid': 'string',
                   'ByteString': 'string',
                   'Double': 'number',
                   'Number': 'number'}

hasSubtypeId = '45'
hasPropertyId = '46'
hasTypeDefinitionId = '40'
hasComponentId = '47'
hasAddInId = '17604'
organizesId = '35'
hasModellingRuleId = '37'
hasInterfaceId = '17603'
baseObjectTypeId = '58'
referencesId = '31'
baseDataTypeId = '24'
baseVariableType = '62'


class NodesetParser:

    def __init__(self, args, opcua_nodeset, opcua_inputs, version_iri, data_schema,
                 imported_ontologies, isstrict=False):
        self.known_opcua_ns = {
            'http://opcfoundation.org/UA/': 'opcua'
        }
        # Namespaces defined for RDF usage
        self.rdf_ns = {
        }
        self.known_ns_classes = {
            'http://opcfoundation.org/UA/': URIRef('http://opcfoundation.org/UA/OPCUANamespace')
        }
        self.g = Graph()
        self.ig = Graph()
        self.nodeIds = [{}]
        self.typeIds = [{}]
        self.opcua_ns = ['http://opcfoundation.org/UA/']
        self.known_references = []  # triples of all references (id, namespace, name)
        self.imported_ontologies = imported_ontologies
        self.aliases = {}
        self.opcua_inputs = opcua_inputs
        self.versionIRI = version_iri
        self.isstrict = isstrict
        self.xml_ns = {
            'opcua': 'http://opcfoundation.org/UA/2011/03/UANodeSet.xsd',
            'xsd': 'http://opcfoundation.org/UA/2008/02/Types.xsd'
        }
        try:
            with urllib.request.urlopen(opcua_nodeset) as response:
                tree = ET.parse(response)
        except:
            tree = ET.parse(opcua_nodeset)
        # calling the root element
        self.root = tree.getroot()
        self.data_schema = data_schema
        if args.namespace is None:
            models = self.root.find('opcua:Models', self.xml_ns)
            if models is None:
                print("Error: Namespace cannot be retrieved, please set it explicitly.")
                exit(1)
            model_count = len(models.findall('opcua:Model', self.xml_ns))
            if model_count != 1:
                print("Error: Target Namespace cannot be retrieved, there is more than one <Model> definition. \
Please set it explictly.")
                exit(1)
            model = models.find('opcua:Model', self.xml_ns)
            self.ontology_name = URIRef(model.get('ModelUri'))
            if not str(self.ontology_name).endswith('/'):
                self.ontology_name += '/'
        else:
            self.ontology_name = URIRef(args.namespace) if args.namespace is not None else None
        self.namespace_uris = self.root.find('opcua:NamespaceUris', self.xml_ns)
        if self.namespace_uris is not None:
            for uri in self.namespace_uris:
                if not uri.text.endswith('/'):
                    uri.text += '/'
        self.base_ontology = args.baseOntology
        self.opcua_namespace = args.opcuaNamespace
        self.ontology_prefix = args.prefix

    def parse(self):
        self.create_prefixes(self.namespace_uris, self.base_ontology, self.opcua_namespace)
        self.init_nodeids(self.opcua_inputs, self.ontology_name, self.ontology_prefix)
        self.create_header()
        try:
            aliases_node = self.root.find('opcua:Aliases', self.xml_ns)
            alias_nodes = aliases_node.findall('opcua:Alias', self.xml_ns)
            self.scan_aliases(alias_nodes)
        except:
            pass
        all_nodeclasses = [
            ('opcua:UADataType', 'DataTypeNodeClass'),
            ('opcua:UAReferenceType', 'ReferenceTypeNodeClass'),
            ('opcua:UAVariable', 'VariableNodeClass'),
            ('opcua:UAObjectType', 'ObjectTypeNodeClass'),
            ('opcua:UAObject', 'ObjectNodeClass'),
            ('opcua:UAVariableType', 'VariableTypeNodeClass'),
            ('opcua:UAMethod', 'MethodNodeClass')
        ]
        type_nodeclasses = [
            ('opcua:UAReferenceType', 'ReferenceTypeNodeClass'),
            ('opcua:UADataType', 'DataTypeNodeClass'),
            ('opcua:UAObjectType', 'ObjectTypeNodeClass'),
            ('opcua:UAVariableType', 'VariableTypeNodeClass')
        ]
        typed_nodeclasses = [
            ('opcua:UAVariable', 'VariableNodeClass'),
            ('opcua:UAObject', 'ObjectNodeClass')
        ]
        # Add Basic definition of NodeClasses
        for tag_name, type in all_nodeclasses:
            uanodes = self.root.findall(tag_name, self.xml_ns)
            for uanode in uanodes:
                self.add_uanode(uanode, type, self.xml_ns)
        # Create Type Hierarchy
        for tag_name, _ in type_nodeclasses:
            uanodes = self.root.findall(tag_name, self.xml_ns)
            firstpass = True
            for uanode in uanodes:
                try:
                    self.add_type(uanode)
                except:
                    firstpass = False
            if not firstpass:
                for uanode in uanodes:
                    self.add_type(uanode)
        # Type objects and varialbes
        for tag_name, _ in typed_nodeclasses:
            uanodes = self.root.findall(tag_name, self.xml_ns)
            for uanode in uanodes:
                self.add_typedef(uanode)

        # Process all nodes by type
        uadatatypes = self.root.findall('opcua:UADataType', self.xml_ns)
        for uadatatype in uadatatypes:
            self.add_uadatatype(uadatatype)

        # Process properties which need datatypes
        uanodes = self.root.findall('opcua:UAVariable', self.xml_ns)
        for uanode in uanodes:
            self.add_datatype_dependent(uanode)

    def init_imports(self, base_ontologies):
        if not self.isstrict:
            loader = utils.OntologyLoader(verbose=True)
            loader.init_imports(base_ontologies)
            self.ig = loader.get_graph()
        else:
            for file in base_ontologies:
                hgraph = Graph()
                hgraph.parse(file)
                self.ig += hgraph

    def get_all_node_ids(self):
        query_result = self.ig.query(query_nodeIds, initNs=self.rdf_ns)
        uris = self.opcua_ns
        urimap = {}
        for idx, uri in enumerate(uris):
            urimap[uri] = idx
            self.nodeIds.append({})
            self.typeIds.append({})
        for nodeId, uri, nodeIri in query_result:
            if str(uri) in urimap.keys():
                ns = urimap[str(uri)]
            else:
                continue
            try:
                self.nodeIds[ns][str(nodeId)] = nodeIri
            except:
                print(f"Warning: Did not find namespace {uri}. Did you import the respective companion specification?")
                exit(1)
        self.urimap = urimap

    def get_all_types(self):
        query_result = self.ig.query(query_types, initNs=self.rdf_ns)
        for nodeId, uri, type in query_result:
            if str(uri) in self.urimap.keys():
                ns = self.urimap[str(uri)]
            else:
                continue
            self.typeIds[ns][str(nodeId)] = type

    def get_all_references(self):
        query_result = self.ig.query(query_references, initNs=self.rdf_ns)
        for id, namespace_uri, name in query_result:
            self.known_references.append((id, namespace_uri, name))

    def get_all_namespaces(self, ontology_prefix, ontology_name, namespaceclass):
        query_result = self.ig.query(query_namespaces, initNs=self.rdf_ns)
        corens = list(self.known_opcua_ns.keys())[0]
        for uri, prefix, ns in query_result:
            if str(uri) != corens:
                print(f"Found RDF Prefix {prefix}: {uri}  with namespaceclass {ns}")
                self.known_opcua_ns[str(uri)] = str(prefix)
                self.known_ns_classes[str(uri)] = ns
                self.rdf_ns[str(prefix)] = Namespace(str(uri))
                self.g.bind(str(prefix), Namespace(str(uri)))
        self.rdf_ns[ontology_prefix] = Namespace(str(ontology_name))
        self.g.bind(ontology_prefix, Namespace(str(ontology_name)))
        self.known_ns_classes[str(ontology_name)] = self.rdf_ns[ontology_prefix][namespaceclass]
        self.known_opcua_ns[ontology_name.toPython()] = ontology_prefix

    def add_ontology_namespace(self, ontology_prefix, namespaceclass, ontology_name):
        self.g.add((self.rdf_ns[ontology_prefix][namespaceclass], RDF.type, self.rdf_ns['base']['Namespace']))
        self.g.add((self.rdf_ns[ontology_prefix][namespaceclass], self.rdf_ns['base']['hasUri'],
                    Literal(ontology_name.toPython())))
        self.g.add((self.rdf_ns[ontology_prefix][namespaceclass], self.rdf_ns['base']['hasPrefix'],
                    Literal(ontology_prefix)))

    def init_nodeids(self, base_ontologies, ontology_name, ontology_prefix):
        self.init_imports(base_ontologies)
        namespaceclass = f"{ontology_prefix.upper()}Namespace"
        self.get_all_namespaces(ontology_prefix, ontology_name, namespaceclass)
        self.get_all_node_ids()
        self.get_all_types()
        self.get_all_references()
        self.add_ontology_namespace(ontology_prefix, namespaceclass, ontology_name)

    def create_header(self):
        self.g.add((self.ontology_name, RDF.type, OWL.Ontology))
        if self.versionIRI is not None:
            self.g.add((self.ontology_name, OWL.versionIRI, self.versionIRI))
        self.g.add((self.ontology_name, OWL.versionInfo, Literal(0.1)))
        for ontology in self.imported_ontologies:
            self.g.add((self.ontology_name, OWL.imports, utils.file_path_to_uri(ontology)))

    def create_prefixes(self, xml_node, base, opcua_namespace):
        self.rdf_ns['base'] = Namespace(base)
        self.rdf_ns['opcua'] = Namespace(opcua_namespace)
        self.g.bind('opcua', self.rdf_ns['opcua'])
        self.g.bind('base', self.rdf_ns['base'])
        if xml_node is None:
            return
        for ns in xml_node:
            self.opcua_ns.append(ns.text)

    def get_rdf_ns_from_ua_index(self, index):
        namespace_uri = self.opcua_ns[int(index)]
        try:
            prefix = self.known_opcua_ns[namespace_uri]
        except:
            print(f"Warning: Namespace {namespace_uri} not found in imported companion specifications. \
Did you forget to import it?")
            exit(1)
        namespace = self.rdf_ns[prefix]
        return namespace

    def get_reference_subtype(self, node):
        subtype = None
        references = node.find('opcua:References', self.xml_ns)
        refs = references.findall('opcua:Reference', self.xml_ns)
        for ref in refs:
            reftype = ref.get('ReferenceType')
            isForward = ref.get('IsForward')
            if reftype == 'HasSubtype' and isForward == 'false':
                nsid, id = self.parse_nodeid(ref.text)
                try:
                    subtype = self.nodeIds[nsid][id]
                except:
                    print(f"Warning: Could not find type ns={nsid};i={id}")
                    subtype = None
        return subtype

    def add_datatype(self, node, classiri):
        datatype = node.get('DataType')
        if 'i=' not in datatype:  # alias is used
            datatype = self.aliases[datatype]
        index, id = self.parse_nodeid(datatype)
        try:
            typeiri = self.nodeIds[index][id]
        except:
            print(f'Warning: Cannot find nodeId ns={index};i={id}')
            return
        if datatype is not None:
            self.g.add((classiri, self.rdf_ns['base']['hasDatatype'], typeiri))

    def add_to_nodeids(self, rdf_namespace, name, node):
        nodeid = node.get('NodeId')
        ni_index, ni_id = self.parse_nodeid(nodeid)
        # prefix = self.known_opcua_ns[str(rdf_namespace)]
        self.nodeIds[ni_index][ni_id] = rdf_namespace[name]

    def nodeId_to_iri(self, namespace, nid, idtype):
        if idtype == self.rdf_ns['base']['numericID']:
            idt = 'i'
        elif idtype == self.rdf_ns['base']['stringID']:
            idt = 's'
            nid = urllib.parse.quote(nid)
        elif idtype == self.rdf_ns['base']['guidID']:
            idt = 'g'
        elif idtype == self.rdf_ns['base']['opaqueID']:
            idt = 'b'
        else:
            idt = 'x'
            print(f'Warning: No valid identifier found in {nid}')
        return namespace[f'node{idt}{nid}']

    def add_nodeid_to_class(self, node, nodeclasstype, xml_ns):
        nid, index, bn_name, idtype = self.get_nid_ns_and_name(node)
        rdf_namespace = self.get_rdf_ns_from_ua_index(index)
        classiri = self.nodeId_to_iri(rdf_namespace, nid, idtype)
        self.g.add((classiri, self.rdf_ns['base']['hasNodeId'], Literal(nid)))
        self.g.add((classiri, self.rdf_ns['base']['hasIdentifierType'], idtype))
        self.g.add((classiri, self.rdf_ns['base']['hasBrowseName'], Literal(bn_name)))
        namespace = self.opcua_ns[index]
        self.g.add((classiri, self.rdf_ns['base']['hasNamespace'], self.known_ns_classes[namespace]))
        self.g.add((classiri, RDF.type, self.rdf_ns['opcua'][nodeclasstype]))
        self.nodeIds[index][nid] = classiri
        displayname_node = node.find('opcua:DisplayName', xml_ns)
        self.g.add((classiri, self.rdf_ns['base']['hasDisplayName'], Literal(displayname_node.text)))
        symbolic_name = node.get('SymbolicName')
        if symbolic_name is not None:
            self.g.add((classiri, self.rdf_ns['base']['hasSymbolicName'], Literal(symbolic_name)))
        description_node = node.find('opcua:Description', xml_ns)
        if description_node is not None:
            description = description_node.text
            self.g.add((classiri, self.rdf_ns['base']['hasDescription'], Literal(description)))
        isSymmetric = node.get('Symmetric')
        if isSymmetric is not None:
            self.g.add((classiri, self.rdf_ns['base']['isSymmetric'], Literal(isSymmetric)))
        minimum_sampling_interval = node.get('MinimumSamplingInterval')
        if minimum_sampling_interval is not None:
            self.g.add((classiri, self.rdf_ns['base']['hasMinimumSamplingInterval'],
                        Literal(float(minimum_sampling_interval))))

        historizing = node.get('Historizing')
        if historizing is not None:
            self.g.add((classiri, self.rdf_ns['base']['isHistorizing'], Literal(bool(historizing))))
        return rdf_namespace, classiri

    def parse_nodeid(self, nodeid):
        """
        Parses a NodeId in the format 'ns=X;i=Y' and returns a dictionary with the namespace index and identifier.

        Args:
        nodeid (str): The NodeId to parse.

        Returns:
        tuple for ns, i
        """
        ns_index = 0
        try:
            ns_part, i_part = nodeid.split(';', 1)
        except:
            ns_part = None
            i_part = nodeid
        if ns_part is not None:
            ns_index = int(ns_part.split('=')[1])
        idt = i_part[0]
        if idt == 'i':
            identifierType = self.rdf_ns['base']['numericID']
        elif idt == 'g':
            identifierType = self.rdf_ns['base']['guidID']
        elif idt == 's':
            identifierType = self.rdf_ns['base']['stringID']
        elif idt == 'b':
            identifierType = self.rdf_ns['base']['opqueID']
        identifier = str(i_part.split('=', 1)[1])
        return ns_index, identifier, identifierType

    def add_uadatatype(self, node):
        nid, index, name, idtype = self.get_nid_ns_and_name(node)
        rdf_namespace = self.get_rdf_ns_from_ua_index(index)
        # classiri = self.nodeId_to_iri(rdf_namespace, nid, idtype)
        typeIri = rdf_namespace[name]
        definition = node.find('opcua:Definition', self.xml_ns)
        if definition is not None:
            fields = definition.findall('opcua:Field', self.xml_ns)
            for field in fields:
                elementname = field.get('Name')
                symbolicname = field.get('SymbolicName')
                if symbolicname is None:
                    symbolicname = elementname
                value = field.get('Value')
                itemname = rdf_namespace[f'{symbolicname}']
                datatypeid = field.get('DataType')
                datatypeIri = None
                if datatypeid is not None:  # structure is providing field details
                    datatypeid = self.resolve_alias(datatypeid)
                    datatype_index, datatype_id, _ = self.parse_nodeid(datatypeid)
                    datatypeIri = self.typeIds[datatype_index][datatype_id]
                    self.g.add((itemname, self.rdf_ns['base']['hasDatatype'], datatypeIri))
                    self.g.add((itemname, RDF.type, self.rdf_ns['base']['Field']))
                    self.g.add((typeIri, self.rdf_ns['base']['hasField'], itemname))
                else:  # Enumtype is considered as instance of class
                    self.g.add((itemname, RDF.type, typeIri))
                self.g.add((itemname, RDF.type, OWL.NamedIndividual))
                if value is not None:
                    bnode = BNode()
                    bbnode = self.rdf_ns['base']['_' + str(bnode)]
                    self.g.add((bbnode, RDF.type, self.rdf_ns['base']['ValueNode']))
                    self.g.add((itemname, self.rdf_ns['base']['hasValueNode'], bbnode))
                    self.g.add((bbnode, self.rdf_ns['base']['hasValueClass'], typeIri))
                    self.g.add((bbnode, self.rdf_ns['base']['hasEnumValue'], Literal(int(value))))
                self.g.add((itemname, self.rdf_ns['base']['hasFieldName'], Literal(str(symbolicname))))

    def add_uanode(self, node, type, xml_ns):
        namespace, classiri = self.add_nodeid_to_class(node, type, xml_ns)

    def resolve_alias(self, nodeid):
        alias = nodeid
        if not utils.isNodeId(nodeid):
            alias = self.aliases[nodeid]
        return alias

    def get_datatype(self, node, classiri):
        data_type = node.get('DataType')
        if data_type is not None:
            data_type = self.resolve_alias(data_type)
            dt_index, dt_id, _ = self.parse_nodeid(data_type)
            try:
                self.g.add((classiri, self.rdf_ns['base']['hasDatatype'], self.typeIds[dt_index][dt_id]))
            except Exception as e:
                print(f'Could not find datatype ns={dt_index},i={dt_id}')
                raise (e)

    def get_value_rank(self, node, classiri):
        value_rank = node.get('ValueRank')
        if value_rank is not None:
            self.g.add((classiri, self.rdf_ns['base']['hasValueRank'], Literal(int(value_rank))))

    def get_array_dimensions(self, node, classiri):
        array_dimensions = node.get('ArrayDimensions')
        if array_dimensions is not None:
            if isinstance(array_dimensions, str):
                result = [int(num) for num in array_dimensions.split(",")]
                array_dimensions = result
            if not isinstance(array_dimensions, list):
                array_dimensions = [array_dimensions]
            list_start = utils.create_list(self.g, array_dimensions, int)
            self.g.add((classiri, self.rdf_ns['base']['hasArrayDimensions'], list_start))

    def get_value(self, node, classiri, xml_ns):
        result = None
        value = node.find('opcua:Value', xml_ns)
        if value is not None:
            for children in value:
                tag = children.tag
                basic_type_found = bool([ele for ele in basic_types if (ele in tag)])
                basic_json_type = None
                if basic_type_found:
                    basic_json_type = [value for key, value in basic_types_map.items() if key in tag][0]
                if 'ListOf' in tag:
                    if basic_type_found:
                        data = self.data_schema.to_dict(children, namespaces=xml_ns, indent=4)
                        field = [ele for ele in data.keys() if ('@' not in ele)][0]
                        result = data[field]
                        created_list = utils.create_list(self.g, result, lambda x: x)
                        self.g.add((classiri, self.rdf_ns['base']['hasValue'], created_list))
                    continue
                elif basic_type_found:
                    data = self.data_schema.to_dict(children, namespaces=xml_ns, indent=4)
                    if '$' in data:
                        result = data["$"]
                        result = utils.convert_to_json_type(result, basic_json_type)
                        self.g.add((classiri, self.rdf_ns['base']['hasValue'], Literal(result)))
                else:  # does it contain a complex structure
                    data = self.data_schema.to_dict(children, namespaces=xml_ns, indent=4)
                    if "LocalizedText" in tag:
                        text = data.get('xsd:Text')
                        locale = data.get('xsd:Locale')
                        if text is not None:
                            result = Literal(text, lang=locale)
                            self.g.add((classiri, self.rdf_ns['base']['hasValue'], Literal(result)))
                    else:
                        json_obj = {}
                        for k, v in data.items():
                            if "xsd:" in k:
                                json_obj[k] = v
                        if len(json_obj.keys()) > 0:
                            result = Literal(json.dumps(json_obj), datatype=RDF.JSON)
                            self.g.add((classiri, self.rdf_ns['base']['hasValue'], Literal(result)))

    def references_get_special(self, id, ns):
        special_components = {
            (hasComponentId, self.opcua_namespace): 'hasComponent',
            (hasAddInId, self.opcua_namespace): 'hasAddIn',
            (hasPropertyId, self.opcua_namespace): 'hasProperty',
            (organizesId, self.opcua_namespace): 'organizes',
            (hasModellingRuleId, self.opcua_namespace): 'hasModellingRule',
            (hasInterfaceId, self.opcua_namespace): 'hasInterface'
        }
        try:
            return special_components[(id, ns)]
        except:
            return None

    def references_ignore(self, id, ns):
        ignored_components = [
            (hasSubtypeId, self.opcua_namespace),
            (hasTypeDefinitionId, self.opcua_namespace)
        ]
        return (id, ns) in ignored_components

    def get_references(self, refnodes, classiri):

        for reference in refnodes:
            reftype = reference.get('ReferenceType')
            isforward = reference.get('IsForward')
            nodeid = self.resolve_alias(reftype)
            reftype_index, reftype_id, _ = self.parse_nodeid(nodeid)
            reftype_ns = self.get_rdf_ns_from_ua_index(reftype_index)
            if self.references_ignore(reftype_id, reftype_ns):
                continue
            try:
                found_component = [ele[2] for ele in self.known_references if (int(ele[0]) == int(reftype_id) and
                                   str(ele[1]) == str(reftype_ns))][0]
            except:
                found_component = None
            if found_component is not None:
                componentId = self.resolve_alias(reference.text)
                index, id, idtype = self.parse_nodeid(componentId)
                namespace = self.get_rdf_ns_from_ua_index(index)
                targetclassiri = self.nodeId_to_iri(namespace, id, idtype)
                basens = self.rdf_ns['base']
                if self.references_get_special(reftype_id, reftype_ns) is None:
                    basens = reftype_ns
                else:
                    found_component = self.references_get_special(reftype_id, reftype_ns)
                if isforward != 'false':
                    self.g.add((classiri, basens[found_component], targetclassiri))
                else:
                    self.g.add((targetclassiri, basens[found_component], classiri))
            else:
                print(f"Warning: Could not find reference: {reftype}")

    def get_type_from_references(self, references, classiri):
        typedef = None
        for reference in references:
            reftype = reference.get('ReferenceType')
            isforward = reference.get('IsForward')
            nodeid = self.resolve_alias(reftype)
            type_index, type_id, _ = self.parse_nodeid(nodeid)
            if type_id == hasTypeDefinitionId and type_index == 0:
                # HasSubtype detected
                typedef = reference.text
                break
        if typedef is None:
            print(f'Warning: Object {classiri} has no type definition. This is not OPCUA compliant.')
            exit
        else:
            nodeid = self.resolve_alias(typedef)
            typedef_index, typedef_id, _ = self.parse_nodeid(typedef)
            if (isforward == 'false'):
                print(f"Warning: IsForward=false makes not sense here: {classiri}")
            else:
                try:
                    self.g.add((classiri, RDF.type, self.typeIds[typedef_index][typedef_id]))
                except IndexError as e:
                    print(f"Could not find namespace with id {typedef_index}")
                    raise e
                except Exception as e:
                    print(f"Could not find type with id {typedef_id} in namespace {self.opcua_ns[typedef_index]}")
                    raise e

    def add_typedef(self, node):
        _, browsename = self.getBrowsename(node)
        nodeid = node.get('NodeId')
        index, id, idtype = self.parse_nodeid(nodeid)
        namespace = self.get_rdf_ns_from_ua_index(index)
        classiri = self.nodeId_to_iri(namespace, id, idtype)
        references_node = node.find('opcua:References', self.xml_ns)
        references = references_node.findall('opcua:Reference', self.xml_ns)
        self.get_references(references, classiri)
        self.get_type_from_references(references, classiri)
        self.get_datatype(node, classiri)
        self.get_value_rank(node, classiri)
        self.get_array_dimensions(node, classiri)
        self.get_value(node, classiri, self.xml_ns)
        return

    def add_datatype_dependent(self, node):
        nodeid = node.get('NodeId')
        index, id, idtype = self.parse_nodeid(nodeid)
        namespace = self.get_rdf_ns_from_ua_index(index)
        classiri = self.nodeId_to_iri(namespace, id, idtype)
        self.get_user_access(node, classiri)
        self.get_event_notifier(node, classiri)

    def get_event_notifier(self, node, classiri):
        event_notifier = node.get('EventNotifier')
        if event_notifier is not None:
            for bit in (0, 2, 3):
                if int(event_notifier) & (1 << bit):
                    try:
                        content_class = utils.get_contentclass(self.rdf_ns['opcua']['EventNotifierType'],
                                                               bit, self.ig, self.rdf_ns['base'])
                        self.g.add((classiri, self.rdf_ns['base']['hasEventNotifier'], content_class))
                    except:
                        print(f"Warning: Cannot read all defined event in event_notifier value \
{event_notifier} in node {classiri}")

    def get_user_access(self, node, classiri):
        access_level = node.get('AccessLevel')
        if access_level is not None:
            for bit in range(7):
                if int(access_level) & (1 << bit):
                    try:
                        content_class = utils.get_contentclass(self.rdf_ns['opcua']['AccessLevelType'],
                                                               int(bit), self.ig, self.rdf_ns['base'])
                        if content_class is None:
                            content_class = utils.get_contentclass(self.rdf_ns['opcua']['AccessLevelType'],
                                                                   int(bit), self.g, self.rdf_ns['base'])
                        self.g.add((classiri, self.rdf_ns['base']['hasAccessLevel'], content_class))
                    except:
                        print(f"Warning: Cannot read access_level value {access_level} in node {classiri}")
        user_access_level = node.get('UserAccessLevel')
        if user_access_level is not None:
            for bit in range(7):
                if int(user_access_level) & (1 << bit):
                    try:
                        content_class = utils.get_contentclass(self.rdf_ns['opcua']['AccessLevelType'],
                                                               int(bit), self.ig, self.rdf_ns['base'])
                        if content_class is None:
                            content_class = utils.get_contentclass(self.rdf_ns['opcua']['AccessLevelType'],
                                                                   int(bit), self.g, self.rdf_ns['base'])
                        self.g.add((classiri, self.rdf_ns['base']['hasUserAccessLevel'], content_class))
                    except:
                        print(f"Warning: Cannot read access_level value {user_access_level} in node {classiri}")
        access_level_ex = node.get('AccessLevelEx')
        if access_level_ex is not None:
            for bit in range(7):
                if int(access_level_ex) & (1 << bit):
                    try:
                        content_class = utils.get_contentclass(self.rdf_ns['opcua']['AccessLevelExType'],
                                                               int(bit), self.ig, self.rdf_ns['base'])
                        if content_class is None:
                            content_class = utils.get_contentclass(self.rdf_ns['opcua']['AccessLevelExType'],
                                                                   int(bit), self.g, self.rdf_ns['base'])
                        self.g.add((classiri, self.rdf_ns['base']['hasAccessLevelEx'], content_class))
                    except:
                        print(f"Warning: Cannot read access_level value {access_level_ex} in node {classiri}")

    def is_objecttype_nodeset_node(node):
        return node.tag.endswith('UAObjectType')

    def is_base_object(self, name):
        return name == self.rdf_ns['opcua']['BaseObject']

    def get_typedefinition_from_references(self, references, ref_classiri, node):
        _, browsename = self.getBrowsename(node)
        nodeid = node.get('NodeId')
        ref_index, ref_id, idtype = self.parse_nodeid(nodeid)
        ref_namespace = self.get_rdf_ns_from_ua_index(ref_index)
        br_namespace = ref_namespace
        mandatory_typedef_found = False
        for reference in references:
            reftype = reference.get('ReferenceType')
            isforward = reference.get('IsForward')
            nodeid = self.resolve_alias(reftype)
            reftype_index, reftype_id, _ = self.parse_nodeid(nodeid)
            if reftype_id != hasSubtypeId or reftype_index != 0:
                continue
                # HasSubtype detected
            subtype = reference.text
            if subtype is not None:
                nodeid = self.resolve_alias(subtype)
                subtype_index, subtype_id, _ = self.parse_nodeid(subtype)
                typeiri = self.typeIds[subtype_index][subtype_id]
                if (isforward == 'false'):
                    self.g.add((br_namespace[browsename], RDFS.subClassOf, typeiri))
                    mandatory_typedef_found = True
                else:
                    self.g.add((typeiri, RDFS.subClassOf, br_namespace[browsename]))
            # else:
            #     if is_objecttype_nodeset(node):
            #         g.add((br_namespace[browsename], RDFS.subClassOf, rdf_ns['opcua']['BaseObjectType']))
                isAbstract = node.get('IsAbstract')
                if isAbstract is not None:
                    self.g.add((br_namespace[browsename], self.rdf_ns['base']['isAbstract'], Literal(isAbstract)))
                self.typeIds[ref_index][ref_id] = br_namespace[browsename]
                self.g.add((ref_classiri, self.rdf_ns['base']['definesType'], br_namespace[browsename]))
        if ref_id == baseObjectTypeId or ref_id == referencesId or ref_id == baseDataTypeId or\
                ref_id == baseVariableType:
            isAbstract = node.get('IsAbstract')
            if isAbstract is not None:
                self.g.add((br_namespace[browsename], self.rdf_ns['base']['isAbstract'], Literal(isAbstract)))
            self.typeIds[ref_index][ref_id] = br_namespace[browsename]
            self.g.add((ref_classiri, self.rdf_ns['base']['definesType'], br_namespace[browsename]))
        elif not mandatory_typedef_found:
            print(f"Error: Objecttype {ref_classiri} has no supertype and is not the base object type.")
            exit(1)

    def add_type(self, node):
        _, browsename = self.getBrowsename(node)
        nodeid = node.get('NodeId')
        ref_index, ref_id, idtype = self.parse_nodeid(nodeid)
        ref_namespace = self.get_rdf_ns_from_ua_index(ref_index)
        ref_classiri = self.nodeId_to_iri(ref_namespace, ref_id, idtype)
        try:
            references_node = node.find('opcua:References', self.xml_ns)
            references = references_node.findall('opcua:Reference', self.xml_ns)
        except:
            references = []
        self.g.add((ref_namespace[browsename], RDF.type, OWL.Class))
        if (node.tag.endswith("UAReferenceType")):
            self.known_references.append((Literal(ref_id), ref_namespace, Literal(browsename)))
            self.g.add((ref_namespace[browsename], RDF.type, OWL.ObjectProperty))
        self.get_references(references, ref_classiri)
        self.get_typedefinition_from_references(references, ref_classiri, node)
        self.get_datatype(node, ref_classiri)
        self.get_value_rank(node, ref_classiri)
        self.get_array_dimensions(node, ref_classiri)
        self.get_value(node, ref_classiri, self.xml_ns)
        return

    def get_nid_ns_and_name(self, node):
        nodeid = node.get('NodeId')
        ni_index, ni_id, idtype = self.parse_nodeid(nodeid)
        _, bn_name = self.getBrowsename(node)
        index = ni_index
        return ni_id, index, bn_name, idtype

    def scan_aliases(self, alias_nodes):
        for alias in alias_nodes:
            name = alias.get('Alias')
            nodeid = alias.text
            self.aliases[name] = nodeid

    def getBrowsename(self, node):
        name = node.get('BrowseName')
        index = None
        if ':' in name:
            result = name.split(':', 1)
            name = result[1]
            index = int(result[0])
        return index, name

    def write_graph(self, filename):
        self.g.serialize(destination=filename)
