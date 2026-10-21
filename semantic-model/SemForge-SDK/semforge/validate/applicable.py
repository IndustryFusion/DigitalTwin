"""The applicable-set enumerator (implementation-plan.md H1).

A SHACL engine reports violations and nothing else. Conformance is the ABSENCE
of a result -- which is exactly the silence invariant V1 forbids us to read as
success, because it is also what a constraint that never ran produces.

So the set of constraints that SHOULD have been evaluated is computed
independently of the validator, and the engine's results are subtracted from it:

    in the report            -> VIOLATED
    enumerated, not reported -> CONFORMANT
    shape with no target     -> NOT_APPLICABLE
    enumerated badly, or engine error -> NOT_EVALUATED

The enumerator is a second, partial implementation of SHACL targeting, and it
can drift from pyshacl's. That is caught rather than assumed: every reported
result must map onto an enumerated pair, and one that does not is an enumerator
bug reported as such. Drift in the other direction -- enumerating something
pyshacl does not check -- shows up as a constraint that is CONFORMANT on every
example forever, which is what the coverage report exists to surface.
"""

from rdflib import BNode, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH

from .normalise import UNIT_CODE, UNIT_SUFFIX, inverse_predicate, layered, local

from ..ngsild.kinds import PAYLOAD_PATHS  # noqa: E402

NGSILD_VALUE_PATHS = set(PAYLOAD_PATHS)

# SHACL parameter -> the constraint component pyshacl names in its report.
# Only parameters that actually produce a result belong here: sh:path and
# sh:order describe a shape, they do not constrain anything.
PARAMETERS = {
    SH.minCount: 'MinCountConstraintComponent',
    SH.maxCount: 'MaxCountConstraintComponent',
    SH.datatype: 'DatatypeConstraintComponent',
    SH.nodeKind: 'NodeKindConstraintComponent',
    SH['class']: 'ClassConstraintComponent',
    SH.minInclusive: 'MinInclusiveConstraintComponent',
    SH.maxInclusive: 'MaxInclusiveConstraintComponent',
    SH.minExclusive: 'MinExclusiveConstraintComponent',
    SH.maxExclusive: 'MaxExclusiveConstraintComponent',
    SH.minLength: 'MinLengthConstraintComponent',
    SH.maxLength: 'MaxLengthConstraintComponent',
    SH.pattern: 'PatternConstraintComponent',
    SH.hasValue: 'HasValueConstraintComponent',
    SH['in']: 'InConstraintComponent',
    SH.node: 'NodeConstraintComponent',
    SH['or']: 'OrConstraintComponent',
    SH['and']: 'AndConstraintComponent',
    SH.xone: 'XoneConstraintComponent',
    SH['not']: 'NotConstraintComponent',
}


def subclasses_of(graph, cls):
    """cls and everything below it through rdfs:subClassOf*.

    sh:targetClass goes through the subclass closure -- that is SHACL, and it is
    why a Plasmacutter is a target of a shape written for Cutter.
    """
    found = {cls}
    pending = [cls]
    while pending:
        current = pending.pop()
        for sub in graph.subjects(RDFS.subClassOf, current):
            if sub not in found:
                found.add(sub)
                pending.append(sub)
    return found


def focus_nodes(shape, shapes_graph, data_graph, knowledge_graph=None):
    """Every node a shape targets, by any of SHACL's target mechanisms."""
    typing = data_graph
    closure = knowledge_graph if knowledge_graph is not None else shapes_graph

    nodes = set()
    for cls in shapes_graph.objects(shape, SH.targetClass):
        for member in subclasses_of(closure, cls):
            nodes.update(typing.subjects(RDF.type, member))
    for node in shapes_graph.objects(shape, SH.targetNode):
        nodes.add(node)
    for predicate in shapes_graph.objects(shape, SH.targetSubjectsOf):
        nodes.update(typing.subjects(predicate, None))
    for predicate in shapes_graph.objects(shape, SH.targetObjectsOf):
        nodes.update(typing.objects(None, predicate))
    # Implicit class target: a shape that is itself a class targets its instances.
    if (shape, RDF.type, RDFS.Class) in shapes_graph or \
            (shape, RDF.type, OWL.Class) in shapes_graph:
        for member in subclasses_of(closure, shape):
            nodes.update(typing.subjects(RDF.type, member))
    # A SPARQL target (SHACL-AF): whatever its SELECT binds to ?this.
    for target in shapes_graph.objects(shape, SH.target):
        for select in shapes_graph.objects(target, SH.select):
            nodes.update(_sparql_target(shapes_graph, target, str(select), typing))
    return nodes


