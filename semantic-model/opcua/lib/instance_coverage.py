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
"""What the shapes and the ontology written by owl2instances.py cover of the instances.

The type pass of owl2instances.py only reaches types through the type definitions of children and the members their
declarations add. This module finds the types the instance nodes use and decides which of them need a shape of their
own; the entity pass declares with it every attribute of the instances which no domain in the ontologies covers; and
it checks the written outputs for types and attributes of the instances that are still not covered.
"""
from rdflib import URIRef
from rdflib.namespace import RDFS, SH

from lib.utils import UARDF

ENTITY_KEYS = ('id', 'type', '@context')
NGSILD_HAS_OBJECT = URIRef('https://uri.etsi.org/ngsi-ld/hasObject')


def instance_object_types(g, rdfutils, roots, ignored_hierarchical_references, ignored_references):
    """Object types of the instance nodes reachable from the root entities, in the order they are first met.

    Follows the references the entity pass follows: hierarchical children (without the ignored hierarchical
    references), Organizes, and non-hierarchical references (without the ignored references), also through
    variables, whose children and references the entity pass follows too; only object nodes contribute a type.

    Args:
        g (Graph): instance ontology with its imports
        rdfutils (RdfUtils): helper bound to the base and OPC UA namespaces
        roots (list(URIRef)): the root entities of the run
        ignored_hierarchical_references (list(URIRef)): hierarchical references not followed
        ignored_references (list(URIRef)): non-hierarchical references not followed

    Returns:
        list(URIRef): the object types, without duplicates
    """
    opcuans = rdfutils.opcuans
    seen = set()
    found = []
    stack = [root for root in reversed(roots) if root is not None]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        nodeclass, nodetype = rdfutils.get_type(g, node)
        is_object = rdfutils.isObjectNodeClass(nodeclass)
        if not is_object and not rdfutils.isVariableNodeClass(nodeclass):
            continue
        if is_object and nodetype is not None and nodetype not in found:
            found.append(nodetype)
        targets = []
        for reference, target in rdfutils.get_all_subreferences(g, node, opcuans['HasChild']):
            if reference not in ignored_hierarchical_references:
                targets.append(target)
        if is_object:
            for _, target in rdfutils.get_all_subreferences(g, node, opcuans['Organizes']):
                targets.append(target)
        for reference, target in rdfutils.get_all_subreferences(g, node, opcuans['NonHierarchicalReferences']):
            if reference not in ignored_references:
                targets.append(target)
        stack.extend(reversed(targets))
    return found


def supertype_chain(g, objtype):
    """The type followed by its supertypes, nearest first (OPC UA object types have one supertype)."""
    chain = []
    current = URIRef(objtype)
    while current is not None and current not in chain:
        chain.append(current)
        current = next((o for o in sorted(g.objects(current, RDFS.subClassOf)) if isinstance(o, URIRef)), None)
    return chain


def defines_members(g, rdfutils, typenode, ignored_hierarchical_references, ignored_references):
    """True if the type node defines a member of its own that gives a rule: a child other than a Method, an
    Organizes or non-hierarchical reference (without the ignored ones), or an interface."""
    opcuans = rdfutils.opcuans
    if next(g.objects(typenode, opcuans['HasInterface']), None) is not None:
        return True
    for reference, child in rdfutils.get_all_subreferences(g, typenode, opcuans['HasChild']):
        if reference in ignored_hierarchical_references:
            continue
        if rdfutils.isMethodNodeClass(rdfutils.get_type(g, child)[0]):
            continue  # a Method gives no rule
        return True
    if rdfutils.get_all_subreferences(g, typenode, opcuans['Organizes']):
        return True
    for reference, _ in rdfutils.get_all_subreferences(g, typenode, opcuans['NonHierarchicalReferences']):
        if reference not in ignored_references:
            return True
    return False


def needs_own_shape(g, rdfutils, objtype, shaped_types, ignored_hierarchical_references, ignored_references):
    """Decide whether a type of the instances needs a node shape of its own.

    A type needs its own shape if it, or a type between it and its nearest supertype with a shape, defines a member.
    Otherwise the supertype's shape covers its entities through rdfs:subClassOf (a second shape would only repeat
    its rules), or, without such a supertype, neither the type nor its supertypes define a rule (a shape would be
    empty). A type without a definition cannot get a shape.

    Returns:
        bool: True if the type scan has to run for objtype
    """
    if objtype in shaped_types:
        return False
    if next(g.subjects(UARDF['definesType'], URIRef(objtype)), None) is None:
        return False
    for current in supertype_chain(g, objtype):
        if current in shaped_types:
            return False
        typenode = next(g.subjects(UARDF['definesType'], current), None)
        if typenode is not None and defines_members(g, rdfutils, typenode, ignored_hierarchical_references,
                                                    ignored_references):
            return True
    return False


def lacks_shape(g, rdfutils, objtype, shaped_types, ignored_hierarchical_references, ignored_references):
    """True if a type of the instances is not covered by the shapes: no node shape targets it, and it, or a type
    between it and its nearest supertype with a node shape, defines a member, or its definition is unknown (its rules
    are unknown). A type whose members all come from a shaped supertype is covered by that shape; a type that with its
    supertypes defines no member needs no shape."""
    if URIRef(objtype) in shaped_types:
        return False
    if next(g.subjects(UARDF['definesType'], URIRef(objtype)), None) is None:
        return True
    return needs_own_shape(g, rdfutils, objtype, shaped_types, ignored_hierarchical_references, ignored_references)


def shape_order(g, types):
    """Supertypes before their subtypes, so that a subtype is decided after its supertypes got their shapes."""
    return sorted(types, key=lambda t: (len(supertype_chain(g, t)), str(t)))


