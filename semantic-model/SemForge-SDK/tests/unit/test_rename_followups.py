"""A shape renamed by typing in the .ttl, and the asserts it leaves behind.

Three defences, each tested here on a copy of the kms corpus renamed by hand
the way an author would (a text replace in shacl.ttl):

* a stale assert says which constraint it most likely meant, and is fixed
  in one step -- in the Problems panel and on the case page;
* the server notices the rename when the file is saved and offers to carry
  the asserts, residues and suite along;
* F2 on a shape's name finds the shape, so the rename goes through Rename…
  in the first place.
"""

import json
import os
import shutil
import subprocess
import sys
from unittest import mock

import pytest

from semforge.cooked.rename import (follow_plan, follow_rename, renamed_pairs,
                                    shape_prints)
from semforge.expect.stale import retarget_assert, suggestion
from semforge.package import load

BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
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


def _rename_by_hand(kms, old, new):
    """What an author does in the editor: the name, replaced in shacl.ttl only."""
    shacl = kms / 'shacl.ttl'
    shacl.write_text(_read(shacl).replace(f'iffBaseShacl:{old} ', f'iffBaseShacl:{new} '))


def _test(kms):
    return subprocess.run([SEMFORGE, 'test', str(kms)], capture_output=True, text=True)


# --- the suggestion ---------------------------------------------------------------------

def test_one_shape_declaring_the_same_constraint_is_the_suggestion():
    known = {'ns:New/hasA/MinCountConstraintComponent', 'ns:Other/hasB/MinCountConstraintComponent'}
    assert suggestion('ns:Old/hasA/MinCountConstraintComponent', known) == \
        'ns:New/hasA/MinCountConstraintComponent'


def test_several_candidates_need_the_case_s_results_to_decide():
    known = {'ns:A/SPARQLConstraintComponent', 'ns:B/SPARQLConstraintComponent'}
    stale = 'ns:Old/SPARQLConstraintComponent'
    assert suggestion(stale, known) == '', 'two shapes could be meant'
    assert suggestion(stale, known, firing=['ns:B/SPARQLConstraintComponent']) == \
        'ns:B/SPARQLConstraintComponent'
    assert suggestion(stale, known, firing=[]) == ''


# --- the Problems panel ------------------------------------------------------------------

def test_a_hand_rename_s_stale_assert_names_what_it_meant(kms):
    from semforge.sanity import sanity as check

    _rename_by_hand(kms, 'FilterShape', 'FilterCheckShape')
    finding = next(f for f in check(load(str(kms))) if f.code == 'stale-assert')
    assert finding.subject == 'iffBaseShacl:FilterShape/hasCartridge/MinCountConstraintComponent'
    assert finding.fix['suggest'] == 'iffBaseShacl:FilterCheckShape/hasCartridge/MinCountConstraintComponent'
    assert 'Renamed? iffBaseShacl:FilterCheckShape/hasCartridge/MinCountConstraintComponent' \
        in finding.message


def test_the_quick_fixes_put_the_rename_first():
    from lsprotocol import types

    from semforge.editor import server

    diagnostic = types.Diagnostic(
        range=types.Range(types.Position(3, 0), types.Position(3, 9)), message='stale',
        source='semforge',
        data={'code': 'stale-assert', 'subject': 'ns:Old/hasA/X', 'file': '/e.yaml',
              'case': 'c.jsonld', 'index': 1, 'suggest': 'ns:New/hasA/X'})
    actions = server._fixes_for(diagnostic, 'file:///pkg/shacl.ttl')
    assert [a.title for a in actions] == ['Rename the assert to ns:New/hasA/X', 'Remove this assert']
    assert actions[0].is_preferred and not actions[1].is_preferred
    assert actions[0].command.arguments[0]['kind'] == 'retarget'
    assert actions[0].command.arguments[0]['constraint'] == 'ns:New/hasA/X'


def test_retargeting_the_assert_makes_the_case_pass_again(kms):
    from semforge.editor import server

    _rename_by_hand(kms, 'FilterShape', 'FilterCheckShape')
    assert _test(kms).returncode != 0, 'the stale assert fails the case'
    yaml = kms / 'examples' / 'test_FilterShape' / 'bad' / 'expectations.yaml'
    with mock.patch.object(server, '_publish'):
        done = server.remove_use_feature(mock.MagicMock(), {
            'uri': f'file://{kms}/shacl.ttl', 'kind': 'retarget', 'file': str(yaml),
            'case': 'without-cartridge.jsonld', 'index': 0,
            'constraint': 'iffBaseShacl:FilterCheckShape/hasCartridge/MinCountConstraintComponent'})
    assert done['ok'], done
    assert 'iffBaseShacl:FilterCheckShape/hasCartridge/MinCountConstraintComponent' in _read(yaml)
    after = _test(kms)
    assert after.returncode == 0, after.stdout[-600:]


