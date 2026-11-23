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

"""A package's tests run offline (openspec gh-943-offline-package-tests).

The scenarios of "SERVICE in a package's SPARQL", "A package's tests run
offline" and "Contexts of a test run resolve from the package"
(contracts/kms-package), and of "Tests run offline unless contexts may be
fetched" and "The SDK ships the NGSI-LD core context"
(semforge-sdk/package-tools).
Every network check runs against a local listener that records each request,
so "no connection is opened" is measured, not assumed.
"""

import http.server
import json
import os
import random
import socket
import sys
import threading
import urllib.request

import pytest
from click.testing import CliRunner
from rdflib import Graph

from semforge.errors import PackageError

from semforge.cli.main import cli
from semforge.package.discover import packages_below
from semforge.package.offline import (ALLOW, PINNED, NetworkRefused, ServiceRefused,
                                      network_uses, offline, pinned,
                                      resolve_context, services)
from semforge.package.releases import PublishRefused, publish, run_tests
from semforge.package.scaffold import create_package

KMS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'kms'))
CORE = 'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld'
OFFICIAL = 'https://industryfusion.github.io/contexts/staging/ontology/v0/ngsild.ttl'
NGSILD_TTL = os.environ['SEMFORGE_NGSILD']        # the repo's copy (conftest)


