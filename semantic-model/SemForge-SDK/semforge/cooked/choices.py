"""Candidate values for a constraint parameter.

`sh:class` means something different either side of the NGSI-LD encoding, and
offering one list for both is what makes a picker useless:

    …/hasObject   a Relationship points at an ENTITY -- Filter, Workpiece
    …/hasValue    a Property with an IRI value points into the VOCABULARY --
                  MachineState, Wasteclass, Material

The shipped kms says exactly that: `hasFilter → hasObject → sh:class Filter`
against `hasState → hasValue → sh:class MachineState`. So the slot the
constraint sits in decides which half of the ontology is offered.

Telling the halves apart needs a root for the entity hierarchy. The kms already
has one -- `base_entities:Entity`, with Machine, Cutter, Filter, Consumable,
Workpiece and FilterCartridge all beneath it -- so this is read from the
ontology rather than guessed. Where a package has no such root it is DECLARED,
in semforge.yaml, and where it is neither present nor declared the choices are
reported as unavailable rather than filled with everything.
"""

import os
from dataclasses import dataclass

from rdflib import OWL, RDF, RDFS, URIRef

from ..validate.normalise import local

NGSILD = 'https://uri.etsi.org/ngsi-ld/'
VALUE_PATH = NGSILD + 'hasValue'
OBJECT_PATH = NGSILD + 'hasObject'

# Scaffolding, not domain vocabulary. Offering these as a value class would be
# offering the encoding itself.
EXCLUDED = {NGSILD + 'Property', NGSILD + 'Relationship',
            str(RDFS.Datatype), str(RDFS.Class), str(OWL.Class)}

# Above this, sending the whole list to a picker stops being useful and the
# client asks the server to filter instead.
SEARCH_THRESHOLD = 200

NODE_KINDS = ['sh:IRI', 'sh:BlankNode', 'sh:Literal', 'sh:BlankNodeOrIRI',
              'sh:IRIOrLiteral', 'sh:BlankNodeOrLiteral']

COMMON_DATATYPES = ['xsd:string', 'xsd:integer', 'xsd:double', 'xsd:decimal',
                    'xsd:boolean', 'xsd:dateTime', 'xsd:date', 'xsd:anyURI']


def declared_entity_root(package_path):
    """`entityRoot:` from semforge.yaml, if the package declares one.

    It may be a full IRI or a prefixed name, and a prefixed name is what a
    human writes -- `semforge init` writes one. Taking it literally made
    `URIRef('testEntities:Entity')`, which matches nothing in the knowledge, so
    every scaffolded package reported an entity hierarchy of exactly one class:
    the root, with no descendants. Silently, because a hierarchy of one is a
    legal answer.
    """
    config = os.path.join(package_path, 'semforge.yaml')
    if not os.path.exists(config):
        return None
    from ruamel.yaml import YAML

    with open(config) as handle:
        data = YAML().load(handle) or {}
    root = data.get('entityRoot')
    if not root:
        return None
    return URIRef(expand(package_path, str(root)))


def expand(package_path, term):
    """A prefixed name against the package's agreed names, or the term itself."""
    from ..package.prefixes import canonical_map

    if '://' in term or term.startswith('urn:'):
        return term
    prefix, sep, rest = term.partition(':')
    if not sep:
        return term
    namespace = canonical_map(package_path).get(prefix)
    return namespace + rest if namespace else term


def entity_root(package):
    """The class every entity type descends from, or None.

    Declared wins. Otherwise it is derived as the common ancestor of the
    shapes' target classes -- which is a real signal rather than a guess: a
    shape's target IS an entity type, so whatever sits above all of them is the
    root of the entity hierarchy.
    """
    declared = declared_entity_root(package.path)
    if declared is not None:
        return declared

    from ..validate.shapes import node_shapes
    from rdflib.namespace import SH

    targets = {t for shape in node_shapes(package.shapes)
               for t in package.shapes.objects(shape, SH.targetClass)}
    if not targets:
        return None

    ancestors = None
    for target in targets:
        chain = _ancestors(package.knowledge, target)
        ancestors = chain if ancestors is None else (ancestors & chain)
    if not ancestors:
        return None
    # The most specific class that is still above every target.
    return max(ancestors, key=lambda c: len(_descendants(package.knowledge, c)))


def _ancestors(graph, cls):
    found = {cls}
    pending = [cls]
    while pending:
        current = pending.pop()
        for parent in graph.objects(current, RDFS.subClassOf):
            if parent not in found:
                found.add(parent)
                pending.append(parent)
    return found


