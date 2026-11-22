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

"""The release record is append-only (openspec gh-942-append-only-release-record).

`semforge verify --against REF` compares a package's `.kms/releases.yaml`
with the one at a git ref: removing an entry or changing a field of one
fails and names the version and the field; appending passes; a package
whose record does not exist at the ref passes. `make kms-check` passes
`KMS_AGAINST` on, which CI sets to the pull request's base branch.

The records here list versions other than the package's current one, so the
digest rule of "Published versions are immutable" stays out of the way and
only the history is judged.
"""

import datetime
import json
import os
import shutil
import subprocess
import sys

import pytest
from click.testing import CliRunner

from semforge.cli.main import cli
from semforge.package.archive import pack
from semforge.package.releases import (RECORD_POSIX, history_problems, publish,
                                       raise_version, record_changes, record_path)
from semforge.package.scaffold import create_package

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='needs git')

SDK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIRST = {'version': '0.0.1', 'digest': 'sha256:' + 'a' * 64, 'date': '2026-11-01',
         'examples': 2, 'met': 2, 'coverage': 6.7, 'threshold': 5.0}
SECOND = dict(FIRST, version='0.0.2', digest='sha256:' + 'b' * 64, date='2026-11-02')


def _git(where, *arguments):
    subprocess.run(('git', '-C', where, '-c', 'user.name=t', '-c', 'user.email=t@t',
                    '-c', 'commit.gpgsign=false') + arguments,
                   check=True, capture_output=True, text=True)


def _write(root, releases):
    os.makedirs(os.path.dirname(record_path(root)), exist_ok=True)
    with open(record_path(root), 'w', encoding='utf-8') as handle:
        json.dump({'releases': releases}, handle)     # JSON is YAML


def _commit(repo, message='base'):
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-q', '-m', message)


@pytest.fixture
def repo(tmp_path):
    """A git repository holding kms/fresh, whose record lists 0.0.1, committed."""
    where = str(tmp_path / 'repo')
    os.makedirs(where)
    _git(where, 'init', '-q')
    root = os.path.join(where, 'kms', 'fresh')
    create_package(root, name='fresh', layout='flat')
    _write(root, [FIRST])
    _commit(where)
    return where


def _root(repo):
    return os.path.join(repo, 'kms', 'fresh')


def _verify(target, *extra):
    return CliRunner().invoke(cli, ['verify', '--against', 'HEAD', *extra, target])


# --- the comparison ------------------------------------------------------------

def test_record_changes_append_passes():
    assert record_changes([FIRST], [FIRST, SECOND]) == []


def test_record_changes_names_version_and_field():
    changed = dict(FIRST, digest='sha256:' + 'c' * 64, met=1)
    problems = [str(p) for p in record_changes([FIRST], [changed])]
    assert len(problems) == 2
    assert any('0.0.1: digest was sha256:aaa' in p for p in problems)
    assert any('0.0.1: met was 2 and is now 1' in p for p in problems)


def test_record_changes_removed_and_added_field():
    trimmed = {k: v for k, v in FIRST.items() if k != 'date'}
    assert 'date was 2026-11-01 and is now (absent)' in str(
        record_changes([FIRST], [trimmed])[0])
    widened = dict(FIRST, note='x')
    assert 'note was (absent) and is now x' in str(record_changes([FIRST], [widened])[0])


def test_record_changes_removed_entry():
    problems = record_changes([FIRST, SECOND], [SECOND])
    assert [p.path for p in problems] == ['.kms/releases.yaml']
    assert '0.0.1 was published and its entry has been removed' in problems[0].message


def test_record_changes_version_listed_twice():
    other = dict(FIRST, digest='sha256:' + 'd' * 64)
    problems = [str(p) for p in record_changes([FIRST], [FIRST, other])]
    assert problems == ['.kms/releases.yaml: 0.0.1 is listed 2 times; '
                        'a version is published once']


# --- against git ------------------------------------------------------------------

def test_unchanged_record_passes(repo):
    result = _verify(_root(repo))
    assert result.exit_code == 0, result.output
    assert 'history  keeps the 1 entries published on HEAD, 0 appended' in result.output


def test_appended_entry_passes(repo):
    _write(_root(repo), [FIRST, SECOND])
    result = _verify(_root(repo))
    assert result.exit_code == 0, result.output
    assert '1 appended' in result.output


