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

import unittest
from unittest.mock import patch, MagicMock
from rdflib import Graph, URIRef, Literal, Namespace, BNode
from lib.nodesetparser import NodesetParser
from rdflib.namespace import RDF, OWL, RDFS
import xml.etree.ElementTree as ET  # Import ElementTree as ET

class TestNodesetParser(unittest.TestCase):

    @patch('lib.nodesetparser.NodesetParser.__init__')
    def setUp(self, mock_init):
        # Mock the constructor to do nothing
        mock_init.return_value = None
        
        # Manually create the parser instance and set necessary attributes
        self.parser = NodesetParser(None, None, None, None, None, None)
        self.parser.g = Graph()  # Initialize the RDF graph
        self.parser.ig = Graph()  # Initialize the imported graph
        self.parser.rdf_ns = {
            'base': Namespace('http://example.com/base#'), 
            'opcua': Namespace('http://opcua.namespace.com/')
        }  # RDF namespace dictionary
        self.parser.nodeIds = [{}]  # Initialize nodeIds list with an empty dict
        self.parser.typeIds = [{}]  # Initialize typeIds list with an empty dict
        self.parser.known_references = []
        self.parser.xml_ns = {
            'opcua': 'http://opcfoundation.org/UA/2011/03/UANodeSet.xsd',
            'xsd': 'http://opcfoundation.org/UA/2008/02/Types.xsd'
        }
        self.parser.ontology_name = URIRef("http://my.ontology/")
        self.parser.versionIRI = URIRef("http://version.iri/")
        self.parser.opcua_ns = ['http://example.com/ns1', 'http://example.com/ns2']  # Sample opcua namespaces
        self.parser.urimap = {
            'http://example.com/ns1': 1,
            'http://example.com/ns2': 2
        }  # Map namespace URIs to indices
        self.parser.known_opcua_ns = {
            'http://testnamespace.org/': 'myprefix'
        }
        self.parser.known_ns_classes = {
            'http://testnamespace.org/': URIRef('http://testnamespace.org/Namespace')
        }
        self.parser.imported_ontologies = [URIRef('http://example.com/importedOntology')]

    @patch('urllib.request.urlopen')
    @patch('xml.etree.ElementTree.parse')
    @patch('sys.exit')  # Patch sys.exit to prevent it from terminating the test
    def test_init(self, mock_exit, mock_et_parse, mock_urlopen):
        # Mock arguments
        args = MagicMock()
        args.namespace = None
        args.baseOntology = 'http://example.com/baseOntology'
        args.opcuaNamespace = 'http://example.com/opcuaNamespace'
        args.prefix = 'ex'

        opcua_nodeset = 'http://example.com/nodeset'
        opcua_inputs = 'opcua_inputs'
        version_iri = URIRef('http://example.com/versionIRI')
        data_schema = MagicMock()
        imported_ontologies = [URIRef('http://example.com/importedOntology')]

        # Mock the root.find method to simulate finding the Models element
        mock_root = MagicMock()
        mock_models_element = MagicMock()
        mock_model_element = MagicMock()
        mock_model_element.get.return_value = 'http://example.com/modelUri'
        
        mock_root.find.return_value = mock_models_element
        mock_models_element.find.return_value = mock_model_element
        mock_models_element.findall.return_value = [1]
        
        mock_et_parse.return_value.getroot.return_value = mock_root

        # Create an instance of NodesetParser
        parser = NodesetParser(args, opcua_nodeset, opcua_inputs, version_iri, data_schema, imported_ontologies)

        # Check that attributes are set correctly
        self.assertEqual(parser.known_opcua_ns['http://opcfoundation.org/UA/'], 'opcua')
        self.assertEqual(parser.rdf_ns, {})
        self.assertEqual(parser.known_ns_classes['http://opcfoundation.org/UA/'], URIRef('http://opcfoundation.org/UA/OPCUANamespace'))
        self.assertIsInstance(parser.g, Graph)
        self.assertIsInstance(parser.ig, Graph)
        self.assertEqual(parser.nodeIds, [{}])
        self.assertEqual(parser.typeIds, [{}])
        self.assertEqual(parser.opcua_ns, ['http://opcfoundation.org/UA/'])
        self.assertEqual(parser.known_references, [])
        self.assertEqual(parser.imported_ontologies, imported_ontologies)
        self.assertEqual(parser.aliases, {})
        self.assertEqual(parser.opcua_inputs, opcua_inputs)
        self.assertEqual(parser.versionIRI, version_iri)
        self.assertEqual(parser.xml_ns, {
            'opcua': 'http://opcfoundation.org/UA/2011/03/UANodeSet.xsd',
            'xsd': 'http://opcfoundation.org/UA/2008/02/Types.xsd'
        })
        self.assertEqual(parser.base_ontology, args.baseOntology)
        self.assertEqual(parser.opcua_namespace, args.opcuaNamespace)
        self.assertEqual(parser.ontology_prefix, args.prefix)

        # Check that the ontology name is set correctly when namespace is not provided
        self.assertIsInstance(parser.ontology_name, URIRef)
        self.assertTrue(str(parser.ontology_name).endswith('/'))

        # Check if XML root is correctly set
        self.assertIsNotNone(parser.root)
        self.assertEqual(parser.data_schema, data_schema)

        # Assert that sys.exit was not called
        mock_exit.assert_not_called()

    @patch('lib.nodesetparser.ET.parse')
    @patch('lib.nodesetparser.urllib.request.urlopen')
    @patch('lib.nodesetparser.NodesetParser.add_uadatatype')
    @patch('lib.nodesetparser.NodesetParser.add_typedef')
    @patch('lib.nodesetparser.NodesetParser.add_type')
    @patch('lib.nodesetparser.NodesetParser.add_uanode')
    @patch('lib.nodesetparser.NodesetParser.scan_aliases')
    @patch('lib.nodesetparser.NodesetParser.create_header')
    @patch('lib.nodesetparser.NodesetParser.init_nodeids')
    @patch('lib.nodesetparser.NodesetParser.create_prefixes')
    @patch('lib.nodesetparser.NodesetParser.add_datatype_dependent')
    def test_parse(self, mock_add_datatype_dependent, mock_create_prefixes, mock_init_nodeids, mock_create_header, mock_scan_aliases,
                   mock_add_uanode, mock_add_type, mock_add_typedef, mock_add_uadatatype,
                   mock_urlopen, mock_et_parse):
        
        # Mock the XML parsing
        mock_tree = MagicMock()
        mock_et_parse.return_value = mock_tree
        mock_root = MagicMock()
        mock_tree.getroot.return_value = mock_root

        # Mock the URL open return value
        mock_urlopen.return_value.__enter__.return_value = MagicMock()

        # Set up the parser instance
        parser = NodesetParser(MagicMock(), "dummy_nodeset", None, None, None, None)

        # Mock the XML root and its findall method
        parser.root = mock_root

        # Define a mock return value for findall for each node class
        mock_uadatatype_nodes = [MagicMock() for _ in range(2)]
        mock_uaobject_nodes = [MagicMock() for _ in range(3)]
        mock_uavariable_nodes = [MagicMock() for _ in range(4)]
        mock_uamethod_nodes = [MagicMock() for _ in range(1)]
        
        # Configure the return values for findall based on tag names
        parser.root.findall.side_effect = lambda tag_name, _: {
            'opcua:UADataType': mock_uadatatype_nodes,
            'opcua:UAObject': mock_uaobject_nodes,
            'opcua:UAVariable': mock_uavariable_nodes,
            'opcua:UAMethod': mock_uamethod_nodes
        }.get(tag_name, [])

        # Call the parse method
        parser.parse()

        # Verify that create_prefixes was called
        mock_create_prefixes.assert_called_once_with(parser.namespace_uris, parser.base_ontology, parser.opcua_namespace)
        
        # Verify that init_nodeids was called
        mock_init_nodeids.assert_called_once_with(parser.opcua_inputs, parser.ontology_name, parser.ontology_prefix)
        
        # Verify that create_header was called
        mock_create_header.assert_called_once()

        # Verify that scan_aliases was called if aliases_node exists
        if parser.root.find('opcua:Aliases', parser.xml_ns):
            mock_scan_aliases.assert_called_once()

        # Verify that add_uanode was called for each node class type in all_nodeclasses
        expected_calls = len(mock_uadatatype_nodes) + len(mock_uaobject_nodes) + len(mock_uavariable_nodes) + len(mock_uamethod_nodes)
        self.assertEqual(mock_add_uanode.call_count, expected_calls)

        # Verify that add_type was called for each type node class in type_nodeclasses
        expected_type_calls = len(mock_uadatatype_nodes)
        self.assertEqual(mock_add_type.call_count, expected_type_calls)

        # Verify that add_typedef was called for typed node classes
        expected_typed_calls = len(mock_uavariable_nodes) + len(mock_uaobject_nodes)
        self.assertEqual(mock_add_typedef.call_count, expected_typed_calls)

        expected_typed_calls = len(mock_uavariable_nodes)
        self.assertEqual(mock_add_datatype_dependent.call_count, expected_typed_calls)

        # Verify that add_uadatatype was called for each UADataType node
        self.assertEqual(mock_add_uadatatype.call_count, len(mock_uadatatype_nodes))

    @patch('lib.nodesetparser.Graph.query')
    def test_get_all_node_ids(self, mock_query):
        # Mock the RDF query result
        query_result = [
            (Literal('node1'), URIRef('http://example.com/ns1'), URIRef('http://example.com/device1')),
            (Literal('node2'), URIRef('http://example.com/ns2'), URIRef('http://example.com/device2'))
        ]
        mock_query.return_value = query_result

        # Call the method to be tested
        self.parser.get_all_node_ids()

        # Check if nodeIds were correctly populated
        expected_node_ids = [
            {'node1': URIRef('http://example.com/device1')},
            {'node2': URIRef('http://example.com/device2')},
            {}
        ]

        # Assert that the nodeIds list matches the expected output
        self.assertEqual(self.parser.nodeIds, expected_node_ids)

    @patch('lib.nodesetparser.Graph.query')
    def test_get_all_types(self, mock_query):
        # Mock the RDF query result for get_all_types
        query_result = [
            (Literal('type1'), URIRef('http://example.com/ns1'), URIRef('http://example.com/type1')),
            (Literal('type2'), URIRef('http://example.com/ns2'), URIRef('http://example.com/type2'))
        ]
        mock_query.return_value = query_result
        self.parser.typeIds.append({})
        self.parser.typeIds.append({})
        # Call the method to be tested
        self.parser.get_all_types()

        # Check if typeIds were correctly populated
        expected_type_ids = [
            {},
            {'type1': URIRef('http://example.com/type1')},
            {'type2': URIRef('http://example.com/type2')},
        ]

        # Assert that the typeIds list matches the expected output
        self.assertEqual(self.parser.typeIds, expected_type_ids)

    @patch('lib.nodesetparser.Graph.query')
    def test_get_all_references(self, mock_query):
        # Mock the RDF query result for get_all_references
        query_result = [
            (Literal('ref1'), URIRef('http://example.com/ns1'), Literal('name1')),
            (Literal('ref2'), URIRef('http://example.com/ns2'), Literal('name2'))
        ]
        mock_query.return_value = query_result

        # Call the method to be tested
        self.parser.get_all_references()

        # Check if known_references were correctly populated
        expected_references = [
            (Literal('ref1'), URIRef('http://example.com/ns1'), Literal('name1')),
            (Literal('ref2'), URIRef('http://example.com/ns2'), Literal('name2'))
        ]

        # Assert that the known_references list matches the expected output
        self.assertEqual(self.parser.known_references, expected_references)

    @patch('lib.nodesetparser.Graph.query')
    def test_get_all_namespaces(self, mock_query):
        # Mock the RDF query result for get_all_namespaces
        query_result = [
            (URIRef('http://example.com/ns1'), Literal('prefix1'), URIRef('http://example.com/ns_class1')),
            (URIRef('http://example.com/ns2'), Literal('prefix2'), URIRef('http://example.com/ns_class2'))
        ]
        mock_query.return_value = query_result

        # Define the ontology prefix and name
        ontology_prefix = 'base'
        ontology_name = URIRef('http://example.com/baseOntology')
        namespace_class = 'BaseNamespace'

        # Call the method to be tested
        self.parser.get_all_namespaces(ontology_prefix, ontology_name, namespace_class)

        # Check if known_opcua_ns and known_ns_classes were correctly populated
        expected_known_opcua_ns = {
            'http://testnamespace.org/': 'myprefix',
            'http://example.com/ns1': 'prefix1',
            'http://example.com/ns2': 'prefix2',
            'http://example.com/baseOntology': 'base'
        }

        expected_known_ns_classes = {
            'http://testnamespace.org/': URIRef('http://testnamespace.org/Namespace'),
            'http://example.com/ns1': URIRef('http://example.com/ns_class1'),
            'http://example.com/ns2': URIRef('http://example.com/ns_class2'),
            'http://example.com/baseOntology': URIRef('http://example.com/baseOntologyBaseNamespace')
        }

        # Assert that the known_opcua_ns dictionary matches the expected output
        self.assertEqual(self.parser.known_opcua_ns, expected_known_opcua_ns)

        # Assert that the known_ns_classes dictionary matches the expected output
        self.assertEqual(self.parser.known_ns_classes, expected_known_ns_classes)

    def test_add_ontology_namespace(self):
        # Set up input values for the method
        ontology_prefix = 'base'
        namespace_class = 'ExampleNamespace'
        ontology_name = URIRef('http://example.com/ontology/')

        # Call the method to be tested
        self.parser.add_ontology_namespace(ontology_prefix, namespace_class, ontology_name)

        # Define the expected triples
        expected_triples = [
            (
                self.parser.rdf_ns['base'][namespace_class], 
                RDF.type, 
                self.parser.rdf_ns['base']['Namespace']
            ),
            (
                self.parser.rdf_ns['base'][namespace_class], 
                self.parser.rdf_ns['base']['hasUri'], 
                Literal(ontology_name.toPython())
            ),
            (
                self.parser.rdf_ns['base'][namespace_class], 
                self.parser.rdf_ns['base']['hasPrefix'], 
                Literal(ontology_prefix)
            )
        ]

        # Check if the graph contains the expected triples
        for triple in expected_triples:
            self.assertIn(triple, self.parser.g)

    @patch('lib.nodesetparser.NodesetParser.init_imports')
    @patch('lib.nodesetparser.NodesetParser.get_all_namespaces')
    @patch('lib.nodesetparser.NodesetParser.get_all_node_ids')
    @patch('lib.nodesetparser.NodesetParser.get_all_types')
    @patch('lib.nodesetparser.NodesetParser.get_all_references')
    @patch('lib.nodesetparser.NodesetParser.add_ontology_namespace')
    def test_init_nodeids(self, mock_ontology_namespace, mock_references, mock_types, mock_node_ids, mock_namespaces, mock_imports):
        base_ontologies = ['base_ontology1', 'base_ontology2']
        ontology_name = URIRef('http://example.com/ontology')
        ontology_prefix = 'example'

        # Call the method to be tested
        self.parser.init_nodeids(base_ontologies, ontology_name, ontology_prefix)

        # Assert that init_imports was called with the correct arguments
        mock_imports.assert_called_once_with(base_ontologies)

        # Assert that get_all_namespaces was called with the correct arguments
        mock_namespaces.assert_called_once_with(ontology_prefix, ontology_name, f"{ontology_prefix.upper()}Namespace")

        # Assert that get_all_node_ids was called
        mock_node_ids.assert_called_once()

        # Assert that get_all_types was called
        mock_types.assert_called_once()

        # Assert that get_all_references was called
        mock_references.assert_called_once()
        mock_ontology_namespace.assert_called_once()

    def test_create_header(self):
        # Call the method to be tested
        self.parser.create_header()

        # Define the expected triples
        expected_triples = [
            (self.parser.ontology_name, RDF.type, OWL.Ontology),
            (self.parser.ontology_name, OWL.versionIRI, self.parser.versionIRI),
            (self.parser.ontology_name, OWL.versionInfo, Literal(0.1)),
            (self.parser.ontology_name, OWL.imports, self.parser.imported_ontologies[0])
        ]

        # Check if the graph contains the expected triples
        for triple in expected_triples:
            self.assertIn(triple, self.parser.g)

    def test_create_prefixes(self):
        xml_node = None  # No XML node to simulate
        base = 'http://example.com/base#'
        opcua_namespace = 'http://example.com/opcua'

        # Call the method to be tested
        self.parser.create_prefixes(xml_node, base, opcua_namespace)

        # Check if rdf_ns was correctly updated
        self.assertIn('base', self.parser.rdf_ns)
        self.assertIn('opcua', self.parser.rdf_ns)

        # Assert that the base and opcua namespaces were added to rdf_ns
        self.assertEqual(str(self.parser.rdf_ns['base']), base)
        self.assertEqual(str(self.parser.rdf_ns['opcua']), opcua_namespace)

    def test_get_rdf_ns_from_ua_index(self):
        # Test when the namespace exists
        index = 1  # Corresponds to 'http://example.com/ns1'
        expected_namespace = Namespace('http://example.com/ns1')
        self.parser.rdf_ns['myprefix'] = expected_namespace
        self.parser.opcua_ns = ['http://not.selected.org/', 'http://testnamespace.org/']

        # Call the method to be tested
        result = self.parser.get_rdf_ns_from_ua_index(index)

        # Assert that the correct namespace is returned
        self.assertEqual(result, expected_namespace)


    def test_get_reference_subtype(self):
        # Mock an XML node with references
        reference_mock = MagicMock()
        reference_mock.get.side_effect = lambda x: 'HasSubtype' if x == 'ReferenceType' else 'false' if x == 'IsForward' else None
        reference_mock.text = 'ns=1;i=100'
        
        node = MagicMock()
        node.find.return_value.findall.return_value = [reference_mock]

        # Mock necessary method returns
        self.parser.nodeIds = [{}, {'100': URIRef('http://example.com/type/100')}]
        self.parser.parse_nodeid = MagicMock(return_value=(1, '100'))

        # Call the method to be tested
        result = self.parser.get_reference_subtype(node)

        # Assert that the correct subtype URI is returned
        self.assertEqual(result, URIRef('http://example.com/type/100'))


    def test_add_datatype(self):
        # Mock a node with a DataType attribute
        node = MagicMock()
        node.get.return_value = 'ns=1;i=200'  # Mock NodeId
        
        # Mock necessary method returns
        classiri = URIRef('http://example.com/classiri')
        self.parser.nodeIds = [{}, { '200': URIRef('http://example.com/datatype/200')}]
        self.parser.parse_nodeid = MagicMock(return_value=(1, '200'))

        # Call the method to be tested
        self.parser.add_datatype(node, classiri)

        # Assert that the correct triple was added to the graph
        expected_triple = (
            classiri, 
            self.parser.rdf_ns['base']['hasDatatype'], 
            URIRef('http://example.com/datatype/200')
        )
        self.assertIn(expected_triple, self.parser.g)

    def test_add_to_nodeids(self):
        # Mock a node with a NodeId attribute
        node = MagicMock()
        node.get.return_value = 'ns=1;i=300'  # Mock NodeId
        self.parser.parse_nodeid = MagicMock(return_value=(1, '300'))
        # Prepare the RDF namespace and class name
        rdf_namespace = Namespace('http://testnamespace.org/')
        name = 'TestClass'
        self.parser.nodeIds.append({})
        # Call the method to be tested
        self.parser.add_to_nodeids(rdf_namespace, name, node)

        # Assert that the nodeId was correctly added to nodeIds
        expected_iri = rdf_namespace[name]
        self.assertEqual(self.parser.nodeIds[1]['300'], expected_iri)

    def test_nodeId_to_iri(self):
        # Test for numeric ID
        namespace = Namespace('http://example.com/ns1#')
        nid = '123'
        idtype = self.parser.rdf_ns['base']['numericID']

        # Call the method to be tested
        result = self.parser.nodeId_to_iri(namespace, nid, idtype)

        # Assert that the correct IRI is returned
        expected_iri = namespace['nodei123']
        self.assertEqual(result, expected_iri)
        
        idtype = self.parser.rdf_ns['base']['stringID']
        nid = 'teststring'
        result = self.parser.nodeId_to_iri(namespace, nid, idtype)
        expected_iri = namespace['nodesteststring']
        self.assertEqual(result, expected_iri)

        idtype = self.parser.rdf_ns['base']['guidID']
        nid = '123-123-uuid'
        result = self.parser.nodeId_to_iri(namespace, nid, idtype)
        expected_iri = namespace['nodeg123-123-uuid']
        self.assertEqual(result, expected_iri)
        
        idtype = self.parser.rdf_ns['base']['opaqueID']
        nid = 'opaque'
        result = self.parser.nodeId_to_iri(namespace, nid, idtype)
        expected_iri = namespace['nodebopaque']
        self.assertEqual(result, expected_iri)

    def test_add_nodeid_to_class(self):
        # Mock a node with necessary attributes
        node = MagicMock()
        node.get.side_effect = lambda x: 'ns=1;i=400' if x == 'NodeId' else 'TestSymbolicName' if x == 'SymbolicName' else None
        self.parser.opcua_ns = ['http://not.selected.org/', 'http://testnamespace.org/']
        self.parser.nodeIds.append({})
        # Mock other necessary method returns
        self.parser.get_nid_ns_and_name = MagicMock(return_value=('400', 1, 'TestBrowseName', self.parser.rdf_ns['base']['numericID']))
        self.parser.get_rdf_ns_from_ua_index = MagicMock(return_value=Namespace('http://example.com/ns1#'))

        # Call the method to be tested
        rdf_namespace, classiri = self.parser.add_nodeid_to_class(node, 'ObjectTypeNodeClass', self.parser.xml_ns)

        # Assert that the correct triples were added to the graph
        expected_triples = [
            (classiri, self.parser.rdf_ns['base']['hasNodeId'], Literal('400')),
            (classiri, self.parser.rdf_ns['base']['hasBrowseName'], Literal('TestBrowseName')),
            (classiri, self.parser.rdf_ns['base']['hasSymbolicName'], Literal('TestSymbolicName'))
        ]
        for triple in expected_triples:
            self.assertIn(triple, self.parser.g)

    def test_add_nodeid_to_class_historizing_and_minimumsamplinginterval(self):
        # Set up mocks for get_nid_ns_and_name, get_rdf_ns_from_ua_index, and nodeId_to_iri.
        self.parser.get_nid_ns_and_name = MagicMock(return_value=('500', 1, 'TestBrowseName', self.parser.rdf_ns['base']['numericID']))
        self.parser.get_rdf_ns_from_ua_index = MagicMock(return_value=Namespace('http://example.com/ns1#'))
        self.parser.nodeId_to_iri = MagicMock(return_value=URIRef('http://example.com/ns1#500'))

        # Prepare a fake node with Historizing and MinimumSamplingInterval attributes.
        node = MagicMock()
        node.get.side_effect = lambda key: {
            'SymbolicName': 'TestSymbolicName',
            'Historizing': 'true',  # any non-empty value becomes True when converted using bool()
            'MinimumSamplingInterval': '200',
            'Symmetric': None
        }.get(key, None)
        
        # Simulate the XML find for DisplayName and Description.
        display_node = MagicMock()
        display_node.text = 'DisplayNameValue'
        description_node = MagicMock()
        description_node.text = 'TestDescription'
        def find_side_effect(tag, ns):
            if tag == 'opcua:DisplayName':
                return display_node
            elif tag == 'opcua:Description':
                return description_node
            return None
        node.find.side_effect = find_side_effect

        # Ensure that the required namespace information exists.
        self.parser.opcua_ns = ['http://unused.org/', 'http://testnamespace.org/']
        self.parser.known_ns_classes['http://testnamespace.org/'] = URIRef('http://testnamespace.org/Namespace')
        self.parser.nodeIds = [{}, {}]  # Ensure the list has an entry for index 1.
        self.parser.g = Graph()  # Reset the graph

        # Call the method.
        rdf_ns, classiri = self.parser.add_nodeid_to_class(node, 'ObjectTypeNodeClass', self.parser.xml_ns)

        # Verify that the triple for MinimumSamplingInterval is added.
        expected_triple_msi = (
            classiri, 
            self.parser.rdf_ns['base']['hasMinimumSamplingInterval'], 
            Literal(200.0)
        )
        self.assertIn(expected_triple_msi, self.parser.g)

        # Verify that the triple for Historizing is added.
        # Note: bool('true') evaluates to True in Python.
        expected_triple_hist = (
            classiri, 
            self.parser.rdf_ns['base']['isHistorizing'], 
            Literal(True)
        )
        self.assertIn(expected_triple_hist, self.parser.g)

    def test_add_nodeid_to_class_no_historizing_no_minimumsamplinginterval(self):
        # Set up mocks for get_nid_ns_and_name, get_rdf_ns_from_ua_index, and nodeId_to_iri.
        self.parser.get_nid_ns_and_name = MagicMock(return_value=('600', 1, 'TestBrowseName', self.parser.rdf_ns['base']['numericID']))
        self.parser.get_rdf_ns_from_ua_index = MagicMock(return_value=Namespace('http://example.com/ns1#'))
        self.parser.nodeId_to_iri = MagicMock(return_value=URIRef('http://example.com/ns1#600'))

        # Prepare a fake node without Historizing and MinimumSamplingInterval.
        node = MagicMock()
        node.get.side_effect = lambda key: {
            'SymbolicName': 'TestSymbolicName',
            'Historizing': None,
            'MinimumSamplingInterval': None,
            'Symmetric': None
        }.get(key, None)
        
        # Simulate the XML find for DisplayName and Description.
        display_node = MagicMock()
        display_node.text = 'DisplayNameValue'
        description_node = MagicMock()
        description_node.text = 'TestDescription'
        def find_side_effect(tag, ns):
            if tag == 'opcua:DisplayName':
                return display_node
            elif tag == 'opcua:Description':
                return description_node
            return None
        node.find.side_effect = find_side_effect

        # Ensure that the required namespace information exists.
        self.parser.opcua_ns = ['http://unused.org/', 'http://testnamespace.org/']
        self.parser.known_ns_classes['http://testnamespace.org/'] = URIRef('http://testnamespace.org/Namespace')
        self.parser.nodeIds = [{}, {}]  # Ensure the list has an entry for index 1.
        self.parser.g = Graph()  # Reset the graph

        # Call the method.
        rdf_ns, classiri = self.parser.add_nodeid_to_class(node, 'ObjectTypeNodeClass', self.parser.xml_ns)

        # Verify that no triple is added for MinimumSamplingInterval.
        for s, p, o in self.parser.g:
            self.assertNotEqual(p, self.parser.rdf_ns['base']['hasMinimumSamplingInterval'])

        # Verify that no triple is added for Historizing.
        for s, p, o in self.parser.g:
            self.assertNotEqual(p, self.parser.rdf_ns['base']['isHistorizing'])

    def test_parse_nodeid_numeric(self):
        # Test a NodeId with numeric identifier
        nodeid = "ns=1;i=123"
        
        # Call the method to be tested
        ns_index, identifier, identifierType = self.parser.parse_nodeid(nodeid)
        
        # Assert the returned values
        self.assertEqual(ns_index, 1)
        self.assertEqual(identifier, "123")
        self.assertEqual(identifierType, self.parser.rdf_ns['base']['numericID'])
        
        nodeid = "ns=12345;s=Test123==;Test123"
        
        # Call the method to be tested
        ns_index, identifier, identifierType = self.parser.parse_nodeid(nodeid)
        
        # Assert the returned values
        self.assertEqual(ns_index, 12345)
        self.assertEqual(identifier, 'Test123==;Test123')
        self.assertEqual(identifierType, self.parser.rdf_ns['base']['stringID'])
        
        nodeid = "ns=11;g=000-1111-2222-3333"
        ns_index, identifier, identifierType = self.parser.parse_nodeid(nodeid)
        
        # Assert the returned values
        self.assertEqual(ns_index, 11)
        self.assertEqual(identifier, '000-1111-2222-3333')
        self.assertEqual(identifierType, self.parser.rdf_ns['base']['guidID'])
        

    @patch.object(Graph, 'add')
    def test_add_uadatatype_with_definition(self, mock_add):
        # Mock node with necessary attributes
        node = MagicMock()
        node.get.return_value = 'ns=1;i=400'  # Mock NodeId

        # Mock definition and fields
        definition = MagicMock()
        field1 = MagicMock()
        field1.get.side_effect = lambda key: {'Name': 'Field1', 'SymbolicName': 'Sym1', 'Value': '100'}.get(key)
        field2 = MagicMock()
        field2.get.side_effect = lambda key: {'Name': 'Field2', 'SymbolicName': 'Sym2'}.get(key)
        definition.findall.return_value = [field1, field2]
        node.find.return_value = definition

        # Mock necessary method returns
        self.parser.get_rdf_ns_from_ua_index = MagicMock(return_value=Namespace('http://example.com/ns1#'))
        self.parser.parse_nodeid = MagicMock(return_value=(1, '400', self.parser.rdf_ns['base']['numericID']))
        self.parser.resolve_alias = MagicMock(side_effect=lambda x: x)

        # Mock the typeIds mapping
        self.parser.typeIds = [{}, {'400': URIRef('http://example.com/datatype/400')}]

        # Call the method to be tested
        self.parser.add_uadatatype(node)

        # Expected URIs and BNodes
        itemname1 = URIRef('http://example.com/ns1#Sym1')
        itemname2 = URIRef('http://example.com/ns1#Sym2')

        # Define the expected triples for field1
        expected_triples = [
            (itemname1, RDF.type, URIRef('http://example.com/ns1#ns=1;i=400')),
            (itemname1, self.parser.rdf_ns['base']['hasFieldName'], Literal('Sym1')),
        ]

        # Define the expected triples for field2

        # Check if the correct triples were added to the graph
        for triple in expected_triples:
            mock_add.assert_any_call(triple)

    @patch('lib.nodesetparser.utils.convert_to_json_type')
    @patch.object(Graph, 'add')
    def test_get_value(self, mock_add, mock_convert):
        # Mock node with a Value child
        node = MagicMock()
        value = MagicMock()

        # Create a mock list of children to simulate iteration
        children1 = MagicMock()
        children1.tag = 'opcua:String'
        children2 = MagicMock()
        children2.tag = 'opcua:Boolean'

        # The value.find() method should return an iterable list of children
        value.__iter__.return_value = iter([children1, children2])
        node.find.return_value = value

        # Mock the classiri URI
        classiri = URIRef('http://example.com/classiri')

        # Mock the data_schema's to_dict method to return a mock value
        self.parser.data_schema = MagicMock()
        self.parser.data_schema.to_dict.side_effect = [
            {'$': 'mock_value1'},
            {'$': 'mock_value2'}
        ]

        # Mock the convert_to_json_type method to return specific values
        mock_convert.side_effect = ['converted_value1', 'converted_value2']

        # Call the method to be tested
        self.parser.get_value(node, classiri, self.parser.xml_ns)

        # Assert that the correct triples were added to the graph
        expected_triples = [
            (classiri, self.parser.rdf_ns['base']['hasValue'], Literal('converted_value1')),
            (classiri, self.parser.rdf_ns['base']['hasValue'], Literal('converted_value2'))
        ]

        # Check that the add method was called with each expected triple
        for expected_triple in expected_triples:
            mock_add.assert_any_call(expected_triple)

    @patch.object(Graph, 'add')
    def test_get_value_no_value(self, mock_add):
        # Mock node with no Value child
        node = MagicMock()
        node.find.return_value = None

        # Mock the classiri URI
        classiri = URIRef('http://example.com/classiri')

        # Call the method to be tested
        self.parser.get_value(node, classiri, self.parser.xml_ns)

        # Since there's no value, nothing should be added to the graph
        mock_add.assert_not_called()


    def test_references_ignore(self):
        # Test when the reference should be ignored
        ignored_id = '45'  # corresponds to hasSubtypeId
        self.parser.opcua_namespace = 'http://example.com/opcua'
        
        # Call the method to be tested
        result = self.parser.references_ignore(ignored_id, 'http://example.com/opcua')

        # Assert that the reference is ignored
        self.assertTrue(result)

        # Test when the reference should not be ignored
        non_ignored_id = '47'  # corresponds to hasComponentId
        result = self.parser.references_ignore(non_ignored_id, 'http://example.com/opcua')

        # Assert that the reference is not ignored
        self.assertFalse(result)

    @patch.object(Graph, 'add')
    def test_get_references(self, mock_add):
        # Mock the node and its references
        ref_node1 = MagicMock()
        ref_node1.get.side_effect = lambda key: 'HasSubtype' if key == 'ReferenceType' else 'true' if key == 'IsForward' else None
        ref_node1.text = 'ns=1;i=100'

        ref_node2 = MagicMock()
        ref_node2.get.side_effect = lambda key: 'HasProperty' if key == 'ReferenceType' else 'false' if key == 'IsForward' else None
        ref_node2.text = 'ns=2;i=200'

        # Mock the references node to return the mocked references
        refnodes = [ref_node1, ref_node2]

        # Set up other necessary attributes and mocks
        classiri = URIRef('http://example.com/classiri')
        self.parser.resolve_alias = MagicMock(side_effect=lambda x: x)
        self.parser.parse_nodeid = MagicMock(side_effect=[(1, '100', None), (1, '100', None), (2, '200', None), (2, '200', None)])
        self.parser.get_rdf_ns_from_ua_index = MagicMock(side_effect=[Namespace('http://example.com/ns1#'), Namespace('http://example.com/ns1#'), Namespace('http://example.com/ns2#'), Namespace('http://example.com/ns2#')])
        self.parser.references_ignore = MagicMock(return_value=False)
        self.parser.references_get_special = MagicMock(return_value=None)
        self.parser.nodeId_to_iri = MagicMock(side_effect=[URIRef('http://example.com/iri100'), URIRef('http://example.com/iri200')])

        # Mock known_references to match the mock data
        self.parser.known_references = [
            (Literal('100'), Namespace('http://example.com/ns1#'), Literal('Subtype')),
            (Literal('200'), Namespace('http://example.com/ns2#'), Literal('Property'))
        ]

        # Call the method to be tested
        self.parser.get_references(refnodes, classiri)

        # Assert that the correct triples were added to the graph
        expected_triples = [
            (classiri, Namespace('http://example.com/ns1#')['Subtype'], URIRef('http://example.com/iri100')),
            (URIRef('http://example.com/iri200'), Namespace('http://example.com/ns2#')['Property'], classiri)
        ]
        for triple in expected_triples:
            mock_add.assert_any_call(triple)

    @patch.object(Graph, 'add')
    def test_get_type_from_references(self, mock_add):
        # Mock the reference nodes
        ref_node = MagicMock()
        ref_node.get.side_effect = lambda x: 'HasTypeDefinition' if x == 'ReferenceType' else 'true' if x == 'IsForward' else None
        ref_node.text = 'ns=1;i=400'
        
        # Set up other necessary attributes and mocks
        classiri = URIRef('http://example.com/classiri')
        self.parser.resolve_alias = MagicMock(return_value='ns=1;i=400')
        self.parser.parse_nodeid = MagicMock(side_effect=[(0, '40', None), (1, '400', None)])
        self.parser.typeIds = [{}, {'400': URIRef('http://example.com/type/400')}]

        # Call the method to be tested
        self.parser.get_type_from_references([ref_node], classiri)

        # Assert that the correct triple was added to the graph
        expected_triple = (
            classiri,
            RDF.type,
            URIRef('http://example.com/type/400')
        )
        mock_add.assert_any_call(expected_triple)


    @patch.object(Graph, 'add')
    @patch.object(NodesetParser, 'get_references')
    @patch.object(NodesetParser, 'get_type_from_references')
    @patch.object(NodesetParser, 'get_datatype')
    @patch.object(NodesetParser, 'get_value_rank')
    @patch.object(NodesetParser, 'get_value')
    def test_add_typedef(self, mock_get_value, mock_get_value_rank, mock_get_datatype, mock_get_type_from_references, mock_get_references, mock_add):
        # Mock a node with necessary attributes
        def node_get(tag):
            if tag == 'ArrayDimensions' or \
                tag == 'EventNotifier' or \
                tag == 'AccessLevel' or \
                tag == 'UserAccessLevel' or \
                tag == 'AccessLevelEx':
                return None
            else:
                return 'ns=1;i=600'
        node = MagicMock()
        # node.get.return_value = 'ns=1;i=500'
        node.get = node_get
        self.parser.get_nid_ns_and_name = MagicMock(return_value=('500', 1, 'TestBrowseName', self.parser.rdf_ns['base']['numericID']))
        self.parser.get_rdf_ns_from_ua_index = MagicMock(return_value=Namespace('http://example.com/ns1#'))
        self.parser.nodeId_to_iri = MagicMock(return_value=URIRef('http://example.com/ns1#500'))
        node.find.return_value = MagicMock()  # Mock for references_node

        # Call the method to be tested
        self.parser.add_typedef(node)

        # Assert that the relevant methods were called
        mock_get_references.assert_called_once_with(node.find.return_value.findall.return_value, URIRef('http://example.com/ns1#500'))
        mock_get_type_from_references.assert_called_once_with(node.find.return_value.findall.return_value, URIRef('http://example.com/ns1#500'))
        mock_get_datatype.assert_called_once_with(node, URIRef('http://example.com/ns1#500'))
        mock_get_value_rank.assert_called_once_with(node, URIRef('http://example.com/ns1#500'))
        mock_get_value.assert_called_once_with(node, URIRef('http://example.com/ns1#500'), self.parser.xml_ns)

    def test_is_objecttype_nodeset_node(self):
        # Mock a node with the appropriate tag
        node = MagicMock()
        node.tag = 'opcua:UAObjectType'
        
        # Call the method to be tested
        result = NodesetParser.is_objecttype_nodeset_node(node)

        # Assert that the result is True
        self.assertTrue(result)

        # Change the tag and test again
        node.tag = 'opcua:UAOtherType'
        
        # Call the method to be tested
        result = NodesetParser.is_objecttype_nodeset_node(node)

        # Assert that the result is False
        self.assertFalse(result)

    def test_is_base_object(self):
        # Test when the name is BaseObject
        name = self.parser.rdf_ns['opcua']['BaseObject']
        
        # Call the method to be tested
        result = self.parser.is_base_object(name)

        # Assert that the result is True
        self.assertTrue(result)

        # Test with a different name
        name = self.parser.rdf_ns['opcua']['SomeOtherObject']
        
        # Call the method to be tested
        result = self.parser.is_base_object(name)

        # Assert that the result is False
        self.assertFalse(result)

    @patch.object(Graph, 'add')
    def test_get_typedefinition_from_references(self, mock_add):
        # Mock the reference nodes
        ref_node = MagicMock()
        ref_node.get.side_effect = lambda x: 'HasSubtype' if x == 'ReferenceType' else 'false' if x == 'IsForward' else None
        ref_node.text = 'ns=1;i=500'
        
        # Set up other necessary attributes and mocks
        node = MagicMock()
        node.get.return_value = 'true'  # Mock IsAbstract
        node.find.return_value.findall.return_value = [ref_node]
        ref_classiri = URIRef('http://example.com/classiri')
        self.parser.getBrowsename = MagicMock(return_value=(None, 'TestBrowseName'))
        self.parser.parse_nodeid = MagicMock(side_effect=[(1, '100', None), (0, '45', None), (1, '500', None)])
        self.parser.resolve_alias = MagicMock(return_value='ns=1;i=500')
        self.parser.get_rdf_ns_from_ua_index = MagicMock(return_value=Namespace('http://example.com/ns1#'))
        self.parser.typeIds = [{}, {'500': URIRef('http://example.com/type/500')}]
        #self.parser.rdf_ns['opcua']['BaseObjectType'] = URIRef('http://example.com/BaseObjectType')

        # Call the method to be tested
        self.parser.get_typedefinition_from_references([ref_node], ref_classiri, node)

        # Assert that the correct triples were added to the graph
        expected_triples = [
            (URIRef('http://example.com/ns1#TestBrowseName'), RDFS.subClassOf, URIRef('http://example.com/type/500')),
            (URIRef('http://example.com/ns1#TestBrowseName'), self.parser.rdf_ns['base']['isAbstract'], Literal('true')),
            (ref_classiri, self.parser.rdf_ns['base']['definesType'], URIRef('http://example.com/ns1#TestBrowseName'))
        ]
        for triple in expected_triples:
            mock_add.assert_any_call(triple)

    @patch.object(Graph, 'add')
    def test_add_type(self, mock_add):
        # Mock the node with necessary attributes
        def node_get(tag):
            if tag == 'ArrayDimensions':
                return None
            else:
                return 'ns=1;i=600'

        node = MagicMock()
        #node.get.return_value = 'ns=1;i=600'  # Mock NodeId
        node.get = node_get  # Mock NodeId
        node.tag = 'opcua:UAObjectType'
        
        # Mock other necessary method returns
        self.parser.getBrowsename = MagicMock(return_value=(None, 'TestBrowseName'))
        self.parser.get_rdf_ns_from_ua_index = MagicMock(return_value=Namespace('http://example.com/ns1#'))
        self.parser.parse_nodeid = MagicMock(return_value=(1, '600', self.parser.rdf_ns['base']['numericID']))
        self.parser.get_references = MagicMock()
        self.parser.get_typedefinition_from_references = MagicMock()
        self.parser.get_datatype = MagicMock()
        self.parser.get_value_rank = MagicMock()
        self.parser.get_value = MagicMock()
        
        # Call the method to be tested
        self.parser.add_type(node)
        
        # Assert that the correct triples were added to the graph
        expected_triple_class = (URIRef('http://example.com/ns1#TestBrowseName'), RDF.type, OWL.Class)
        mock_add.assert_any_call(expected_triple_class)
        
        # Ensure the correct methods were called
        self.parser.get_references.assert_called_once()
        self.parser.get_typedefinition_from_references.assert_called_once()
        self.parser.get_datatype.assert_called_once()
        self.parser.get_value_rank.assert_called_once()
        self.parser.get_value.assert_called_once()

        # Check if known_references was updated correctly for UAReferenceType
        node.tag = 'opcua:UAReferenceType'
        self.parser.add_type(node)
        expected_triple_property = (URIRef('http://example.com/ns1#TestBrowseName'), RDF.type, OWL.ObjectProperty)
        mock_add.assert_any_call(expected_triple_property)
        self.assertIn((Literal('600'), Namespace('http://example.com/ns1#'), Literal('TestBrowseName')), self.parser.known_references)

    def test_get_nid_ns_and_name(self):
        # Mock the node with necessary attributes
        node = MagicMock()
        node.get.return_value = 'ns=1;i=700'  # Mock NodeId
        
        # Mock other necessary method returns
        self.parser.getBrowsename = MagicMock(return_value=(None, 'TestBrowseName'))
        self.parser.parse_nodeid = MagicMock(return_value=(1, '700', self.parser.rdf_ns['base']['numericID']))
        
        # Call the method to be tested
        nid, index, bn_name, idtype = self.parser.get_nid_ns_and_name(node)
        
        # Assert that the values were correctly returned
        self.assertEqual(nid, '700')
        self.assertEqual(index, 1)
        self.assertEqual(bn_name, 'TestBrowseName')
        self.assertEqual(idtype, self.parser.rdf_ns['base']['numericID'])

    def test_scan_aliases(self):
        # Ensure that self.aliases is initialized as an empty dictionary
        self.parser.aliases = {}

        # Mock alias nodes
        alias1 = MagicMock()
        alias1.get.return_value = 'Alias1'
        alias1.text = 'ns=1;i=800'
        
        alias2 = MagicMock()
        alias2.get.return_value = 'Alias2'
        alias2.text = 'ns=2;i=900'
        
        alias_nodes = [alias1, alias2]
        
        # Call the method to be tested
        self.parser.scan_aliases(alias_nodes)
        
        # Assert that the aliases were correctly populated
        expected_aliases = {
            'Alias1': 'ns=1;i=800',
            'Alias2': 'ns=2;i=900'
        }
        self.assertEqual(self.parser.aliases, expected_aliases)


    def test_getBrowsename(self):
        # Mock the node with a BrowseName attribute
        node = MagicMock()
        node.get.return_value = '1:TestBrowseName'
        
        # Call the method to be tested
        index, name = self.parser.getBrowsename(node)
        
        # Assert that the index and name were correctly returned
        self.assertEqual(index, 1)
        self.assertEqual(name, 'TestBrowseName')
        
        # Test with a different format
        node.get.return_value = 'TestBrowseNameWithoutIndex'
        
        # Call the method to be tested
        index, name = self.parser.getBrowsename(node)
        
        # Assert that the index is None and the name is correctly returned
        self.assertIsNone(index)
        self.assertEqual(name, 'TestBrowseNameWithoutIndex')

    @patch('lib.nodesetparser.utils.get_contentclass')
    def test_get_event_notifier_adds_triples(self, mock_get_contentclass):
        # Simulate an EventNotifier attribute with bits 0, 2, and 3 set.
        # Value "13" in decimal is binary 1101, so bits 0, 2, and 3 are active.
        node = MagicMock()
        node.get.return_value = "13"
        classiri = URIRef("http://example.com/classiri")
        
        # Define expected content classes for each bit.
        content_classes = {
            0: URIRef("http://example.com/event0"),
            2: URIRef("http://example.com/event2"),
            3: URIRef("http://example.com/event3")
        }
        
        # Patch utils.get_contentclass to return the corresponding content class for each bit.
        def side_effect(arg1, bit, arg3, arg4):
            return content_classes[bit]
        mock_get_contentclass.side_effect = side_effect
        
        # Clear the graph before calling.
        self.parser.g = Graph()
        self.parser.get_event_notifier(node, classiri)
        
        # Verify that for each active bit, the expected triple is added.
        for bit in (0, 2, 3):
            expected_triple = (classiri, self.parser.rdf_ns['base']['hasEventNotifier'], content_classes[bit])
            self.assertIn(expected_triple, self.parser.g)
        
        # Ensure get_contentclass was called three times.
        self.assertEqual(mock_get_contentclass.call_count, 3)

    def test_get_event_notifier_no_value(self):
        # Test that nothing is added to the graph when EventNotifier is None.
        node = MagicMock()
        node.get.return_value = None
        classiri = URIRef("http://example.com/classiri")
        
        # Clear the graph.
        self.parser.g = Graph()
        self.parser.get_event_notifier(node, classiri)
        
        # Expect that no triples have been added.
        self.assertEqual(len(self.parser.g), 0)

    @patch('lib.nodesetparser.utils.get_contentclass')
    def test_get_event_notifier_exception(self, mock_get_contentclass):
        # Test the scenario where get_contentclass raises an exception for one of the bits.
        # Using the same EventNotifier value "13" (bits 0, 2, and 3 set).
        node = MagicMock()
        node.get.return_value = "13"
        classiri = URIRef("http://example.com/classiri")
        
        # For bit 0, raise an exception; for bits 2 and 3, return valid content classes.
        def side_effect(arg1, bit, arg3, arg4):
            if bit == 0:
                raise Exception("Test exception")
            else:
                return URIRef(f"http://example.com/event{bit}")
        mock_get_contentclass.side_effect = side_effect
        
        # Clear the graph.
        self.parser.g = Graph()
        
        # Patch print to catch the warning message.
        with patch('builtins.print') as mock_print:
            self.parser.get_event_notifier(node, classiri)
            
            # Verify that for bits 2 and 3, the expected triples are added.
            for bit in (2, 3):
                expected_triple = (
                    classiri,
                    self.parser.rdf_ns['base']['hasEventNotifier'],
                    URIRef(f"http://example.com/event{bit}")
                )
                self.assertIn(expected_triple, self.parser.g)
            
            # Ensure that get_contentclass was attempted for all three bits.
            self.assertEqual(mock_get_contentclass.call_count, 3)
            
            # Verify that a warning message was printed (for the exception on bit 0).
            self.assertTrue(mock_print.called)

    @patch('lib.nodesetparser.utils.get_contentclass')
    def test_get_user_access_all_values(self, mock_get_contentclass):
        # Create a node that returns valid values for all access attributes.
        node = MagicMock()
        node.get.side_effect = lambda key: {
            "AccessLevel": "1",
            "UserAccessLevel": "2",
            "AccessLevelEx": "4"
        }.get(key)
        classiri = URIRef("http://example.com/classiri")
        
        # Define expected return values from get_contentclass for each access type.
        content_access = URIRef("http://example.com/access1")
        content_user_access = URIRef("http://example.com/useraccess2")
        content_access_ex = URIRef("http://example.com/accessEx3")
        
        def side_effect(namespace, value, ig, base):
            if namespace == self.parser.rdf_ns['opcua']['AccessLevelType'] and value == 0:
                return content_access
            elif namespace == self.parser.rdf_ns['opcua']['AccessLevelType'] and value == 1:
                return content_user_access
            elif namespace == self.parser.rdf_ns['opcua']['AccessLevelExType'] and value == 2:
                return content_access_ex
            return None
        mock_get_contentclass.side_effect = side_effect
        
        # Clear the graph and call the method.
        self.parser.g = Graph()
        self.parser.get_user_access(node, classiri)
        
        # Verify that the graph contains the expected triples.
        self.assertIn(
            (classiri, self.parser.rdf_ns['base']['hasAccessLevel'], content_access),
            self.parser.g
        )
        self.assertIn(
            (classiri, self.parser.rdf_ns['base']['hasUserAccessLevel'], content_user_access),
            self.parser.g
        )
        self.assertIn(
            (classiri, self.parser.rdf_ns['base']['hasAccessLevelEx'], content_access_ex),
            self.parser.g
        )

    def test_get_user_access_missing_values(self):
        # Create a node with only UserAccessLevel set.
        node = MagicMock()
        node.get.side_effect = lambda key: {
            "AccessLevel": None,
            "UserAccessLevel": "2",
            "AccessLevelEx": None
        }.get(key)
        classiri = URIRef("http://example.com/classiri")
        
        with patch('lib.nodesetparser.utils.get_contentclass', return_value=URIRef("http://example.com/useraccess2")) as mock_get:
            self.parser.g = Graph()
            self.parser.get_user_access(node, classiri)
            
            # Only one triple should be added.
            self.assertEqual(len(self.parser.g), 1)
            self.assertIn(
                (classiri, self.parser.rdf_ns['base']['hasUserAccessLevel'], URIRef("http://example.com/useraccess2")),
                self.parser.g
            )
            self.assertEqual(mock_get.call_count, 1)

    @patch('lib.nodesetparser.utils.get_contentclass')
    def test_get_user_access_exception(self, mock_get_contentclass):
        # Create a node with all access attributes provided.
        node = MagicMock()
        node.get.side_effect = lambda key: {
            "AccessLevel": "1",
            "UserAccessLevel": "2",
            "AccessLevelEx": "4"
        }.get(key)
        classiri = URIRef("http://example.com/classiri")
        
        # Simulate an exception for AccessLevel while others succeed.
        def side_effect(namespace, value, ig, base):
            if namespace == self.parser.rdf_ns['opcua']['AccessLevelType'] and value == 0:
                raise Exception("Test exception")
            elif namespace == self.parser.rdf_ns['opcua']['AccessLevelType'] and value == 1:
                return URIRef("http://example.com/useraccess2")
            elif namespace == self.parser.rdf_ns['opcua']['AccessLevelExType'] and value == 2:
                return URIRef("http://example.com/accessEx3")
        mock_get_contentclass.side_effect = side_effect
        
        # Patch print to capture warning messages.
        with patch('builtins.print') as mock_print:
            self.parser.g = Graph()
            self.parser.get_user_access(node, classiri)
            
            # Verify that only the UserAccessLevel and AccessLevelEx triples are added.
            expected_user_access = (classiri, self.parser.rdf_ns['base']['hasUserAccessLevel'], URIRef("http://example.com/useraccess2"))
            expected_access_ex = (classiri, self.parser.rdf_ns['base']['hasAccessLevelEx'], URIRef("http://example.com/accessEx3"))
            
            self.assertIn(expected_user_access, self.parser.g)
            self.assertIn(expected_access_ex, self.parser.g)
            
            # Ensure that no triple is added for AccessLevel.
            for s, p, o in self.parser.g:
                self.assertNotEqual(p, self.parser.rdf_ns['base']['hasAccessLevel'])
            
            # Verify that a warning was printed for AccessLevel.
            mock_print.assert_any_call(f"Warning: Cannot read access_level value 1 in node {classiri}")


if __name__ == '__main__':
    unittest.main()
