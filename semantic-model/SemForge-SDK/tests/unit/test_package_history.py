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

"""A KMS package keeps its own git history: started on open, every change committed."""

import os
import shutil
import subprocess

import pytest

from semforge.package import history


def _git(where, *arguments):
    return subprocess.run(('git', '-C', where) + arguments, capture_output=True,
                          text=True, check=True).stdout


def _log(where):
    return _git(where, 'log', '--format=%s').splitlines()


@pytest.fixture
def package(tmp_path, corpus_path, monkeypatch):
    monkeypatch.delenv('SEMFORGE_HISTORY', raising=False)
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge', '.git', history.NO_HISTORY))
    return str(target)


def test_the_marker_keeps_a_package_without_history(package):
    open(os.path.join(package, history.NO_HISTORY), 'w').write('# kept by a checkout\n')
    assert history.ensure(package)['mode'] == 'off'
    assert not os.path.exists(os.path.join(package, '.git'))
    assert history.state(package)['mode'] == 'off'
    with pytest.raises(history.Refused, match='no history of its own'):
        history.undo(package)


def test_every_package_this_repository_keeps_carries_the_marker(corpus_path):
    """The packages DigitalTwin itself tracks get no repository of their own:
    every tracked folder SemForge takes as a package has the marker."""
    from semforge.package.discover import is_package

    top = subprocess.run(['git', '-C', corpus_path, 'rev-parse', '--show-toplevel'],
                         capture_output=True, text=True)
    if top.returncode != 0:
        pytest.skip('not in a checkout')
    top = top.stdout.strip()
    tracked = subprocess.run(['git', '-C', top, 'ls-files'], capture_output=True, text=True).stdout.split()
    packages, unmarked = [], []
    for folder in sorted({os.path.dirname(p) for p in tracked}):
        full = os.path.join(top, folder)
        if any(folder.startswith(p + '/') for p in packages) or not os.path.isdir(full) or not is_package(full):
            continue
        packages.append(folder)
        if not os.path.isfile(os.path.join(full, history.NO_HISTORY)):
            unmarked.append(folder)
    assert packages and unmarked == [], unmarked


def test_the_marker_is_no_member_and_not_exported(package):
    from semforge.package.conformance import check
    open(os.path.join(package, history.NO_HISTORY), 'w').write('#\n')
    assert history.NO_HISTORY not in str(check(package).members)


def test_extracted_from_a_marked_package_the_history_starts(package, tmp_path):
    """"Extracted from a marked package": its members carry no marker, so the copy is tracked."""
    from semforge.package.conformance import check

    open(os.path.join(package, history.NO_HISTORY), 'w').write('#\n')
    assert history.ensure(package)['mode'] == 'off'
    extracted = tmp_path / 'extracted'
    for member in check(package).members:
        target = extracted / member
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(os.path.join(package, member), target)
    assert not (extracted / history.NO_HISTORY).exists()
    done = history.ensure(str(extracted))
    assert done['mode'] == 'own' and done['started']


def test_a_signing_setup_never_makes_a_commit_fail(package, tmp_path, monkeypatch):
    """"A signing setup": signing everything with a key that is not there."""
    config = tmp_path / 'gitconfig'
    config.write_text('[commit]\n\tgpgsign = true\n[tag]\n\tgpgsign = true\n[gpg]\n\tformat = ssh\n'
                      '[user]\n\tsigningkey = /nowhere/key.pub\n[core]\n\thooksPath = /nowhere\n')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(config))
    assert history.ensure(package)['started']
    open(os.path.join(package, 'kms.yaml'), 'a').write('\n# edited\n')
    assert history.ensure(package, 'SemForge edit')['commit']
    assert history.tag(package, '9.9.9') == 'v9.9.9'
    assert _git(package, 'log', '-1', '--format=%an %G?').startswith('SemForge N')


def test_an_untracked_package_is_started(package):
    os.makedirs(os.path.join(package, '.semforge'))
    open(os.path.join(package, '.semforge', 'cache.db'), 'w').write('x')
    done = history.ensure(package)
    assert done['mode'] == 'own' and done['started']
    assert _log(package)[0].startswith('Start tracking ')
    tracked = _git(package, 'ls-files').split()
    assert 'kms.yaml' in tracked and '.gitignore' in tracked
    assert not any(t.startswith('.semforge/') for t in tracked)
    assert _git(package, 'status', '--porcelain') == ''
    commit = _git(package, 'log', '-1', '--format=%an <%ae> %G?')
    assert commit.startswith('SemForge <semforge@localhost>')


