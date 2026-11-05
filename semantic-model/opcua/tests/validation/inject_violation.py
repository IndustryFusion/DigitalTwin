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
"""Add a violation of the HasComponent rule to an ontology: a type as target of a HasComponent reference."""
import sys
from rdflib import Graph, Namespace
from rdflib.namespace import RDF

UARDF = Namespace('http://opcfoundation.org/rdf/uacore#')
OPCUA = Namespace('http://opcfoundation.org/UA/')

graph = Graph()
graph.parse(sys.argv[1])
source = next(graph.subjects(RDF.type, UARDF.Object))
target = next(graph.subjects(RDF.type, UARDF.ObjectType))
graph.add((source, OPCUA.HasComponent, target))
graph.serialize(sys.argv[2])