def test_removed_entry_fails(repo):
    _write(_root(repo), [SECOND])
    result = _verify(_root(repo))
    assert result.exit_code == 2
    assert '0.0.1 was published and its entry has been removed' in result.output


def test_deleted_record_fails(repo):
    os.unlink(record_path(_root(repo)))
    result = _verify(_root(repo))
    assert result.exit_code == 2 and 'entry has been removed' in result.output


@pytest.mark.parametrize('field,value', [('digest', 'sha256:' + 'e' * 64),
                                         ('date', '2026-11-05'),
                                         ('examples', 3), ('met', 1),
                                         ('coverage', 90.0), ('threshold', 0.0)])
def test_changed_field_fails(repo, field, value):
    _write(_root(repo), [dict(FIRST, **{field: value})])
    result = _verify(_root(repo))
    assert result.exit_code == 2
    assert f'0.0.1: {field} was {FIRST[field]} and is now {value}' in result.output


def test_new_package_passes(repo):
    other = os.path.join(repo, 'kms', 'other')
    create_package(other, name='other', layout='flat')
    _write(other, [FIRST])
    result = _verify(other)
    assert result.exit_code == 0, result.output
    assert 'no release record on HEAD; nothing to keep' in result.output


# --- a package is identified by its name, not its path -----------------------

def _move(repo, new='moved'):
    _git(repo, 'mv', 'kms/fresh', f'kms/{new}')
    return os.path.join(repo, 'kms', new)


def _rename(root, name):
    path = os.path.join(root, 'kms.yaml')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text.replace('name: fresh', f'name: {name}'))


def test_moved_package_with_a_rewritten_record_fails(repo):
    moved = _move(repo)
    _write(moved, [dict(FIRST, digest='sha256:' + 'f' * 64)])
    result = _verify(moved)
    assert result.exit_code == 2
    assert '0.0.1: digest was sha256:aaa' in result.output
    assert '(published as kms/fresh on HEAD)' in result.output


def test_moved_package_with_an_emptied_record_fails(repo):
    moved = _move(repo)
    _write(moved, [])
    result = _verify(moved)
    assert result.exit_code == 2
    assert '0.0.1 was published and its entry has been removed' in result.output
    assert 'kms/fresh' in result.output


def test_moved_package_with_its_record_intact_passes(repo):
    moved = _move(repo)
    _write(moved, [FIRST, SECOND])
    result = _verify(moved)
    assert result.exit_code == 0, result.output
    assert 'keeps the 1 entries published on HEAD at kms/fresh, 1 appended' \
        in result.output


def test_renamed_and_moved_package_is_new(repo):
    moved = _move(repo)
    _rename(moved, 'other')
    _write(moved, [SECOND])
    result = _verify(moved)
    assert result.exit_code == 0, result.output
    assert 'no release record on HEAD; nothing to keep' in result.output


def test_renamed_in_place_is_compared_by_path(repo):
    _rename(_root(repo), 'other')
    _write(_root(repo), [SECOND])
    assert _verify(_root(repo)).exit_code == 2


def test_moved_package_beside_the_default_link(repo):
    """kms/default at the ref is a link, not a second package to match."""
    os.symlink('fresh', os.path.join(repo, 'kms', 'default'))
    _commit(repo, 'default')
    os.unlink(os.path.join(repo, 'kms', 'default'))
    moved = _move(repo)
    os.symlink('moved', os.path.join(repo, 'kms', 'default'))
    _write(moved, [SECOND])
    result = _verify(os.path.join(repo, 'kms', 'default'))
    assert result.exit_code == 2
    assert '(published as kms/fresh on HEAD)' in result.output


def test_descriptor_on_the_ref_that_does_not_parse(repo):
    with open(os.path.join(_root(repo), 'kms.yaml'), 'w', encoding='utf-8') as handle:
        handle.write('name: [unclosed\n')
    _commit(repo, 'broken descriptor')
    _git(repo, 'checkout', '-q', 'HEAD~1', '--', 'kms/fresh/kms.yaml')
    moved = _move(repo)
    _write(moved, [SECOND])
    problems, _ = history_problems(moved, 'HEAD')
    assert len(problems) == 1
    assert 'the descriptor kms/fresh/kms.yaml on HEAD does not parse' in problems[0].message


