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
from dataclasses import dataclass, field

from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH

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
    return roots
