#
# Copyright (c) 2026 IndustryFusion Foundation
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
"""Node identification: canonical ExpandedNodeId IRIs, static/dynamic classification, uardf: attributes."""

import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
from rdflib import Graph, Literal, Namespace, URIRef, BNode
from rdflib.namespace import RDF, RDFS, OWL
from rdflib.collection import Collection
import lib.utils as utils
from lib.utils import UARDF
from lib.nodesetparser import NodesetParser

BASE = Namespace('https://industryfusion.github.io/contexts/ontology/v0/base/')
OPCUA = Namespace('http://opcfoundation.org/UA/')
TEST_NS = 'http://test.org/A/'
SERVER = 'urn:test:server'


def iri(expanded, prefix=TEST_NS):
    return URIRef(prefix + utils.base64url_nopad(expanded))


class TestIdentificationUtils(unittest.TestCase):
    def test_canonical_nodeid(self):
        self.assertEqual(utils.canonical_nodeid('i', '0031'), 'i=31')
        self.assertEqual(utils.canonical_nodeid('s', 'Foo;Bar'), 's=Foo;Bar')
        self.assertEqual(utils.canonical_nodeid('g', '{09087E75-8E5E-499B-954F-F2A9603DB28A}'),
                         'g=09087e75-8e5e-499b-954f-f2a9603db28a')
        self.assertEqual(utils.canonical_nodeid('b', 'M/RbKBsRVkePCePcx24oRA=='), 'b=M/RbKBsRVkePCePcx24oRA==')

    def test_expanded_nodeid_string(self):
        # nsu is omitted for the core namespace, svu only for dynamic nodes
        self.assertEqual(utils.expanded_nodeid_string('i=31', 'http://opcfoundation.org/UA/'), 'i=31')
        self.assertEqual(utils.expanded_nodeid_string('i=1001', TEST_NS), f'nsu={TEST_NS};i=1001')
        self.assertEqual(utils.expanded_nodeid_string('i=5001', TEST_NS, SERVER),
                         f'svu={SERVER};nsu={TEST_NS};i=5001')
        self.assertEqual(utils.expanded_nodeid_string('i=2253', 'http://opcfoundation.org/UA/', SERVER),
                         f'svu={SERVER};i=2253')

    def test_parse_expanded_nodeid_roundtrip(self):
        for args in (('i=31', 'http://opcfoundation.org/UA/', None), ('s=a;b', TEST_NS, None),
                     ('i=5001', TEST_NS, SERVER)):
            expanded = utils.expanded_nodeid_string(*args)
            server, namespace, idt, identifier = utils.parse_expanded_nodeid(expanded)
            self.assertEqual(server, args[2])
            self.assertEqual(namespace, None if args[1] == utils.OPCUA_CORE_NAMESPACE else args[1])
            self.assertEqual(f'{idt}={identifier}', args[0])

    def test_iri(self):
        self.assertEqual(utils.base64url_nopad('i=31'), 'aT0zMQ')
        self.assertEqual(utils.expanded_nodeid_to_iri(OPCUA, 'i=31'), URIRef('http://opcfoundation.org/UA/aT0zMQ'))
        # base64url: no '+', '/' or padding
        encoded = utils.base64url_nopad('s=>>>???')
        self.assertNotIn('/', encoded)
        self.assertNotIn('+', encoded)
        self.assertNotIn('=', encoded)

    def test_qualified_name_roundtrip(self):
        self.assertEqual(utils.canonical_qualified_name('References', 'http://opcfoundation.org/UA/'), 'References')
        self.assertEqual(utils.canonical_qualified_name('Machines', TEST_NS), f'nsu={TEST_NS};Machines')
        self.assertEqual(utils.parse_qualified_name(f'nsu={TEST_NS};Machines'), (TEST_NS, 'Machines'))
        self.assertEqual(utils.parse_qualified_name('References'), ('http://opcfoundation.org/UA/', 'References'))

    def test_parse_numeric_range(self):
        self.assertEqual(utils.parse_numeric_range('1:2252'), (1, 2252))
        self.assertEqual(utils.parse_numeric_range(' 2270 '), (2270, 2270))

    def test_restore_type_of_node_iris_reads_both_predicates(self):
        g = Graph()
        g.add((URIRef('http://n/1'), UARDF['hasTypeDefinition'], URIRef('http://t/A')))
        g.add((URIRef('http://n/2'), BASE['instanceOf'], URIRef('http://t/B')))
        utils.restore_type_of_node_iris(g, OPCUA, BASE)
        self.assertIn((URIRef('http://n/1'), RDF.type, URIRef('http://t/A')), g)
        self.assertIn((URIRef('http://n/2'), RDF.type, URIRef('http://t/B')), g)
        self.assertEqual(len(g), 2)


