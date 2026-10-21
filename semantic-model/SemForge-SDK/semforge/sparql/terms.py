"""What a SPARQL query of this package can name: namespaces and terms.

Built once per loaded package. A term is a class (an entity type or a
vocabulary class), an attribute (with its NGSI-LD kind, Property or
Relationship -- which decides whether its value sits under ngsild:hasValue
or ngsild:hasObject), an individual (a vocabulary value), or one of the
NGSI-LD core terms every query of this package uses.
"""

from dataclasses import dataclass, field

from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS

NGSILD = 'https://uri.etsi.org/ngsi-ld/'
CORE = {
    'hasValue': 'the value of a Property instance',
    'hasObject': 'the entity a Relationship instance points at',
    'hasValueList': 'the value of a ListProperty instance',
    'hasObjectList': 'the entities of a ListRelationship instance',
    'hasJSON': 'the value of a JsonProperty instance',
    'observedAt': 'when the attribute instance was observed (xsd:dateTime)',
    'datasetId': 'which instance of a multi-instance attribute',
    'Property': 'the class of a Property instance',
    'Relationship': 'the class of a Relationship instance',
}


@dataclass
class Term:
    iri: str
    local: str
    kind: str                 # class | attribute | individual | ngsild | property
    detail: str = ''          # one line: "Property · on Filter", "an individual of MachineState"
    comment: str = ''
    attribute_kind: str = ''  # Property | Relationship | ... for an attribute
    domain_iri: str = ''      # the entity type that carries an attribute
    subs: tuple = ()          # the attributes its shapes nest inside it (IRIs)


@dataclass
class Terms:
    namespaces: dict = field(default_factory=dict)      # prefix -> namespace
    terms: dict = field(default_factory=dict)           # iri -> Term

    def prefix_for(self, iri):
        """(prefix, namespace) whose namespace is the longest one `iri` starts with."""
        best = None
        for prefix, namespace in self.namespaces.items():
            if str(iri).startswith(namespace) and (best is None or len(namespace) > len(best[1])):
                best = (prefix, namespace)
        return best

    def in_namespace(self, namespace):
        return [t for t in self.terms.values() if t.iri.startswith(namespace)
                and '/' not in t.iri[len(namespace):] and '#' not in t.iri[len(namespace):]]

    def own(self, iri):
        """Is this IRI in a namespace the package itself declares terms in --
        where a name nobody declared is a typo, not an outside vocabulary?"""
        return any(str(iri).startswith(ns) for ns in self.owned)

    owned: set = field(default_factory=set)
    # Attributes a shape nests a payload for: the ones shacl2flink can read as
    # NGSI-LD. Anything else it compiles as a plain triple.
    compiled: set = field(default_factory=set)


_cache = {}


def terms_for(package):
    key = id(package)
    if key not in _cache:
        _cache.clear()                     # one package at a time is all a page needs
        _cache[key] = (package, _build(package))
    return _cache[key][1]


def _local(iri):
    text = str(iri)
    for cut in ('#', '/'):
        if cut in text.rstrip(cut):
            text = text.rstrip(cut).rsplit(cut, 1)[-1]
    return text


def _nesting(package):
    """(attributes whose shapes nest a payload, {attribute: sub-attributes})
    -- read from the shapes, which is where shacl2flink reads them too."""
    from rdflib.namespace import SH

    from ..ngsild.kinds import PAYLOAD_PATHS

    compiled, subs = set(), {}
    shapes = package.shapes
    for prop in set(shapes.subjects(SH.path, None)):
        outer = shapes.value(prop, SH.path)
        if not isinstance(outer, URIRef):
            continue
        for inner in _inner_shapes(shapes, prop):
            path = shapes.value(inner, SH.path)
            if not isinstance(path, URIRef):
                continue
            if str(path) in PAYLOAD_PATHS:
                compiled.add(str(outer))
            elif not str(path).startswith(NGSILD):
                subs.setdefault(str(outer), set()).add(str(path))
    return compiled, subs


