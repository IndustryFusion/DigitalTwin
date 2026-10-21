"""Delete… a test case, or a whole suite.

A case is its file and its entry; both go, and the folders they leave empty.
What the deletion costs -- the constraints no other case asserts any more --
is said first. Shared data stays: a file another case includes keeps
existing, and a suite such a file lives in is refused. Run on copies of the
kms corpus (its files link into semantic-model/kms, so a copy follows the
links).
"""

import json
import os
import shutil
import subprocess
import sys
from unittest import mock

import pytest

from semforge.errors import PackageError
from semforge.expect.deletecase import delete_cases, delete_plan
from semforge.package import load

BAD = 'test_StateOnCutterShape/bad/filter-off.jsonld'
GOOD = 'test_StateOnCutterShape/good/filter-on.jsonld'
SEMFORGE = os.path.join(os.path.dirname(sys.executable), 'semforge')


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return target


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def _test(kms):
    return subprocess.run([SEMFORGE, 'test', str(kms)], capture_output=True, text=True)


def test_the_plan_says_which_evidence_goes(kms):
    plan = delete_plan(load(str(kms)), BAD)
    assert plan['lost'] == ['iffBaseShacl:StateOnCutterShape/SPARQLConstraintComponent']
    assert [c['case'] for c in plan['cases']] == [BAD]
    assert not plan['cases'][0]['keptFile'] and plan['suite'] == ''


def test_a_deleted_case_takes_its_file_its_entry_and_an_empty_folder(kms):
    done = delete_cases(load(str(kms)), BAD)
    folder = kms / 'examples' / 'test_StateOnCutterShape' / 'bad'
    assert done['removed'] == [str(folder / 'filter-off.jsonld')]
    assert not folder.exists(), 'its only case gone: bad/ and its expectations.yaml too'
    assert (kms / 'examples' / 'test_StateOnCutterShape' / 'good').is_dir()
    after = _test(kms)
    assert after.returncode == 0, after.stdout[-600:]
    assert 'filter-off.jsonld' not in after.stdout


def test_a_case_beside_others_leaves_them_and_their_declaration(kms):
    from semforge.expect.addcase import clone_case

    clone_case(load(str(kms)), BAD, 'same')       # a second case in bad/
    delete_cases(load(str(kms)), BAD)
    yaml = kms / 'examples' / 'test_StateOnCutterShape' / 'bad' / 'expectations.yaml'
    assert 'path: filter-off-copy.jsonld' in _read(yaml)
    assert 'path: filter-off.jsonld\n' not in _read(yaml)
    assert _test(kms).returncode == 0


def test_a_file_another_case_includes_stays(kms):
    good = kms / 'examples' / 'test_StateOnCutterShape' / 'good' / 'expectations.yaml'
    good.write_text(_read(good).replace('    include:\n', f'    include:\n      - {BAD}\n', 1))
    plan = delete_plan(load(str(kms)), BAD)
    assert plan['cases'][0]['keptFile'] and plan['cases'][0]['includedBy'] == [GOOD]
    done = delete_cases(load(str(kms)), BAD)
    assert done['removed'] == [] and (kms / 'examples' / BAD).exists()
    # Its entry was the only one there: the declaration goes, the folder
    # stays -- the shared file is still in it.
    assert not (kms / 'examples' / 'test_StateOnCutterShape' / 'bad' / 'expectations.yaml').exists()


def test_a_suite_goes_whole(kms):
    plan = delete_plan(load(str(kms)), suite='test_FilterShape')
    assert [c['case'] for c in plan['cases']] == ['test_FilterShape/bad/without-cartridge.jsonld']
    assert plan['lost'] == ['iffBaseShacl:FilterShape/hasCartridge/MinCountConstraintComponent']
    delete_cases(load(str(kms)), suite='test_FilterShape')
    assert not (kms / 'examples' / 'test_FilterShape').exists()
    assert _test(kms).returncode == 0


def test_a_suite_another_case_reaches_into_is_refused(kms):
    good = kms / 'examples' / 'test_StateOnCutterShape' / 'good' / 'expectations.yaml'
    good.write_text(_read(good).replace(
        '    include:\n', '    include:\n      - test_FilterShape/bad/without-cartridge.jsonld\n', 1))
    with pytest.raises(PackageError, match=f'{GOOD} include'):
        delete_plan(load(str(kms)), suite='test_FilterShape')
    assert (kms / 'examples' / 'test_FilterShape').is_dir()