# ns=1 is http://test.org/A/. Without NamespaceMetadata the fallback rule decides:
#   i=1001 ObjectType (static), i=1002 instance declaration (modelling rule, static),
#   i=1003 child of an instance declaration (static), i=5001 instance (dynamic),
#   i=5002 child of an instance (dynamic)
NODESET = """<?xml version="1.0" encoding="utf-8"?>
<UANodeSet xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd">
  <NamespaceUris><Uri>http://test.org/A/</Uri></NamespaceUris>
  <Aliases>
    <Alias Alias="HasModellingRule">i=37</Alias>
    <Alias Alias="HasTypeDefinition">i=40</Alias>
    <Alias Alias="HasSubtype">i=45</Alias>
    <Alias Alias="HasProperty">i=46</Alias>
    <Alias Alias="HasComponent">i=47</Alias>
  </Aliases>
  <UAObjectType NodeId="ns=1;i=1001" BrowseName="1:TestType">
    <DisplayName>TestType</DisplayName>
    <References><Reference ReferenceType="HasSubtype" IsForward="false">i=58</Reference></References>
  </UAObjectType>
  <UAObject NodeId="ns=1;i=1002" BrowseName="1:Declaration" ParentNodeId="ns=1;i=1001">
    <DisplayName>Declaration</DisplayName>
    <References>
      <Reference ReferenceType="HasTypeDefinition">i=58</Reference>
      <Reference ReferenceType="HasModellingRule">i=78</Reference>
      <Reference ReferenceType="HasComponent" IsForward="false">ns=1;i=1001</Reference>
    </References>
  </UAObject>
  <UAVariable NodeId="ns=1;i=1003" BrowseName="1:DeclarationChild" ParentNodeId="ns=1;i=1002" DataType="i=12">
    <DisplayName>DeclarationChild</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=68</Reference></References>
  </UAVariable>
  <UAObject NodeId="ns=1;i=5001" BrowseName="1:Instance">
    <DisplayName>Instance</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">ns=1;i=1001</Reference></References>
  </UAObject>
  <UAVariable NodeId="ns=1;i=5002" BrowseName="1:InstanceChild" ParentNodeId="ns=1;i=5001" DataType="i=12">
    <DisplayName>InstanceChild</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=68</Reference></References>
  </UAVariable>
  <UAObject NodeId="ns=1;s=Named" BrowseName="1:Named">
    <DisplayName>Named</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=58</Reference></References>
  </UAObject>
  {metadata}
</UANodeSet>
"""

# Nodes for the instance-with-variables heuristic (all in the static range of METADATA): a ModellingRule object
# with its NamingRule property (excepted) and a Variable below core's ServerCapabilities (another nodeset)
HEURISTIC_NODES = """
  <UAObject NodeId="ns=1;i=4000" BrowseName="1:MyRule">
    <DisplayName>MyRule</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=77</Reference></References>
  </UAObject>
  <UAVariable NodeId="ns=1;i=4001" BrowseName="NamingRule" ParentNodeId="ns=1;i=4000" DataType="i=120">
    <DisplayName>NamingRule</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=68</Reference></References>
  </UAVariable>
  <UAObject NodeId="ns=1;i=4200" BrowseName="1:Folder" ParentNodeId="ns=1;i=5001">
    <DisplayName>Folder</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=61</Reference></References>
  </UAObject>
  <UAObject NodeId="ns=1;i=4300" BrowseName="1:Entry" ParentNodeId="ns=1;i=5001">
    <DisplayName>Entry</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=17589</Reference></References>
  </UAObject>
  <UAObject NodeId="ns=1;i=4400" BrowseName="1:OrganizedFolder">
    <DisplayName>OrganizedFolder</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=61</Reference>
      <Reference ReferenceType="i=35" IsForward="false">ns=1;i=5001</Reference></References>
  </UAObject>
  <UAMethod NodeId="ns=1;i=4500" BrowseName="1:Reset" ParentNodeId="ns=1;i=5001">
    <DisplayName>Reset</DisplayName>
    <References><Reference ReferenceType="HasComponent" IsForward="false">ns=1;i=5001</Reference></References>
  </UAMethod>
  <UAObject NodeId="ns=1;i=4600" BrowseName="1:ComponentFolder">
    <DisplayName>ComponentFolder</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=61</Reference>
      <Reference ReferenceType="HasComponent" IsForward="false">ns=1;i=5001</Reference></References>
  </UAObject>
  <UAVariable NodeId="ns=1;i=4100" BrowseName="1:MaxLockTime" ParentNodeId="i=2268" DataType="i=11">
    <DisplayName>MaxLockTime</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=68</Reference></References>
  </UAVariable>
"""

