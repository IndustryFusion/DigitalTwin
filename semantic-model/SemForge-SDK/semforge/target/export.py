"""Export a package to the KMS triple shacl2flink consumes (section 6.3).

Two properties matter more than convenience here.

**Determinism (H5).** Export twice, get identical bytes -- otherwise every
export produces a spurious git diff and the semantic diff drowns in noise. The
`default1:`/`default2:` auto-prefixes in today's knowledge.ttl are exactly that
failure. Determinism is achieved by NOT reserialising: Turtle artifacts are
emitted from their source text, which is byte-stable by construction and also
preserves the comments rdflib would drop (C2 -- an alert should refer to a shape
that appears in the file you wrote).

**Emission mode.** model-instance.jsonld and model-instance.scorpio.jsonld are
the same model serialised for different consumers, and today they are two files
a human keeps in sync:

    compile   keep the observation stream. Four hasStrength values sharing a
              datasetId exercise the dedup and the aggregations built on it.
    broker    collapse each (id, attribute, datasetId) to its latest
              observedAt. NGSI-LD 4.5.5.1 permits only one default instance per
              attribute IN ANY REQUEST, and 4.5.5.3 requires a receiver to keep
              the most recent -- so the four-instance form is not a conformant
              request, however well it compiles offline.
"""

import json
import os
import shutil
from enum import Enum


def complete_node_kinds(text, where=None):
    """Add the `sh:nodeKind sh:BlankNode` the NGSI-LD encoding implies.

    An attribute IS a blank node carrying hasValue/hasObject, so stating it on
    every forward attribute path is boilerplate an author should not have to
    write -- the cooked view hides it. The EXPORTED shapes still need it,
    because the compiler and any other consumer read plain SHACL with no
    knowledge of that convention.

    Two cases are deliberately skipped, and the second is why this is not a
    blanket rewrite:

    * a VALUE shape, where nodeKind is a real choice -- sh:IRI for a
      relationship target, sh:Literal for a plain value;
    * an INVERSE path, which does not reach an attribute node at all. It walks
      back to the entity pointing here, which is an IRI. CartridgeShape's
      exclusivity constraint is exactly that, and BlankNode there would be
      wrong rather than missing.

    Returns (text, added). Adding nothing returns the input unchanged, so a
    package that already states them exports byte-identically. `where`, a list,
    receives each place it added one -- "shape › attribute path" -- so the
    export can say exactly which shapes it changed.

    Its contract, pinned by test_node_kind.py: the added constraint changes no
    verdict on NGSI-LD data, where an attribute IS a blank node -- the corpus
    validates identically with and without it.
    """
    from ..cooked.tree import IMPLIED_NODE_KIND, VALUE_PATHS, \
        forward_attribute_path
    from ..rdfio import add_parameter, property_blocks
    from ..rdfio.turtle_index import TurtleIndex

    def gather(block, is_value, out, owner, chain):
        chain = chain + [block.path]
        if (not is_value and forward_attribute_path(block.path)
                and 'sh:nodeKind' not in block.parameters):
            out.append((block, owner, chain))
        for child in block.children:
            gather(child, child.path in VALUE_PATHS, out, owner, chain)

    added = 0
    while True:
        index = TurtleIndex(text)
        targets = []
        for block in index.blocks:
            for group in property_blocks(text, block):
                gather(group, False, targets, block.raw_subject, [])
        if not targets:
            break
        # Rightmost first: an insertion shifts every offset after it.
        target, owner, chain = max(targets, key=lambda t: t[0].start)
        text = add_parameter(text, target, 'sh:nodeKind', IMPLIED_NODE_KIND)
        if where is not None:
            where.insert(0, f'{owner} › {" / ".join(chain)}')
        added += 1
        if added > 500:
            raise RuntimeError('node-kind completion did not converge')
    return text, added


class EmissionMode(Enum):
    COMPILE = 'compile'
    BROKER = 'broker'


# Keys of an entity or an attribute instance that are not attributes.
NOT_ATTRIBUTES = {'id', '@id', 'type', '@type', '@context', 'value', 'object', 'valueList',
                  'objectList', 'json', 'languageMap', 'vocab', 'observedAt', 'datasetId',
                  'unitCode', 'createdAt', 'modifiedAt', 'instanceId'}


class AmbiguousInstances(ValueError):
    """Instances of one (attribute, datasetId) tied for the latest: the broker
    keeps one, and nothing says which."""

    def __init__(self, ties):
        self.ties = ties
        super().__init__(
            'several instances tie for the latest of their datasetId -- the same '
            'observedAt, or none -- so there is no one instance to send: '
            + '; '.join(ties) + '. Give each its own time or its own datasetId.')