class _Listener:
    """A local HTTP server that records every request it receives.

    It answers a SPARQL query with one binding, `*.ttl` with an NGSI-LD
    vocabulary and anything else with an empty JSON-LD context, which is
    enough for a SERVICE, a vocabulary or a context fetch to succeed when it
    is allowed. `connections` counts every accepted TCP connection, also one
    that never sends an HTTP request (ftp).
    """

    def __init__(self):
        self.requests = []
        self.connections = 0
        self.answers = {}                          # path -> (status, headers, body)
        listener = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                listener.requests.append(self.path)
                if self.path in listener.answers:
                    status, headers, body = listener.answers[self.path]
                    self.send_response(status)
                    for name, value in headers.items():
                        self.send_header(name, value)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path.startswith('/sparql'):
                    body = json.dumps({'head': {'vars': ['o']}, 'results': {'bindings': [
                        {'o': {'type': 'literal', 'value': 'remote'}}]}}).encode()
                    kind = 'application/sparql-results+json'
                elif self.path.endswith('.ttl'):
                    with open(NGSILD_TTL, 'rb') as handle:
                        body = handle.read()
                    kind = 'text/turtle'
                else:
                    body, kind = b'{"@context": {}}', 'application/ld+json'
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_POST = do_GET

            def log_message(self, *args):
                pass

        class Server(http.server.ThreadingHTTPServer):
            def verify_request(self, request, client_address):
                listener.connections += 1
                return True

        self.server = Server(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def listener():
    started = _Listener()
    yield started
    started.close()


@pytest.fixture
def fresh(tmp_path):
    root = str(tmp_path / 'fresh')
    create_package(root, name='fresh', layout='flat')
    with open(os.path.join(root, 'kms.yaml'), 'a', encoding='utf-8') as handle:
        handle.write('\ntests:\n  coverage: 5\n')
    return root


def _add_shapes(root, text):
    with open(os.path.join(root, 'shacl.ttl'), 'a', encoding='utf-8') as handle:
        handle.write('\n' + text)


def _service_rule(root, url):
    """A SPARQL rule whose CONSTRUCT asks a SERVICE: it adds a triple the
    shapes never read, so the examples still meet their expectations."""
    _add_shapes(root, f'''
freshShacl:RemoteRuleShape a sh:NodeShape ;
    sh:targetClass freshEntities:Machine ;
    sh:rule [ a sh:SPARQLRule ;
        sh:construct """CONSTRUCT {{ $this <urn:remote:said> ?o }}
            WHERE {{ SERVICE <{url}/sparql> {{ ?s ?p ?o }} }}""" ] .
''')


def _service_constraint(root, url):
    _add_shapes(root, f'''
freshShacl:RemoteShape a sh:NodeShape ;
    sh:targetClass freshEntities:Machine ;
    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "asks a remote service" ;
        sh:select """SELECT $this WHERE {{ SERVICE <{url}/sparql> {{ $this ?p ?o }} }}""" ] .
''')


def _remote_context(root, url):
    """The model names a second, remote context beside the package's own."""
    path = os.path.join(root, 'model-instance.jsonld')
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    for entity in document:
        entity['@context'] = [entity['@context'], f'{url}/extra.jsonld']
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(document, handle)


# --- SERVICE --------------------------------------------------------------------

@pytest.mark.parametrize('allowed', [False, True])
def test_service_in_a_rule_is_refused(fresh, listener, allowed):
    _service_rule(fresh, listener.url)
    with pytest.raises(ServiceRefused) as refused:
        run_tests(fresh, allow_network=allowed)
    assert refused.value.problems == [(
        'freshShacl:RemoteRuleShape (rule)',
        f'uses SPARQL SERVICE <{listener.url}/sparql>, which a package cannot use: '
        f'a package\'s results must not depend on a remote endpoint')]
    assert listener.requests == []


@pytest.mark.parametrize('allowed', [False, True])
def test_service_in_a_constraint_is_refused(fresh, listener, allowed):
    # SHACL does not allow SERVICE in a SPARQL constraint; pyshacl refuses it.
    _service_constraint(fresh, listener.url)
    with pytest.raises(ServiceRefused) as refused:
        run_tests(fresh, allow_network=allowed)
    assert refused.value.problems[0][0] == \
        'freshShacl:RemoteShape/SPARQLConstraintComponent'
    assert 'SHACL does not allow SERVICE in a SPARQL constraint' in refused.value.problems[0][1]
    assert listener.requests == []


@pytest.mark.parametrize('flags', [[], ['--allow-network']])
def test_cli_verify_names_the_rule_and_opens_no_connection(fresh, listener, flags):
    _service_rule(fresh, listener.url)
    result = CliRunner().invoke(cli, ['verify', '--tests', *flags, fresh])
    assert result.exit_code == 2
    assert 'freshShacl:RemoteRuleShape (rule): uses SPARQL SERVICE' in result.output
    assert listener.requests == []


@pytest.mark.parametrize('flags', [[], ['--allow-network']])
def test_publish_is_refused(fresh, listener, tmp_path, flags):
    _service_rule(fresh, listener.url)
    out = str(tmp_path / 'p.kms.zip')
    with pytest.raises(PublishRefused) as refused:
        publish(fresh, output=out, allow_network=bool(flags))
    assert 'freshShacl:RemoteRuleShape (rule): uses SPARQL SERVICE' in str(refused.value)
    result = CliRunner().invoke(cli, ['publish', fresh, '-o', out, *flags])
    assert result.exit_code == 2
    assert 'freshShacl:RemoteRuleShape (rule): uses SPARQL SERVICE' in result.output
    assert not os.path.exists(out) and listener.requests == []
    assert not os.path.exists(os.path.join(fresh, '.kms', 'releases.yaml'))


def test_service_that_slips_past_the_scan_is_stopped(listener):
    """The audit hook: whatever opens a connection inside the scope fails,
    and the listener sees nothing."""
    query = f'SELECT ?o WHERE {{ SERVICE <{listener.url}/sparql> {{ ?s ?p ?o }} }}'
    with offline(os.getcwd()):
        with pytest.raises(ServiceRefused):
            list(Graph().query(query))
        with pytest.raises(NetworkRefused):
            urllib.request.urlopen(listener.url + '/plain', timeout=5)
        with pytest.raises(NetworkRefused):
            socket.create_connection(('127.0.0.1', listener.server.server_address[1]))
    # --allow-network lets a context fetch through, nothing else.
    with offline(os.getcwd(), fetch_contexts=True):
        with pytest.raises(NetworkRefused, match='only a JSON-LD context'):
            urllib.request.urlopen(listener.url + '/plain', timeout=5)
        with pytest.raises(ServiceRefused):
            list(Graph().query(query))
    assert listener.requests == []
    # Outside the scope the hook does nothing.
    assert list(Graph().query(query))
    assert listener.requests


def test_services_are_read_from_code_not_from_strings_or_comments():
    assert services('SELECT * WHERE { SERVICE SILENT <http://a/> { ?s ?p ?o } }') == ['<http://a/>']
    assert services('SELECT * WHERE { service ?endpoint { ?s ?p ?o } }') == ['?endpoint']
    assert services('# SERVICE <http://a/>\nSELECT * WHERE { ?s ?p "SERVICE" }') == []


def test_network_uses_names_targets_and_validators(fresh):
    _add_shapes(fresh, '''
freshShacl:TargetShape a sh:NodeShape ;
    sh:target [ a sh:SPARQLTarget ;
        sh:select """SELECT ?this WHERE { SERVICE <http://a.invalid/> { ?this ?p ?o } }""" ] .
freshShacl:RemoteComponent a sh:ConstraintComponent ;
    sh:parameter [ sh:path freshShacl:remote ] ;
    sh:validator [ a sh:SPARQLAskValidator ;
        sh:ask """ASK { SERVICE <http://b.invalid/> { $value ?p ?o } }""" ] .
''')
    from semforge.package.loader import load
    assert network_uses(load(fresh)) == [
        ('freshShacl:RemoteComponent', '<http://b.invalid/>', True),
        ('freshShacl:TargetShape (target)', '<http://a.invalid/>', False)]


# --- JSON-LD contexts -----------------------------------------------------------

def test_remote_context_is_refused_offline(fresh, listener, monkeypatch, tmp_path):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    _remote_context(fresh, listener.url)
    result = CliRunner().invoke(cli, ['verify', '--tests', fresh])
    assert result.exit_code == 2
    assert f'the JSON-LD context {listener.url}/extra.jsonld is neither' in result.output
    assert listener.requests == []

    allowed = CliRunner().invoke(cli, ['verify', '--tests', '--allow-network', fresh])
    assert allowed.exit_code == 0, allowed.output
    assert '/extra.jsonld' in listener.requests


def test_an_undeclared_own_context_says_what_to_add(fresh, listener, monkeypatch, tmp_path):
    """The model names its context URL, and kms.yaml does not declare it."""
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    url = listener.url + '/own.jsonld'
    path = os.path.join(fresh, 'model-instance.jsonld')
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    for entity in document:
        entity['@context'] = url
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(document, handle)
    result = CliRunner().invoke(cli, ['verify', '--tests', fresh])
    assert result.exit_code == 2
    assert f'the model names {url} as its context' in result.output
    assert f'add `published: {url}` under `context:` in kms.yaml' in result.output
    assert listener.requests == []


def test_context_file_outside_the_package_is_refused(fresh, tmp_path):
    outside = tmp_path / 'outside.jsonld'
    outside.write_text('{"@context": {}}', encoding='utf-8')
    with offline(fresh):
        with pytest.raises(NetworkRefused, match='outside the package'):
            resolve_context(outside.as_uri())
        with open(os.path.join(fresh, 'context.jsonld'), encoding='utf-8') as handle:
            assert resolve_context('file://' + os.path.join(fresh, 'context.jsonld')) == \
                json.load(handle)


def test_the_package_s_own_and_the_pinned_contexts_answer(fresh):
    from semforge.package.offline import package_contexts
    own = package_contexts(fresh)
    with offline(fresh, own):
        assert resolve_context('https://example.org/fresh/context.jsonld') == \
            own['https://example.org/fresh/context.jsonld']
        assert resolve_context(CORE)['@context']['ngsi-ld'] == 'https://uri.etsi.org/ngsi-ld/'
        with pytest.raises(NetworkRefused, match='is not a URL'):
            resolve_context(object())


def test_pinned_contexts_ship_with_etsi_s_licence():
    from semforge.package.offline import PINNED_DIR
    with open(os.path.join(PINNED_DIR, 'LICENSE-ETSI-BSD-3-Clause'), encoding='utf-8') as handle:
        text = handle.read()
    assert text.startswith('Copyright 2024 ETSI') and 'Redistribution and use' in text
    for name, _ in PINNED.values():
        assert os.path.isfile(os.path.join(PINNED_DIR, name))


def test_pinned_contexts_are_checked_on_every_read(monkeypatch):
    import semforge.package.offline as offline_module
    assert pinned('https://example.org/not-pinned.jsonld') is None
    assert pinned(CORE) is not None               # read once, and it holds
    name, _ = PINNED[CORE]
    monkeypatch.setitem(offline_module.PINNED, CORE, (name, 'sha256:' + '0' * 64))
    with pytest.raises(PackageError, match='the context the SDK ships'):
        pinned(CORE)                              # read again: hashed again


# --- the packages in semantic-model/kms -------------------------------------------

def _no_network(monkeypatch):
    """Every connection and lookup fails and is recorded: below the SDK's own
    guard, so the test does not rely on what it checks."""
    attempts = []

    def refuse(*args, **kwargs):
        attempts.append(args)
        raise OSError('no network in this test')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    return attempts


def test_kms_example_passes_with_no_network_at_all(monkeypatch):
    attempts = _no_network(monkeypatch)
    run = run_tests(os.path.join(KMS, 'example'))
    assert run.passed and run.examples == run.met > 0
    result = CliRunner().invoke(cli, ['verify', '--tests', os.path.join(KMS, 'example')])
    assert result.exit_code == 0, result.output
    assert attempts == []


def _summary(run):
    return dict(run.as_dict(), covered=run.covered, constraints=run.constraints)


@pytest.mark.parametrize('package', [p for _, p, _ in packages_below(KMS)])
def test_results_are_the_same_with_and_without_the_network(package):
    from semforge.package.context import fetch_context, user_context_cache
    offline_run = _summary(run_tests(package))
    if fetch_context(CORE, user_context_cache()) is None:
        pytest.skip('the NGSI-LD core context cannot be fetched here')
    assert _summary(run_tests(package, allow_network=True)) == offline_run


def test_there_are_packages_to_compare():
    # An empty directory would make the comparison above vacuous.
    assert 'example' in [name for name, _, _ in packages_below(KMS)]


def test_shapes_the_validator_refuses_are_reported():
    """A SPARQL constraint pyshacl refuses (here: VALUES) is a PackageError,
    not a traceback reading a report that is not one."""
    from semforge.validate.adapters import pyshacl_adapter
    shapes = Graph().parse(format='turtle', data='''
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://example.org/> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ;
    sh:sparql [ sh:select """SELECT $this WHERE { VALUES ?x { 1 } $this ?p ?x }""" ] .
''')
    data = Graph().parse(format='turtle', data='<http://example.org/a> a <http://example.org/T> .')
    with pytest.raises(PackageError, match='cannot be validated'):
        pyshacl_adapter.run(data, shapes)


# --- review of #1085 ----------------------------------------------------------------

def _model_context(root, value):
    path = os.path.join(root, 'model-instance.jsonld')
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    for entity in document:
        entity['@context'] = [entity['@context'], value]
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(document, handle)


@pytest.mark.parametrize('flags', [[], ['--allow-network']])
@pytest.mark.parametrize('scheme', ['ftp', 'gopher'])
def test_another_scheme_is_never_read(fresh, listener, scheme, flags):
    port = listener.server.server_address[1]
    _model_context(fresh, f'{scheme}://127.0.0.1:{port}/ctx.jsonld')
    result = CliRunner().invoke(cli, ['verify', '--tests', *flags, fresh])
    assert result.exit_code == 2
    assert 'nor an http(s) URL' in result.output
    assert listener.connections == 0


def test_an_upper_case_scheme_is_still_offline(fresh, listener, monkeypatch, tmp_path):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    url = listener.url.replace('http://', 'HTTP://') + '/extra.jsonld'
    _model_context(fresh, url)
    result = CliRunner().invoke(cli, ['verify', '--tests', fresh])
    assert result.exit_code == 2 and f'the JSON-LD context {url} is neither' in result.output
    assert listener.connections == 0
    with offline(fresh):                       # and the shipped copy answers HTTPS://
        assert resolve_context(CORE.replace('https://', 'HTTPS://')) == pinned(CORE)


@pytest.mark.parametrize('scheme', ['FILE', 'File'])
def test_a_file_context_outside_the_package_in_any_case(fresh, tmp_path, scheme):
    outside = tmp_path / 'outside.jsonld'
    outside.write_text('{"@context": {}}', encoding='utf-8')
    url = outside.as_uri().replace('file:', scheme + ':', 1)
    with offline(fresh):
        with pytest.raises(NetworkRefused, match='outside the package'):
            resolve_context(url)
        inside = os.path.join(fresh, 'context.jsonld')
        for other in ('file://elsewhere' + inside, 'file://localhost' + inside,
                      'file:' + inside, str(outside), inside):
            with pytest.raises(NetworkRefused, match='nor an http'):
                resolve_context(other)
    _model_context(fresh, url)
    result = CliRunner().invoke(cli, ['verify', '--tests', fresh])
    assert result.exit_code == 2 and 'outside the package' in result.output


@pytest.mark.parametrize('written', ['\\u0053ERVICE', '\\U00000053ERVICE', 'S\\u0045RVICE'])
def test_service_written_with_an_escape_is_found(fresh, listener, written):
    assert services(f'SELECT * WHERE {{ {written} <http://a/> {{ ?s ?p ?o }} }}') == ['<http://a/>']
    # In Turtle the backslash itself is escaped, so the SPARQL text holds \\u.
    turtle = written.replace('\\', '\\\\')
    _add_shapes(fresh, f'''
freshShacl:EscapedShape a sh:NodeShape ;
    sh:targetClass freshEntities:Machine ;
    sh:rule [ a sh:SPARQLRule ;
        sh:construct """CONSTRUCT {{ $this <urn:remote:said> ?o }}
            WHERE {{ {turtle} <{listener.url}/sparql> {{ ?s ?p ?o }} }}""" ] .
''')
    with pytest.raises(ServiceRefused, match='EscapedShape'):
        run_tests(fresh, allow_network=True)
    assert listener.connections == 0


def test_an_invalid_escape_does_not_parse():
    with pytest.raises(ValueError):
        services('SELECT * WHERE { ?s ?p "\\U0011FFFF" }')


def test_publish_reports_a_shipped_copy_that_fails_its_hash(fresh, monkeypatch, tmp_path):
    import semforge.package.offline as offline_module
    name, _ = PINNED[CORE]
    monkeypatch.setitem(offline_module.PINNED, CORE, (name, 'sha256:' + '0' * 64))
    out = str(tmp_path / 'p.kms.zip')
    result = CliRunner().invoke(cli, ['publish', fresh, '-o', out])
    assert result.exit_code == 2, result.output
    assert 'not published; nothing written' in result.output
    assert 'tests do not run' in result.output and 'the context the SDK ships' in result.output
    assert not os.path.exists(out)


def test_publish_reports_shapes_the_validator_refuses(fresh, tmp_path):
    _add_shapes(fresh, '''
freshShacl:ValuesShape a sh:NodeShape ;
    sh:targetClass freshEntities:Machine ;
    sh:sparql [ sh:select """SELECT $this WHERE { VALUES ?x { 1 } $this ?p ?x }""" ] .
''')
    out = str(tmp_path / 'p.kms.zip')
    result = CliRunner().invoke(cli, ['publish', fresh, '-o', out])
    assert result.exit_code == 2, result.output
    assert 'not published; nothing written' in result.output
    assert 'tests do not run: the shapes cannot be validated' in result.output
    assert not os.path.exists(out)


def _vocabulary(root, source, sha256=''):
    path = os.path.join(root, 'kms.yaml')
    with open(path, encoding='utf-8') as handle:
        lines = handle.read().split('\n')
    start = lines.index('ngsild:')
    end = start + 1
    while end < len(lines) and lines[end].startswith('  '):
        end += 1
    lines[start:end] = ['ngsild:', f'  source: {source}'] + \
        ([f'  sha256: {sha256}'] if sha256 else [])
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))


