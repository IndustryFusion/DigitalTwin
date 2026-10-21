"""The SPARQL workbench page, driven through the extension with the harness,
on the payloads the real server builds (so page and server cannot drift).

The query is edited in a real editor: a `semforge-sparql:` document the
extension's file system reads from and saves into shacl.ttl. The page's
buttons act on that document; what the extension sends back -- a result, a
save -- is posted INTO the page rather than re-rendering it.
"""

import json
import re
import os
import shutil
import subprocess
from unittest import mock

import pytest

from semforge.cooked import sparqlbench as sb

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')
BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
CUTTER = BASE + 'StateOnCutterShape'
PACKAGE = 'file:///pkg/shacl.ttl'
OFF = 'test_StateOnCutterShape/bad/filter-off.jsonld'


@pytest.fixture(scope='module')
def page(corpus):
    return dict(sb.bench_page(corpus, CUTTER, 0, sb.MAIN), ok=True)


@pytest.fixture(scope='module')
def run(corpus, page):
    return sb.run_query(corpus, CUTTER, 0, sb.MAIN, page['holder']['query'])


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


def _render(tmp_path, page, dirty=False):
    return _drive(tmp_path, {'mode': 'render', 'function': 'renderSparqlBench', 'payload': page,
                             'options': {'nonce': 'n1', 'dirty': dirty}}, 'sparqlpage.js')['html']


def _open(tmp_path, page, messages, **scenario):
    replies = {'semforge/sparqlBench': page, 'semforge/sparqlRun': {'ok': True},
               'semforge/sparqlQuery': dict(page['holder'], ok=True)}
    replies.update(scenario.pop('replies', {}))
    return _drive(tmp_path, dict({
        'command': 'semforge.openSparqlBench',
        'node': {'raw': {'shape': CUTTER}, 'packageUri': PACKAGE},
        'webviewMessages': messages, 'replies': replies}, **scenario))


