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

"""A SPARQL constraint's sh:message: edited in the workbench, filled from a
row, and checked against the query and what the platform makes of it."""

import html as entities
import json
import os
import re
import shutil
import sqlite3
import subprocess
from unittest import mock

import headless_chromium
import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import SH

from semforge.cooked import sparqlbench as sb
from semforge.errors import PackageError
from semforge.package import load
from semforge.sanity import sanity
from semforge.sparql.message import check, fill, placeholders, variables

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')
BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
CUTTER = BASE + 'StateOnCutterShape'
UNTIL = BASE + 'TimestampCartridgeUntilRulesShape'
OFF = 'test_StateOnCutterShape/bad/filter-off.jsonld'
SAYS = 'Cutter running without running filter'
PACKAGE = 'file:///pkg/shacl.ttl'


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False, ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _rewrite(kms, old, new):
    path = os.path.join(kms, 'shacl.ttl')
    text = open(path).read()
    assert text.count(old) == 1, old
    with open(path, 'w') as handle:
        handle.write(text.replace(old, new))


def _written(kms):
    graph = Graph().parse(os.path.join(kms, 'shacl.ttl'))
    return [m for h in graph.objects(URIRef(CUTTER), SH.sparql) for m in graph.objects(h, SH.message)]


# --- filling, and what a query selects ------------------------------------------------------

def test_filled_by_name_with_its_case_and_unfilled_as_text():
    row = {'this': 'urn:a', 'V': '3'}
    assert fill('{$this}: {?V} of {?v}, {?}', row) == 'urn:a: 3 of {?v}, {?}'
    assert fill('', row) == fill(None, row) == ''
    assert placeholders('{?b} {$a} {?b}') == ['b', 'a']


@pytest.mark.parametrize('query, known', [
    ('SELECT ?v $this WHERE { $this ?p ?v }', ['this', 'v']),
    ('SELECT * WHERE { $this ?p ?v }', ['this', 'p', 'v']),
    ('SELECT $this (COUNT(?v) AS ?n) WHERE { $this ?p ?v } GROUP BY $this', ['this', 'n']),
    ('SELECT $this WHERE { $this ex:p ?v }', ['this']),
    ('SELECT $this WHERE {', None),
    ('CONSTRUCT { $this ?p ?v } WHERE { $this ?p ?v }', None)])
def test_what_a_query_selects_is_what_the_parser_says(query, known):
    found = variables(query, ['PREFIX ex: <urn:ex:>'])
    assert (found and (found[0], sorted(found))) == (known and (known[0], sorted(known)))


@pytest.mark.parametrize('message, known, codes', [
    ('fine {$this} {?v}', ['this', 'v'], []),
    ('{?x}', ['this'], ['message-variable']),
    ('{?This}', ['this'], ['message-variable']),
    ('{?}', ['this'], ['message-variable']),
    ('{v}', ['this', 'v'], ['message-variable']),
    ('{v}', ['this'], []),
    ('{?x}', None, []),
    ('it\'s', [], ['message-apostrophe']),
    ('it’s', [], []),
    (' ', [], ['message-missing'])])
def test_what_is_wrong_in_a_message(message, known, codes):
    assert [p.code for p in check(message, known)] == codes


def test_a_case_that_differs_is_named():
    assert '{?this} is' in check('{?This}', ['this'])[0].message


# --- saving ---------------------------------------------------------------------------------

def test_a_message_is_changed_and_nothing_else(kms):
    path = os.path.join(kms, 'shacl.ttl')
    before = open(path).read()
    done = sb.save_message(load(kms), CUTTER, 0, 'Off: {?f} of {$this}', SAYS)
    assert open(path).read() == before.replace(f'"{SAYS}"', '"Off: {?f} of {$this}"')
    assert 'Off: {?f}' in open(path).read().splitlines()[done['line'] - 1]
    assert sb.holders(load(kms), CUTTER)[0]['message'] == 'Off: {?f} of {$this}'


@pytest.mark.parametrize('message', [
    'a "quoted" \\ back\\n slash', 'two\nlines\r\n\tand a tab', 'grüße 😀 \x07', "it's", ' padded ',
    'sh:message "x" ; ] .', '"""', '# no comment', '\\'])
def test_any_text_survives_and_can_be_changed_again(kms, message):
    sb.save_message(load(kms), CUTTER, 0, message, SAYS)
    assert [str(m) for m in _written(kms)] == [message]
    assert sb.holders(load(kms), CUTTER)[0]['message'] == message
    sb.save_message(load(kms), CUTTER, 0, SAYS, message)
    assert [str(m) for m in _written(kms)] == [SAYS]


def test_emptied_it_is_removed_and_can_be_added(kms):
    path = os.path.join(kms, 'shacl.ttl')
    sb.save_message(load(kms), CUTTER, 0, '  ', SAYS)
    assert _written(kms) == [] and SAYS not in open(path).read()
    holder = sb.holders(load(kms), CUTTER)[0]
    assert holder['message'] == '' and holder['severity'] == 'base:severityCritical'
    sb.save_message(load(kms), CUTTER, 0, '', '')                  # nothing to remove
    sb.save_message(load(kms), CUTTER, 0, SAYS, '', holder['query'])
    assert [str(m) for m in _written(kms)] == [SAYS]
    lines = open(path).read().splitlines()
    at = next(i for i, line in enumerate(lines) if SAYS in line)
    select = next(line for line in lines[at:] if 'sh:select' in line)
    assert lines[at].index('sh:message') == select.index('sh:select'), 'indented as the query'