def _ancestor_chain(graph, cls):
    """`cls`, then its superclasses, nearest first and in a fixed order.

    `_ancestors` answers a set, which is the right answer to "is this above
    that" and the wrong one to "which shape judges this": several may, and the
    nearest is the one to name.
    """
    order, seen, pending = [], {cls}, [cls]
    while pending:
        current = pending.pop(0)
        order.append(current)
        for parent in sorted(graph.objects(current, RDFS.subClassOf), key=str):
            if isinstance(parent, URIRef) and parent not in seen:
                seen.add(parent)
                pending.append(parent)
    return order


def _descendants(graph, cls):
    found = {cls}
    pending = [cls]
    while pending:
        current = pending.pop()
        for child in graph.subjects(RDFS.subClassOf, current):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def classify_classes(package):
    """(entity classes, knowledge classes, root). Both sorted by IRI."""
    declared = {c for c in package.knowledge.subjects(RDF.type, OWL.Class)
                if isinstance(c, URIRef) and str(c) not in EXCLUDED}
    # A class used only as a superclass may never be declared owl:Class.
    for subject, obj in package.knowledge.subject_objects(RDFS.subClassOf):
        for node in (subject, obj):
            if isinstance(node, URIRef) and str(node) not in EXCLUDED:
                declared.add(node)

    root = entity_root(package)
    if root is None:
        return [], sorted(declared, key=str), None

    entities = _descendants(package.knowledge, root) & declared
    entities.add(root)
    knowledge = declared - entities
    return sorted(entities, key=str), sorted(knowledge, key=str), root


@dataclass(frozen=True)
class EntityType:
    """A type an entity may be given, as the knowledge declares it."""
    iri: str
    term: str                 # what to write in the .jsonld
    label: str                # the local name
    parent: str = ''          # the term of its superclass, '' at the root
    shape: str = ''           # the node shape that will judge it, '' when none
    instances: int = 0        # entities of this type in the shipped model
    is_root: bool = False


def model_term(package, iri):
    """A term valid in the MODEL, whose @context decides what names mean.

    Not `term_for`, which answers for the shapes file: an entity type is
    written into a .jsonld and read back through the context, so the name has
    to be the one the context (or semforge.yaml, which overrides it) agreed.
    A full IRI is always valid, and is what a namespace with no agreed name
    gets.
    """
    from ..package.prefixes import names_by_namespace

    text = str(iri)
    names = names_by_namespace(package.path)
    for namespace in sorted(names, key=len, reverse=True):
        if text.startswith(namespace) and len(text) > len(namespace):
            return f'{names[namespace]}:{text[len(namespace):]}'
    return text


def entity_types(package):
    """(every type an entity may have, the root), from the knowledge.

    Typing a type by hand is how a model acquires a class the ontology has
    never heard of: nothing rejects it, no shape targets it, so every
    constraint stays silent and the entity reads as validated. The editor
    therefore offers these and nothing else -- a type that is genuinely
    missing is added to the knowledge first, which is where a type belongs.
    """
    from rdflib.namespace import SH

    from ..validate.shapes import node_shapes

    entities, _, root = classify_classes(package)
    if root is None:
        return [], None

    by_target = {}
    for shape in node_shapes(package.shapes):
        for target in package.shapes.objects(shape, SH.targetClass):
            by_target.setdefault(target, []).append(shape)

    found = []
    for cls in entities:
        parents = [p for p in package.knowledge.objects(cls, RDFS.subClassOf)
                   if isinstance(p, URIRef)]
        # sh:targetClass traverses rdfs:subClassOf*, so an inherited shape
        # judges this type just as its own would. Nearest first, because a
        # Plasmacutter is judged by CutterShape AND MachineShape and naming
        # whichever a set happened to yield made the row flicker.
        judging = [shape
                   for ancestor in _ancestor_chain(package.knowledge, cls)
                   for shape in sorted(by_target.get(ancestor, []), key=str)]
        found.append(EntityType(
            iri=str(cls),
            term=model_term(package, cls),
            label=local(cls),
            parent=model_term(package, parents[0]) if parents else '',
            shape=term_for(package.shapes, judging[0]) if judging else '',
            instances=len(set(package.model.subjects(RDF.type, cls))),
            is_root=(cls == root)))
    found.sort(key=lambda entry: entry.label)
    return found, str(root)


