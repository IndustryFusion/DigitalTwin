"""Clone… a test case: its data, in its suite, expecting the opposite or the same.

A valid case's invalid twin is how a bad case is usually made -- the same
scene with one thing broken. The clone starts from identical data, so an
opposite clone FAILS until its data is edited; that is the point, and the
case says so. Run on copies of the kms corpus (its files link into
semantic-model/kms, so a copy follows the links).
"""

import json
import os
import shutil
import subprocess
from unittest import mock

import pytest

from semforge.errors import PackageError
from semforge.expect.addcase import clone_case
from semforge.package import load

GOOD = 'test_StateOnCutterShape/good/filter-on.jsonld'
BAD = 'test_StateOnCutterShape/bad/filter-off.jsonld'


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return target


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def _entry(kms, case):
    from semforge.expect.store import load_expectations

    return next(e for e in load_expectations(str(kms)).examples if e.path == case)


def test_a_valid_case_s_invalid_twin_fails_until_its_data_is_broken(kms):
    made = clone_case(load(str(kms)), GOOD, 'opposite')
    assert made['case'] == 'test_StateOnCutterShape/bad/filter-on-violates.jsonld'
    assert made['expect'] == 'invalid' and made['sourceExpect'] == 'valid'
    assert not made['passes'] and made['violations'] == 0
    entry = _entry(kms, made['case'])
    assert entry.asserts == [] and entry.include == [], 'the includes are written into the file'
    assert 'It fails until its data is edited' in entry.description
    documents = json.loads(_read(made['file']))
    ids = {d['id'] for d in documents}
    assert {'urn:plasmacutter:1', 'urn:filter:1'} <= ids, 'the scene, includes and all'


def test_an_invalid_case_s_valid_twin_drops_its_asserts(kms):
    made = clone_case(load(str(kms)), BAD, 'opposite')
    assert made['case'] == 'test_StateOnCutterShape/good/filter-off-conforms.jsonld'
    assert made['expect'] == 'valid' and not made['passes'] and made['violations'] == 1
    assert _entry(kms, made['case']).asserts == []


def test_a_same_clone_keeps_asserts_and_description_and_passes(kms):
    made = clone_case(load(str(kms)), BAD, 'same')
    assert made['case'] == 'test_StateOnCutterShape/bad/filter-off-copy.jsonld'
    assert made['passes'] and made['asserts'] == 1
    entry, source = _entry(kms, made['case']), _entry(kms, BAD)
    assert entry.asserts == source.asserts and entry.description == source.description


def test_editing_the_clone_leaves_the_shared_files_alone(kms):
    shared = kms / 'examples' / 'subobjects' / 'filter-on.jsonld'
    before = _read(shared)
    made = clone_case(load(str(kms)), GOOD, 'opposite')
    documents = json.loads(_read(made['file']))
    for document in documents:
        if document['id'] == 'urn:filter:1':
            document['iffBaseEntities:hasState']['value'] = {'@id': 'base:state_OFF'}
    with open(made['file'], 'w', encoding='utf-8') as handle:
        json.dump(documents, handle)
    assert _read(shared) == before
    run = subprocess.run([os.path.join(os.path.dirname(os.sys.executable), 'semforge'), 'test',
                          str(kms)], capture_output=True, text=True)
    assert 'FAIL  test_StateOnCutterShape/good/filter-on.jsonld' not in run.stdout, \
        'the original still passes'


def test_a_name_and_an_explicit_expectation(kms):
    made = clone_case(load(str(kms)), str(kms / 'examples' / GOOD), 'valid', 'filter-on-again')
    assert made['case'] == 'test_StateOnCutterShape/good/filter-on-again.jsonld'
    assert made['passes'], 'the same expectation, said outright'


@pytest.mark.parametrize('case, expect, name, said', [
    ('test_StateOnCutterShape/good/nothing.jsonld', 'opposite', '', 'not a declared test case'),
    (GOOD, 'maybe', '', 'either conforms or violates'),
    (GOOD, 'opposite', 'filter-off', 'already exists'),
])
def test_a_clone_is_refused_when_it_cannot_be_right(kms, case, expect, name, said):
    if said == 'already exists':
        name = 'filter-off'                        # bad/filter-off.jsonld is there
    with pytest.raises(PackageError, match=said):
        clone_case(load(str(kms)), case, expect, name)


def test_the_server_clones_and_re_reads(kms):
    from semforge.editor import server

    made = server.clone_case_feature(mock.MagicMock(), {
        'uri': f'file://{kms}/shacl.ttl', 'case': GOOD, 'expect': 'opposite', 'name': ''})
    assert made['ok'] and made['case'].endswith('bad/filter-on-violates.jsonld'), made


# --- the extension ----------------------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
FILE = '/pkg/examples/test_S/good/filter-on.jsonld'
MADE = {'ok': True, 'file': '/pkg/examples/test_S/bad/filter-on-violates.jsonld',
        'case': 'test_S/bad/filter-on-violates.jsonld', 'expect': 'invalid', 'violations': 0,
        'passes': False, 'failures': ['expected invalid'], 'sourceExpect': 'valid',
        'source': 'test_S/good/filter-on.jsonld', 'asserts': 0}


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


def test_clone_from_a_row_asks_which_way_and_names_it(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.cloneTestCase',
        'node': {'raw': {'kind': 'example', 'file': FILE}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': ['$(arrow-swap) Expect the opposite'], 'inputs': ['filter-on-violates'],
        'replies': {'semforge/cloneCase': MADE, 'semforge/casePage': {'ok': False, 'error': 'x'}}})
    first = seen['quickPicks'][0]['items']
    assert first[0]['description'] == 'violates, in bad/', 'a good/ case clones into bad/'
    assert seen['inputs'][0]['value'] == 'filter-on-violates', 'the suggested name'
    assert _asked(seen, 'semforge/cloneCase') == [{
        'uri': 'file:///pkg/shacl.ttl', 'case': FILE, 'expect': 'opposite',
        'name': 'filter-on-violates'}]
    opened = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openCasePage']
    assert opened[0][0]['raw']['file'] == MADE['file']
    assert any('Nothing fires yet: edit its data until it violates' in w for w in seen['warnings'])


def test_the_same_clone_is_suggested_as_a_copy(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.cloneTestCase',
        'node': {'raw': {'kind': 'example', 'file': FILE}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': ['$(copy) Expect the same'], 'inputs': [None]})
    assert seen['inputs'][0]['value'] == 'filter-on-copy'
    assert _asked(seen, 'semforge/cloneCase') == [], 'no name: nothing written'


def test_the_case_page_menu_clones_with_its_expectation(tmp_path):
    page = {'ok': True, 'kind': 'case', 'name': 'filter-on.jsonld', 'expect': 'valid',
            'passed': True, 'file': FILE, 'expectations': '/pkg/examples/test_S/good/expectations.yaml',
            'claims': [], 'unasserted': [], 'files': [], 'summary': {}, 'failures': []}
    seen = _drive(tmp_path, {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'file': FILE}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'pageMenu'}], 'picks': ['$(copy) Clone…'],
        'replies': {'semforge/casePage': page}})
    asked = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.cloneTestCase']
    assert asked[0][0]['raw'] == {'kind': 'example', 'file': FILE, 'expect': 'valid'}