def test_a_retarget_onto_an_assert_the_case_already_has_removes_the_duplicate(tmp_path):
    yaml = tmp_path / 'expectations.yaml'
    yaml.write_text('examples:\n  - path: c.jsonld\n    expect: invalid\n    asserts:\n'
                    '      - constraint: ns:Old/hasA/X\n        resource: urn:a\n'
                    '      - constraint: ns:New/hasA/X\n        resource: urn:a\n')
    note = retarget_assert(str(yaml), 'c.jsonld', 0, 'ns:New/hasA/X')
    assert 'already asserted' in note
    assert _read(yaml).count('ns:New/hasA/X') == 1 and 'ns:Old' not in _read(yaml)


# --- the case page -----------------------------------------------------------------------

def test_the_case_page_narrows_the_guess_by_what_fires(kms):
    from semforge.cooked.casepage import build_case_page

    _rename_by_hand(kms, 'StateOnCutterShape', 'CutterRunningShape')
    case = kms / 'examples' / 'test_StateOnCutterShape' / 'bad' / 'filter-off.jsonld'
    page = build_case_page(load(str(kms)), str(case))
    claim = page['claims'][0]
    assert claim['stale'] and not claim['holds']
    # Four shapes have a SPARQL constraint; only one fires on this cutter.
    assert claim['suggest'] == 'iffBaseShacl:CutterRunningShape/SPARQLConstraintComponent'
    assert claim['entry'] == 'filter-off.jsonld' and claim['index'] == 0


DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')


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


STALE_PAGE = {'ok': True, 'kind': 'case', 'name': 'filter-off.jsonld', 'case': 'test_S/bad/filter-off.jsonld',
              'expect': 'invalid', 'passed': False, 'file': '/pkg/examples/test_S/bad/filter-off.jsonld',
              'expectations': '/pkg/examples/test_S/bad/expectations.yaml',
              'claims': [{'constraint': 'ns:Old/SPARQLConstraintComponent', 'resource': 'urn:c:1',
                          'holds': False, 'explained': None, 'stale': True,
                          'suggest': 'ns:New/SPARQLConstraintComponent', 'entry': 'filter-off.jsonld',
                          'index': 0}],
              'unasserted': [], 'files': [], 'summary': {}, 'failures': ['stale']}


@pytest.mark.parametrize('command, kind', [('retargetAssert', 'retarget'), ('removeAssert', 'assert')])
def test_the_case_page_fixes_a_stale_assert(tmp_path, command, kind):
    seen = _drive(tmp_path, {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'file': STALE_PAGE['file']},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': command, 'index': 0}],
        'replies': {'semforge/casePage': STALE_PAGE, 'semforge/removeUse': {'ok': True}}})
    html = seen['webviews'][0]['html'][0]
    assert 'names no shape' in html and 'data-retarget="0"' in html and 'Rename to New' in html
    assert _asked(seen, 'semforge/removeUse') == [{
        'uri': 'file:///pkg/shacl.ttl', 'kind': kind, 'file': STALE_PAGE['expectations'],
        'case': 'filter-off.jsonld', 'index': 0, 'constraint': 'ns:New/SPARQLConstraintComponent'}]
    assert len(seen['webviews'][0]['html']) == 2, 'the page shows the result'


# --- noticing the rename on save --------------------------------------------------------

def test_a_hand_rename_is_recognised_by_what_the_shape_says(kms):
    before = shape_prints(load(str(kms)))
    _rename_by_hand(kms, 'StateOnCutterShape', 'CutterRunningShape')
    after = shape_prints(load(str(kms)))
    assert renamed_pairs(before, after) == [(BASE + 'StateOnCutterShape', BASE + 'CutterRunningShape')]


def test_a_shape_that_also_changed_is_not_called_a_rename(kms):
    before = shape_prints(load(str(kms)))
    shacl = kms / 'shacl.ttl'
    _rename_by_hand(kms, 'StateOnCutterShape', 'CutterRunningShape')
    shacl.write_text(_read(shacl).replace('base:severityCritical', 'base:severityWarning', 1))
    assert renamed_pairs(before, shape_prints(load(str(kms)))) == []


def test_two_identical_shapes_are_not_guessed_between():
    before = {'a': 'same', 'b': 'same'}
    after = {'c': 'same', 'd': 'same'}
    assert renamed_pairs(before, after) == []


