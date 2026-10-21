"""Rename… for a shape, a test case and a suite.

A shape rename must leave a package that tests exactly as before: every
reference, every assert, every pinned residue follows the name. The SDK side
runs on copies of the kms corpus (its files link into semantic-model/kms, so
a copy follows the links); the extension side through the harness.
"""

import json
import os
import shutil
import subprocess
import sys
from unittest import mock

import pytest

from semforge.cooked.rename import rename_case, rename_plan, rename_shape, rename_suite
from semforge.errors import PackageError
from semforge.package import load

BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
CUTTER = BASE + 'StateOnCutterShape'
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


# --- a shape --------------------------------------------------------------------------

def test_the_plan_says_everything_that_names_the_shape(kms):
    plan = rename_plan(load(str(kms)), CUTTER, 'CutterRunningShape-c0ffee12')
    assert plan['name'] == 'iffBaseShacl:StateOnCutterShape'
    assert plan['newCurie'] == 'iffBaseShacl:CutterRunningShape-c0ffee12'
    assert plan['newIri'] == BASE + 'CutterRunningShape-c0ffee12'
    assert [os.path.basename(f['file']) for f in plan['files']] == ['shacl.ttl']
    assert plan['asserts'] == [{'case': 'test_StateOnCutterShape/bad/filter-off.jsonld',
                                'count': 1}]
    assert plan['suite'] == {'from': 'test_StateOnCutterShape',
                             'to': 'test_CutterRunningShape-c0ffee12', 'free': True}


def test_a_renamed_shape_tests_exactly_as_before(kms):
    before = _semforge('test', str(kms))
    assert before.returncode == 0, before.stdout[-600:]
    text = _read(kms / 'shacl.ttl')
    done = rename_shape(load(str(kms)), CUTTER, 'CutterRunningShape-c0ffee12', suite=True)
    assert done['asserts'] == 1 and done['suiteMoved'] == 'test_CutterRunningShape-c0ffee12'
    after = _semforge('test', str(kms))
    assert after.returncode == 0, after.stdout[-600:]
    # Byte-exact: the one name changed, nothing else in the file.
    expected = text.replace('iffBaseShacl:StateOnCutterShape', 'iffBaseShacl:CutterRunningShape-c0ffee12')
    assert _read(kms / 'shacl.ttl') == expected
    assert (kms / 'examples' / 'test_CutterRunningShape-c0ffee12' / 'bad' / 'filter-off.jsonld').exists()
    assert not (kms / 'examples' / 'test_StateOnCutterShape').exists()
    asserts = _read(kms / 'examples' / 'test_CutterRunningShape-c0ffee12' / 'bad' / 'expectations.yaml')
    assert 'iffBaseShacl:CutterRunningShape-c0ffee12/SPARQLConstraintComponent' in asserts
    assert 'iffBaseShacl:StateOnCutterShape/' not in asserts


def test_the_suite_keeps_its_name_unless_asked(kms):
    rename_shape(load(str(kms)), CUTTER, 'CutterRunningShape-c0ffee12')
    assert (kms / 'examples' / 'test_StateOnCutterShape').is_dir()
    assert _semforge('test', str(kms)).returncode == 0


def test_references_from_other_shapes_and_queries_follow(kms):
    shacl = kms / 'shacl.ttl'
    shacl.write_text(_read(shacl) + (
        '\niffBaseShacl:UsesCutterShape a sh:NodeShape ;\n'
        '    sh:targetNode <urn:nothing:1> ;\n'
        '    sh:node <' + CUTTER + '> ;\n'
        '    sh:sparql [ sh:select """SELECT $this WHERE { $this a iffBaseShacl:StateOnCutterShape }""" ] .\n'))
    plan = rename_plan(load(str(kms)), CUTTER, 'CutterRunningShape-c0ffee12')
    assert plan['files'][0]['references'] == 3 and plan['files'][0]['inQueries'] == 1
    rename_shape(load(str(kms)), CUTTER, 'CutterRunningShape-c0ffee12')
    text = _read(shacl)
    assert 'sh:node <' + BASE + 'CutterRunningShape-c0ffee12> ;' in text, 'an <IRI> stays one'
    assert '$this a iffBaseShacl:CutterRunningShape-c0ffee12 }' in text
    assert 'StateOnCutterShape' not in text


