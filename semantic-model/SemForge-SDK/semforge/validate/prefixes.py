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

"""The prefixes a SPARQL text's `sh:prefixes` declares, as SHACL 5.2.1 says it.

The declarations of a query are the `sh:declare` values of the nodes its
`sh:prefixes` names -- several, IRIs or blank nodes, `owl:Ontology` or not --
and of everything those reach through `owl:imports`, within the shapes graph.

pyshacl reads them differently: it follows no import, and a query whose
`sh:prefixes` names a node that is not an `owl:Ontology` gets the prefixes of
every ontology of the graph as well. So a graph made for pyshacl is completed
with `complete`; what reads a query's prefixes itself asks `declared`.
"""

from rdflib.namespace import OWL, RDF, SH


def closure(graph, holder):
    """`holder` and what it imports, directly or not."""
    found, todo = set(), [holder]
    while todo:
        node = todo.pop()
        if node not in found:
            found.add(node)
            todo.extend(graph.objects(node, OWL.imports))
    return found


def declarations(graph, holder):
    """The prefix declaration nodes of `holder` and of what it imports."""
    return {d for node in closure(graph, holder) for d in graph.objects(node, SH.declare)}


def declared(graph, query):
    """The sorted (prefix, namespace) texts `sh:prefixes` of `query` declares."""
    found = {(graph.value(d, SH.prefix), graph.value(d, SH.namespace))
             for holder in graph.objects(query, SH.prefixes)
             for d in declarations(graph, holder)}
    return sorted((str(p), str(n)) for p, n in found if p is not None and n is not None)


def lines(graph, query):
    """`sh:prefixes` of `query` as PREFIX lines, to put in front of its text."""
    return [f'PREFIX {p}: <{n}>' for p, n in declared(graph, query)]


def complete(out, shapes_graph):
    """Give the queries in `out`, a copy or a part of `shapes_graph` made for
    pyshacl, the prefixes they declare: each node `sh:prefixes` names gets every
    declaration of its closure as its own, and is called an `owl:Ontology`,
    which is how pyshacl is told to read that node alone. One that declares
    nothing is no longer named: pyshacl would read every ontology instead."""
    for holder in set(out.objects(None, SH.prefixes)):
        found = declarations(shapes_graph, holder)
        if not found:
            out.remove((None, SH.prefixes, holder))
            continue
        out.add((holder, RDF.type, OWL.Ontology))
        for declaration in found:
            out.add((holder, SH.declare, declaration))
            for predicate in (SH.prefix, SH.namespace):
                for value in shapes_graph.objects(declaration, predicate):
                    out.add((declaration, predicate, value))