@pytest.mark.parametrize('written', [
    '"""{}"""', "'{}'", '"{}"@en', '"{}"^^xsd:string', '"{}" # why "this"; ]\n'])
def test_however_it_is_written(kms, written):
    _rewrite(kms, f'"{SAYS}"', written.format(SAYS))
    before = _written(kms)[0]
    sb.save_message(load(kms), CUTTER, 0, 'New {$this}', SAYS)
    (after,) = _written(kms)
    assert str(after) == 'New {$this}' and after.language == before.language
    sb.save_message(load(kms), CUTTER, 0, '', 'New {$this}')
    assert _written(kms) == []


def test_on_one_line_first_last_and_behind_an_iri_with_a_hash(kms):
    with open(os.path.join(kms, 'shacl.ttl'), 'a') as handle:
        handle.write('\n<urn:S> a sh:NodeShape ; sh:sparql [ sh:select "SELECT $this WHERE { $this a <urn:a> }" ; '
                     'sh:message "one" ] ; sh:sparql [ sh:message "two" ; <urn:x#y> <urn:z#q> ;\n '
                     'sh:select "SELECT $this WHERE { $this a <urn:b> }" ] ; '
                     'sh:sparql [ sh:select "SELECT $this WHERE { $this a <urn:c> }" ] .\n')
    for index, expected in enumerate(['one', 'two', '']):
        sb.save_message(load(kms), 'urn:S', index, f'new {index}', expected)
    assert [h['message'] for h in sb.holders(load(kms), 'urn:S')] == ['new 0', 'new 1', 'new 2']
    for index in range(3):
        sb.save_message(load(kms), 'urn:S', index, '', f'new {index}')
    assert [h['message'] for h in sb.holders(load(kms), 'urn:S')] == ['', '', '']


@pytest.mark.parametrize('values, why', [
    ('"a"@en , "b"@de', 'has 2 sh:message values'),
    ('"a" ; sh:message "b"', 'has 2 sh:message values'),
    ('<urn:x>', 'not a text')])
def test_what_cannot_be_told_apart_is_refused(kms, values, why):
    _rewrite(kms, f'"{SAYS}"', values)
    path = os.path.join(kms, 'shacl.ttl')
    before = open(path).read()
    holder = sb.holders(load(kms), CUTTER)[0]
    assert why in holder['messageLocked']
    with pytest.raises(PackageError, match=why):
        sb.save_message(load(kms), CUTTER, 0, 'x', holder['message'])
    assert open(path).read() == before


def test_an_empty_message_is_given_a_text(kms):
    _rewrite(kms, f'"{SAYS}"', '""')
    holder = sb.holders(load(kms), CUTTER)[0]
    assert holder['message'] == '' and holder['messageLocked'] == ''
    sb.save_message(load(kms), CUTTER, 0, 'Off {?f}', '')
    assert [str(m) for m in _written(kms)] == ['Off {?f}']


def test_a_message_edited_in_the_ttl_is_said_so_everywhere(kms):
    from semforge.cooked.shapepage import _checks
    from semforge.cooked.typepage import _rule_message

    assert _rule_message(load(kms), CUTTER) == {'hasMessage': True, 'messageLocked': ''}
    _rewrite(kms, f'"{SAYS}"', '<urn:x>')
    package = load(kms)
    (check,) = [c for c in _checks(package, URIRef(CUTTER)) if c['kind'] == 'constraint']
    assert 'not a text' in check['messageLocked']
    row = _rule_message(package, CUTTER)          # the type page's row; pyshacl refuses to validate it
    assert 'not a text' in row['messageLocked'] and row['hasMessage'] is False
    assert sb.bench_page(package, CUTTER)['message']['warnings'] == [], 'no "it has no sh:message"'
    holder = sb.holders(package, CUTTER)[0]
    assert sb.run_query(package, CUTTER, 0, OFF, holder['query'])['message']['warnings'] == []


def test_without_a_target_class_the_workbench_says_no_missing_message(kms):
    _rewrite(kms, f'sh:message "{SAYS}" ;', '')
    assert sb.bench_page(load(kms), CUTTER)['message']['warnings'], 'with a target class: said'
    end = '?v2 != base:state_ON)\n    }\n        \"\"\" ;\n            sh:severity base:severityCritical ]'
    _rewrite(kms, end + ' ;\n    sh:targetClass iffBaseEntities:Cutter .', end + ' .')
    package = load(kms)
    assert sb.bench_page(package, CUTTER)['message']['warnings'] == []
    holder = sb.holders(package, CUTTER)[0]
    assert sb.check_message(package, CUTTER, 0, holder['query'], '')['warnings'] == []
    assert not [f for f in sanity(package) if f.code == 'message-missing']


