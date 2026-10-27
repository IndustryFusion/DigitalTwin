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

"""What the constraints can read: the knowledge cut down to it.

The knowledge is merged into the data before validation, so `sh:class` and
the targets see the types it declares. On the OPC UA pump package that is
217,582 triples against 277 of data -- browse names, node ids, display names
of 9,600 OPC UA nodes -- and the rule fixpoint, the NGSI-LD view and pyshacl
all walk every one of them, though no constraint reads any. Validation time
follows the size of that graph, not the number of shapes: one shape against
all of it took longer than every shape against the types alone.

So the knowledge is cut to the triples whose predicate some constraint can
read. That is decided from the shapes alone, and soundly:

* `rdf:type` and `rdfs:subClassOf` are always kept: targets and `sh:class`
  read them, and SHACL's class semantics is exactly that pair;
* every predicate named in a `sh:path`, however nested (sequence, inverse,
  alternative, `*`/`+`/`?`) -- which also covers the node expressions of
  SHACL-AF rules and `sh:values`;
* the predicate-valued parameters: `sh:equals`, `sh:disjoint`, `sh:lessThan`,
  `sh:lessThanOrEquals`, `sh:targetSubjectsOf`, `sh:targetObjectsOf`;
* every predicate a SPARQL text (constraint, target, rule) uses in a triple
  pattern or a property path -- not in a CONSTRUCT template, which writes.

A query that can read ANY predicate -- a variable in predicate position, a
negated property set -- or one that does not parse, or a constraint language
this cannot see into (JavaScript), makes the cut unknowable: the whole
knowledge is used. Never a guess. `$PATH` in a SPARQL-based constraint
component stands for a `sh:path`, which is collected anyway.
"""

from rdflib import BNode, Graph, URIRef, Variable
from rdflib.collection import Collection
from rdflib.namespace import RDF, RDFS, SH

ALWAYS = frozenset({RDF.type, RDFS.subClassOf})

PREDICATE_PARAMETERS = (SH.equals, SH.disjoint, SH.lessThan, SH.lessThanOrEquals,
                        SH.targetSubjectsOf, SH.targetObjectsOf)

PATH_OPERATORS = (SH.inversePath, SH.zeroOrMorePath, SH.oneOrMorePath, SH.zeroOrOnePath)

QUERIES = (SH.select, SH.ask, SH.construct)

# Constraint languages whose reads cannot be seen from here.
OPAQUE = (URIRef(str(SH) + 'jsFunctionName'), URIRef(str(SH) + 'jsLibrary'))

STAND_IN = {'PATH'}       # pre-bound by SPARQL-based constraint components


class Unbounded(Exception):
    """A constraint can read any predicate: the cut is not knowable."""


def _path_predicates(shapes, path, seen=None):
    seen = seen if seen is not None else set()
    if isinstance(path, URIRef):
        return {path}
    if not isinstance(path, BNode) or path in seen:
        return set()
    seen.add(path)
    found = set()
    if (path, RDF.first, None) in shapes:                    # a sequence path
        for member in Collection(shapes, path):
            found |= _path_predicates(shapes, member, seen)
        return found
    for operator in PATH_OPERATORS:
        for inner in shapes.objects(path, operator):
            found |= _path_predicates(shapes, inner, seen)
    for alternatives in shapes.objects(path, SH.alternativePath):
        for member in Collection(shapes, alternatives):
            found |= _path_predicates(shapes, member, seen)
    return found


def _namespaces(shapes, node):
    """The prefixes a SPARQL text may use: the shapes graph's, and the
    sh:prefixes declarations of the node that carries it."""
    found = {prefix: namespace for prefix, namespace in shapes.namespaces()}
    for ontology in shapes.objects(node, SH.prefixes):
        for declaration in shapes.objects(ontology, SH.declare):
            prefix = shapes.value(declaration, SH.prefix)
            namespace = shapes.value(declaration, SH.namespace)
            if prefix is not None and namespace is not None:
                found[str(prefix)] = URIRef(str(namespace))
    return found


