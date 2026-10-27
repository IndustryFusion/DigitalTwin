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

"""Make tests/corpus/opcua-pumps from a package of the OPC UA pump example.

    python tests/corpus/slice_opcua.py <opcua-kms package> [<out>]

The OPC UA tool chain writes 12.8 MB of knowledge for the pumps; its shapes
and model are small. The slice keeps what the generator wrote, as written:
shacl.ttl, model-instance.jsonld, semforge.yaml and the test cases whole, and
of every knowledge file the statements about what the shapes and the model
name -- with the superclasses, the property declarations and the individuals
of every class a value must be. The files stay separate: a knowledge
directory of several files is part of what is tested.
"""

import os
import re
import shutil
import sys

from rdflib import Graph, RDF, RDFS, URIRef
from rdflib.namespace import OWL, SH

KEEP = ('shacl.ttl', 'model-instance.jsonld', 'semforge.yaml')
IRI = re.compile(r'<(https?://[^>\s]+)>|"(https?://[^"\s]+)"')


def _named(text, prefixes):
    """Every IRI a text names: written whole, or as a prefixed name."""
    found = {a or b for a, b in IRI.findall(text)}
    for prefix, namespace in prefixes.items():
        for local in re.findall(r'(?<![\w/#])' + re.escape(prefix) + r':([\w.-]+)', text):
            found.add(namespace + local.rstrip('.'))
    return {URIRef(iri) for iri in found}


def main(source, out):
    knowledge_dir = os.path.join(source, 'knowledge')
    files = sorted(f for f in os.listdir(knowledge_dir) if f.endswith('.ttl'))
    graphs = {}
    for name in files:
        graph = Graph()
        graph.parse(os.path.join(knowledge_dir, name), format='turtle')
        graphs[name] = graph
    merged = Graph()
    for graph in graphs.values():
        merged += graph

    shapes = Graph().parse(os.path.join(source, 'shacl.ttl'), format='turtle')
    prefixes = {str(p): str(n) for p, n in shapes.namespaces()}
    for graph in graphs.values():
        prefixes.update({str(p): str(n) for p, n in graph.namespaces()})
    seeds = {o for o in shapes.objects() if isinstance(o, URIRef)}
    seeds |= {s for s in shapes.subjects() if isinstance(s, URIRef)}
    with open(os.path.join(source, 'model-instance.jsonld'), encoding='utf-8') as handle:
        seeds |= _named(handle.read(), prefixes)
    for root, _, names in os.walk(os.path.join(source, 'examples')):
        for name in names:
            with open(os.path.join(root, name), encoding='utf-8') as handle:
                seeds |= _named(handle.read(), prefixes)

    # The classes a value must be: their individuals are what a test picks.
    valued = {o for o in shapes.objects(None, SH['class'])} | \
             {o for o in merged.objects(None, RDFS.range) if (o, RDF.type, OWL.Class) in merged}
    keep, pending = set(), [s for s in seeds if (s, None, None) in merged]
    while pending:
        node = pending.pop()
        if node in keep:
            continue
        keep.add(node)
        for predicate in (RDFS.subClassOf, RDFS.domain, RDFS.range, RDF.type,
                          RDFS.subPropertyOf):
            for o in merged.objects(node, predicate):
                if isinstance(o, URIRef) and (o, None, None) in merged:
                    pending.append(o)
        if node in valued:
            for individual in merged.subjects(RDF.type, node):
                if isinstance(individual, URIRef):
                    pending.append(individual)

    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, 'knowledge'))
    for name, graph in graphs.items():
        sliced = Graph()
        for prefix, namespace in graph.namespaces():
            sliced.bind(prefix, namespace)
        for subject in keep:
            for triple in graph.cbd(subject):
                sliced.add(triple)
        sliced.serialize(os.path.join(out, 'knowledge', name), format='turtle')
        print(f'knowledge/{name}: {len(graph)} -> {len(sliced)} triples')
    for name in KEEP:
        if os.path.exists(os.path.join(source, name)):
            shutil.copy(os.path.join(source, name), os.path.join(out, name))
    if os.path.isdir(os.path.join(source, 'examples')):
        shutil.copytree(os.path.join(source, 'examples'), os.path.join(out, 'examples'))


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, 'opcua-pumps'))