def test_the_official_vocabulary_is_shipped(fresh, monkeypatch):
    from semforge.package.offline import PINNED_VOCABULARIES, shipped_vocabulary
    _, digest = PINNED_VOCABULARIES[OFFICIAL]
    _vocabulary(fresh, OFFICIAL, digest)
    attempts = _no_network(monkeypatch)
    run = run_tests(fresh)
    assert run.passed and run.examples == 2
    assert attempts == []
    assert shipped_vocabulary(OFFICIAL)[1].startswith(b'@prefix : <https://uri.etsi.org/ngsi-ld/>')


def test_a_vocabulary_that_does_not_load_fails_the_run(fresh, listener, tmp_path):
    url = listener.url + '/vocabulary.ttl'
    _vocabulary(fresh, url)
    result = CliRunner().invoke(cli, ['verify', '--tests', fresh])
    assert result.exit_code == 2
    assert f'tests do not run: the NGSI-LD vocabulary {url} did not load' in result.output
    assert listener.connections == 0
    out = str(tmp_path / 'p.kms.zip')
    refused = CliRunner().invoke(cli, ['publish', fresh, '-o', out])
    assert refused.exit_code == 2 and f'the NGSI-LD vocabulary {url} did not load' in refused.output

    allowed = CliRunner().invoke(cli, ['verify', '--tests', '--allow-network', fresh])
    assert allowed.exit_code == 0, allowed.output
    assert '/vocabulary.ttl' in listener.requests
    assert not os.path.exists(os.path.join(fresh, '.semforge', 'cache', 'deps'))