def _asked(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


# --- the page ---------------------------------------------------------------------------

def test_it_shows_its_editor_the_data_and_the_buttons(tmp_path, page):
    html = _render(tmp_path, page)
    for text in ('data-editor="1"', 'StateOnCutterShape.rq', '<kbd>Ctrl+Space</kbd> completes',
                 '<kbd>Shift+Alt+F</kbd> formats', 'id="apply"', 'id="inspect"', 'id="cancel"',
                 'id="save"', 'id="more"', 'id="source"', 'Cutter running without running filter',
                 'severity: critical</span>', 'Instance data (Turtle)',
                 'urn:plasmacutter:1', '2 focus nodes'):
        assert text in html, text
    assert 'severity: base:severityCritical' not in html, 'said as a reader says it'
    assert '<span class="severity"' in html and 'chip bad">critical' not in html, \
        'a label, not a verdict'
    assert 'id="remove"' not in html, 'Remove waits behind the ⋯'
    assert '<textarea' not in html, 'the query is edited in its own editor'
    state = json.loads(html.split('const state = ', 1)[1].split(';\n', 1)[0])
    assert state['dirty'] is False
    assert 'id="dirty" hidden' in html
    assert "script-src 'nonce-n1'" in html
    # The result comes first; what is looked at now and then is folded away.
    body = html.split('<body>', 1)[1]
    assert body.index('<h2>Result</h2>') < body.index('id="fold-selects"') \
        < body.index('id="fold-data"') < body.index('id="fold-keys"')
    assert '<details class="fold" id="fold-data">' in html, 'the data is collapsed'
    assert '<details class="fold" id="fold-snapshots" hidden>' in html, 'no snapshot yet'
    assert html.count('<option') == len(page['sources'])


def test_the_page_script_parses(tmp_path, page):
    """The script is generated inside a template string, where `\\n` in a regex
    turns into a real line break -- a page whose script does not parse shows
    everything and does nothing. Checked here, not only in a real VS Code."""
    html = _render(tmp_path, page)
    script = html.split('<script nonce="n1">', 1)[1].split('</script>', 1)[0]
    path = tmp_path / 'page-script.js'
    path.write_text('function acquireVsCodeApi() {}\n' + script)
    node = shutil.which('node')
    checked = subprocess.run([node, '--check', str(path)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr[-800:]


def test_an_undeclared_severity_is_said_to_be_the_default(tmp_path, page):
    bare = json.loads(json.dumps(page))
    bare['holder']['severity'] = ''
    html = _render(tmp_path, bare)
    assert 'severity: violation <span class="dim">(default)</span>' in html
    assert 'It does not say whether it fires.' in html


def test_unsaved_changes_in_the_editor_are_said_on_the_page(tmp_path, page):
    html = _render(tmp_path, page, dirty=True)
    assert 'id="dirty"\n    title="The editor holds changes not in shacl.ttl">● unsaved' in html
    state = json.loads(html.split('const state = ', 1)[1].split(';\n', 1)[0])
    assert state['dirty'] is True


def test_nothing_reaches_the_page_unescaped(tmp_path, page):
    hostile = json.loads(json.dumps(page))
    hostile['holder']['message'] = '<img src=x onerror=alert(2)>'
    hostile['label'] = '<script>alert(1)</script>'
    html = _render(tmp_path, hostile)
    assert '<script>alert' not in html and '<img src=x' not in html


# --- what the buttons do -----------------------------------------------------------------

def test_the_query_opens_as_a_document_read_from_shacl_ttl(tmp_path, page):
    seen = _open(tmp_path, page, [])
    assert seen['errors'] == [], seen['errors']
    assert _asked(seen, 'semforge/sparqlQuery') == [{'uri': PACKAGE, 'shape': CUTTER,
                                                    'holder': 0}]
    assert seen['webviews'][0]['title'] == 'StateOnCutterShape · SPARQL'
    assert 'StateOnCutterShape.rq' in seen['webviews'][0]['html'][0]


def test_apply_runs_what_the_editor_holds_and_posts_the_result_back(tmp_path, page, run):
    seen = _open(tmp_path, page, [{'command': 'run'}], replies={'semforge/sparqlRun': run})
    assert _asked(seen, 'semforge/sparqlRun') == [{
        'uri': PACKAGE, 'shape': CUTTER, 'index': 0, 'source': '@main',
        'query': page['holder']['query']}]
    assert seen['webviews'][0]['posted'] == [{'type': 'result', 'result': run}]
    assert len(seen['webviews'][0]['html']) == 1, 'a run never re-renders the page'


def test_save_writes_over_the_query_it_opened(tmp_path, page):
    edited = page['holder']['query'] + '\n'
    seen = _open(tmp_path, page, [{'command': 'save', 'query': edited}],
                 replies={'semforge/sparqlSave': {'ok': True, 'file': '/pkg/shacl.ttl',
                                                  'line': 187}})
    assert _asked(seen, 'semforge/sparqlSave') == [{
        'uri': PACKAGE, 'shape': CUTTER, 'index': 0, 'query': edited,
        'expected': page['holder']['query']}]
    assert {'type': 'saved', 'query': edited, 'where': 'shacl.ttl:187'} in \
        seen['webviews'][0]['posted']
    assert seen['webviews'][0]['posted'][-1] == {'type': 'dirty', 'dirty': False}
    assert any(e['command'] == 'semforge.refreshShapes' for e in seen['executed'])
    assert any(e['type'] == 'saved' for e in seen['events']), 'the document was saved'


def test_a_refused_save_fails_as_a_save_and_keeps_the_edit(tmp_path, page):
    seen = _open(tmp_path, page, [{'command': 'save', 'query': 'x'}],
                 replies={'semforge/sparqlSave': {'ok': False, 'error': 'changed in the file'}})
    assert any('changed in the file' in e for e in seen['saveErrors'])
    assert seen['webviews'][0]['posted'][-1] == {'type': 'error', 'text': 'not saved'}
    assert not any(e['type'] == 'saved' for e in seen['events'])


def test_cancel_is_the_editor_s_revert(tmp_path, page):
    seen = _open(tmp_path, page, [{'command': 'loadSnapshot', 'id': 'saved'},
                                  {'command': 'cancel'}])
    assert any(e['command'] == 'workbench.action.files.revert' for e in seen['executed'])


def test_another_source_rerenders_and_leaves_the_editor_alone(tmp_path, page):
    seen = _open(tmp_path, page, [{'command': 'source', 'source': OFF}])
    asked = _asked(seen, 'semforge/sparqlBench')
    assert [a['source'] for a in asked] == ['@main', OFF]
    assert not any(e['type'] == 'edited' for e in seen['events'])


def test_another_query_of_the_shape_opens_its_own_document(tmp_path, page):
    second = dict(page['holder'], index=1, query='SELECT 2')
    two = dict(page, holders=page['holders'] + [second])
    seen = _open(tmp_path, two, [{'command': 'holder', 'index': 1}],
                 replies={'semforge/sparqlBench': [two, dict(two, holder=second)]})
    assert [a.get('index') for a in _asked(seen, 'semforge/sparqlBench')] == [None, 1]
    assert [a['holder'] for a in _asked(seen, 'semforge/sparqlQuery')] == [0, 1]
    assert 'StateOnCutterShape-2.rq' in seen['webviews'][0]['html'][-1]
    assert seen['warnings'] == [], 'each query is its own document: nothing to discard'


# --- the way in ------------------------------------------------------------------------

def test_the_shape_page_opens_the_workbench_on_the_clicked_query(tmp_path, corpus):
    from semforge.cooked.shapepage import build_shape_page

    shape_page = dict(build_shape_page(corpus, CUTTER), ok=True)
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': {'shape': CUTTER}, 'packageUri': PACKAGE},
        'webviewMessages': [{'command': 'bench', 'row': 0}],
        'replies': {'semforge/shapePage': shape_page}})
    html = seen['webviews'][0]['html'][0]
    assert 'data-action="bench" data-row="0"' in html and 'data-action="addCheck"' in html
    opened = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openSparqlBench']
    assert opened[0][0]['raw']['shape'] == CUTTER
    assert opened[0][1] == {'query': shape_page['checks'][0]['query'], 'kind': 'constraint'}


def test_add_sparql_constraint_asks_the_message_and_opens_it(tmp_path, page):
    seen = _drive(tmp_path, {
        'command': 'semforge.addSparqlConstraint',
        'node': {'raw': {'shape': CUTTER, 'label': 'StateOnCutterShape'}, 'packageUri': PACKAGE},
        'inputs': ['Cutter too hot'],
        'replies': {'semforge/addSparqlConstraint': {'ok': True, 'file': '/pkg/shacl.ttl',
                                                     'index': 1, 'line': 210},
                    'semforge/sparqlBench': page,
                    'semforge/sparqlQuery': dict(page['holder'], ok=True)}})
    assert _asked(seen, 'semforge/addSparqlConstraint') == [
        {'uri': PACKAGE, 'shape': CUTTER, 'message': 'Cutter too hot'}]
    assert _asked(seen, 'semforge/sparqlBench')[0]['index'] == 1
    assert any('fires on nothing yet' in m for m in seen['info'])


def test_the_type_page_s_rule_rows_open_it(tmp_path, corpus):
    from semforge.cooked.typepage import build_type_page

    type_page = dict(build_type_page(corpus, 'iffBaseEntities:Cutter'), ok=True)
    rule = next(r for r in type_page['rules'] if r['shape'] == CUTTER)
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'targetClass': type_page['iri'], 'children': []},
                 'packageUri': PACKAGE},
        'webviewMessages': [{'command': 'bench', 'shape': rule['shape'], 'kind': rule['kind']}],
        'replies': {'semforge/typePage': type_page}})
    assert f'data-bench="{CUTTER}"' in seen['webviews'][0]['html'][0]
    opened = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openSparqlBench']
    assert opened == [[{'raw': {'shape': CUTTER}, 'packageUri': PACKAGE}, {'kind': 'constraint'}]]