def test_a_message_under_another_prefix_is_refused(kms):
    _rewrite(kms, f'sh:message "{SAYS}"', f'<{SH.message}> "{SAYS}"')
    with pytest.raises(PackageError, match='cannot be edited here'):
        sb.save_message(load(kms), CUTTER, 0, 'x', '')


@pytest.mark.parametrize('arguments, why', [
    ((0, 'x', 'something else'), 'the message changed in the file'),
    ((0, 'x', SAYS, 'SELECT $this {}'), 'the query changed in the file'),
    ((7, 'x', SAYS), 'no such SPARQL query'),
    ((0, 'x \ud800', SAYS), 'lone surrogate')])
def test_a_save_that_does_not_fit_the_file_writes_nothing(kms, arguments, why):
    path = os.path.join(kms, 'shacl.ttl')
    before = open(path).read()
    with pytest.raises(PackageError, match=why):
        sb.save_message(load(kms), CUTTER, *arguments)
    assert open(path).read() == before


def test_a_rule_has_no_message(kms):
    with pytest.raises(PackageError, match='a SPARQL rule'):
        sb.save_message(load(kms), UNTIL, 0, 'x', '')
    assert sb.holders(load(kms), UNTIL)[0]['messageLocked'] == ''
    assert sb.bench_page(load(kms), UNTIL)['message'] is None


@pytest.mark.parametrize('broken, why', [
    (lambda v: '"other"', 'did not survive'), (lambda v: '"open', 'did not survive')])
def test_a_write_that_would_go_wrong_is_not_made(kms, broken, why):
    path = os.path.join(kms, 'shacl.ttl')
    before = open(path).read()
    with mock.patch.object(sb, '_turtle_string', broken), pytest.raises(PackageError, match=why):
        sb.save_message(load(kms), CUTTER, 0, 'x', SAYS)
    assert open(path).read() == before


def test_validation_reports_the_new_message_as_the_workbench_fills_it(kms):
    from semforge.cooked.casepage import _find_case
    from semforge.expect.store import compose
    from semforge.validate.orchestrator import validate_graphs

    sb.save_message(load(kms), CUTTER, 0, 'Off: {$this} {?V2} {?nope}', SAYS)
    package = load(kms)
    holder = sb.holders(package, CUTTER)[0]
    run = sb.run_query(package, CUTTER, 0, OFF, holder['query'])
    (said,) = run['focus'][0]['messages']
    assert said == 'Off: urn:plasmacutter:1 {?V2} {?nope}'
    report = validate_graphs(compose(package, _find_case(package, OFF)), package.shapes,
                             package.knowledge, strict=False)
    assert [r.message for r in report.violations if str(r.shape) == CUTTER] == [said]


# --- warnings -------------------------------------------------------------------------------

def test_a_run_says_what_the_message_may_name_and_what_does_not_fit(kms):
    sb.save_message(load(kms), CUTTER, 0, 'Off {?f}', SAYS)
    package = load(kms)
    query = sb.holders(package, CUTTER)[0]['query']
    assert sb.bench_page(package, CUTTER)['message'] == {
        'variables': ['this', 'v1', 'f', 'v2'], 'warnings': []}
    run = sb.run_query(package, CUTTER, 0, sb.MAIN, query.replace('?f ?v2\n', '?v2\n', 1)
                       if '?f ?v2\n' in query else re.sub(r'SELECT[^{]*', 'SELECT $this ', query, count=1))
    assert 'f' not in run['message']['variables']
    assert any('{?f} is not a variable the query selects' in w for w in run['message']['warnings'])
    drafted = sb.check_message(package, CUTTER, 0, query, 'it\'s {?F}')
    assert len(drafted['warnings']) == 2 and drafted['variables'][0] == 'this'


def test_check_and_the_problems_panel_say_it_on_its_line(kms):
    def found():
        return {f.code: f for f in sanity(load(kms)) if f.code.startswith('message-')}

    assert found() == {}, 'the kms itself is clean'
    sb.save_message(load(kms), CUTTER, 0, 'It\'s {?nope}', SAYS)
    now = found()
    assert sorted(now) == ['message-apostrophe', 'message-variable']
    finding = now['message-variable']
    assert finding.severity == 'warning' and '{?nope}' in finding.message
    assert 'nope' in open(finding.file).read().splitlines()[finding.line - 1]
    sb.save_message(load(kms), CUTTER, 0, '', 'It\'s {?nope}')
    now = found()
    assert list(now) == ['message-missing']
    assert 'sh:select' in open(now['message-missing'].file).read().splitlines()[now['message-missing'].line - 1]


def test_check_prints_it(kms):
    from click.testing import CliRunner

    from semforge.cli.main import check_command

    sb.save_message(load(kms), CUTTER, 0, 'Off {?nope}', SAYS)
    result = CliRunner().invoke(check_command, [kms])
    assert 'message-variable' in result.output


def test_a_message_written_where_it_cannot_be_found_is_on_the_shape(kms):
    _rewrite(kms, f'sh:message "{SAYS}"', f'<{SH.message}> "{{?nope}}"')
    (finding,) = [f for f in sanity(load(kms)) if f.code == 'message-variable']
    assert finding.line > 1