def _sparql_target(shapes_graph, target, select, data_graph):
    """?this of a SPARQL target's SELECT, with its sh:prefixes declared."""
    lines = []
    for holder in shapes_graph.objects(target, SH.prefixes):
        for declaration in shapes_graph.objects(holder, SH.declare):
            prefix = shapes_graph.value(declaration, SH.prefix)
            namespace = shapes_graph.value(declaration, SH.namespace)
            if prefix is not None and namespace is not None:
                lines.append(f'PREFIX {prefix}: <{namespace}>')
    try:
        rows = data_graph.query('\n'.join(lines + [select]))
    except Exception:                               # noqa: BLE001
        return set()                                # pyshacl will say why
    return {row.this for row in rows if getattr(row, 'this', None) is not None}


def _constraints_of(node, shapes_graph):
    """The constraint components a single shape node declares."""
    return sorted({name for parameter, name in PARAMETERS.items()
                   if (node, parameter, None) in shapes_graph})


def _walk(node, shapes_graph, attribute, seen, value_path=None):
    """(attribute, component) pairs under a shape node, recursively.

    `attribute` is the NGSI-LD attribute a constraint is attributed to. A nested
    shape on ngsild:hasValue constrains the value of the attribute above it, so
    it keeps that attribute's name -- matching how a result is named on the way
    back out (normalise.attribute_name).
    """
    if node in seen:
        return []
    seen.add(node)

    pairs = [(layered(attribute, value_path, component), component)
             for component in _constraints_of(node, shapes_graph)]

    for child in shapes_graph.objects(node, SH.property):
        path = shapes_graph.value(child, SH.path)
        if isinstance(path, URIRef) and str(path) == UNIT_CODE:
            child_attribute = attribute + UNIT_SUFFIX
        elif isinstance(path, URIRef) and str(path) not in NGSILD_VALUE_PATHS:
            child_attribute = local(path)
        else:
            # An NGSI-LD inverse path is a two-hop sequence reported as an
            # unnamed blank node; it must resolve to the SAME name the adapter
            # gives it on the way back out, or a violation of it would look
            # like enumerator drift. Nothing in the corpus violates the
            # cartridge exclusivity rule, so this disagreement could not
            # surface there -- test_inverse_path_constraint_does_not_look_like_drift
            # makes one violate it.
            predicate = inverse_predicate(path, shapes_graph) \
                if isinstance(path, BNode) else None
            child_attribute = local(predicate) if predicate is not None else attribute
        on_value = path if isinstance(path, URIRef) and str(path) in NGSILD_VALUE_PATHS else None
        pairs.extend(_walk(child, shapes_graph, child_attribute, seen, on_value))
    return pairs


def constraints_of_shape(shape, shapes_graph):
    """Every (attribute, component) a node shape declares.

    SPARQL constraints and rules are node-level: they are attributed to the
    shape, not to an attribute, because their bodies may touch many.
    """
    pairs = _walk(shape, shapes_graph, '', set())
    if (shape, SH.sparql, None) in shapes_graph:
        pairs.append(('', 'SPARQLConstraintComponent'))
    return sorted(set(pairs))


def enumerate_pairs(shapes_graph, data_graph, knowledge_graph=None, shapes=None):
    """{(resource, attribute, component, shape)} that should be evaluated.

    Returns (pairs, inapplicable) where inapplicable holds the shapes whose
    target matched nothing -- reported NOT_APPLICABLE rather than omitted, so a
    shape that silently stopped matching anything is visible.
    """
    from .shapes import targeted_shapes

    pairs = set()
    inapplicable = []
    for shape in (shapes if shapes is not None else targeted_shapes(shapes_graph)):
        declared = constraints_of_shape(shape, shapes_graph)
        if not declared:
            continue
        targets = focus_nodes(shape, shapes_graph, data_graph, knowledge_graph)
        if not targets:
            inapplicable.append((str(shape), declared))
            continue
        for node in targets:
            for attribute, component in declared:
                pairs.add((str(node), attribute, component, str(shape)))
    return pairs, inapplicable
