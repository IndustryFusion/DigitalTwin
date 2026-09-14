"""The third ingredient: the knowledge, as a tree.

Shapes say what must hold; examples are what holds or does not. Neither says
what the model IS -- which classes exist, what descends from what, which
vocabularies have members. That lives in knowledge.ttl, and until now the only
way to read it here was to read the file.

The point of the view is not to mirror the ontology; rdflib and a text editor do
that. It is to show the three ingredients' joins, which are exactly where
authoring goes wrong:

  * an entity type with no shape -- nothing will ever be checked about it;
  * a class a shape uses as `sh:class` with no individuals -- a constraint
    nothing can satisfy, which reads as a data error forever;
  * a class with no instance in any example -- a shape that may never fire;
  * an individual no example mentions -- a vocabulary term the model never
    exercises.

Each of those is a row with a severity, not a separate report, so the thing you
need to fix is next to the thing it is about.
"""

import json
import os
import re
from dataclasses import dataclass, field

from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH

from ..errors import PackageError

from ..validate.normalise import curie, local, owner_and_edge
from ..validate.shapes import node_shapes
# The NGSI-LD keys that are not attributes; one definition, two trees.
from .examples import RESERVED

SKIP = {str(RDFS.Datatype), str(OWL.Class), str(RDFS.Class)}


@dataclass
class KnowledgeNode:
    # kind: group | class | individual | instance | usage
    kind: str
    label: str
    detail: str = ''
    iri: str = ''
    defined_at: str = ''       # knowledge.ttl:line
    shape: str = ''            # the node shape targeting this class
    shape_name: str = ''
    shape_at: str = ''         # shacl.ttl:line
    entity: str = ''           # for an instance row, the NGSI-LD id
    entity_type: str = ''
    file: str = ''
    severity: str = ''         # warning -- a join that is missing
    messages: list = field(default_factory=list)
    children: list = field(default_factory=list)


def flatten(nodes, depth=0):
    for node in nodes:
        yield depth, node
        yield from flatten(node.children, depth + 1)


# --- reading the pieces -------------------------------------------------------

def _declared_classes(package):
    """Every class the package talks about, however it was introduced.

    A class named only as a `sh:targetClass` or only as a superclass is still a
    class -- and one missing from knowledge.ttl is worth seeing, not hiding.
    """
    found = set()
    for predicate in (OWL.Class, RDFS.Class):
        found |= set(package.knowledge.subjects(RDF.type, predicate))
    for subject, obj in package.knowledge.subject_objects(RDFS.subClassOf):
        found.add(subject)
        found.add(obj)
    for shape in node_shapes(package.shapes):
        found |= set(package.shapes.objects(shape, SH.targetClass))
    return {c for c in found
            if isinstance(c, URIRef) and str(c) not in SKIP}


def _shapes_by_target(package):
    out = {}
    for shape in node_shapes(package.shapes):
        for target in package.shapes.objects(shape, SH.targetClass):
            out.setdefault(target, []).append(shape)
    return out


def _ancestors_with_shape(package, cls, by_target):
    """The shapes that will judge an instance of this class, inherited ones
    included."""
    found = []
    seen = set()
    pending = [cls]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        found.extend(by_target.get(current, []))
        pending.extend(package.knowledge.objects(current, RDFS.subClassOf))
    return found


def _children_of(package, cls):
    return sorted(
        (c for c in package.knowledge.subjects(RDFS.subClassOf, cls)
         if isinstance(c, URIRef)), key=lambda c: local(c))


def _example_files(package):
    """Every JSON-LD document in the package, example suites included.

    Counting instances in model-instance.jsonld alone would call a type
    uninstantiated while four cases under examples/ instantiate it.
    """
    from ..expect.store import load_expectations

    files = []
    model = package.sources.get('model')
    if model and os.path.exists(model):
        files.append(model)

    try:
        expectations = load_expectations(package.path)
    except Exception:                              # noqa: BLE001
        expectations = None
    for example in (expectations.examples if expectations else []):
        for relative in list(example.include) + [example.path]:
            for candidate in (os.path.join(package.examples_dir, relative),
                              os.path.join(package.path, relative), relative):
                if os.path.exists(candidate):
                    files.append(os.path.abspath(candidate))
                    break
    out = []
    for path in files:
        if path not in out:
            out.append(path)
    return out