def test_pinned_residues_that_held_are_pinned_again(kms):
    accepted = _semforge('accept', str(kms))
    assert accepted.returncode == 0, accepted.stderr
    done = rename_shape(load(str(kms)), CUTTER, 'CutterRunningShape-c0ffee12', suite=True)
    assert done['repinned'], 'the digest names the shape: its cases changed residue'
    assert all(p.startswith('test_') for p in done['repinned'])
    after = _semforge('test', str(kms))
    assert after.returncode == 0, after.stdout[-800:]


def test_a_case_failing_before_is_left_failing(kms):
    assert _semforge('accept', str(kms)).returncode == 0
    yaml = kms / 'examples' / 'test_StateOnCutterShape' / 'good' / 'expectations.yaml'
    text = _read(yaml)
    pinned = text.split('residue: ', 1)[1].split('\n', 1)[0]
    yaml.write_text(text.replace(pinned, 'sha256:' + '0' * 64, 1))
    done = rename_shape(load(str(kms)), CUTTER, 'CutterRunningShape-c0ffee12')
    assert 'test_StateOnCutterShape/good/filter-on.jsonld' not in done['repinned']
    assert 'sha256:' + '0' * 64 in _read(yaml), 'what it said is kept'


def test_a_rewrite_that_changes_more_than_the_name_writes_nothing(kms):
    """The check after the rewrite is what makes it safe: a statement lost
    on the way is caught before any file is touched."""
    from semforge.cooked import rename

    text = _read(kms / 'shacl.ttl')
    real = rename._renamed_text

    def lossy(*args, **kwargs):
        return real(*args, **kwargs).replace('sh:severity', 'sh:message', 1)

    with mock.patch.object(rename, '_renamed_text', lossy), \
            pytest.raises(PackageError, match='more than its name'):
        rename_shape(load(str(kms)), CUTTER, 'CutterRunningShape-c0ffee12', suite=True)
    assert _read(kms / 'shacl.ttl') == text
    assert (kms / 'examples' / 'test_StateOnCutterShape').is_dir()


@pytest.mark.parametrize('name, said', [
    ('FilterShape', 'already a shape'),
    ('2Shape', 'not a shape name'),
    ('Bad Name', 'not a shape name'),
    ('Ends.', 'not a shape name'),
])
def test_a_shape_rename_is_refused_when_it_cannot_be_right(kms, name, said):
    with pytest.raises(PackageError, match=said):
        rename_plan(load(str(kms)), CUTTER, name)


def test_a_shape_that_is_a_class_is_not_renamed(kms):
    shacl = kms / 'shacl.ttl'
    shacl.write_text(_read(shacl) +
                     f'\n<{CUTTER}> a <http://www.w3.org/2000/01/rdf-schema#Class> .\n')
    with pytest.raises(PackageError, match='also a class'):
        rename_plan(load(str(kms)), CUTTER, 'CutterRunningShape-c0ffee12')


def test_only_a_shape_is_renamed(kms):
    with pytest.raises(PackageError, match='not a node shape'):
        rename_plan(load(str(kms)), BASE + 'Nothing', 'Other')


# --- cases and suites -------------------------------------------------------------------

def test_a_renamed_case_keeps_its_claims(kms):
    done = rename_case(load(str(kms)), 'test_StateOnCutterShape/bad/filter-off.jsonld',
                       'filter-switched-off')
    assert done['case'] == 'test_StateOnCutterShape/bad/filter-switched-off.jsonld'
    folder = kms / 'examples' / 'test_StateOnCutterShape' / 'bad'
    assert (folder / 'filter-switched-off.jsonld').exists()
    assert not (folder / 'filter-off.jsonld').exists()
    yaml = _read(folder / 'expectations.yaml')
    assert 'path: filter-switched-off.jsonld' in yaml and 'SPARQLConstraintComponent' in yaml
    assert _semforge('test', str(kms)).returncode == 0


def test_a_case_is_found_by_its_file_too(kms):
    file = kms / 'examples' / 'test_StateOnCutterShape' / 'bad' / 'filter-off.jsonld'
    done = rename_case(load(str(kms)), str(file), 'off.jsonld')
    assert done['file'].endswith('/bad/off.jsonld'), '.jsonld is not doubled'