def _inner_shapes(shapes, prop):
    """The property shapes under a property shape, through sh:or/and/xone/not
    as shacl2flink reads them."""
    from rdflib.collection import Collection
    from rdflib.namespace import SH

    clauses = [prop]
    for connective in (SH['or'], SH['and'], SH.xone):
        for head in shapes.objects(prop, connective):
            clauses.extend(Collection(shapes, head))
    clauses.extend(shapes.objects(prop, SH['not']))
    for clause in clauses:
        yield from shapes.objects(clause, SH.property)


def _build(package):
    from ..cooked.choices import attribute_terms, entity_types
    from ..package.prefixes import canonical_map

    graphs = (package.knowledge, package.shapes, package.model)
    used = set()
    for graph in graphs:
        for triple in graph:
            used.update(str(term) for term in triple if isinstance(term, URIRef))

    namespaces = {}
    for prefix, namespace in canonical_map(package.path).items():
        namespaces[prefix] = str(namespace)
    for graph in graphs:
        for prefix, namespace in graph.namespaces():
            if prefix and prefix not in namespaces and any(u.startswith(str(namespace))
                                                           for u in used):
                namespaces[prefix] = str(namespace)
    namespaces.setdefault('ngsild', NGSILD)

    found = Terms(namespaces=namespaces)
    for name, said in CORE.items():
        found.terms[NGSILD + name] = Term(NGSILD + name, name, 'ngsild', 'NGSI-LD', said)

    knowledge = package.knowledge
    entity = {e.iri: e for e in entity_types(package)[0]}
    classes = {s for s in knowledge.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)} | \
        {s for s in knowledge.subjects(RDF.type, RDFS.Class) if isinstance(s, URIRef)}
    for cls in classes:
        info = entity.get(str(cls))
        detail = (f'entity type · under {info.parent}' if info and info.parent
                  else 'entity type' if info else 'class')
        found.terms[str(cls)] = Term(str(cls), _local(cls), 'class', detail,
                                     str(knowledge.value(cls, RDFS.comment) or
                                         knowledge.value(cls, RDFS.label) or ''))
    compiled, subs = _nesting(package)
    found.compiled = compiled
    for attribute in attribute_terms(package):
        detail = ' · '.join(p for p in (attribute.kind or 'plain property',
                                        f'on {" or ".join(attribute.domains)}'
                                        if attribute.domains else '')
                            if p)
        found.terms[attribute.iri] = Term(attribute.iri, attribute.label, 'attribute', detail,
                                          attribute.comment, attribute.kind,
                                          attribute.domain_iri,
                                          tuple(sorted(subs.get(attribute.iri, ()))))
    for subject, cls in knowledge.subject_objects(RDF.type):
        if isinstance(subject, URIRef) and str(subject) not in found.terms and \
                cls in classes:
            found.terms[str(subject)] = Term(str(subject), _local(subject), 'individual',
                                             f'an individual of {_local(cls)}',
                                             str(knowledge.value(subject, RDFS.label) or ''))
    for prop in set(knowledge.subjects(RDF.type, OWL.ObjectProperty)) | \
            set(knowledge.subjects(RDF.type, OWL.DatatypeProperty)) | \
            set(knowledge.subjects(RDF.type, RDF.Property)):
        if isinstance(prop, URIRef) and str(prop) not in found.terms:
            found.terms[str(prop)] = Term(str(prop), _local(prop), 'property', 'property',
                                          str(knowledge.value(prop, RDFS.comment) or ''))

    # The namespaces whose terms the package declares itself: a name there that
    # nobody declared is a typo. NGSI-LD's core is listed above, so it counts.
    found.owned = {ns for ns in namespaces.values()
                   if any(t.startswith(ns) for t in found.terms)
                   and not ns.startswith(('http://www.w3.org/', 'https://schema.org'))}
    return found