def _scan_examples(package):
    """Read every example file once: what it instantiates, and where things are.

    Two results, because both come from the same scan and reading the files
    twice to keep them apart would be the only reason to separate them:

      * instances  {type local name: [(id, file, 'file:line')]}
      * places     {(entity id, attribute local name): ['file:line', ...]} and
                   {(entity id, ''): [...]} for the entity itself

    The second is what makes a usage row clickable. A row saying "urn:filter:1
    uses this" that cannot open urn:filter:1 is a dead end -- and the same
    entity id legitimately appears in several files, a good case and a bad one,
    so one location is not enough.
    """
    from .jsonloc import locate

    instances = {}
    places = {}
    for path in _example_files(package):
        try:
            with open(path, encoding='utf-8') as handle:
                raw = handle.read()
            document = json.loads(raw)
        except Exception:                          # noqa: BLE001
            continue
        try:
            index = locate(raw)
        except Exception:                          # noqa: BLE001
            index = {}
        entities = document if isinstance(document, list) else [document]
        for position, entity in enumerate(entities):
            if not isinstance(entity, dict):
                continue
            identifier = str(entity.get('id') or entity.get('@id') or '')
            kind = str(entity.get('type') or entity.get('@type') or '')
            if not identifier:
                continue
            line = index.get((position,))
            at = f'{path}:{line}' if line else ''
            if kind:
                instances.setdefault(kind.split(':')[-1], []).append(
                    (identifier, path, at))
            if at:
                places.setdefault((identifier, ''), []).append(at)
            for key in entity:
                if key in RESERVED:
                    continue
                where = index.get((position, key))
                if where:
                    places.setdefault(
                        (identifier, key.split(':')[-1].rsplit('/', 1)[-1]),
                        []).append(f'{path}:{where}')
    return instances, places


def _data_graph(package):
    """Every example file as one graph, for "is this term ever used".

    The shipped model-instance alone is not the answer: state_OFF is used by a
    case under examples/bad, and calling it unused would send someone deleting
    a term the suite depends on.
    """
    from rdflib import Graph

    from ..package.context import context_config, resolve_model_document

    graph = Graph()
    config = context_config(package.path)
    for path in _example_files(package):
        try:
            document, _ = resolve_model_document(package.path, path, config)
            graph.parse(data=json.dumps(document), format='json-ld')
        except Exception:                          # noqa: BLE001
            continue                               # reported by the examples view
    return graph if len(graph) else package.model


def _usages(graph, places):
    """{individual IRI: [(entity, attribute, 'file:line')]} -- where the data
    mentions it.

    This is the join that makes a vocabulary real: an individual no example
    references is a term the model declares and never uses. The location comes
    from the JSON scan rather than the graph, which has no positions -- and it
    is what lets the row open the entity that does the using.
    """
    out = {}
    for subject, predicate, obj in graph:
        if not isinstance(obj, URIRef):
            continue
        entity, edge = owner_and_edge(subject, graph)
        if entity is None:
            continue
        name = local(edge) if edge is not None else local(predicate)
        found = places.get((entity, name)) or places.get((entity, '')) or ['']
        for at in found:
            out.setdefault(str(obj), []).append((entity, name, at))
    return out


# --- the tree -----------------------------------------------------------------

def _relative(package, path):
    """The path as the package sees it, which is what distinguishes entities.

    `urn:filter:1` is not an address: it names a different entity in each of
    four files, and the file is the rest of the address. A basename will not do
    either -- `examples/subobjects/filter-on.jsonld` and
    `examples/test_StateOnCutterShape/good/filter-on.jsonld` are both
    filter-on.jsonld.
    """
    try:
        return os.path.relpath(path, package.path)
    except ValueError:                             # different drive on Windows
        return path


