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

Loading is read-only and executes no code from the package.
"""

import os
from dataclasses import dataclass, field

from rdflib import Graph

from ..errors import PackageError
from .context import context_config, model_context, resolve_model_document

DEFAULTS = {
    'knowledge': ['knowledge.ttl'],
    'shapes': ['shacl.ttl'],
    'model': ['model-instance.jsonld', 'model.jsonld'],
}

# A directory standing in for the file of the same role, and what counts as one
# of its documents.
FOLDERS = {
    'knowledge': (['knowledge'], ('.ttl',)),
    'shapes': (['shacl', 'shapes'], ('.ttl',)),
    'model': (['model-instance', 'model'], ('.jsonld', '.json')),
}


@dataclass
class Package:
    path: str
    context_url: str = ''      # what the model names on disk
    context_resolved_locally: bool = False
    knowledge: Graph = field(default_factory=Graph)
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

    def index(self, role):
        """A locator over every Turtle file of a role."""
        from ..rdfio import PackageIndex

        key = f'_index_{role}'
        if not hasattr(self, key):
            setattr(self, key, PackageIndex(self.files(role)))
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


def _documents_for(path, role, names):
    """Every file of a role: the single file, or the directory's contents."""
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


def load(path):
    """Load a package directory. Raises PackageError naming what is missing."""
    if not os.path.isdir(path):
        raise PackageError(f'not a package directory: {path}')

    sources = {}
    documents = {}
    missing = []
    for role, names in DEFAULTS.items():
        found = _documents_for(path, role, names)
        if not found:
            folders = FOLDERS.get(role, ([], ()))[0]
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
    for document in documents['knowledge']:
        package.knowledge.parse(document, format='turtle')
    for document in documents['shapes']:
        package.shapes.parse(document, format='turtle')

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
        if swapped:
            package.model.parse(data=_json.dumps(document), format='json-ld')
        else:
            package.model.parse(source, format='json-ld')
    return package
