"""An existing ontology -> proposed shapes.

This is the seam the OPC UA path plugs into. `nodeset2owl.py` already turns a
nodeset into OWL and `owl2vt.py` derives Virtual Types; reimplementing either
would be duplicating work that is tested where it lives. What SemForge adds is
the step after: read the OWL, propose SHACL for what it declares, and keep the
result at the `proposed` tier so a generator cannot quietly make the model
stricter.

A generator that is confident is still a generator. `test_no_importer_reaches_
the_shapes_file` is what enforces that.
"""

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH

from .base import Proposal

NGSILD = Namespace('https://uri.etsi.org/ngsi-ld/')


def import_ontology(path, shape_namespace, only_classes=None):
    """Propose one NodeShape per owl:Class, with a property shape per property.

    Cardinality is left at [0, 1]: an ontology says a property EXISTS on a
    class, which is an open-world statement and not the same as requiring it.
    Turning rdfs:domain into minCount 1 is exactly the inference this project
    rejects -- so the proposal carries the shape and leaves requiredness to a
    human.
    """
    source = Graph()
    source.parse(path)

    base = Namespace(shape_namespace if shape_namespace.endswith(('/', '#'))
                     else shape_namespace + '/')
    proposal = Proposal(source=path, kind='imported-ontology')
    graph = proposal.graph
    graph.bind('sh', SH)
    graph.bind('ngsild', NGSILD)
    graph.bind('shapes', base)

    classes = sorted({s for s in source.subjects(RDF.type, OWL.Class)
                      if isinstance(s, URIRef)}, key=str)
    if only_classes:
        wanted = set(only_classes)
        classes = [c for c in classes
                   if str(c) in wanted or str(c).rsplit('/', 1)[-1] in wanted]

    for cls in classes:
        name = str(cls).rsplit('/', 1)[-1].rsplit('#', 1)[-1]
        shape = base[f'{name}Shape']
        graph.add((shape, RDF.type, SH.NodeShape))
        graph.add((shape, SH.targetClass, cls))
        proposal.propose(shape, f'node shape for {name}')

        for prop in sorted(source.subjects(RDFS.domain, cls), key=str):
            if not isinstance(prop, URIRef):
                continue
            outer = BNode()
            graph.add((shape, SH.property, outer))
            graph.add((outer, SH.path, prop))
            graph.add((outer, SH.nodeKind, SH.BlankNode))
            graph.add((outer, SH.maxCount, Literal(1)))
            graph.add((outer, SH.minCount, Literal(0)))

            inner = BNode()
            graph.add((outer, SH.property, inner))
            ranges = list(source.objects(prop, RDFS.range))
            is_relationship = any(str(r).endswith('Relationship') for r in ranges)
            graph.add((inner, SH.path,
                       NGSILD.hasObject if is_relationship else NGSILD.hasValue))
            graph.add((inner, SH.maxCount, Literal(1)))
            graph.add((inner, SH.minCount, Literal(1)))
            if is_relationship:
                graph.add((inner, SH.nodeKind, SH.IRI))
            proposal.propose(prop, f'property of {name}')
        if not list(graph.objects(shape, SH.property)):
            proposal.notes.append(
                f'{name}: no property has rdfs:domain pointing at it; the shape '
                f'would compile to nothing and is proposed empty')
    return proposal
