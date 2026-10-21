"""Which package applies here.

`semforge validate` used to read the current directory and nothing else. Run it
one level inside a package and it reported all three roles missing; run it one
level above and it reported the same thing. Both are the ordinary place to be
standing, and neither error said where to stand instead.

Every other SDK walks up -- cargo to Cargo.toml, npm to package.json, git to
.git -- so these tests pin that behaviour and the report that goes with it.
"""

import os

import pytest
from click.testing import CliRunner

from semforge.cli.main import cli
from semforge.editor.analysis import package_root
from semforge.package import discover


def test_a_package_is_found_from_a_directory_inside_it(corpus_path):
    inside = os.path.join(corpus_path, 'examples')
    assert os.path.isdir(inside)
    assert discover.root(inside) == corpus_path


def test_a_package_is_found_from_a_file(corpus_path):
    """An editor hands you a file, not a project."""
    assert discover.root(os.path.join(corpus_path, 'shacl.ttl')) == corpus_path


def test_the_manifest_anchors_even_when_a_role_is_missing(tmp_path):
    """A directory that SAYS it is a package is broken, not absent.

    Walking past it to some ancestor would validate a different package than
    the one you are standing in -- silently.
    """
    broken = tmp_path / 'declared'
    broken.mkdir()
    (broken / 'semforge.yaml').write_text('name: declared\n')
    found, why = discover.find(broken)
    assert found == str(broken)
    assert why == discover.BY_MANIFEST
    assert discover.missing_roles(str(broken))


def test_the_layout_anchors_without_a_manifest(tmp_path):
    """The kms predates semforge.yaml and must keep working without one."""
    package = tmp_path / 'kms'
    (package / 'shacl').mkdir(parents=True)
    (package / 'knowledge.ttl').write_text('')
    (package / 'model-instance.jsonld').write_text('{}')
    assert discover.find(package) == (str(package), discover.BY_LAYOUT)


def test_nothing_found_says_where_it_looked_and_what_would_count(tmp_path):
    found, why, roles = discover.describe(tmp_path)
    assert found is None and roles == {}
    assert str(tmp_path) in why            # where it looked
    assert 'semforge.yaml' in why          # what would have counted
    assert 'semforge init' in why          # what to do about it


def test_the_editor_and_the_command_line_agree(corpus_path):
    """One rule, in one place: they used to keep private copies of it."""
    inside = os.path.join(corpus_path, 'examples')
    assert package_root(inside) == discover.root(inside)


# --- through the command line ------------------------------------------------

def test_a_command_run_inside_a_package_reads_that_package(corpus_path):
    inside = os.path.join(corpus_path, 'examples')
    result = CliRunner().invoke(cli, ['validate', inside])
    assert result.exit_code in (0, 1), result.output
    assert 'constraints evaluated' in result.output


def test_every_command_says_which_package_it_resolved(corpus_path):
    """The answer to "which directory does this apply to?", on every run."""
    result = CliRunner().invoke(cli, ['validate',
                                      os.path.join(corpus_path, 'examples')])
    assert f'package: {corpus_path}' in result.output


def test_where_reports_the_root_and_the_roles(corpus_path):
    result = CliRunner().invoke(cli, ['where',
                                      os.path.join(corpus_path, 'examples')])
    assert result.exit_code == 0, result.output
    assert corpus_path in result.output
    for role in ('knowledge', 'shapes', 'model'):
        assert role in result.output
    assert 'shacl.ttl' in result.output


def test_where_outside_a_package_exits_2_and_explains(tmp_path):
    result = CliRunner().invoke(cli, ['where', str(tmp_path)])
    assert result.exit_code == 2
    assert 'semforge init' in result.output


@pytest.mark.parametrize('command', ['validate', 'test', 'observe'])
def test_no_package_anywhere_is_a_usage_error_not_a_crash(tmp_path, command):
    result = CliRunner().invoke(cli, [command, str(tmp_path)])
    assert result.exit_code == 2
    assert 'package error' in result.output
