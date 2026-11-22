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


# --- the whole main model -------------------------------------------------------------------

def _model(root):
    with open(os.path.join(root, 'model-instance.jsonld')) as handle:
        return json.load(handle)


def _replace_model(root, documents):
    # The corpus copy follows its links, so this is a file of the copy.
    path = os.path.join(root, 'model-instance.jsonld')
    os.remove(path)
    with open(path, 'w') as handle:
        json.dump(documents, handle)


HEALTHY = ['subobjects/workpiece-steel.jsonld', 'subobjects/cartridge-fresh.jsonld',
           'subobjects/filter-on.jsonld', 'test_StateOnCutterShape/good/filter-on.jsonld']


@pytest.fixture
def healthy(kms):
    """The corpus with a conforming main model: the healthy baseline case's
    scene. (The corpus's own model is a scratchpad with violations in it.)"""
    documents = []
    for relative in HEALTHY:
        with open(os.path.join(kms, 'examples', relative)) as handle:
            data = json.load(handle)
        documents += data if isinstance(data, list) else [data]
    _replace_model(kms, documents)
    return kms


def test_the_options_name_the_main_model_s_files(kms):
    assert case_options(load(kms))['modelFiles'] == ['model-instance.jsonld']


def test_the_whole_model_is_written_in_and_passes_as_a_good_case(healthy):
    made = add_test_case(load(healthy), 'test_StateOnCutterShape', 'valid', 'whole-model', '',
                         'whole')
    assert made['case'] == 'test_StateOnCutterShape/good/whole.jsonld'
    assert made['passes'], made['failures']
    with open(made['file']) as handle:
        assert json.load(handle) == _model(healthy), 'every document, as the model has it'
    entry = _declared(healthy)[made['case']]
    assert entry.expect == 'valid' and not entry.include, 'written in, not included'
    assert entry.description == ('Started from the whole main model, which conforms: a '
                                 'snapshot, so editing this case never changes the model.')
    assert made['sharedIds'] == []


def test_a_bad_case_from_a_conforming_model_fails_until_edited_and_says_so(healthy):
    made = add_test_case(load(healthy), 'test_StateOnCutterShape', 'invalid', 'whole-model',
                         '', 'broken')
    assert made['case'] == 'test_StateOnCutterShape/bad/broken.jsonld'
    assert not made['passes'] and made['violations'] == 0
    entry = _declared(healthy)[made['case']]
    assert entry.expect == 'invalid'
    assert 'which conforms' in entry.description
    assert 'fails until its data is edited' in entry.description


def test_the_case_is_a_snapshot_of_the_model(kms):
    made = add_test_case(load(kms), 'test_FilterShape', 'valid', 'whole-model', '', 'snap')
    with open(made['file']) as handle:
        written = handle.read()
    _replace_model(kms, [])                        # the model changes: the case does not
    with open(made['file']) as handle:
        assert handle.read() == written
    with open(made['file'], 'w') as handle:        # the case changes: the model does not
        handle.write('[{"id": "urn:only:here"}]')
    assert _model(kms) == []


def test_documents_of_every_model_file_are_written_in(kms):
    documents = _model(kms)
    os.remove(os.path.join(kms, 'model-instance.jsonld'))
    folder = os.path.join(kms, 'model-instance')
    os.makedirs(folder)
    with open(os.path.join(folder, 'a.jsonld'), 'w') as handle:
        json.dump(documents[:2], handle)
    with open(os.path.join(folder, 'b.jsonld'), 'w') as handle:
        json.dump(documents[2:], handle)
    package = load(kms)
    assert case_options(package)['modelFiles'] == ['model-instance/a.jsonld',
                                                   'model-instance/b.jsonld']
    made = add_test_case(package, 'test_FilterShape', 'valid', 'whole-model', '', 'both')
    with open(made['file']) as handle:
        assert json.load(handle) == documents


def test_a_violating_model_says_so_in_either_case(kms):
    # The corpus's own model violates: three machines without a workpiece.
    good = add_test_case(load(kms), 'test_FilterShape', 'valid', 'whole-model', '', 'g')
    assert not good['passes'] and good['violations'] == 3
    assert 'which violates. It fails until' in _declared(kms)[good['case']].description
    bad = add_test_case(load(kms), 'test_FilterShape', 'invalid', 'whole-model', '', 'b')
    assert bad['violations'] == 3
    assert 'violates already' in _declared(kms)[bad['case']].description


def test_a_description_given_is_kept(kms):
    made = add_test_case(load(kms), 'test_FilterShape', 'invalid', 'whole-model', '', 'mine',
                         description='Mine.')
    assert _declared(kms)[made['case']].description == 'Mine.'