def test_a_shipped_vocabulary_that_fails_its_hash_fails_the_run(fresh, monkeypatch):
    import semforge.package.offline as offline_module
    name, digest = offline_module.PINNED_VOCABULARIES[OFFICIAL]
    _vocabulary(fresh, OFFICIAL, digest)
    monkeypatch.setitem(offline_module.PINNED_VOCABULARIES, OFFICIAL, (name, 'sha256:' + '0' * 64))
    with pytest.raises(PackageError, match=f'the NGSI-LD vocabulary {OFFICIAL} did not load'):
        run_tests(fresh)


def test_the_shipped_vocabulary_gives_the_networked_result(fresh):
    from semforge.package.offline import PINNED_VOCABULARIES
    _vocabulary(fresh, OFFICIAL, PINNED_VOCABULARIES[OFFICIAL][1])
    offline_run = _summary(run_tests(fresh))
    try:
        with urllib.request.urlopen(OFFICIAL, timeout=10) as response:
            response.read()
    except OSError:
        pytest.skip('the official NGSI-LD vocabulary cannot be fetched here')
    import semforge.package.offline as offline_module
    shipped = dict(offline_module.PINNED_VOCABULARIES)
    try:
        offline_module.PINNED_VOCABULARIES.clear()    # fetch it for real
        assert _summary(run_tests(fresh, allow_network=True)) == offline_run
    finally:
        offline_module.PINNED_VOCABULARIES.update(shipped)


