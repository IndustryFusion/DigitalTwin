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

"""Where the NGSI-LD vocabulary comes from: declared, never shipped.

A package names it in semforge.yaml -- a local file while it is worked on, the
official url, pinned, once published. One that names none gets the default:
the official url, or SEMFORGE_NGSILD.
"""

import io
import os
import shutil

import pytest

from semforge.package import load

SDK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SHARED = os.path.abspath(os.path.join(SDK, '..', 'ontology', 'ngsild.ttl'))
HASVALUE = 'https://uri.etsi.org/ngsi-ld/hasValue'
URL = 'https://example.org/contexts/ngsild.ttl'


def _package(tmp_path, ngsild=None, config=True):
    """A copy of the corpus whose semforge.yaml says `ngsild` (or nothing)."""
    from tests.unit.conftest import CORPUS

    root = tmp_path / 'pkg'
    shutil.copytree(CORPUS, root, ignore=shutil.ignore_patterns('.semforge'))
    text = (root / 'semforge.yaml').read_text()
    text = text[:text.index('\n# The NGSI-LD vocabulary')] + '\n'
    if ngsild:
        text += ngsild
    if config:
        (root / 'semforge.yaml').write_text(text)
    else:
        (root / 'semforge.yaml').unlink()
    return str(root)


def _codes(package):
    from semforge.sanity import sanity

    return {f.code: f for f in sanity(package) if f.code.startswith('ngsild-')}


@pytest.fixture
def served(monkeypatch):
    """urlopen answering URL with the shared copy; counts the fetches."""
    import urllib.request

    with open(SHARED, 'rb') as handle:
        data = handle.read()
    fetched = []

    def urlopen(url, timeout=None):
        fetched.append(url)
        if url != URL:
            raise OSError(f'offline: {url}')
        return io.BytesIO(data)

    monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
    return fetched


def test_the_sdk_ships_no_vocabulary():
    shipped = [os.path.join(where, name)
               for where, _, names in os.walk(os.path.join(SDK, 'semforge'))
               for name in names if name.endswith('.ttl')]
    assert shipped == []


def test_the_kms_declares_the_shared_local_copy(corpus):
    from semforge.ngsild.vocabulary import source_for

    source = source_for(corpus.path)
    assert source.declared and source.source == '../ontology/ngsild.ttl'
    assert (None, None, None) in corpus.vocabulary
    assert not corpus.vocabulary_error
    assert _codes(corpus) == {}


def test_the_short_form_is_read_too(tmp_path):
    package = load(_package(tmp_path, 'ngsild: ../ontology/ngsild.ttl\n'))
    assert not package.vocabulary_error
    assert len(package.vocabulary)


def test_an_undeclared_package_gets_the_default_and_is_told(tmp_path, monkeypatch):
    from semforge.ngsild.vocabulary import source_for

    monkeypatch.setenv('SEMFORGE_NGSILD', SHARED)
    package = load(_package(tmp_path))
    source = source_for(package.path)
    assert not source.declared and source.source == SHARED
    assert len(package.vocabulary)
    finding = _codes(package)['ngsild-undeclared']
    assert finding.severity == 'information' and SHARED in finding.message


def test_without_the_setting_the_default_is_the_official_url(monkeypatch):
    from semforge.ngsild.vocabulary import OFFICIAL, default_source

    monkeypatch.delenv('SEMFORGE_NGSILD', raising=False)
    assert default_source() == OFFICIAL


def test_without_a_semforge_yaml_nothing_is_said(tmp_path):
    package = load(_package(tmp_path, config=False))
    assert _codes(package) == {}


def test_a_missing_file_is_an_error_not_a_crash(tmp_path):
    package = load(_package(tmp_path, 'ngsild:\n  source: vendor/nowhere.ttl\n'))
    assert len(package.vocabulary) == 0
    finding = _codes(package)['ngsild-unavailable']
    assert finding.severity == 'error' and 'nowhere.ttl' in finding.message
    assert finding.file.endswith('semforge.yaml') and finding.line > 1


def test_a_remote_source_is_fetched_once_and_cached(tmp_path, served):
    root = _package(tmp_path, f'ngsild:\n  source: {URL}\n')
    package = load(root)
    assert (None, None, None) in package.vocabulary
    load(root)
    assert served == [URL]
    cache = os.path.join(root, '.semforge', 'cache', 'deps')
    assert '*' in open(os.path.join(cache, '.gitignore')).read().split()
    assert _codes(package)['ngsild-unpinned'].severity == 'warning'


def test_a_pinned_remote_source_is_verified(tmp_path, served):
    from semforge.package.registry import digest

    with open(SHARED, 'rb') as handle:
        pinned = digest(handle.read())
    package = load(_package(tmp_path, f'ngsild:\n  source: {URL}\n  sha256: {pinned}\n'))
    assert len(package.vocabulary) and _codes(package) == {}

    wrong = load(_package(tmp_path / 'other',
                          f'ngsild:\n  source: {URL}\n  sha256: sha256:{"0" * 64}\n'))
    assert len(wrong.vocabulary) == 0
    assert 'does not match' in _codes(wrong)['ngsild-unavailable'].message


def test_offline_a_remote_source_is_an_error_not_a_crash(tmp_path, served):
    package = load(_package(tmp_path, 'ngsild:\n  source: https://example.org/gone.ttl\n'))
    assert len(package.vocabulary) == 0
    assert 'offline' in _codes(package)['ngsild-unavailable'].message


def test_init_writes_a_local_default_relative_to_the_package(tmp_path, monkeypatch):
    from semforge.ngsild.vocabulary import source_for
    from semforge.package.scaffold import create_package

    monkeypatch.setenv('SEMFORGE_NGSILD', SHARED)
    root = tmp_path / 'new'
    create_package(str(root), name='new')
    source = source_for(str(root))
    assert source.declared and not os.path.isabs(source.source)
    assert os.path.realpath(os.path.join(root, source.source)) == os.path.realpath(SHARED)
    package = load(str(root))
    assert len(package.vocabulary) and _codes(package) == {}


def test_init_pins_a_remote_default(tmp_path, monkeypatch, served):
    from semforge.ngsild.vocabulary import source_for
    from semforge.package.scaffold import create_package

    monkeypatch.setenv('SEMFORGE_NGSILD', URL)
    root = tmp_path / 'new'
    create_package(str(root), name='new')
    source = source_for(str(root))
    assert source.source == URL and source.sha256.startswith('sha256:')
    assert _codes(load(str(root))) == {}


def test_init_offline_writes_it_unpinned_and_says_so(tmp_path, monkeypatch, served):
    from semforge.package.scaffold import create_package

    monkeypatch.setenv('SEMFORGE_NGSILD', 'https://example.org/gone.ttl')
    root = tmp_path / 'new'
    create_package(str(root), name='new')
    assert 'sha256: not fetched' in (root / 'semforge.yaml').read_text()


def test_the_setting_shows_the_source_or_the_default(tmp_path, corpus, monkeypatch):
    from semforge.package.config import settings

    row = {s.key: s for s in settings(corpus.path)}['ngsild.source']
    assert row.value == '../ontology/ngsild.ttl' and row.line > 1
    assert not row.editable

    monkeypatch.setenv('SEMFORGE_NGSILD', SHARED)
    row = {s.key: s for s in settings(_package(tmp_path))}['ngsild.source']
    assert row.value == '' and row.default == SHARED