def test_no_main_model_no_whole_model_case(kms):
    package = load(kms)
    package.documents['model'] = []
    package.sources['model'] = None
    with pytest.raises(PackageError, match='no main model'):
        add_test_case(package, 'test_FilterShape', 'valid', 'whole-model', '', 'x')
    assert not os.path.exists(os.path.join(kms, 'examples', 'test_FilterShape', 'good',
                                           'x.jsonld'))


def test_a_relative_context_still_names_the_package_s_context(healthy):
    # `semforge retarget --to local` writes "@context": "context.jsonld".
    from semforge.package.context import retarget_model

    model = os.path.join(healthy, 'model-instance.jsonld')
    retarget_model(model, 'context.jsonld')
    made = add_test_case(load(healthy), 'test_StateOnCutterShape', 'valid', 'whole-model', '',
                         'local')
    assert made['passes'], made['failures']
    with open(made['file']) as handle:
        contexts = {d['@context'] for d in json.load(handle)}
    assert contexts == {'../../../context.jsonld'}
    folder = os.path.dirname(made['file'])
    assert os.path.exists(os.path.join(folder, '../../../context.jsonld'))
    assert {d['@context'] for d in _model(healthy)} == {'context.jsonld'}, 'the model as it was'


@pytest.mark.parametrize('context, written', [
    ('context.jsonld', '../../../context.jsonld'),
    (['https://x/core.jsonld', 'sub/ctx.jsonld'], ['https://x/core.jsonld',
                                                   '../../../sub/ctx.jsonld']),
    ('https://x/context.jsonld', 'https://x/context.jsonld'),
    ('urn:x:context', 'urn:x:context'),
    ({'@vocab': 'https://x/'}, {'@vocab': 'https://x/'}),
])
def test_only_relative_contexts_are_moved(tmp_path, context, written):
    from semforge.expect.addcase import _moved_context

    source = str(tmp_path)
    target = os.path.join(source, 'examples', 'test_x', 'good')
    assert _moved_context({'id': 'urn:a', '@context': context}, source, target)['@context'] \
        == written
    absolute = os.path.join(source, 'context.jsonld')
    assert _moved_context({'@context': absolute}, source, target)['@context'] == absolute
    assert _moved_context({'id': 'urn:a'}, source, target) == {'id': 'urn:a'}


def test_ids_two_model_files_share_are_reported(healthy):
    documents = _model(healthy)
    os.remove(os.path.join(healthy, 'model-instance.jsonld'))
    folder = os.path.join(healthy, 'model-instance')
    os.makedirs(folder)
    with open(os.path.join(folder, 'a.jsonld'), 'w') as handle:
        json.dump(documents, handle)
    with open(os.path.join(folder, 'b.jsonld'), 'w') as handle:
        json.dump([documents[0]], handle)
    made = add_test_case(load(healthy), 'test_StateOnCutterShape', 'valid', 'whole-model', '',
                         'shared')
    assert made['sharedIds'] == [documents[0]['id']]


def test_a_run_that_cannot_load_keeps_the_neutral_description(healthy, monkeypatch):
    import semforge.expect.addcase as addcase

    def broken(*_):
        raise ValueError('no graph')
    monkeypatch.setattr(addcase, 'compose', broken)
    made = add_test_case(load(healthy), 'test_StateOnCutterShape', 'invalid', 'whole-model',
                         '', 'unloaded')
    assert made['failures'] == ['does not load: no graph']
    assert _declared(healthy)[made['case']].description == 'Started from the whole main model.'


@pytest.mark.parametrize('folder', ['good', 'bad'])
def test_a_failure_after_declaring_leaves_nothing_behind(healthy, monkeypatch, folder):
    import semforge.package.loader as loader

    expectations = os.path.join(healthy, 'examples', 'test_StateOnCutterShape', folder,
                                'expectations.yaml')
    with open(expectations) as handle:
        before = handle.read()

    def broken(*_):
        raise RuntimeError('reload failed')
    monkeypatch.setattr(loader, 'reload_keeping_shapes', broken)
    with pytest.raises(RuntimeError, match='reload failed'):
        add_test_case(load(healthy), 'test_StateOnCutterShape',
                      'valid' if folder == 'good' else 'invalid', 'whole-model', '', 'gone')
    directory = os.path.dirname(expectations)
    assert not [n for n in os.listdir(directory) if n.startswith('gone.jsonld')]
    with open(expectations) as handle:
        assert handle.read() == before, 'the declaration is gone again'


def test_a_failure_in_a_new_suite_leaves_no_expectations(healthy, monkeypatch):
    import semforge.package.loader as loader

    def broken(*_):
        raise RuntimeError('reload failed')
    monkeypatch.setattr(loader, 'reload_keeping_shapes', broken)
    with pytest.raises(RuntimeError):
        add_test_case(load(healthy), 'test_New', 'valid', 'whole-model', '', 'gone')
    assert os.listdir(os.path.join(healthy, 'examples', 'test_New', 'good')) == []