# Nodes for the default heuristic (no NamespaceMetadata decides): an encoding, a Variable two levels below an
# Object, an empty container of the dynamic instance 5001, a static Method with its argument, and a Variable below
# an Object via a custom subtype of HasComponent, and an instance without children whose type declares Variables
DEFAULT_HEURISTIC_NODES = """
  <UAReferenceType NodeId="ns=1;i=6500" BrowseName="1:HasSpecialPart">
    <DisplayName>HasSpecialPart</DisplayName>
    <References><Reference ReferenceType="HasSubtype" IsForward="false">i=47</Reference></References>
  </UAReferenceType>
  <UAObject NodeId="ns=1;i=6000" BrowseName="Default Binary">
    <DisplayName>Default Binary</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=76</Reference></References>
  </UAObject>
  <UAObject NodeId="ns=1;i=6100" BrowseName="1:Machine">
    <DisplayName>Machine</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=58</Reference>
      <Reference ReferenceType="HasComponent">ns=1;i=6101</Reference></References>
  </UAObject>
  <UAObject NodeId="ns=1;i=6101" BrowseName="1:Group">
    <DisplayName>Group</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=58</Reference></References>
  </UAObject>
  <UAVariable NodeId="ns=1;i=6102" BrowseName="1:Value" ParentNodeId="ns=1;i=6101" DataType="i=11">
    <DisplayName>Value</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=63</Reference></References>
  </UAVariable>
  <UAObject NodeId="ns=1;i=6201" BrowseName="1:EmptyContainer">
    <DisplayName>EmptyContainer</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=61</Reference>
      <Reference ReferenceType="HasComponent" IsForward="false">ns=1;i=5001</Reference></References>
  </UAObject>
  <UAObject NodeId="ns=1;i=6400" BrowseName="1:Service">
    <DisplayName>Service</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=58</Reference></References>
  </UAObject>
  <UAMethod NodeId="ns=1;i=6300" BrowseName="1:Run" ParentNodeId="ns=1;i=6400">
    <DisplayName>Run</DisplayName>
    <References><Reference ReferenceType="HasComponent" IsForward="false">ns=1;i=6400</Reference></References>
  </UAMethod>
  <UAVariable NodeId="ns=1;i=6301" BrowseName="InputArguments" ParentNodeId="ns=1;i=6300" DataType="i=296">
    <DisplayName>InputArguments</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=68</Reference></References>
  </UAVariable>
  <UAObject NodeId="ns=1;i=6600" BrowseName="1:Special">
    <DisplayName>Special</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=58</Reference>
      <Reference ReferenceType="ns=1;i=6500">ns=1;i=6601</Reference></References>
  </UAObject>
  <UAObject NodeId="ns=1;i=6700" BrowseName="1:PartialInstance">
    <DisplayName>PartialInstance</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">ns=1;i=1001</Reference></References>
  </UAObject>
  <UAVariable NodeId="ns=1;i=6601" BrowseName="1:SpecialValue" DataType="i=11">
    <DisplayName>SpecialValue</DisplayName>
    <References><Reference ReferenceType="HasTypeDefinition">i=63</Reference></References>
  </UAVariable>
"""

