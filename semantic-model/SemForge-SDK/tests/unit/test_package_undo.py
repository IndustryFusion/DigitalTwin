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

"""Undo and redo over a package's own git history."""

import json
import os
import shutil

import pytest

from semforge.editor import edits
from semforge.package import history


@pytest.fixture
def package(tmp_path, corpus_path, monkeypatch):
    monkeypatch.delenv('SEMFORGE_HISTORY', raising=False)
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge', '.git', history.NO_HISTORY))
    history.ensure(str(target))
    return str(target)


def _edit(package, text, title='SemForge edit'):
    with open(os.path.join(package, 'kms.yaml'), 'a') as handle:
        handle.write(f'\n# {text}\n')
    return history.ensure(package, title)


def _yaml(package):
    with open(os.path.join(package, 'kms.yaml')) as handle:
        return handle.read()


def test_undo_then_redo_is_where_it_was(package):
    start = _yaml(package)
    _edit(package, 'one')
    edited = _yaml(package)
    assert history.state(package)['undo'] == 'SemForge: change kms.yaml'
    done = history.undo(package)
    assert done['undone'] == 'SemForge: change kms.yaml' and _yaml(package) == start
    assert history.state(package)['redo'] == 'SemForge: change kms.yaml'
    assert history.redo(package)['redone'] == 'SemForge: change kms.yaml'
    assert _yaml(package) == edited and history.state(package)['redo'] is None


def test_an_outside_change_is_kept_first_then_undone(package):
    with open(os.path.join(package, 'kms.yaml'), 'a') as handle:
        handle.write('\n# by hand\n')
    assert history.undo(package)['undone'] == history.OUTSIDE
    assert '# by hand' not in _yaml(package)
    history.redo(package)
    assert '# by hand' in _yaml(package), 'not lost: redo brings it back'


def test_a_new_change_ends_redo(package):
    _edit(package, 'one')
    history.undo(package)
    _edit(package, 'two')
    assert history.state(package)['redo'] is None
    with pytest.raises(history.Refused, match='nothing to redo'):
        history.redo(package)


def test_nothing_before_the_start(package):
    assert history.state(package)['undo'] is None
    with pytest.raises(history.Refused, match='where the history starts'):
        history.undo(package)


def test_back_to_an_earlier_step_and_redo_one_by_one(package):
    start = _yaml(package)
    for word in ('one', 'two', 'three'):
        _edit(package, word)
    log = history.state(package)['log']
    assert [e['title'] for e in log[:3]] == ['SemForge: change kms.yaml'] * 3
    done = history.back_to(package, log[3]['sha'])            # the starting point
    assert len(done['undone']) == 3 and _yaml(package) == start
    history.redo(package)
    assert _yaml(package).rstrip().endswith('# one'), 'the oldest step comes back first'
    with pytest.raises(history.Refused, match='already'):
        history.back_to(package, history.state(package)['log'][0]['sha'])


def test_off_refuses(package, monkeypatch):
    monkeypatch.setenv('SEMFORGE_HISTORY', 'off')
    assert history.state(package)['mode'] == 'off'
    with pytest.raises(history.Refused, match='turned off'):
        history.undo(package)


def test_the_server_steps_and_says_why_not(package, monkeypatch):
    monkeypatch.setattr(edits.validation, 'publish', lambda *a, **k: None)
    uri = {'uri': f'file://{package}/shacl.ttl'}
    _edit(package, 'one')
    state = edits.history_feature(None, uri)
    assert state['ok'] and state['undo'] and state['log']
    assert edits.undo_feature(None, uri)['ok']
    assert edits.redo_feature(None, uri)['ok']
    first = edits.history_feature(None, uri)['log'][-1]['sha']
    assert edits.back_to_feature(None, dict(uri, sha=first))['ok']
    refused = edits.undo_feature(None, uri)
    assert not refused['ok'] and refused['refused'] and 'starts' in refused['error']
    assert not edits.undo_feature(None, {'uri': 'file:///nowhere/x'})['ok']


