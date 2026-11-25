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

"""A package's tests read and write no cache (issue #1096, openspec
gh-1096-tests-read-no-cache).

A package directory from elsewhere can bring a `.semforge/cache` of its own:
the tests judge the package by its files. Elsewhere the caches keep working.
"""

import hashlib
import json
import os
import sys

import pytest
from click.testing import CliRunner

from semforge.cli.main import cli
from semforge.cooked import choices
from semforge.package import context, graphcache, prefixes
from semforge.package.graphcache import graphs_dir
from semforge.package.loader import load
from semforge.package.offline import offline
from semforge.package.releases import run_tests
from semforge.package.scaffold import create_package
from semforge.rdfio import turtle_index
from semforge.rdfio.derived import cache_dir

CORE = 'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld'
OFFICIAL = 'https://industryfusion.github.io/contexts/staging/ontology/v0/ngsild.ttl'

_watching = []          # the list that collects paths, while one is watching
_hooked = False


def _watch(event, args):
    if _watching and event in ('open', 'os.listdir', 'os.scandir', 'os.mkdir',
                               'os.rename', 'os.remove'):
        _watching[-1].extend(os.fsdecode(a) for a in args[:2]
                             if isinstance(a, (str, bytes, os.PathLike)))


@pytest.fixture
def touched():
    """Every path the code opens, lists, makes, renames or removes."""
    global _hooked
    if not _hooked:
        sys.addaudithook(_watch)
        _hooked = True
    paths = []
    _watching.append(paths)
    yield paths
    _watching.pop()


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    """A fresh package, and an empty cache of the user's. What a test leaves in
    the process's memory, forged or not, goes with it."""
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'user'))
    root = str(tmp_path / 'fresh')
    create_package(root, name='fresh', layout='flat')
    memos = (turtle_index._PARSED, prefixes._read, choices._ENTITY_ROOTS, context._fetched)
    kept = [memo.copy() for memo in memos]
    yield root
    for memo, before in zip(memos, kept):
        memo.clear()
        memo.update(before)


def _warm(root):
    """Load the package as the editor does: its caches are filled."""
    turtle_index._PARSED.clear()
    package = load(root)
    package.index('knowledge')
    package.index('shapes')
    turtle_index._PARSED.clear()                   # the next process
    return package


def _entry(directory, file):
    names = [n for n in os.listdir(directory) if f'_{file}.' in n and n.endswith('.json')]
    assert len(names) == 1, names
    return os.path.join(directory, names[0])


def _change(path, **values):
    with open(path, encoding='utf-8') as handle:
        stored = json.load(handle)
    stored.update(values)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(stored, handle)


def _verify(root):
    result = CliRunner().invoke(cli, ['verify', '--tests', '--format', 'json', root])
    return result.exit_code, json.loads(result.output)


def _tree(root):
    """{path: content}, None for a directory."""
    found = {}
    for directory, below, names in os.walk(root):
        found.update((os.path.join(directory, name), None) for name in below)
        for name in names:
            path = os.path.join(directory, name)
            with open(path, 'rb') as handle:
                found[path] = handle.read()
    return found


@pytest.mark.parametrize('file', ['shacl.ttl', 'knowledge.ttl'])
def test_emptied_triples_do_not_decide(pkg, file):
    code, clean = _verify(pkg)
    assert code == 0 and clean['tests']['constraints'] > 0, clean
    _warm(pkg)
    _change(_entry(graphs_dir(pkg), file), terms=[], triples=[])
    assert _verify(pkg) == (code, clean)


def test_a_violated_example_is_not_hidden(pkg):
    """Files that fail, and an entry with the triples of files that pass."""
    _warm(pkg)
    with open(_entry(graphs_dir(pkg), 'shacl.ttl'), encoding='utf-8') as handle:
        passing = json.load(handle)
    with open(os.path.join(pkg, 'shacl.ttl'), 'a', encoding='utf-8') as handle:
        handle.write('''
<urn:test:Broken> a <http://www.w3.org/ns/shacl#NodeShape> ;
    <http://www.w3.org/ns/shacl#targetSubjectsOf> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ;
    <http://www.w3.org/ns/shacl#property> [
        <http://www.w3.org/ns/shacl#path> <urn:test:missing> ;
        <http://www.w3.org/ns/shacl#minCount> 1 ] .
''')
    _warm(pkg)
    _change(_entry(graphs_dir(pkg), 'shacl.ttl'), **passing)
    code, report = _verify(pkg)
    assert code == 2 and report['tests']['met'] < report['tests']['examples'], report