def test_the_query_editor_says_when_the_message_no_longer_fits(kms):
    from semforge.editor.sparqldocs import Context, _message_fits

    def said(text, message='Off {?f}'):
        return _message_fits(text, Context(None, CUTTER, 'constraint', 'current', [], None, message))

    (found,) = said('# SELECT\nSELECT $this WHERE { $this ?p ?f }')
    assert found.code == 'message-variable' and 'does not fit this query' in found.message
    assert (found.range.start.line, found.range.start.character) == (1, 0)
    assert said('SELECT $this ?f WHERE { $this ?p ?f }') == []
    assert said('SELECT $this WHERE {') == [] and said('SELECT $this WHERE {}', None) == []


def test_the_select_says_only_what_the_query_no_longer_selects():
    from semforge.editor.sparqldocs import Context, _message_fits

    def said(message):
        return _message_fits('SELECT $this ?f WHERE { $this ?p ?f }',
                             Context(None, CUTTER, 'constraint', 'current', [], None, message))

    assert said('Off {?} {f}') == [], 'no edit of the query repairs these'
    (found,) = said('Off {?} {f} {?gone}')
    assert '{?gone}' in found.message


def test_the_query_document_knows_its_message(kms):
    import base64

    from semforge.editor import sparqldocs

    sb.save_message(load(kms), CUTTER, 0, 'Off {?f}', SAYS)
    ref = base64.urlsafe_b64encode(json.dumps(
        {'p': f'file://{kms}/shacl.ttl', 's': CUTTER, 'h': 0, 'k': 'constraint'}).encode()).decode()
    ctx = sparqldocs.context(f'semforge-sparql:/x.rq?{ref}', load, lambda path: kms, lambda uri: uri)
    assert ctx.message == 'Off {?f}'
    assert any(d.code == 'message-variable' for d in sparqldocs.diagnostics(
        'SELECT $this WHERE { $this ?p ?f }', ctx))


# --- what the platform does: shacl2flink itself -----------------------------------------------

def _compiled(message):
    """The SQL text of one message as shacl2flink writes it."""
    path = os.path.join(os.path.dirname(SDK), 'shacl2flink', 'lib', 'shacl_sparql_to_sql.py')
    source = open(path).read()
    body = re.search(r'^def add_variables_to_message.*?(?=^def )', source, re.S | re.M).group(0)
    scope = {'re': re}
    exec(body, scope)                              # the function alone: no Flink dependencies
    return f"SELECT '{scope['add_variables_to_message'](message)}' FROM (SELECT 1 AS this, 2 AS v)"


@pytest.mark.parametrize('message, fits', [
    ('{?v} of {$this}', True), ('{?x}', False), ('{?}', False), ('it\'s', False),
    ('it’s', True), ('{v} {? v}', True), ('a \\ "b"\n;', True)])
def test_what_is_warned_about_is_what_the_platform_cannot_run(message, fits):
    run = sqlite3.connect(':memory:')
    if fits:
        run.execute(_compiled(message))
    else:
        with pytest.raises(sqlite3.Error):
            run.execute(_compiled(message))
    warned = {p.part for p in check(message, ['this', 'v'])} - {'{v}', '{? v}'}
    assert bool(warned) is not fits


# --- the server --------------------------------------------------------------------------------

def test_the_server_saves_and_checks(kms):
    from semforge.editor import edits, validation, views

    uri = f'file://{kms}/shacl.ttl'
    query = sb.holders(load(kms), CUTTER)[0]['query']
    with mock.patch.object(validation, 'publish') as publish:
        ls = mock.MagicMock()
        done = edits.sparql_save_message_feature(ls, {
            'uri': uri, 'shape': CUTTER, 'message': 'Off {?f}', 'expected': SAYS, 'query': query})
        assert done['ok'] and done['message'] == 'Off {?f}' and publish.called
        again = edits.sparql_save_message_feature(ls, {
            'uri': uri, 'shape': CUTTER, 'index': 0, 'message': 'x', 'expected': SAYS})
        assert not again['ok'] and 'changed in the file' in again['error']
    page = views.sparql_bench_feature(None, {'uri': uri, 'shape': CUTTER})
    assert page['holder']['message'] == 'Off {?f}'
    checked = views.sparql_message_feature(None, {
        'uri': uri, 'shape': CUTTER, 'query': query, 'message': '{?no}'})
    assert checked['ok'] and len(checked['warnings']) == 1
    assert not views.sparql_message_feature(None, {'uri': uri, 'shape': 'urn:no'})['ok']
    assert not views.sparql_message_feature(None, {'uri': 'file:///nowhere/x.ttl'})['ok']


def test_the_shape_and_type_page_show_the_new_message(kms):
    from semforge.cooked.shapepage import build_shape_page
    from semforge.cooked.typepage import PENDING, build_type_page

    sb.save_message(load(kms), CUTTER, 0, 'Off {?f}', SAYS)
    package = load(kms)
    assert [c['message'] for c in build_shape_page(package, CUTTER, PENDING)['checks']] == ['Off {?f}']
    rules = build_type_page(package, 'iffBaseEntities:Cutter', PENDING)['rules']
    assert next(r['text'] for r in rules if r['shape'] == CUTTER) == 'Off {?f}'


