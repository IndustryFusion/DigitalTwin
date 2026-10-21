"""The CLI. Exit codes are the CI contract: 0 clean, 1 violations, 2 bad package."""

from click.testing import CliRunner

from semforge.cli import cli


def test_validate_reports_violations_and_exits_1(corpus_path):
    result = CliRunner().invoke(cli, ['validate', corpus_path])
    assert result.exit_code == 1
    assert 'MachineShape' in result.output
    assert '3 violations' in result.output


def test_validate_reports_the_view_and_what_it_removed(corpus_path):
    """The view builder removes data, so every run says what it removed."""
    result = CliRunner().invoke(cli, ['validate', corpus_path])
    assert 'view=current' in result.output
    assert 'collapsed=3' in result.output


def test_validate_states_conformance_rather_than_implying_it(corpus_path):
    """Was a warning that conformance was not established; M2 established it."""
    result = CliRunner().invoke(cli, ['validate', corpus_path])
    assert 'constraints evaluated' in result.output
    assert 'INCOMPLETE' not in result.output


def test_bad_package_exits_2(tmp_path):
    result = CliRunner().invoke(cli, ['validate', str(tmp_path)])
    assert result.exit_code == 2
    assert 'package error' in result.output


def test_missing_path_is_rejected_by_the_parser():
    result = CliRunner().invoke(cli, ['validate', '/nonexistent/path'])
    assert result.exit_code == 2


def test_test_command_runs_and_reports_coverage(corpus_path):
    result = CliRunner().invoke(cli, ['test', corpus_path, '--coverage'])
    assert 'Coverage' in result.output
    assert 'no-firing-example' in result.output


def test_test_command_fail_on_turns_coverage_into_a_failure(corpus_path):
    clean = CliRunner().invoke(cli, ['test', corpus_path])
    gated = CliRunner().invoke(cli, [
        'test', corpus_path, '--coverage', '--fail-on', 'no-firing-example'])
    assert gated.exit_code == 1
    assert 'no-firing-example' in gated.output
    assert clean.exit_code in (0, 1)


def test_validate_reports_how_many_constraints_were_evaluated(corpus_path):
    """V1 surfaced: the count is stated, not left as silence."""
    result = CliRunner().invoke(cli, ['validate', corpus_path])
    assert 'constraints evaluated' in result.output


def test_accept_writes_the_residue(tmp_path, corpus_path):
    import os
    import shutil
    package = tmp_path / 'pkg'
    package.mkdir()
    for name in ('knowledge.ttl', 'shacl.ttl', 'model-instance.jsonld'):
        shutil.copy(os.path.join(corpus_path, name), package / name)

    result = CliRunner().invoke(cli, ['accept', str(package)])
    assert result.exit_code == 0
    # Nothing declared anything yet, so it lands where a reader will look.
    written = (package / 'examples' / 'expectations.yaml').read_text()
    assert 'sha256:' in written

    # Second accept is a no-op: nothing changed, so nothing to accept.
    again = CliRunner().invoke(cli, ['accept', str(package)])
    assert 'accepted residue for 0 example(s)' in again.output


def test_test_says_nothing_about_ids_reused_across_files(corpus_path):
    """The shipped suite reuses ids deliberately, and the path tells them apart.

    An Identity section listing all four would be noise in every run.
    """
    result = CliRunner().invoke(cli, ['test', corpus_path])
    assert 'Identity' not in result.output
    # The corpus has failing cases of its own, so only the absence of identity
    # noise is asserted here.
    assert 'urn:filter:1' not in result.output


def test_test_fails_when_one_id_names_two_entities_in_a_case(tmp_path, corpus):
    """There the definitions merge, so the case no longer tests what it says."""
    import json
    import shutil

    package = tmp_path / 'pkg'
    package.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], package / name)
    for extra in ('context.jsonld', 'semforge.yaml'):
        shutil.copy(f'{corpus.path}/{extra}', package / extra)
    examples = package / 'examples'
    examples.mkdir()
    published = ('https://industryfusion.github.io/contexts/staging/example/'
                 'v0.2/context.jsonld')
    for name in ('inc.jsonld', 'case.jsonld'):
        with open(examples / name, 'w') as handle:
            json.dump([{'id': 'urn:filter:99',
                        'type': 'iffBaseEntities:Filter',
                        '@context': published}], handle)
    with open(examples / 'expectations.yaml', 'w') as handle:
        handle.write('examples:\n  - path: case.jsonld\n'
                     '    include: [inc.jsonld]\n    expect: invalid\n')

    result = CliRunner().invoke(cli, ['test', str(package)])
    assert 'urn:filter:99' in result.output
    assert '[in-case]' in result.output
    assert result.exit_code == 1
