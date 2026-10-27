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

"""Name a validation result after the attribute that owns it.

Ported from shacl2flink/tests/pyshacl-compare/compare.py. The NGSI-LD RDF
encoding puts every attribute in a blank node, so pyshacl reports focus nodes
and paths that are meaningless on their own: an unnamed blank node, and a path
of ngsild:hasValue. What a reader needs is the entity and the attribute.

This is also what keeps blank node LABELS out of every downstream identity --
they are not stable across runs, so a residue digest built on them would churn
on every execution (implementation-plan.md H4).
"""

from rdflib import BNode, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF, SH

NGSILD = 'https://uri.etsi.org/ngsi-ld/'

# How an attribute's value is reached. pyshacl reports the value path itself;
# we name the attribute that carries it, so these resolve to the parent.
from ..ngsild.kinds import PAYLOAD_PATHS  # noqa: E402

VALUE_PATHS = set(PAYLOAD_PATHS)
# An attribute's unit is its metadata: a constraint on it is named after the
# attribute -- hasTemperature.unitCode -- not after "unitCode", which every
# attribute with a unit would share.
UNIT_CODE = 'https://uri.etsi.org/ngsi-ld/unitCode'
UNIT_SUFFIX = '.unitCode'
# The constraint types an attribute node and its value can BOTH carry. On the
# value they are named with the value's path -- hasTemperature.hasValue -- or
# an attribute's sh:minCount and its value's would be one reference. Every
# other value constraint (datatype, ranges, class, list) exists only on the
# value, so it keeps the attribute's name.
LAYERED = {'MinCountConstraintComponent', 'MaxCountConstraintComponent',
           'NodeKindConstraintComponent'}


def layered(attribute, path, component):
    """`attribute`, or `attribute.hasValue` for a constraint on the value that
    the attribute node could carry too (LAYERED)."""
    if attribute and path is not None and str(path) in VALUE_PATHS and \
            str(component).rsplit('#', 1)[-1] in LAYERED:
        return f'{attribute}.{local(path)}'
    return attribute


# Edges carrying no name of their own: they say how a value is stored, not
# which attribute it belongs to. The climb steps over them, including the
# rdf:first/rdf:rest cells of a list.
TRANSPARENT_EDGES = VALUE_PATHS | {str(RDF.first), str(RDF.rest)}


def curie(graph, iri):
    """A prefixed name for an IRI, falling back to the local name.

    Used wherever a shape is named for a HUMAN -- coverage lines, expectation
    files -- because the local name alone is ambiguous: the kms carries both
    base_shacl:CartridgeShape and filter_shacl:CartridgeShape.
    """
    if not iri:
        return ''
    try:
        prefix, _, name = graph.namespace_manager.compute_qname(str(iri), generate=False)
        # An EMPTY prefix is still a prefix -- ':CartridgeShape' is what
        # distinguishes the base shape from 'default1:CartridgeShape'. Dropping
        # it back to the bare local name reintroduces the collision.
        return f'{prefix}:{name}'
    except Exception:
        return local(iri)


def local(iri):
    """The last segment of an IRI, for readable names."""
    return str(iri).rsplit('/', 1)[-1].rsplit('#', 1)[-1]


def inverse_predicate(path, *graphs):
    """The relationship predicate of an NGSI-LD inverse path, or None.

    The path is the two-hop sequence that walks back out of the blank node a
    relationship is stored in -- ( [^ngsild:hasObject] [^predicate] ) -- which
    pyshacl reports as an unnamed blank node. The expression may live in the
    report or in the shapes graph depending on how much pyshacl copies, so both
    are searched.
    """
    if not isinstance(path, BNode):
        return None
    for graph in graphs:
        try:
            steps = list(Collection(graph, path))
        except Exception:
            continue
        if len(steps) != 2:
            continue
        if graph.value(steps[0], SH.inversePath) != URIRef(NGSILD + 'hasObject'):
            continue
        predicate = graph.value(steps[1], SH.inversePath)
        if isinstance(predicate, URIRef):
            return predicate
    return None


def owner_and_edge(node, graph, seen=None):
    """The entity owning this node, and the predicate that attaches it.

    The edge wanted is the one closest to the NODE, not the one closest to the
    entity: a constraint on a sub-attribute is named after the sub-attribute
    (`bolt`), not after its grandparent (`assembly`).
    """
    from ..rdfio.relative import as_written

    seen = seen if seen is not None else set()
    if isinstance(node, URIRef):
        return as_written(node), None
    if node in seen:
        return None, None
    seen.add(node)
    for subject, predicate in graph.subject_predicates(node):
        owner, higher = owner_and_edge(subject, graph, seen)
        if owner:
            if str(predicate) in TRANSPARENT_EDGES:
                return owner, higher
            return owner, predicate
    return None, None


def attribute_name(focus, path, data_graph, shapes_graph, report_graph):
    """(resource, attribute name) for a reported result, or (None, None).

    The attribute is taken from the reported path when that path names an
    attribute, and otherwise from the climb out of the focus node.
    """
    resource, edge = owner_and_edge(focus, data_graph)
    if resource is None:
        return None, None

    name = None
    if isinstance(path, URIRef):
        if str(path) in VALUE_PATHS:
            # The path says how to read the value; the attribute is the edge
            # the focus node hangs from.
            name = local(edge) if edge is not None else None
        elif str(path) == UNIT_CODE:
            name = local(edge) + UNIT_SUFFIX if edge is not None else None
        else:
            name = local(path)
    elif isinstance(path, BNode):
        predicate = inverse_predicate(path, report_graph, shapes_graph)
        name = local(predicate) if predicate is not None else None
    if name is None and edge is not None:
        name = local(edge)
    return resource, name


def owning_shape(shape, *graphs):
    """The named shape a (possibly anonymous) property shape belongs to.

    pyshacl reports sh:sourceShape, which for a nested property shape is a
    blank node. Its LABEL is not stable across runs, so using it as identity
    would make every residue digest churn on every execution (H4). Walking up
    to the enclosing named NodeShape gives a name that appears in the file the
    author wrote -- which is also what invariant C2 promises: an alert refers to
    a shape you can find.
    """
    if isinstance(shape, URIRef):
        return str(shape)
    seen = set()
    pending = [shape]
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        for graph in graphs:
            for subject in graph.subjects(None, node):
                if isinstance(subject, URIRef):
                    return str(subject)
                pending.append(subject)
    return None
