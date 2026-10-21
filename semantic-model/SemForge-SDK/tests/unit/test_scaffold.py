"""`semforge init`: a package that already works.

Three empty files would be a worse starting point than none, because the first
run blames the author for the tool's omissions. So these assert the promise
rather than the file list: it loads, it validates clean, its suite passes, and
its bad case really does make a constraint fire.
"""

import json
import os

import pytest
from click.testing import CliRunner

from semforge.cli import cli
from semforge.errors import PackageError
from semforge.expect.runner import run_tests
from semforge.expect.store import load_expectations
from semforge.package import load
from semforge.package.scaffold import create_package
from semforge.validate import validate_package


@pytest.fixture
def made(tmp_path):
    target = tmp_path / 'plant'
    target.mkdir()
    create_package(str(target), name='Plant Line')
    return load(str(target))


# --- the promise ---------------------------------------------------------------

def test_what_it_writes_loads(made):
    assert len(made.shapes) and len(made.knowledge) and len(made.model)
    assert os.path.basename(made.sources['model']) == 'main.jsonld'
    assert 'model/' in os.path.relpath(made.sources['model'], made.path)


def test_the_scratchpad_validates_clean(made):
    report = validate_package(made, strict=False)
    assert report.violations == [], [str(v) for v in report.violations]
    assert report.results, 'nothing was evaluated at all'


def test_the_suite_passes_and_the_bad_case_fires(made):
    from semforge.cli.main import _examples_and_reports

    paired = _examples_and_reports(made, load_expectations(made.path))
    outcomes = {o.example: o for o in run_tests(paired)}
    assert len(outcomes) == 2, outcomes
    assert all(o.passed for o in outcomes.values()), \
        {name: o.failures for name, o in outcomes.items() if not o.passed}

    bad = next(report for example, report in paired if 'bad/' in example.path)
    assert bad.violations, 'the bad case does not violate anything'
    assert any('MaxInclusive' in v.component for v in bad.violations)


def test_one_constraint_is_two_sided_and_the_rest_are_honest(made):
    """A starter package should demonstrate the coverage rule, not hide it."""
    from semforge.cli.main import _examples_and_reports
    from semforge.expect import coverage

    entries = coverage(_examples_and_reports(made, load_expectations(made.path)))
    statuses = {e.status for e in entries}
    assert 'two-sided' in statuses
    assert any(e.status == 'two-sided' and 'MaxInclusive' in e.constraint
               for e in entries)
    # And it does not pretend the others are covered.
    assert 'no-firing-example' in statuses


def test_the_shapes_use_the_ngsi_ld_two_layer_encoding(made):
    """The encoding is the thing a newcomer gets wrong.

    A datatype or a range on the OUTER layer constrains the blank node the
    attribute is, and can never be satisfied -- so the scaffold has to show the
    inner layer.
    """
    from rdflib.namespace import SH

    text = open(made.sources['shapes'], encoding='utf-8').read()
    assert 'ngsild:hasValue' in text
    assert 'sh:nodeKind sh:BlankNode' in text

    inner = [o for o in made.shapes.objects(None, SH.datatype)]
    assert inner, 'no value-level datatype constraint at all'
    for parameter in (SH.datatype, SH.maxInclusive, SH['class']):
        for shape in made.shapes.subjects(parameter, None):
            paths = list(made.shapes.objects(shape, SH.path))
            assert paths and str(paths[0]).endswith(('hasValue', 'hasObject')), \
                f'{parameter} sits on the attribute rather than on its value'


def test_a_vocabulary_value_is_an_iri_not_a_string(made):
    """`{"@id": …}` in a Property is how a term is referenced.

    `{"object": …}` would make it a Relationship and mean an entity, which is
    the mistake this repo has already paid for.
    """
    document = json.load(open(made.sources['model'], encoding='utf-8'))
    state = next(v for k, v in document[0].items() if k.endswith('hasState'))
    assert state['type'] == 'Property'
    assert set(state['value']) == {'@id'}


