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
"""How owl2instances.py turns the attribute keys of the instances into IRIs (opcua/instance-coverage)."""
import unittest
from types import SimpleNamespace
from unittest import mock

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from lib.entity import Entity
import owl2instances

DI = Namespace('http://opcfoundation.org/UA/DI/')
OPCUA = Namespace('http://opcfoundation.org/UA/')
BASE = Namespace('https://industryfusion.github.io/contexts/ontology/v0/base/')
TEST = Namespace('http://my.test/')
UACORE = Namespace('http://opcfoundation.org/rdf/uacore#')
GLOBALS = ('g', 'context_graph', 'basens', 'opcuans', 'e')


class TestAttributeKeys(unittest.TestCase):
    def setUp(self):
        # the instance ontology names DI 'di'; the published context names it 'devices'
        self.g = Graph()
        self.g.bind('di', DI)
        self.g.bind('opcua', OPCUA)
        self.g.add((DI.ConnectsTo, RDF.type, OWL.ObjectProperty))
        self.g.add((DI.ConnectsTo, RDFS.subPropertyOf, OPCUA.NonHierarchicalReferences))
        self.g.add((OPCUA.NonHierarchicalReferences, RDFS.subPropertyOf, OPCUA.References))
        # a semantic bridge attribute is a sub-property too, but not of References
        self.g.add((TEST.hasLevel, RDFS.subPropertyOf, UACORE.semanticBridgeReferenceType))
        self.context = Graph()
        self.context.bind('devices', DI)
        self.context.bind('test', TEST)
        # the module globals exist only once its main code ran; the test provides them
        self.saved = tuple(getattr(owl2instances, name, None) for name in GLOBALS)
        self.e = Entity('http://my.test/', BASE, OPCUA)
        for name, value in zip(GLOBALS, (self.g, self.context, BASE, OPCUA, self.e)):
            setattr(owl2instances, name, value)

    def tearDown(self):
        for name, value in zip(GLOBALS, self.saved):
            setattr(owl2instances, name, value)

    def test_key_with_the_contexts_prefix(self):
        self.assertEqual(owl2instances.attribute_iri('test:hasLevel'), TEST.hasLevel)
        self.assertEqual(owl2instances.attribute_iri('devices:ConnectsTo'), DI.ConnectsTo)

    def test_reference_key_with_the_ontologys_prefix(self):
        # Organizes and non-hierarchical reference keys come from g.qname: 'di' is unknown to the context
        self.assertEqual(owl2instances.attribute_iri('di:ConnectsTo'), DI.ConnectsTo)

    def test_absolute_iri(self):
        self.assertEqual(owl2instances.attribute_iri('http://my.test/hasLevel'), URIRef('http://my.test/hasLevel'))

    def test_declared_attributes(self):
        # the declaration of an entity's attributes resolves the keys the same way
        owl2instances.declare_attributes({'id': 'urn:x', 'type': 'test:AType', 'di:ConnectsTo': [],
                                          'test:hasLevel': {}},
                                         TEST.AType)
        declared = set(self.e.get_graph().subject_objects(RDFS.domain))
        self.assertEqual(declared, {(DI.ConnectsTo, OPCUA.BaseObjectType), (TEST.hasLevel, TEST.AType)})

    def test_report_resolves_the_keys(self):
        # ConnectsTo is declared, so the report must not call it undeclared because its prefix is unknown
        self.e.add_instancetype(OPCUA.BaseObjectType, DI.ConnectsTo)
        self.g.add((TEST.AType, RDFS.subClassOf, OPCUA.BaseObjectType))
        instances = [{'id': 'urn:x', 'type': 'test:AType', 'di:ConnectsTo': []}]
        with mock.patch.multiple(owl2instances, create=True, jsonld=SimpleNamespace(instances=instances),
                                 shaclg=SimpleNamespace(get_graph=Graph), rdfutils=None,
                                 ignored_hierarchical_references=[], ignored_references=[]), \
                mock.patch.object(owl2instances.coverage, 'lacks_shape', return_value=False), \
                mock.patch.object(owl2instances, 'print_warning') as warning:
            owl2instances.report_uncovered_terms()
        message = warning.call_args[0][1]
        self.assertIn('not constrained: devices:ConnectsTo', message)
        self.assertNotIn('not declared', message)

    def test_reference_attributes(self):
        self.assertTrue(owl2instances.is_reference_attribute(DI.ConnectsTo))
        self.assertTrue(owl2instances.is_reference_attribute(BASE.hasNodeRef))
        self.assertFalse(owl2instances.is_reference_attribute(TEST.hasLevel))


if __name__ == '__main__':
    unittest.main()
