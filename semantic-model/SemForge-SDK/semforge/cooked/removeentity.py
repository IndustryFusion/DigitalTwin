#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Remove an entity from the file it is written in -- and say first what that touches.

A row of the Entities & Test Cases view, or a card, stands for one document of one
file. An id does not say which: a file may define it twice. So both carry the
document's place and the digest of the file they were read from, and a removal
only acts on that file as it was: anything else is refused, not guessed.

Remove entity: what refers to the entity is reported, never changed. A
relationship that points at nothing, or an assert whose entity is gone, is
evidence, and the author's.

Remove with subtree (`remove_subtree`) is the one exception: what it cuts out is
meant to leave no trace in the file, so the relationship objects that name a
removed entity go with it -- after the author was told which.
"""

import hashlib
import json
import os
from collections import OrderedDict

from ..errors import PackageError


def digest_of(text):
    """What tells one content of a file from another."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def _read(path):
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    try:
        document = json.loads(text, object_pairs_hook=OrderedDict)
    except ValueError as exc:
        raise PackageError(f'{os.path.basename(path)} is not JSON: {exc}')
    documents = document if isinstance(document, list) else [document]
    if any(isinstance(d, dict) and '@graph' in d for d in documents):
        # The row stands for the whole of it: all its entities would go.
        raise PackageError(f'{os.path.basename(path)} has its entities inside "@graph", which is not read '
                           'here; write them as a list')
    return documents, text


def _write_whole(source, document, text):
    """The file is either what it was or all of the new one. A link stays a
    link: what it leads to is written. `text` is what the file said when the
    change was decided; written over anything else, that would be lost."""
    import shutil
    import tempfile

    from .examples import _write

    target = os.path.realpath(source)
    handle, partial = tempfile.mkstemp(dir=os.path.dirname(target), suffix='.partial')
    os.close(handle)
    try:
        _write(partial, document, text)
        shutil.copymode(target, partial)
        with open(target, encoding='utf-8') as handle:
            if digest_of(handle.read()) != digest_of(text):
                raise PackageError(f'{os.path.basename(source)} changed while it was written; nothing is removed')
        os.replace(partial, target)
    finally:
        if os.path.exists(partial):
            os.remove(partial)


def _case_files(package, example):
    """A case's own file and the files it includes, found as `compose` finds them."""
    from ..expect.store import examples_root
    from .examples import _included_files

    # Its own file as `compose` finds it, under examples/ first; the includes likewise.
    own = [os.path.abspath(os.path.join(base, example.path)) for base in (examples_root(package.path), package.path)]
    return [p for p in own if os.path.exists(p)][:1] + _included_files(package, example)


def _allowed(package, source):
    """([the cases that use the file], is it a file of the main model). Refused:
    a file that is neither, or is not in the package."""
    from ..expect.store import load_expectations

    real, root, uses, named = os.path.realpath(source), os.path.abspath(package.path), [], []
    for example in load_expectations(package.path).examples:
        same = [p for p in _case_files(package, example) if os.path.realpath(p) == real]
        if same:
            uses.append(example)
            named += same
    models = [os.path.abspath(p) for p in package.files('model')
              if p.endswith(('.jsonld', '.json')) and os.path.realpath(p) == real]
    # As the package names it: the link to a shared file may be inside it.
    if not any(_inside(root, path) for path in named + models):
        raise PackageError(f'{os.path.basename(source)} is no model file, test case or included file of this package')
    return uses, bool(models)


def _inside(root, path):
    """Is `path` in the folder `root`? A path on another drive is not."""
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:
        return False


def _name(document):
    """A document's id as a row shows it."""
    return str(document.get('id') or document.get('@id') or '(no id)')