# --- the extension --------------------------------------------------------------------------------

@pytest.fixture(scope='module')
def page(corpus):
    return dict(sb.bench_page(corpus, CUTTER, 0, sb.MAIN), ok=True)


def _drive(tmp_path, scenario, target='extension.js'):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    result = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, target), str(path)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-1500:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def _open(tmp_path, page, messages, args=(), **scenario):
    replies = {'semforge/sparqlBench': page, 'semforge/sparqlRun': {'ok': True},
               'semforge/sparqlQuery': dict(page['holder'], ok=True)}
    replies.update(scenario.pop('replies', {}))
    return _drive(tmp_path, dict({
        'command': 'semforge.openSparqlBench', 'args': list(args),
        'node': {'raw': {'shape': CUTTER}, 'packageUri': PACKAGE},
        'webviewMessages': messages, 'replies': replies}, **scenario))


def _asked(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


def test_saving_asks_the_server_and_draws_the_page_anew(tmp_path, page):
    new = json.loads(json.dumps(page))
    new['holder']['message'] = 'Off {?f}'
    seen = _open(tmp_path, page, [{'command': 'saveMessage', 'message': 'Off {?f}', 'expected': SAYS}],
                 replies={'semforge/sparqlBench': [page, new],
                          'semforge/sparqlSaveMessage': {'ok': True, 'message': 'Off {?f}'}})
    assert _asked(seen, 'semforge/sparqlSaveMessage') == [{
        'uri': PACKAGE, 'shape': CUTTER, 'index': 0, 'message': 'Off {?f}', 'expected': SAYS,
        'query': page['holder']['query']}]
    html = seen['webviews'][0]['html']
    assert len(html) == 2 and '“Off {?f}”' in html[1]
    assert any(e['command'] == 'semforge.refreshShapes' for e in seen['executed'])
    assert any('message of StateOnCutterShape saved' in m for m in seen['messages'])


def test_a_refused_save_stays_in_the_field(tmp_path, page):
    seen = _open(tmp_path, page, [{'command': 'saveMessage', 'message': 'x', 'expected': SAYS}],
                 replies={'semforge/sparqlSaveMessage': {'ok': False, 'error': 'it changed'}})
    assert seen['webviews'][0]['posted'] == [{'type': 'messageError', 'text': 'Not saved: it changed'}]
    assert len(seen['webviews'][0]['html']) == 1


@pytest.mark.parametrize('answer', ['Remove message', None])
def test_emptying_asks_and_says_what_the_platform_does(tmp_path, page, answer):
    seen = _open(tmp_path, page, [{'command': 'saveMessage', 'message': ' ', 'expected': SAYS}],
                 answer=answer, replies={'semforge/sparqlSaveMessage': {'ok': True, 'message': ''}})
    warning = next(w for w in seen['warnings'] if w.startswith('Remove the message'))
    assert 'The platform then does not check this constraint' in warning
    assert len(_asked(seen, 'semforge/sparqlSaveMessage')) == (1 if answer else 0)
    if not answer:
        assert seen['webviews'][0]['posted'] == [{'type': 'messageError', 'text': ''}]


def test_a_draft_is_checked_over_the_editor_s_text(tmp_path, page):
    answer = {'ok': True, 'variables': ['this'], 'warnings': ['w']}
    seen = _open(tmp_path, page, [{'command': 'checkMessage', 'message': '{?x}'}],
                 replies={'semforge/sparqlMessage': answer})
    (asked,) = _asked(seen, 'semforge/sparqlMessage')
    assert asked['message'] == '{?x}' and asked['query'].strip() == page['holder']['query'].strip()
    assert seen['webviews'][0]['posted'] == [dict(answer, type='messageCheck', message='{?x}')]


def test_the_workbench_menu_opens_the_field(tmp_path, page):
    seen = _open(tmp_path, page, [{'command': 'menu'}], picks=['$(comment) Edit message…'])
    html = seen['webviews'][0]['html']
    assert '"editMessage":false' in html[0] and '"editMessage":true' in html[1]


def test_the_shape_page_opens_the_workbench_at_the_message(tmp_path, corpus):
    from semforge.cooked.shapepage import build_shape_page

    shape_page = dict(build_shape_page(corpus, CUTTER), ok=True)
    for message, messages, picks in (
            (SAYS, [{'command': 'checkMenu', 'row': 0}], ['$(comment) Edit message…']),
            ('', [{'command': 'checkMenu', 'row': 0}], ['$(comment) + Message…']),
            ('', [{'command': 'checkMessage', 'row': 0}], [])):
        shape_page['checks'][0]['message'] = message
        seen = _drive(tmp_path, {
            'command': 'semforge.openShapePage',
            'node': {'raw': {'shape': CUTTER}, 'packageUri': PACKAGE},
            'webviewMessages': messages, 'picks': picks,
            'replies': {'semforge/shapePage': shape_page}})
        assert ('data-action="checkMessage"' in seen['webviews'][0]['html'][0]) == (not message)
        (opened,) = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openSparqlBench']
        assert opened[1] == {'query': shape_page['checks'][0]['query'], 'kind': 'constraint',
                             'editMessage': True}


def test_the_type_page_opens_the_workbench_at_the_message(tmp_path, corpus):
    from semforge.cooked.typepage import build_type_page

    type_page = dict(build_type_page(corpus, 'iffBaseEntities:Cutter'), ok=True)
    row = next(i for i, r in enumerate(type_page['rules']) if r['shape'] == CUTTER)
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'targetClass': type_page['iri'], 'children': []},
                 'packageUri': PACKAGE},
        'webviewMessages': [{'command': 'ruleMenu', 'row': row}], 'picks': ['$(comment) Edit message…'],
        'replies': {'semforge/typePage': type_page}})
    (opened,) = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openSparqlBench']
    assert opened[1] == {'kind': 'constraint', 'editMessage': True}