# --- what review of the implementation found ---------------------------------

def _make(repo, directory, name, releases):
    root = os.path.join(repo, 'kms', directory)
    create_package(root, name=name, layout='flat')
    _write(root, releases)
    return root


def test_record_that_is_a_link_fails(repo):
    """Step one of the two-step escape: the record becomes a link to a copy."""
    root = _root(repo)
    os.rename(record_path(root), os.path.join(root, '.kms', 'copy.yaml'))
    os.symlink('copy.yaml', record_path(root))
    result = _verify(root)
    assert result.exit_code == 2
    assert '.kms/releases.yaml: is a symbolic link' in result.output


def test_record_that_is_a_link_at_the_ref_fails(repo):
    """Step two: the link is on the ref, and the copy behind it is rewritten.
    A file here again does not make the link at the ref comparable."""
    root = _root(repo)
    os.rename(record_path(root), os.path.join(root, '.kms', 'copy.yaml'))
    os.symlink('copy.yaml', record_path(root))
    _commit(repo, 'link')
    os.unlink(record_path(root))
    _write(root, [])
    result = _verify(root)
    assert result.exit_code == 2
    assert 'HEAD:kms/fresh/.kms/releases.yaml is a symbolic link' in result.output


def test_kms_directory_that_is_a_link_fails(repo):
    root = _root(repo)
    os.rename(os.path.join(root, '.kms'), os.path.join(root, '.kms-real'))
    os.symlink('.kms-real', os.path.join(root, '.kms'))
    result = _verify(root)
    assert result.exit_code == 2 and '.kms: is a symbolic link' in result.output


def test_kms_directory_that_is_a_link_at_the_ref_fails(repo):
    root = _root(repo)
    os.rename(os.path.join(root, '.kms'), os.path.join(root, '.kms-real'))
    os.symlink('.kms-real', os.path.join(root, '.kms'))
    _commit(repo, 'link')
    os.unlink(os.path.join(root, '.kms'))
    _write(root, [])
    result = _verify(root)
    assert result.exit_code == 2
    assert 'HEAD:kms/fresh/.kms/releases.yaml is a symbolic link' in result.output


def test_taking_a_published_name_at_a_path_with_a_record_fails(tmp_path):
    """kms/other (empty record) renamed to `example`, which kms/example
    published: compared with kms/example's record as well, and the name
    clash with kms/example is reported."""
    repo = str(tmp_path / 'r')
    os.makedirs(repo)
    _git(repo, 'init', '-q')
    _make(repo, 'example', 'example', [FIRST])
    other = _make(repo, 'other', 'other', [])
    _commit(repo)
    _rename_to(other, 'other', 'example')
    _write(other, [dict(FIRST, digest='sha256:' + 'f' * 64)])
    result = _verify(other)
    assert result.exit_code == 2
    assert 'declares the name example, and so does example beside it' in result.output
    assert '0.0.1: digest was sha256:aaa' in result.output
    assert '(published as kms/example on HEAD)' in result.output


def test_moving_onto_a_removed_packages_path_fails(tmp_path):
    repo = str(tmp_path / 'r')
    os.makedirs(repo)
    _git(repo, 'init', '-q')
    _make(repo, 'example', 'example', [FIRST])
    _make(repo, 'other', 'other', [])
    _commit(repo)
    _git(repo, 'rm', '-q', '-r', 'kms/other')
    _git(repo, 'mv', 'kms/example', 'kms/other')
    other = os.path.join(repo, 'kms', 'other')
    _write(other, [dict(FIRST, digest='sha256:' + 'f' * 64)])
    result = _verify(other)
    assert result.exit_code == 2
    assert '(published as kms/example on HEAD)' in result.output


def test_moving_onto_a_removed_packages_path_intact_passes(tmp_path):
    repo = str(tmp_path / 'r')
    os.makedirs(repo)
    _git(repo, 'init', '-q')
    _make(repo, 'example', 'example', [FIRST])
    _make(repo, 'other', 'other', [])
    _commit(repo)
    _git(repo, 'rm', '-q', '-r', 'kms/other')
    _git(repo, 'mv', 'kms/example', 'kms/other')
    result = _verify(os.path.join(repo, 'kms', 'other'))
    assert result.exit_code == 0, result.output
    assert 'keeps the 1 entries published on HEAD at kms/example, 0 appended ' \
        'and the 0 entries published on HEAD, 1 appended' in result.output