@pytest.mark.parametrize('written', ['../outside.jsonld', 'ABSOLUTE'])
def test_examples_outside_the_package_are_refused(fresh, tmp_path, written):
    outside = tmp_path / 'outside.jsonld'
    good = os.path.join(fresh, 'examples', 'test_MachineShape', 'good')
    with open(os.path.join(good, 'running.jsonld'), encoding='utf-8') as handle:
        outside.write_text(handle.read(), encoding='utf-8')
    relative = str(outside) if written == 'ABSOLUTE' else \
        os.path.relpath(outside, good)
    path = os.path.join(good, 'expectations.yaml')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text.replace('running.jsonld', relative, 1))
    # The package check refuses it before the tests (since #940)...
    result = CliRunner().invoke(cli, ['verify', '--tests', fresh])
    assert result.exit_code == 2
    assert 'inside the package' in result.output or 'leaves the package' in result.output
    # ...and the test run itself refuses to read it, whoever calls it.
    with pytest.raises(PackageError, match='is outside the package'):
        run_tests(fresh)


def test_allow_network_does_not_read_the_user_s_cache(fresh, listener, monkeypatch, tmp_path):
    from semforge.package.context import fetch_context, user_context_cache
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    url = listener.url + '/extra.jsonld'
    fetch_context(url, user_context_cache())          # in the cache now
    seen = len(listener.requests)
    _model_context(fresh, url)
    allowed = CliRunner().invoke(cli, ['verify', '--tests', '--allow-network', fresh])
    assert allowed.exit_code == 0, allowed.output
    assert len(listener.requests) > seen             # fetched, not read from the cache


# --- second review of #1085: decide on what is parsed and opened ---------------------

_opened, _watching = [], []


def _watch(event, args):
    if _watching and event == 'open':
        _opened.append(str(args[0]))


@pytest.fixture
def opened():
    """Every path Python opens while the test runs, seen below the SDK."""
    if not getattr(sys, '_semforge_watch', False):
        sys.addaudithook(_watch)
        sys._semforge_watch = True
    _opened.clear()
    _watching.append(True)
    yield _opened
    _watching.clear()


@pytest.fixture
def canary(tmp_path):
    path = tmp_path / 'canary.jsonld'
    path.write_text('{"@context": {"canary": "https://example.org/canary"}}', encoding='utf-8')
    return str(path)


def _entity_context(root, context):
    path = os.path.join(root, 'model-instance.jsonld')
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    document[0]['@context'] = [document[0]['@context'], context]
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(document, handle)


def _verify(root, *flags):
    result = CliRunner().invoke(cli, ['verify', '--tests', *flags, root])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result


@pytest.mark.parametrize('flags', [[], [ALLOW]])
@pytest.mark.parametrize('form', [
    lambda url: url,
    lambda url: [[url]],
    lambda url: {'@version': 1.1, '@import': url},
    lambda url: {'@version': 1.1, 'x': {'@id': 'https://example.org/x', '@context': url}},
    lambda url: {'@version': 1.1, 'freshEntities:hasState': {
        '@id': 'https://example.org/x', '@context': [{}, url]}},
    lambda url: {'@version': 1.1, 'T': {'@id': 'https://example.org/T', '@context': url}},
], ids=['string', 'nested-list', 'import', 'term-scoped', 'term-scoped-list', 'type-scoped'])
def test_every_place_a_context_is_named_is_checked(fresh, canary, opened, form, flags):
    _entity_context(fresh, form('file://' + canary))
    # A term-scoped context is read where the term is used.
    path = os.path.join(fresh, 'model-instance.jsonld')
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    document[0]['x'] = {'@type': 'T', 'freshEntities:hasState': 1}
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(document, handle)
    result = _verify(fresh, *flags)
    assert result.exit_code == 2 and 'outside the package' in result.output
    assert canary not in opened


def test_a_context_file_names_another_context(fresh, canary, opened):
    """A context inside the package: read, and what it names is checked too."""
    inside = os.path.join(fresh, 'inside.jsonld')
    with open(inside, 'w', encoding='utf-8') as handle:
        json.dump({'@context': {'ok': 'https://example.org/ok'}}, handle)
    _entity_context(fresh, 'inside.jsonld')
    assert _verify(fresh).exit_code == 0
    with open(inside, 'w', encoding='utf-8') as handle:
        json.dump({'@context': ['../canary.jsonld']}, handle)
    result = _verify(fresh)
    assert result.exit_code == 2 and 'outside the package' in result.output
    assert canary not in opened