def test_following_the_rename_carries_asserts_residues_and_suite(kms):
    assert _semforge_accept(kms).returncode == 0
    _rename_by_hand(kms, 'StateOnCutterShape', 'CutterRunningShape')
    assert _test(kms).returncode != 0
    package = load(str(kms))
    plan = follow_plan(package, BASE + 'StateOnCutterShape', BASE + 'CutterRunningShape')
    assert plan['asserts'] == 1 and plan['suite'] == {
        'from': 'test_StateOnCutterShape', 'to': 'test_CutterRunningShape', 'free': True}
    done = follow_rename(package, BASE + 'StateOnCutterShape', BASE + 'CutterRunningShape',
                         suite=True)
    assert done['asserts'] == 1 and done['suiteMoved'] == 'test_CutterRunningShape'
    assert done['repinned'], 'the residues it contributed to were pinned under the old name'
    after = _test(kms)
    assert after.returncode == 0, after.stdout[-800:]


def test_a_residue_that_changed_for_another_reason_is_not_pinned_again(kms):
    assert _semforge_accept(kms).returncode == 0
    yaml = kms / 'examples' / 'test_StateOnCutterShape' / 'good' / 'expectations.yaml'
    text = _read(yaml)
    pinned = text.split('residue: ', 1)[1].split('\n', 1)[0]
    yaml.write_text(text.replace(pinned, 'sha256:' + '1' * 64, 1))
    _rename_by_hand(kms, 'StateOnCutterShape', 'CutterRunningShape')
    done = follow_rename(load(str(kms)), BASE + 'StateOnCutterShape', BASE + 'CutterRunningShape')
    assert 'test_StateOnCutterShape/good/filter-on.jsonld' not in done['repinned']


def _semforge_accept(kms):
    return subprocess.run([SEMFORGE, 'accept', str(kms)], capture_output=True, text=True)


def test_the_server_offers_it_after_the_save(kms):
    from semforge.editor import server

    root = str(kms)
    uri = f'file://{kms}/shacl.ttl'
    for table in (server._packages, server._stamps, server._shape_prints, server._pending_renames):
        table.pop(root, None)
    server._package_for(root)                       # the package as it was read
    _rename_by_hand(kms, 'StateOnCutterShape', 'CutterRunningShape')
    ls = mock.MagicMock()
    with mock.patch.object(server, '_publish'):
        server.did_save(ls, mock.MagicMock(text_document=mock.MagicMock(uri=uri)))
    ls.protocol.notify.assert_called_once()
    method, notice = ls.protocol.notify.call_args[0]
    assert method == 'semforge/shapeRenamed'
    assert notice['oldName'] == 'StateOnCutterShape' and notice['newName'] == 'CutterRunningShape'
    assert notice['asserts'] == 1 and notice['suite']['free']
    # Offered once: the next save says nothing more.
    ls2 = mock.MagicMock()
    with mock.patch.object(server, '_publish'):
        server.did_save(ls2, mock.MagicMock(text_document=mock.MagicMock(uri=uri)))
    ls2.protocol.notify.assert_not_called()


def test_semforge_s_own_rename_is_not_offered_again(kms):
    from semforge.editor import server

    root = str(kms)
    uri = f'file://{kms}/shacl.ttl'
    for table in (server._packages, server._stamps, server._shape_prints, server._pending_renames):
        table.pop(root, None)
    server._package_for(root)
    with mock.patch.object(server, '_publish'):
        done = server.rename_shape_feature(mock.MagicMock(), {
            'uri': uri, 'shape': BASE + 'StateOnCutterShape', 'name': 'CutterRunningShape'})
        assert done['ok']
        ls = mock.MagicMock()
        server.did_save(ls, mock.MagicMock(text_document=mock.MagicMock(uri=uri)))
    ls.protocol.notify.assert_not_called(), 'the suite was kept on purpose'


NOTICE = {'shape': BASE + 'StateOnCutterShape', 'newIri': BASE + 'CutterRunningShape',
          'name': 'iffBaseShacl:StateOnCutterShape', 'newCurie': 'iffBaseShacl:CutterRunningShape',
          'oldName': 'StateOnCutterShape', 'newName': 'CutterRunningShape', 'asserts': 1,
          'suite': {'from': 'test_StateOnCutterShape', 'to': 'test_CutterRunningShape', 'free': True},
          'uri': 'file:///pkg/shacl.ttl'}


@pytest.mark.parametrize('answer, suite', [('Update them', False),
                                           ('Update them and rename test_StateOnCutterShape', True)])