def _class_node(package, cls, context):
    shapes = context['shapes_by_target'].get(cls, [])
    instances = context['instances'].get(local(cls), [])
    individuals = context['individuals'].get(cls, [])
    used = context['used'].get(cls, 0)
    declared = cls in context['declared']

    node = KnowledgeNode(
        kind='class', label=curie(package.knowledge, cls), iri=str(cls),
        defined_at=context['knowledge_index'].locator(cls))
    if shapes:
        node.shape = str(shapes[0])
        node.shape_name = curie(package.shapes, shapes[0])
        node.shape_at = context['shapes_index'].locator(shapes[0])

    parts = []
    if shapes:
        parts.append(' + '.join(curie(package.shapes, s) for s in shapes))
    if individuals:
        parts.append(f'{len(individuals)} member(s)')
    if instances:
        parts.append(f'{len(instances)} instance(s)')
    if used:
        parts.append(f'used by {used} constraint(s)')

    # The joins. Each of these is silent today and expensive later.
    if not declared:
        node.severity = 'warning'
        node.messages.append(
            'a shape targets this class but knowledge.ttl does not declare it')
        parts.append('not declared')
    if used and not individuals and not context['is_entity'](cls):
        # Only for a vocabulary class. An entity class under sh:class is the
        # RANGE of a relationship -- its instances are entities, which live in
        # the data and not in knowledge.ttl, so "no individuals" says nothing
        # about whether the constraint can be met.
        node.severity = 'warning'
        node.messages.append(
            'used as sh:class but has no individuals, so no value can '
            'satisfy it')
        parts.append('no members')
    abstract = bool(_children_of(package, cls)) and not instances
    if context['is_entity'](cls) and not context['covered'](cls) \
            and not abstract:
        # An abstract root -- subclasses, no instances -- is not expected to
        # have a shape of its own, so flagging it would be noise on the two
        # rows at the top of every hierarchy.
        node.severity = node.severity or 'warning'
        node.messages.append(
            'no shape targets this type or anything above it, so nothing '
            'about it is checked')
        parts.append('no shape')
    elif not shapes and context['is_entity'](cls) \
            and not _children_of(package, cls):
        # Covered, but only through an ancestor. Worth saying: the shape that
        # judges a Plasmacutter is CutterShape, and sh:targetClass reaching
        # subclasses is the least obvious rule in SHACL.
        parts.append('checked by an inherited shape')
    node.detail = ' · '.join(parts)

    for child in _children_of(package, cls):
        node.children.append(_class_node(package, child, context))

    for identifier, path, at in instances:
        node.children.append(KnowledgeNode(
            kind='instance', label=identifier,
            # The path, not the basename: an id is not an address on its own
            # (four files define urn:filter:1) and two of the example files are
            # even called filter-on.jsonld.
            detail=_relative(package, path), entity=identifier,
            entity_type=curie(package.knowledge, cls), file=path,
            defined_at=at))

    for individual in individuals:
        node.children.append(
            _individual_node(package, individual, context, constrained=bool(used)))
    return node


def _individual_node(package, individual, context, constrained=False):
    label = next(package.knowledge.objects(individual, RDFS.label), None)
    # One row per place, so the count and the rows agree: the same term in the
    # same attribute of the same entity in two example files is two places, and
    # each opens a different file.
    usages = sorted(set(context['usages'].get(str(individual), [])))
    internal = any(package.knowledge.subject_predicates(individual))
    node = KnowledgeNode(
        kind='individual', label=local(individual),
        iri=str(individual),
        defined_at=context['knowledge_index'].locator(individual),
        detail=' · '.join(p for p in (
            str(label) if label else '',
            f'used in {len(usages)} place(s)' if usages
            else 'referenced in knowledge' if internal
            else 'unused') if p))
    # Flagged only for a vocabulary some shape draws values from. A Binding or
    # a ChemicalElement is not something an NGSI-LD example is supposed to
    # mention, and colouring those yellow would make the whole tree yellow and
    # the real gap -- a machine state no case exercises -- invisible.
    if constrained and not usages:
        node.severity = 'warning'
        node.messages.append(
            'no example gives this as a value, so no case exercises it')
    for entity, attribute, at in usages:
        detail = attribute
        if at:
            detail += ' · ' + _relative(package, at.rsplit(':', 1)[0])
        node.children.append(KnowledgeNode(
            kind='usage', label=entity, detail=detail, entity=entity,
            file=at.rsplit(':', 1)[0] if at else '', defined_at=at))
    return node