def test_a_link_or_a_pipe_is_not_a_context_file(fresh, canary, opened):
    os.symlink(canary, os.path.join(fresh, 'link.jsonld'))
    os.mkfifo(os.path.join(fresh, 'pipe.jsonld'))
    with offline(fresh):
        with pytest.raises(NetworkRefused, match='outside the package'):
            resolve_context('file://' + os.path.join(fresh, 'link.jsonld'))
        with pytest.raises(PackageError, match='not a regular file'):
            resolve_context('file://' + os.path.join(fresh, 'pipe.jsonld'))
    assert canary not in opened


def test_the_reviewed_spelling_of_a_path(fresh, canary, opened):
    # What urlparse takes for a fragment is part of the file name to rdflib.
    _entity_context(fresh, 'a#/%2e%2e/%2e%2e/canary.jsonld')
    result = _verify(fresh)
    assert result.exit_code == 2 and 'context' in result.output
    assert canary not in opened


def test_no_spelling_of_a_path_reads_outside(fresh, canary, opened, listener):
    """Random spellings: a document only from inside, and nothing else opened."""
    rand = random.Random(943)
    os.mkdir(os.path.join(fresh, 'sub'))
    targets = [canary, os.path.join(fresh, 'context.jsonld'),
               os.path.join(fresh, 'sub', '..', '..', 'canary.jsonld'),
               os.path.join(fresh, '..', 'fresh', 'context.jsonld')]

    def respelled(path):
        out, rate = [], rand.choice([.02, .15])
        for ch in path:
            roll = rand.random()
            if roll < rate:
                out.append(f'%{ord(ch):02x}' if roll < rate / 2 else f'%{ord(ch):02X}')
            elif ch == '/' and roll < 3 * rate:
                out.append(rand.choice(['//', '/./', '/sub/../', '/a#/../', '/a?b/../',
                                        '/%2e/', '/;x/..%2f', '/#/%2e%2e/', '/%23/../']))
            else:
                out.append(ch)
        return ''.join(out) + rand.choice(['', '', '', '', '#x', '?x', '%00', '\n', ' '])

    read = 0
    host = listener.url[len('http:'):]
    with offline(fresh) as scope:
        for _ in range(600):
            scheme = ''.join(rand.choice([c.lower(), c.upper()]) for c in 'file')
            prefix = rand.choice(['://'] * 9 + [':', ':/', ':///', '://localhost', ':' + host,
                                                ':\\\\', '%3a//'])
            source = rand.choice([''] * 9 + [' ', '\t', '\x00']) + scheme + prefix + \
                respelled(rand.choice(targets))
            try:
                document = resolve_context(source)
            except PackageError:
                continue
            read += 1
            assert 'canary' not in json.dumps(document), source
        assert scope.refusals
    assert read > 10                               # the test reads something
    outside = [p for p in opened if p.endswith('.jsonld')
               and not os.path.realpath(p).startswith(os.path.realpath(fresh) + os.sep)
               and 'ngsi-ld-core-context' not in p]
    assert outside == [] and listener.connections == 0


SPELLINGS = [
    'PREFIX ex: <http://a/> SELECT * { SERVICE ex:sparql { ?s ?p ?o } }',
    'PREFIX : <http://a/> SELECT * { SERVICE:sparql { ?s ?p ?o } }',
    'SELECT * { ?a ?b ?u FILTER(?b<2).SERVICE?u#> {\n{ ?s ?p ?o } }',
    "PREFIX ex: <http://a/> SELECT * { ?s ex:a\\'b ?o . SERVICE <http://a/> { ?s ?p ?o } #'\n }",
    'SELECT * { { SELECT * { ?x ?y ?z FILTER EXISTS { sErViCe SILENT<http://a/>{ } } } } }',
    'SELECT * { ?s ?p ?o MINUS { OPTIONAL { GRAPH ?g { SERVICE ?s { ?a ?b ?c } } } } }',
    'SELECT * { BIND(NOT EXISTS { SERVICE <http://a/> { ?a ?b ?c } } AS ?x) }',
    'SELECT (COUNT(?s) AS ?n) { ?s ?p ?o } HAVING(EXISTS { SERVICE <http://a/> { } })',
]


@pytest.mark.parametrize('text', SPELLINGS)
def test_service_in_any_spelling(fresh, text):
    assert len(services(text)) == 1 and not services(text)[0].startswith('prefix:')
    construct = 'CONSTRUCT { $this <urn:x> 1 } WHERE ' + text[text.index('{'):] \
        if text.startswith('SELECT *') else None
    if construct:
        literal = json.dumps(construct)            # a Turtle string, too
        _add_shapes(fresh, f"""
freshShacl:SpelledShape a sh:NodeShape ; sh:targetClass freshEntities:Machine ;
    sh:rule [ a sh:SPARQLRule ; sh:construct {literal} ] .
""")
        result = _verify(fresh, ALLOW)
        assert result.exit_code == 2
        assert 'freshShacl:SpelledShape (rule): uses SPARQL SERVICE' in result.output


def test_declared_prefixes_are_part_of_what_is_parsed(fresh, listener):
    """A namespace literal is put into the query text as it is."""
    _add_shapes(fresh, f"""
freshShacl:ns sh:declare [ sh:prefix "a" ; sh:namespace
    "http://a> CONSTRUCT {{ $this <urn:x> 1 }} WHERE {{ SERVICE <{listener.url}/sparql> {{ ?s ?p ?o }} }} #" ] .
freshShacl:InjectedShape a sh:NodeShape ; sh:targetClass freshEntities:Machine ;
    sh:rule [ a sh:SPARQLRule ; sh:prefixes freshShacl:ns ;
        sh:construct "CONSTRUCT {{ $this <urn:x> 1 }} WHERE {{ $this ?p ?o }}" ] .
""")
    result = _verify(fresh, ALLOW)
    assert result.exit_code == 2
    assert 'freshShacl:InjectedShape (rule)' in result.output
    assert listener.connections == 0