# --- the server --------------------------------------------------------------------------

def test_the_server_answers_all_four(corpus_path, tmp_path):
    from semforge.editor import server

    copy = tmp_path / 'kms'
    shutil.copytree(corpus_path, copy, symlinks=False, ignore=shutil.ignore_patterns('.semforge'))
    uri = f'file://{copy}/shacl.ttl'
    ls = mock.MagicMock()
    with mock.patch.object(server, '_publish'):
        opened = server.sparql_bench_feature(ls, {'uri': uri, 'shape': CUTTER, 'source': OFF})
        assert opened['ok'] and opened['focus'] == ['urn:plasmacutter:1']
        ran = server.sparql_run_feature(ls, {'uri': uri, 'shape': CUTTER, 'index': 0,
                                             'source': OFF, 'query': opened['holder']['query']})
        assert ran['violating'] == ['urn:plasmacutter:1']
        saved = server.sparql_save_feature(ls, {
            'uri': uri, 'shape': CUTTER, 'index': 0,
            'query': opened['holder']['query'] + '\n', 'expected': opened['holder']['query']})
        assert saved['ok'], saved
        added = server.add_sparql_constraint_feature(ls, {'uri': uri, 'shape': CUTTER,
                                                          'message': 'second'})
        assert added['ok'] and added['index'] == 1
        refused = server.sparql_bench_feature(ls, {'uri': uri, 'shape': BASE + 'WorkpieceShape'})
        assert not refused['ok'] and 'no SPARQL query' in refused['error']


