"""The project view and the settings behind it.

"I am missing the settings, and the current status. I just see a project name;
`test` can be different projects." Four modules read semforge.yaml and none of
them could say what a package's settings ARE, so nothing could show them and
nothing could change one.
"""

import os
import shutil

import pytest

from semforge.cooked.project import build_project
from semforge.package import config, load


@pytest.fixture
def package(tmp_path, corpus_path):
    copy = tmp_path / 'pkg'
    shutil.copytree(corpus_path, copy)
    return str(copy)


def _rows(nodes):
    for node in nodes:
        yield node
        yield from _rows(node.children)


def _by_label(package_path):
    return {node.label: node for node in _rows(build_project(load(package_path)))}


# --- reading -----------------------------------------------------------------

def test_a_package_without_a_name_says_where_its_name_came_from(package):
    """`test` can be two projects. The row has to say which is which."""
    rows = _by_label(package)
    assert rows['name'].value == 'pkg'
    assert 'directory' in rows['name'].detail
    assert rows['path'].value == os.path.abspath(package)


def test_a_declared_name_wins_over_the_directory(package):
    config.set_value(package, 'name', 'Cutting cell')
    rows = _by_label(package)
    assert rows['name'].value == 'Cutting cell'
    assert rows['name'].detail == ''


def test_the_settings_show_what_is_not_declared_too(package):
    """A list of whatever is in the file cannot show what you have NOT set."""
    rows = _by_label(package)
    assert rows['entity root'].value == '—'
    assert 'not declared' in rows['entity root'].detail
    assert rows['entity root'].editable


def test_a_missing_published_context_is_a_warning_not_a_blank(tmp_path, package):
    """Absence is flagged only where it costs something: export cannot run."""
    config.set_value(package, 'context.published', '')
    rows = _by_label(package)
    assert rows['published context'].severity == 'warning'
    assert 'export' in rows['published context'].detail


def test_every_setting_points_at_its_own_line(package):
    rows = _by_label(package)
    where, _, line = rows['published context'].defined_at.rpartition(':')
    assert where.endswith('semforge.yaml')
    text = open(where).read().splitlines()[int(line) - 1]
    assert text.strip().startswith('published:')


def test_the_contents_count_what_the_other_views_show(package):
    rows = _by_label(package)
    # The suite's own count, not a directory listing: examples/ also holds the
    # shared subobjects, which are not cases.
    assert rows['test cases'].value == '6'
    assert 'suite(s)' in rows['test cases'].detail
    assert rows['shapes'].value == 'shacl.ttl'


def test_a_package_with_no_cases_says_what_that_costs(tmp_path):
    from semforge.package.scaffold import create_package

    bare = tmp_path / 'bare'
    bare.mkdir()
    create_package(str(bare), name='bare', namespace='https://example.org/b/')
    shutil.rmtree(os.path.join(str(bare), 'model', 'examples'))
    rows = _by_label(str(bare))
    assert rows['test cases'].value == '0'
    assert rows['test cases'].severity == 'warning'


# --- writing -----------------------------------------------------------------

def test_writing_a_setting_keeps_every_comment(package):
    before = open(config.path_for(package)).read()
    comments = [line for line in before.splitlines() if line.startswith('#')]
    assert comments

    config.set_value(package, 'context.published', 'https://example.org/c.jsonld')
    after = open(config.path_for(package)).read()
    assert [line for line in after.splitlines() if line.startswith('#')] == comments
    assert 'published: https://example.org/c.jsonld' in after


def test_a_nested_key_is_found_by_its_parent(package):
    """`context.published` is the `published:` under `context:`.

    Not the first `published:` in the file -- another block may have one.
    """
    config.set_value(package, 'context.published', 'https://example.org/c.jsonld')
    assert config.read(package)['context']['published'] == \
        'https://example.org/c.jsonld'
    assert config.read(package)['context']['local'] == 'context.jsonld'


def test_a_new_key_arrives_with_the_paragraph_that_explains_it(package):
    config.set_value(package, 'entityRoot', 'base:Entity')
    text = open(config.path_for(package)).read()
    assert 'entityRoot: base:Entity' in text
    line = text.splitlines().index('entityRoot: base:Entity')
    assert text.splitlines()[line - 1].startswith('#')
    assert config.read(package)['entityRoot'] == 'base:Entity'


def test_a_package_with_no_manifest_gets_one(tmp_path):
    """The kms layout has no semforge.yaml; editing a setting is when it needs one."""
    bare = tmp_path / 'kms'
    bare.mkdir()
    for name in ('knowledge.ttl', 'shacl.ttl'):
        (bare / name).write_text('')
    (bare / 'model-instance.jsonld').write_text('{"@graph": []}')
    assert not os.path.isfile(config.path_for(str(bare)))

    config.set_value(str(bare), 'name', 'the kms')
    assert config.read(str(bare))['name'] == 'the kms'


def test_a_url_is_not_quoted_on_the_way_back(package):
    config.set_value(package, 'context.published', 'https://example.org/c.jsonld')
    text = open(config.path_for(package)).read()
    assert "'https" not in text


def test_a_value_that_yaml_would_read_as_a_number_is_quoted(package):
    config.set_value(package, 'name', '2024')
    assert config.read(package)['name'] == '2024'
