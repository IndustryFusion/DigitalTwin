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

"""Which of an entity's relationships lead to its children.

A relationship made from an OPC UA reference keeps the reference's type in the
shape of the entity's type (or of one above it): `base:hasReferenceType
opcua:HasComponent`. Those of HasChild and of what is below it are the
hierarchy; any other only refers to something, which may be anywhere, the
entity's own parent included.

Instances also have what their type does not declare, a folder's content most
of all. Then the other shapes that declare the same relationship say it. When
none declares it, and the package has reference types at all, the data does: a
target only this entity points at is below it, one others point at too is
shared.
"""

from rdflib import BNode, URIRef
from rdflib.namespace import RDF, RDFS, SH

from ..ngsild.views import INSTANCE_MARKS, NGSILD

OPCUA = 'http://opcfoundation.org/UA/'
HAS_CHILD = URIRef(OPCUA + 'HasChild')
HAS_OBJECT = URIRef(NGSILD + 'hasObject')
HAS_OBJECT_LIST = URIRef(NGSILD + 'hasObjectList')
REFERENCE_TYPE = '/hasReferenceType'        # base:, whichever version of it
# HasChild and all that the OPC UA core nodeset (Opc.Ua.NodeSet2.xml) has below
# it, for a package whose knowledge does not have the reference types.
CORE = frozenset(URIRef(OPCUA + name) for name in (
    'HasChild', 'Aggregates', 'HasSubtype', 'HasProperty', 'HasComponent', 'HasOrderedComponent',
    'HasHistoricalConfiguration', 'HasAddIn', 'HasStructuredComponent', 'HasPhysicalComponent',
    'HasContainedComponent', 'HasAttachedComponent', 'HasArgumentDescription',
    'HasOptionalInputArgumentDescription', 'HasGuard', 'HasAlarmSuppressionGroup', 'HasPubSubConnection',
    'HasDataSetWriter', 'HasWriterGroup', 'HasDataSetReader', 'HasReaderGroup', 'HasReferenceDescription'))
# What is no attribute: an instance's values, however long or deep, above all.
SKIPPED = INSTANCE_MARKS | {RDF.type, RDF.first, RDF.rest}


def _above(graph, start, predicate):
    """`start` and all that `predicate` leads to from it."""
    found, pending = set(), [start]
    while pending:
        node = pending.pop()
        if node not in found:
            found.add(node)
            pending.extend(graph.objects(node, predicate))
    return found


def weightier(one, other):
    """Of two answers for one target: one way to a child is enough, and what a
    shape refuses does not hide what another relationship leaves open."""
    return max(one, other, key=lambda answer: {True: 2, None: 1, False: 0}[answer])


def _items(graph, head):
    """The members of an RDF list, as far as it is one: a list that is broken
    off, or leads back into itself, ends there."""
    seen = set()
    while head is not None and head != RDF.nil and head not in seen:
        seen.add(head)
        item = graph.value(head, RDF.first)
        if item is not None:
            yield item
        head = graph.value(head, RDF.rest)