def test_a_parameter_the_client_left_out_is_missing_not_a_tuple_method():
    """pygls hands custom params over as a namedtuple: without this, an omitted
    `index` was tuple.index, and the workbench failed only in a real VS Code."""
    from collections import namedtuple

    from semforge.editor.server import _field

    Sent = namedtuple('Object', ['uri', 'shape'])
    assert _field(Sent('u', 's'), 'index') is None
    assert _field(Sent('u', 's'), 'count', 7) == 7
    assert _field(Sent('u', 's'), 'shape') == 's'
    WithIndex = namedtuple('Object', ['uri', 'index'])
    assert _field(WithIndex('u', 2), 'index') == 2


# --- Remove… ----------------------------------------------------------------------------

def _plan(page, asserts, last=True, others=0):
    return {'ok': True, 'holder': page['holder'], 'last': last, 'others': others,
            'asserts': [{'file': '/pkg/examples/x/expectations.yaml', 'case': case,
                         'resource': 'urn:plasmacutter:1'} for case in asserts]}


def _remove(tmp_path, page, plan, answer, dirty=False, after=None):
    replies = {'semforge/sparqlRemovalPlan': plan,
               'semforge/sparqlRemove': {'ok': True, 'file': '/pkg/shacl.ttl', 'line': 185,
                                         'asserts': 1 if answer and 'asserts' in answer else 0}}
    if after is not None:
        replies['semforge/sparqlBench'] = [page, after]
    scenario = {'replies': replies}
    if answer:
        scenario['answer'] = answer
    # Unsaved changes: the saved text put back into the editor marks it edited.
    edit = [{'command': 'loadSnapshot', 'id': 'saved'}] if dirty else []
    return _open(tmp_path, page, edit + [{'command': 'remove'}], **scenario)


def test_remove_says_which_cases_assert_it_and_can_take_them(tmp_path, page):
    seen = _remove(tmp_path, page, _plan(page, ['filter-off.jsonld']),
                   'Remove it and its asserts')
    warning = next(w for w in seen['warnings'] if w.startswith('Remove the SPARQL constraint'))
    assert '"Cutter running without running filter"' in warning
    assert 'filter-off.jsonld (on urn:plasmacutter:1)' in warning
    assert 'no other SPARQL constraint of this shape is left' in warning
    sent = _asked(seen, 'semforge/sparqlRemove')
    assert sent == [{'uri': PACKAGE, 'shape': CUTTER, 'query': page['holder']['query'],
                     'kind': 'constraint', 'expected': page['holder']['query'],
                     'dropAsserts': True}]
    assert any(e['command'] == 'semforge.refreshShapes' for e in seen['executed'])


