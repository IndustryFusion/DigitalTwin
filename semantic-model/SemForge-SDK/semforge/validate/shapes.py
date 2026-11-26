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

"""Which data view a shape is validated against, and whether it said so honestly.

A shape declares its view with semforge:dataView. The default is `current`,
which is right for every Core constraint and for the whole production KMS.

The declaration is then CHECKED against the shape's body, because getting it
wrong is silent: an aggregate evaluated over the collapsed view computes across
one instance where four were meant and returns a plausible number, never an
error. That is the failure class C1 exists to prevent, so a mismatch fails the
build naming the shape.

Detection follows the same rule the compiler uses -- lib/sparql_to_sql.py keys
off the presence of GROUP BY / aggregate functions in the query algebra.
"""

import re

from rdflib import Namespace, URIRef
from rdflib.namespace import SH

from ..errors import Diagnostic
from ..ngsild import DataView
from . import prefixes

SEMFORGE = Namespace('https://industryfusion.github.io/semforge/v0/')
DATA_VIEW = SEMFORGE.dataView

# GROUP BY, or any SPARQL aggregate function applied to something.
_AGGREGATE = re.compile(
    r'\bGROUP\s+BY\b|\b(?:COUNT|SUM|AVG|MIN|MAX|SAMPLE|GROUP_CONCAT)\s*\(',
    re.IGNORECASE)


def query_texts(shapes_graph, shape):
    """Every SPARQL body attached to a shape: constraints and rules alike."""
    texts = []
    for constraint in shapes_graph.objects(shape, SH.sparql):
        for select in shapes_graph.objects(constraint, SH.select):
            texts.append(str(select))
    for rule in shapes_graph.objects(shape, SH.rule):
        for construct in shapes_graph.objects(rule, SH.construct):
            texts.append(str(construct))
        for select in shapes_graph.objects(rule, SH.select):
            texts.append(str(select))
    return texts


def aggregates(text):
    return bool(_AGGREGATE.search(text))


def _implicit(shapes_graph, shape):
    """A shape that is itself a class targets that class's instances."""
    from rdflib.namespace import OWL, RDF, RDFS

    return isinstance(shape, URIRef) and \
        (shape, RDF.type, SH.NodeShape) in shapes_graph and (
            (shape, RDF.type, RDFS.Class) in shapes_graph or
            (shape, RDF.type, OWL.Class) in shapes_graph)


def class_targets(shapes_graph, shape):
    """The classes a shape targets: its sh:targetClass values, and the shape
    itself when it is a class (an implicit class target)."""
    found = [t for t in shapes_graph.objects(URIRef(shape), SH.targetClass)
             if isinstance(t, URIRef)]
    if _implicit(shapes_graph, URIRef(shape)) and URIRef(shape) not in found:
        found.append(URIRef(shape))
    return found


def node_shapes(shapes_graph):
    """The shapes that target a class -- the ones that belong to an entity
    type, by sh:targetClass or by being the class themselves. Most callers ask
    exactly that (which shapes judge a Filter, which shape to add an attribute
    to); read their classes with `class_targets`. Which shapes RUN is
    `targeted_shapes`."""
    found = set(shapes_graph.subjects(SH.targetClass, None))
    from rdflib.namespace import RDF

    found.update(s for s in shapes_graph.subjects(RDF.type, SH.NodeShape)
                 if _implicit(shapes_graph, s))
    return sorted(found, key=str)


TARGETS = (SH.targetClass, SH.targetNode, SH.targetSubjectsOf,
           SH.targetObjectsOf, SH.target)


def targeted_shapes(shapes_graph):
    """Every shape SHACL evaluates on its own: one with any target, explicit
    or implicit (a shape that is itself a class targets its instances).

    A shape is not tied to an entity type. Before this the validator ran only
    class-targeted shapes, so one written with sh:targetNode was silently
    never checked at all."""
    from rdflib.namespace import OWL, RDF, RDFS

    found = set()
    for predicate in TARGETS:
        found.update(s for s in shapes_graph.subjects(predicate, None)
                     if isinstance(s, URIRef))
    for shape in shapes_graph.subjects(RDF.type, SH.NodeShape):
        if isinstance(shape, URIRef) and (
                (shape, RDF.type, RDFS.Class) in shapes_graph or
                (shape, RDF.type, OWL.Class) in shapes_graph):
            found.add(shape)
    return sorted(found, key=str)


def every_node_shape(shapes_graph):
    """Every named shape a reader might look for: the targeted ones, a
    declared sh:NodeShape without a target, and one only reached through
    sh:node from another shape."""
    from rdflib.namespace import RDF

    found = set(targeted_shapes(shapes_graph))
    found.update(s for s in shapes_graph.subjects(RDF.type, SH.NodeShape)
                 if isinstance(s, URIRef))
    found.update(o for o in shapes_graph.objects(None, SH.node)
                 if isinstance(o, URIRef))
    return sorted(found, key=str)


