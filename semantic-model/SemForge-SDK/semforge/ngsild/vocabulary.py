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

"""The NGSI-LD vocabulary, as a graph: declared by the package, not chosen by the SDK.

Every package written against this SDK uses these terms -- `ngsild:Property`,
`ngsild:hasValue`, `ngsild:observedAt` -- and the rule this project applies to
everything else, *declared before used*, applies to its own encoding too. So
the terms come from an ontology the package names, like any other knowledge it
depends on, not from a copy inside the SDK:

    ngsild:
      source: ../ontology/ngsild.ttl       # a local file, relative to the package

    ngsild:
      source: https://industryfusion.github.io/contexts/staging/ontology/v0/ngsild.ttl
      sha256: sha256:...                   # a remote one, pinned

A local source is how a repo works on the vocabulary before it is published; a
remote one is the shared, official version. Moving from one to the other is
editing `source` (and pinning it). The short form `ngsild: <path or url>` is
read too.

A package that declares nothing gets the DEFAULT: the official url, or what
SEMFORGE_NGSILD names instead -- a path or a url, so a machine or a CI job can
point every undeclared package at one copy (the test suite points it at the
repo's local file and never reaches the network). `semforge init` writes the
default into the new package, pinned.

A remote source is fetched through the dependency machinery: cached in the
package, verified against its sha256 when it has one. While a package's tests
run (package/offline.py) the official url is read from a pinned copy the SDK
ships instead -- the package still names it, the SDK only answers the url --
and any other remote source is fetched only with --allow-network.
"""

import os
from dataclasses import dataclass

from rdflib import Graph

OFFICIAL = ('https://industryfusion.github.io/contexts/staging/ontology/v0/'
            'ngsild.ttl')
ENVIRONMENT = 'SEMFORGE_NGSILD'

_cache = {}


@dataclass(frozen=True)
class Source:
    """Where a package's NGSI-LD vocabulary comes from."""
    source: str
    sha256: str = ''
    version: str = ''
    declared: bool = True      # False: the default, the package names none

    @property
    def is_remote(self):
        return self.source.startswith(('http://', 'https://'))


def default_source():
    """What an undeclared package uses: SEMFORGE_NGSILD, else the official url.

    While a package's tests run, the official url: their result must not
    depend on this machine's environment.
    """
    from ..package.offline import active

    if active() is not None:
        return OFFICIAL
    return os.environ.get(ENVIRONMENT, '').strip() or OFFICIAL


def declared_source(package_path):
    """The `ngsild:` of kms.yaml as a Source, or None when there is none."""
    from ..package.config import read

    declared = read(package_path).get('ngsild')
    if isinstance(declared, dict):
        if not declared.get('source'):
            return None
        return Source(source=str(declared['source']),
                      sha256=str(declared.get('sha256') or ''),
                      version=str(declared.get('version') or ''))
    if declared:
        return Source(source=str(declared))
    return None


def source_for(package_path):
    """The declared source, or the default one."""
    return declared_source(package_path) or Source(
        source=default_source(), declared=False)


def _resolved(source, package_path):
    from ..package.registry import Dependency, resolve

    return resolve([Dependency(name='ngsild', source=source.source,
                               version=source.version, sha256=source.sha256)],
                   package_path)


def locate(source, package_path):
    """A local file the source names: relative paths are the package's."""
    if source.is_remote:
        return _resolved(source, package_path).paths['ngsild']
    where = os.path.expanduser(source.source)
    if not os.path.isabs(where):
        where = os.path.join(package_path, where)
    if not os.path.isfile(where):
        from ..errors import PackageError
        raise PackageError(f'the NGSI-LD vocabulary {source.source} does not exist '
                           f'(looked for {os.path.normpath(where)})')
    return where


def graph(where):
    """A vocabulary file, parsed once per path."""
    if where not in _cache:
        parsed = Graph()
        parsed.parse(where, format='turtle')
        _cache[where] = parsed
    return _cache[where]


def for_package(package_path):
    """The vocabulary this package uses: what it declares, or the default."""
    from ..package.offline import active

    source = source_for(package_path)
    if active() is None:
        return graph(locate(source, package_path))
    # A test run: the bytes that were verified are the bytes that are parsed,
    # and a local file is one inside the package.
    parsed = Graph()
    if source.is_remote:
        return parsed.parse(data=_resolved(source, package_path).data['ngsild'],
                            format='turtle', publicID=source.source)
    where = os.path.abspath(locate(source, package_path))
    root = os.path.abspath(package_path)
    if os.path.commonpath([where, root]) != root:
        from ..errors import PackageError
        raise PackageError(f'the NGSI-LD vocabulary {source.source} is outside the '
                           f'package')
    with open(where, 'rb') as handle:
        return parsed.parse(data=handle.read(), format='turtle')


def terms(package_path):
    """{local name: IRI} for everything the vocabulary declares."""
    from rdflib import URIRef

    NGSILD = 'https://uri.etsi.org/ngsi-ld/'
    found = {}
    for subject in set(for_package(package_path).subjects(None, None)):
        text = str(subject)
        if isinstance(subject, URIRef) and text.startswith(NGSILD) \
                and len(text) > len(NGSILD):
            found[text[len(NGSILD):]] = text
    return found