def test_remove_it_only_keeps_the_asserts(tmp_path, page):
    seen = _remove(tmp_path, page, _plan(page, ['filter-off.jsonld']), 'Remove it only')
    assert _asked(seen, 'semforge/sparqlRemove')[0]['dropAsserts'] is False


def test_asserts_another_constraint_answers_for_are_only_mentioned(tmp_path, page):
    seen = _remove(tmp_path, page, _plan(page, ['filter-off.jsonld'], last=False, others=1),
                   'Remove')
    warning = next(w for w in seen['warnings'] if w.startswith('Remove the'))
    assert '1 other(s) remain, so the asserts are kept' in warning
    assert _asked(seen, 'semforge/sparqlRemove')[0]['dropAsserts'] is False


def test_unsaved_edits_are_mentioned_and_a_dismissal_removes_nothing(tmp_path, page):
    seen = _remove(tmp_path, page, _plan(page, []), None, dirty=True)
    assert any(e['type'] == 'edited' for e in seen['events'])
    assert any('unsaved edits in the workbench go with it' in w for w in seen['warnings'])
    assert _asked(seen, 'semforge/sparqlRemove') == []


def test_after_the_last_query_the_page_closes(tmp_path, page):
    gone = {'ok': False, 'error': 'iffBaseShacl:StateOnCutterShape has no SPARQL query'}
    seen = _remove(tmp_path, page, _plan(page, []), 'Remove', after=gone)
    assert len(seen['webviews'][0]['html']) == 1, 'not re-rendered into an error page'


def test_the_shape_page_s_remove_names_the_query_by_its_text(tmp_path, corpus):
    from semforge.cooked.shapepage import build_shape_page

    shape_page = dict(build_shape_page(corpus, CUTTER), ok=True)
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': {'shape': CUTTER}, 'packageUri': PACKAGE},
        'webviewMessages': [{'command': 'checkMenu', 'row': 0}],
        'picks': ['$(trash) Remove…'],
        'replies': {'semforge/shapePage': shape_page}})
    assert 'data-action="checkMenu" data-row="0"' in seen['webviews'][0]['html'][0]
    assert [i['label'] for i in seen['quickPicks'][0]['items']] == [
        '$(beaker) Open in SPARQL workbench', '$(warning) Severity…', '$(trash) Remove…']
    asked = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.removeSparqlQuery']
    check = shape_page['checks'][0]
    assert asked[0][1] == {'query': check['query'], 'kind': 'constraint',
                           'message': check['message']}


def test_the_server_finds_the_query_by_its_text(corpus_path, tmp_path):
    from semforge.editor import server
    from semforge.package import load

    copy = tmp_path / 'kms'
    shutil.copytree(corpus_path, copy, symlinks=False, ignore=shutil.ignore_patterns('.semforge'))
    uri = f'file://{copy}/shacl.ttl'
    query = sb.holders(load(str(copy)), CUTTER)[0]['query']
    with mock.patch.object(server, '_publish'):
        plan = server.sparql_removal_plan_feature(mock.MagicMock(), {
            'uri': uri, 'shape': CUTTER, 'query': query})
        assert plan['ok'] and plan['last'] and len(plan['asserts']) == 1
        done = server.sparql_remove_feature(mock.MagicMock(), {
            'uri': uri, 'shape': CUTTER, 'query': query, 'expected': query,
            'dropAsserts': True})
        assert done['ok'] and done['asserts'] == 1


def test_add_check_offers_a_sparql_constraint(tmp_path, corpus):
    """+ Add check ▾ on a shape with no attributes of its own: only SPARQL."""
    from semforge.cooked.shapepage import build_shape_page

    shape_page = dict(build_shape_page(corpus, CUTTER), ok=True)
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': {'shape': CUTTER}, 'packageUri': PACKAGE},
        'webviewMessages': [{'command': 'addCheck', 'row': -1}],
        'picks': ['$(beaker) SPARQL constraint'],
        'replies': {'semforge/shapePage': shape_page}})
    labels = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert labels[-1] == '$(beaker) SPARQL constraint'
    assert ('$(symbol-field) Attribute' in labels) == bool(shape_page.get('ownShape'))
    asked = [e['command'] for e in seen['executed']]
    assert 'semforge.addSparqlConstraint' in asked