@dataclass(frozen=True)
class AttributeTerm:
    """An attribute the knowledge declares, and what it says about it."""
    iri: str
    term: str                 # what to write as the key in the .jsonld
    label: str
    kind: str = ''            # the NGSI-LD kind, from rdfs:range
    domain: str = ''          # the entity type that carries it, '' when none
    domain_iri: str = ''
    comment: str = ''         # rdfs:label, which is where the kms puts the gloss
    constrained: bool = False  # a shape has sh:path on it
    defined_at: str = ''      # knowledge.ttl:line
    # The attributes this one nests INSIDE, read from the shapes -- see
    # `nesting`. Which SPECIFIC attribute is the shapes' business; which KIND
    # of node carries it is rdfs:domain's, and that is `carrier_kind`.
    parents: tuple = ()
    carrier_kind: str = ''    # Property | Relationship | ... when it nests


# rdfs:range on an NGSI-LD attribute says which kind of attribute it is, and
# the kind decides which key carries the payload: a Relationship has `object`,
# a Property `value`, a JsonProperty `json`, a ListProperty `valueList`. The
# kms declares exactly this, so the kind is read rather than asked.
def _range_kinds():
    from ..ngsild.build import KINDS

    return {NGSILD + kind: kind for kind in KINDS}


RANGE_KIND = _range_kinds()

ATTRIBUTE_TYPES = (OWL.ObjectProperty, OWL.DatatypeProperty, RDF.Property,
                   OWL.AnnotationProperty)


# The encoding's own predicates. A nested sh:property on one of these is the
# VALUE of the attribute; a nested sh:property on anything else is a
# sub-attribute of it.
PAYLOAD_PATHS = {NGSILD + name for name in
                 ('hasValue', 'hasObject', 'hasJSON', 'hasValueList')}


def sub_attribute_domains():
    """The classes an attribute NODE has, which is what carries a sub-attribute.

    In the NGSI-LD-in-RDF encoding an attribute is a blank node, and that node
    is typed: `hasFilter` expands to a node `a ngsild:Relationship` carrying
    `ngsild:hasObject`. A sub-attribute hangs off THAT node, so its rdfs:domain
    is an ordinary class after all -- `ngsild:Relationship` for `hasTrust`,
    `ngsild:Property` for `hasXXXWorkpiece`, both measured against the shipped
    kms. No punning and nothing invented.

    What domain cannot say is WHICH attribute: it constrains the kind of node,
    not the one attribute. That half stays in the shapes, where the nesting is
    already spelled out.
    """
    from ..ngsild.build import KINDS

    return {NGSILD + kind: kind for kind in KINDS}


def nesting(package):
    """{attribute: the attributes it nests inside}, read from the SHAPES.

    A sub-attribute hangs off an ATTRIBUTE, not off an entity, so `rdfs:domain`
    cannot say where it belongs: domain takes a class, and an attribute is not
    one. Declaring `rdfs:domain hasFilter` would be punning -- it would make
    rdflib and any OWL tool treat `hasFilter` as a class as well as a property.

    The shapes say it already, and exactly. The NGSI-LD encoding is two-layer,
    so a property shape's inner `sh:property` is either the value
    (`ngsild:hasValue`, `hasObject`, `hasJSON`, `hasValueList`) or a
    sub-attribute. The kms's `hasTrust` sits inside `hasFilter` and its
    `hasXXXWorkpiece` inside `hasState`, both spelled out in shacl.ttl.

    So the knowledge says what a term IS -- its kind, its meaning -- and the
    shapes say where it may APPEAR. Which is the division this architecture
    already draws for values: `sh:class` is the shapes' business, not the
    ontology's.
    """
    from rdflib.namespace import SH

    found = {}

    def walk(shape, parent):
        for child in package.shapes.objects(shape, SH.property):
            paths = [str(p) for p in package.shapes.objects(child, SH.path)]
            path = paths[0] if paths else ''
            if path and path not in PAYLOAD_PATHS:
                if parent:
                    found.setdefault(path, set()).add(parent)
                walk(child, path)
            else:
                # The value layer: its own sh:property constrains the literal,
                # and nothing below it is an attribute.
                continue

    from ..validate.shapes import node_shapes

    for shape in node_shapes(package.shapes):
        walk(shape, '')
    return {child: sorted(parents) for child, parents in found.items()}