@pytest.mark.parametrize('file', ['knowledge.ttl', 'shacl.ttl'])
def test_a_changed_statement_index_does_not_decide(pkg, file):
    clean = _verify(pkg)
    assert clean[0] == 0, clean
    _warm(pkg)
    # A subject that cannot be one: an index built from it raises.
    _change(_entry(cache_dir(pkg, 'index'), file), blocks=[[[], '', 0, 0, 1, 1]])
    assert _verify(pkg) == clean


@pytest.mark.parametrize('how', [
    lambda path, pkg, text: turtle_index.index_file(path, pkg),
    lambda path, pkg, text: turtle_index.index_file(path),
    lambda path, pkg, text: turtle_index.TurtleIndex(text),
], ids=['package', 'file', 'text'])
def test_an_index_kept_in_memory_does_not_decide(pkg, how):
    """Read from a changed entry earlier, in the same process."""
    path = os.path.join(pkg, 'shacl.ttl')
    with offline(pkg):
        own = turtle_index.index_file(path, pkg).blocks
    _warm(pkg)
    _change(_entry(cache_dir(pkg, 'index'), 'shacl.ttl'), blocks=[])
    assert len(turtle_index.index_file(path, pkg)) == 0           # elsewhere: the cache
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    with offline(pkg):
        assert how(path, pkg, text).blocks == own
    assert own
    assert len(turtle_index.TurtleIndex(text)) == 0               # elsewhere: as before


def _restamp(path, text):
    """`text` in `path`, with the time and size the file had."""
    before = os.stat(path)
    assert len(text.encode()) == before.st_size
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


def test_a_descriptor_with_the_same_stamp_is_read(pkg):
    from semforge.cooked.choices import declared_entity_root
    from semforge.package.prefixes import declared_prefixes

    path = os.path.join(pkg, 'kms.yaml')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    text = '\n'.join(line for line in text.split('\n') if not line.startswith('entityRoot:'))
    if '\nnamespaces:' not in text:
        text += '\nnamespaces:\n'
    text = text.replace('\nnamespaces:', '\nnamespaces:\n  one: https://one.example/', 1) \
        + '\nentityRoot: https://one.example/Root\n'
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    assert str(declared_entity_root(pkg)) == 'https://one.example/Root'
    assert declared_prefixes(pkg)['one'] == 'https://one.example/'
    _restamp(path, text.replace('one.example', 'two.example'))
    with offline(pkg):
        assert declared_prefixes(pkg)['one'] == 'https://two.example/'
        assert str(declared_entity_root(pkg)) == 'https://two.example/Root'
    with offline(pkg):                                            # each run its own
        _restamp(path, text)
        assert declared_prefixes(pkg)['one'] == 'https://one.example/'


def test_a_context_with_the_same_stamp_is_read(pkg):
    from semforge.package.prefixes import context_prefixes

    path = os.path.join(pkg, 'context.jsonld')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    found = context_prefixes(pkg)                                 # remembered
    name, namespace = next((n, v) for n, v in found.items() if n.endswith('Entities'))
    other = namespace[:-2] + '_' + namespace[-1]
    _restamp(path, text.replace(namespace, other))
    with offline(pkg):
        assert context_prefixes(pkg)[name] == other


