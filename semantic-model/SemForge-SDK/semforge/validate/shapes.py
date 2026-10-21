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
    """A shapes graph containing only the given shapes.

    Built by concise bounded description, which follows the blank node tree a
    shape is written as. Shapes reference each other only through sh:node,
    which CBD does not cross -- so a referenced shape is pulled in explicitly.
    """
    from rdflib import Graph

    out = Graph()
    for prefix, namespace in shapes_graph.namespaces():
        out.bind(prefix, namespace)

    pending = list(shapes)
    done = set()
    while pending:
        shape = pending.pop()
        if shape in done:
            continue
        done.add(shape)
        for triple in shapes_graph.cbd(shape):
            out.add(triple)
        for referenced in out.objects(None, SH.node):
            if isinstance(referenced, URIRef) and referenced not in done:
                pending.append(referenced)
    return out