def declared_view(shapes_graph, shape):
    value = shapes_graph.value(shape, DATA_VIEW)
    if value is None:
        return DataView.CURRENT
    try:
        return DataView(str(value))
    except ValueError:
        raise ValueError(f'{shape}: unknown semforge:dataView "{value}"')


def view_of(shapes_graph, shape):
    """The view a shape is validated against, defaulting to current."""
    try:
        return declared_view(shapes_graph, shape)
    except ValueError:
        return DataView.CURRENT


def check_declarations(shapes_graph):
    """Diagnostics for shapes whose declared view contradicts their body.

    Two findings:

    * a shape reading `current` (declared or defaulted) whose body aggregates.
      The aggregate would run over collapsed instances and be quietly wrong.
    * an unknown view name, which would otherwise fall back to the default and
      validate something other than what was asked for.
    """
    found = []
    for shape in targeted_shapes(shapes_graph):
        try:
            view = declared_view(shapes_graph, shape)
        except ValueError as exc:
            found.append(Diagnostic(
                code='SF-VIEW-002', category='package', severity='error',
                message=str(exc), subject=str(shape)))
            continue

        if view is not DataView.CURRENT:
            continue
        for text in query_texts(shapes_graph, shape):
            if aggregates(text):
                found.append(Diagnostic(
                    code='SF-VIEW-001', category='package', severity='error',
                    subject=str(shape),
                    message=(
                        f'{shape} aggregates but is validated against the '
                        f'"current" view, where each attribute has been resolved to '
                        f'its latest instance. The aggregate would run over one '
                        f'observation where several were meant, and would return a '
                        f'plausible wrong number rather than an error. Declare '
                        f'semforge:dataView "history".')))
                break
    return found


def partition(shapes_graph):
    """{DataView: [shape, ...]} for every shape with a target, of any kind."""
    groups = {}
    for shape in targeted_shapes(shapes_graph):
        groups.setdefault(view_of(shapes_graph, shape), []).append(shape)
    return groups


def subgraph_for(shapes_graph, shapes):
    """A shapes graph containing only the given shapes, and everything they
    name by an IRI that pyshacl reads (`reach`).

    Kept with a frozen shapes graph (rdfio/frozen.py), per shape set:
    rebuilt for every validation it cost 0.8 s on the OPC UA pump shapes.
    What is kept is frozen too -- pyshacl, which writes into its shapes, is
    handed a copy.
    """
    from ..rdfio.frozen import derived, freeze, is_frozen

    if not is_frozen(shapes_graph):
        return _subgraph(shapes_graph, shapes)
    return derived(shapes_graph, 'subgraphs', lambda: freeze(_subgraph(shapes_graph, shapes)),
                   key=(frozenset(shapes),), keep=32)


def _sh(name):
    """A term of the SHACL namespace, also one rdflib's SH does not define."""
    return URIRef(str(SH) + name)


# The SHACL parameters whose IRI values are terms of the data -- a class, a
# predicate, a datatype, a value -- and not a part of the shapes. Every other
# IRI a shape names with a SHACL predicate is followed: a shape (sh:node,
# sh:property, sh:not, sh:qualifiedValueShape, a member of sh:and, sh:or,
# sh:xone), a SPARQL constraint (sh:sparql), a target (sh:target), a rule, a
# validator, a parameter, a list.
_TERMS = frozenset({
    _sh('targetClass'), _sh('targetNode'), _sh('targetSubjectsOf'), _sh('targetObjectsOf'),
    _sh('path'), _sh('inversePath'), _sh('alternativePath'), _sh('zeroOrMorePath'),
    _sh('oneOrMorePath'), _sh('zeroOrOnePath'),
    _sh('class'), _sh('datatype'), _sh('nodeKind'), _sh('hasValue'), _sh('equals'), _sh('disjoint'),
    _sh('lessThan'), _sh('lessThanOrEquals'), _sh('severity'), _sh('group'), _sh('defaultValue'),
    _sh('subject'), _sh('predicate'), _sh('object'), _sh('this'), _sh('returnType'), _sh('nodes'),
    # read by prefixes.complete, which also says how pyshacl is to read them
    _sh('prefixes'),
})
# Of those, the ones whose value is a list: its cells belong to the shapes,
# its members don't.
_TERM_LISTS = frozenset({_sh('in'), _sh('languageIn'), _sh('ignoredProperties')})