def build_knowledge(package):
    """Entity hierarchy and vocabularies, annotated with what connects them."""
    from .choices import class_stats, entity_root

    classes = _declared_classes(package)
    individuals = {}
    for subject, cls in package.knowledge.subject_objects(RDF.type):
        if isinstance(cls, URIRef) and isinstance(subject, URIRef) \
                and cls in classes:
            individuals.setdefault(cls, []).append(subject)
    for members in individuals.values():
        members.sort(key=lambda i: local(i))

    counted, used = class_stats(package)
    root = entity_root(package)
    entity_family = set()
    if root is not None:
        pending = [root]
        entity_family.add(root)
        while pending:
            for child in _children_of(package, pending.pop()):
                if child not in entity_family:
                    entity_family.add(child)
                    pending.append(child)

    by_target = _shapes_by_target(package)
    instances, places = _scan_examples(package)
    context = {
        'shapes_by_target': by_target,
        'instances': instances,
        'individuals': individuals,
        'used': used,
        'declared': classes - {
            c for c in classes
            if not any(package.knowledge.predicate_objects(c))},
        'usages': _usages(_data_graph(package), places),
        'knowledge_index': package.index('knowledge'),
        'shapes_index': package.index('shapes'),
        'is_entity': lambda cls: cls in entity_family,
        # sh:targetClass traverses rdfs:subClassOf*, so a type with no shape of
        # its own is still checked when an ancestor has one.
        'covered': lambda cls: bool(
            _ancestors_with_shape(package, cls, by_target)),
    }
    del counted

    roots = []
    if root is not None:
        entities = KnowledgeNode(
            kind='group', label='Entity types',
            detail=f'{len(entity_family)} type(s) under {local(root)}')
        entities.children.append(_class_node(package, root, context))
        if any(n.severity for _, n in flatten(entities.children)):
            entities.severity = 'warning'
        roots.append(entities)

    others = sorted((c for c in classes if c not in entity_family),
                    key=lambda c: (-len(individuals.get(c, [])), local(c)))
    # Only the tops: a vocabulary class with a parent is shown under it.
    tops = [c for c in others
            if not any(p in others
                       for p in package.knowledge.objects(c, RDFS.subClassOf))]
    if tops:
        vocabulary = KnowledgeNode(
            kind='group', label='Vocabulary classes',
            detail=f'{len(others)} class(es)')
        for cls in tops:
            vocabulary.children.append(_class_node(package, cls, context))
        if any(n.severity for _, n in flatten(vocabulary.children)):
            vocabulary.severity = 'warning'
        roots.append(vocabulary)

    attributes = _attributes_group(package, context)
    if attributes is not None:
        roots.append(attributes)
    encoding = _ngsild_group(package)
    if encoding is not None:
        roots.append(encoding)
    return roots


def _ngsild_group(package):
    """The NGSI-LD vocabulary: what the terms of the ENCODING mean.

    Not the package's, which is why it is last and why nothing here is
    editable. It is here because the rule this project applies to everything
    else -- declared before used -- was the one rule the encoding itself did
    not follow: `rdfs:range ngsild:Property` pointed at a class no file
    declared, and a typo in it produced an attribute with no kind and no
    complaint.

    A term the package uses and the vocabulary does not declare is reported
    here, which is the same finding from the other side.
    """
    from rdflib.namespace import OWL

    from ..expect.vocabulary import unknown_ngsild_terms
    from ..ngsild.vocabulary import SHIPPED, declared_source

    if not len(package.vocabulary):
        return None

    NGSILD = 'https://uri.etsi.org/ngsi-ld/'
    used = _ngsild_usage(package)
    source = declared_source(package.path)
    classes, slots = [], []
    for subject in sorted({s for s in package.vocabulary.subjects(None, None)
                           if isinstance(s, URIRef)
                           and str(s).startswith(NGSILD)
                           and len(str(s)) > len(NGSILD)}, key=str):
        name = str(subject)[len(NGSILD):]
        uses = used.get(str(subject), 0)
        comment = next((str(c) for c in
                        package.vocabulary.objects(subject, RDFS.comment)), '')
        node = KnowledgeNode(
            kind='term', label=f'ngsild:{name}', iri=str(subject),
            detail=' · '.join(filter(None, [
                f'{uses} use(s)' if uses else 'not used here', comment])))
        target = classes if (subject, RDF.type, OWL.Class) in package.vocabulary \
            else slots
        target.append(node)

    group = KnowledgeNode(
        kind='group', label='NGSI-LD vocabulary',
        detail=f'{len(classes) + len(slots)} term(s) · '
               f'{source if source else "shipped with the SDK"}')
    if classes:
        kinds = KnowledgeNode(
            kind='carrier', label='Attribute kinds',
            detail="what an attribute's `type` may say")
        kinds.children = classes
        group.children.append(kinds)
    if slots:
        holder = KnowledgeNode(
            kind='carrier', label='Slots and metadata',
            detail='where the payload hangs, and what is recorded beside it')
        holder.children = slots
        group.children.append(holder)

    missing = unknown_ngsild_terms(package)
    if missing:
        holder = KnowledgeNode(
            kind='carrier', label='Used but not declared',
            detail=f'{len(missing)} term(s) this vocabulary does not have',
            severity='warning')
        for entry in missing:
            holder.children.append(KnowledgeNode(
                kind='term', label=f'ngsild:{entry.term}', iri=entry.iri,
                detail='in the ' + ', '.join(entry.where),
                severity='warning', messages=[entry.message]))
        group.children.append(holder)
        group.severity = 'warning'
    del SHIPPED
    return group


