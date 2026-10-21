"""New test case…: add a test file to a suite.

The general way in: a suite (existing or new for a shape), good or bad, and
a start -- a copy of a case (includes written in), an entity from the model,
a fresh entity of a type, an empty file, or a .jsonld already under
examples/ that nothing declares. Written, declared, run once.
"""

import json
import os
import shutil

import pytest

from semforge.errors import PackageError
from semforge.expect.addcase import add_test_case, case_options
from semforge.expect.store import load_expectations
from semforge.package import load
from semforge.package.scaffold import create_package

FILTER = 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter'


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _declared(root):
    return {e.path: e for e in load_expectations(root).examples}


def test_the_options_name_what_a_case_can_start_from(kms):
    options = case_options(load(kms))
    assert 'test_FilterShape' in options['suites']
    assert 'test_FilterShape/bad/without-cartridge.jsonld' in [c['path'] for c in options['cases']]
    assert 'urn:filter:1' in options['entities']
    assert 'Filter' in [t['label'] for t in options['types']]
    assert options['undeclared'] == [], 'subobjects are includes, not undeclared cases'


def test_a_copy_writes_its_includes_in_and_passes(kms):
    made = add_test_case(load(kms), 'test_StateOnCutterShape', 'valid', 'copy',
                         'test_StateOnCutterShape/good/filter-on.jsonld', 'Filter on, again')
    assert made['case'] == 'test_StateOnCutterShape/good/filter-on-again.jsonld'
    assert made['passes'], made['failures']
    entry = _declared(kms)[made['case']]
    assert entry.expect == 'valid' and not entry.include
    with open(made['file']) as handle:
        ids = {d['id'] for d in json.load(handle)}
    assert {'urn:plasmacutter:1', 'urn:filter:1'} <= ids


def test_a_model_entity_starts_a_case(kms):
    made = add_test_case(load(kms), 'test_FilterShape', 'valid', 'model', 'urn:filter:1', 'f1')
    with open(made['file']) as handle:
        assert [d['id'] for d in json.load(handle)] == ['urn:filter:1']


def test_a_new_suite_and_a_fresh_entity_of_a_type(tmp_path):
    root = str(tmp_path / 'm')
    create_package(root)
    package = load(root)
    machine = next(str(c) for c in package.knowledge.subjects() if str(c).endswith('/Machine'))
    made = add_test_case(package, 'test_Fresh', 'valid', 'type', machine, 'machine')
    assert made['case'] == 'test_Fresh/good/machine.jsonld'
    assert made['passes'], made['failures']


def test_a_bad_empty_case_says_nothing_fires_yet(kms):
    made = add_test_case(load(kms), 'test_FilterShape', 'invalid', 'empty', '', 'todo')
    assert made['case'] == 'test_FilterShape/bad/todo.jsonld'
    assert not made['passes'] and made['violations'] == 0
    assert _declared(kms)[made['case']].expect == 'invalid'


def test_a_file_nobody_runs_is_found_and_declared_where_it_is(kms):
    root = os.path.join(kms, 'examples', 'test_FilterShape', 'good')
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, 'by-hand.jsonld'), 'w') as handle:
        handle.write('[]')
    assert case_options(load(kms))['undeclared'] == ['test_FilterShape/good/by-hand.jsonld']
    made = add_test_case(load(kms), '', 'valid', 'existing',
                         'test_FilterShape/good/by-hand.jsonld')
    assert made['passes']
    assert case_options(load(kms))['undeclared'] == []


@pytest.mark.parametrize('args, said', [
    (('test_FilterShape', 'maybe', 'empty', '', 'x'), 'conforms'),
    (('', 'valid', 'empty', '', 'x'), 'needs a suite'),
    (('../outside', 'valid', 'empty', '', 'x'), 'needs a suite'),
    (('test_FilterShape', 'valid', 'copy', 'nope.jsonld', 'x'), 'not a declared test case'),
    (('test_FilterShape', 'valid', 'model', 'urn:nope', 'x'), 'not an entity in the model'),
    (('', 'valid', 'existing', '../../shacl.ttl', ''), 'not a file under'),
    (('test pump', 'valid', 'empty', '', 'x'), 'not a folder name'),
    (('test_$HOME', 'valid', 'empty', '', 'x'), 'not a folder name'),
])
def test_what_it_cannot_write_is_refused(kms, args, said):
    with pytest.raises(PackageError, match=said):
        add_test_case(load(kms), *args)


def test_a_name_taken_is_refused_and_nothing_is_left_behind(kms):
    add_test_case(load(kms), 'test_FilterShape', 'valid', 'empty', '', 'twice')
    with pytest.raises(PackageError, match='already exists'):
        add_test_case(load(kms), 'test_FilterShape', 'valid', 'empty', '', 'twice')
