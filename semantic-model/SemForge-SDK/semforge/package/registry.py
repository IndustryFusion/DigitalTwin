"""Resolving declared dependencies, reproducibly (architecture.md section 6.2).

Today `make ontology2kms` fetches an ontology tree with `wget -r` and merges
whatever it finds. Nothing records which version a KMS was built from, so a KMS
cannot be reproduced from its own contents -- and a semantic diff across
releases is meaningless if the two sides were assembled from whatever the URL
served that day.

So a dependency is declared with a version AND a content hash, every fetch is
verified against the hash, and assembly is deterministic. A hash mismatch is a
hard failure: it means the thing you declared and the thing you got are not the
same, which is precisely what a supply chain check exists to notice.

Sources may be local paths or http(s) URLs. Local paths are resolved relative to
the package, which keeps the whole mechanism testable without a network.
"""

import hashlib
import os
from dataclasses import dataclass, field

from ..errors import PackageError

CACHE = os.path.join('.semforge', 'cache', 'deps')


@dataclass
class Dependency:
    name: str
    source: str
    version: str = ''
    sha256: str = ''

    @property
    def is_remote(self):
        return self.source.startswith(('http://', 'https://'))


@dataclass
class Resolution:
    dependencies: list = field(default_factory=list)
    paths: dict = field(default_factory=dict)
    hashes: dict = field(default_factory=dict)
    unpinned: list = field(default_factory=list)


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def _fetch(dependency, package_path):
    if not dependency.is_remote:
        path = dependency.source
        if not os.path.isabs(path):
            path = os.path.join(package_path, path)
        if not os.path.exists(path):
            raise PackageError(
                f'dependency {dependency.name!r}: {path} does not exist')
        with open(path, 'rb') as handle:
            return path, handle.read()

    cache = os.path.join(package_path, CACHE)
    os.makedirs(cache, exist_ok=True)
    cached = os.path.join(cache, hashlib.sha256(
        dependency.source.encode()).hexdigest() + '.ttl')
    if os.path.exists(cached):
        with open(cached, 'rb') as handle:
            return cached, handle.read()

    from urllib.request import urlopen
    with urlopen(dependency.source, timeout=30) as response:   # noqa: S310
        data = response.read()
    with open(cached, 'wb') as handle:
        handle.write(data)
    return cached, data


def resolve(dependencies, package_path, allow_unpinned=True):
    """Fetch every dependency and verify it against its declared hash."""
    resolution = Resolution(dependencies=list(dependencies))
    for dependency in dependencies:
        path, data = _fetch(dependency, package_path)
        actual = digest(data)
        if dependency.sha256:
            if actual != dependency.sha256:
                raise PackageError(
                    f'dependency {dependency.name!r} does not match its declared '
                    f'hash.\n  declared {dependency.sha256}\n  actual   {actual}\n'
                    f'  source   {dependency.source}\n'
                    f'The declared artifact and the fetched one are not the same.')
        else:
            resolution.unpinned.append(dependency.name)
            if not allow_unpinned:
                raise PackageError(
                    f'dependency {dependency.name!r} declares no sha256; an '
                    f'unpinned dependency makes the package unreproducible')
        resolution.paths[dependency.name] = path
        resolution.hashes[dependency.name] = actual
    return resolution


def assemble_knowledge(resolution, out_path):
    """Concatenate resolved modules into one knowledge file, deterministically.

    Source text, in declared order -- not a reserialisation. Same reason export
    does not reserialise: byte-stability is what makes a diff mean something,
    and rdflib guarantees neither ordering nor prefix assignment.
    """
    parts = []
    for dependency in resolution.dependencies:
        path = resolution.paths[dependency.name]
        with open(path, encoding='utf-8') as handle:
            parts.append(
                f'# --- {dependency.name} '
                f'{dependency.version or "(unversioned)"} '
                f'{resolution.hashes[dependency.name]}\n' + handle.read())
    text = '\n'.join(parts)
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as handle:
            handle.write(text)
    return text


def dependencies_from_config(config):
    """Read the `dependencies:` list of a semforge.yaml mapping."""
    found = []
    for entry in (config or {}).get('dependencies') or []:
        if 'source' not in entry or 'name' not in entry:
            raise PackageError(
                'each dependency needs at least a name and a source')
        found.append(Dependency(
            name=entry['name'], source=entry['source'],
            version=str(entry.get('version', '')),
            sha256=entry.get('sha256', '')))
    return found