def _ngsild_usage(package):
    """{IRI: how many times the package mentions this NGSI-LD term}."""
    NGSILD = 'https://uri.etsi.org/ngsi-ld/'
    counts = {}
    graphs = [package.knowledge, package.shapes]
    try:
        graphs.append(_data_graph(package))
    except Exception:                              # noqa: BLE001
        pass
    for graph in graphs:
        for triple in graph:
            for node in triple:
                if isinstance(node, URIRef) and str(node).startswith(NGSILD):
                    counts[str(node)] = counts.get(str(node), 0) + 1
    return counts


def _attributes_group(package, context):
    """The attribute hierarchy: what carries what, and what nests in it.

    The third thing knowledge.ttl declares, and the one the view could not
    show. Entity types were there and vocabularies were there, but the
    attributes -- the terms every shape's `sh:path` names and every document's
    keys are -- had to be read out of the file.

    Three nestings, in the order they mean something:

      * `rdfs:subPropertyOf`, where a package has it -- a real hierarchy;
      * `rdfs:domain`, which says which entity type carries it, and is
        inherited, so it is shown under the type that DECLARES it;
      * the shapes' nesting, which puts a sub-attribute under the attribute it
        hangs off -- the only thing that names one specific parent.

    knowledge.ttl also declares the ontology's OWN relations --
    `base:bindsFirmware`, `material:contains` -- which are never keys in a
    document and which no shape should constrain. They are shown apart, and
    judged apart: reporting them as unused and unchecked is true of a document
    and meaningless of an ontology.

    Flags only where absence is a defect. For an attribute: no shape constrains
    it, so nothing is ever checked against it; no document carries it, so no
    constraint about it can fire; no `rdfs:range`, so nothing says which half
    of the encoding it is. For an ontology relation: nothing uses it, in the
    data or in the ontology itself.
    """
    from .choices import attribute_terms, model_term
    from .shapelink import find_property_shape

    declared = attribute_terms(package)
    if not declared:
        return None

    by_term = {entry.term: entry for entry in declared}
    used = _attribute_usage(package)
    in_ontology = _ontology_usage(package)
    index = package.index('knowledge')

    # A sub-attribute is shown under its parent, never at the top.
    nested = {}
    for entry in declared:
        for parent in entry.parents:
            nested.setdefault(parent, []).append(entry)

    # rdfs:subPropertyOf, when a package declares it.
    below = {}
    for child, parent in package.knowledge.subject_objects(RDFS.subPropertyOf):
        if isinstance(child, URIRef) and isinstance(parent, URIRef):
            below.setdefault(model_term(package, parent), []).append(
                model_term(package, child))

    placed = {child for children in nested.values() for child in children}
    placed |= {by_term[t] for terms in below.values() for t in terms
               if t in by_term}

    def node_for(entry, seen, carrier=''):
        if entry.term in seen:
            return None                     # a cycle in subPropertyOf
        seen = seen | {entry.term}
        uses = used.get(entry.iri, 0)
        ontology_uses = in_ontology.get(entry.iri, 0)
        node = KnowledgeNode(
            kind='attribute' if entry.ngsild else 'relation',
            label=entry.term, iri=entry.iri,
            detail=_attribute_detail(entry, uses, ontology_uses),
            defined_at=index.locator(URIRef(entry.iri)))
        # The join the view exists for: where this attribute is CONSTRAINED.
        # An attribute row that cannot reach its property shape leaves you to
        # find it by hand, which is the work the view removes.
        if carrier and entry.ngsild:
            found = find_property_shape(package, carrier, entry.term)
            if found:
                node.shape = found['shape']
                node.shape_name = found['shapeName']
                node.shape_at = f"{found['file']}:{found['line']}"
        node.messages = _attribute_notes(entry, uses, ontology_uses)
        node.severity = 'warning' if node.messages else ''
        for child in sorted(nested.get(entry.term, []), key=lambda e: e.term):
            made = node_for(child, seen, carrier)
            if made is not None:
                node.children.append(made)
        for term in sorted(below.get(entry.term, [])):
            if term in by_term:
                made = node_for(by_term[term], seen, carrier)
                if made is not None:
                    node.children.append(made)
        return node

    carriers = {}
    homeless = []
    relations = []
    for entry in declared:
        if entry in placed:
            continue                        # shown under its parent
        if not entry.ngsild:
            relations.append(entry)
        elif entry.domain and not entry.carrier_kind:
            carriers.setdefault(entry.domain, []).append(entry)
        elif entry.carrier_kind:
            carriers.setdefault(f'any {entry.carrier_kind}', []).append(entry)
        else:
            homeless.append(entry)

    group = KnowledgeNode(
        kind='group', label='Attributes',
        detail=f'{len(declared) - len(relations)} attribute(s)' +
               (f' · {len(relations)} ontology relation(s)' if relations else ''))
    for carrier in sorted(carriers):
        holder = KnowledgeNode(
            kind='carrier', label=carrier,
            iri=by_term[carrier].iri if carrier in by_term else '',
            detail=f'{len(carriers[carrier])} attribute(s)')
        for entry in sorted(carriers[carrier], key=lambda e: e.term):
            made = node_for(entry, frozenset(), carrier)
            if made is not None:
                holder.children.append(made)
        group.children.append(holder)
    if homeless:
        holder = KnowledgeNode(
            kind='carrier', label='carried by nothing declared',
            detail='no rdfs:domain, and no shape nests them', severity='warning')
        for entry in sorted(homeless, key=lambda e: e.term):
            made = node_for(entry, frozenset())
            if made is not None:
                holder.children.append(made)
        group.children.append(holder)

    if relations:
        # The ontology's own relations: declared here, used here, and never a
        # key in a document. Apart, so the attributes above stay readable.
        holder = KnowledgeNode(
            kind='carrier', label='Ontology relations',
            detail='used within the ontology, never as a document key')
        for entry in sorted(relations, key=lambda e: e.term):
            made = node_for(entry, frozenset())
            if made is not None:
                holder.children.append(made)
        if any(n.severity for _, n in flatten(holder.children)):
            holder.severity = 'warning'
        group.children.append(holder)

    if any(n.severity for _, n in flatten(group.children)):
        group.severity = 'warning'
    return group


