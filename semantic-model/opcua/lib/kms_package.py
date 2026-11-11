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
"""Assemble the output of nodeset2owl/owl2instances into a KMS package.

openspec change gh-944-opcua-kms-package, capability `opcua/kms-packaging`;
the package format is `contracts/kms-package`.

A KMS package is a directory: knowledge, shapes, model, a local context, the
NGSI-LD vocabulary and kms.yaml. The knowledge is the hard part. nodeset2owl
writes the type system into separate ontologies (core, di, machinery, pumps,
...) and points at them with owl:imports -- `file:///` paths on the machine
that built them, or urls. A package holding only the instance ontology has no
type system: every sh:targetClass names a class nothing declares.

So the knowledge becomes a directory holding the whole import closure, one
file per ontology. Each file is copied as it is, with one change: an import of
another copied file names that file's ontology IRI instead of where it was on
the building machine. Nothing in the package points outside it, and the same
inputs give the same package -- the same digest -- on every machine.

The package holds the model only: no examples suite. It is a draft.
"""

import os
import pathlib
import re
import shutil
import urllib.parse
import urllib.request
from collections import OrderedDict

from rdflib import Graph, OWL, RDF

KNOWLEDGE_DIR = 'knowledge'
VOCABULARY = os.path.join('vocabulary', 'ngsild.ttl')
FORMAT_VERSION = 1

# The repository's shared NGSI-LD vocabulary, copied into every package.
DEFAULT_NGSILD = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'ontology', 'ngsild.ttl'))

# Not copied, and not followed: the W3C vocabularies, and the NGSI-LD
# vocabulary, which the package carries once as vocabulary/ngsild.ttl.
EXCLUDED = ('http://www.w3.org/', 'https://www.w3.org/', '*/ngsild.ttl')

# The KMS package format's rules for a name and a version.
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
SEMVER = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
                    r'(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$')


class PackagingError(Exception):
    """The package cannot be written; the message says what and where."""


def _is_url(source):
    # urlparse lowercases the scheme: HTTP:// is a url too, never a local path.
    return urllib.parse.urlparse(source).scheme in ('http', 'https')


def excluded(source, patterns=EXCLUDED):
    for pattern in patterns:
        if pattern.startswith('*'):
            if source.endswith(pattern[1:]):
                return True
        elif source.startswith(pattern):
            return True
    return False


def _base(source):
    """The IRI a source's relative IRIs resolve against: the url itself, or the
    file: URI of the local file -- never the working directory."""
    return source if _is_url(source) else pathlib.Path(os.path.abspath(source)).as_uri()


def _location(iri, source):
    """Where an import of `source` is read from: a local path or a url.

    A local source may import local files (file: or relative) and urls. A url
    may import only other http(s) urls: an ontology fetched from the network
    must not make the tool read a file on this machine. Every other scheme is
    an error.
    """
    resolved = urllib.parse.urljoin(_base(source), iri)
    scheme = urllib.parse.urlparse(resolved).scheme
    if scheme in ('http', 'https'):
        return urllib.parse.urlunparse(urllib.parse.urlparse(resolved))   # scheme lowercased
    if scheme == 'file' and not _is_url(source):
        return os.path.normpath(urllib.parse.unquote(urllib.parse.urlparse(resolved).path))
    besides = '' if _is_url(source) else ' besides local files'
    raise PackagingError(f'{source} imports {iri}: only http(s) imports are followed{besides}')


def _read(source):
    """The bytes of a local file or a url."""
    if _is_url(source):
        with urllib.request.urlopen(source, timeout=60) as response:   # noqa: S310
            return response.read()
    with open(source, 'rb') as handle:
        return handle.read()


def _graph(source, data):
    graph = Graph()
    graph.parse(data=data.decode('utf-8'), format='turtle',
                publicID=_base(source))
    return graph


def _imports(source, read=_read):
    return [str(o) for o in _graph(source, read(source)).objects(None, OWL.imports)]


def import_closure(roots, resolve=_imports, exclude=EXCLUDED):
    """Every source reachable from `roots` through owl:imports, imports first.

    Returns an OrderedDict {source: [(iri, location), ...]} in a fixed order;
    a source is a local path or a url, and each pair is an owl:imports as
    written in the source and where it was found. A source matching `exclude`
    is neither copied nor followed. A source that cannot be read raises
    PackagingError naming it.
    """
    found = OrderedDict()

    def visit(source, trail):
        if source in found or source in trail or excluded(source, exclude):
            return
        try:
            iris = resolve(source)
        except PackagingError:
            raise
        except Exception as exc:                   # noqa: BLE001
            via = f' (imported by {sorted(trail)[-1]})' if trail else ''
            raise PackagingError(f'cannot read {source}{via}: {exc}') from exc
        imported = []
        for iri in iris:
            try:
                imported.append((iri, _location(iri, source)))
            except PackagingError:
                if not excluded(iri, exclude):
                    raise
                imported.append((iri, iri))         # excluded: never read
        for _, child in sorted(imported, key=lambda pair: pair[1]):
            visit(child, trail | {source})
        found[source] = imported

    for root in roots:
        visit(os.path.abspath(root), frozenset())
    return found


