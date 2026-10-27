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

"""Load a package from disk.

M1 reads the KMS triple layout directly -- knowledge.ttl, shacl.ttl and a
model-instance -- which is what the corpus is and what `semforge export` will
have to reproduce byte-for-byte. The modular layout of architecture.md section
6.1, with semforge.yaml, is read when present and otherwise defaulted from
these names.

**A role may be one file or a directory of them.** `shacl.ttl` or `shacl/`,
`knowledge.ttl` or `knowledge/`, `model-instance.jsonld` or `model-instance/`.
A model outgrows one file long before it outgrows one package -- the kms shapes
are already 400 lines of several vocabularies -- and splitting them should not
mean inventing a second package or a build step that concatenates. The graph is
the union either way; what changes is where an edit lands, so every artifact
keeps its own path and the index knows which file holds which subject.

**The data may be grouped under `model/`.** The scratchpad and the suite are two
kinds of data about the same model, so they sit at the same level:

    model/
    ├── model-instance.jsonld   (or model-instance/, or bare *.jsonld)
    └── examples/

Both layouts are read: `model/` when a package groups them, and the flat
`model-instance.jsonld` + `examples/` the kms already has.

Loading is read-only and executes no code from the package.
"""

import os
import threading
from dataclasses import dataclass, field

from rdflib import Graph

from ..errors import PackageError
from .context import context_config, model_context, resolve_model_document

DEFAULTS = {
    'knowledge': ['knowledge.ttl'],
    'shapes': ['shacl.ttl'],
    # `main` is the name the tree uses for it; `model-instance` is what the kms
    # has. Both are read, so the vocabulary can move without a migration.
    'model': ['main.jsonld', 'model-instance.jsonld', 'model.jsonld'],
}

# A directory standing in for the file of the same role, and what counts as one
# of its documents.
FOLDERS = {
    'knowledge': (['knowledge'], ('.ttl',)),
    'shapes': (['shacl', 'shapes'], ('.ttl',)),
    'model': (['main', 'model-instance'], ('.jsonld', '.json')),
}
# `model/` groups the data: the instance beside the suite. What it holds decides
# whether it is that grouping or simply a directory of instance documents.
MODEL_FOLDER = 'model'
MODEL_SUFFIXES = ('.jsonld', '.json')


_INDEX_LOCK = threading.RLock()


@dataclass
class Package:
    path: str
    context_url: str = ''      # what the model names on disk
    context_resolved_locally: bool = False
    knowledge: Graph = field(default_factory=Graph)
    # The NGSI-LD vocabulary: not the package's, but what every term of the
    # encoding means. Kept apart from `knowledge` so nothing mistakes it for
    # something this package declares, owns, or may write to.
    vocabulary: Graph = field(default_factory=Graph)
    vocabulary_error: str = ''   # why the declared vocabulary did not load
    shapes: Graph = field(default_factory=Graph)
    model: Graph = field(default_factory=Graph)
    sources: dict = field(default_factory=dict)    # role -> primary file
    documents: dict = field(default_factory=dict)  # role -> every file, in order

    def artifact(self, role):
        return self.sources.get(role)

    def files(self, role):
        """Every file of a role, in load order.

        One file or many: the difference belongs here and nowhere else, so a
        caller that reads or exports an artifact iterates and a caller that
        writes asks the index which file holds the subject.
        """
        if self.documents.get(role):
            return list(self.documents[role])
        found = self.sources.get(role)
        return [found] if found else []

    @property
    def examples_dir(self):
        """Where the declared cases live: `model/examples` or `examples`."""
        from ..expect.store import examples_root

        return examples_root(self.path)

    def index(self, role):
        """A locator over every Turtle file of a role.

        Built once, under a lock: the editor warms it in the background while a
        click may already ask for it, and two builds would only double the wait.
        """
        from ..rdfio import PackageIndex

        key = f'_index_{role}'
        if not hasattr(self, key):
            with _INDEX_LOCK:
                if not hasattr(self, key):
                    setattr(self, key, PackageIndex(self.files(role), cache_root=self.path))
        return getattr(self, key)


def _documents_of(directory, suffixes):
    """The artifact files directly inside a role directory, in name order.

    Not recursive: a nested directory under `model-instance/` is somebody's own
    structure, and walking into it would quietly adopt whatever is there --
    including, in this repo, an examples suite.
    """
    found = []
    for name in sorted(os.listdir(directory)):
        if name.startswith('.'):
            continue
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and name.endswith(suffixes):
            found.append(candidate)
    return found