def _attribute_usage(package):
    """{attribute IRI: how many times a document carries it}."""
    counts = {}
    for _, predicate, _ in _data_graph(package):
        if isinstance(predicate, URIRef):
            counts[str(predicate)] = counts.get(str(predicate), 0) + 1
    return counts


def _ontology_usage(package):
    """{IRI: how many statements in the KNOWLEDGE use it as a predicate}."""
    counts = {}
    for _, predicate, _ in package.knowledge:
        if isinstance(predicate, URIRef):
            counts[str(predicate)] = counts.get(str(predicate), 0) + 1
    return counts


def _attribute_detail(entry, uses, ontology_uses):
    if not entry.ngsild:
        return ' · '.join(filter(None, [
            f'{ontology_uses} statement(s)' if ontology_uses
            else 'used by nothing',
            entry.comment]))
    parts = [entry.kind or 'kind not declared']
    if entry.parents:
        parts.append('inside ' + ', '.join(entry.parents))
    elif entry.carrier_kind:
        parts.append(f'on any {entry.carrier_kind}')
    parts.append(f'{uses} use(s)' if uses else 'used by nothing')
    if not entry.constrained:
        parts.append('unconstrained')
    if entry.comment:
        parts.append(entry.comment)
    return ' · '.join(parts)


def _attribute_notes(entry, uses, ontology_uses):
    if not entry.ngsild:
        if uses or ontology_uses:
            return []
        return ['Nothing uses this -- not a document, not the ontology '
                'itself. It is a term the package declares and never says '
                'anything with.']
    notes = []
    if not entry.kind:
        notes.append('No rdfs:range, so nothing says whether this is a '
                     'Property or a Relationship -- the two carry their '
                     'payload under different keys.')
    if not entry.constrained:
        notes.append('No sh:path names it, so no constraint is ever checked '
                     'against it.')
    if not uses:
        notes.append('No document carries it, so no constraint about it can '
                     'fire.')
    return notes


