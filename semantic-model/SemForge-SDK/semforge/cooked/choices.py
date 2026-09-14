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