@pytest.mark.parametrize('case, suite, said', [
    ('test_StateOnCutterShape/bad/nothing.jsonld', '', 'not a declared test case'),
    ('model-instance.jsonld', '', 'not a declared test case'),
    ('', 'test_Nothing', 'not a suite folder'),
])
def test_what_is_not_a_case_is_not_deleted(kms, case, suite, said):
    with pytest.raises(PackageError, match=said):
        delete_plan(load(str(kms)), case, suite)


def test_the_server_plans_and_deletes(kms):
    from semforge.editor import server

    uri = f'file://{kms}/shacl.ttl'
    with mock.patch.object(server, '_publish'):
        plan = server.delete_case_plan_feature(mock.MagicMock(), {'uri': uri, 'case': BAD})
        assert plan['ok'] and plan['lost']
        done = server.delete_case_feature(mock.MagicMock(), {'uri': uri, 'case': BAD})
        assert done['ok'] and done['removed'], done
        again = server.delete_case_plan_feature(mock.MagicMock(), {'uri': uri, 'case': BAD})
        assert not again['ok'] and 'not a declared test case' in again['error']


# --- the extension ----------------------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
FILE = '/pkg/examples/test_S/bad/filter-off.jsonld'
PLAN = {'ok': True, 'suite': '', 'folder': '',
        'cases': [{'case': 'test_S/bad/filter-off.jsonld', 'file': FILE, 'expect': 'invalid',
                   'asserts': 1, 'keptFile': False, 'includedBy': []}],
        'lost': ['iffBaseShacl:S/SPARQLConstraintComponent']}
DONE = dict(PLAN, removed=[FILE], kept=[])


def _drive(tmp_path, scenario):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(path)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _asked(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


def _delete(tmp_path, answer, raw=None, plan=PLAN):
    return _drive(tmp_path, {
        'command': 'semforge.deleteSuite' if raw and raw['kind'] == 'suite'
        else 'semforge.deleteTestCase',
        'node': {'raw': raw or {'kind': 'example', 'file': FILE},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'answer': answer,
        'replies': {'semforge/deleteCasePlan': plan, 'semforge/deleteCase': DONE}})


def test_delete_says_what_it_costs_before_writing(tmp_path):
    seen = _delete(tmp_path, None)
    said = seen['warnings'][0]
    assert said.startswith('Delete filter-off.jsonld?')
    assert 'filter-off.jsonld and its entry in expectations.yaml go.' in said
    assert 'No other case asserts:\n  iffBaseShacl:S/SPARQLConstraintComponent' in said
    assert 'nothing proves it can fire' in said
    assert _asked(seen, 'semforge/deleteCase') == [], 'dismissed: nothing deleted'


def test_confirmed_the_case_is_deleted(tmp_path):
    seen = _delete(tmp_path, 'Delete')
    assert _asked(seen, 'semforge/deleteCase') == [
        {'uri': 'file:///pkg/shacl.ttl', 'case': FILE, 'suite': ''}]
    assert any('filter-off.jsonld deleted — 1 constraint(s) no longer asserted' in m
               for m in seen['messages'])


def test_a_shared_file_is_said_to_stay(tmp_path):
    plan = json.loads(json.dumps(PLAN))
    plan['cases'][0].update(keptFile=True, includedBy=['test_S/good/on.jsonld'])
    seen = _delete(tmp_path, None, plan=plan)
    assert 'The file itself stays: test_S/good/on.jsonld include(s) it.' in seen['warnings'][0]


def test_a_suite_row_deletes_the_suite_by_its_folder(tmp_path):
    plan = dict(PLAN, suite='test_S', folder='/pkg/examples/test_S')
    seen = _delete(tmp_path, 'Delete', raw={'kind': 'suite', 'label': 'S', 'term': 'test_S'},
                   plan=plan)
    assert seen['warnings'][0].startswith('Delete the suite test_S?')
    assert 'The folder test_S goes, with its 1 case(s):\n  bad/filter-off.jsonld' in seen['warnings'][0]
    assert _asked(seen, 'semforge/deleteCase') == [
        {'uri': 'file:///pkg/shacl.ttl', 'case': '', 'suite': 'test_S'}]


def test_the_case_page_menu_offers_delete(tmp_path):
    page = {'ok': True, 'kind': 'case', 'name': 'filter-off.jsonld', 'expect': 'invalid',
            'passed': True, 'file': FILE, 'expectations': '/pkg/examples/test_S/bad/expectations.yaml',
            'claims': [], 'unasserted': [], 'files': [], 'summary': {}, 'failures': []}
    seen = _drive(tmp_path, {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'file': FILE}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'pageMenu'}], 'picks': ['$(trash) Delete…'],
        'replies': {'semforge/casePage': page}})
    asked = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.deleteTestCase']
    assert asked[0][0]['raw'] == {'kind': 'example', 'file': FILE}
