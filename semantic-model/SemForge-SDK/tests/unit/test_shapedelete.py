"""Delete… for a shape: the statement, and what goes with it by choice.

A deletion must leave a package that tests clean when everything that named
the shape went with it, refuse when another shape reaches it, and never
touch another shape. The SDK side runs on copies of the kms corpus (its
files link into semantic-model/kms, so a copy follows the links); the
extension side through the harness.
"""

import json
import os
import shutil
import subprocess
import sys
from unittest import mock

import pytest

from semforge.cooked.shapedelete import delete_plan, delete_shape
from semforge.errors import PackageError
from semforge.package import load

BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
CUTTER = BASE + 'StateOnCutterShape'
FILTER = BASE + 'FilterShape'
SEMFORGE = os.path.join(os.path.dirname(sys.executable), 'semforge')


@pytest.fixture()
def kms(corpus_path, tmp_path):
    copy = tmp_path / 'kms'
    shutil.copytree(corpus_path, copy, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return copy


def _semforge(*args):
    return subprocess.run([SEMFORGE, *args], capture_output=True, text=True)


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def _mentions(kms, name):
    out = []
    for folder, _, files in os.walk(kms):
        for file in files:
            if file.endswith(('.ttl', '.yaml')) and name in _read(os.path.join(folder, file)):
                out.append(os.path.relpath(os.path.join(folder, file), kms))
    return out


# --- the plan --------------------------------------------------------------------------

def test_the_plan_says_what_goes_with_the_shape(kms):
    plan = delete_plan(load(str(kms)), CUTTER)
    assert plan['name'] == 'iffBaseShacl:StateOnCutterShape'
    assert plan['definedAt'].endswith('shacl.ttl:184')
    assert plan['cases'] == [{'case': 'test_StateOnCutterShape/bad/filter-off.jsonld',
                              'asserts': 1, 'only': True, 'expect': 'invalid'}]
    assert plan['onlyCases'] == ['test_StateOnCutterShape/bad/filter-off.jsonld']
    assert plan['suite'] == 'test_StateOnCutterShape'
    assert plan['suiteEmpties'] is False, 'its good case stays'


def test_a_suite_holding_only_its_cases_is_said_to_empty(kms):
    plan = delete_plan(load(str(kms)), FILTER)
    assert plan['suite'] == 'test_FilterShape' and plan['suiteEmpties'] is True


def test_a_shape_reached_by_another_is_refused(kms):
    shacl = kms / 'shacl.ttl'
    shacl.write_text(_read(shacl) + (
        '\niffBaseShacl:UsesCutterShape a sh:NodeShape ;\n'
        '    sh:targetNode <urn:nothing:1> ;\n'
        f'    sh:node <{CUTTER}> .\n'))
    with pytest.raises(PackageError, match=r'reached from iffBaseShacl:UsesCutterShape \(sh:node\)'):
        delete_plan(load(str(kms)), CUTTER)


def test_a_shape_that_is_a_class_is_refused(kms):
    shacl = kms / 'shacl.ttl'
    shacl.write_text(_read(shacl) +
                     f'\n<{CUTTER}> a <http://www.w3.org/2000/01/rdf-schema#Class> .\n')
    with pytest.raises(PackageError, match='also a class'):
        delete_plan(load(str(kms)), CUTTER)


def test_only_a_shape_is_deleted(kms):
    with pytest.raises(PackageError, match='not a node shape'):
        delete_plan(load(str(kms)), BASE + 'Nothing')


# --- deleting ---------------------------------------------------------------------------

def test_deleted_with_everything_that_named_it_the_package_tests_clean(kms):
    good = kms / 'examples' / 'test_StateOnCutterShape' / 'good' / 'filter-on.jsonld'
    done = delete_shape(load(str(kms)), CUTTER, asserts=True, cases=True)
    assert done['assertsRemoved'] == 1
    assert done['casesRemoved'] == ['test_StateOnCutterShape/bad/filter-off.jsonld']
    assert not (kms / 'examples' / 'test_StateOnCutterShape' / 'bad' / 'filter-off.jsonld').exists()
    assert good.exists(), 'a case asserting nothing about it stays'
    assert _mentions(kms, 'StateOnCutterShape') == []
    after = _semforge('test', str(kms))
    assert after.returncode == 0, after.stdout[-800:]


def test_only_the_shape_s_statement_leaves_the_file(kms):
    """One contiguous piece of the file goes, and it is the shape's statement:
    everything before and after it is byte for byte what it was."""
    text = _read(kms / 'shacl.ttl')
    delete_shape(load(str(kms)), CUTTER, asserts=True, cases=True)
    after = _read(kms / 'shacl.ttl')
    head = 0
    while after[head] == text[head]:
        head += 1
    tail = 0
    while after[-1 - tail] == text[-1 - tail] and len(after) - tail > head:
        tail += 1
    assert len(after) == head + tail, 'nothing but the cut differs'
    gone = text[head:len(text) - tail]
    # (the boundary may slide over a prefix the next statement shares)
    assert gone.count('a sh:NodeShape') == 1 and 'Cutter running without running filter' in gone


def test_the_suite_goes_when_it_holds_no_case_after(kms):
    done = delete_shape(load(str(kms)), FILTER, asserts=True, cases=True)
    assert done['suiteRemoved'] == 'test_FilterShape'
    assert not (kms / 'examples' / 'test_FilterShape').exists()
    assert _semforge('test', str(kms)).returncode == 0


def test_asserts_without_the_cases(kms):
    case = kms / 'examples' / 'test_StateOnCutterShape' / 'bad' / 'filter-off.jsonld'
    done = delete_shape(load(str(kms)), CUTTER, asserts=True)
    assert done['assertsRemoved'] == 1 and done['casesRemoved'] == []
    assert case.exists()
    yaml = _read(case.parent / 'expectations.yaml')
    assert 'path: filter-off.jsonld' in yaml and 'iffBaseShacl:StateOnCutterShape' not in yaml


def test_the_shape_only_leaves_its_asserts_failing(kms):
    delete_shape(load(str(kms)), CUTTER)
    assert _mentions(kms, 'StateOnCutterShape') == [
        os.path.join('examples', 'test_StateOnCutterShape', 'bad', 'expectations.yaml')]
    after = _semforge('test', str(kms))
    assert after.returncode != 0, 'a stale assert is a failure, as the dialog says'


def test_a_case_another_case_includes_keeps_its_file(kms):
    good = kms / 'examples' / 'test_StateOnCutterShape' / 'good' / 'expectations.yaml'
    good.write_text(_read(good).replace(
        '    include:\n', '    include:\n      - test_StateOnCutterShape/bad/filter-off.jsonld\n', 1))
    done = delete_shape(load(str(kms)), CUTTER, asserts=True, cases=True)
    assert done['casesRemoved'] and done['filesRemoved'] == []
    assert (kms / 'examples' / 'test_StateOnCutterShape' / 'bad' / 'filter-off.jsonld').exists()


def test_pinned_residues_that_held_are_pinned_again(kms):
    assert _semforge('accept', str(kms)).returncode == 0
    done = delete_shape(load(str(kms)), CUTTER, asserts=True, cases=True)
    assert done['repinned'], 'the shape left their digest'
    after = _semforge('test', str(kms))
    assert after.returncode == 0, after.stdout[-800:]


def test_a_cut_that_would_change_another_shape_writes_nothing(kms):
    from semforge.cooked import merge

    text = _read(kms / 'shacl.ttl')
    real = merge._knowledge_without_text

    def greedy(source, shape):
        return real(source, shape).replace('sh:minCount 1', 'sh:minCount 0', 1)

    with mock.patch.object(merge, '_knowledge_without_text', greedy), \
            pytest.raises(PackageError, match='more than its own statement'):
        delete_shape(load(str(kms)), CUTTER, asserts=True, cases=True)
    assert _read(kms / 'shacl.ttl') == text
    assert (kms / 'examples' / 'test_StateOnCutterShape' / 'bad' / 'filter-off.jsonld').exists()


# --- the server ------------------------------------------------------------------------

def test_the_server_plans_deletes_and_re_reads(kms):
    from semforge.editor import server

    uri = f'file://{kms}/shacl.ttl'
    with mock.patch.object(server, '_publish'):
        plan = server.delete_shape_plan_feature(mock.MagicMock(), {'uri': uri, 'shape': CUTTER})
        assert plan['ok'] and plan['onlyCases']
        done = server.delete_shape_feature(mock.MagicMock(), {
            'uri': uri, 'shape': CUTTER, 'asserts': True, 'cases': True})
        assert done['ok'] and done['casesRemoved'], done
        again = server.delete_shape_plan_feature(mock.MagicMock(), {'uri': uri, 'shape': CUTTER})
        assert not again['ok'] and 'not a node shape' in again['error']


# --- the extension ----------------------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
PLAN = {'ok': True, 'shape': CUTTER, 'name': 'iffBaseShacl:StateOnCutterShape',
        'file': '/pkg/shacl.ttl', 'definedAt': '/pkg/shacl.ttl:184',
        'cases': [{'case': 'test_S/bad/filter-off.jsonld', 'asserts': 1, 'only': True,
                   'expect': 'invalid'},
                  {'case': 'test_X/bad/two.jsonld', 'asserts': 1, 'only': False,
                   'expect': 'invalid'}],
        'onlyCases': ['test_S/bad/filter-off.jsonld'], 'residues': ['test_S/good/on.jsonld'],
        'suite': 'test_S', 'suiteEmpties': True, 'asserts': 2}
DONE = dict(PLAN, assertsRemoved=2, casesRemoved=['test_S/bad/filter-off.jsonld'],
            filesRemoved=['/pkg/examples/test_S/bad/filter-off.jsonld'],
            suiteRemoved='test_S', repinned=['test_X/good/on.jsonld'])


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


def _delete(tmp_path, answer, plan=PLAN):
    return _drive(tmp_path, {
        'command': 'semforge.deleteShape',
        'node': {'raw': {'kind': 'shape', 'shape': CUTTER}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'answer': answer,
        'replies': {'semforge/deleteShapePlan': plan, 'semforge/deleteShape': DONE}})


def test_delete_says_what_goes_before_writing(tmp_path):
    seen = _delete(tmp_path, None)
    said = seen['warnings'][0]
    assert said.startswith('Delete iffBaseShacl:StateOnCutterShape?')
    for part in ('shacl.ttl: its statement, and the property shapes inside it, go.',
                 '2 assert(s) in 2 test case(s) name its constraints:',
                 'test_S/bad/filter-off.jsonld — asserts nothing else',
                 '1 of them assert nothing else', 'and test_S with them',
                 '"Delete it only" keeps the asserts',
                 '1 case(s) pin a residue', 'open alerts close for good'):
        assert part in said, part
    assert _asked(seen, 'semforge/deleteShape') == [], 'dismissed: nothing written'


@pytest.mark.parametrize('answer, asserts, cases', [
    ('Delete it, its asserts and the cases', True, True),
    ('Delete it and its asserts', True, False),
    ('Delete it only', False, False),
])
def test_each_answer_asks_for_what_it_says(tmp_path, answer, asserts, cases):
    seen = _delete(tmp_path, answer)
    assert _asked(seen, 'semforge/deleteShape') == [{
        'uri': 'file:///pkg/shacl.ttl', 'shape': CUTTER, 'asserts': asserts, 'cases': cases}]
    assert any('StateOnCutterShape deleted' in i for i in seen['info'])


def test_a_shape_nothing_names_asks_one_question(tmp_path):
    plan = dict(PLAN, cases=[], onlyCases=[], residues=[], suite='', suiteEmpties=False,
                asserts=0)
    seen = _delete(tmp_path, 'Delete', plan)
    assert 'assert' not in seen['warnings'][0].split('\n', 1)[1].split('Deployed')[0]
    assert _asked(seen, 'semforge/deleteShape')[0]['asserts'] is False


def test_a_refusal_is_said_and_nothing_written(tmp_path):
    seen = _delete(tmp_path, 'Delete', {'ok': False, 'error': 'iffBaseShacl:S is reached from '
                                        'iffBaseShacl:T (sh:node)'})
    assert seen['errors'] == ['SemForge: iffBaseShacl:S is reached from iffBaseShacl:T (sh:node)']
    assert _asked(seen, 'semforge/deleteShape') == []


def test_the_shape_page_menu_offers_delete(tmp_path):
    page = {'ok': True, 'iri': CUTTER, 'name': 'iffBaseShacl:StateOnCutterShape',
            'label': 'StateOnCutterShape', 'definedAt': '/pkg/shacl.ttl:184', 'targets': [],
            'usedBy': [], 'checks': [], 'attributes': [], 'types': [], 'reach': {'nodes': []},
            'exercisedBy': [], 'summary': {}}
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': {'shape': CUTTER}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'pageMenu', 'row': -1}], 'picks': ['$(trash) Delete…'],
        'replies': {'semforge/shapePage': page}})
    asked = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.deleteShape']
    assert asked[0][0]['raw']['shape'] == CUTTER