# NamespaceMetadata: numeric ids 1..5001 and string ids starting with "Named" are static
METADATA = """
  <UAObject NodeId="ns=1;i=9000" BrowseName="1:http://test.org/A/">
    <DisplayName>http://test.org/A/</DisplayName>
    <References>
      <Reference ReferenceType="HasTypeDefinition">i=11616</Reference>
      <Reference ReferenceType="HasProperty">ns=1;i=9001</Reference>
    </References>
  </UAObject>
  <UAVariable NodeId="ns=1;i=9001" BrowseName="NamespaceUri" ParentNodeId="ns=1;i=9000" DataType="String">
    <DisplayName>NamespaceUri</DisplayName>
    <Value><String xmlns="http://opcfoundation.org/UA/2008/02/Types.xsd">http://test.org/A/</String></Value>
  </UAVariable>
  <UAVariable NodeId="ns=1;i=9002" BrowseName="StaticNodeIdTypes" ParentNodeId="ns=1;i=9000" DataType="i=256">
    <DisplayName>StaticNodeIdTypes</DisplayName>
    <Value><ListOfInt32 xmlns="http://opcfoundation.org/UA/2008/02/Types.xsd"><Int32>0</Int32></ListOfInt32></Value>
  </UAVariable>
  <UAVariable NodeId="ns=1;i=9003" BrowseName="StaticNumericNodeIdRange" ParentNodeId="ns=1;i=9000" DataType="i=291">
    <DisplayName>StaticNumericNodeIdRange</DisplayName>
    <Value><ListOfString xmlns="http://opcfoundation.org/UA/2008/02/Types.xsd">
      <String>1:5001</String><String>9000:9010</String></ListOfString></Value>
  </UAVariable>
  <UAVariable NodeId="ns=1;i=9004" BrowseName="StaticStringNodeIdPattern" ParentNodeId="ns=1;i=9000" DataType="String">
    <DisplayName>StaticStringNodeIdPattern</DisplayName>
    <Value><String xmlns="http://opcfoundation.org/UA/2008/02/Types.xsd">Named.*</String></Value>
  </UAVariable>
"""