def attribute_terms(package):
    """Every attribute the knowledge declares.

    An attribute typed by hand is the same silent failure as a type typed by
    hand, one level down: nothing rejects an undeclared term, no `sh:path`
    matches it, so the constraint that should have judged it never fires and
    the entity reads as validated. `iffBaseEntities:hasOutWorkpiecexx` is in
    the shipped kms today, one letter pair away from a real attribute, and
    nothing has ever said so.
    """
    from rdflib.namespace import SH

    index = package.index('knowledge')
    constrained = {str(path) for path in package.shapes.objects(None, SH.path)}
    entity_family = {entry.iri for entry in entity_types(package)[0]}
    inside = nesting(package)
    sub_domains = sub_attribute_domains()

    found = []
    for iri in sorted({s for s, o in package.knowledge.subject_objects(RDF.type)
                       if o in ATTRIBUTE_TYPES and isinstance(s, URIRef)},
                      key=str):
        ranges = [str(r) for r in package.knowledge.objects(iri, RDFS.range)]
        domains = [d for d in package.knowledge.objects(iri, RDFS.domain)
                   if isinstance(d, URIRef)]
        kind = next((RANGE_KIND[r] for r in ranges if r in RANGE_KIND), '')
        if not kind and ranges:
            # A package may name the VALUE class instead of the NGSI-LD half --
            # `semforge init` used to. A class in the entity hierarchy can only
            # be the target of a Relationship; anything else is a value, so a
            # Property.
            kind = 'Relationship' if any(r in entity_family for r in ranges) \
                else 'Property'
        comment = next((str(t) for t in package.knowledge.objects(iri, RDFS.label)),
                       '')
        carrier_kind = next((sub_domains[str(d)] for d in domains
                             if str(d) in sub_domains), '')
        found.append(AttributeTerm(
            iri=str(iri), term=model_term(package, iri), label=local(iri),
            kind=kind, carrier_kind=carrier_kind,
            domain=model_term(package, domains[0]) if domains else '',
            domain_iri=str(domains[0]) if domains else '',
            comment=comment,
            constrained=str(iri) in constrained,
            defined_at=index.locator(iri),
            parents=tuple(model_term(package, parent)
                          for parent in inside.get(str(iri), ()))))
    return found


def attributes_for(package, entity_type):
    """The declared attributes an entity of this type may carry.

    `rdfs:domain` is the join: it says which entity type an attribute belongs
    to, and it is inherited, because a Plasmacutter is a Cutter is a Machine.
    An attribute with no domain is not filtered out -- a package may simply not
    have said -- but it is reported as open so the picker can rank it below the
    ones that name this type.
    """
    wanted = entity_type
    for entry in entity_types(package)[0]:
        if entity_type in (entry.term, entry.iri, entry.label):
            wanted = entry.iri
            break
    family = {str(c) for c in _ancestor_chain(package.knowledge, URIRef(wanted))}

    mine, open_ended = [], []
    for attribute in attribute_terms(package):
        if attribute.parents or attribute.carrier_kind:
            # A sub-attribute is not something an ENTITY carries: its subject
            # is an attribute NODE. Offering it here would invite `hasTrust`
            # onto a Filter, where no shape constrains it and nothing would
            # ever say so. Either half is enough to know -- the declaration
            # (rdfs:domain ngsild:Relationship) or the shapes' nesting.
            continue
        if not attribute.domain_iri:
            open_ended.append(attribute)
        elif attribute.domain_iri in family:
            mine.append(attribute)
    return mine, open_ended


def sub_attributes_for(package, parent):
    """The attributes that may nest inside this one.

    Two sources, and they answer different questions. The shapes say this
    sub-attribute is PLACED here -- a nested `sh:property`, which is the only
    thing that names one specific parent. The knowledge says it is ALLOWED
    here -- `rdfs:domain ngsild:Relationship` carries over to every
    Relationship. Placed ones come first, because a shape that mentions it is
    a stronger statement than a kind that permits it.
    """
    declared = attribute_terms(package)
    carrier = next((entry for entry in declared
                    if parent in (entry.term, entry.iri, entry.label)), None)
    if carrier is None:
        return []

    placed = [entry for entry in declared if carrier.term in entry.parents]
    seen = {entry.iri for entry in placed}
    allowed = [entry for entry in declared
               if entry.carrier_kind and entry.carrier_kind == carrier.kind
               and entry.iri not in seen]
    return placed + allowed


def term_for(shapes_graph, iri):
    """A term that is valid IN THE SHAPES FILE.

    A package whose prefixes are aligned (`semforge prefixes`) has one name per
    namespace, so this is usually the same answer either file would give. It is
    computed against the SHAPES graph anyway, because that is where the value is
    written and alignment is a property a package can lack -- the kms did, and
    the two files disagreed about what `:` and `default1:` meant. Where the
    shapes file binds no prefix at all, a full IRI is always valid.
    """
    try:
        prefix, _, name = shapes_graph.namespace_manager.compute_qname(
            str(iri), generate=False)
        return f'{prefix}:{name}'
    except Exception:
        return f'<{iri}>'