def add_entity_type(package, name, parent):
    """Declare a new entity type in the knowledge, beneath `parent`.

    The editor offers only the types the knowledge declares, so this is the way
    a type that is genuinely missing gets used: it is added HERE first, and the
    entity is typed with it afterwards. A type introduced the other way round
    -- typed into a .jsonld and never declared -- is the failure this exists to
    prevent: no shape targets it, so every constraint stays silent and the
    entity reads as validated.

    It lands in the file that declares its parent, which is where a reader will
    look for it, and it takes its parent's namespace: a subclass of
    `base_entities:Machine` belongs in base_entities.
    """
    from .choices import entity_types

    local_name = (name or '').strip()
    if not local_name:
        raise PackageError('an entity type needs a name')
    if not re.match(r'^[A-Za-z][\w-]*$', local_name):
        raise PackageError(
            f'{local_name!r} is not usable as a class name: a letter, then '
            'letters, digits, underscores or hyphens')

    known, root = entity_types(package)
    if root is None:
        raise PackageError(
            'this package has no entity hierarchy to add to. Declare '
            '`entityRoot:` in semforge.yaml, or give one shape an '
            'sh:targetClass.')
    chosen = next((entry for entry in known
                   if parent in (entry.term, entry.iri, entry.label)), None)
    if chosen is None:
        raise PackageError(
            f'{parent} is not an entity type in this package. '
            f'Known: {", ".join(entry.term for entry in known)}')

    namespace = _namespace_of(chosen.iri)
    iri = URIRef(namespace + local_name)
    if (iri, None, None) in package.knowledge:
        raise PackageError(f'{local_name} is already declared')

    index = package.index('knowledge')
    path = index.file_for(URIRef(chosen.iri)) or package.sources['knowledge']
    with open(path, encoding='utf-8') as handle:
        text = handle.read()

    subject = _turtle_name(text, iri)
    superclass = _turtle_name(text, URIRef(chosen.iri))
    kind = _turtle_name(text, OWL.Class)
    edge = _turtle_name(text, RDFS.subClassOf)

    addition = (f'\n{subject} a {kind} ;\n'
                f'    {edge} {superclass} .\n')
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write(addition)

    line = len(text.splitlines()) + 2
    from .choices import model_term
    return {'iri': str(iri), 'term': model_term(package, iri),
            'label': local_name, 'parent': chosen.term,
            'file': path, 'line': line}


def _namespace_of(iri):
    text = str(iri)
    cut = max(text.rfind('#'), text.rfind('/'))
    return text[:cut + 1] if cut >= 0 else text


def _turtle_name(text, iri):
    """A prefixed name valid in THIS file, or the IRI in angle brackets.

    A full IRI always parses, so a file that binds no prefix for the namespace
    still gets a legal statement rather than a broken one.
    """
    from ..package.prefixes import PREFIX_LINE

    text_iri = str(iri)
    best = None
    for match in PREFIX_LINE.finditer(text):
        prefix, namespace = match.group(2) or '', match.group(3)
        if text_iri.startswith(namespace) and len(text_iri) > len(namespace):
            rest = text_iri[len(namespace):]
            if re.match(r'^[\w-]+$', rest) and \
                    (best is None or len(namespace) > best[0]):
                best = (len(namespace), f'{prefix}:{rest}')
    return best[1] if best else f'<{text_iri}>'