def test_a_rule_s_menus_offer_no_message(tmp_path, corpus):
    from semforge.cooked.shapepage import build_shape_page
    from semforge.cooked.typepage import build_type_page

    shape_page = dict(build_shape_page(corpus, CUTTER), ok=True)
    shape_page['checks'][0].update(kind='rule', message='')
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage', 'node': {'raw': {'shape': CUTTER}, 'packageUri': PACKAGE},
        'webviewMessages': [{'command': 'checkMenu', 'row': 0}], 'picks': [],
        'replies': {'semforge/shapePage': shape_page}})
    labels = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert labels and not [label for label in labels if 'essage' in label]
    assert 'data-action="checkMessage"' not in seen['webviews'][0]['html'][0]

    type_page = dict(build_type_page(corpus, 'iffBaseEntities:Cutter'), ok=True)
    row = next(i for i, r in enumerate(type_page['rules']) if r['shape'] == CUTTER)
    type_page['rules'][row]['kind'] = 'rule'
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'targetClass': type_page['iri'], 'children': []},
                 'packageUri': PACKAGE},
        'webviewMessages': [{'command': 'ruleMenu', 'row': row}], 'picks': [],
        'replies': {'semforge/typePage': type_page}})
    labels = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert '$(beaker) Open in SPARQL workbench' in labels
    assert not [label for label in labels if 'essage' in label]


def test_a_locked_or_missing_message_is_offered_as_it_is(tmp_path, corpus):
    from semforge.cooked.shapepage import build_shape_page
    from semforge.cooked.typepage import build_type_page

    shape_page = dict(build_shape_page(corpus, CUTTER), ok=True)
    shape_page['checks'][0].update(message='', messageLocked='its sh:message is not a text.')
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage', 'node': {'raw': {'shape': CUTTER}, 'packageUri': PACKAGE},
        'webviewMessages': [{'command': 'checkMenu', 'row': 0}], 'picks': [],
        'replies': {'semforge/shapePage': shape_page}})
    assert 'data-action="checkMessage"' not in seen['webviews'][0]['html'][0]
    labels = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert '$(warning) Severity…' in labels and not [label for label in labels if 'essage' in label]

    type_page = dict(build_type_page(corpus, 'iffBaseEntities:Cutter'), ok=True)
    row = next(i for i, r in enumerate(type_page['rules']) if r['shape'] == CUTTER)
    for change, offered in (({'messageLocked': 'it has 2 sh:message values'}, []),
                            ({'hasMessage': False, 'text': 'Cutter checks'}, ['$(comment) + Message…'])):
        rules = json.loads(json.dumps(type_page['rules']))
        rules[row].update(change)
        seen = _drive(tmp_path, {
            'command': 'semforge.openTypePage',
            'node': {'raw': {'kind': 'type', 'targetClass': type_page['iri'], 'children': []},
                     'packageUri': PACKAGE},
            'webviewMessages': [{'command': 'ruleMenu', 'row': row}], 'picks': [],
            'replies': {'semforge/typePage': dict(type_page, rules=rules)}})
        labels = [i['label'] for i in seen['quickPicks'][0]['items']]
        assert [label for label in labels if 'essage' in label] == offered, labels


def test_opened_at_the_message_the_page_starts_editing(tmp_path, page):
    seen = _open(tmp_path, page, [], args=[{'editMessage': True}])
    assert '"editMessage":true' in seen['webviews'][0]['html'][0]


# --- the page's script, in a browser ---------------------------------------------------------------

STUB = '''<script nonce="n1">function acquireVsCodeApi() {
  var root = document.documentElement.dataset;
  return { getState() { return JSON.parse(root.state || 'null') || undefined; },
    setState(s) { root.state = JSON.stringify(s); },
    postMessage(m) { var all = JSON.parse(root.posted || '[]'); all.push(m); root.posted = JSON.stringify(all); } };
}
function say(m) { window.dispatchEvent(new MessageEvent('message', { data: m })); }
function type(text) { var f = document.getElementById('messagetext');
  f.value = text; f.setSelectionRange(text.length, text.length); f.dispatchEvent(new Event('input')); }
function key(k, more) { document.getElementById('messagetext').dispatchEvent(
  new KeyboardEvent('keydown', Object.assign({ key: k, cancelable: true }, more))); }
function click(id) { document.getElementById(id).click(); }
</script>'''


