"""What a delete button has to say before it deletes anything.

"Are you sure?" is not a warning: a person can only be sure about something
they have been told. Three things are worth knowing and none of them are
visible from a tree row -- what in the directory is not the package, whether it
holds packages of its own, and whether git has any of it.
"""

import os
import shutil
import subprocess

import pytest

from semforge.package.removal import plan_deletion


@pytest.fixture
def project(tmp_path, corpus_path):
    copy = tmp_path / 'project'
    shutil.copytree(corpus_path, copy, symlinks=False)
    return str(copy)


def test_it_deletes_nothing(project):
    before = sorted(os.listdir(project))
    plan_deletion(project)
    assert sorted(os.listdir(project)) == before


def test_it_counts_what_is_there(project):
    plan = plan_deletion(project)
    assert plan.is_package and not plan.error
    assert plan.files > 0 and plan.bytes > 0
    assert plan.name


def test_only_a_package_is_deletable_from_here(tmp_path):
    (tmp_path / 'ordinary').mkdir()
    plan = plan_deletion(str(tmp_path / 'ordinary'))
    assert not plan.is_package
    assert 'not a SemForge package' in plan.error


def test_a_directory_inside_a_package_names_the_package(project):
    plan = plan_deletion(os.path.join(project, 'examples'))
    assert not plan.is_package
    assert 'the package here is' in plan.error


def test_what_is_not_the_package_is_listed_first(project):
    """A README somebody wrote, a scratch file, a vendored copy.

    Those are what a deletion actually costs, and nothing else knows what they
    are.
    """
    with open(os.path.join(project, 'notes.md'), 'w') as handle:
        handle.write('mine\n')
    os.makedirs(os.path.join(project, 'vendor'))

    plan = plan_deletion(project)
    assert 'notes.md' in plan.strangers
    assert 'vendor' + os.sep in plan.strangers
    assert any('not part of the package' in warning
               for warning in plan.warnings)


def test_the_package_layout_is_not_called_a_stranger(project):
    plan = plan_deletion(project)
    for known in ('knowledge.ttl', 'shacl.ttl', 'examples' + os.sep,
                  'semforge.yaml', 'context.jsonld'):
        assert known not in plan.strangers


def test_a_nested_package_is_called_out(project, tmp_path):
    from semforge.package.scaffold import create_package

    inside = os.path.join(project, 'sub')
    os.makedirs(inside)
    create_package(inside, name='sub', namespace='https://example.org/sub/')

    plan = plan_deletion(project)
    assert 'sub' + os.sep in plan.nested
    assert any('of its own' in warning for warning in plan.warnings), \
        plan.warnings
    # And not repeated as an unexplained stranger.
    assert 'sub' + os.sep not in plan.strangers


def test_untracked_means_it_cannot_come_back(tmp_path, project):
    plan = plan_deletion(project)
    assert not plan.in_git or plan.tracked == 0
    assert any('nothing can bring it back' in warning
               for warning in plan.warnings), plan.warnings


def test_tracked_means_it_can(tmp_path, project):
    """The difference between an annoyance and a loss, and it is knowable."""
    if shutil.which('git') is None:
        pytest.skip('git is not installed')
    subprocess.run(['git', 'init', '-q', project], check=True)
    subprocess.run(['git', '-C', project, 'add', '-A'], check=True)

    plan = plan_deletion(project)
    assert plan.in_git and plan.tracked > 0 and plan.untracked == 0
    assert any('recoverable with `git checkout`' in warning
               for warning in plan.warnings), plan.warnings


def test_a_mixture_says_how_much_of_each(tmp_path, project):
    if shutil.which('git') is None:
        pytest.skip('git is not installed')
    subprocess.run(['git', 'init', '-q', project], check=True)
    subprocess.run(['git', '-C', project, 'add', 'knowledge.ttl'], check=True)

    plan = plan_deletion(project)
    assert plan.tracked and plan.untracked
    assert any('can be restored' in warning and 'cannot' in warning
               for warning in plan.warnings), plan.warnings