class _Names:
    """The IRI a document's id is in the graph, however it is written."""

    def __init__(self, path):
        self.path, self.contexts = path, {}

    def iri(self, document):
        """'' for a document without an id."""
        return self.resolve(document, str(document.get('id') or document.get('@id') or ''))

    def resolve(self, document, name):
        """The IRI `name` -- an id, or a relationship's object -- is, read
        with `document`'s context; '' for no name."""
        from rdflib.plugins.shared.jsonld.context import Context

        from ..rdfio.relative import BASE, absolute_contexts

        value = document.get('@context')
        key = json.dumps(value, sort_keys=True)
        if key not in self.contexts:
            value = absolute_contexts({'@context': value}, self.path)['@context']
            self.contexts[key] = Context(value, base=BASE)
        return (self.contexts[key].resolve(name) or name) if name else ''


def _own_contexts(package, documents):
    """`documents` with the package's published context as the package has it,
    as validation reads them; copies, so what is written keeps the URL."""
    from ..package.context import context_config, local_context_value

    config = context_config(package.path)
    inline = local_context_value(package.path, config) if config.declared else None
    if inline is None:
        return documents

    def own(value):
        if value == config.published:
            return inline
        if isinstance(value, list):
            return [inline if item == config.published else item for item in value]
        return value
    return [dict(d, **{'@context': own(d['@context'])}) if isinstance(d, dict) and '@context' in d else d
            for d in documents]


def _pointers():
    from rdflib import RDF, URIRef

    from ..ngsild.kinds import NGSILD
    return (URIRef(NGSILD + 'hasObject'), URIRef(NGSILD + 'hasObjectList'), RDF.first, RDF.rest)


POINTERS = _pointers()


def _left(package, source, documents, at):
    """(what the entity at `at` is called in results, those still pointing at
    it when it is gone, does another document of the file define it). Of the
    documents as they were read, as a graph, so an id is found however it is
    spelled."""
    from rdflib import BNode, Graph, URIRef

    from ..package.loader import hoist_context
    from ..rdfio.relative import BASE, as_written, for_rdflib

    documents = _own_contexts(package, documents)
    names = _Names(source)
    iri = names.iri(documents[at])
    if not iri:
        return '', [], False                       # nothing can name it
    rest = [d for n, d in enumerate(documents) if n != at]
    # Written inside another document it is no definition of its own.
    remains = any(isinstance(d, dict) and names.iri(d) == iri for d in rest)
    graph = Graph().parse(data=json.dumps(hoist_context(for_rdflib(rest, source))), format='json-ld', base=BASE)
    target, pointing = URIRef(iri), set()
    # What holds it as a relationship's object -- one of a list's, too -- and
    # then, up through attributes and sub-attributes, the entity that has it.
    # A datasetId, a type or a Property's value that names it is no reference.
    holders, pending = set(), [target]
    while pending:
        node = pending.pop()
        for predicate in POINTERS:
            for subject in graph.subjects(predicate, node):
                if subject not in holders:
                    holders.add(subject)
                    pending.append(subject)
    seen, pending = set(holders), list(holders)
    while pending:
        node = pending.pop()
        if not isinstance(node, BNode):
            if node != target:
                pointing.add(str(node))
            continue
        for subject in graph.subjects(None, node):
            if subject not in seen:
                seen.add(subject)
                pending.append(subject)
    spelled = {}
    if pointing:
        spelled = {names.iri(d): _name(d) for d in rest if isinstance(d, dict)}
    return as_written(iri), sorted(spelled.get(i) or as_written(i) for i in pointing), remains