def _browse(tmp_path, page, after, edit=False, state=None):
    html = _drive(tmp_path, {'mode': 'render', 'function': 'renderSparqlBench', 'payload': page,
                             'options': {'nonce': 'n1', 'editMessage': edit}}, 'sparqlpage.js')['html']
    html = re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]*>', '', html)
    if state:
        html = html.replace('<html ', f'<html data-state="{entities.escape(json.dumps(state))}" ', 1)
    html = html.replace('<body>', '<body>' + STUB, 1).replace(
        '</body>', '<script>' + after + '</script></body>')
    path = tmp_path / 'page.html'
    path.write_text(html)
    dom = subprocess.run([headless_chromium.chrome(), '--headless=new', '--no-sandbox', '--disable-gpu',
                          '--virtual-time-budget=3000', '--dump-dom', f'file://{path}'],
                         capture_output=True, text=True, timeout=120).stdout

    def attribute(name):
        found = re.search(rf'<html[^>]* data-{name}="([^"]*)"', dom)
        return json.loads(entities.unescape(found.group(1))) if found else None

    def inside(name):
        found = re.search(rf'id="{name}"[^>]*>(.*?)</div>', dom, re.S)
        return entities.unescape(re.sub(r'<[^>]+>', '', found.group(1)))

    return dom, [m for m in attribute('posted') or [] if 'essage' in m['command']], inside, attribute('state')


def _run(corpus, page):
    return json.dumps({'type': 'result', 'result': sb.run_query(corpus, CUTTER, 0, OFF, page['holder']['query'])})


def test_edit_shows_the_field_the_variables_and_a_preview_of_a_real_row(tmp_path, corpus, page):
    dom, posted, inside, _ = _browse(tmp_path, page, f'''
say({_run(corpus, page)}); click('messageedit'); type('Off: {{?f}} <b> {{?nope}}');''')
    assert inside('messagepreview') == 'Preview · urn:plasmacutter:1: Off: urn:filter:1 <b> {?nope}'
    assert re.search(r'class="unfilled"[^>]*>\{\?nope\}', dom) and 'Off: urn:filter:1 &lt;b&gt;' in dom
    assert inside('messagevars') == 'Insert$this?v1?f?v2', '$this first'
    assert re.search(r'id="messageview" hidden', dom)
    assert posted == [{'command': 'checkMessage', 'message': 'Off: {?f} <b> {?nope}'}], 'asked once'


def test_without_a_violating_row_the_preview_says_so(tmp_path, page):
    _, _, inside, _ = _browse(tmp_path, page, "click('messageedit');")
    assert inside('messagepreview').startswith('Preview · no row of this run violates')


def test_a_chip_inserts_at_the_cursor_and_tab_completes(tmp_path, page):
    dom, posted, _, _ = _browse(tmp_path, page, '''
click('messageedit'); type('a  b');
var f = document.getElementById('messagetext'); f.setSelectionRange(2, 2);
document.querySelector('[data-var=this]').click();
f.setRangeText(' {?v', f.value.length, f.value.length, 'end'); f.dispatchEvent(new Event('input'));
document.documentElement.dataset.dimmed = JSON.stringify(
  Array.from(document.querySelectorAll('[data-var].other')).map((b) => b.dataset.var));
key('Tab'); key('Enter');''')
    assert [m['message'] for m in posted if m['command'] == 'saveMessage'] == ['a {?this} b {?v1}']
    assert json.loads(entities.unescape(re.search(r'data-dimmed="([^"]*)"', dom).group(1))) == ['this', 'f']


def test_a_chip_replaces_the_placeholder_being_written(tmp_path, page):
    _, posted, _, _ = _browse(tmp_path, page, '''
click('messageedit'); type('x {?fo} y');
document.getElementById('messagetext').setSelectionRange(5, 5);
document.querySelector('[data-var=v2]').click(); click('messagesave');''')
    assert [m['message'] for m in posted if m['command'] == 'saveMessage'] == ['x {?v2} y']


def test_warnings_are_the_server_s_for_the_text_as_it_is(tmp_path, page):
    _, _, inside, _ = _browse(tmp_path, page, '''
click('messageedit'); type('{?x}');
say({ type: 'messageCheck', message: 'older', variables: ['this'], warnings: ['old'] });
say({ type: 'messageCheck', message: '{?x}', variables: ['this'], warnings: ['x <is> not selected'] });''')
    assert inside('messagewarnings') == 'x <is> not selected'
    assert inside('messagevars') == 'Insert$this'


def test_the_saved_message_s_warnings_follow_the_run(tmp_path, page):
    _, _, inside, _ = _browse(tmp_path, page, '''
say({ type: 'result', result: { ok: true, kind: 'constraint', focus: [], violating: [],
  message: { variables: ['this'], warnings: ['no longer fits'] } } });''')
    assert inside('messagewarnings') == 'no longer fits'


