"""JSON Schema -> proposed OWL and SHACL.

The Python counterpart of datamodel/tools/jsonschema2shacl.js, emitting into a
Proposal rather than into the package. Only the constructs that map cleanly are
translated; anything else is recorded as a note, because a silently skipped
schema keyword is a constraint the author thinks they have and does not.
"""

import json

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, XSD

from .base import Proposal

NGSILD = Namespace('https://uri.etsi.org/ngsi-ld/')

TYPES = {
    'string': XSD.string,
    'number': XSD.double,
    'integer': XSD.integer,
    'boolean': XSD.boolean,
}


def _property_shape(graph, schema, path, required):
    """The two-layer NGSI-LD shape: cardinality on the attribute, type on the value."""
    outer = BNode()
    graph.add((outer, SH.path, path))
    graph.add((outer, SH.nodeKind, SH.BlankNode))
    graph.add((outer, SH.maxCount, Literal(1)))
    graph.add((outer, SH.minCount, Literal(1 if required else 0)))

    inner = BNode()
    graph.add((outer, SH.property, inner))
    graph.add((inner, SH.path, NGSILD.hasValue))
    graph.add((inner, SH.maxCount, Literal(1)))
    graph.add((inner, SH.minCount, Literal(1)))

    datatype = TYPES.get(schema.get('type'))
    if datatype is not None:
        graph.add((inner, SH.datatype, datatype))
    for keyword, parameter in (('minimum', SH.minInclusive),
                               ('maximum', SH.maxInclusive),
                               ('exclusiveMinimum', SH.minExclusive),
                               ('exclusiveMaximum', SH.maxExclusive),
                               ('minLength', SH.minLength),
                               ('maxLength', SH.maxLength),
                               ('pattern', SH.pattern)):
        if keyword in schema:
            value = schema[keyword]
            graph.add((inner, parameter,
                       Literal(value) if not isinstance(value, str)
                       else Literal(value)))
    return outer


def import_json_schema(path, namespace, class_name=None):
    """Read a JSON Schema and propose an OWL class plus a NodeShape."""
    with open(path, encoding='utf-8') as handle:
        schema = json.load(handle)

    base = Namespace(namespace if namespace.endswith(('/', '#'))
                     else namespace + '/')
    name = class_name or schema.get('title') or 'ImportedType'
    cls = base[name]
    shape = base[f'{name}Shape']

    proposal = Proposal(source=path, kind='imported-schema')
    graph = proposal.graph
    graph.bind('sh', SH)
    graph.bind('owl', OWL)
    graph.bind('ngsild', NGSILD)
    graph.bind('base', base)

    graph.add((cls, RDF.type, OWL.Class))
    if schema.get('description'):
        graph.add((cls, RDFS.comment, Literal(schema['description'])))
    graph.add((shape, RDF.type, SH.NodeShape))
    graph.add((shape, SH.targetClass, cls))
    proposal.propose(cls, 'class from schema title')
    proposal.propose(shape, 'node shape from schema properties')

    required = set(schema.get('required') or [])
    for key, definition in (schema.get('properties') or {}).items():
        if not isinstance(definition, dict):
            proposal.notes.append(f'{key}: unsupported property definition')
            continue
        if definition.get('type') in ('object', 'array'):
            # Nested objects and arrays need a modelling decision -- a
            # sub-attribute, a relationship, or a ListProperty -- that a schema
            # does not carry. Skipping it silently would hand the author a
            # constraint they do not have.
            proposal.notes.append(
                f'{key}: type {definition["type"]!r} not translated; it needs a '
                f'modelling decision (sub-attribute, relationship or list)')
            continue
        graph.add((base[key], RDF.type, OWL.ObjectProperty))
        graph.add((base[key], RDFS.domain, cls))
        graph.add((base[key], RDFS.range, NGSILD.Property))
        graph.add((shape, SH.property,
                   _property_shape(graph, definition, base[key], key in required)))
        proposal.propose(base[key], f'property {key} from schema')
    return proposal


def as_turtle(proposal):
    return proposal.graph.serialize(format='turtle')


def empty_graph():
    return Graph()


__all__ = ['import_json_schema', 'as_turtle', 'empty_graph', 'URIRef']