def remove_entity(package, entity_id, file=None, position=None, digest=None, check=False, plan=None):
    """Remove one entity's document from the file it is written in.

    `position` and `digest` are of the row or card: its place in the file, and
    the content the file had. Without a position the id has to be there once.
    `check` only asks; its `plan`, handed back, makes the removal refuse when
    what was said is not so any more.

    Returns {'file', 'real', 'removed', 'model', 'empty', 'remains', 'pointing',
    'asserts', 'cases', 'plan', 'unread'}: the file, and behind links; is it of
    the main model; is it left without an entity; does it define the entity
    elsewhere still; the ids in it that point at the entity; the cases that
    assert something on it, and all that use the file; and, when the file could
    not be read as a graph (its context is not to be had), why.
    """
    from .examples import _target_file

    source = os.path.abspath(_target_file(package, file))
    uses, model = _allowed(package, source)
    documents, text = _read(source)
    name = os.path.basename(source)
    if digest and digest != digest_of(text):
        raise PackageError(f'{name} has changed since it was read; nothing is removed')
    found = [n for n, d in enumerate(documents) if isinstance(d, dict) and _name(d) == entity_id]
    if not found:
        raise PackageError(f'no entity {entity_id} in {name} any more')
    if position is None and len(found) > 1:
        raise PackageError(f'{entity_id} is written {len(found)} times in {name}: remove it from its row or card')
    at = found[0] if position is None else int(position)
    if at not in found:
        raise PackageError(f'{entity_id} is not where it was in {name}; nothing is removed')
    unread = ''
    try:
        said, pointing, remains = _left(package, source, documents, at)
    except Exception as exc:                       # noqa: BLE001 -- what it says is what is missing then
        said, pointing, remains, unread = entity_id, [], len(found) > 1, str(exc) or type(exc).__name__
    asserts = [e.path for e in uses if any(a.get('resource') and a['resource'] in (said, entity_id)
                                           for a in e.asserts)]
    cases = [e.path for e in uses]
    # What the question said follows from these: the file, and the asserts of
    # the cases that use it. Not from what was read of it as a graph, which
    # one run may build and another not -- that is no change of the file.
    claims = [[e.path, str(a.get('resource', '')), str(a.get('constraint', ''))] for e in uses for a in e.asserts]
    seen = digest_of(json.dumps([text, at, cases, claims]))
    if plan and plan != seen:
        raise PackageError(f'{name} was changed meanwhile, or a case that uses it; nothing is removed')
    if not check:
        _write_whole(source, documents[:at] + documents[at + 1:], text)
    return {'file': source, 'real': os.path.realpath(source), 'removed': entity_id, 'model': model,
            'empty': not any(isinstance(d, dict) for n, d in enumerate(documents) if n != at),
            'remains': remains, 'pointing': pointing, 'asserts': asserts, 'cases': cases,
            'plan': seen, 'unread': unread}