def test_a_package_that_does_not_load_can_still_be_undone(package, monkeypatch):
    """A broken hand edit: History still answers, and the step back is done even if the reload fails."""
    from semforge.editor import session

    monkeypatch.setattr(edits.validation, 'publish', lambda *a, **k: None)
    uri = {'uri': f'file://{package}/shacl.ttl'}
    _edit(package, 'one')
    monkeypatch.setattr(session, 'package_for', lambda root: (_ for _ in ()).throw(ValueError('broken')))
    state = edits.history_feature(None, uri)
    assert state['ok'] and state['undo']
    done = edits.undo_feature(None, uri)
    assert done['ok'] and done['reload'] == 'broken'


# --- the extension -----------------------------------------------------------------

STATE = {'ok': True, 'mode': 'own', 'root': '/pkg', 'undo': 'SemForge: change kms.yaml', 'redo': None,
         'log': [{'sha': 'a1', 'title': 'SemForge: change kms.yaml', 'date': '2026-11-27T10:00:00Z', 'tags': []},
                 {'sha': 'a0', 'title': 'Start tracking kms', 'date': '2026-11-27T09:00:00Z', 'tags': ['v1.0.0']}]}


def _undo(tmp_path, **scenario):
    from test_tree_clicks import _drive

    return _drive(tmp_path, dict({'command': 'semforge.undo', 'replies': {
        'semforge/history': STATE, 'semforge/undo': {'ok': True, 'undone': STATE['undo'], 'now': 'Start'},
        'semforge/model': {'roots': []}}}, **scenario))


def test_the_status_bar_says_what_undo_takes_back(tmp_path):
    """"The status bar": Undo is there, says the change, and is the command run."""
    seen = _undo(tmp_path)
    assert '$(discard) Undo' in seen['statusBar']
    asked = [r['method'] for r in seen['requests']]
    assert 'semforge/history' in asked and 'semforge/undo' in asked


def test_a_repository_semforge_did_not_start_says_why(tmp_path):
    """"A clone of a package repository": no status bar item, and History… says whose history it is."""
    foreign = {'ok': True, 'mode': 'foreign', 'root': '/pkg', 'undo': None, 'redo': None, 'log': [],
               'reason': 'this package folder is a repository SemForge did not start (a clone, a checkout)'}
    seen = _undo(tmp_path, command='semforge.history',
                 replies={'semforge/history': foreign, 'semforge/model': {'roots': []}})
    assert not any('Undo' in s for s in seen['statusBar'])
    assert any('did not start' in m for m in seen['info'])
    assert 'semforge/backTo' not in [r['method'] for r in seen['requests']]


def test_unsaved_edits_refuse_a_step(tmp_path):
    """"Unsaved": nothing is stepped, the message names the file."""
    seen = _undo(tmp_path, openDocuments=[{'file': '/pkg/kms.yaml', 'dirty': True}])
    assert 'semforge/undo' not in [r['method'] for r in seen['requests']]
    assert any('kms.yaml' in w and 'unsaved' in w for w in seen['warnings']), seen['warnings']


def test_undo_is_bound_in_semforge_views_only():
    """"In a view": the keys are SemForge's while one of its views has focus, not in an editor."""
    from test_tree_clicks import PACKAGE_JSON

    with open(PACKAGE_JSON) as handle:
        contributes = json.load(handle)['contributes']
    keys = {(k.get('command'), k['key']): k['when'] for k in contributes['keybindings']
            if k.get('command') in ('semforge.undo', 'semforge.redo')}
    assert set(keys) == {('semforge.undo', 'ctrl+z'), ('semforge.redo', 'ctrl+shift+z'), ('semforge.redo', 'ctrl+y')}
    assert all(w == 'focusedView =~ /^semforge/ && !inputFocus' for w in keys.values())
    buttons = {e.get('command'): e['when'] for e in contributes['menus']['view/title']
               if e.get('command') in ('semforge.undo', 'semforge.redo', 'semforge.history')}
    assert buttons['semforge.undo'].endswith('semforge.canUndo')
    assert buttons['semforge.redo'].endswith('semforge.canRedo')
