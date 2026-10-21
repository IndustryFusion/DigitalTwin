"""Local context while working, published context on export."""

import json
import shutil
import urllib.request

import pytest
from click.testing import CliRunner

from semforge.cli import cli
from semforge.package import load
from semforge.package.context import (ContextServer, check_export_readiness,
                                      context_config, local_context_value,
                                      model_context, resolve_model_document,
                                      retarget_model, serve_local_context)
from semforge.target import export

PUBLISHED = ('https://industryfusion.github.io/contexts/staging/example/'
             'v0.2/context.jsonld')


@pytest.fixture
def package(tmp_path, corpus):
    target = tmp_path / 'pkg'
    target.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], target / name)
    for extra in ('context.jsonld', 'semforge.yaml'):
        shutil.copy(f'{corpus.path}/{extra}', target / extra)
    return load(str(target))


def test_the_package_declares_both_contexts(corpus):
    config = context_config(corpus.path)
    assert config.local == 'context.jsonld'
    assert config.published == PUBLISHED


def test_the_model_on_disk_names_the_published_url(corpus):
    """It must, or it would be useless to anyone who resolves the url."""
    assert model_context(corpus.sources['model']) == PUBLISHED


def test_loading_resolves_it_locally_anyway(corpus):
    """No network, and a term works the moment the local context declares it."""
    assert corpus.context_resolved_locally is True
    assert len(corpus.model) > 0


def test_resolution_substitutes_content_not_a_path(corpus):
    document, swapped = resolve_model_document(corpus.path,
                                               corpus.sources['model'])
    assert swapped
    inline = document[0]['@context']
    assert inline == local_context_value(corpus.path)
    assert not isinstance(inline, str), 'the url should be replaced by content'


def test_a_package_without_a_declared_context_is_left_alone(tmp_path, corpus):
    target = tmp_path / 'plain'
    target.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], target / name)
    loaded = load(str(target))
    assert loaded.context_resolved_locally is False


# --- export ------------------------------------------------------------------

def test_export_points_the_model_at_the_published_context(package, tmp_path):
    out = str(tmp_path / 'out')
    written = export(package, out)
    assert written['context_url'] == PUBLISHED
    with open(written['model']) as handle:
        assert json.load(handle)[0]['@context'] == PUBLISHED


def test_export_can_be_pointed_somewhere_else(package, tmp_path):
    out = str(tmp_path / 'out')
    written = export(package, out, target_context='https://elsewhere/ctx.jsonld')
    assert written['context_url'] == 'https://elsewhere/ctx.jsonld'


def test_the_corpus_is_ready_to_export(corpus, tmp_path):
    """Everything the model uses is in the published context today."""
    findings = check_export_readiness(corpus, cache_dir=str(tmp_path))
    assert [f for f in findings if f.severity == 'error'] == []


def test_a_locally_declared_term_blocks_export_until_it_is_published(package,
                                                                     tmp_path):
    """The gate the local/published split exists for.

    A term can be used the moment the LOCAL context declares it. Exported, it
    works only if the url the file names declares it too -- so export says so
    instead of shipping values that will not expand.
    """
    with open(package.sources['model']) as handle:
        model = json.load(handle)
    model[0]['brandNew:attr'] = {'type': 'Property', 'value': 1}
    with open(package.sources['model'], 'w') as handle:
        json.dump(model, handle)

    with open(f'{package.path}/context.jsonld') as handle:
        context = json.load(handle)
    context['@context'][1]['brandNew'] = {
        '@id': 'https://example.org/brand-new/', '@prefix': True}
    with open(f'{package.path}/context.jsonld', 'w') as handle:
        json.dump(context, handle)

    reloaded = load(package.path)
    findings = check_export_readiness(reloaded, cache_dir=str(tmp_path / 'c'))
    blocking = [f for f in findings if f.severity == 'error']
    assert blocking, 'a term the published context lacks must block export'
    assert 'brandNew' in blocking[0].message
    assert 'PUBLISHED context does not declare it' in blocking[0].message


def test_export_writes_nothing_when_the_context_is_not_ready(package, tmp_path):
    with open(package.sources['model']) as handle:
        model = json.load(handle)
    model[0]['neverPublished:attr'] = {'type': 'Property', 'value': 1}
    with open(package.sources['model'], 'w') as handle:
        json.dump(model, handle)
    with open(f'{package.path}/context.jsonld') as handle:
        context = json.load(handle)
    context['@context'][1]['neverPublished'] = {
        '@id': 'https://example.org/np/', '@prefix': True}
    with open(f'{package.path}/context.jsonld', 'w') as handle:
        json.dump(context, handle)

    out = tmp_path / 'out'
    result = CliRunner().invoke(cli, ['export', package.path, '-o', str(out)])
    assert result.exit_code == 2
    assert 'published context must be updated' in result.output
    assert not out.exists() or not list(out.iterdir())


# --- import / retarget -------------------------------------------------------

def test_retargeting_a_model_to_local_and_back(package):
    changed = retarget_model(package.sources['model'], 'context.jsonld')
    assert changed > 0
    assert model_context(package.sources['model']) == 'context.jsonld'

    retarget_model(package.sources['model'], PUBLISHED)
    assert model_context(package.sources['model']) == PUBLISHED


def test_retarget_command_switches_an_imported_model(package):
    result = CliRunner().invoke(cli, ['retarget', package.path, '--to', 'local'])
    assert result.exit_code == 0
    assert model_context(package.sources['model']) == 'context.jsonld'

    result = CliRunner().invoke(cli, ['retarget', package.path,
                                      '--to', 'published'])
    assert model_context(package.sources['model']) == PUBLISHED


# --- the server --------------------------------------------------------------

def test_the_local_context_can_be_served_over_http(corpus):
    """For tools that insist on a url. The SDK itself does not need it."""
    server = serve_local_context(corpus.path)
    try:
        served = json.loads(urllib.request.urlopen(server.url).read())
        assert served['@context'] == local_context_value(corpus.path)
        assert server.url.startswith('http://127.0.0.1:')
    finally:
        server.stop()


def test_serving_a_package_without_a_context_is_an_error(tmp_path, corpus):
    from semforge.errors import PackageError

    target = tmp_path / 'plain'
    target.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], target / name)
    with pytest.raises(PackageError):
        serve_local_context(str(target))


def test_the_server_stops_cleanly():
    server = ContextServer(path='tests/corpus/kms/context.jsonld').start()
    port = server.port
    server.stop()
    assert port > 0