def _walk_algebra(node, found, template=False):
    """Collect predicates from every triple pattern and path in the algebra."""
    from rdflib.paths import NegatedPath, Path
    from rdflib.plugins.sparql.parserutils import CompValue

    if isinstance(node, CompValue):
        if node.name == 'BGP':
            for _, predicate, _ in node.get('triples', []):
                _predicate(predicate, found)
        elif node.name == 'TriplesBlock':
            # Inside FILTER (NOT) EXISTS rdflib keeps the parser's form: each
            # entry is s p o s p o ... flattened. Missed, `?v base:isValidFor ?s`
            # in a NOT EXISTS was cut away and a constraint fired that did not.
            for flat in node.get('triples', []):
                for predicate in list(flat)[1::3]:
                    _predicate(predicate, found)
        for key, value in node.items():
            # A CONSTRUCT template is what the query writes, not what it reads.
            if key == 'template':
                continue
            _walk_algebra(value, found)
    elif isinstance(node, (list, tuple, set)):
        for value in node:
            _walk_algebra(value, found)
    elif isinstance(node, NegatedPath):
        raise Unbounded('a negated property set reads every other predicate')
    elif isinstance(node, Path):
        _predicate(node, found)
    elif isinstance(node, URIRef):
        # Every IRI the query names counts as one it may read, wherever it
        # stands: a form of the algebra this walk does not know (the bug
        # above was one) then costs some kept triples, never a wrong verdict.
        found.add(node)


def _predicate(predicate, found):
    from rdflib.paths import AlternativePath, InvPath, MulPath, NegatedPath, SequencePath

    if isinstance(predicate, URIRef):
        found.add(predicate)
    elif isinstance(predicate, Variable):
        if str(predicate) not in STAND_IN:
            raise Unbounded(f'?{predicate} in predicate position reads any predicate')
    elif isinstance(predicate, NegatedPath):
        raise Unbounded('a negated property set reads every other predicate')
    elif isinstance(predicate, (SequencePath, AlternativePath)):
        for arg in predicate.args:
            _predicate(arg, found)
    elif isinstance(predicate, (InvPath, MulPath)):
        _predicate(predicate.arg if isinstance(predicate, InvPath) else predicate.path, found)
    else:
        raise Unbounded(f'a predicate this cannot read: {predicate!r}')


def query_predicates(text, namespaces=None):
    """The predicates a SPARQL text reads. Raises Unbounded when that is any."""
    from rdflib.plugins.sparql import prepareQuery

    try:
        query = prepareQuery(text, initNs=namespaces or {})
    except Exception as exc:                       # noqa: BLE001
        raise Unbounded(f'a query that does not parse here: {exc}') from exc
    found = set()
    _walk_algebra(query.algebra, found)
    return found


def read_set(shapes):
    """Every predicate the shapes can read, or None when that is any.

    Kept with a frozen shapes graph (rdfio/frozen.py): parsing its SPARQL is
    most of the cost.
    """
    from ..rdfio.frozen import derived

    return derived(shapes, 'read_set', lambda: _read_set(shapes))


def _read_set(shapes):
    for opaque in OPAQUE:
        if (None, opaque, None) in shapes:
            return None
    found = set(ALWAYS)
    for path in shapes.objects(None, SH.path):
        found |= _path_predicates(shapes, path)
    for parameter in PREDICATE_PARAMETERS:
        found |= {o for o in shapes.objects(None, parameter) if isinstance(o, URIRef)}
    try:
        for kind in QUERIES:
            for node, text in shapes.subject_objects(kind):
                found |= query_predicates(str(text), _namespaces(shapes, node))
    except Unbounded:
        return None
    return frozenset(found)


def cut(knowledge, predicates):
    """The knowledge triples whose predicate is in `predicates` (None: all)."""
    if knowledge is None or predicates is None:
        return knowledge
    out = Graph()
    for prefix, namespace in knowledge.namespaces():
        out.bind(prefix, namespace)
    for predicate in predicates:
        for triple in knowledge.triples((None, predicate, None)):
            out.add(triple)
    return out