def remove_subtree(package, entity_id, file=None, digest=None, check=False, plan=None):
    """Remove an entity with its subtree from the file it is written in: the
    entities Copy with subtree copies (`copy_entities`), its children, theirs,
    and so on.

    Unlike Remove entity, what is cut out takes its references with it: every
    relationship object left in the file that is a removed entity -- the
    parent's reference to the root above all -- goes, only that object, an
    instance left with none goes, and an attribute left with no instance too.
    An object counts by its IRI, however it is written (whole, with a prefix
    of the context, relative, the relationship's type and keys compacted or
    expanded), in sub-attributes, among several objects and in object lists.
    An IRI a document left in the file still defines is no removed entity.

    Only that file is written. A member of the subtree written in another file
    (one the case includes, the main model) stays there: `elsewhere`. A child
    that an entity outside the subtree points at stays, with what is reached
    only through it: `shared`. A member written more than once in the file is
    refused: which of them is meant cannot be told. `digest`, `check` and
    `plan` are as for `remove_entity`.

    Returns {'file', 'real', 'removed', 'elsewhere', 'shared', 'assumed',
    'missing', 'dropped', 'pointing', 'model', 'empty', 'asserts', 'cases',
    'plan', 'unread'}: `dropped` the references taken out ({'entity', 'path',
    'datasetId', 'object'}, `path` the attribute and sub-attribute keys),
    `pointing` the entities they are taken from; `unread`, when a context
    could not be had, why -- ids under it are compared as written.
    """
    from .examples import _target_file, copy_entities

    source = os.path.abspath(_target_file(package, file))
    uses, model = _allowed(package, source)
    documents, text = _read(source)
    name = os.path.basename(source)
    if digest and digest != digest_of(text):
        raise PackageError(f'{name} has changed since it was read; nothing is removed')
    entities = [d for d in documents if isinstance(d, dict)]
    written = {}
    for document in entities:
        written[_name(document)] = written.get(_name(document), 0) + 1
    if entity_id not in written:
        raise PackageError(f'no entity {entity_id} in {name} any more')
    tree = copy_entities(package, entity_id, file=source, subtree=True)
    members = [n for n in tree['copied'] if n in written]
    elsewhere = [n for n in tree['copied'] if n not in written]
    twice = [n for n in members if written[n] > 1]
    if twice:
        raise PackageError(f'{twice[0]} is written {written[twice[0]]} times in {name}: remove it with '
                           'Remove entity… from its row')
    iri_of = _Resolver(package, source)
    by_iri = {}                                    # IRI -> the names its documents have here
    for document in entities:
        by_iri.setdefault(iri_of(document, _name(document)), set()).add(_name(document))
    members, shared = _held_back(entities, entity_id, members, iri_of, by_iri)
    gone = set(members)
    kept = [d for d in documents if not (isinstance(d, dict) and _name(d) in gone)]
    still = {iri_of(d, _name(d)) for d in kept if isinstance(d, dict)}
    gone_iris = {iri for iri, spelled in by_iri.items() if spelled & gone} - still
    dropped = []
    for document in kept:
        if isinstance(document, dict):
            found = _drop_references(document, lambda value, d=document: iri_of(d, value) in gone_iris)
            dropped += [dict(entity=_name(document), **d) for d in found]
    asserts = [e.path for e in uses
               if any(a.get('resource') and (a['resource'] in gone or a['resource'] in gone_iris)
                      for a in e.asserts)]
    cases = [e.path for e in uses]
    claims = [[e.path, str(a.get('resource', '')), str(a.get('constraint', ''))] for e in uses for a in e.asserts]
    seen = digest_of(json.dumps([text, members, cases, claims]))
    if plan and plan != seen:
        raise PackageError(f'{name} was changed meanwhile, or a case that uses it; nothing is removed')
    if not check:
        _write_whole(source, kept, text)
    return {'file': source, 'real': os.path.realpath(source), 'removed': members, 'elsewhere': elsewhere,
            'shared': shared, 'assumed': [n for n in tree['assumed'] if n in gone],
            'missing': tree['missing'], 'dropped': dropped,
            'pointing': sorted({d['entity'] for d in dropped}), 'model': model,
            'empty': not any(isinstance(d, dict) for d in kept), 'asserts': asserts, 'cases': cases,
            'plan': seen, 'unread': iri_of.unread}


class _Resolver:
    """iri_of(document, value): `value` -- an id, or a relationship's object --
    as an IRI, read with the document's context as validation reads it. Built
    once per distinct context; a context that cannot be had is remembered, its
    ids are compared as written, and `unread` says why."""

    def __init__(self, package, source):
        self.package, self.names, self.known, self.unread = package, _Names(source), {}, ''

    def __call__(self, document, value):
        if not value:
            return value
        key = json.dumps(document.get('@context'), sort_keys=True)
        if key not in self.known:
            holder = {'@context': document['@context']} if '@context' in document else {}
            try:
                holder = _own_contexts(self.package, [holder])[0]
                self.names.resolve(holder, 'x')        # builds the context now, or fails now
                self.known[key] = holder
            except Exception as exc:                   # noqa: BLE001 -- compared as written then
                self.known[key] = None
                self.unread = self.unread or str(exc) or type(exc).__name__
        holder = self.known[key]
        return value if holder is None else self.names.resolve(holder, value)


NGSILD_CORE = 'https://uri.etsi.org/ngsi-ld/'
RELATIONSHIP = {'Relationship', 'ngsi-ld:Relationship', NGSILD_CORE + 'Relationship'}
OBJECT_KEYS = ('object', 'ngsi-ld:hasObject', NGSILD_CORE + 'hasObject')
LIST_KEYS = ('objectList', 'ngsi-ld:hasObjectList', NGSILD_CORE + 'hasObjectList')
SKIP = ('@context', 'id', '@id', 'type', '@type')