def test_outside_changes_are_committed_and_a_clean_package_is_left(package):
    history.ensure(package)
    assert history.ensure(package)['commit'] is None              # nothing changed
    with open(os.path.join(package, 'kms.yaml'), 'a') as handle:
        handle.write('\n# edited by hand\n')
    open(os.path.join(package, 'notes.txt'), 'w').write('new')
    done = history.ensure(package)
    assert sorted(done['commit']['files']) == ['kms.yaml', 'notes.txt']
    assert _log(package)[0] == history.OUTSIDE
    body = _git(package, 'log', '-1', '--format=%b')
    assert 'add notes.txt' in body and 'change kms.yaml' in body


def test_a_semforge_edit_is_named_by_what_it_changed(package):
    history.ensure(package)
    os.remove(os.path.join(package, 'kms.yaml'))
    history.ensure(package, 'SemForge edit')
    assert _log(package)[0] == 'SemForge: delete kms.yaml'


def test_inside_a_repository_that_tracks_it_it_still_gets_its_own(tmp_path, package):
    """`git init` in the package folder: its own history, the outer one untouched."""
    outer = str(tmp_path)
    _git(outer, 'init', '-q')
    _git(outer, '-c', 'user.name=t', '-c', 'user.email=t@t', 'add', '-A')
    _git(outer, '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false',
         'commit', '-q', '-m', 'outer')
    done = history.ensure(package)
    assert done['mode'] == 'own' and done['started']
    assert os.path.isdir(os.path.join(package, '.git'))
    open(os.path.join(package, 'kms.yaml'), 'a').write('\n# change\n')
    assert history.ensure(package, 'SemForge edit')['commit']
    assert len(_log(outer)) == 1, 'SemForge never commits into the outer repository'
    assert 'kms.yaml' in _git(outer, 'status', '--porcelain'), 'which still sees the change'


def test_an_enclosing_repository_that_does_not_track_it_gets_a_nested_one(tmp_path, package):
    _git(str(tmp_path), 'init', '-q')
    done = history.ensure(package)
    assert done['mode'] == 'own' and done['started']
    assert os.path.isdir(os.path.join(package, '.git'))


def test_publishing_never_starts_a_history(tmp_path, package):
    """CI publishes from a checkout: a repository started there would hide the files."""
    _git(str(tmp_path), 'init', '-q')
    assert history.tag(package, '1.0.0') is None
    assert not os.path.exists(os.path.join(package, '.git'))


def test_publish_tags_the_version_and_never_moves_a_tag(package):
    history.ensure(package)
    assert history.tag(package, '1.2.3') == 'v1.2.3'
    first = _git(package, 'rev-parse', 'v1.2.3^{commit}')
    open(os.path.join(package, 'kms.yaml'), 'a').write('\n# later\n')
    assert history.tag(package, '1.2.3') is None
    assert _git(package, 'rev-parse', 'v1.2.3^{commit}') == first
    assert _log(package)[0] == 'Publish 1.2.3'                    # the change, committed


def test_off_does_nothing(package, monkeypatch):
    monkeypatch.setenv('SEMFORGE_HISTORY', 'off')
    assert history.ensure(package)['mode'] == 'off'
    assert not os.path.exists(os.path.join(package, '.git'))


def test_no_git_is_reported_not_raised(package, monkeypatch):
    monkeypatch.setenv('PATH', '/nonexistent')
    assert history.ensure(package)['mode'] == 'none'


def test_summary_shortens_long_lists():
    changes = [('?', f'f{i}') for i in range(6)] + [('M', 'g'), ('D', 'h')]
    assert history.summary(changes) == 'add f0, f1, f2, f3 and 2 more; change g; delete h'


def test_the_editor_session_starts_and_commits(package):
    from semforge.editor import session

    session.package_for(package)
    assert _log(package)[0].startswith('Start tracking ')
    open(os.path.join(package, 'kms.yaml'), 'a').write('\n# by semforge\n')
    session.forget(package)
    assert _log(package)[0] == 'SemForge: change kms.yaml'
    session.package_for(package)
    open(os.path.join(package, 'kms.yaml'), 'a').write('\n# by hand\n')
    session.package_for(package)                                  # an outside change, loaded
    assert _log(package)[0] == history.OUTSIDE


def test_a_hand_edit_right_after_an_editor_write_is_its_own_commit(package):
    """After forget() the package is not loaded; a hand edit then is still an outside change."""
    from semforge.editor import session

    session.package_for(package)
    open(os.path.join(package, 'kms.yaml'), 'a').write('\n# by semforge\n')
    session.forget(package)
    open(os.path.join(package, 'kms.yaml'), 'a').write('\n# by hand, before any read\n')
    session.package_for(package)
    assert _log(package)[:2] == [history.OUTSIDE, 'SemForge: change kms.yaml']