def test_shift_enter_is_a_new_line_and_enter_saves(tmp_path, page):
    script = """click('messageedit'); type('two');
var shifted = new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, cancelable: true });
document.getElementById('messagetext').dispatchEvent(shifted);
document.documentElement.dataset.shifted = JSON.stringify(shifted.defaultPrevented);"""
    dom, posted, _, _ = _browse(tmp_path, page, script)
    assert 'data-shifted="false"' in dom, 'the field keeps its own line break'
    assert not [m for m in posted if m['command'] == 'saveMessage']
    _, posted, _, _ = _browse(tmp_path, page, script + " key('Enter');")
    assert [m for m in posted if m['command'] == 'saveMessage'] == [
        {'command': 'saveMessage', 'message': 'two', 'expected': SAYS}]


def test_tab_inserts_only_after_a_question_mark(tmp_path, page):
    script = """click('messageedit'); type('Range {v'); key('Tab');
document.documentElement.dataset.value = JSON.stringify(document.getElementById('messagetext').value);"""
    dom, _, _, _ = _browse(tmp_path, page, script)
    assert 'data-value="&quot;Range {v&quot;"' in dom
    dom, _, _, _ = _browse(tmp_path, page, script.replace('{v', '{?v'))
    assert 'data-value="&quot;Range {?v1}&quot;"' in dom


def test_escape_and_an_unchanged_save_write_nothing(tmp_path, page):
    for close in ("type('x'); key('Escape');", "click('messagesave');", "type('x'); click('messagecancel');",
                  "key('Escape');"):
        dom, posted, _, state = _browse(tmp_path, page, "click('messageedit');" + close)
        assert not [m for m in posted if m['command'] == 'saveMessage']
        assert re.search(r'id="messageeditor"[^>]* hidden', dom) and 'message' not in (state or {})


def test_a_draft_outlives_a_redraw_and_a_refused_save(tmp_path, page):
    _, posted, inside, state = _browse(tmp_path, page, '''
click('messageedit'); type('mine'); click('messagesave'); click('messagesave');
say({ type: 'messageError', text: 'Not saved: it changed' });''')
    assert len([m for m in posted if m['command'] == 'saveMessage']) == 1, 'not twice'
    assert inside('messagewarnings') == 'Not saved: it changed'
    assert state['message'] == {'shape': CUTTER, 'index': 0, 'text': 'mine', 'expected': SAYS}
    other = json.loads(json.dumps(page))
    other['holder']['message'] = 'theirs'
    dom, _, inside, _ = _browse(tmp_path, other, 'click("messagesave");', state=dict(state, open={}))
    assert inside('messagechanged') == 'The message changed in the file meanwhile: “theirs”. Cancel to see it.'
    assert '"expected":"' + SAYS in entities.unescape(dom), 'the save is refused by the server, not lost'


def test_a_constraint_without_a_message_offers_one_and_a_rule_none(tmp_path, page, corpus):
    bare = json.loads(json.dumps(page))
    bare['holder']['message'] = ''
    bare['message']['warnings'] = ['it has no sh:message']
    dom, posted, inside, _ = _browse(tmp_path, bare, "type('New'); key('Enter');", edit=True)
    assert '+ Message' in dom and 'no sh:message' in dom
    assert posted[-1] == {'command': 'saveMessage', 'message': 'New', 'expected': ''}
    rule = dict(sb.bench_page(corpus, UNTIL), ok=True)
    made = {'ok': True, 'kind': 'rule', 'focus': [], 'triples': 0}
    dom, _, _, _ = _browse(tmp_path, rule, f"say({json.dumps({'type': 'result', 'result': made})});", edit=True)
    assert 'id="messageview"' not in dom and 'Constructs nothing' in dom


def test_several_messages_are_shown_where_they_are_written(tmp_path, page):
    locked = json.loads(json.dumps(page))
    locked['holder']['messageLocked'] = 'it has 2 sh:message values'
    dom, _, _, _ = _browse(tmp_path, locked, '', edit=True)
    assert 'id="messageedit"' not in dom and 'it has 2 sh:message values' in dom and 'Show in .ttl' in dom


def test_the_page_fills_by_the_server_s_rule(tmp_path):
    cases = [('{?v} on {$this}, {?missing} {?}', {'v': '1', 'this': 'urn:a'}), ('', {}), ('{?toString}', {}),
             ('{?größe}x', {'größe': '$&'}), ('{v} {? v}', {'v': '1'})]
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    script = tmp_path / 'fill.js'
    script.write_text(
        'const M = require("module"); const l = M._load; M._load = (r, ...a) => r === "vscode" ? {} : l(r, ...a);'
        f'const {{ fillPieces }} = require({json.dumps(os.path.join(SRC, "sparqlmessage.js"))});'
        f'console.log(JSON.stringify({json.dumps(cases)}.map(([t, r]) => '
        'fillPieces(t, r).map((p) => p.text).join(""))));')
    out = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60)
    assert json.loads(out.stdout) == [fill(t, r) for t, r in cases], out.stderr