def test_the_extension_offers_to_follow_the_rename(tmp_path, answer, suite):
    seen = _drive(tmp_path, {
        'notify': [{'method': 'semforge/shapeRenamed', 'params': NOTICE}], 'answer': answer,
        'replies': {'semforge/followRename': {'ok': True, 'asserts': 1, 'repinned': ['x'],
                                              'suiteMoved': 'test_CutterRunningShape' if suite else ''}}})
    assert seen['errors'] == [], seen['errors']
    said = seen['info'][0]
    assert said.startswith('SemForge: StateOnCutterShape is gone and CutterRunningShape says '
                           'exactly what it said. Renamed?')
    assert '1 assert(s) still name iffBaseShacl:StateOnCutterShape' in said
    assert _asked(seen, 'semforge/followRename') == [{
        'uri': 'file:///pkg/shacl.ttl', 'shape': NOTICE['shape'], 'newIri': NOTICE['newIri'],
        'suite': suite}]


def test_dismissed_nothing_is_written(tmp_path):
    seen = _drive(tmp_path, {'notify': [{'method': 'semforge/shapeRenamed', 'params': NOTICE}],
                             'replies': {}})
    assert _asked(seen, 'semforge/followRename') == []


# --- F2 on a shape's name ----------------------------------------------------------------

def _shape_at(kms, line, character):
    from semforge.editor import server

    ls = mock.MagicMock()
    ls.workspace.get_text_document.side_effect = Exception('not open')
    return server.shape_at_feature(ls, {'uri': f'file://{kms}/shacl.ttl', 'line': line,
                                        'character': character})


def test_f2_finds_the_shape_under_the_cursor(kms):
    lines = _read(kms / 'shacl.ttl').splitlines()
    line = next(i for i, text in enumerate(lines)
                if text.startswith('iffBaseShacl:StateOnCutterShape a'))
    at = _shape_at(kms, line, 20)
    assert at['ok'] and at['shape'] == BASE + 'StateOnCutterShape'
    assert at['placeholder'] == 'StateOnCutterShape'
    assert at['range'] == {'start': {'line': line, 'character': len('iffBaseShacl:')},
                           'end': {'line': line, 'character': len('iffBaseShacl:StateOnCutterShape')}}


def test_f2_elsewhere_says_what_it_renames(kms):
    lines = _read(kms / 'shacl.ttl').splitlines()
    line = next(i for i, text in enumerate(lines) if 'sh:targetClass' in text)
    at = _shape_at(kms, line, 8)
    assert not at['ok'] and 'F2 renames a shape' in at['error']


def test_f2_s_rename_runs_rename_with_the_name_given():
    """The provider hands F2's name to Rename… -- the same plan, question and
    write -- and returns no text edit of its own."""
    rename_js = _read(os.path.join(SRC, 'rename.js'))
    provider = rename_js.split('const RENAME_PROVIDER', 1)[1].split('\n});', 1)[0]
    assert "renameShape(clientHolder, session," in provider and 'bench, newName)' in provider
    assert 'return new vscode.WorkspaceEdit();' in provider
    assert 'await document.save();' in provider


# --- over the wire ---------------------------------------------------------------------

def test_the_real_server_notices_a_rename_typed_and_saved(kms):
    """Open, type, save -- as an editor does, to a server on stdio. The views
    come from the disk cache and the diagnostics reload the package on their
    own path; both once hid the rename (no "before", or a reload that skipped
    the comparison), which only a real server shows."""
    from test_lsp_protocol import Session

    doc = str(kms / 'shacl.ttl')
    uri = 'file://' + doc
    session = Session(doc)
    try:
        session.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                      'params': {'processId': os.getpid(), 'rootUri': f'file://{kms}',
                                 'capabilities': {}}})
        assert session.wait_for(lambda m: m.get('id') == 1)
        session.send({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})
        text = _read(doc)
        session.send({'jsonrpc': '2.0', 'method': 'textDocument/didOpen', 'params': {
            'textDocument': {'uri': uri, 'languageId': 'turtle', 'version': 1, 'text': text}}})
        # The open is handled (the diagnostics come after the "before" is
        # taken) before anything is typed -- as in an editor, where typing
        # and saving come long after opening.
        assert session.wait_for(lambda m: m.get('method') == 'textDocument/publishDiagnostics', 120)
        renamed = text.replace('iffBaseShacl:CartridgeShape ', 'iffBaseShacl:CartridgeCheckShape ')
        session.send({'jsonrpc': '2.0', 'method': 'textDocument/didChange', 'params': {
            'textDocument': {'uri': uri, 'version': 2}, 'contentChanges': [{'text': renamed}]}})
        (kms / 'shacl.ttl').write_text(renamed)
        session.send({'jsonrpc': '2.0', 'method': 'textDocument/didSave',
                      'params': {'textDocument': {'uri': uri}}})
        got = session.wait_for(lambda m: m.get('method') == 'semforge/shapeRenamed', 120)
        assert got, 'no offer after the save'
        notice = got[0]['params']
        assert (notice['oldName'], notice['newName']) == ('CartridgeShape', 'CartridgeCheckShape')
        assert notice['asserts'] == 1
    finally:
        session.close()