def test_includes_naming_a_renamed_case_follow(kms):
    good = kms / 'examples' / 'test_StateOnCutterShape' / 'good' / 'expectations.yaml'
    good.write_text(_read(good).replace(
        '    include:\n', '    include:\n      - test_StateOnCutterShape/bad/filter-off.jsonld\n', 1))
    done = rename_case(load(str(kms)), 'test_StateOnCutterShape/bad/filter-off.jsonld', 'off')
    assert done['includes'] == 1
    assert '- test_StateOnCutterShape/bad/off.jsonld' in _read(good)
    assert '- subobjects/filter-on.jsonld' in _read(good), 'the other includes stay'


@pytest.mark.parametrize('case, name, said', [
    ('test_StateOnCutterShape/bad/filter-off.jsonld', 'filter-off', 'already its name'),
    ('test_StateOnCutterShape/bad/nothing.jsonld', 'x', 'not a case file'),
    ('../shacl.ttl', 'x', 'not a case file'),
    ('test_StateOnCutterShape/bad/filter-off.jsonld', 'a/b', 'not a case name'),
])
def test_a_case_rename_is_refused_when_it_cannot_be_right(kms, case, name, said):
    with pytest.raises(PackageError, match=said):
        rename_case(load(str(kms)), case, name)


def test_a_case_cannot_take_a_neighbour_s_name(kms):
    folder = kms / 'examples' / 'test_StateOnCutterShape' / 'bad'
    (folder / 'taken.jsonld').write_text('{}')
    with pytest.raises(PackageError, match='already exists'):
        rename_case(load(str(kms)), 'test_StateOnCutterShape/bad/filter-off.jsonld', 'taken')


def test_an_undeclared_file_is_not_a_case(kms):
    folder = kms / 'examples' / 'test_StateOnCutterShape' / 'bad'
    (folder / 'loose.jsonld').write_text('{}')
    with pytest.raises(PackageError, match='not declared'):
        rename_case(load(str(kms)), 'test_StateOnCutterShape/bad/loose.jsonld', 'kept')
    assert (folder / 'loose.jsonld').exists(), 'nothing moved'


def test_a_renamed_suite_tests_as_before(kms):
    done = rename_suite(load(str(kms)), 'test_FilterShape', 'filter_suite')
    assert done['suite'] == 'filter_suite' and done['from'] == 'test_FilterShape'
    assert (kms / 'examples' / 'filter_suite' / 'bad').is_dir()
    assert _semforge('test', str(kms)).returncode == 0


def test_includes_reaching_into_a_renamed_suite_follow(kms):
    good = kms / 'examples' / 'test_StateOnCutterShape' / 'good' / 'expectations.yaml'
    good.write_text(_read(good).replace(
        '    include:\n', '    include:\n      - test_FilterShape/bad/without-cartridge.jsonld\n', 1))
    done = rename_suite(load(str(kms)), 'test_FilterShape', 'filter_suite')
    assert done['includes'] == 1
    assert '- filter_suite/bad/without-cartridge.jsonld' in _read(good)


@pytest.mark.parametrize('suite, name, said', [
    ('test_FilterShape/bad', 'worse', 'good/ and bad/'),
    ('test_FilterShape', 'test_StateOnCutterShape', 'already exists'),
    ('test_Nothing', 'x', 'not a suite folder'),
    ('test_FilterShape', 'a/b', 'not a suite name'),
])
def test_a_suite_rename_is_refused_when_it_cannot_be_right(kms, suite, name, said):
    with pytest.raises(PackageError, match=said):
        rename_suite(load(str(kms)), suite, name)


# --- the server ------------------------------------------------------------------------

