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
import hashlib
import urllib
import lib.utils as utils
from lib.utils import RdfUtils
import json
import re
import sys


attribute_prefix = utils.ATTRIBUTE_PREFIX
query_namespaces = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?uri ?prefix ?ns WHERE {
    ?ns rdf:type base:Namespace .
    ?ns base:hasUri ?uri .
    ?ns base:hasPrefix ?prefix .
}
"""
# Nodes of the imported ontologies are read via their uardf: identification.
# ?nodeId is the canonical ExpandedNodeId string (e.g. "i=31", "nsu=...;i=1001").
query_nodeIds = """
SELECT ?nodeId ?uri ?node WHERE {
    VALUES ?nodeclass { uardf:DataType uardf:ReferenceType uardf:ObjectType uardf:VariableType
                        uardf:Object uardf:Variable uardf:Method uardf:View }
    ?node a ?nodeclass ;
          uardf:nodeId ?nodeId ;
          uardf:namespaceUri ?uri .
}
"""
query_types = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?nodeId ?uri ?type WHERE {
  {?type rdfs:subClassOf* opcua:BaseDataType . }
  UNION
  {?type rdfs:subClassOf* opcua:BaseObjectType . }
  UNION
  {?type rdfs:subClassOf* opcua:BaseVariableType . }
  UNION
  {?type rdfs:subPropertyOf* opcua:References . }
  ?node uardf:definesType ?type ;
        uardf:nodeId ?nodeId ;
        uardf:namespaceUri ?uri .
}
"""
query_references = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?id ?namespaceUri ?name
WHERE {
  ?subclass rdfs:subPropertyOf* <http://opcfoundation.org/UA/References> .
  ?node uardf:definesType ?subclass ;
        uardf:nodeId ?id ;
        uardf:namespaceUri ?namespaceUri ;
        uardf:name ?name .
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
hasOrderedComponentId = '49'
namespaceMetadataTypeId = '11616'
hasChildId = '34'
# HasChild and its subtypes of core, used until the reference type hierarchy is resolved (haschild_reference_types)
core_haschild_ids = ('34', '44', '45', '46', '47', '49', '17604', '24136')

UARDF = utils.UARDF
# IdType enumeration (i=256) as used in NamespaceMetadataType.StaticNodeIdTypes
idtype_enum = {'i': 0, 's': 1, 'g': 2, 'b': 3}
instance_tags = ('UAObject', 'UAVariable', 'UAMethod', 'UAView')
type_tags = ('UAObjectType', 'UAVariableType', 'UADataType', 'UAReferenceType')
# Definition types (rule R4): their instances are definitions rather than data, which types and data types refer to
# by NodeId (HasEncoding, HasDictionaryEntry, HasModellingRule, HasDescription): DataType encodings, dictionary
# entries, ModellingRules and the legacy type dictionaries. Where the NamespaceMetadata (R3) does not decide, R4 makes
# them static; the heuristic rule R1 never makes them dynamic (e.g. every ModellingRule has a NamingRule
# property).
definition_types = {'77': 'ModellingRuleType', '75': 'DataTypeSystemType', '72': 'DataTypeDictionaryType',
                    '69': 'DataTypeDescriptionType', '76': 'DataTypeEncodingType', '17589': 'DictionaryEntryType'}
# Variables of the (legacy) type dictionaries: definitions as well (R4)
typesystem_variable_types = ('72', '69')


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
        # Server URI (svu) used to identify dynamic nodes. Without it, dynamic nodes are not exported.
        self.server_uri = getattr(args, 'serverUri', None)
        self.default_locale = getattr(args, 'defaultLocale', 'en')
        self.enforce_opcua_type_semantic = getattr(args, 'enforce_opcua_type_semantic', False)
        # strict: only the standard rules R3 (NamespaceMetadata) and R5 (default fallback) decide
        self.strict_classification = getattr(args, 'strict_classification', False)
        self.heuristic_overrides = {}  # key -> reason, nodes which only the heuristic classifies dynamic
        self.node_iris = {}  # (ns index, canonical nodeid) -> IRI, or None for not exported dynamic nodes
        self.expanded_nodeids = {}  # (ns index, canonical nodeid) -> canonical ExpandedNodeId string (encoded in IRI)
        self.skipped_dynamic_nodes = []
        self.unknown_nodes = set()
        self.foreign_dynamic_iris = set()  # dynamic nodes of other nodesets which are referenced
        self.imported_namespace_indices = set()  # namespaces (index) exported by the imported ontologies
        self.xml_ns = {
            'opcua': 'http://opcfoundation.org/UA/2011/03/UANodeSet.xsd',
            'xsd': 'http://opcfoundation.org/UA/2008/02/Types.xsd'
        }
        try:
            with urllib.request.urlopen(opcua_nodeset) as response:
                tree = ET.parse(response)
        except Exception:
            tree = ET.parse(opcua_nodeset)
        # calling the root element
        self.root = tree.getroot()
        self.data_schema = data_schema
        models = self.root.find('opcua:Models', self.xml_ns)
        # RequiredModel entries are only used to annotate a missing-dependency error with the
        # version the nodeset itself expects (see check_namespace_dependencies); they are not
        # authoritative for *which* namespaces are actually needed. Some companion specs (e.g.
        # Machinery/ProcessValues) declare a RequiredModel for a namespace they never reference
        # by index (it's needed transitively by another direct dependency, e.g. PADIM), so
        # treating RequiredModel as required-coverage would demand ttls that aren't actually
        # dereferenced and currently aren't (and shouldn't need to be) passed via -i.
        self.required_models = {}
        if models is not None:
            for model in models.findall('opcua:Model', self.xml_ns):
                for required_model in model.findall('opcua:RequiredModel', self.xml_ns):
                    required_uri = required_model.get('ModelUri')
                    if required_uri is None:
                        continue
                    required_uri = str(utils.normalize_namespaceuri(required_uri))
                    self.required_models[required_uri] = required_model.get('Version')
        if args.namespace is None:
            if models is None:
                print("Error: Namespace cannot be retrieved, please set it explicitly.")
                sys.exit(1)
            model_count = len(models.findall('opcua:Model', self.xml_ns))
            if model_count != 1:
                print("Error: Target Namespace cannot be retrieved, there is more than one <Model> definition. \
Please set it explictly.")
                sys.exit(1)
            model = models.find('opcua:Model', self.xml_ns)
            self.ontology_name = URIRef(model.get('ModelUri'))
            self.ontology_name = utils.normalize_namespaceuri(self.ontology_name)
        else:
            self.ontology_name = utils.normalize_namespaceuri(args.namespace) if args.namespace is not None else None
        self.namespace_uris = self.root.find('opcua:NamespaceUris', self.xml_ns)
        # Namespace URIs exactly as defined in the nodeset (index aligned with self.opcua_ns)
        self.opcua_ns_raw = ['http://opcfoundation.org/UA/']
        if self.namespace_uris is not None:
            self.opcua_ns_raw += [uri.text.strip() for uri in self.namespace_uris]
            self.namespace_uris = [utils.normalize_namespaceuri(uri.text) for uri in self.namespace_uris]
        self.base_ontology = args.baseOntology
        self.opcua_namespace = args.opcuaNamespace
        self.ontology_prefix = args.prefix
        self.rdf_utils = RdfUtils(Namespace(self.base_ontology), Namespace(self.opcua_namespace))

    def parse(self):
        self.create_prefixes(self.namespace_uris, self.base_ontology, self.opcua_namespace)
        self.init_nodeids(self.opcua_inputs, self.ontology_name, self.ontology_prefix)
        self.create_header()
        try:
            aliases_node = self.root.find('opcua:Aliases', self.xml_ns)
            alias_nodes = aliases_node.findall('opcua:Alias', self.xml_ns)
            self.scan_aliases(alias_nodes)
        except Exception:
            pass
        self.classify_nodes()
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
            # Pre-register all type names so forward references don't raise KeyError in add_type.
            for uanode in uanodes:
                self.add_type_name_only(uanode)
            # Now add full type definitions; all type names are pre-registered so forward references resolve.
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

    def add_semantic_bridge(self):
        """Add semantic relationships to the graph.

        This function executes a SPARQL query to find all semantic relationships and adds them to the graph.

        """
        not_needed_property_query = """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        SELECT ?s ?sbc ?o ?bn ?qualifiedname WHERE {
            ?sbc rdfs:subPropertyOf* opcua:Aggregates .
            ?s ?sbc ?o .
            ?o uardf:name ?bn ;
               uardf:browseName ?qualifiedname .
        }
        """
        joint_graph = self.g + self.ig
        root_property = self.rdf_utils.get_root_property_of_semantic_bridge()
        bindings = {'root_property': root_property}
        query_result = joint_graph.query(not_needed_property_query, initNs=self.rdf_ns, initBindings=bindings)
        for s, sbc, o, bn, qualifiedname in query_result:
            if ((s, sbc, o) in self.g) is False:
                continue
            targetns = self.rdf_ns_for_uri(utils.parse_qualified_name(qualifiedname)[0])
            targetreference = targetns[urllib.parse.quote(f'{attribute_prefix}{bn}')]
            self.g.add((s, targetreference, o))
            self.add_semantic_relationship(targetreference)

    def rdf_ns_for_uri(self, namespace_uri):
        """RDF namespace of an OPC UA namespace URI (as used for the nodes of that namespace)."""
        normalized = str(utils.normalize_namespaceuri(namespace_uri))
        if normalized in self.opcua_ns:
            return self.get_rdf_ns_from_ua_index(self.opcua_ns.index(normalized))
        return Namespace(normalized)

    def add_semantic_relationship(self, targetreference):
        semantic_bridge_property = UARDF['semanticBridgeReferenceType']
        if (targetreference, RDFS.subPropertyOf, semantic_bridge_property) not in self.ig:
            self.g.add((targetreference, RDF.type, OWL.ObjectProperty))
            self.g.add((targetreference, RDFS.subPropertyOf, semantic_bridge_property))

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
            uri = str(utils.normalize_namespaceuri(uri))
            if uri in urimap.keys():
                ns = urimap[uri]
            else:
                continue
            try:
                self.nodeIds[ns][utils.parse_expanded_nodeid(nodeId)[3]] = nodeIri
                self.imported_namespace_indices.add(ns)
            except Exception:
                print(f"Warning: Did not find namespace {uri}. Did you import the respective companion specification?")
                sys.exit(1)
        self.urimap = urimap

    def get_all_types(self):
        query_result = self.ig.query(query_types, initNs=self.rdf_ns)
        for nodeId, uri, type in query_result:
            uri = str(utils.normalize_namespaceuri(uri))
            if uri in self.urimap.keys():
                ns = self.urimap[uri]
            else:
                continue
            self.typeIds[ns][utils.parse_expanded_nodeid(nodeId)[3]] = type

    def get_all_references(self):
        query_result = self.ig.query(query_references, initNs=self.rdf_ns)
        for id, namespace_uri, name in query_result:
            self.known_references.append((Literal(utils.parse_expanded_nodeid(id)[3]),
                                          utils.normalize_namespaceuri(namespace_uri), name))

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
        ontology_name = utils.normalize_namespaceuri(ontology_name)
        self.rdf_ns[ontology_prefix] = Namespace(str(ontology_name))
        self.g.bind(ontology_prefix, Namespace(str(ontology_name)))
        self.known_ns_classes[str(ontology_name)] = self.rdf_ns[ontology_prefix][namespaceclass]
        self.known_opcua_ns[ontology_name.toPython()] = ontology_prefix

    def add_ontology_namespace(self, ontology_prefix, namespaceclass, ontology_name):
        self.g.add((self.rdf_ns[ontology_prefix][namespaceclass], RDF.type, self.rdf_ns['base']['Namespace']))
        self.g.add((self.rdf_ns[ontology_prefix][namespaceclass], self.rdf_ns['base']['hasUri'],
                    Literal(str(utils.normalize_namespaceuri(ontology_name)))))
        self.g.add((self.rdf_ns[ontology_prefix][namespaceclass], self.rdf_ns['base']['hasPrefix'],
                    Literal(ontology_prefix)))

    def init_nodeids(self, base_ontologies, ontology_name, ontology_prefix):
        self.init_imports(base_ontologies)
        namespaceclass = f"{ontology_prefix.upper()}Namespace"
        self.get_all_namespaces(ontology_prefix, ontology_name, namespaceclass)
        self.check_namespace_dependencies()
        self.get_all_node_ids()
        self.get_all_types()
        self.get_all_references()
        self.add_ontology_namespace(ontology_prefix, namespaceclass, ontology_name)

    def check_namespace_dependencies(self):
        """Fail fast, with one consolidated error, if a namespace this file can reference by
        index (ns=X, per its own <NamespaceUris>) isn't covered by the provided --inputs
        (directly, or transitively via their owl:imports under --import-indirect-dependencies).

        self.opcua_ns (core + <NamespaceUris>) is the authoritative index table -- every ns=X
        in this file resolves through it, so it's exactly what needs to be covered. This file's
        own target namespace is never reported missing: get_all_namespaces() always registers it
        in known_opcua_ns before this runs, since it's what this run is producing, not something
        that needs to be imported.
        """
        required = {str(utils.normalize_namespaceuri(uri)) for uri in self.opcua_ns}
        covered = set(self.known_opcua_ns.keys())
        missing = sorted(required - covered)
        if not missing:
            return
        print("Error: The following namespace(s) are referenced by this NodeSet2 file (via its "
              "<NamespaceUris>) but are not covered by any of the provided --inputs, whether "
              "directly or via their transitive owl:imports:")
        for uri in missing:
            version = self.required_models.get(uri)
            hint = f" (RequiredModel version {version})" if version else ""
            print(f"  - {uri}{hint}")
        print("Did you forget to pass the corresponding companion specification ttl via -i/--inputs?")
        exit(1)

    def create_header(self):
        self.g.add((self.ontology_name, RDF.type, OWL.Ontology))
        if self.versionIRI is not None:
            self.g.add((self.ontology_name, OWL.versionIRI, self.versionIRI))
        self.g.add((self.ontology_name, OWL.versionInfo, Literal(0.1)))
        for ontology in self.imported_ontologies:
            self.g.add((self.ontology_name, OWL.imports, utils.file_path_to_uri(ontology)))

    def create_prefixes(self, ns_uris, base, opcua_namespace):
        self.rdf_ns['base'] = Namespace(base)
        self.rdf_ns['opcua'] = Namespace(opcua_namespace)
        self.g.bind('opcua', self.rdf_ns['opcua'])
        self.g.bind('base', self.rdf_ns['base'])
        self.rdf_ns['uardf'] = UARDF
        self.g.bind('uardf', UARDF)
        if ns_uris is None:
            return
        for ns in ns_uris:
            self.opcua_ns.append(str(ns))

    def get_rdf_ns_from_ua_index(self, index):
        namespace_uri = self.opcua_ns[int(index)]
        try:
            prefix = self.known_opcua_ns[namespace_uri]
        except Exception:
            print(f"Warning: Namespace {namespace_uri} not found in imported companion specifications. \
Did you forget to import it?")
            sys.exit(1)
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
                except Exception:
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
        except Exception:
            print(f'Warning: Cannot find nodeId ns={index};i={id}')
            return
        if datatype is not None:
            self.g.add((classiri, self.rdf_ns['base']['hasDatatype'], typeiri))

    def add_to_nodeids(self, rdf_namespace, name, node):
        nodeid = node.get('NodeId')
        ni_index, ni_id = self.parse_nodeid(nodeid)
        # prefix = self.known_opcua_ns[str(rdf_namespace)]
        self.nodeIds[ni_index][ni_id] = rdf_namespace[name]

    def add_nodeid_to_class(self, node, nodeclasstype, xml_ns):
        nid, index, bn_name, bn_index, idtype = self.get_nid_ns_and_name(node)
        rdf_namespace = self.get_rdf_ns_from_ua_index(index)
        classiri = self.node_iri(index, nid, idtype)
        if classiri is None:
            return rdf_namespace, None
        # Node class, NodeId, namespace, BrowseName, SymbolicName, DisplayName and Description are
        # described by uardf: only.
        # The base: attributes below have no uardf: counterpart yet.
        self.add_uardf_identification(node, nodeclasstype, index, nid, idtype, bn_name, bn_index, classiri)
        self.add_uardf_parent(node, classiri)
        self.nodeIds[index][nid] = classiri
        displayname = self.localized_text(node.find('opcua:DisplayName', xml_ns))
        if displayname is not None:
            self.g.add((classiri, UARDF['displayName'], displayname))
        description = self.localized_text(node.find('opcua:Description', xml_ns))
        if description is not None:
            self.g.add((classiri, UARDF['description'], description))
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

    def localized_text(self, element):
        """LocalizedText element (e.g. DisplayName, Description) as rdf:langString, None if empty.

        Elements without Locale get the default locale.
        """
        if element is None or element.text is None or element.text.strip() == '':
            return None
        locale = (element.get('Locale') or '').strip() or self.default_locale
        return Literal(element.text, lang=locale)

    def add_uardf_parent(self, node, classiri):
        """Preserve the ParentNodeId structure of the nodeset."""
        parent = node.get('ParentNodeId')
        if parent is None:
            return
        parent_index, parent_id, parent_idtype = self.parse_nodeid(self.resolve_alias(parent))
        parent_iri = self.node_iri(parent_index, parent_id, parent_idtype)
        if parent_iri is not None:  # None: not exported dynamic node
            self.g.add((classiri, UARDF['parent'], parent_iri))

    def add_uardf_identification(self, node, nodeclasstype, index, nid, idtype, bn_name, bn_index, classiri):
        key = self.node_key(index, nid, idtype)
        self.g.add((classiri, RDF.type, UARDF[nodeclasstype.removesuffix('NodeClass')]))
        # the canonical ExpandedNodeId string without server URI; for static nodes exactly what is encoded in the IRI,
        # dynamic nodes have their server URI in the IRI (svu=) and in uardf:serverUri
        self.g.add((classiri, UARDF['nodeId'], Literal(utils.expanded_nodeid_string(key[1], self.opcua_ns_raw[index]))))
        self.g.add((classiri, UARDF['namespaceUri'], Literal(self.opcua_ns_raw[index])))
        if key not in self.static_nodes:
            self.g.add((classiri, UARDF['serverUri'], Literal(self.server_uri)))
        # browseName is the canonical QualifiedName (nsu=<uri>;<name>), name is just its name part
        self.g.add((classiri, UARDF['browseName'],
                    Literal(utils.canonical_qualified_name(bn_name, self.opcua_ns_raw[bn_index]))))
        self.g.add((classiri, UARDF['name'], Literal(bn_name)))
        # SymbolicName defaults to the BrowseName
        symbolic_name = node.get('SymbolicName')
        self.g.add((classiri, UARDF['symbolicName'], Literal(symbolic_name if symbolic_name is not None else bn_name)))

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
        except Exception:
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
            identifierType = self.rdf_ns['base']['opaqueID']
        else:
            raise ValueError(f'Unknown identifier type in NodeId: {nodeid}')
        identifier = str(i_part.split('=', 1)[1])
        return ns_index, identifier, identifierType

    def add_uadatatype(self, node):
        nid, index, name, bn_index, idtype = self.get_nid_ns_and_name(node)
        rdf_namespace = self.get_rdf_ns_from_ua_index(index)
        bn_namespace = self.get_rdf_ns_from_ua_index(bn_index)
        if bn_namespace != rdf_namespace:
            print(f'Warning: BrowseName namespace differs from NodeId namespace for datatype {name}')
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
                    # Named after the field and its value, not a random id: the
                    # same NodeSet gives the same ontology, so a KMS package
                    # built from it has the same digest (gh-944-opcua-kms-package).
                    # The type is part of the key: equal fields of different
                    # enums keep one value node each.
                    value_key = hashlib.sha256(f'{typeIri}|{itemname}|{int(value)}'.encode()).hexdigest()[:32]
                    bbnode = self.rdf_ns['base']['_' + value_key]
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
        def get_single_value(item_node):
            tag = item_node.tag
            basic_type_found = bool([ele for ele in basic_types if (ele in tag)])
            basic_json_type = None
            if basic_type_found:
                basic_json_type = [value for key, value in basic_types_map.items() if key in tag][0]
            if basic_type_found:
                data = self.data_schema.to_dict(item_node, namespaces=xml_ns, indent=4)
                if '$' in data:
                    result = data["$"]
                    result = utils.convert_to_json_type(result, basic_json_type)
                    return Literal(result)
                else:
                    return None
            else:  # does it contain a complex structure
                data = self.data_schema.to_dict(item_node, namespaces=xml_ns, indent=4)
                if "}LocalizedText" in tag:
                    text = data.get('xsd:Text')
                    locale = data.get('xsd:Locale')
                    if locale is not None:
                        locale = locale.strip() or None
                    if locale is None:
                        locale = self.default_locale
                    if text is not None:
                        result = Literal(text, lang=locale)
                        return Literal(result)
                elif "}NodeId" in tag:
                    identifier = data['xsd:Identifier']
                    ns_index, node_id, idtype = self.parse_nodeid(identifier)
                    return self.node_iri(ns_index, node_id, idtype)
                else:
                    json_obj = {}
                    for k, v in data.items():
                        if "xsd:" in k:
                            json_obj[k] = v
                    if len(json_obj.keys()) > 0:
                        result = Literal(json.dumps(json_obj), datatype=RDF.JSON)
                        return Literal(result)
        result = None
        value = node.find('opcua:Value', xml_ns)
        if value is not None:
            for children in value:
                tag = children.tag
                if 'ListOf' in tag:
                    # figure out the element tag (e.g. 'ListOfString' → 'String')
                    items = []
                    for item_node in children:
                        # if it's a primitive type, extract its literal value
                        result = get_single_value(item_node)
                        if result is not None:
                            items.append(result)
                    # create an RDF list of Python objects (literals or JSON-serialized)
                    created_list = utils.create_list(
                        self.g,
                        [Literal(json.dumps(elem)) if isinstance(elem, dict) else elem for elem in items],
                        None
                    )
                    self.g.add((classiri, self.rdf_ns['base']['hasValueList'], created_list))
                else:
                    result = get_single_value(children)
                    if result is not None:
                        self.g.add((classiri, self.rdf_ns['base']['hasValue'], result))

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
            except Exception:
                found_component = None
            if found_component is not None:
                componentId = self.resolve_alias(reference.text)
                index, id, idtype = self.parse_nodeid(componentId)
                targetclassiri = self.node_iri(index, id, idtype)
                if targetclassiri is None:  # not exported dynamic node
                    continue
                if isforward != 'false':
                    self.g.add((classiri, reftype_ns[found_component], targetclassiri))
                else:
                    self.g.add((targetclassiri, reftype_ns[found_component], classiri))
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
                    # uardf:hasTypeDefinition is the instantiation intent of OPC UA, not the real
                    # instantiation (rdf:type) of e.g. JSON-LD instances
                    type_predicate = RDF.type if self.enforce_opcua_type_semantic else UARDF['hasTypeDefinition']
                    self.g.add((classiri, type_predicate, self.typeIds[typedef_index][typedef_id]))
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
        classiri = self.node_iri(index, id, idtype)
        if classiri is None:  # not exported dynamic node
            return
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
        classiri = self.node_iri(index, id, idtype)
        if classiri is None:  # not exported dynamic node
            return
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
                    except Exception:
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
                    except Exception:
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
                    except Exception:
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
                    except Exception:
                        print(f"Warning: Cannot read access_level value {access_level_ex} in node {classiri}")

    @staticmethod
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
                subtype_index, subtype_id, _ = self.parse_nodeid(nodeid)
                typeiri = self.typeIds[subtype_index][subtype_id]
                if (isforward == 'false'):
                    if not node.tag.endswith("UAReferenceType"):
                        self.g.add((br_namespace[browsename], RDFS.subClassOf, typeiri))
                    else:
                        self.g.add((br_namespace[browsename], RDFS.subPropertyOf, typeiri))
                    mandatory_typedef_found = True
                else:
                    if not node.tag.endswith("UAReferenceType"):
                        self.g.add((typeiri, RDFS.subClassOf, br_namespace[browsename]))
                    else:
                        self.g.add((typeiri, RDFS.subPropertyOf, br_namespace[browsename]))
        if not mandatory_typedef_found and ref_id != baseObjectTypeId and ref_id != referencesId and \
                ref_id != baseDataTypeId and ref_id != baseVariableType:
            print(f"Error: Objecttype {ref_classiri} has no supertype and is not the base object type.")
            sys.exit(1)

    def add_type_name_only(self, node):
        _, browsename = self.getBrowsename(node)
        nodeid = node.get('NodeId')
        ref_index, ref_id, idtype = self.parse_nodeid(nodeid)
        ref_namespace = self.get_rdf_ns_from_ua_index(ref_index)
        ref_classiri = self.node_iri(ref_index, ref_id, idtype)
        isAbstract = node.get('IsAbstract')
        br_namespace = ref_namespace
        if isAbstract is not None and ref_classiri is not None:
            self.g.add((ref_classiri, UARDF['isAbstract'], Literal(isAbstract.strip().lower() == 'true')))
        self.typeIds[ref_index][ref_id] = br_namespace[browsename]
        if ref_classiri is not None:
            self.g.add((ref_classiri, UARDF['definesType'], br_namespace[browsename]))
        if not node.tag.endswith("UAReferenceType"):
            self.g.add((ref_namespace[browsename], RDF.type, OWL.Class))
        else:
            self.known_references.append((Literal(ref_id), ref_namespace, Literal(browsename)))
            self.g.add((ref_namespace[browsename], RDF.type, OWL.ObjectProperty))

    def add_type(self, node):
        _, browsename = self.getBrowsename(node)
        nodeid = node.get('NodeId')
        ref_index, ref_id, idtype = self.parse_nodeid(nodeid)
        ref_namespace = self.get_rdf_ns_from_ua_index(ref_index)
        ref_classiri = self.node_iri(ref_index, ref_id, idtype)
        try:
            references_node = node.find('opcua:References', self.xml_ns)
            references = references_node.findall('opcua:Reference', self.xml_ns)
        except Exception:
            references = []
        if not node.tag.endswith("UAReferenceType"):
            self.g.add((ref_namespace[browsename], RDF.type, OWL.Class))
        else:
            self.known_references.append((Literal(ref_id), ref_namespace, Literal(browsename)))
            self.g.add((ref_namespace[browsename], RDF.type, OWL.ObjectProperty))
        self.get_typedefinition_from_references(references, ref_classiri, node)
        if ref_classiri is None:  # type node declared dynamic but no server URI given
            return
        self.get_references(references, ref_classiri)
        self.get_datatype(node, ref_classiri)
        self.get_value_rank(node, ref_classiri)
        self.get_array_dimensions(node, ref_classiri)
        self.get_value(node, ref_classiri, self.xml_ns)
        return

    def get_nid_ns_and_name(self, node):
        nodeid = node.get('NodeId')
        ni_index, ni_id, idtype = self.parse_nodeid(nodeid)
        bn_index, bn_name = self.getBrowsename(node)
        index = ni_index
        return ni_id, index, bn_name, bn_index, idtype

    def scan_aliases(self, alias_nodes):
        for alias in alias_nodes:
            name = alias.get('Alias')
            nodeid = alias.text
            self.aliases[name] = nodeid

    def getBrowsename(self, node):
        name = node.get('BrowseName')
        index = 0
        if ':' in name:
            result = name.split(':', 1)
            name = result[1]
            index = int(result[0])
        return index, name

    # Identification of nodes
    #
    # Every node is identified by its namespace URI as IRI prefix plus the base64url encoded
    # canonical ExpandedNodeId, e.g. i=31 in http://opcfoundation.org/UA/ => opcua:aT0zMQ,
    # ns=1;i=1001 in http://opcfoundation.org/UA/DI/ =>
    #     di:<base64url(nsu=http://opcfoundation.org/UA/DI/;i=1001)>.
    # Static nodes are server independent. Dynamic nodes only exist in a specific server, so their
    # ExpandedNodeId additionally contains the server URI (svu=<uri>;nsu=<uri>;i=...).
    # Whether a node is static is decided by
    # 1. the NamespaceMetadataType object of its namespace (StaticNodeIdTypes,
    #    StaticNumericNodeIdRange, StaticStringNodeIdPattern), if it decides the node's IdType,
    # 2. otherwise the general rule: type nodes and instance declarations are static,
    #    all other instance nodes are dynamic.

    def node_key(self, index, identifier, idtype):
        idt = utils.idtype2String(idtype, self.rdf_ns['base'])
        return (int(index), utils.canonical_nodeid(idt, identifier))

    def key_from_nodeid_string(self, nodeid):
        index, identifier, idtype = self.parse_nodeid(self.resolve_alias(nodeid.strip()))
        return self.node_key(index, identifier, idtype)

    def get_node_references(self, node):
        references = node.find('opcua:References', self.xml_ns)
        if references is None:
            return []
        return references.findall('opcua:Reference', self.xml_ns)

    def is_reference_of_type(self, reference, reftype_id, forward=True):
        reftype = self.resolve_alias(reference.get('ReferenceType'))
        index, id, _ = self.parse_nodeid(reftype)
        isforward = reference.get('IsForward') != 'false'
        return index == 0 and id == reftype_id and isforward == forward

    def get_value_texts(self, node):
        value = node.find('opcua:Value', self.xml_ns)
        if value is None:
            return []
        texts = []
        for child in value:
            if 'ListOf' in child.tag:
                texts += [item.text for item in child if item.text is not None]
            elif child.text is not None:
                texts.append(child.text)
        return [text.strip() for text in texts]

    def scan_namespace_metadata(self, xml_nodes):
        """Collect the static node rules of all NamespaceMetadataType objects in the nodeset."""
        self.static_node_rules = {}
        for key, obj in xml_nodes.items():
            if not obj.tag.endswith('}UAObject'):
                continue
            references = self.get_node_references(obj)
            typedef = next((ref.text for ref in references
                            if self.is_reference_of_type(ref, hasTypeDefinitionId)), None)
            if typedef is None or self.key_from_nodeid_string(typedef) != (0, f'i={namespaceMetadataTypeId}'):
                continue
            property_keys = {self.key_from_nodeid_string(ref.text) for ref in references
                             if self.is_reference_of_type(ref, hasPropertyId)}
            properties = {}
            for prop_key, prop in xml_nodes.items():
                if not prop.tag.endswith('}UAVariable'):
                    continue
                parent = prop.get('ParentNodeId')
                if prop_key in property_keys or (parent is not None and self.key_from_nodeid_string(parent) == key):
                    _, browsename = self.getBrowsename(prop)
                    properties[browsename] = self.get_value_texts(prop)
            namespace_uri = properties.get('NamespaceUri')
            if not namespace_uri:  # e.g. the <NamespaceIdentifier> placeholder
                continue
            pattern = properties.get('StaticStringNodeIdPattern')
            rule = {
                'types': {int(idtype) for idtype in properties.get('StaticNodeIdTypes', [])},
                'ranges': [utils.parse_numeric_range(r) for r in properties.get('StaticNumericNodeIdRange', [])],
                'pattern': re.compile(pattern[0]) if pattern and pattern[0] else None
            }
            namespace_uri = str(utils.normalize_namespaceuri(namespace_uri[0]))
            self.static_node_rules[namespace_uri] = rule
            print(f"Found NamespaceMetadata for {namespace_uri}: StaticNodeIdTypes={sorted(rule['types'])}, "
                  f"{len(rule['ranges'])} StaticNumericNodeIdRange(s), "
                  f"StaticStringNodeIdPattern={rule['pattern'].pattern if rule['pattern'] else None}")

    def explicit_static(self, namespace_uri, idt, identifier):
        """True/False if the NamespaceMetadata decides about the node, None otherwise."""
        rule = self.static_node_rules.get(str(utils.normalize_namespaceuri(namespace_uri)))
        if rule is None:
            return None
        if idt == 'i' and rule['ranges']:
            return any(lo <= int(identifier) <= hi for lo, hi in rule['ranges'])
        if idt == 's' and rule['pattern'] is not None:
            return rule['pattern'].fullmatch(identifier) is not None
        if idtype_enum[idt] in rule['types']:
            return True
        return None

    def haschild_reference_types(self):
        """Keys of HasChild and all its subtypes: core's, the ones of the imported ontologies (rdfs:subPropertyOf
        of the semantic bridge properties) and the ReferenceTypes of this nodeset (HasSubtype)."""
        keys = {(0, f'i={i}') for i in core_haschild_ids}
        if 'opcua' not in self.rdf_ns:
            return keys
        haschild = self.rdf_ns['opcua']['HasChild']
        for node, prop in self.ig.subject_objects(UARDF['definesType']):
            if (node, RDF.type, UARDF['ReferenceType']) not in self.ig or \
                    haschild not in set(self.ig.transitive_objects(prop, RDFS.subPropertyOf)):
                continue
            nodeid = self.ig.value(node, UARDF['nodeId'])
            if nodeid is None:
                continue
            _, nsu, idt, identifier = utils.parse_expanded_nodeid(nodeid)
            index = self.namespace_index(nsu or self.opcua_ns_raw[0])
            if index is not None:
                keys.add((index, utils.canonical_nodeid(idt, identifier)))
        supertypes = {}
        for node in self.root:
            if node.tag.endswith('}UAReferenceType'):
                key = self.key_from_nodeid_string(node.get('NodeId'))
                for ref in self.get_node_references(node):
                    if self.is_reference_of_type(ref, hasSubtypeId, forward=False):
                        supertypes[key] = self.key_from_nodeid_string(ref.text)
        changed = True
        while changed:
            changed = False
            for key, supertype in supertypes.items():
                if key not in keys and supertype in keys:
                    keys.add(key)
                    changed = True
        return keys

    def namespace_index(self, namespace_uri):
        normalized = str(utils.normalize_namespaceuri(namespace_uri))
        for index, uri in enumerate(self.opcua_ns_raw):
            if str(utils.normalize_namespaceuri(uri)) == normalized:
                return index
        return None

    def is_haschild_reference(self, reference, forward=True):
        """True if the reference is a HasChild (or subtype) reference in the given direction."""
        if (reference.get('IsForward') != 'false') != forward:
            return False
        keys = getattr(self, 'haschild_keys', None) or {(0, f'i={i}') for i in core_haschild_ids}
        return self.key_from_nodeid_string(reference.get('ReferenceType')) in keys

    def get_parent_key(self, node):
        """HasChild parent of a node: ParentNodeId, otherwise the source of an inverse HasChild reference."""
        parent = node.get('ParentNodeId')
        if parent is not None:
            return self.key_from_nodeid_string(parent)
        for ref in self.get_node_references(node):
            if self.is_haschild_reference(ref, forward=False) and \
                    not self.is_reference_of_type(ref, hasSubtypeId, forward=False):
                return self.key_from_nodeid_string(ref.text)
        return None

    def children_of_nodes(self, xml_nodes):
        """Parent key -> keys of its HasChild children of this nodeset (ParentNodeId or HasChild references in
        either direction, without HasSubtype). The parent may be a node of another nodeset."""
        children = {}
        for key, node in xml_nodes.items():
            parent = self.get_parent_key(node)
            if parent is not None:
                children.setdefault(parent, set()).add(key)
            for ref in self.get_node_references(node):
                if self.is_haschild_reference(ref) and not self.is_reference_of_type(ref, hasSubtypeId):
                    target = self.key_from_nodeid_string(ref.text)
                    if target in xml_nodes:
                        children.setdefault(key, set()).add(target)
        return children

    def is_type_node(self, key, xml_nodes):
        node = xml_nodes.get(key)
        if node is not None:
            return node.tag.split('}')[-1] in type_tags
        index, canonical = key
        try:
            return canonical.split('=', 1)[1] in self.typeIds[index]  # type of an imported namespace
        except IndexError:
            return False

    def is_instance_declaration(self, key, xml_nodes):
        """Instance node which is part of a type definition: it has a ModellingRule or its parent
        is a type or an instance declaration."""
        visited = set()
        while key is not None and key not in visited:
            visited.add(key)
            node = xml_nodes.get(key)
            if node is None or node.tag.split('}')[-1] not in instance_tags:
                return False
            if any(self.is_reference_of_type(ref, hasModellingRuleId) for ref in self.get_node_references(node)):
                return True
            key = self.get_parent_key(node)
            if key is not None and self.is_type_node(key, xml_nodes):
                return True
        return False

    def get_typedefinition_id(self, node):
        """Numeric identifier of the core TypeDefinition of an xml node, None if it has none in namespace 0."""
        typedef = next((ref.text for ref in self.get_node_references(node)
                        if self.is_reference_of_type(ref, hasTypeDefinitionId)), None)
        if typedef is None:
            return None
        index, canonical = self.key_from_nodeid_string(typedef)
        return canonical.split('=', 1)[1] if index == 0 and canonical.startswith('i=') else None

    def variables_of_nodes(self, xml_nodes):
        """Parent key -> keys of its HasChild children which are Variables. The parent may be a node of another
        nodeset."""
        result = {}
        for parent, children in self.children_of_nodes(xml_nodes).items():
            variables = {c for c in children if xml_nodes[c].tag.endswith('}UAVariable')}
            if variables:
                result[parent] = variables
        return result

    def is_foreign_instance(self, key):
        """True if a node of another nodeset is an instance (no type, no instance declaration, no definition
        node). Nodes which the static export of an imported namespace does not contain are dynamic instances."""
        index, canonical = key
        if index >= len(self.nodeIds) or index not in self.imported_namespace_indices:
            return False  # nothing known about it
        iri = self.nodeIds[index].get(canonical.split('=', 1)[1])
        if iri is None:
            return True
        if not any((iri, RDF.type, UARDF[nodeclass]) in self.ig for nodeclass in ('Object', 'Variable')):
            return False
        typedef = self.ig.value(iri, UARDF['hasTypeDefinition'])
        if typedef is not None and str(typedef) in {str(self.rdf_ns['opcua'][name])
                                                    for name in definition_types.values()}:
            return False
        node, visited = iri, set()
        while node is not None and node not in visited:  # instance declaration: below a type or with rule
            visited.add(node)
            if (node, UARDF['definesType'], None) in self.ig or \
                    (node, self.rdf_ns['opcua']['HasModellingRule'], None) in self.ig:
                return False
            node = self.ig.value(node, UARDF['parent'])
        return True

    def typedef_key(self, node):
        """Key of the TypeDefinition of an xml node, None if it has none."""
        typedef = next((ref.text for ref in self.get_node_references(node)
                        if self.is_reference_of_type(ref, hasTypeDefinitionId)), None)
        return self.key_from_nodeid_string(typedef) if typedef is not None else None

    def is_definition_type(self, key, xml_nodes):
        """True if the type (key) is or derives from a definition type (definition_types),
        resolved via the supertypes of this nodeset (HasSubtype) and of the imported ontologies (rdfs:subClassOf)."""
        cache = self.__dict__.setdefault('_definition_type_cache', {})
        if key is None:
            return False
        if key not in cache:
            cache[key] = False  # cycle guard
            index, canonical = key
            if index == 0 and canonical[2:] in definition_types:
                cache[key] = True
            elif key in xml_nodes:
                supertype = next((self.key_from_nodeid_string(ref.text)
                                  for ref in self.get_node_references(xml_nodes[key])
                                  if self.is_reference_of_type(ref, hasSubtypeId, forward=False)), None)
                cache[key] = self.is_definition_type(supertype, xml_nodes)
            elif index < len(self.nodeIds):
                node = self.nodeIds[index].get(canonical.split('=', 1)[1])
                cls = self.ig.value(node, UARDF['definesType']) if node is not None else None
                for supertype in (self.ig.objects(cls, RDFS.subClassOf) if cls is not None else ()):
                    supernode = self.ig.value(predicate=UARDF['definesType'], object=supertype)
                    nodeid = self.ig.value(supernode, UARDF['nodeId']) if supernode is not None else None
                    if nodeid is None:
                        continue
                    _, nsu, idt, identifier = utils.parse_expanded_nodeid(nodeid)
                    superindex = self.namespace_index(nsu or self.opcua_ns_raw[0])
                    if superindex is not None and \
                            self.is_definition_type((superindex, utils.canonical_nodeid(idt, identifier)), xml_nodes):
                        cache[key] = True
        return cache[key]

    def node_label(self, key, xml_nodes):
        node = xml_nodes.get(key)
        nodeid = f'nsu={self.opcua_ns_raw[key[0]]};{key[1]}'
        return f'{self.getBrowsename(node)[1]} ({nodeid})' if node is not None else nodeid

    def instances_with_variables(self, xml_nodes):
        """R1 (instance-with-Variables override): an instance which has Variables is server specific, so the instance
        and its Variables are dynamic (adding Variables to an instance expresses the intention of server specific
        data).

        Instances are Objects and Variables which are neither types nor instance declarations; instances of the
        definition types are excluded. The parent may be an instance of another nodeset (e.g. DI's
        MaxInactiveLockTime below core's ServerCapabilities), then only its Variables of this nodeset are classified.
        Returns key -> reason.
        """
        result = {}
        for parent, variables in self.variables_of_nodes(xml_nodes).items():
            node = xml_nodes.get(parent)
            if node is not None:
                if node.tag.split('}')[-1] not in ('UAObject', 'UAVariable') or \
                        self.is_instance_declaration(parent, xml_nodes) or \
                        self.is_definition_type(self.typedef_key(node), xml_nodes):
                    continue
                result.setdefault(parent, 'R1: instance with Variables')
            elif not self.is_foreign_instance(parent):
                continue
            for variable in variables:
                # a Variable of an instance belongs to the instance, even if it (wrongly) has a ModellingRule
                if self.is_definition_type(self.typedef_key(xml_nodes[variable]), xml_nodes):
                    continue
                result.setdefault(variable, f'R1: Variable of instance {self.node_label(parent, xml_nodes)}')
        return result

    def classify_with_heuristics(self, xml_nodes):
        """key -> (static, formally static, reason of a difference).

        The first matching rule decides, in the order R1, R3, R4, R5:
          override (heuristic, it overrules R3):
          R1 instance-with-Variables override: an instance which has Variables is dynamic together with its
             Variables, except definition nodes.
          standard rule:
          R3 NamespaceMetadata rule: the NamespaceMetadata of the namespace decides.
          fallbacks (only where R3 does not decide):
          R4 definition fallback (heuristic): definition nodes - instances of the definition types (definition_types
             and their subtypes) and the Variables of the type dictionaries - are static.
          R5 default fallback (standard): types and instance declarations are static, instances dynamic.
        --strict-classification keeps the standard rules R3 and R5 only. R1 considers HasChild (and its subtypes):
        Organizes (or any other reference which is not HasChild) never influences the classification.
        """
        formal = {key: self.is_static_node(key, node, xml_nodes) for key, node in xml_nodes.items()}
        if self.strict_classification:
            return {key: (static, static, None) for key, static in formal.items()}
        rule1 = self.instances_with_variables(xml_nodes)
        result = {}

        def tag(key):
            return xml_nodes[key].tag.split('}')[-1]

        def is_definition(key):
            return self.is_definition_type(self.typedef_key(xml_nodes[key]), xml_nodes)

        def is_typesystem_variable(key, seen=()):
            node = xml_nodes[key]
            if self.get_typedefinition_id(node) in typesystem_variable_types:
                return True
            parent = self.get_parent_key(node)
            return parent in xml_nodes and parent not in seen and tag(parent) == 'UAVariable' and \
                is_typesystem_variable(parent, set(seen) | {key})

        for key in xml_nodes:
            static = formal[key]
            reason = None
            index, canonical = key
            idt, identifier = canonical.split('=', 1)
            undecided = self.explicit_static(self.opcua_ns[index], idt, identifier) is None
            if key in rule1:
                static, reason = False, rule1[key]
            elif undecided and not static and tag(key) in instance_tags:
                if tag(key) in ('UAObject', 'UAView') and is_definition(key):
                    static, reason = True, 'R4: definition node (fallback)'
                elif tag(key) == 'UAVariable' and is_typesystem_variable(key):
                    static, reason = True, 'R4: Variable of a type dictionary (fallback)'
            result[key] = (static, formal[key], reason if static != formal[key] else None)
        return result

    def is_static_node(self, key, node, xml_nodes):
        index, canonical = key
        idt, identifier = canonical.split('=', 1)
        explicit = self.explicit_static(self.opcua_ns[index], idt, identifier)
        if explicit is not None:
            return explicit
        if node.tag.split('}')[-1] in type_tags:
            return True
        return self.is_instance_declaration(key, xml_nodes)

    def classify_nodes(self):
        """Decide for all nodes of the nodeset whether they are static or dynamic and assign their IRIs.

        Dynamic nodes are not exported when no server URI is given.
        """
        xml_nodes = {}
        for node in self.root:
            if node.tag.split('}')[-1] in instance_tags + type_tags:
                xml_nodes[self.key_from_nodeid_string(node.get('NodeId'))] = node
        self.scan_namespace_metadata(xml_nodes)
        self.haschild_keys = self.haschild_reference_types()
        self.static_nodes = set()
        self.heuristic_overrides = {}
        classification = self.classify_with_heuristics(xml_nodes)
        for key, node in xml_nodes.items():
            index, canonical = key
            prefix = self.get_rdf_ns_from_ua_index(index)
            static, formal, reason = classification[key]
            if static != formal:
                self.heuristic_overrides[key] = reason
            if static:
                self.static_nodes.add(key)
                expanded_nodeid = utils.expanded_nodeid_string(canonical, self.opcua_ns_raw[index])
            elif self.server_uri is not None:
                expanded_nodeid = utils.expanded_nodeid_string(canonical, self.opcua_ns_raw[index], self.server_uri)
            else:
                expanded_nodeid = None
            if expanded_nodeid is not None:
                self.expanded_nodeids[key] = expanded_nodeid
                self.node_iris[key] = utils.expanded_nodeid_to_iri(prefix, expanded_nodeid)
            else:
                self.node_iris[key] = None
                self.skipped_dynamic_nodes.append((self.opcua_ns_raw[index], canonical, node.get('BrowseName')))
        dynamic_count = len(xml_nodes) - len(self.static_nodes)
        print(f"Identified {len(self.static_nodes)} static and {dynamic_count} dynamic nodes.")
        if self.heuristic_overrides:
            to_dynamic = sum(1 for k in self.heuristic_overrides if k not in self.static_nodes)
            print(f"Heuristics: {len(self.heuristic_overrides)} node(s) classified differently than the standard "
                  f"rules: {to_dynamic} static -> dynamic, {len(self.heuristic_overrides) - to_dynamic} dynamic -> "
                  "static (--strict-classification disables the heuristics).")
        self.xml_nodes = xml_nodes
        if self.skipped_dynamic_nodes:
            print(f"Warning: No server URI given (--serverUri). {len(self.skipped_dynamic_nodes)} dynamic node(s) "
                  "and references to them are not exported:")
            for namespace_uri, canonical, browsename in self.skipped_dynamic_nodes[:20]:
                print(f"  - nsu={namespace_uri};{canonical} ({browsename})")
            if len(self.skipped_dynamic_nodes) > 20:
                print(f"  ... and {len(self.skipped_dynamic_nodes) - 20} more")

    def write_classification_report(self, filename):
        """TSV of the nodes which the heuristics classify differently than the standard rules (NamespaceMetadata,
        otherwise types and instance declarations static, instances dynamic)."""
        with open(filename, 'w') as f:
            f.write('NodeId\tBrowseName\tNodeClass\tTypeDefinition\tStandard\tClassification\tReason\n')

            def order(item):
                idt, identifier = item[0][1].split('=', 1)
                return (item[0][0], idt, int(identifier) if idt == 'i' else 0, identifier)
            for key, reason in sorted(self.heuristic_overrides.items(), key=order):
                node = self.xml_nodes[key]
                _, browsename = self.getBrowsename(node)
                typedef = next((ref.text for ref in self.get_node_references(node)
                                if self.is_reference_of_type(ref, hasTypeDefinitionId)), '')
                classification = 'static' if key in self.static_nodes else 'dynamic'
                standard = 'dynamic' if classification == 'static' else 'static'
                f.write(f'nsu={self.opcua_ns_raw[key[0]]};{key[1]}\t{browsename}\t'
                        f'{node.tag.split("}")[-1][2:]}\t{self.resolve_alias(typedef) if typedef else ""}\t'
                        f'{standard}\t{classification}\t{reason}\n')

    def node_iri(self, index, identifier, idtype):
        """IRI of a node, None if it is a dynamic node which is not exported."""
        key = self.node_key(index, identifier, idtype)
        if key in self.node_iris:
            return self.node_iris[key]
        try:
            imported = self.nodeIds[key[0]].get(str(identifier))
        except IndexError:
            imported = None
        if imported is not None:
            if (imported, UARDF['serverUri'], None) in self.ig:  # imported ontology was built with server URI
                self.foreign_dynamic_iris.add(imported)
            return imported
        if key[0] not in self.imported_namespace_indices:
            # Its namespace is not exported by any imported ontology (e.g. a nodeset which defines only a
            # part of a namespace): nothing is known about the node, it is assumed to be static.
            return utils.expanded_nodeid_to_iri(self.get_rdf_ns_from_ua_index(key[0]),
                                                utils.expanded_nodeid_string(key[1], self.opcua_ns_raw[key[0]]))
        # Neither defined here nor exported by the imported ontology of its namespace. That (static) export
        # contains all static nodes, so it is a dynamic node (or missing). With a server URI it can be
        # identified as dynamic node of this server, otherwise references to it cannot be exported.
        if self.server_uri is not None:
            iri = utils.expanded_nodeid_to_iri(
                self.get_rdf_ns_from_ua_index(key[0]),
                utils.expanded_nodeid_string(key[1], self.opcua_ns_raw[key[0]], self.server_uri))
            if key not in self.unknown_nodes:
                self.unknown_nodes.add(key)
                self.foreign_dynamic_iris.add(iri)
                print(f"Note: Node nsu={self.opcua_ns_raw[key[0]]};{key[1]} is not exported by the imported "
                      "ontologies, it is referenced as dynamic node of the given server URI.")
            return iri
        if key not in self.unknown_nodes:
            self.unknown_nodes.add(key)
            print(f"Warning: Node nsu={self.opcua_ns_raw[key[0]]};{key[1]} is neither defined in the nodeset nor "
                  "exported by the imported ontologies (dynamic node?). References to it are not exported.")
        return None

    @staticmethod
    def dynamic_ontology_iri(iri, server_uri):
        """IRI of the dynamic export of the ontology iri for one server: the (normalized) iri plus the base64url
        encoding of 'svu=<server_uri>', like a node IRI. It cannot collide with a node IRI, since 'svu=<server>'
        alone is no NodeId, and the dynamic exports of different servers get different IRIs."""
        return utils.expanded_nodeid_to_iri(utils.normalize_namespaceuri(iri), f'svu={server_uri}')

    def restrict_to_dynamic_nodes(self, dynamic_imports=()):
        """Keep only the server specific part of the graph.

        Kept are all triples about dynamic nodes, including references between static and dynamic nodes,
        the RDF lists they use, the declarations of the properties they need and the ontology header.
        The export without server URI contains exactly the rest, so both together compose the full export.
        The header gets its own ontology IRI (and versionIRI) of the server, so that the static export and the
        dynamic exports of one or more servers can be loaded together; dynamic_imports are added as owl:imports
        (e.g. the static export of the same nodeset and the dynamic exports of its dependencies).
        """
        dynamic = {iri for key, iri in self.node_iris.items() if iri is not None and key not in self.static_nodes}
        dynamic |= self.foreign_dynamic_iris
        keep = {(s, p, o) for s, p, o in self.g if s in dynamic or o in dynamic}
        # RDF lists and other blank node structures used by the kept triples
        frontier = [o for _, _, o in keep if isinstance(o, BNode)]
        while frontier:
            bnode = frontier.pop()
            for s, p, o in self.g.triples((bnode, None, None)):
                if (s, p, o) not in keep:
                    keep.add((s, p, o))
                    if isinstance(o, BNode):
                        frontier.append(o)
        # e.g. semantic bridge properties which are only used by references of dynamic nodes
        for p in {p for _, p, _ in keep}:
            keep.update(self.g.triples((p, RDFS.subPropertyOf, None)))
            keep.update(self.g.triples((p, RDF.type, None)))
        # ontology header and namespace declaration
        keep.update(self.g.triples((self.ontology_name, None, None)))
        for namespace in self.g.subjects(RDF.type, self.rdf_ns['base']['Namespace']):
            keep.update(self.g.triples((namespace, None, None)))
        removed = 0
        for triple in list(self.g):
            if triple not in keep:
                self.g.remove(triple)
                removed += 1
        dynamic_ontology = self.dynamic_ontology_iri(self.ontology_name, self.server_uri)
        for _, p, o in list(self.g.triples((self.ontology_name, None, None))):
            self.g.remove((self.ontology_name, p, o))
            if p == OWL.versionIRI:
                o = self.dynamic_ontology_iri(o, self.server_uri)
            self.g.add((dynamic_ontology, p, o))
        self.g.add((dynamic_ontology, RDFS.comment,
                    Literal(f'Server specific (dynamic) part of {self.ontology_name} for server {self.server_uri}')))
        for ontology in dynamic_imports:
            self.g.add((dynamic_ontology, OWL.imports, utils.file_path_to_uri(ontology)))
        print(f"Dynamic only: kept {len(keep)} triples of {len(dynamic)} dynamic nodes "
              f"({len(self.foreign_dynamic_iris)} of other nodesets), removed {removed} triples.")

    def write_graph(self, filename):
        self.g.serialize(destination=filename)