def collapse_for_broker(entities):
    """Keep one instance per (attribute, datasetId): the one validation reads.

    That is the platform's rule (ngsild/timestamps.py): the latest point in
    time, an instance without observedAt -- or with one that does not parse --
    counting as now. Sub-attributes are collapsed the same way. Instances tied
    for the latest (the same time, or several unstamped) are one update written
    twice: validation counts them, the broker would keep one of them -- so they
    are refused (AmbiguousInstances), never guessed. Returns how many
    instances were dropped.
    """
    from ..ngsild.timestamps import key as moment

    collapsed, ties = 0, []

    def walk(holder, owner, trail):
        nonlocal collapsed
        for name, value in list(holder.items()):
            if name in NOT_ATTRIBUTES or not isinstance(value, (list, dict)):
                continue
            instances = value if isinstance(value, list) else [value]
            if isinstance(value, list):
                groups = {}
                for instance in instances:
                    dataset = instance.get('datasetId', '@none') \
                        if isinstance(instance, dict) else '@none'
                    groups.setdefault(str(dataset), []).append(instance)
                kept = []
                for dataset, members in groups.items():
                    stamped = [m for m in members if isinstance(m, dict)]
                    if len(stamped) > 1:
                        latest = max(moment(m) for m in stamped)
                        winners = [m for m in stamped if moment(m) == latest]
                        if len(winners) > 1:
                            ties.append(f'{owner} {"/".join(trail + [name])} '
                                        f'({"default" if dataset == "@none" else dataset})')
                        collapsed += len(members) - 1
                        members = [winners[-1]]
                    kept.extend(members)
                holder[name] = kept
                instances = kept
            for instance in instances:
                if isinstance(instance, dict):
                    walk(instance, owner, trail + [name])

    for entity in entities:
        if isinstance(entity, dict):
            walk(entity, str(entity.get('id') or entity.get('@id') or ''), [])
    if ties:
        raise AmbiguousInstances(ties)
    return collapsed


def export(package, out_dir, mode=EmissionMode.COMPILE, target_context=None):
    """Write knowledge.ttl, shacl.ttl and a model instance into out_dir.

    Returns a dict of what was written. The Turtle artifacts are copied from
    source text rather than reserialised, so they are byte-identical to the
    package and stable across runs.

    `target_context` points the exported model somewhere: by default at the
    package's PUBLISHED context, because the broker and the compiler resolve it
    themselves and a file naming a local path is useless to them. Locally the
    same file resolves against the local copy -- that is the whole point of
    declaring both.
    """
    mode = mode if isinstance(mode, EmissionMode) else EmissionMode(mode)
    written = {}

    # The model first: a broker export that cannot be made (AmbiguousInstances)
    # must write nothing at all, not half an output.
    entities = []
    for source_path in package.files('model'):
        with open(source_path, encoding='utf-8') as handle:
            document = json.load(handle)
        entities.extend(document if isinstance(document, list) else [document])
    if mode is EmissionMode.BROKER:
        written['collapsed'] = collapse_for_broker(entities)
    os.makedirs(out_dir, exist_ok=True)

    # A role may be several files. They are concatenated into the single
    # artifact the target expects -- shacl2flink reads one shapes file -- rather
    # than exported as a directory: how a package is ORGANISED is the author's
    # business, and what a compiler is handed is the target's.
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl')):
        destination = os.path.join(out_dir, name)
        parts = []
        for source_path in package.files(role):
            with open(source_path, encoding='utf-8') as source:
                parts.append(source.read())
        text = '\n'.join(parts) if len(parts) > 1 else parts[0]
        if role == 'shapes':
            places = []
            text, added = complete_node_kinds(text, places)
            if added:
                # Every shape it changed, by name: the export adds a SHACL
                # constraint, so it says where.
                written['node_kinds_added'] = added
                written['node_kinds_where'] = places
        with open(destination, 'w', encoding='utf-8') as handle:
            handle.write(text)
        written[role] = destination
        if len(parts) > 1:
            written.setdefault('merged', {})[role] = len(parts)

    from ..package.context import context_config

    config = context_config(package.path)
    context_value = target_context if target_context is not None else config.published
    if context_value:
        retargeted = 0
        for entity in entities:
            if isinstance(entity, dict) and entity.get('@context') != context_value:
                entity['@context'] = context_value
                retargeted += 1
        written['context_url'] = context_value
        written['retargeted'] = retargeted

    model_path = os.path.join(out_dir, 'model-instance.jsonld')
    with open(model_path, 'w', encoding='utf-8') as handle:
        # sort_keys and fixed indent: the JSON must not reorder between runs,
        # for the same reason the Turtle must not.
        json.dump(entities, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write('\n')
    written['model'] = model_path

    # The compiler needs a LOCAL context; the package's model may reference a
    # remote one, which is not something a build should depend on.
    context = os.path.join(package.path, 'context.jsonld')
    if os.path.exists(context):
        shutil.copyfile(context, os.path.join(out_dir, 'context.jsonld'))
        written['context'] = os.path.join(out_dir, 'context.jsonld')
    return written
