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

import unittest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS
import lib.utils as utils
from lib.composition import compose, composed_ontology_iri, server_of_dynamic_header

NS = 'http://example.org/di/'
STATIC_NODE = URIRef(NS + 'static')
ORGANIZES = URIRef('http://opcfoundation.org/UA/Organizes')


def static_graph():
    g = Graph()
    g.add((URIRef(NS), RDF.type, OWL.Ontology))
    g.add((URIRef(NS), OWL.versionIRI, URIRef('http://example.com/v0.1/di/')))
    g.add((URIRef(NS), OWL.versionInfo, Literal(0.1)))
    g.add((URIRef(NS), OWL.imports, URIRef('file:///build/core.owl.ttl')))
    g.add((URIRef(NS), OWL.imports, URIRef('https://example.org/base.ttl')))
    g.add((STATIC_NODE, utils.UARDF['name'], Literal('Type')))
    return g


def dynamic_graph(server):
    g = Graph()
    header = utils.expanded_nodeid_to_iri(NS, f'svu={server}')
    node = utils.expanded_nodeid_to_iri(NS, f'svu={server};nsu={NS};i=5001')
    g.add((header, RDF.type, OWL.Ontology))
    g.add((header, OWL.imports, URIRef('file:///build/di.owl.ttl')))
    g.add((node, utils.UARDF['serverUri'], Literal(server)))
    g.add((STATIC_NODE, ORGANIZES, node))
    return g, node


class TestComposition(unittest.TestCase):
    def test_compose_servers(self):
        dynamic1, node1 = dynamic_graph('urn:server:1')
        dynamic2, node2 = dynamic_graph('urn:server:2')
        composed = compose(static_graph(), [dynamic1, dynamic2], {'core.owl.ttl': 'core.owl.all.ttl'})
        header = composed_ontology_iri(NS)
        self.assertEqual(header, URIRef(NS + 'all'))
        self.assertEqual(list(composed.subjects(RDF.type, OWL.Ontology)), [header])
        # content of all parts: one static node, organizing the dynamic node of each server
        self.assertIn((STATIC_NODE, utils.UARDF['name'], Literal('Type')), composed)
        self.assertEqual(set(composed.objects(STATIC_NODE, ORGANIZES)), {node1, node2})
        # header: versionIRI + all, imports of the static part with the mapped dependencies
        self.assertIn((header, OWL.versionIRI, URIRef('http://example.com/v0.1/di/all')), composed)
        self.assertIn((header, OWL.versionInfo, Literal(0.1)), composed)
        imports = set(composed.objects(header, OWL.imports))
        self.assertEqual(imports, {utils.file_path_to_uri('core.owl.all.ttl'), URIRef('https://example.org/base.ttl')})
        self.assertIn('urn:server:1, urn:server:2', str(composed.value(header, RDFS.comment)))

    def test_compose_static_only(self):
        composed = compose(static_graph(), [])
        self.assertEqual(len(composed) - len(static_graph()), 1)  # rdfs:comment of the header

    def test_server_of_dynamic_header(self):
        header = utils.expanded_nodeid_to_iri(NS, 'svu=urn:server:1')
        self.assertEqual(server_of_dynamic_header(URIRef(NS), header), 'urn:server:1')
        for wrong in (URIRef(NS), URIRef(NS + 'aT0x'), utils.expanded_nodeid_to_iri('http://other/', 'svu=urn:a'),
                      utils.expanded_nodeid_to_iri(NS, f'svu=urn:a;nsu={NS};i=1')):
            with self.assertRaises(ValueError):
                server_of_dynamic_header(URIRef(NS), wrong)


if __name__ == '__main__':
    unittest.main()