def test_the_server_renames_and_re_reads(kms):
    from semforge.editor import server

    uri = f'file://{kms}/shacl.ttl'
    with mock.patch.object(server, '_publish'):
        plan = server.rename_shape_plan_feature(mock.MagicMock(), {
            'uri': uri, 'shape': CUTTER, 'name': 'CutterRunningShape-c0ffee12'})
        assert plan['ok'] and plan['suite']['free']
        refused = server.rename_shape_feature(mock.MagicMock(), {
            'uri': uri, 'shape': CUTTER, 'name': 'FilterShape'})
        assert not refused['ok'] and 'already a shape' in refused['error']
        done = server.rename_shape_feature(mock.MagicMock(), {
            'uri': uri, 'shape': CUTTER, 'name': 'CutterRunningShape-c0ffee12', 'suite': True})
        assert done['ok'] and done['suiteMoved']
        case = server.rename_case_feature(mock.MagicMock(), {
            'uri': uri, 'case': 'test_CutterRunningShape-c0ffee12/bad/filter-off.jsonld', 'name': 'off'})
        assert case['ok'], case
        suite = server.rename_suite_feature(mock.MagicMock(), {
            'uri': uri, 'suite': 'test_CutterRunningShape-c0ffee12', 'name': 'cutter'})
        assert suite['ok'], suite
        # The package is read again: the next request sees the new names.
        again = server.rename_shape_plan_feature(mock.MagicMock(), {
            'uri': uri, 'shape': BASE + 'CutterRunningShape-c0ffee12', 'name': 'StateOnCutterShape'})
        assert again['ok'] and again['suite'] is None


# --- the extension ----------------------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
PLAN = {'ok': True, 'shape': CUTTER, 'name': 'iffBaseShacl:StateOnCutterShape',
        'oldName': 'StateOnCutterShape', 'newName': 'CutterRunningShape-c0ffee12',
        'newIri': BASE + 'CutterRunningShape-c0ffee12', 'newCurie': 'iffBaseShacl:CutterRunningShape-c0ffee12',
        'files': [{'file': '/pkg/shacl.ttl', 'references': 2, 'inQueries': 1}],
        'asserts': [{'case': 'test_StateOnCutterShape/bad/filter-off.jsonld', 'count': 1}],
        'residues': ['test_StateOnCutterShape/good/filter-on.jsonld'],
        'suite': {'from': 'test_StateOnCutterShape', 'to': 'test_CutterRunningShape-c0ffee12',
                  'free': True}}
DONE = dict(PLAN, asserts=1, repinned=['test_CutterRunningShape-c0ffee12/good/filter-on.jsonld'],
            suiteMoved='test_CutterRunningShape-c0ffee12', files=['/pkg/shacl.ttl'])


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