def _model_documents(path):
    """The instance documents, wherever the package keeps them.

    In order: a file at the root, `model-instance/` at the root, then `model/` --
    which may hold the instance as a file, as `model-instance/`, or as bare
    documents beside `examples/`. The last case is why this is not just the
    generic directory rule: `model/examples` is a sibling of the instance, not
    part of it, and a recursive scan would swallow the whole suite.
    """
    for name in DEFAULTS['model']:
        candidate = os.path.join(path, name)
        if os.path.isfile(candidate):
            return [candidate]

    for name in ('main', 'model-instance'):
        instance_dir = os.path.join(path, name)
        if not os.path.isdir(instance_dir):
            continue
        found = _documents_of(instance_dir, MODEL_SUFFIXES)
        if found:
            return found
        raise PackageError(
            f'{instance_dir} is the model directory but holds no '
            f'{" or ".join(MODEL_SUFFIXES)} file')

    umbrella = os.path.join(path, MODEL_FOLDER)
    if not os.path.isdir(umbrella):
        return []

    for name in DEFAULTS['model'] + ['instance.jsonld']:
        candidate = os.path.join(umbrella, name)
        if os.path.isfile(candidate):
            return [candidate]
    for name in ('main', 'model-instance', 'instance'):
        candidate = os.path.join(umbrella, name)
        if os.path.isdir(candidate):
            found = _documents_of(candidate, MODEL_SUFFIXES)
            if found:
                return found
    found = _documents_of(umbrella, MODEL_SUFFIXES)
    if found:
        return found
    raise PackageError(
        f'{umbrella} holds no instance documents. It should contain '
        f'main.jsonld (or main/, or model-instance.jsonld, or .jsonld files) '
        f'beside examples/.')


def _documents_for(path, role, names):
    """Every file of a role: the single file, or the directory's contents."""
    if role == 'model':
        return _model_documents(path)

    for name in names:
        candidate = os.path.join(path, name)
        if os.path.isfile(candidate):
            return [candidate]

    folders, suffixes = FOLDERS.get(role, ([], ()))
    for name in folders:
        candidate = os.path.join(path, name)
        if os.path.isdir(candidate):
            found = _documents_of(candidate, suffixes)
            if not found:
                raise PackageError(
                    f'{candidate} is the {role} directory but holds no '
                    f'{" or ".join(suffixes)} file')
            return found
    return []


def reload_keeping_shapes(package):
    """`package` read again after a write that left its knowledge and shapes
    alone -- a test case is files under examples/ -- with their graphs, and
    what is kept with them (rdfio/frozen.py), reused: on the OPC UA pumps a
    plain reload is 7.5 s, and a validation on new graphs starts cold."""
    return load(package.path, reuse={role: (package.files(role), getattr(package, role))
                                     for role in ('knowledge', 'shapes')})


def load(path, reuse=None):
    """Load a package directory. Raises PackageError naming what is missing.

    `reuse` -- {role: (documents, graph)} from an earlier load -- takes that
    role's graph as it is when the role is made of the same documents and the
    caller knows none of them changed (editor/incremental.py): the OPC UA pump
    knowledge is 217,582 triples that an edit to a shape leaves alone. The
    graph is shared, so nothing may write to it: it is frozen (rdfio/frozen.py).
    """
    if not os.path.isdir(path):
        raise PackageError(f'not a package directory: {path}')

    sources = {}
    documents = {}
    missing = []
    for role, names in DEFAULTS.items():
        found = _documents_for(path, role, names)
        if not found:
            folders = list(FOLDERS.get(role, ([], ()))[0])
            if role == 'model':
                folders.append('model (holding the instance beside examples/)')
            missing.append(
                f'{role} (looked for {", ".join(names)}, or a directory named '
                f'{" or ".join(folders)})')
        else:
            documents[role] = found
            sources[role] = found[0]
    if missing:
        raise PackageError(
            f'{path} is missing:\n' + '\n'.join(f'  - {m}' for m in missing))

    package = Package(path=path, sources=sources, documents=documents)
    from ..ngsild.vocabulary import for_package

    try:
        package.vocabulary = for_package(path)
    except Exception as exc:                       # noqa: BLE001
        # The package still loads: a vocabulary that is offline, missing or
        # fails its hash is reported (ngsild-unavailable), not fatal.
        package.vocabulary_error = str(exc).strip() or type(exc).__name__
    # Parsed once per content, then read back from .semforge/cache/graphs
    # (package/graphcache.py): the same triples and prefixes, in half the time.
    from .graphcache import parse_turtle
    for role in ('knowledge', 'shapes'):
        kept = (reuse or {}).get(role)
        if kept is not None and list(kept[0]) == list(documents[role]):
            setattr(package, role, kept[1])
            continue
        for document in documents[role]:
            parse_turtle(getattr(package, role), document, path)

    # The model names the PUBLISHED context on disk; loading answers it from the
    # local copy. Editing the file to point at a local path would make the
    # package unusable to everyone who resolves the url themselves, and fetching
    # the url would make every load depend on the network and on whatever it
    # serves today.
    import json as _json

    config = context_config(path)
    package.context_url = str(model_context(sources['model']) or '')
    for source in documents['model']:
        document, swapped = resolve_model_document(path, source, config)
        package.context_resolved_locally = \
            package.context_resolved_locally or swapped
        # One base for a relative id, whatever the process's directory
        # (rdfio/relative.py).
        from ..rdfio.relative import BASE, absolute_contexts
        if not swapped:
            with open(source, encoding='utf-8') as handle:
                document = _json.load(handle)
        package.model.parse(data=_json.dumps(absolute_contexts(document, source)),
                            format='json-ld', base=BASE)
    # One version of its files each: read-only from here, and what is derived
    # from one is kept with it (rdfio/frozen.py).
    from ..rdfio.frozen import freeze
    for role in ('knowledge', 'vocabulary', 'shapes', 'model'):
        freeze(getattr(package, role))
    return package
