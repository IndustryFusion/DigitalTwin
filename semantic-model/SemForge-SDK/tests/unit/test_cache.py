"""The editor cache: served while nothing changed, recomputed the moment
anything does, and removable at will.

The failure that matters is a stale hit -- a view from before an edit served
as if it were current -- so most of these change one thing and assert the next
read recomputes. The remote-context cache is tested without the network: the
download is injected.
"""

import os
import shutil

import pytest

from semforge.editor import cache


@pytest.fixture
def root(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _counting():
    calls = []

    def compute():
        calls.append(1)
        return {'roots': [len(calls)]}
    return compute, calls


# --- served while unchanged, recomputed on any change ---------------------------

def test_a_second_read_is_a_hit_and_computes_nothing(root):
    compute, calls = _counting()
    first, hit = cache.cached(root, 'view', compute)
    again, hit_again = cache.cached(root, 'view', compute)
    assert (hit, hit_again) == (False, True)
    assert first == again and len(calls) == 1


@pytest.mark.parametrize('change', ['edit', 'new-example', 'delete'])
def test_any_change_to_the_package_recomputes(root, change):
    compute, calls = _counting()
    cache.cached(root, 'view', compute)
    if change == 'edit':
        path = os.path.join(root, 'shacl.ttl')
        with open(path, 'a', encoding='utf-8') as handle:
            handle.write('\n# an edit\n')
    elif change == 'new-example':
        with open(os.path.join(root, 'examples', 'new.jsonld'), 'w') as handle:
            handle.write('[]')
    else:
        os.remove(os.path.join(root, 'examples', 'subobjects', 'filter-on.jsonld'))
    _, hit = cache.cached(root, 'view', compute)
    assert not hit and len(calls) == 2


def test_an_edit_behind_a_symlink_counts(tmp_path):
    """The corpus symlinks its examples in; an edit there is still an edit."""
    real = tmp_path / 'real-examples'
    real.mkdir()
    (real / 'case.jsonld').write_text('[]')
    package = tmp_path / 'pkg'
    package.mkdir()
    (package / 'examples').symlink_to(real)
    before = cache.fingerprint(str(package))
    (real / 'case.jsonld').write_text('[{}]')
    assert cache.fingerprint(str(package)) != before


def test_the_cache_itself_does_not_change_the_fingerprint(root):
    before = cache.fingerprint(root)
    cache.store(root, 'view', {'x': 1})
    assert cache.fingerprint(root) == before


def test_an_sdk_change_invalidates(root, monkeypatch):
    compute, calls = _counting()
    cache.cached(root, 'view', compute)
    monkeypatch.setattr(cache, '_sdk_fingerprint', 'a different sdk')
    _, hit = cache.cached(root, 'view', compute)
    assert not hit


def test_force_recomputes_even_when_current(root):
    compute, calls = _counting()
    cache.cached(root, 'view', compute)
    cache.cached(root, 'view', compute, force=True)
    assert len(calls) == 2


def test_a_torn_entry_reads_as_a_miss(root):
    compute, calls = _counting()
    cache.cached(root, 'view', compute)
    with open(os.path.join(cache.views_dir(root), 'view.json'), 'w') as handle:
        handle.write('{"fingerprint": ')
    _, hit = cache.cached(root, 'view', compute)
    assert not hit


def test_the_cache_is_never_committed(root):
    cache.store(root, 'view', {})
    with open(os.path.join(cache.views_dir(root), '.gitignore')) as handle:
        assert handle.read().strip().endswith('*')


# --- status and deletion ----------------------------------------------------------

def test_status_says_what_is_current(root):
    cache.store(root, 'one', {})
    cache.store(root, 'two', {})
    state = cache.status(root)
    assert state['current'] == 2 and state['bytes'] > 0
    with open(os.path.join(root, 'shacl.ttl'), 'a') as handle:
        handle.write('\n')
    assert cache.status(root)['current'] == 0


def test_clear_removes_views_and_optionally_the_contexts(root, tmp_path, monkeypatch):
    from semforge.package.context import user_context_cache

    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'xdg'))
    os.makedirs(user_context_cache())
    with open(os.path.join(user_context_cache(), 'x.jsonld'), 'w') as handle:
        handle.write('{}')
    cache.store(root, 'view', {'x': 1})

    assert cache.clear(root) > 0
    assert not os.path.exists(cache.views_dir(root))
    assert os.path.exists(user_context_cache()), 'contexts go only when asked'
    cache.clear(root, contexts=True)
    assert not os.path.exists(user_context_cache())


# --- remote JSON-LD contexts --------------------------------------------------------

def test_a_remote_context_is_downloaded_once(tmp_path):
    from semforge.package import context

    downloads = []

    def download(url):
        downloads.append(url)
        return {'@context': {'a': 'https://example.org/a'}}

    url = 'https://example.org/test-context-once.jsonld'
    context._fetched.pop(url, None)
    first = context.fetch_context(url, str(tmp_path), download=download)
    context._fetched.pop(url, None)              # a new process: disk only
    second = context.fetch_context(url, str(tmp_path), download=download)
    assert first == second and downloads == [url]


def test_the_context_cache_is_never_committed(tmp_path):
    from semforge.package import context

    url = 'https://example.org/test-context-ignored.jsonld'
    context._fetched.pop(url, None)
    context.fetch_context(url, str(tmp_path / 'contexts'),
                          download=lambda u: {'@context': {}})
    ignore = (tmp_path / 'contexts' / '.gitignore').read_text().splitlines()
    assert '*' in ignore


def test_an_unreachable_context_falls_back_rather_than_failing(tmp_path):
    from semforge.package import context

    def offline(url):
        raise OSError('no network')

    assert context.fetch_context('https://example.org/never.jsonld',
                                 str(tmp_path), download=offline) is None


def test_rdflib_fetches_through_the_cache():
    from rdflib.plugins.shared.jsonld import context as jsonld_context

    from semforge.package.context import install_context_cache

    install_context_cache()
    install_context_cache()                      # idempotent
    assert getattr(jsonld_context.source_to_json, '_semforge_cached', False)


# --- the server serves from it ----------------------------------------------------

def test_a_second_server_serves_the_views_from_disk(root):
    """Two server processes in a row: the second one's views are hits."""
    from test_lsp_protocol import Session

    def views():
        live = Session(os.path.join(root, 'shacl.ttl'))
        try:
            live.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                       'params': {'processId': os.getpid(), 'rootUri': 'file://' + root,
                                  'capabilities': {}}})
            assert live.wait_for(lambda m: m.get('id') == 1)
            out = {}
            for number, method in enumerate(('semforge/knowledge', 'semforge/model',
                                             'semforge/tree', 'semforge/project'), 10):
                live.send({'jsonrpc': '2.0', 'id': number, 'method': method,
                           'params': {'uri': 'file://' + os.path.join(root, 'shacl.ttl')}})
                reply = live.wait_for(lambda m, n=number: m.get('id') == n)[0]['result']
                assert not reply.get('error'), reply.get('error')
                out[method] = reply
            return out
        finally:
            live.close()

    first = views()
    second = views()
    assert not any(r['cached'] for r in first.values())
    assert all(r['cached'] for r in second.values())
    assert second['semforge/knowledge']['roots'] == first['semforge/knowledge']['roots']
    labels = [r['label'] for r in second['semforge/project']['roots']]
    assert labels[-1] == 'Cache', 'the project view shows the cache'
    assert 'all current' in second['semforge/project']['roots'][-1]['value']