def test_the_workbench_menu_holds_what_is_used_now_and_then(tmp_path, page):
    seen = _open(tmp_path, page, [{'command': 'menu'}], picks=['$(go-to-file) Show it in shacl.ttl'])
    labels = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert labels[0] == "$(edit) Show the query's editor"
    assert labels[-1] == '$(trash) Remove this constraint…'
    assert '$(save) Save into shacl.ttl' not in labels, 'nothing unsaved: nothing to save'


# --- the selector, Inspect, snapshots ----------------------------------------------------------

def test_the_page_says_how_this_is_bound(tmp_path, page):
    html = _render(tmp_path, page)
    assert '<b>Selects</b>' in html
    assert 'What it selects <span class="dim">· $this = 2 node(s)</span>' in html
    assert '$this = each of every Cutter, and every subclass of it → 2 node(s)' in html
    assert 'Show as SPARQL — what the engine adds' in html
    assert 'VALUES $this { &lt;urn:plasmacutter:1&gt; &lt;urn:plasmacutter:2&gt; }' in html


def test_inspect_asks_with_the_text_as_it_is_and_posts_the_answer(tmp_path, page, corpus):
    inspected = sb.inspect(corpus, CUTTER, 0, sb.MAIN, page['holder']['query'])
    seen = _open(tmp_path, page, [{'command': 'inspect', 'query': 'SELECT $this WHERE {}'}],
                 replies={'semforge/sparqlInspect': inspected})
    assert _asked(seen, 'semforge/sparqlInspect') == [{
        'uri': PACKAGE, 'shape': CUTTER, 'index': 0, 'source': '@main',
        'query': 'SELECT $this WHERE {}'}]
    assert seen['webviews'][0]['posted'] == [{'type': 'inspect', 'result': inspected}]
    assert len(seen['webviews'][0]['html']) == 1, 'the editor is not re-rendered away'
    html = seen['webviews'][0]['html'][0]
    assert 'id="inspect"' in html and 'id="inspected"' in html


def _snap(tmp_path, page, messages, **scenario):
    ran = {'ok': True, 'kind': 'constraint', 'violating': ['urn:plasmacutter:1']}
    return _open(tmp_path, page, messages, replies={'semforge/sparqlRun': ran}, **scenario)


def test_a_snapshot_keeps_the_text_with_what_it_did(tmp_path, page):
    seen = _snap(tmp_path, page, [{'command': 'snapshot', 'query': 'SELECT 1'}],
                 inputs=['works on filter-off'])
    assert seen['inputs'][0]['title'] == 'Snapshot'
    assert 'closing VS Code forgets it' in seen['inputs'][0]['prompt']
    (posted,) = seen['webviews'][0]['posted']
    (entry,) = posted['list']
    assert posted['type'] == 'snapshots'
    assert entry['name'] == 'works on filter-off' and entry['query'] == 'SELECT 1'
    assert entry['verdict'] == '1 violating on Main'


def test_snapshots_outlive_a_rerender_and_can_be_deleted(tmp_path, page):
    seen = _snap(tmp_path, page, [{'command': 'snapshot', 'query': 'SELECT 1'},
                                  {'command': 'snapshot', 'query': 'SELECT 2'},
                                  {'command': 'source', 'source': OFF, 'query': 'SELECT 2'},
                                  {'command': 'deleteSnapshot', 'id': 1}],
                 inputs=['first', 'second'])
    html = seen['webviews'][0]['html'][-1]
    state = json.loads(html.split('const state = ', 1)[1].split(';\n', 1)[0])
    assert [s['name'] for s in state['snapshots']] == ['first', 'second'], 'kept across data'
    assert [s['name'] for s in seen['webviews'][0]['posted'][-1]['list']] == ['second']