def test_a_path_in_a_constraint_is_parsed_as_run(fresh):
    _add_shapes(fresh, """
freshShacl:PathShape a sh:NodeShape ; sh:targetClass freshEntities:Machine ;
    sh:property [ sh:path freshEntities:never ;
        sh:sparql [ sh:select "SELECT $this ?value WHERE { $this $PATH/<urn:y> ?value }" ] ] .
""")
    assert _verify(fresh).exit_code == 0


def test_sparql_that_does_not_parse_is_refused(fresh):
    _add_shapes(fresh, """
freshShacl:BrokenShape a sh:NodeShape ; sh:targetClass freshEntities:Machine ;
    sh:rule [ a sh:SPARQLRule ; sh:construct "CONSTRUCT { $this <urn:x> } WHERE" ] .
""")
    result = _verify(fresh)
    assert result.exit_code == 2
    assert 'freshShacl:BrokenShape (rule): SPARQL that does not parse' in result.output


def test_a_swallowed_refusal_fails_the_run(fresh, listener, monkeypatch):
    """No scan, and a target evaluation that swallows what is raised in it."""
    import semforge.package.offline as offline_module
    monkeypatch.setattr(offline_module, 'refuse_services', lambda package: None)
    _add_shapes(fresh, f"""
freshShacl:TargetShape a sh:NodeShape ; sh:nodeKind sh:IRI ;
    sh:target [ a sh:SPARQLTarget ;
        sh:select "SELECT ?this WHERE {{ SERVICE <{listener.url}/sparql> {{ ?this ?p ?o }} }}" ] .
""")
    with pytest.raises((ServiceRefused, PackageError)):
        run_tests(fresh, allow_network=True)
    assert listener.connections == 0
    import semforge.package.releases as releases
    monkeypatch.setattr(releases, '_run_tests', lambda root: _swallow(listener.url))
    with pytest.raises(NetworkRefused, match='network access refused'):
        run_tests(fresh)


def _swallow(url):
    try:
        urllib.request.urlopen(url, timeout=5)
    except Exception:                              # noqa: BLE001 -- the point
        return None


def test_services_agree_with_the_algebra():
    """Random queries: what `services` finds is what rdflib would evaluate."""
    from rdflib.plugins.sparql import prepareQuery

    rand = random.Random(943)

    def word(text):
        return ''.join(rand.choice([c.lower(), c.upper()]) for c in text)

    def gap():
        return rand.choice(['', ' ', '\n', '\t', ' # SERVICE <x> {\n', '\n#"\n'])

    made = []

    def service():
        made.append(True)
        key = word('service')
        if rand.random() < .3:
            key = key.replace(key[1], f'\\u{ord(key[1]):04x}', 1)
        silent = rand.choice(['', ' ' + word('silent') + ' '])
        return key + gap() + silent + rand.choice(['<http://a/>', '?u', ':x', 'e:x']) + \
            gap() + '{' + gap() + group(2) + '}'

    def group(depth):
        parts = []
        for _ in range(rand.randint(0, 2)):
            parts.append(rand.choice([
                lambda: "?s e:a\\'b ?o ", lambda: '?s ?p "SERVICE <x> { }" ',
                lambda: "?s :service 'it' ", lambda: 'FILTER(?b<2)',
                lambda: 'BIND(1 AS ?v%d) ' % rand.randint(0, 99999),
                lambda: '?SERVICE ?p <http://SERVICE/> ',
                lambda: service() if rand.random() < .5 else '',
                lambda: '{' + group(depth + 1) + '}' if depth < 3 else '',
                lambda: 'OPTIONAL {' + group(depth + 1) + '}' if depth < 3 else '',
                lambda: 'FILTER EXISTS {' + group(depth + 1) + '}' if depth < 3 else '',
                lambda: '{ SELECT ?s {' + group(depth + 1) + '} }' if depth < 3 else '',
            ])())
        return (rand.choice([' . ', '.', ' ']) + gap()).join(p for p in parts if p)

    hits = parsed = 0
    for _ in range(250):
        made.clear()
        text = 'PREFIX : <http://d/> PREFIX e: <http://e/> SELECT * {' + gap() + group(0) + '}'
        try:
            query = prepareQuery(text)
        except Exception:                          # noqa: BLE001 -- not a query to rdflib
            continue
        parsed += 1
        expected = 'ServiceGraphPattern_' in repr(query.algebra)
        found = services(text)
        # Never less than the algebra. It may be more: rdflib's translation
        # drops a pattern of an EXISTS nested in another one; the text has it.
        assert found or not expected, text
        assert made or not found, text
        hits += expected
    assert parsed > 60 and hits > 8


# --- what a server may do to an allowed fetch ------------------------------------

def _remote_answer(listener, kind, path, status, headers, body, fresh):
    listener.answers[path] = (status, headers, body)
    if kind == 'context':
        _entity_context(fresh, listener.url + path)
    else:
        _vocabulary(fresh, listener.url + path)


CONTEXT = b'{"@context": {}}'


@pytest.mark.parametrize('kind', ['context', 'vocabulary'])
@pytest.mark.parametrize('scheme', ['ftp', 'file', 'FILE', 'data', 'gopher'])
def test_a_redirect_away_from_http_is_not_followed(fresh, listener, canary, opened, kind, scheme):
    other = _Listener()
    try:
        port = other.server.server_address[1]
        to = {'ftp': f'ftp://127.0.0.1:{port}/x', 'data': 'data:application/json,{}',
              'gopher': f'gopher://127.0.0.1:{port}/x'}.get(scheme, f'{scheme}://{canary}')
        _remote_answer(listener, kind, '/moved', 302, {'Location': to}, b'', fresh)
        result = _verify(fresh, ALLOW)
        assert result.exit_code == 2 and 'tests do not run' in result.output
        assert canary not in opened and other.connections == 0
    finally:
        other.close()