def all_supertypes(graphs, objtype):
    """The type and all its supertypes, over several graphs."""
    result = set()
    todo = [URIRef(objtype)]
    while todo:
        current = todo.pop()
        if current in result:
            continue
        result.add(current)
        for graph in graphs:
            todo.extend(o for o in graph.objects(current, RDFS.subClassOf) if isinstance(o, URIRef))
    return result


def has_covering_domain(graphs, attribute, supertypes):
    """True if one of the graphs declares the attribute with a domain among the given types."""
    return any(domain in supertypes for graph in graphs for domain in graph.objects(attribute, RDFS.domain))


def constrained_paths(shapes, supertypes):
    """The paths of the property shapes of every node shape targeting one of the given types."""
    paths = set()
    for objtype in supertypes:
        for shape in shapes.subjects(SH.targetClass, objtype):
            paths.update(shape_paths(shapes, shape))
    return paths


def shape_paths(shapes, shape):
    """The paths of the property shapes of one node shape."""
    return {path for prop in shapes.objects(shape, SH.property) for path in shapes.objects(prop, SH.path)}


def declaration_shapes(shapes, supertypes, attribute):
    """The node shapes which a relationship of an entity of the given types applies to the entities it refers to:
    sh:node on ngsi-ld:hasObject of the relationship's property shape (the declaration shapes of instance
    declarations, which add members beyond the declared child's type)."""
    result = set()
    for objtype in supertypes:
        for shape in shapes.subjects(SH.targetClass, objtype):
            for prop in shapes.objects(shape, SH.property):
                if attribute not in shapes.objects(prop, SH.path):
                    continue
                for objprop in shapes.objects(prop, SH.property):
                    if NGSILD_HAS_OBJECT in shapes.objects(objprop, SH.path):
                        result.update(shapes.objects(objprop, SH.node))
    return result


def referred_entities(value):
    """The ids of the entities an attribute value of the instances refers to as a Relationship."""
    values = value if isinstance(value, list) else [value]
    return [v['object'] for v in values if isinstance(v, dict) and v.get('type') == 'Relationship' and 'object' in v]


def uncovered_terms(instances, expand, shapes, ontologies, exempt_attributes=(), lacks_shape=None):
    """Types and attributes of the instances that the shapes or the ontologies do not cover.

    Args:
        instances (list(dict)): the entities as written to the instances file
        expand (callable): maps a compact name of the instances to its IRI
        shapes (Graph): the written shapes
        ontologies (list(Graph)): the written ontology and the loaded ontologies
        exempt_attributes (iterable(URIRef)): attributes that are not reported, e.g. the node reference
        lacks_shape (callable): tells for a type and the set of targeted types whether the type is not covered by
            the shapes (see lacks_shape()). Without it, a type is covered if a node shape targets it or a supertype.

    Returns:
        dict: type IRI -> {'no_shape': bool, 'undeclared': set(IRI), 'unconstrained': set(IRI)}, only for types
        with a gap
    """
    targets = set(shapes.objects(None, SH.targetClass))
    per_type = {}       # type -> (supertypes, constrained paths); computed once per type, not per entity
    covered = {}        # (type, attribute) -> declared with a covering domain

    def type_info(objtype):
        if objtype not in per_type:
            supertypes = all_supertypes(ontologies, objtype)
            per_type[objtype] = (supertypes, constrained_paths(shapes, supertypes))
        return per_type[objtype]

    declared_paths = {}
    for instance in instances:
        supertypes, _ = type_info(URIRef(expand(instance['type'])))
        for key, value in instance.items():
            if key in ENTITY_KEYS:
                continue
            referred = referred_entities(value)
            if not referred:
                continue
            for shape in declaration_shapes(shapes, supertypes, URIRef(expand(key))):
                for entity_id in referred:
                    declared_paths.setdefault(entity_id, set()).update(shape_paths(shapes, shape))
    result = {}
    for instance in instances:
        objtype = URIRef(expand(instance['type']))
        supertypes, type_paths = type_info(objtype)
        if objtype not in result:
            no_shape = lacks_shape(objtype, targets) if lacks_shape is not None else not supertypes & targets
            result[objtype] = {'no_shape': no_shape, 'undeclared': set(), 'unconstrained': set()}
        gaps = result[objtype]
        paths = type_paths | declared_paths.get(instance['id'], set())
        for key in instance:
            if key in ENTITY_KEYS:
                continue
            attribute = URIRef(expand(key))
            if attribute in exempt_attributes:
                continue
            if (objtype, attribute) not in covered:
                covered[(objtype, attribute)] = has_covering_domain(ontologies, attribute, supertypes)
            if not covered[(objtype, attribute)]:
                gaps['undeclared'].add(attribute)
            if attribute not in paths:
                gaps['unconstrained'].add(attribute)
    return {t: gaps for t, gaps in result.items() if gaps['no_shape'] or gaps['undeclared'] or gaps['unconstrained']}


def format_uncovered(uncovered, compact):
    """One line per type, ordered by type, for the coverage warning."""
    lines = []
    for objtype in sorted(uncovered, key=str):
        gaps = uncovered[objtype]
        parts = []
        if gaps['no_shape']:
            parts.append('no shape')
        if gaps['undeclared']:
            parts.append('not declared: ' + ', '.join(sorted(compact(a) for a in gaps['undeclared'])))
        if gaps['unconstrained']:
            parts.append('not constrained: ' + ', '.join(sorted(compact(a) for a in gaps['unconstrained'])))
        lines.append(f"{compact(objtype)}: {'; '.join(parts)}")
    return lines