def globals_of(shapes_graph):
    """What pyshacl applies wherever it is, not where a shape names it: the
    constraint components (a shape uses one by carrying its parameters), the
    SHACL functions a query calls, the target types, and the subclasses that
    make something one of them. Each is part of every shapes graph handed to
    pyshacl.

    Kept with a frozen graph, as everything derived from one is."""
    from ..rdfio.frozen import derived

    return derived(shapes_graph, 'shape_globals', lambda: _globals_of(shapes_graph))


def _globals_of(shapes_graph):
    from rdflib.namespace import RDF, RDFS

    found = set()
    # A component is an instance of sh:ConstraintComponent or of a class
    # directly below it, and so are the classes that make it one: no deeper,
    # as pyshacl finds them (ShapesGraph._find_custom_constraints).
    for kind in component_classes(shapes_graph):
        found |= set(shapes_graph.subjects(RDF.type, kind))
        found.add(kind)
    # A function is an instance of its kind itself (pyshacl's gather_functions).
    for kind in (_sh('SPARQLFunction'), _sh('SHACLFunction'), _sh('JSFunction')):
        found |= set(shapes_graph.subjects(RDF.type, kind))
    found |= set(shapes_graph.subjects(RDFS.subClassOf, _sh('Target')))
    # Those of SHACL itself are built into pyshacl.
    return frozenset(node for node in found if not str(node).startswith(str(SH)))


def component_classes(shapes_graph):
    """sh:ConstraintComponent and the classes directly below it."""
    from rdflib.namespace import RDFS

    return {_sh('ConstraintComponent')} | set(
        shapes_graph.subjects(RDFS.subClassOf, _sh('ConstraintComponent')))


_FOLLOWS = {}


def _follows(predicate):
    """Whether an IRI that `predicate` names may be a part of the shapes."""
    found = _FOLLOWS.get(predicate)
    if found is None:
        found = _FOLLOWS[predicate] = str(predicate).startswith(str(SH)) and predicate not in _TERMS
    return found


def _named(shapes_graph, predicate, value):
    """The IRIs `value`, an object of `predicate`, brings into the shapes: none
    for a term; the cells of a list of terms; the members of any other list
    too."""
    from rdflib import BNode
    from rdflib.namespace import RDF

    if not isinstance(value, (URIRef, BNode)):
        return []
    if value != RDF.nil and (value, RDF.first, None) not in shapes_graph:
        return [value] if isinstance(value, URIRef) and predicate not in _TERM_LISTS else []
    found, cell, seen = [], value, set()
    while isinstance(cell, (URIRef, BNode)) and cell != RDF.nil and cell not in seen:
        seen.add(cell)
        if isinstance(cell, URIRef):
            found.append(cell)
        member = shapes_graph.value(cell, RDF.first)
        if predicate not in _TERM_LISTS and isinstance(member, URIRef):
            found.append(member)
        cell = shapes_graph.value(cell, RDF.rest)
    return found


def reach(shapes_graph, start):
    """`start` and every node they name by an IRI that pyshacl reads, through
    each other: what a shapes graph needs for pyshacl to validate them as it
    validates them in the whole shapes graph (#1105).

    A node goes in by its concise bounded description, which follows the blank
    node tree it is written as. An IRI does not: a named shape (sh:node,
    sh:property, sh:or, ...), a SPARQL constraint or target, a rule, a
    validator is pulled in by name. So are the constraint components, SHACL
    functions and target types (globals_of), which nothing names.
    """
    pending = list(start) + sorted(globals_of(shapes_graph), key=str)
    done = set()
    triples = []
    while pending:
        node = pending.pop()
        if node in done:
            continue
        done.add(node)
        for triple in shapes_graph.cbd(node):
            triples.append(triple)
            if _follows(triple[1]):
                pending.extend(n for n in _named(shapes_graph, triple[1], triple[2])
                               if n not in done)
    return triples


# What makes a shape evaluated on its own: its targets, and being a class.
_TARGETING = frozenset({_sh('targetClass'), _sh('targetNode'), _sh('targetSubjectsOf'),
                        _sh('targetObjectsOf'), _sh('target')})


def _subgraph(shapes_graph, shapes):
    """The part of `shapes_graph` for `shapes`: what they reach. A shape that is
    only reached, by name, comes as a body: without its targets, and not as a
    class, or pyshacl would evaluate it on its own here too, in this view and
    whether asked for or not."""
    from rdflib import Graph
    from rdflib.namespace import OWL, RDF, RDFS

    asked = set(shapes)
    out = Graph()
    for prefix, namespace in shapes_graph.namespaces():
        out.bind(prefix, namespace)
    for triple in reach(shapes_graph, shapes):
        subject, predicate, obj = triple
        if subject not in asked and isinstance(subject, URIRef) and (
                predicate in _TARGETING or
                (predicate == RDF.type and obj in (RDFS.Class, OWL.Class))):
            continue
        out.add(triple)
    prefixes.complete(out, shapes_graph)
    return out