def test_a_repository_semforge_did_not_start_is_left_alone(package):
    """A clone or a checkout whose top is the package folder: its history, not the editor's."""
    for args in (('init', '-q'), ('-c', 'user.name=t', '-c', 'user.email=t@t', 'add', '-A'),
                 ('-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false',
                  'commit', '-q', '-m', 'a package repository')):
        _git(package, *args)
    open(os.path.join(package, 'kms.yaml'), 'a').write('\n# work in progress\n')
    assert history.mode(package) == 'foreign'
    assert history.ensure(package)['commit'] is None and len(_log(package)) == 1
    assert history.tag(package, '1.0.0') is None
    assert history.state(package)['mode'] == 'foreign'
    with pytest.raises(history.Refused, match='did not start'):
        history.undo(package)
    assert 'kms.yaml' in _git(package, 'status', '--porcelain'), 'the work in progress stays'


def test_a_background_thread_never_commits_half_an_edit(package):
    """The warm-up and the verdict worker load, but only the requests' thread commits."""
    import threading
    from semforge.editor import session

    session.package_for(package)
    open(os.path.join(package, 'kms.yaml'), 'a').write('\n# the first file of an edit\n')
    worker = threading.Thread(target=session.package_for, args=(package,))
    worker.start()
    worker.join()
    assert len(_log(package)) == 1, 'nothing committed from the background'
    session.forget(package)
    assert _log(package)[0] == 'SemForge: change kms.yaml'


def test_every_request_commits_outside_changes_first(package):
    """A write that never reads the package first does not take a hand edit into its commit."""
    from semforge.editor import session
    from semforge.editor.protocol import server
    import semforge.editor.edits  # noqa: F401 -- registers the requests

    session.package_for(package)
    open(os.path.join(package, 'shacl.ttl'), 'a').write('\n# by hand\n')
    session.before_request({'uri': f'file://{package}/kms.yaml'})
    open(os.path.join(package, 'kms.yaml'), 'a').write('\n# by semforge, without reading\n')
    session.forget(package)
    assert _log(package)[:2] == ['SemForge: change kms.yaml', history.OUTSIDE]
    registered = server.protocol.fm.features['semforge/undo'].func
    assert registered.__name__ == 'undo_feature' and registered is not semforge.editor.edits.undo_feature


def test_the_cache_stays_out_whatever_the_gitignore_says(package):
    open(os.path.join(package, '.gitignore'), 'w').write('*.bak\n')
    history.ensure(package)
    os.makedirs(os.path.join(package, '.semforge'), exist_ok=True)
    open(os.path.join(package, '.semforge', 'verdicts.json'), 'w').write('{}')
    assert history.ensure(package)['commit'] is None


def test_a_repository_git_refuses_to_read_is_foreign(package, monkeypatch):
    monkeypatch.setattr(history, '_git_err', lambda root, *a, **k: (
        128, '', "fatal: detected dubious ownership in repository at '/x'"))
    assert history.mode(package) == 'foreign'


def test_file_names_are_written_as_they_are(package):
    history.ensure(package)
    open(os.path.join(package, 'examples', 'Größe.jsonld'), 'w').write('[]')
    history.ensure(package, 'SemForge edit')
    assert _log(package)[0] == 'SemForge: add examples/Größe.jsonld'


def test_a_translated_git_still_starts_a_history(package, monkeypatch):
    """git's messages are read: they are asked for in English, whatever the locale."""
    monkeypatch.setenv('LANG', 'de_DE.UTF-8')
    monkeypatch.setenv('LC_ALL', 'de_DE.UTF-8')
    monkeypatch.setenv('LANGUAGE', 'de')
    assert history.mode(package) == 'untracked'
    assert history.ensure(package)['started']
    assert history._env()['LC_ALL'] == 'C'


def test_git_that_times_out_fails_a_checked_step(package, monkeypatch):
    history.ensure(package)

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired('git', 60)

    monkeypatch.setattr(history.subprocess, 'run', slow)
    with pytest.raises(RuntimeError, match='timed out|60'):
        history._git(package, 'reset', '--hard', 'HEAD^', check=True)
    assert history._git(package, 'status')[0] is None, 'unchecked: reported, not raised'