def test_the_package_is_named_after_what_was_asked_for(made):
    prefixes = {name for name, _ in made.shapes.namespaces()}
    assert 'plantLineShacl' in prefixes
    assert 'plantLineEntities' in prefixes


# --- what it refuses -----------------------------------------------------------

def test_it_will_not_write_into_an_existing_package(tmp_path, made):
    with pytest.raises(PackageError) as raised:
        create_package(made.path, name='again')
    assert 'already holds' in str(raised.value)
    assert 'will not merge' in str(raised.value)


def test_a_nameless_package_is_refused(tmp_path):
    target = tmp_path / 'x'
    target.mkdir()
    with pytest.raises(PackageError):
        create_package(str(target), name='---')


def test_the_flat_layout_is_available(tmp_path):
    target = tmp_path / 'flat'
    target.mkdir()
    create_package(str(target), name='Flat', layout='flat')
    package = load(str(target))
    assert os.path.relpath(package.sources['model'], package.path) == \
        'main.jsonld'
    assert os.path.isdir(os.path.join(package.path, 'examples'))
    assert validate_package(package, strict=False).violations == []


# --- through the CLI -----------------------------------------------------------

def test_init_reports_what_it_wrote_and_proves_it_loads(tmp_path):
    target = tmp_path / 'via-cli'
    result = CliRunner().invoke(cli, ['init', str(target), '--name', 'Via CLI'])
    assert result.exit_code == 0, result.output
    assert 'knowledge.ttl' in result.output
    assert '0 violation(s)' in result.output
    assert 'semforge test' in result.output, 'no next step offered'

    outcome = CliRunner().invoke(cli, ['test', str(target)])
    assert outcome.exit_code == 0, outcome.output
    assert 'FAIL' not in outcome.output


def test_init_into_an_occupied_directory_exits_2(tmp_path):
    target = tmp_path / 'twice'
    assert CliRunner().invoke(cli, ['init', str(target)]).exit_code == 0
    again = CliRunner().invoke(cli, ['init', str(target)])
    assert again.exit_code == 2
    assert 'already holds' in again.output


# --- a project is a directory --------------------------------------------------

def test_new_creates_the_directory_and_scaffolds_it(tmp_path):
    """The classical gesture: `semforge new plant-line` makes ./plant-line."""
    result = CliRunner().invoke(
        cli, ['new', 'Plant Line', '--in', str(tmp_path)])
    assert result.exit_code == 0, result.output

    created = tmp_path / 'plant-line'
    assert created.is_dir(), 'no project directory was made'
    package = load(str(created))
    assert validate_package(package, strict=False).violations == []
    assert 'plantLineShacl' in {name for name, _ in package.shapes.namespaces()}


def test_new_refuses_a_directory_that_is_already_occupied(tmp_path):
    occupied = tmp_path / 'taken'
    occupied.mkdir()
    (occupied / 'something.txt').write_text('hello')

    result = CliRunner().invoke(cli, ['new', 'taken', '--in', str(tmp_path)])
    assert result.exit_code == 2
    assert 'not empty' in result.output
    assert (occupied / 'something.txt').read_text() == 'hello'


def test_new_and_init_produce_the_same_package(tmp_path):
    """Two gestures, one scaffold. A project made one way that differs from the
    other is a bug waiting to be reported as "works on the command line"."""
    CliRunner().invoke(cli, ['new', 'twinned', '--in', str(tmp_path)])
    second = tmp_path / 'by-init'
    CliRunner().invoke(cli, ['init', str(second), '--name', 'twinned'])

    def layout(root):
        return sorted(
            os.path.relpath(os.path.join(base, name), root)
            for base, _, names in os.walk(root) for name in names)

    assert layout(str(tmp_path / 'twinned')) == layout(str(second))


def test_a_new_project_declares_its_own_name(tmp_path):
    """`test` can be two projects; a scaffold should not leave that to the folder."""
    from semforge.package import config
    from semforge.package.scaffold import create_package

    target = tmp_path / 'test'
    target.mkdir()
    create_package(str(target), name='Cutting cell',
                   namespace='https://example.org/cell/')
    assert config.read(str(target))['name'] == 'Cutting cell'