def test_non_ascii_directory_at_the_ref(tmp_path):
    """git quotes such names unless asked not to; the lookup must still match."""
    repo = str(tmp_path / 'r')
    os.makedirs(repo)
    _git(repo, 'init', '-q')
    origin = _make(repo, 'exämple', 'example', [FIRST])
    _commit(repo)
    moved = os.path.join(repo, 'kms', 'example2')
    os.rename(origin, moved)
    _write(moved, [dict(FIRST, digest='sha256:' + 'f' * 64)])
    result = _verify(moved)
    assert result.exit_code == 2
    assert '(published as kms/exämple on HEAD)' in result.output


def test_types_are_compared():
    changed = dict(FIRST, met='2', coverage='6.7')
    problems = [str(p) for p in record_changes([FIRST], [changed])]
    assert any("met was 2 (int) and is now '2' (str)" in p for p in problems)
    assert any("coverage was 6.7 (float) and is now '6.7' (str)" in p for p in problems)
    assert record_changes([FIRST], [dict(FIRST, coverage=6.70)]) == []


def test_null_fields_added_or_dropped_are_changes():
    assert 'note was (absent) and is now null' in str(
        record_changes([FIRST], [dict(FIRST, note=None)])[0])
    assert 'note was null and is now (absent)' in str(
        record_changes([dict(FIRST, note=None)], [FIRST])[0])


def test_a_record_that_cannot_be_read_at_the_ref_fails(repo, monkeypatch):
    """Only a path the ref does not list is absent; any other failure of
    reading it is a problem."""
    import semforge.package.releases as releases

    real = releases._git

    def failing_show(where, *arguments):
        if arguments and arguments[0] == 'show' and arguments[1].endswith(RECORD_POSIX):
            return 128, ''
        return real(where, *arguments)

    monkeypatch.setattr(releases, '_git', failing_show)
    problems, _ = history_problems(_root(repo), 'HEAD')
    assert problems and 'cannot be read' in problems[0].message


def test_removing_a_whole_package_is_left_to_review(repo):
    """Out of the rule by the contract: the other packages still pass."""
    _git(repo, 'rm', '-q', '-r', 'kms/fresh')
    other = _make(repo, 'other', 'other', [])
    result = _verify(other)
    assert result.exit_code == 0, result.output
    assert 'nothing to keep' in result.output


def _rename_to(root, old, new):
    path = os.path.join(root, 'kms.yaml')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text.replace(f'name: {old}', f'name: {new}'))


def test_tests_still_run_when_the_history_fails(repo):
    _write(_root(repo), [SECOND])
    result = _verify(_root(repo), '--tests')
    assert result.exit_code == 2
    assert 'examples 2 of 2 meet their expectations' in result.output
    assert 'entry has been removed' in result.output


def test_json_output(repo):
    _write(_root(repo), [SECOND])
    result = _verify(_root(repo), '--format', 'json')
    data = json.loads(result.output)
    assert data['ok'] is False
    assert data['against']['ref'] == 'HEAD'
    assert data['against']['result'] == 'does not keep the entries published on HEAD'


def test_unknown_ref_fails(repo):
    result = CliRunner().invoke(cli, ['verify', '--against', 'no-such-ref', _root(repo)])
    assert result.exit_code == 2 and 'no-such-ref is not a commit' in result.output


def test_outside_git_fails(tmp_path):
    root = str(tmp_path / 'loose')
    create_package(root, name='loose', layout='flat')
    problems, said = history_problems(root, 'HEAD')
    if not problems:                                   # tmp_path inside a work tree
        pytest.skip('the temporary directory lies in a git work tree')
    assert 'is not in a git work tree' in problems[0].message
    assert said == 'not compared with HEAD'


def test_archive_is_refused(repo, tmp_path):
    out = str(tmp_path / 'p.kms.zip')
    pack(_root(repo), output=out)
    result = _verify(out)
    assert result.exit_code == 2 and 'an archive has none' in result.output


def test_malformed_record_on_ref_fails(repo):
    """Otherwise breaking the record in one pull request and rewriting it in
    the next would pass both."""
    with open(record_path(_root(repo)), 'w', encoding='utf-8') as handle:
        handle.write('- just a list\n')
    _commit(repo, 'broken')
    _write(_root(repo), [FIRST])
    problems, _ = history_problems(_root(repo), 'HEAD')
    assert len(problems) == 1
    assert 'HEAD:kms/fresh/.kms/releases.yaml does not parse' in problems[0].message


