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

"""Parsed Turtle, kept: a file is parsed once per content.

Loading the OPC UA pump package spent most of its 7 s in rdflib's Turtle
parser, on ontologies that never change between loads -- and the editor's
validation worker loads the package again after every edit. A triple list read
back from JSON builds the same graph in about half the time (measured:
pumps.owl.ttl 4.5 s -> 2.2 s, core.owl.ttl 3.9 s -> 1.3 s); what remains is
rdflib building its indexes, which no format avoids.

* Keyed by the file's CONTENT (sha256), the rdflib version and this format's
  version: an edit, a checkout or an rdflib upgrade simply misses.
* JSON, never pickle: the cache sits in the package directory, and a cloned
  package must not be able to run code by shipping one.
* Blank nodes are fresh on every load, as they are from a parse; the file's
  prefixes are bound again, in its order, because shape names are shown
  through them.
* In `.semforge/cache/graphs/`, which carries its own `.gitignore`; an entry
  replaces the previous one for the same file, so the cache holds one version
  per file.
"""

import os

import rdflib
from rdflib import BNode, Literal, URIRef

from ..rdfio.derived import entry_name, read_entry, write_entry

FORMAT = 2
GRAPHS = os.path.join('.semforge', 'cache', 'graphs')


def graphs_dir(package_path):
    return os.path.join(package_path, GRAPHS)


def _out(term):
    if isinstance(term, URIRef):
        return ['u', str(term)]
    if isinstance(term, BNode):
        return ['b', str(term)]
    return ['l', str(term), str(term.datatype) if term.datatype else '', term.language or '']


def _declared_prefixes(text):
    from ..rdfio.turtle_index import _prefixes

    return list(_prefixes(text)[0].items())


def _read(stored, graph):
    if not isinstance(stored, dict) or stored.get('format') != FORMAT or stored.get('rdflib') != rdflib.__version__:
        return False
    # Every distinct term once, then each triple as three indexes into them.
    # Blank nodes come back fresh, one per label, as from a parse.
    terms = []
    for row in stored['terms']:
        if row[0] == 'u':
            terms.append(URIRef(row[1]))
        elif row[0] == 'b':
            terms.append(BNode())
        else:
            terms.append(Literal(row[1], datatype=URIRef(row[2]) if row[2] else None,
                                 lang=row[3] or None))
    for prefix, namespace in stored['prefixes']:
        graph.bind(prefix, namespace)
    flat = stored['triples']
    graph.addN((terms[flat[i]], terms[flat[i + 1]], terms[flat[i + 2]], graph)
               for i in range(0, len(flat), 3))
    return True


def _payload(graph_of_file, prefixes):
    index, terms, flat = {}, [], []
    for triple in graph_of_file:
        for term in triple:
            position = index.get(term)
            if position is None:
                position = index[term] = len(terms)
                terms.append(_out(term))
            flat.append(position)
    return {'format': FORMAT, 'rdflib': rdflib.__version__, 'prefixes': prefixes,
            'terms': terms, 'triples': flat}


def parse_turtle(graph, path, package_path):
    """Add the triples of a Turtle file to `graph`, from the cache when it holds
    this content. Bad Turtle raises exactly as rdflib's parse does."""
    from rdflib import Graph

    with open(path, 'rb') as handle:
        data = handle.read()
    directory = graphs_dir(package_path)
    slug, name = entry_name(path, data)
    stored = read_entry(directory, name)
    if stored is not None:
        try:
            if _read(stored, graph):
                return graph
        except (KeyError, TypeError, IndexError, ValueError):
            pass                                   # torn or foreign: parse again

    parsed = Graph()
    parsed.parse(path, format='turtle')
    prefixes = _declared_prefixes(data.decode('utf-8', errors='replace'))
    for prefix, namespace in prefixes:
        graph.bind(prefix, namespace)
    graph.addN((s, p, o, graph) for s, p, o in parsed)
    write_entry(directory, slug, name, _payload(parsed, prefixes), 'Parsed Turtle, kept')
    return graph