def add_attribute_term(package, name, kind, domain, label=''):
    """Declare a new attribute in the knowledge, carried by `domain`.

    The counterpart of `add_entity_type`, one level down and for the same
    reason: an attribute's NAME is what a shape's `sh:path` matches, so one
    that is never declared is not a broken document but an invisible one.

    `domain` names what CARRIES it, and there are two kinds of carrier:

      * an entity type -- an ordinary attribute, `rdfs:domain` the class,
        inherited down the hierarchy;
      * another attribute -- a sub-attribute. Its subject is the parent's
        attribute NODE, and that node is typed, so `rdfs:domain` is the node's
        class: `ngsild:Relationship` for something nested in a Relationship,
        `ngsild:Property` for something nested in a Property. An ordinary
        class, nothing invented, no punning.

    Domain constrains the KIND of carrier, not the one attribute. Which
    specific attribute it nests inside is the shapes' business, spelled out by
    a nested `sh:property` -- the same division that puts `sh:class` there.

    `rdfs:range` says which half of the encoding the attribute itself is.
    """
    from .choices import NGSILD, attribute_terms, entity_types

    local_name = (name or '').split(':')[-1].strip()
    if not local_name:
        raise PackageError('an attribute needs a name')
    if not re.match(r'^[A-Za-z][\w-]*$', local_name):
        raise PackageError(
            f'{local_name!r} is not usable as an attribute name: a letter, '
            'then letters, digits, underscores or hyphens')
    from ..ngsild.build import KINDS

    if kind not in KINDS:
        raise PackageError(
            f'{kind!r} is not an NGSI-LD attribute kind. '
            f'Expected one of: {", ".join(KINDS)}')

    known, root = entity_types(package)
    carrier = next((entry for entry in known
                    if domain in (entry.term, entry.iri, entry.label)), None)
    # A carrier may be another ATTRIBUTE: then this is a sub-attribute, and the
    # domain is the class of that attribute's node.
    parent = None
    if carrier is None and domain:
        parent = next((entry for entry in attribute_terms(package)
                       if domain in (entry.term, entry.iri, entry.label)), None)
        if parent is None:
            raise PackageError(
                f'{domain} is neither an entity type nor an attribute in this '
                f'package, so nothing can carry {local_name}. Declare it '
                f'first.')
        if not parent.kind:
            raise PackageError(
                f'{parent.term} does not say which kind of attribute it is '
                f'(no rdfs:range), so there is no class to carry '
                f'{local_name}. Give it a range first.')
    if carrier is None and parent is None and root is None:
        raise PackageError(
            'this package has no entity hierarchy, so there is no namespace '
            'to declare an attribute in. Declare `entityRoot:` in '
            'semforge.yaml, or give one shape an sh:targetClass.')

    # A sub-attribute hangs off an ATTRIBUTE, not off an entity, so it has no
    # entity type to be its domain -- the kms's `hasTrust`, which sits inside
    # `hasFilter`, is one. An empty domain declares it without one.
    home = carrier.iri if carrier is not None else \
        (parent.iri if parent is not None else root)
    iri = URIRef(_namespace_of(home) + local_name)
    if any(entry.iri == str(iri) for entry in attribute_terms(package)):
        raise PackageError(f'{local_name} is already declared')

    index = package.index('knowledge')
    path = index.file_for(URIRef(home)) or package.sources['knowledge']
    with open(path, encoding='utf-8') as handle:
        text = handle.read()

    declaration = OWL.ObjectProperty if kind == 'Relationship' \
        else OWL.DatatypeProperty
    lines = [f'{_turtle_name(text, iri)} a {_turtle_name(text, declaration)}']
    if carrier is not None:
        lines.append(f'    {_turtle_name(text, RDFS.domain)} '
                     f'{_turtle_name(text, URIRef(carrier.iri))}')
    elif parent is not None:
        lines.append(f'    {_turtle_name(text, RDFS.domain)} '
                     f'{_turtle_name(text, URIRef(NGSILD + parent.kind))}')
    lines.append(f'    {_turtle_name(text, RDFS.range)} '
                 f'{_turtle_name(text, URIRef(NGSILD + kind))}')
    if label:
        lines.append(f'    {_turtle_name(text, RDFS.label)} '
                     f'{json.dumps(label)}')
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write('\n' + ' ;\n'.join(lines) + ' .\n')

    from .choices import model_term
    return {'iri': str(iri), 'term': model_term(package, iri),
            'label': local_name, 'kind': kind,
            'domain': carrier.term if carrier is not None else
                      (parent.term if parent is not None else ''),
            'file': path, 'line': len(text.splitlines()) + 2}