def knowledge_for(shapes, knowledge):
    """The knowledge these shapes can read: all of it when that is unknowable.

    Not cached: a graph edited in place keeps its identity and often its size,
    and a stale cut is a wrong verdict. Cutting reads the predicate index
    only, so it costs a fraction of what it saves.
    """
    if knowledge is None:
        return None
    return cut(knowledge, read_set(shapes))


# Targets that pick focus nodes by something other than their type: what they
# select cannot be told from the data alone, so near() does not apply.
UNANCHORED = (SH.targetSubjectsOf, SH.targetObjectsOf, SH.target, SH.rule, SH.sparql)


def anchored(shapes):
    """Whether near() can narrow the knowledge for these shapes."""
    return read_set(shapes) is not None and \
        not any((None, p, None) in shapes for p in UNANCHORED)


def run_knowledge(shapes, knowledge):
    """The knowledge to validate a package's graphs against, each with
    validate_graphs(cut=False): the whole of it when near() narrows it per
    graph -- cutting 217,582 triples first cost 0.6 s and changes nothing near()
    keeps -- else the cut, made once for all of them."""
    return knowledge if anchored(shapes) else knowledge_for(shapes, knowledge)


def near(shapes, knowledge, data):
    """The knowledge a validation of `data` can reach -- or None when that is
    not knowable, and the caller keeps what it has.

    A test case of one entity was validated against the 31,356 knowledge
    triples of the OPC UA pump package, copied through every step: 2.2 s for
    22 triples of data. What it can actually touch is what is reachable from
    its own nodes:

    * from every node of the data, and every knowledge node a shape targets by
      class (so a targeted knowledge entity is validated as before);
    * along the predicates the shapes read (see read_set) -- forward, and
      backward for those named under sh:inversePath;
    * with the rdf:type of everything reached, and the whole rdfs:subClassOf
      hierarchy, which targets and sh:class read.

    A SPARQL constraint can read any triple, and a target by subject, object
    or SPARQL picks nodes the data does not name: with any of them the answer
    is None.
    """
    from rdflib import Literal
    from rdflib.namespace import OWL

    if knowledge is None or not anchored(shapes):
        return None
    predicates = read_set(shapes)
    forward = set(predicates) - {RDF.type, RDFS.subClassOf}
    backward = set()
    for path in shapes.objects(None, SH.inversePath):
        backward |= _path_predicates(shapes, path)

    # The classes targeted, and every class below them.
    classes = set(shapes.objects(None, SH.targetClass))
    classes |= {s for s in shapes.subjects(RDF.type, SH.NodeShape)
                if (s, RDF.type, RDFS.Class) in shapes or (s, RDF.type, OWL.Class) in shapes}
    todo = list(classes)
    while todo:
        for sub in knowledge.subjects(RDFS.subClassOf, todo.pop()):
            if sub not in classes:
                classes.add(sub)
                todo.append(sub)

    start = set(data.subjects()) | {o for o in data.objects() if not isinstance(o, Literal)}
    start |= set(shapes.objects(None, SH.targetNode))
    for cls in classes:
        start.update(knowledge.subjects(RDF.type, cls))

    out = Graph()
    for prefix, namespace in knowledge.namespaces():
        out.bind(prefix, namespace)
    seen, todo = set(start), list(start)
    while todo:
        node = todo.pop()
        for predicate, obj in knowledge.predicate_objects(node):
            if predicate in forward:
                out.add((node, predicate, obj))
                if not isinstance(obj, Literal) and obj not in seen:
                    seen.add(obj)
                    todo.append(obj)
        for predicate in backward:
            for subject in knowledge.subjects(predicate, node):
                out.add((subject, predicate, node))
                if subject not in seen:
                    seen.add(subject)
                    todo.append(subject)
    for node in seen:
        for cls in knowledge.objects(node, RDF.type):
            out.add((node, RDF.type, cls))
    for triple in knowledge.triples((None, RDFS.subClassOf, None)):
        out.add(triple)
    return out