def test_a_link_added_later_ends_the_history(package, tmp_path):
    history.ensure(package)
    elsewhere = tmp_path / 'shared.jsonld'
    elsewhere.write_text('[]')
    os.symlink(elsewhere, os.path.join(package, 'examples', 'linked.jsonld'))
    assert history.mode(package) == 'linked'
    assert history.ensure(package)['commit'] is None
    assert 'links examples/linked.jsonld' in history.state(package)['reason']


def test_a_hand_edit_in_a_dot_folder_is_an_outside_change(package):
    """`.kms/releases.yaml`: left out of the fingerprint, taken in by git."""
    from semforge.editor import session

    os.makedirs(os.path.join(package, '.kms'), exist_ok=True)
    open(os.path.join(package, '.kms', 'releases.yaml'), 'w').write('[]\n')
    session.package_for(package)
    open(os.path.join(package, '.kms', 'releases.yaml'), 'a').write('# by hand\n')
    session.before_request({'uri': f'file://{package}/kms.yaml'})
    assert _log(package)[0] == history.OUTSIDE


def test_history_says_why_there_is_none(package, monkeypatch):
    open(os.path.join(package, history.NO_HISTORY), 'w').write('#\n')
    assert history.NO_HISTORY in history.state(package)['reason']
    os.remove(os.path.join(package, history.NO_HISTORY))
    monkeypatch.setenv('SEMFORGE_HISTORY', 'off')
    assert 'SEMFORGE_HISTORY' in history.state(package)['reason']
    monkeypatch.delenv('SEMFORGE_HISTORY')
    monkeypatch.setattr(history, 'mode', lambda root: 'none')
    assert 'git is not available' in history.state(package)['reason']


def test_a_started_history_carries_semforge_s_mark(package):
    history.ensure(package)
    assert os.path.isfile(os.path.join(package, '.git', history.STARTED))
    assert history.mode(package) == 'own'


def test_a_history_started_before_the_mark_is_still_own(package):
    """Started by an earlier build: no mark, but a single root commit of SemForge's and no remote."""
    history.ensure(package)
    os.remove(os.path.join(package, '.git', history.STARTED))
    assert history.mode(package) == 'own'
    _git(package, 'remote', 'add', 'origin', 'https://example.org/kms.git')
    assert history.mode(package) == 'foreign', 'with a remote it is somebody\'s repository'


def test_a_clone_of_a_semforge_history_is_foreign(package, tmp_path):
    history.ensure(package)
    clone = tmp_path / 'clone'
    subprocess.run(['git', 'clone', '-q', package, str(clone)], check=True, capture_output=True)
    assert not (clone / '.git' / history.STARTED).exists()
    assert history.mode(str(clone)) == 'foreign'
    open(clone / 'kms.yaml', 'a').write('\n# work in progress\n')
    assert history.ensure(str(clone))['commit'] is None
    assert len(_log(str(clone))) == 1


def test_a_package_with_links_keeps_no_history(package, tmp_path):
    elsewhere = tmp_path / 'shared.jsonld'
    elsewhere.write_text('[]')
    os.symlink(elsewhere, os.path.join(package, 'examples', 'linked.jsonld'))
    assert history.ensure(package)['mode'] == 'linked'
    assert not os.path.exists(os.path.join(package, '.git'))
    with pytest.raises(history.Refused, match='links examples/linked.jsonld'):
        history.undo(package)


def test_git_s_location_is_not_inherited(package, tmp_path, monkeypatch):
    """A hook or an exec shell sets GIT_DIR / GIT_INDEX_FILE: the commits still go here."""
    other = tmp_path / 'other'
    other.mkdir()
    _git(str(other), 'init', '-q')
    monkeypatch.setenv('GIT_DIR', str(other / '.git'))
    monkeypatch.setenv('GIT_INDEX_FILE', str(other / '.git' / 'index'))
    assert history.ensure(package)['started']
    monkeypatch.delenv('GIT_DIR')
    monkeypatch.delenv('GIT_INDEX_FILE')
    assert _log(package)[0].startswith('Start tracking ')
    assert subprocess.run(['git', '-C', str(other), 'log'], capture_output=True).returncode != 0, \
        'the other repository has no commit'


def test_an_index_another_git_holds_is_waited_for(package):
    import threading

    history.ensure(package)
    lock = os.path.join(package, '.git', 'index.lock')
    open(lock, 'w').close()
    threading.Timer(0.3, lambda: os.remove(lock)).start()
    open(os.path.join(package, 'kms.yaml'), 'a').write('\n# while VS Code refreshes\n')
    assert history.ensure(package, 'SemForge edit')['commit']
    assert _log(package)[0] == 'SemForge: change kms.yaml'