def test_the_result_goes_by_the_changed_descriptor(pkg):
    """An example's attribute is declared only through a name kms.yaml gives,
    which changes within one process, the file's size and time kept."""
    from semforge.cooked.choices import attribute_terms
    from semforge.expect import load_expectations
    from semforge.package.prefixes import declared_prefixes

    package = load(pkg)
    attribute = next(str(entry.iri) for entry in attribute_terms(package)
                     if 'ngsi-ld' not in str(entry.iri))
    namespace, local = attribute.rsplit('/', 1)
    other = namespace[:-1] + '_'
    path = os.path.join(pkg, 'kms.yaml')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    text = text.replace('\nnamespaces:', f'\nnamespaces:\n  alias: {other}/', 1)
    assert 'alias:' in text
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    example = next(e for e in load_expectations(pkg).examples if '/good/' in e.path)
    files = [os.path.join(d, n) for d, _, names in os.walk(os.path.join(pkg, 'examples'))
             for n in names if n == os.path.basename(example.path)]
    with open(files[0], encoding='utf-8') as handle:
        document = json.load(handle)
    entity = document[0] if isinstance(document, list) else document
    entity[f'alias:{local}'] = {'type': 'Property', 'value': 1}
    with open(files[0], 'w', encoding='utf-8') as handle:
        json.dump(document, handle)

    failing = run_tests(pkg).failing
    assert any(f'alias:{local}' in f for f in failing), failing
    assert declared_prefixes(pkg)['alias'] == other + '/'         # remembered
    _restamp(path, text.replace(f'alias: {other}/', f'alias: {namespace}/'))
    failing = run_tests(pkg).failing
    assert not any(f'alias:{local}' in f for f in failing), failing


def test_a_run_still_reads_each_file_once(pkg, monkeypatch):
    reads = []
    real = prefixes._declared_prefixes
    monkeypatch.setattr(prefixes, '_declared_prefixes',
                        lambda path: reads.append(path) or real(path))
    run_tests(pkg)
    assert len(reads) == 1
    run_tests(pkg)
    assert len(reads) == 2


def test_no_other_cache_decides(pkg, tmp_path):
    """Fetched dependencies and contexts, the user's too, and the editor's
    verdicts: forged, and not what the tests go by."""
    from semforge.editor import cache

    clean = _verify(pkg)
    assert clean[0] == 0, clean
    vocabulary = hashlib.sha256(OFFICIAL.encode()).hexdigest() + '.ttl'
    context = hashlib.sha256(CORE.encode()).hexdigest() + '.jsonld'
    for path, text in (
            (os.path.join(pkg, '.semforge', 'cache', 'deps', vocabulary), '# nothing\n'),
            (os.path.join(pkg, '.semforge', 'cache', 'contexts', context), '{"@context": {}}'),
            (str(tmp_path / 'user' / 'semforge' / 'contexts' / context), '{"@context": {}}')):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
    cache.store(pkg, 'verdicts', {'main': [], 'cases': {}})
    assert _verify(pkg) == clean


@pytest.mark.parametrize('warm', [False, True])
def test_a_test_run_touches_no_cache(pkg, tmp_path, touched, warm):
    if warm:
        _warm(pkg)
    before = _tree(pkg)
    del touched[:]
    run_tests(pkg)
    mine = [os.path.abspath(p) for p in touched]
    assert os.path.join(pkg, 'shacl.ttl') in mine                 # the watch works
    assert [p for p in mine if os.sep + '.semforge' in p] == []
    assert [p for p in mine if p.startswith(str(tmp_path / 'user'))] == []
    assert _tree(pkg) == before
    assert os.path.exists(os.path.join(pkg, '.semforge')) == warm


def test_a_test_run_computes_nothing_for_a_cache(pkg, monkeypatch):
    """No entry's name -- a hash of the whole file -- and no payload."""
    from semforge.rdfio import derived

    def computed(*args):
        raise AssertionError('computed for a cache that is not in use')

    for module, name in ((derived, 'entry_name'), (derived, 'write_entry'),
                         (graphcache, 'entry_name'), (graphcache, '_payload')):
        monkeypatch.setattr(module, name, computed)
    assert run_tests(pkg).constraints


def test_a_linked_cache_directory_is_not_written_through(pkg, tmp_path):
    """A `.semforge/cache/graphs` that is a link out of the package."""
    outside = tmp_path / 'outside'
    outside.mkdir()
    os.makedirs(os.path.join(pkg, '.semforge', 'cache'))
    os.symlink(outside, graphs_dir(pkg))
    run_tests(pkg)
    assert list(outside.iterdir()) == []


def test_elsewhere_the_cache_is_read_before_and_after_a_test_run(pkg):
    assert len(_warm(pkg).shapes) > 0
    _change(_entry(graphs_dir(pkg), 'shacl.ttl'), terms=[], triples=[])
    assert len(load(pkg).shapes) == 0                             # a hit
    assert run_tests(pkg).constraints
    assert len(load(pkg).shapes) == 0                             # still a hit