def class_stats(package):
    """{class: (individuals, shape uses)} -- the two signals that rank a class.

    A `sh:class` under a value slot says the value IRI is an INDIVIDUAL of that
    class, so a class with no individuals cannot be the answer, however
    plausible its name. And a class already used as sh:class somewhere is a
    proven value class rather than a guess.

    Without this the picker is alphabetical, which on the kms puts Binding,
    BoundConnector, BoundMap and FieldType -- connector infrastructure, none of
    it instantiable -- ahead of MachineState, Wasteclass and Material.
    """
    from rdflib.namespace import SH

    individuals = {}
    for _, cls in package.knowledge.subject_objects(RDF.type):
        if isinstance(cls, URIRef):
            individuals[cls] = individuals.get(cls, 0) + 1

    used = {}
    for cls in package.shapes.objects(None, SH['class']):
        if isinstance(cls, URIRef):
            used[cls] = used.get(cls, 0) + 1
    return individuals, used


def _as_choice(package, cls, note='', stats=None):
    individuals, used = stats if stats else ({}, {})
    count = individuals.get(cls, 0)
    uses = used.get(cls, 0)

    parts = [note] if note else []
    if uses:
        parts.append(f'used by {uses} shape(s)')
    parts.append(f'{count} individual(s)' if count
                 else 'no individuals -- cannot be a value')
    return {'value': term_for(package.shapes, cls),
            'label': local(cls),
            'detail': ' · '.join(parts),
            'iri': str(cls),
            'rank': (-uses, 0 if count else 1, -count, local(cls).lower())}


def _ordered(choices, search, limit):
    """Rank, filter by the typed text, and cap. Returns (choices, total)."""
    if search:
        needle = search.strip().lower()
        choices = [c for c in choices
                   if needle in c['label'].lower() or needle in c['iri'].lower()]
    choices.sort(key=lambda c: c['rank'])
    total = len(choices)
    if limit and total > limit:
        choices = choices[:limit]
    for choice in choices:
        choice.pop('rank', None)
    return choices, total


def choices_for(package, path_chain, parameter, search=None, limit=None):
    """Candidate values for one parameter, or [] when a free value is right.

    Returns (choices, note). The note explains an EMPTY list, because "no
    suggestions" and "suggestions unavailable" are different situations and a
    picker that silently offers nothing cannot tell you which you are in.

    `search` filters on the local name and the IRI, and `limit` caps the result
    -- an ontology of any size makes sending everything pointless, and the note
    says how much was left out.
    """
    if parameter == 'sh:nodeKind':
        return [{'value': kind, 'label': kind, 'detail': ''}
                for kind in NODE_KINDS], ''

    if parameter == 'sh:datatype':
        return [{'value': name, 'label': name, 'detail': ''}
                for name in COMMON_DATATYPES], ''

    if parameter != 'sh:class':
        return [], ''

    entities, knowledge, root = classify_classes(package)
    if root is None:
        return [], ('no entity root: the ontology has no class every '
                    'sh:targetClass descends from, and semforge.yaml declares '
                    'no entityRoot. Add one to get class suggestions.')

    slot = path_chain[-1] if path_chain else ''
    slot_iri = slot.strip('<>')
    is_object = slot_iri.endswith('hasObject') or slot_iri == OBJECT_PATH
    is_value = slot_iri.endswith('hasValue') or slot_iri == VALUE_PATH

    stats = class_stats(package)
    if is_object:
        found, total = _ordered(
            [_as_choice(package, c, f'entity type (under {local(root)})', stats)
             for c in entities], search, limit)
        return found, _note(found, total, 'entity classes below ' + local(root))
    if is_value:
        found, total = _ordered(
            [_as_choice(package, c, 'vocabulary class', stats)
             for c in knowledge], search, limit)
        return found, _note(found, total, 'non-entity classes in the ontology')

    # Not in a value slot: the constraint is on the attribute node itself, where
    # sh:class is unusual. Offer everything and say so.
    found, total = _ordered(
        [_as_choice(package, c, '', stats) for c in entities + knowledge],
        search, limit)
    return found, (f'not a value slot -- both entity and vocabulary classes '
                   f'offered ({total})')


def _note(found, total, what):
    if not total:
        return f'no {what}'
    if len(found) < total:
        return f'showing {len(found)} of {total}; keep typing to narrow'
    return ''