class Hierarchy:
    """What the shapes and the knowledge of a package say about its
    relationships. One for one question (a copy): what it worked out per type
    and per path is kept with it, so thousands of entities ask once."""

    def __init__(self, package):
        self.package = package
        self._declared = {}
        self._elsewhere = {}
        self._names = {}
        self._typed = None

    @property
    def has_reference_types(self):
        """Does any shape name a reference type? Else the package has none."""
        if self._typed is None:
            self._typed = any(str(p).endswith(REFERENCE_TYPE) for p in set(self.package.shapes.predicates()))
        return self._typed

    def _iri(self, term):
        """A name the data's context left prefixed, by the package's names."""
        from .choices import expand

        if term not in self._names:
            self._names[term] = URIRef(expand(self.package.path, str(term)))
        return self._names[term]

    def _is_child(self, reference):
        return not CORE.isdisjoint(_above(self.package.knowledge, reference, RDFS.subPropertyOf))

    def _verdict(self, shapes):
        """True or False by the reference types of `shapes`, None without one."""
        references = {r for shape in shapes for p, r in self.package.shapes.predicate_objects(shape)
                      if str(p).endswith(REFERENCE_TYPE)}
        return any(self._is_child(r) for r in references) if references else None

    def _property_shapes(self, node, seen):
        """The property shapes a shape has: its own, those of the shapes it
        applies (sh:node), and those in a connective, where any may hold.
        `seen` ends shapes that apply each other."""
        shapes, pending = self.package.shapes, [node]
        while pending:
            at = pending.pop()
            if at in seen:
                continue
            seen.add(at)
            yield from shapes.objects(at, SH.property)
            inner = list(shapes.objects(at, SH.node))
            for connective in (SH['and'], SH['or'], SH.xone):
                for head in shapes.objects(at, connective):
                    inner += _items(shapes, head)
            for one in inner:
                if shapes.value(one, SH.path) is None:
                    pending.append(one)
                else:
                    yield one

    def _by_path(self, key, holders):
        """{path: [property shape]} of the shapes `holders()`. A path that is
        no IRI (an inverse, a sequence) is no relationship's."""
        if key not in self._declared:
            found, seen = {}, set()
            for holder in holders():
                for shape in self._property_shapes(holder, seen):
                    path = self.package.shapes.value(shape, SH.path)
                    if isinstance(path, URIRef) and shape not in found.setdefault(path, []):
                        found[path].append(shape)
            self._declared[key] = found
        return self._declared[key]

    def _of_types(self, types):
        def holders():
            wanted = {above for one in types for above in _above(self.package.knowledge, one, RDFS.subClassOf)}
            return [shape for one in sorted(wanted)
                    for shape in sorted(set(self.package.shapes.subjects(SH.targetClass, one)) | {one})]
        return self._by_path(('types', types), holders)

    def _child(self, path, shapes):
        if shapes:
            return bool(self._verdict(shapes))
        if path not in self._elsewhere:
            declaring = list(self.package.shapes.subjects(SH.path, path))
            self._elsewhere[path] = bool(self._verdict(declaring)) if declaring else None
        return self._elsewhere[path]

    def relationships(self, graph, entity):
        """What an entity of `graph` points at: {target: is it a child}, None
        when no shape declares a relationship to it. Sub-attributes are
        included."""
        found, seen = {}, set()
        types = frozenset(self._iri(t) for t in graph.objects(entity, RDF.type))
        pending = [(entity, self._of_types(types), None)]
        while pending:
            node, declared, by = pending.pop()
            if (node, by) in seen:
                continue
            seen.add((node, by))
            for predicate, value in graph.predicate_objects(node):
                if predicate in SKIPPED:
                    continue
                path = self._iri(predicate)
                shapes = declared.get(path, [])
                for target in targets(graph, value):
                    child = self._child(path, shapes)
                    found[target] = weightier(found[target], child) if target in found else child
                if isinstance(value, BNode):
                    key = ('shapes', frozenset(shapes))
                    pending.append((value, self._by_path(key, lambda shapes=shapes: shapes), key))
        return found


def targets(graph, value):
    """The entities an attribute instance points at: one, several, or -- a
    ListRelationship -- a list of them."""
    yield from graph.objects(value, HAS_OBJECT)
    for head in graph.objects(value, HAS_OBJECT_LIST):
        for item in ([head] if (head, RDF.first, None) not in graph else _items(graph, head)):
            if isinstance(item, URIRef):
                yield item
            else:
                yield from graph.objects(item, HAS_OBJECT)


def pointers(graph):
    """{target: the entities of `graph` with a relationship, or a
    sub-attribute's, that leads to it}. All at once: one at a time, a long list
    of targets would be walked once for each."""
    found = {}
    for entity in {s for s in graph.subjects() if isinstance(s, URIRef)}:
        seen, pending = set(), [entity]
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            for predicate, value in graph.predicate_objects(node):
                if predicate not in SKIPPED:
                    for target in targets(graph, value):
                        found.setdefault(target, set()).add(entity)
                    if isinstance(value, BNode):
                        pending.append(value)
    return found