class TestClassification(unittest.TestCase):

    def make_parser(self, metadata='', server_uri=None, strict=False):
        with patch('lib.nodesetparser.NodesetParser.__init__', return_value=None):
            parser = NodesetParser(None, None, None, None, None, None)
        parser.xml_ns = {'opcua': 'http://opcfoundation.org/UA/2011/03/UANodeSet.xsd',
                         'xsd': 'http://opcfoundation.org/UA/2008/02/Types.xsd'}
        parser.root = ET.fromstring(NODESET.format(metadata=metadata))
        parser.g = Graph()
        parser.ig = Graph()
        parser.rdf_ns = {'base': BASE, 'opcua': OPCUA, 'test': Namespace(TEST_NS), 'uardf': UARDF}
        parser.known_opcua_ns = {'http://opcfoundation.org/UA/': 'opcua', TEST_NS: 'test'}
        parser.opcua_ns = ['http://opcfoundation.org/UA/', TEST_NS]
        parser.opcua_ns_raw = ['http://opcfoundation.org/UA/', TEST_NS]
        parser.nodeIds = [{}, {}, {}]
        parser.typeIds = [{}, {}, {}]
        parser.aliases = {}
        parser.server_uri = server_uri
        parser.default_locale = 'en'
        parser.enforce_opcua_type_semantic = False
        parser.strict_classification = strict
        parser.heuristic_overrides = {}
        parser.node_iris = {}
        parser.expanded_nodeids = {}
        parser.skipped_dynamic_nodes = []
        parser.unknown_nodes = set()
        parser.foreign_dynamic_iris = set()
        parser.imported_namespace_indices = set()
        parser.scan_aliases(parser.root.find('opcua:Aliases', parser.xml_ns).findall('opcua:Alias', parser.xml_ns))
        return parser

    def key(self, parser, identifier, idt='numericID'):
        return parser.node_key(1, identifier, BASE[idt])

    def test_fallback_rule_without_server_uri(self):
        parser = self.make_parser(strict=True)
        parser.classify_nodes()
        for static in ('1001', '1002', '1003'):
            key = self.key(parser, static)
            self.assertIn(key, parser.static_nodes)
            self.assertEqual(parser.node_iris[key], iri(f'nsu={TEST_NS};i={static}'))
            self.assertEqual(parser.expanded_nodeids[key], f'nsu={TEST_NS};i={static}')
        for dynamic in ('5001', '5002'):
            key = self.key(parser, dynamic)
            self.assertNotIn(key, parser.static_nodes)
            self.assertIsNone(parser.node_iris[key])  # not exported without server URI
        self.assertIsNone(parser.node_iris[self.key(parser, 'Named', 'stringID')])
        self.assertEqual(len(parser.skipped_dynamic_nodes), 3)

    def test_default_rule_without_metadata(self):
        # without NamespaceMetadata the default fallback R5 applies: the instance 5001 (with Variable) and the Object
        # Named (without Variables) are dynamic; R4 only concerns the definition types
        parser = self.make_parser()
        parser.classify_nodes()
        for dynamic in ('5001', '5002'):
            self.assertNotIn(self.key(parser, dynamic), parser.static_nodes)
        named = self.key(parser, 'Named', 'stringID')
        self.assertNotIn(named, parser.static_nodes)
        self.assertNotIn(named, parser.heuristic_overrides)

    def test_heuristic_cases_without_metadata(self):
        parser = self.make_parser(metadata=DEFAULT_HEURISTIC_NODES)
        parser.classify_nodes()
        self.assertIn(self.key(parser, '6500'), parser.haschild_keys)  # custom subtype of HasComponent
        # R4: the encoding is static
        self.assertIn(self.key(parser, '6000'), parser.static_nodes)
        self.assertEqual(parser.heuristic_overrides[self.key(parser, '6000')], 'R4: definition node (fallback)')
        # R5: all other instances are dynamic, also the partial instance 6700
        for dynamic in ('6100', '6101', '6102', '6201', '6400', '6300', '6301', '6600', '6601', '6700'):
            self.assertNotIn(self.key(parser, dynamic), parser.static_nodes, dynamic)
        # strict: the encoding is dynamic as well
        parser = self.make_parser(metadata=DEFAULT_HEURISTIC_NODES, strict=True)
        parser.classify_nodes()
        self.assertNotIn(self.key(parser, '6000'), parser.static_nodes)

    def test_r4_does_not_overrule_r3(self):
        # the encoding 6000 is outside of the static ranges of METADATA: R3 decides (dynamic), R4 does not apply
        parser = self.make_parser(metadata=METADATA + DEFAULT_HEURISTIC_NODES)
        parser.classify_nodes()
        encoding = self.key(parser, '6000')
        self.assertNotIn(encoding, parser.static_nodes)
        self.assertNotIn(encoding, parser.heuristic_overrides)

    def test_r1_ignores_typedefinition(self):
        # R1 looks at the Variables of the instance only: the partial instance 6700 (its type TestType declares
        # Variables, the nodeset contains none of them) stays static where the NamespaceMetadata declares it static
        metadata = METADATA.replace('<String>1:5001</String>', '<String>1:7000</String>')
        self.assertNotEqual(metadata, METADATA)
        parser = self.make_parser(metadata=metadata + DEFAULT_HEURISTIC_NODES)
        parser.classify_nodes()
        self.assertIn(self.key(parser, '6700'), parser.static_nodes)
        self.assertNotIn(self.key(parser, '6700'), parser.heuristic_overrides)

    def test_fallback_rule_with_server_uri(self):
        parser = self.make_parser(server_uri=SERVER)
        parser.classify_nodes()
        key = self.key(parser, '5002')
        self.assertEqual(parser.expanded_nodeids[key], f'svu={SERVER};nsu={TEST_NS};i=5002')
        self.assertEqual(parser.node_iris[key], iri(f'svu={SERVER};nsu={TEST_NS};i=5002'))
        # static nodes are server independent
        self.assertEqual(parser.node_iris[self.key(parser, '1001')], iri(f'nsu={TEST_NS};i=1001'))
        self.assertEqual(parser.skipped_dynamic_nodes, [])

    def test_namespace_metadata_decides(self):
        parser = self.make_parser(metadata=METADATA, strict=True)
        parser.classify_nodes()
        rule = parser.static_node_rules[TEST_NS]
        self.assertEqual(rule['types'], {0})
        self.assertEqual(rule['ranges'], [(1, 5001), (9000, 9010)])
        self.assertEqual(rule['pattern'].pattern, 'Named.*')
        # numeric: the ranges decide, also against the fallback rule
        self.assertIn(self.key(parser, '5001'), parser.static_nodes)  # instance, but in range
        self.assertNotIn(self.key(parser, '5002'), parser.static_nodes)  # outside of the ranges
        # string: the pattern decides
        self.assertIn(self.key(parser, 'Named', 'stringID'), parser.static_nodes)

    def test_heuristic_instance_with_variables(self):
        # the instance 5001 has a Variable: instance and Variable are dynamic, although NamespaceMetadata says
        # static; the same for the NamespaceMetadata object 9000 and its Variables
        parser = self.make_parser(metadata=METADATA + HEURISTIC_NODES)
        parser.imported_namespace_indices = {0}  # core is imported, its ServerCapabilities (i=2268) is dynamic
        parser.classify_nodes()
        for dynamic in ('5001', '9000', '9001', '9004', '4100'):
            self.assertNotIn(self.key(parser, dynamic), parser.static_nodes, dynamic)
            self.assertIn(self.key(parser, dynamic), parser.heuristic_overrides, dynamic)
        self.assertEqual(parser.heuristic_overrides[self.key(parser, '5001')], 'R1: instance with Variables')
        self.assertIn('R1: Variable of instance nsu=http://opcfoundation.org/UA/;i=2268',
                      parser.heuristic_overrides[self.key(parser, '4100')])
        # children of the dynamic instance 5001 which are no Variables keep the classification of R3: the folder 4200
        # (ParentNodeId 5001), the Method 4500, the dictionary entry 4300 and the HasComponent child 4600
        for static in ('4200', '4300', '4500', '4600'):
            self.assertIn(self.key(parser, static), parser.static_nodes, static)
            self.assertNotIn(self.key(parser, static), parser.heuristic_overrides, static)
        # Organizes does not influence the classification: the folder organized by 5001 stays static
        self.assertIn(self.key(parser, '4400'), parser.static_nodes)
        self.assertNotIn(self.key(parser, '4400'), parser.heuristic_overrides)
        # 5002 is outside of the ranges, dynamic anyway: no override
        self.assertNotIn(self.key(parser, '5002'), parser.heuristic_overrides)
        # types, instance declarations (1002 has the Variable 1003) and ModellingRules stay static
        for static in ('1001', '1002', '1003', '4000', '4001'):
            self.assertIn(self.key(parser, static), parser.static_nodes, static)
        # strict: only NamespaceMetadata decides
        parser = self.make_parser(metadata=METADATA + HEURISTIC_NODES, strict=True)
        parser.imported_namespace_indices = {0}
        parser.classify_nodes()
        for static in ('5001', '9000', '9001', '4100'):
            self.assertIn(self.key(parser, static), parser.static_nodes, static)
        self.assertEqual(parser.heuristic_overrides, {})

    def test_classification_report(self):
        parser = self.make_parser(metadata=METADATA)
        parser.classify_nodes()
        with tempfile.TemporaryDirectory() as tmp:
            report = os.path.join(tmp, 'report.tsv')
            parser.write_classification_report(report)
            lines = open(report).read().splitlines()
        self.assertEqual(lines[0], 'NodeId\tBrowseName\tNodeClass\tTypeDefinition\tStandard\tClassification\tReason')
        self.assertIn(f'nsu={TEST_NS};i=5001\tInstance\tObject\tns=1;i=1001\tstatic\tdynamic\t'
                      'R1: instance with Variables', lines)

    def test_explicit_static_undecided(self):
        parser = self.make_parser()
        parser.static_node_rules = {TEST_NS: {'types': {0}, 'ranges': [], 'pattern': None}}
        self.assertTrue(parser.explicit_static(TEST_NS, 'i', '77'))  # numeric listed, no ranges
        self.assertIsNone(parser.explicit_static(TEST_NS, 's', 'x'))  # strings: not decided -> fallback
        self.assertIsNone(parser.explicit_static('http://other.org/', 'i', '1'))  # no metadata

    def test_node_iri_of_foreign_nodes(self):
        parser = self.make_parser()
        parser.classify_nodes()
        numeric = BASE['numericID']
        # node of a namespace which no import exports: assumed static
        self.assertEqual(parser.node_iri(0, '2253', numeric), URIRef('http://opcfoundation.org/UA/aT0yMjUz'))
        # namespace exported by an import, node not contained: dynamic, not exported without server URI
        parser.imported_namespace_indices = {0}
        parser.unknown_nodes = set()
        self.assertIsNone(parser.node_iri(0, '11715', numeric))
        # ... but referenced as dynamic node of the given server
        parser.server_uri = SERVER
        parser.unknown_nodes = set()
        expected = URIRef('http://opcfoundation.org/UA/' + utils.base64url_nopad(f'svu={SERVER};i=11715'))
        self.assertEqual(parser.node_iri(0, '11715', numeric), expected)
        self.assertIn(expected, parser.foreign_dynamic_iris)
        # node exported by an import: its IRI is taken from there
        imported = URIRef('http://opcfoundation.org/UA/aT0zMQ')
        parser.nodeIds[0]['31'] = imported
        self.assertEqual(parser.node_iri(0, '31', numeric), imported)
        self.assertNotIn(imported, parser.foreign_dynamic_iris)
        # ... and dynamic if the import was built with a server URI
        parser.ig.add((imported, UARDF['serverUri'], Literal(SERVER)))
        parser.node_iri(0, '31', numeric)
        self.assertIn(imported, parser.foreign_dynamic_iris)

    def test_localized_text(self):
        parser = self.make_parser()
        element = ET.fromstring('<DisplayName Locale="de">Pumpe</DisplayName>')
        self.assertEqual(parser.localized_text(element), Literal('Pumpe', lang='de'))
        element = ET.fromstring('<DisplayName>Pump</DisplayName>')
        self.assertEqual(parser.localized_text(element), Literal('Pump', lang='en'))
        element = ET.fromstring('<Description Locale=" ">Pump</Description>')
        self.assertEqual(parser.localized_text(element), Literal('Pump', lang='en'))
        self.assertIsNone(parser.localized_text(ET.fromstring('<Description />')))
        self.assertIsNone(parser.localized_text(None))

    def test_add_uardf_parent(self):
        parser = self.make_parser()
        parser.classify_nodes()
        child = URIRef('http://child')
        declaration = parser.root.find("opcua:UAVariable[@NodeId='ns=1;i=1003']", parser.xml_ns)
        parser.add_uardf_parent(declaration, child)
        self.assertIn((child, UARDF['parent'], iri(f'nsu={TEST_NS};i=1002')), parser.g)
        # parent is a not exported dynamic node: no triple
        parser.g = Graph()
        instance_child = parser.root.find("opcua:UAVariable[@NodeId='ns=1;i=5002']", parser.xml_ns)
        parser.add_uardf_parent(instance_child, child)
        self.assertEqual(len(parser.g), 0)

    def test_add_nodeid_to_class_dynamic_node(self):
        parser = self.make_parser(server_uri=SERVER)
        parser.classify_nodes()
        node = parser.root.find("opcua:UAObject[@NodeId='ns=1;i=5001']", parser.xml_ns)
        _, classiri = parser.add_nodeid_to_class(node, 'ObjectNodeClass', parser.xml_ns)
        self.assertEqual(classiri, iri(f'svu={SERVER};nsu={TEST_NS};i=5001'))
        self.assertIn((classiri, RDF.type, UARDF['Object']), parser.g)
        # the IRI contains the server URI, uardf:nodeId does not (the server is in uardf:serverUri)
        self.assertIn((classiri, UARDF['nodeId'], Literal(f'nsu={TEST_NS};i=5001')), parser.g)
        self.assertIn((classiri, UARDF['serverUri'], Literal(SERVER)), parser.g)
        self.assertIn((classiri, UARDF['browseName'], Literal(f'nsu={TEST_NS};Instance')), parser.g)
        self.assertIn((classiri, UARDF['name'], Literal('Instance')), parser.g)
        self.assertIn((classiri, UARDF['symbolicName'], Literal('Instance')), parser.g)  # defaults to BrowseName
        self.assertIn((classiri, UARDF['displayName'], Literal('Instance', lang='en')), parser.g)
        # not exported without server URI
        parser = self.make_parser()
        parser.classify_nodes()
        self.assertIsNone(parser.add_nodeid_to_class(node, 'ObjectNodeClass', parser.xml_ns)[1])
        self.assertEqual(len(parser.g), 0)

    def test_restrict_to_dynamic_nodes(self):
        parser = self.make_parser(server_uri=SERVER)
        parser.ontology_name = URIRef(TEST_NS)
        parser.classify_nodes()
        static = parser.node_iris[self.key(parser, '1001')]
        dynamic = parser.node_iris[self.key(parser, '5001')]
        foreign = URIRef('http://opcfoundation.org/UA/foreignDynamic')
        parser.foreign_dynamic_iris.add(foreign)
        bridge = URIRef(TEST_NS + 'hasInstance')
        g = parser.g
        g.add((URIRef(TEST_NS), RDF.type, OWL.Ontology))
        g.add((URIRef(TEST_NS), OWL.versionIRI, URIRef('http://example.com/v0.1/test/')))
        g.add((URIRef(TEST_NS + 'TESTNamespace'), RDF.type, BASE['Namespace']))
        g.add((static, UARDF['name'], Literal('TestType')))  # static part
        g.add((dynamic, UARDF['name'], Literal('Instance')))  # dynamic part
        g.add((static, OPCUA['Organizes'], dynamic))  # static -> dynamic: server specific
        g.add((static, bridge, dynamic))
        g.add((bridge, RDF.type, OWL.ObjectProperty))
        g.add((bridge, RDFS.subPropertyOf, UARDF['semanticBridgeReferenceType']))
        g.add((foreign, OPCUA['HasComponent'], static))  # static linked from a foreign dynamic node
        values = BNode()
        Collection(g, values, [Literal(1), Literal(2)])
        g.add((dynamic, BASE['hasValueList'], values))
        parser.restrict_to_dynamic_nodes(['http://example.com/static.owl.ttl'])
        self.assertNotIn((static, UARDF['name'], Literal('TestType')), g)
        for triple in ((dynamic, UARDF['name'], Literal('Instance')), (static, OPCUA['Organizes'], dynamic),
                       (static, bridge, dynamic), (bridge, RDF.type, OWL.ObjectProperty),
                       (bridge, RDFS.subPropertyOf, UARDF['semanticBridgeReferenceType']),
                       (foreign, OPCUA['HasComponent'], static),
                       (URIRef(TEST_NS + 'TESTNamespace'), RDF.type, BASE['Namespace'])):
            self.assertIn(triple, g)
        # own ontology header, importing the static export
        dynamic_ontology = utils.expanded_nodeid_to_iri(TEST_NS, f'svu={SERVER}')
        self.assertNotIn((URIRef(TEST_NS), RDF.type, OWL.Ontology), g)
        self.assertIn((dynamic_ontology, RDF.type, OWL.Ontology), g)
        self.assertIn((dynamic_ontology, OWL.versionIRI,
                       utils.expanded_nodeid_to_iri('http://example.com/v0.1/test/', f'svu={SERVER}')), g)
        self.assertIn((dynamic_ontology, OWL.imports, URIRef('http://example.com/static.owl.ttl')), g)
        self.assertEqual(list(Collection(g, values)), [Literal(1), Literal(2)])

    def test_dynamic_ontology_iri(self):
        # base64url('svu=urn:a') = 'c3Z1PXVybjph'
        self.assertEqual(NodesetParser.dynamic_ontology_iri('http://opcfoundation.org/UA/', 'urn:a'),
                         URIRef('http://opcfoundation.org/UA/c3Z1PXVybjph'))
        self.assertEqual(NodesetParser.dynamic_ontology_iri('http://example.com/v0.1/PADIM', 'urn:a'),
                         URIRef('http://example.com/v0.1/PADIM/c3Z1PXVybjph'))
        self.assertNotEqual(NodesetParser.dynamic_ontology_iri('http://opcfoundation.org/UA/', 'urn:a'),
                            NodesetParser.dynamic_ontology_iri('http://opcfoundation.org/UA/', 'urn:b'))


if __name__ == '__main__':
    unittest.main()