def test_a_dismissed_name_takes_no_snapshot(tmp_path, page):
    seen = _snap(tmp_path, page, [{'command': 'snapshot', 'query': 'SELECT 1'}])
    assert seen['webviews'][0]['posted'] == [] and _asked(seen, 'semforge/sparqlRun') == []


def test_nothing_of_the_workbench_is_stored_anywhere():
    """Agreed: only Save persists -- through the query's file system, into
    shacl.ttl, via the server. Snapshots live in memory and go with VS Code."""
    source = open(os.path.join(SRC, 'sparqlpage.js')).read()
    for storage in ('workspaceState', 'globalState', 'storageUri', "require('fs')",
                    'registerWebviewPanelSerializer'):
        assert storage not in source, storage
    # The webview's own state dies with the panel (no serializer): it keeps
    # which folds are open and the Inspect toggle, never a query.
    assert set(re.findall(r'setState\((\w+)\)', source)) == {'kept'}
    assert "{ open: {}, inspect: false }" in source


# --- the Flink quick fix's command -------------------------------------------------------------

FLINK_ARGS = {'packageUri': PACKAGE, 'attribute': 'https://x/hasJSON', 'kind': 'JsonProperty',
              'entityType': 'https://x/Cutter'}


def test_nest_for_flink_adds_an_optional_property_shape(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.nestForFlink', 'node': FLINK_ARGS,
        'replies': {'semforge/addAttributeConstraint': {'ok': True, 'file': '/pkg/shacl.ttl'}}})
    assert _asked(seen, 'semforge/addAttributeConstraint') == [{
        'uri': PACKAGE, 'shape': None, 'entityType': 'https://x/Cutter',
        'attribute': 'https://x/hasJSON', 'required': False}]
    assert any(e['command'] == 'semforge.refreshTree' for e in seen['executed'])


def test_a_type_without_a_shape_gets_one_first(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.nestForFlink', 'node': FLINK_ARGS,
        'commandResults': {'semforge.newShape': {'ok': True, 'iri': 'https://x/CutterShape'}},
        'replies': {'semforge/addAttributeConstraint': [
            {'ok': False, 'error': 'no shape targets https://x/Cutter itself'},
            {'ok': True, 'file': '/pkg/shacl.ttl'}]}})
    asked = _asked(seen, 'semforge/addAttributeConstraint')
    assert [a['shape'] for a in asked] == [None, 'https://x/CutterShape']
    made = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.newShape']
    assert made[0][0]['raw']['targetClass'] == 'https://x/Cutter'


# --- the editor's keys: Ctrl+Enter applies, Ctrl+Shift+Enter inspects -----------------------------

def test_the_keys_act_on_the_query_in_the_active_editor(tmp_path, page, run, corpus):
    inspected = sb.inspect(corpus, CUTTER, 0, sb.MAIN, page['holder']['query'])
    seen = _open(tmp_path, page, [], then=[{'command': 'semforge.sparqlApply'},
                                           {'command': 'semforge.sparqlInspect'}],
                 replies={'semforge/sparqlRun': run, 'semforge/sparqlInspect': inspected})
    assert seen['errors'] == [], seen['errors']
    assert [a['query'] for a in _asked(seen, 'semforge/sparqlRun')] == [page['holder']['query']]
    assert [a['query'] for a in _asked(seen, 'semforge/sparqlInspect')] == \
        [page['holder']['query']]
    assert [m['type'] for m in seen['webviews'][0]['posted']] == ['result', 'inspect']


def test_the_keys_do_nothing_outside_a_query(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.openSource',
        'node': {'raw': {'kind': 'attribute', 'label': 'x', 'definedAt': '/pkg/shacl.ttl:3',
                         'children': []}, 'packageUri': PACKAGE},
        'then': [{'command': 'semforge.sparqlApply'}, {'command': 'semforge.sparqlInspect'}],
        'replies': {}})
    assert seen['errors'] == [] and seen['webviews'] == []
    assert seen['thenResults'] == [False, False]