def test_a_redirect_to_http_is_followed_and_a_loop_is_not(fresh, listener):
    listener.answers['/there.jsonld'] = (200, {}, CONTEXT)
    _remote_answer(listener, 'context', '/moved', 302, {'Location': '/there.jsonld'}, b'', fresh)
    assert _verify(fresh, ALLOW).exit_code == 0
    listener.answers['/moved'] = (302, {'Location': '/moved'}, b'')
    result = _verify(fresh, ALLOW)
    assert result.exit_code == 2 and 'tests do not run' in result.output


def test_a_link_header_is_not_followed(fresh, listener, canary, opened):
    links = {'Content-Type': 'text/html', 'Link': f'<file://{canary}>; rel="alternate"; '
                                                  f'type="application/ld+json"'}
    _remote_answer(listener, 'context', '/linked', 200, links, CONTEXT, fresh)
    assert _verify(fresh, ALLOW).exit_code == 0      # the document itself, whatever its type
    assert canary not in opened


@pytest.mark.parametrize('status, body', [
    (404, b'gone'), (500, b''), (200, b'<html>'), (200, b'{"no": "context"}'),
    (200, b'7'), (200, b'\xff\xfe'), (200, b'[' * 100000)])
@pytest.mark.parametrize('command', ['verify', 'publish'])
def test_a_context_that_is_none_is_reported(fresh, listener, tmp_path, command, status, body):
    _remote_answer(listener, 'context', '/odd', status, {}, body, fresh)
    out = str(tmp_path / 'p.kms.zip')
    args = ['verify', '--tests', ALLOW, fresh] if command == 'verify' else \
        ['publish', fresh, '-o', out, ALLOW]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 2 and isinstance(result.exception, SystemExit)
    assert 'tests do not run: ' in result.output and not os.path.exists(out)


@pytest.mark.parametrize('context', ['http://[', 'http://127.0.0.1:port/', 'missing.jsonld',
                                     'file:///%00', 'http://a b/', 'sub'])
@pytest.mark.parametrize('flags', [[], [ALLOW]])
def test_a_context_url_that_is_none_is_reported(fresh, context, flags):
    os.mkdir(os.path.join(fresh, 'sub'))
    _entity_context(fresh, context)
    result = _verify(fresh, *flags)
    assert result.exit_code == 2 and 'tests do not run: ' in result.output


def test_an_answer_without_end_is_cut_off(fresh, listener, monkeypatch):
    import semforge.package.offline as offline_module
    monkeypatch.setattr(offline_module, 'FETCH_LIMIT', 1000)
    _remote_answer(listener, 'context', '/big', 200, {}, b'{"@context": {}}' + b' ' * 5000, fresh)
    result = _verify(fresh, ALLOW)
    assert result.exit_code == 2 and 'larger than 1000 bytes' in result.output
    monkeypatch.setattr(offline_module, 'FETCH_LIMIT', 10 ** 6)
    monkeypatch.setattr(offline_module, 'FETCH_TIMEOUT', 0.0001)
    assert _verify(fresh, ALLOW).exit_code == 2


def test_what_is_not_the_tests_fault_is_not_swallowed(fresh, monkeypatch):
    import semforge.package.releases as releases

    def stop(root):
        raise KeyboardInterrupt
    monkeypatch.setattr(releases, '_run_tests', stop)
    with pytest.raises(KeyboardInterrupt):
        run_tests(fresh)

    def broken(root):
        raise ZeroDivisionError('by zero\nmore')
    monkeypatch.setattr(releases, '_run_tests', broken)
    with pytest.raises(PackageError, match='^ZeroDivisionError: by zero$'):
        run_tests(fresh)


def test_a_fetched_vocabulary_is_not_written_anywhere(fresh, listener, monkeypatch, tmp_path):
    import hashlib
    import tempfile
    shared = tmp_path / 'shared'
    shared.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(shared))
    with open(NGSILD_TTL, 'rb') as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    # Somebody else's file, where the first version kept the bytes.
    planted = shared / f'semforge-fetched-{digest}.ttl'
    planted.mkdir()
    _vocabulary(fresh, listener.url + '/vocabulary.ttl', 'sha256:' + digest)
    result = _verify(fresh, ALLOW)
    assert result.exit_code == 0, result.output
    assert [p.name for p in shared.iterdir()] == [planted.name]


def test_the_environment_does_not_choose_the_vocabulary(fresh, monkeypatch):
    from semforge.ngsild.vocabulary import for_package, source_for
    path = os.path.join(fresh, 'kms.yaml')
    with open(path, encoding='utf-8') as handle:
        lines = handle.read().split('\n')
    start = lines.index('ngsild:')
    del lines[start:start + 2]
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))
    monkeypatch.setenv('SEMFORGE_NGSILD', '/nowhere/ngsild.ttl')
    assert source_for(fresh).source == '/nowhere/ngsild.ttl'
    with offline(fresh):
        assert source_for(fresh).source == OFFICIAL
        assert len(for_package(fresh)) > 0


def test_a_vocabulary_file_outside_the_package_is_refused(fresh):
    _vocabulary(fresh, NGSILD_TTL)
    with pytest.raises(PackageError, match='is outside the package'):
        run_tests(fresh)