def _is_relationship(item):
    kind = item.get('type', item.get('@type'))
    return any(k in RELATIONSHIP for k in (kind if isinstance(kind, list) else [kind]) if isinstance(k, str))


def _entry(entry):
    """The id one entry of an object or object list names, or None."""
    while isinstance(entry, dict):
        entry = next((entry[k] for k in ('@id',) + OBJECT_KEYS if k in entry), None)
        if isinstance(entry, list):
            entry = entry[0] if len(entry) == 1 else None
    return entry if isinstance(entry, str) else None


def _objects(item):
    """The objects a Relationship instance names: its object (one or several,
    compacted or expanded) and the entries of its object list."""
    found = []
    for key in OBJECT_KEYS + LIST_KEYS:
        value = item.get(key)
        for entry in value if isinstance(value, list) else [value]:
            named = _entry(entry)
            if named:
                found.append(named)
    return found


def _pointers_of(node):
    """Every object a document's relationships name, sub-attributes included."""
    found = []
    for key, value in (node.items() if isinstance(node, dict) else []):
        if key in SKIP:
            continue
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict):
                if _is_relationship(item):
                    found += _objects(item)
                found += _pointers_of(item)
    return found


def _held_back(entities, root, members, iri_of, by_iri):
    """(members to remove, members kept): a member other than the root that an
    entity outside the subtree points at stays, and so does what is reached
    from the root only through one that stays."""
    pointed, children = {}, {}
    for document in entities:
        for value in _pointers_of(document):
            for target in by_iri.get(iri_of(document, value), ()):
                pointed.setdefault(target, set()).add(_name(document))
                children.setdefault(_name(document), set()).add(target)
    held_back = []
    while True:
        inside = set(members)
        held = [n for n in members if n != root and pointed.get(n, set()) - inside]
        if not held:
            return members, held_back
        reach, todo = {root}, [root]
        while todo:
            for target in children.get(todo.pop(), ()):
                if target in inside and target not in held and target not in reach:
                    reach.add(target)
                    todo.append(target)
        held_back += held + [n for n in members if n not in reach and n not in held]
        members = [n for n in members if n in reach]


def _drop_references(node, removed, trail=()):
    """Take every object `removed(value)` says is a removed entity out of the
    relationship instances of `node` (sub-attributes too); an instance left
    with no object goes, and an attribute left with no instance. Returns what
    was taken: [{'path', 'datasetId', 'object'}], `path` the keys down to it."""
    taken = []
    for key in list(node.keys()) if isinstance(node, dict) else []:
        if key in SKIP:
            continue
        value = node[key]
        items = value if isinstance(value, list) else [value]
        keep = []
        for item in items:
            if isinstance(item, dict) and _is_relationship(item):
                gone = [o for o in _objects(item) if removed(o)]
                if gone:
                    taken += [{'path': list(trail + (key,)), 'datasetId': item.get('datasetId') or '',
                               'object': o} for o in gone]
                    if not _thin(item, removed):
                        continue                   # no object left: the instance goes
            if isinstance(item, dict):
                taken += _drop_references(item, removed, trail + (key,))
            keep.append(item)
        if keep == items:
            continue
        if not keep:
            del node[key]
        else:
            node[key] = keep if isinstance(value, list) else keep[0]
    return taken


def _thin(item, removed):
    """Take the removed objects out of one relationship instance; does an
    object remain?"""
    left = False
    for key in OBJECT_KEYS + LIST_KEYS:
        if key not in item:
            continue
        value = item[key]
        rest = [e for e in (value if isinstance(value, list) else [value])
                if not (_entry(e) and removed(_entry(e)))]
        if not rest:
            del item[key]
        else:
            item[key] = rest if isinstance(value, list) else rest[0]
            left = True
    return left