def _file_name(source, taken):
    """A file name for a source in knowledge/, unique within the package."""
    name = os.path.basename(urllib.parse.urlparse(source).path if _is_url(source)
                            else source) or 'ontology.ttl'
    if not name.endswith('.ttl'):
        name += '.ttl'
    stem, suffix = name[:-4], '.ttl'
    candidate, n = name, 1
    while candidate in taken:
        n += 1
        candidate = f'{stem}-{n}{suffix}'
    taken.add(candidate)
    return candidate


def _ontology_iri(source, data):
    """The IRI of the one owl:Ontology a file declares."""
    subjects = sorted(str(s) for s in _graph(source, data).subjects(RDF.type, OWL.Ontology))
    if not subjects:
        raise PackagingError(f'{source} declares no owl:Ontology, so an import of it '
                             f'cannot name it')
    return subjects[0]


# An IRI reference as Turtle writes it: <...>.
IRIREF = re.compile(r'<([^<>"{}|^`\\\x00-\x20]*)>')


def _rewrite_imports(source, data, imports, iri_of):
    """`data` with every import of a copied source naming that ontology's IRI.

    One pass over the IRI references of the text: each is resolved as rdflib
    resolved it (against the file, so relative imports work) and replaced if
    it is an import of a copied source. A replacement is never looked at
    again, so the order of the imports does not matter.
    """
    text = data.decode('utf-8')
    targets = {}
    for written, location in imports:
        if location in iri_of and written != iri_of[location]:
            targets[written] = iri_of[location]   # excluded imports stay as written
    base = _base(source)

    def replace(match):
        resolved = urllib.parse.urljoin(base, match.group(1))
        return f'<{targets[resolved]}>' if resolved in targets else match.group(0)

    text = IRIREF.sub(replace, text)
    # What counts is what the file imports once rewritten, not what the text
    # looks like: an import written another way (a prefixed name, @base, an
    # escape) is not rewritten, even if its IRI appears elsewhere as <...>.
    expected = sorted({targets.get(written, written) for written, _ in imports})
    data = text.encode('utf-8')
    found = sorted({str(o) for o in _graph(source, data).objects(None, OWL.imports)})
    if found != expected:
        missing = ', '.join(sorted(set(expected) - set(found)) or found)
        raise PackagingError(f'{source}: after rewriting, its imports are not the copied '
                             f'ontologies ({missing}); an import not written as an IRI <...> '
                             f'cannot be rewritten')
    return data


def _origin(source):
    """Where a knowledge file came from, as recorded in kms.yaml: a url, or
    the file's name -- never a path, which would depend on the directory
    layout of the building machine and so change the digest."""
    if _is_url(source):
        return source
    return os.path.basename(source)


def _yaml_string(value):
    """`value` as a YAML double-quoted scalar: printable ASCII as it is, every
    other character escaped, so no value can end the line or the string."""
    out = []
    for ch in str(value):
        code = ord(ch)
        if ch in '"\\':
            out.append('\\' + ch)
        elif 0x20 <= code < 0x7f:
            out.append(ch)
        elif code <= 0xffff:
            out.append(f'\\u{code:04x}')
        else:
            out.append(f'\\U{code:08x}')
    return '"' + ''.join(out) + '"'


def _config(name, version, published, origins):
    lines = [
        f'# {name}: a KMS package (Knowledge, Model, Shapes), written by owl2kms.py',
        '# from the output of nodeset2owl.py and owl2instances.py. It holds the',
        '# model only, no examples, so it is a draft: generated packages are not',
        '# published.',
        '',
        f'name: {name}',
        f'version: {version}',
        f'format: {FORMAT_VERSION}',
        '',
        '# The entities name the PUBLISHED context; tools answer it from the local',
        '# copy, so nothing here depends on the network.',
        'context:',
        '  local: context.jsonld',
        f'  published: {_yaml_string(published)}',
        '',
        '# The NGSI-LD vocabulary, inside the package.',
        'ngsild:',
        f'  source: {VOCABULARY.replace(os.sep, "/")}',
        '',
        '# knowledge/ is the owl:imports closure, one file per ontology:',
    ]
    lines += [f'#   {target} <- {origin}' for target, origin in origins]
    return '\n'.join(lines) + '\n'