def _rename(tmp_path, answer, **scenario):
    return _drive(tmp_path, dict({
        'command': 'semforge.renameShape',
        'node': {'raw': {'kind': 'shape', 'shape': CUTTER}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'inputs': ['CutterRunningShape-c0ffee12'], 'answer': answer,
        'replies': {'semforge/renameShapePlan': PLAN, 'semforge/renameShape': DONE}},
        **scenario))


def test_rename_shape_says_the_plan_before_writing(tmp_path):
    seen = _rename(tmp_path, None)
    said = seen['warnings'][0]
    assert said.startswith('Rename iffBaseShacl:StateOnCutterShape to '
                           'iffBaseShacl:CutterRunningShape-c0ffee12?')
    for part in ('shacl.ttl: 2 reference(s), 1 of them in a SPARQL query',
                 '1 assert(s) in 1 test case(s) name it',
                 '1 case(s) pin a residue',
                 'test_StateOnCutterShape can be renamed to test_CutterRunningShape-c0ffee12 too'):
        assert part in said, part
    assert _asked(seen, 'semforge/renameShape') == [], 'dismissed: nothing written'


def test_rename_shape_with_its_suite(tmp_path):
    seen = _rename(tmp_path, 'Rename it and test_StateOnCutterShape')
    assert _asked(seen, 'semforge/renameShape') == [{
        'uri': 'file:///pkg/shacl.ttl', 'shape': CUTTER, 'name': 'CutterRunningShape-c0ffee12',
        'suite': True}]
    opened = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openShapePage']
    assert opened[0][0]['raw']['shape'] == BASE + 'CutterRunningShape-c0ffee12'
    assert any('StateOnCutterShape is now CutterRunningShape-c0ffee12' in i and
               '1 residue(s) pinned again' in i for i in seen['info'])


def test_rename_shape_alone(tmp_path):
    seen = _rename(tmp_path, 'Rename')
    assert _asked(seen, 'semforge/renameShape')[0]['suite'] is False


def test_rename_shape_reports_a_refusal(tmp_path):
    seen = _rename(tmp_path, 'Rename', replies={
        'semforge/renameShapePlan': {'ok': False, 'error': 'FilterShape is already a shape'}})
    assert seen['errors'] == ['SemForge: FilterShape is already a shape']
    assert _asked(seen, 'semforge/renameShape') == []


def test_the_name_box_refuses_what_cannot_be_a_name(tmp_path):
    seen = _rename(tmp_path, None, inputs=['StateOnCutterShape'])
    validate = seen['inputs'][0]
    assert validate['value'] == 'StateOnCutterShape', 'the box starts with the old name'


def test_rename_case(tmp_path):
    file = '/pkg/examples/test_S/bad/filter-off.jsonld'
    seen = _drive(tmp_path, {
        'command': 'semforge.renameTestCase',
        'node': {'raw': {'kind': 'example', 'file': file}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'inputs': ['filter-switched-off'],
        'replies': {'semforge/renameCase': {
            'ok': True, 'file': '/pkg/examples/test_S/bad/filter-switched-off.jsonld',
            'case': 'test_S/bad/filter-switched-off.jsonld', 'from': 'test_S/bad/filter-off.jsonld',
            'includes': 0}}})
    assert _asked(seen, 'semforge/renameCase') == [{
        'uri': 'file:///pkg/shacl.ttl', 'case': file, 'name': 'filter-switched-off'}]
    opened = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openCasePage']
    assert opened[0][0]['raw']['file'].endswith('filter-switched-off.jsonld')


def test_rename_suite_uses_its_folder_not_its_label(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.renameSuite',
        'node': {'raw': {'kind': 'suite', 'label': 'FilterShape', 'term': 'test_FilterShape'},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'inputs': ['filter_suite'],
        'replies': {'semforge/renameSuite': {
            'ok': True, 'folder': '/pkg/examples/filter_suite',
            'source': '/pkg/examples/test_FilterShape', 'suite': 'filter_suite',
            'from': 'test_FilterShape', 'includes': 0}}})
    assert _asked(seen, 'semforge/renameSuite') == [{
        'uri': 'file:///pkg/shacl.ttl', 'suite': 'test_FilterShape', 'name': 'filter_suite'}]
    assert seen['inputs'][0]['value'] == 'test_FilterShape'


def test_the_case_page_menu_offers_rename(tmp_path):
    page = {'ok': True, 'kind': 'case', 'name': 'filter-off.jsonld', 'expect': 'invalid',
            'passed': True, 'file': '/pkg/examples/test_S/bad/filter-off.jsonld',
            'expectations': '/pkg/examples/test_S/bad/expectations.yaml',
            'claims': [], 'unasserted': [], 'files': [], 'summary': {}, 'failures': []}
    seen = _drive(tmp_path, {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'file': page['file']},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'pageMenu'}], 'picks': ['$(edit) Rename…'],
        'replies': {'semforge/casePage': page}})
    html = seen['webviews'][0]['html'][0]
    assert 'data-pagemenu="1"' in html and 'Open the case file</button>' not in html
    assert [i['label'] for i in seen['quickPicks'][0]['items']] == [
        '$(go-to-file) Open the case file', '$(list-unordered) Open its expectations',
        '$(copy) Clone…', '$(edit) Rename…', '$(trash) Delete…', '$(refresh) Refresh']
    asked = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.renameTestCase']
    assert asked[0][0]['raw']['file'] == page['file']


def test_the_shape_page_menu_offers_rename(tmp_path):
    from semforge.cooked.shapepage import build_shape_page  # noqa: F401  (payload shape)

    page = {'ok': True, 'iri': CUTTER, 'name': 'iffBaseShacl:StateOnCutterShape',
            'label': 'StateOnCutterShape', 'definedAt': '/pkg/shacl.ttl:9', 'targets': [],
            'usedBy': [], 'checks': [], 'attributes': [], 'types': [], 'reach': {'nodes': []},
            'exercisedBy': [], 'summary': {}}
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': {'shape': CUTTER}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'pageMenu', 'row': -1}], 'picks': ['$(edit) Rename…'],
        'replies': {'semforge/shapePage': page}})
    asked = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.renameShape']
    assert asked[0][0]['raw']['shape'] == CUTTER