def test_malformed_record_here_is_left_to_the_package_check(repo):
    with open(record_path(_root(repo)), 'w', encoding='utf-8') as handle:
        handle.write('- just a list\n')
    problems, said = history_problems(_root(repo), 'HEAD')
    assert problems == [] and 'the record does not parse' in said


def test_through_a_link(repo):
    """kms/default is a link; the record is found at the linked package's path."""
    os.symlink('fresh', os.path.join(repo, 'kms', 'default'))
    _write(_root(repo), [SECOND])
    result = _verify(os.path.join(repo, 'kms', 'default'))
    assert result.exit_code == 2 and 'entry has been removed' in result.output


def test_publishing_appends(repo, tmp_path):
    """What `semforge publish` writes is an append, so it passes."""
    root = _root(repo)
    with open(os.path.join(root, 'kms.yaml'), 'a', encoding='utf-8') as handle:
        handle.write('\ntests:\n  coverage: 5\n')
    publish(root, output=str(tmp_path / 'a.kms.zip'), today=datetime.date(2026, 11, 7))
    _commit(repo, 'publish 0.1.0')
    raise_version(root, 'patch')
    publish(root, output=str(tmp_path / 'b.kms.zip'), today=datetime.date(2026, 11, 8))
    result = _verify(root)
    assert result.exit_code == 0, result.output
    assert 'keeps the 2 entries published on HEAD, 1 appended' in result.output


def test_rewritten_record_on_a_pull_request(repo, tmp_path):
    """The hole of #942: change a published version and rewrite its digest to
    match. The digest rule alone passes; the history does not."""
    from semforge.package.conformance import check

    root = _root(repo)
    with open(os.path.join(root, 'kms.yaml'), 'a', encoding='utf-8') as handle:
        handle.write('\ntests:\n  coverage: 5\n')
    publish(root, output=str(tmp_path / 'a.kms.zip'), today=datetime.date(2026, 11, 7))
    _commit(repo, 'publish 0.1.0')
    with open(os.path.join(root, 'shacl.ttl'), 'a', encoding='utf-8') as handle:
        handle.write('\n# changed after publishing\n')
    published = check(root).content_digest
    record = record_path(root)
    with open(record, encoding='utf-8') as handle:
        text = handle.read()
    old = [line for line in text.splitlines() if 'digest:' in line][-1].split()[-1]
    with open(record, 'w', encoding='utf-8') as handle:
        handle.write(text.replace(old, published))
    assert CliRunner().invoke(cli, ['verify', root]).exit_code == 0
    result = _verify(root)
    assert result.exit_code == 2
    assert f'0.1.0: digest was {old} and is now {published}' in result.output


# --- make kms-check -----------------------------------------------------------

def _kms_check(repo, *assignments):
    return subprocess.run(['make', '-s', '-C', SDK, 'kms-check',
                           f'PYTHON={sys.executable}',
                           f'KMS_DIR={os.path.join(repo, "kms")}', *assignments],
                          capture_output=True, text=True)


@pytest.mark.skipif(shutil.which('make') is None, reason='needs make')
def test_kms_check_fails_on_a_removed_entry(repo):
    _write(_root(repo), [SECOND])
    done = _kms_check(repo, 'KMS_AGAINST=HEAD')
    assert done.returncode != 0
    assert '0.0.1 was published and its entry has been removed' in done.stderr


@pytest.mark.skipif(shutil.which('make') is None, reason='needs make')
def test_kms_check_passes_on_an_append(repo):
    _write(_root(repo), [FIRST, SECOND])
    done = _kms_check(repo, 'KMS_AGAINST=HEAD')
    assert done.returncode == 0, done.stdout + done.stderr
    assert '1 appended' in done.stdout


@pytest.mark.skipif(shutil.which('make') is None, reason='needs make')
def test_kms_check_without_a_ref_skips_the_comparison(repo):
    _write(_root(repo), [SECOND])
    done = _kms_check(repo, 'KMS_AGAINST=')
    assert done.returncode == 0, done.stdout + done.stderr
    assert 'history' not in done.stdout