def _check_name_and_version(name, version):
    if not name or not NAME.match(name):
        raise PackagingError(f'name {name!r} must be letters, digits, ".", "_" and "-", '
                             f'starting with a letter or digit')
    if not SEMVER.match(str(version)):
        raise PackagingError(f'version {version!r} must be a semantic version '
                             f'MAJOR.MINOR.PATCH')


def _check_nothing_local(out_dir, roots):
    """No member names a file: IRI or a directory the inputs came from."""
    places = {os.path.dirname(os.path.abspath(root)) for root in roots}
    places.add(os.path.abspath(out_dir))
    for here, _, files in os.walk(out_dir):
        for name in files:
            path = os.path.join(here, name)
            with open(path, 'rb') as handle:
                text = handle.read().decode('utf-8', errors='replace')
            rel = os.path.relpath(path, out_dir)
            if 'file:/' in text:
                raise PackagingError(f'{rel} still names a file: IRI')
            for place in places:
                if place and place != os.sep and place in text:
                    raise PackagingError(f'{rel} names {place}, a directory on this machine')


def build_package(out_dir, knowledge, shacl, instances, context, published, name,
                  version='0.1.0', ngsild=DEFAULT_NGSILD, resolve=None, read=_read,
                  exclude=EXCLUDED):
    """Write a KMS package into `out_dir`. Returns the files written.

    Nothing is left behind when it fails: the directory is written in full or
    not at all.
    """
    _check_name_and_version(name, version)
    if os.path.exists(out_dir) and os.listdir(out_dir):
        raise PackagingError(f'{out_dir} exists and is not empty')
    for role, path in (('NGSI-LD vocabulary', ngsild), ('shapes', shacl),
                       ('instances', instances), ('context', context)):
        if not os.path.isfile(path):
            raise PackagingError(f'the {role} file {path} does not exist')
    resolve = resolve or (lambda source: _imports(source, read))

    closure = import_closure(knowledge, resolve, exclude)

    data = {}
    for source in closure:
        try:
            data[source] = read(source)
        except Exception as exc:                   # noqa: BLE001
            raise PackagingError(f'cannot read {source}: {exc}') from exc
    iri_of = {source: _ontology_iri(source, data[source]) for source in closure}
    rewritten = {source: _rewrite_imports(source, data[source], closure[source], iri_of)
                 for source in closure}

    # One file per ontology. The same ontology can be reached at two paths --
    # build outputs copied from another directory still import the originals
    # there -- and must not become two files. Two different files claiming one
    # ontology IRI are an error.
    kept = OrderedDict()
    for source in closure:
        first = kept.setdefault(iri_of[source], source)
        if first != source and rewritten[first] != rewritten[source]:
            raise PackagingError(f'{first} and {source} both declare the ontology '
                                 f'{iri_of[source]} but differ')
    taken, targets = set(), OrderedDict()
    for source in kept.values():
        targets[source] = _file_name(source, taken)

    created = not os.path.exists(out_dir)
    try:
        os.makedirs(os.path.join(out_dir, KNOWLEDGE_DIR), exist_ok=True)
        written, origins = [], []
        for source, target in targets.items():
            where = os.path.join(out_dir, KNOWLEDGE_DIR, target)
            with open(where, 'wb') as handle:
                handle.write(rewritten[source])
            origins.append((f'{KNOWLEDGE_DIR}/{target}', _origin(source)))
            written.append(where)

        for source, target in ((shacl, 'shacl.ttl'), (instances, 'model-instance.jsonld'),
                               (context, 'context.jsonld')):
            shutil.copyfile(source, os.path.join(out_dir, target))
            written.append(os.path.join(out_dir, target))

        vocabulary = os.path.join(out_dir, VOCABULARY)
        os.makedirs(os.path.dirname(vocabulary), exist_ok=True)
        shutil.copyfile(ngsild, vocabulary)
        written.append(vocabulary)

        config = os.path.join(out_dir, 'kms.yaml')
        with open(config, 'w', encoding='utf-8') as handle:
            handle.write(_config(name, version, published, origins))
        written.append(config)

        _check_nothing_local(out_dir, knowledge)
    except BaseException:
        if created:
            shutil.rmtree(out_dir, ignore_errors=True)
        else:
            for entry in os.listdir(out_dir):
                path = os.path.join(out_dir, entry)
                shutil.rmtree(path) if os.path.isdir(path) else os.unlink(path)
        raise
    return written
