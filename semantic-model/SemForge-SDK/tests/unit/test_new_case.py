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

"""Step D: the rule section of the shape page, and New case….

A rule no case makes fire looks exactly like one that holds. The shape page
shows what a SPARQL shape checks, the query, and the evidence; New case…
writes a bad case asserting the shape fires, copied from a scene where it
holds -- so it fails until its data is edited to break the rule, and cannot
pass by accident.
"""

import json
import os
import shutil

import pytest

from semforge.cooked.shapepage import build_shape_page
from semforge.errors import PackageError
from semforge.expect.newcase import new_case
from semforge.expect.runner import run_tests
from semforge.expect.store import compose, load_expectations
from semforge.package import load
from semforge.sanity import known_constraints
from semforge.validate.orchestrator import validate_graphs

ON_FILTER = 'iffBaseShacl:StateOnFilterShape'


# --- what it checks, and the evidence -------------------------------------------------

def test_a_sparql_shape_says_what_it_checks_and_how_severe(corpus):
    checks = build_shape_page(corpus, ON_FILTER)['checks']
    assert len(checks) == 1
    check = checks[0]
    assert check['kind'] == 'constraint'
    assert check['message'] == 'Filter running without running assigned machine'
    # The kms names its own severities; the page uses their names.
    assert check['severity'] == 'warning'
    assert 'SELECT $this' in check['query'] and 'state_PROCESSING' in check['query']
    critical = build_shape_page(corpus, 'iffBaseShacl:StateOnCutterShape')['checks'][0]
    assert critical['severity'] == 'critical'


def test_a_rule_shows_its_construct_and_offers_no_case(corpus):
    page = build_shape_page(corpus, 'iffBaseShacl:TimestampCartridgeFromRulesShape')
    assert [c['kind'] for c in page['checks']] == ['rule']
    assert 'CONSTRUCT' in page['checks'][0]['query'].upper()
    assert not page['canNewCase'], 'a rule derives data; it does not fire'


def test_the_evidence_names_the_entity_it_fires_on(corpus):
    page = build_shape_page(corpus, 'iffBaseShacl:StateOnCutterShape')
    fired = {c['case']: c['firedOn'] for c in page['exercisedBy']}
    assert fired['test_StateOnCutterShape/bad/filter-off.jsonld'] == ['urn:plasmacutter:1']
    assert fired['test_StateOnCutterShape/good/filter-on.jsonld'] == []


def test_a_shape_reaching_several_types_lists_them_all(corpus):
    """StateOnCutterShape reaches Cutters and Plasmacutters."""
    labels = [t['label'] for t in build_shape_page(
        corpus, 'iffBaseShacl:StateOnCutterShape')['types']]
    assert len(labels) >= 2 and labels == sorted(labels, key=str.lower)


def test_new_case_is_offered_only_where_it_can_be_written(corpus, targets):
    assert build_shape_page(corpus, ON_FILTER)['canNewCase']
    assert not build_shape_page(corpus, 'iffBaseShacl:FilterShape')['canNewCase']
    assert not build_shape_page(targets, 'ex:PositionShape')['canNewCase']


# --- New case… --------------------------------------------------------------------------

@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _outcome(root, case):
    package = load(root)
    example = next(e for e in load_expectations(package.path).examples if e.path == case)
    report = validate_graphs(compose(package, example), package.shapes,
                             package.knowledge, strict=False)
    return run_tests([(example, report)], known_constraints(package))[0]


def test_new_case_starts_from_a_valid_scene_and_fails_until_edited(kms):
    made = new_case(load(kms), ON_FILTER, 'Filter on, cutter idle')
    assert made['case'] == 'test_StateOnFilterShape/bad/filter-on-cutter-idle.jsonld'
    assert made['source'].split('/')[1] == 'good', 'a valid scene, not another bad case'
    assert made['resource'] == 'urn:filter:1'

    with open(made['file']) as handle:
        scene = json.load(handle)
    ids = {document['id'] for document in scene}
    # The includes are written into the case: the filter is editable here
    # without changing the shared subobject every other case uses.
    assert {'urn:filter:1', 'urn:plasmacutter:1'} <= ids

    entry = next(e for e in load_expectations(kms).examples if e.path == made['case'])
    assert entry.expect == 'invalid' and not entry.include
    assert entry.asserts == [{'constraint': f'{ON_FILTER}/SPARQLConstraintComponent',
                              'resource': 'urn:filter:1'}]

    outcome = _outcome(kms, made['case'])
    assert not outcome.passed, 'copied from a scene where it holds, it cannot pass yet'

    # Break the rule: the filter is ON, the cutter it belongs to stops.
    for document in scene:
        if document['id'] == 'urn:plasmacutter:1':
            document['iffBaseEntities:hasState']['value'] = {'@id': 'base:state_OFF'}
    with open(made['file'], 'w') as handle:
        json.dump(scene, handle)
    assert _outcome(kms, made['case']).passed


def test_new_case_keeps_the_other_cases_and_the_comments(kms):
    path = os.path.join(kms, 'examples', 'test_StateOnCutterShape', 'bad',
                        'expectations.yaml')
    with open(path) as handle:
        before = handle.read()
    new_case(load(kms), 'iffBaseShacl:StateOnCutterShape', 'second')
    with open(path) as handle:
        after = handle.read()
    assert after.startswith(before.rstrip('\n'))
    assert 'second.jsonld' in after


@pytest.mark.parametrize('shape, name, said', [
    ('iffBaseShacl:FilterShape', 'x', 'no SPARQL constraint'),
    (ON_FILTER, '   ', 'needs a name'),
    ('iffBaseShacl:Nope', 'x', 'is not a shape'),
])
def test_new_case_refuses_what_it_cannot_write(kms, shape, name, said):
    with pytest.raises(PackageError, match=said):
        new_case(load(kms), shape, name)


def test_new_case_will_not_overwrite_a_case(kms):
    new_case(load(kms), ON_FILTER, 'once')
    with pytest.raises(PackageError, match='already exists'):
        new_case(load(kms), ON_FILTER, 'once')


def test_an_assert_may_name_a_shape_without_a_class_target(targets):
    """known_constraints now covers every shape that runs, so an assert on
    one with sh:targetObjectsOf is not refused as naming nothing."""
    assert 'ex:PointedAtShape/hasPosition/MinCountConstraintComponent' in \
        known_constraints(targets)


# --- New test… of a query, on the type's page ---------------------------------------------

BASE = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
ON_CUTTER = 'iffBaseShacl:StateOnCutterShape'


def test_a_query_gets_a_test_it_is_silent_on(kms):
    made = new_case(load(kms), ON_FILTER, 'silent', 'valid', BASE + 'Filter')
    assert made['case'] == 'test_StateOnFilterShape/good/silent.jsonld' and made['passes']
    entry = next(e for e in load_expectations(kms).examples if e.path == made['case'])
    assert entry.expect == 'valid' and not entry.asserts
    # It does run there: what is not evaluated proves nothing.
    case = next(c for c in build_shape_page(load(kms), ON_FILTER)['exercisedBy']
                if c['case'] == made['case'])
    assert case['firedOn'] == [] and case['held'] is not False


def test_a_failing_one_says_that_it_fails_still(kms):
    made = new_case(load(kms), ON_FILTER, 'fires', 'invalid', BASE + 'Filter')
    assert not made['passes'] and made['failures'] and made['expect'] == 'invalid'


def test_the_scene_has_an_entity_of_the_type_asked_for(kms):
    """The query reaches Cutters and Plasmacutters; asked on one's page, the
    test is about that one -- a new one, when the package has none."""
    for label in ('Plasmacutter', 'Lasercutter'):
        made = new_case(load(kms), ON_CUTTER, label, 'invalid', BASE + label)
        with open(made['file']) as handle:
            scene = json.load(handle)
        entity = next(d for d in scene if d['id'] == made['resource'])
        assert str(entity['type']).split(':')[-1] == label, made


def test_a_test_is_valid_or_invalid(kms):
    with pytest.raises(PackageError, match='valid or invalid'):
        new_case(load(kms), ON_FILTER, 'x', 'sometimes')


def test_a_failing_one_passes_once_its_data_makes_the_query_fire(kms):
    made = new_case(load(kms), ON_FILTER, 'fires', 'invalid', BASE + 'Filter')
    assert made['resource'] == 'urn:filter:1' and made['source'].split('/')[1] == 'good'
    entry = next(e for e in load_expectations(kms).examples if e.path == made['case'])
    assert entry.asserts == [{'constraint': f'{ON_FILTER}/SPARQLConstraintComponent',
                              'resource': 'urn:filter:1'}]
    with open(made['file']) as handle:
        scene = json.load(handle)
    for document in scene:
        if document['id'] == 'urn:plasmacutter:1':
            document['iffBaseEntities:hasState']['value'] = {'@id': 'base:state_OFF'}
    with open(made['file'], 'w') as handle:
        json.dump(scene, handle)
    assert _outcome(kms, made['case']).passed


def _without_cases(kms):
    shutil.rmtree(os.path.join(kms, 'examples'))
    os.makedirs(os.path.join(kms, 'examples'))


def test_from_the_model_what_its_entity_points_at_comes_along(kms):
    _without_cases(kms)
    # New case… of the shape page takes the entity alone, as before.
    alone = new_case(load(kms), ON_FILTER, 'alone')
    assert alone['source'] == 'the model'
    with open(alone['file']) as handle:
        assert len(json.load(handle)) == 1
    _without_cases(kms)
    made = new_case(load(kms), ON_FILTER, 'from-model', 'valid', BASE + 'Filter')
    assert made['source'] == 'the model'
    with open(made['file']) as handle:
        ids = [d['id'] for d in json.load(handle)]
    assert ids[0] == made['resource'] and 'urn:cartridge:' in ' '.join(ids[1:])


def test_a_relative_context_still_names_the_same_file(kms):
    _without_cases(kms)
    model = os.path.join(kms, 'model-instance.jsonld')
    with open(model) as handle:
        documents = json.load(handle)
    for document in documents:
        document['@context'] = 'context.jsonld'
    with open(model, 'w') as handle:
        json.dump(documents, handle)
    made = new_case(load(kms), ON_FILTER, 'local', 'valid', BASE + 'Filter')
    with open(made['file']) as handle:
        assert {d['@context'] for d in json.load(handle)} == {'../../../context.jsonld'}
    # It loads: the query is evaluated on its filter, read through that context.
    from semforge.cooked.shapepage import _reach
    package = load(kms)
    example = next(e for e in load_expectations(kms).examples if e.path == made['case'])
    assert made['resource'] in _reach(package, package.shapes.namespace_manager.expand_curie(ON_FILTER),
                                      compose(package, example))
    with open(model) as handle:
        assert {d['@context'] for d in json.load(handle)} == {'context.jsonld'}


def _tree(kms):
    """Every file under examples/ with its content, and every folder."""
    found = set()
    top = os.path.join(kms, 'examples')
    for folder, _, files in os.walk(top):
        if folder != top:
            found.add(os.path.relpath(folder, kms))
        for name in files:
            with open(os.path.join(folder, name), 'rb') as handle:
                found.add((os.path.relpath(os.path.join(folder, name), kms), handle.read()))
    return found


def test_a_new_entity_the_query_does_not_see_is_refused(kms):
    before = _tree(kms)
    with pytest.raises(PackageError, match='not evaluated on a new entity'):
        new_case(load(kms), ON_FILTER, 'unseen', 'invalid', BASE + 'Workpiece')
    assert _tree(kms) == before


def test_a_failure_after_declaring_leaves_nothing(kms, monkeypatch):
    from semforge.expect import addcase

    new_case(load(kms), ON_FILTER, 'first', 'valid', BASE + 'Filter')
    before = _tree(kms)

    def broken(*_):
        raise RuntimeError('the run broke')
    monkeypatch.setattr(addcase, '_outcome', broken)
    for name in ('second', 'third'):
        with pytest.raises(RuntimeError):
            new_case(load(kms), ON_FILTER, name, 'valid', BASE + 'Filter')
    assert _tree(kms) == before
    _without_cases(kms)
    with pytest.raises(RuntimeError):
        new_case(load(kms), ON_FILTER, 'fourth', 'invalid', BASE + 'Filter')
    assert _tree(kms) == set(), 'not even an expectations.yaml'


def _model_edit(kms, change):
    model = os.path.join(kms, 'model-instance.jsonld')
    with open(model) as handle:
        documents = json.load(handle)
    for document in documents:
        change(document)
    with open(model, 'w') as handle:
        json.dump(documents, handle)


def test_should_conform_prefers_an_entity_the_query_holds_on(kms):
    """Two cutters in the model: the query fires on the first (its filter is
    off), and holds on the second. The test that should conform is about the
    second, and the query is silent on it."""
    _without_cases(kms)

    def filter_off(document):
        if document['id'] == 'urn:filter:1':
            document['iffBaseEntities:hasState'][0]['value'] = {'@id': 'base:state_OFF'}
    _model_edit(kms, filter_off)
    # Asked to fail, the first is as good a start as any.
    made = new_case(load(kms), ON_CUTTER, 'fires', 'invalid', BASE + 'Cutter')
    assert made['resource'] == 'urn:plasmacutter:1'
    made = new_case(load(kms), ON_CUTTER, 'silent', 'valid', BASE + 'Cutter')
    assert made['resource'] == 'urn:plasmacutter:2' and made['source'] == 'the model', made
    case = next(c for c in build_shape_page(load(kms), ON_CUTTER)['exercisedBy']
                if c['case'] == made['case'])
    assert case['firedOn'] == [] and case['held'] is not False


FILTERED = 'iffBaseShacl:FilteredShape'
REACHED_THROUGH_A_CUTTER = '''
iffBaseShacl:FilteredShape a sh:NodeShape ;
    sh:target [ a sh:SPARQLTarget ; sh:select """
SELECT ?this WHERE {
  ?pc <https://industryfusion.github.io/contexts/example/v0/base_entities/hasFilter>
      [ <https://uri.etsi.org/ngsi-ld/hasObject> ?this ] }""" ] ;
    sh:sparql [ a sh:SPARQLConstraint ; sh:select """
SELECT $this WHERE { $this ?p ?o . FILTER(false) }""" ] .
'''


def test_an_entity_from_the_model_the_query_does_not_reach_alone_is_refused(kms):
    """A query that reaches a Filter through the cutter pointing at it: the
    Filter copied from the model, without that cutter, is not evaluated."""
    _without_cases(kms)
    with open(os.path.join(kms, 'shacl.ttl'), 'a') as handle:
        handle.write(REACHED_THROUGH_A_CUTTER)
    for purpose in ('valid', 'invalid'):
        with pytest.raises(PackageError, match='not evaluated on urn:filter:1 without the rest'):
            new_case(load(kms), FILTERED, 'unreached', purpose, BASE + 'Filter')
        assert _tree(kms) == set(), 'no file and no folder'


def test_a_new_entity_takes_its_context_from_the_file_it_was_read_from(kms):
    """The context of a new entity is moved from the folder of the model file
    it was taken from, not from that of the first model file."""
    def local_context(document):
        document['@context'] = 'context.jsonld'
    _model_edit(kms, local_context)
    package = load(kms)
    elsewhere = os.path.join(kms, 'more', 'model.ttl')
    files = package.files
    package.files = lambda role: ([elsewhere] if role == 'model' else []) + files(role)
    made = new_case(package, ON_CUTTER, 'new', 'invalid', BASE + 'Lasercutter')
    with open(made['file']) as handle:
        assert {d['@context'] for d in json.load(handle)} == {'../../../context.jsonld'}


def test_a_new_entity_without_a_model_context_is_relative_to_the_package(tmp_path):
    """No model file names a context (or none can be read): the one kms.yaml
    names is the package's own, so it is relative to the package's folder."""
    from types import SimpleNamespace

    from semforge.expect.newcase import _context_home

    broken, bare = tmp_path / 'broken.jsonld', tmp_path / 'bare.json'
    broken.write_text('{ not json')
    bare.write_text('[{"id": "urn:x"}]')
    package = SimpleNamespace(path=str(tmp_path), files=lambda role: [
        str(tmp_path / 'model.ttl'), str(broken), str(bare)])
    assert _context_home(package) == str(tmp_path)


def test_one_entity_needs_no_run_to_be_put_first():
    from semforge.expect.newcase import _silent_first

    assert _silent_first(None, None, ['urn:a']) == ['urn:a']


def test_should_conform_counts_only_the_query(kms):
    """The second cutter breaks a property constraint of the query's own
    shape, on which the query is silent: it still comes first."""
    _without_cases(kms)

    def first_fires_second_breaks_a_property(document):
        if document['id'] == 'urn:filter:1':
            document['iffBaseEntities:hasState'][0]['value'] = {'@id': 'base:state_OFF'}
        if document['id'] == 'urn:plasmacutter:1':
            del document['iffBaseEntities:hasJSON']
    _model_edit(kms, first_fires_second_breaks_a_property)
    with open(os.path.join(kms, 'shacl.ttl'), 'a') as handle:
        handle.write('\niffBaseShacl:StateOnCutterShape sh:property '
                     '[ sh:path iffBaseEntities:hasJSON ; sh:maxCount 0 ] .\n')
    made = new_case(load(kms), ON_CUTTER, 'silent', 'valid', BASE + 'Cutter')
    assert made['resource'] == 'urn:plasmacutter:2', made


def test_should_conform_prefers_what_breaks_nothing_of_the_shape(kms):
    """The query is silent on both cutters, and the first breaks a property
    constraint of its shape: the test is about the second, which passes it."""
    _without_cases(kms)

    def only_the_first_has_json(document):
        if document['id'] == 'urn:plasmacutter:2':
            del document['iffBaseEntities:hasJSON']
    _model_edit(kms, only_the_first_has_json)
    with open(os.path.join(kms, 'shacl.ttl'), 'a') as handle:
        handle.write('\niffBaseShacl:StateOnCutterShape sh:property '
                     '[ sh:path iffBaseEntities:hasJSON ; sh:maxCount 0 ] .\n')
    made = new_case(load(kms), ON_CUTTER, 'silent', 'valid', BASE + 'Cutter')
    assert made['resource'] == 'urn:plasmacutter:2', made
    case = next(c for c in build_shape_page(load(kms), ON_CUTTER)['exercisedBy']
                if c['case'] == made['case'])
    assert case['firedOn'] == [], 'nothing of the shape fails on it'


def test_a_model_that_cannot_be_validated_keeps_the_plain_order(monkeypatch):
    from types import SimpleNamespace

    from semforge.expect.newcase import _silent_first
    from semforge.validate import orchestrator

    asked = []

    def broken(*_, **__):
        asked.append(True)
        raise RuntimeError('cannot validate')
    monkeypatch.setattr(orchestrator, 'validate_graphs', broken)
    package = SimpleNamespace(model=None, shapes=None, knowledge=None)
    assert _silent_first(package, 'urn:s', ['urn:a', 'urn:b']) == ['urn:a', 'urn:b'] and asked


def test_a_null_context_is_passed_over_as_the_new_entity_does(tmp_path):
    from types import SimpleNamespace

    from semforge.expect.newcase import _context_home

    (tmp_path / 'sub').mkdir()
    (tmp_path / 'null.jsonld').write_text('[{"@context": null, "id": "urn:a"}]')
    (tmp_path / 'sub' / 'named.jsonld').write_text('[{"@context": "context.jsonld", "id": "urn:b"}]')
    package = SimpleNamespace(path='/elsewhere', files=lambda role: [
        str(tmp_path / 'null.jsonld'), str(tmp_path / 'sub' / 'named.jsonld')])
    assert _context_home(package) == str(tmp_path / 'sub')


def test_a_refused_test_takes_back_the_examples_folder_it_made(kms):
    shutil.rmtree(os.path.join(kms, 'examples'))
    with pytest.raises(PackageError, match='not evaluated on a new entity'):
        new_case(load(kms), ON_FILTER, 'unseen', 'invalid', BASE + 'Workpiece')
    assert not os.path.exists(os.path.join(kms, 'examples'))


def test_a_shape_page_runs_nothing_after_writing(kms, monkeypatch):
    """New case… of a shape page writes and declares, as before: no run, so
    nothing a run could break takes the case away again."""
    from semforge.expect import addcase

    def broken(*_):
        raise RuntimeError('not to be run')
    monkeypatch.setattr(addcase, '_outcome', broken)
    made = new_case(load(kms), ON_FILTER, 'plain')
    assert os.path.exists(made['file']) and 'passes' not in made


def test_a_name_that_is_taken_is_refused_and_kept(kms):
    made = new_case(load(kms), ON_FILTER, 'taken', 'valid', BASE + 'Filter')
    with open(made['file'], 'rb') as handle:
        before = handle.read()
    with pytest.raises(PackageError, match='already exists'):
        new_case(load(kms), ON_FILTER, 'taken', 'valid', BASE + 'Filter')
    with open(made['file'], 'rb') as handle:
        assert handle.read() == before


def test_a_shape_page_still_writes_no_new_entity(kms):
    _without_cases(kms)
    with open(os.path.join(kms, 'model-instance.jsonld'), 'w') as handle:
        json.dump([], handle)
    with pytest.raises(PackageError, match='no scene'):
        new_case(load(kms), ON_FILTER, 'none')


def test_the_server_takes_the_kind_and_the_type(kms, monkeypatch):
    from semforge.editor import edits

    asked = {'uri': f'file://{kms}/kms.yaml', 'shape': ON_FILTER, 'name': 'served',
             'purpose': 'valid', 'entityType': BASE + 'Filter'}
    made = edits.new_case_feature(None, asked)
    assert made['ok'] and made['case'].endswith('good/served.jsonld') and made['passes']
    refused = edits.new_case_feature(None, dict(asked, name='other', purpose='sometimes'))
    assert not refused['ok'] and 'valid or invalid' in refused['error']
    assert edits.new_case_feature(None, dict(asked, name='plain', purpose='', entityType=''))['expect'] == 'invalid'


RULE_PAGE = {'ok': True, 'iri': BASE + 'Filter', 'label': 'Filter', 'crumbs': [], 'summary': {},
             'attributes': [], 'exercisedBy': [], 'instances': [], 'subtypes': [], 'rules': [
                 {'shape': 'https://x/S', 'shapeName': 'x:S', 'kind': 'constraint', 'text': 'too hot',
                  'inherited': False, 'tested': 'untested', 'definedAt': ''},
                 {'shape': 'https://x/R', 'shapeName': 'x:R', 'kind': 'rule', 'text': '',
                  'inherited': False, 'tested': '', 'definedAt': ''}]}


def _menu(tmp_path, row, **scenario):
    from test_tree_clicks import _drive

    return _drive(tmp_path, dict({
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'label': 'Filter', 'targetClass': BASE + 'Filter',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'ruleMenu', 'row': row}]}, **scenario))


def test_the_menu_of_a_query_writes_a_test(tmp_path):
    seen = _menu(tmp_path, 0, picks=['$(beaker) New test…', '$(error) Should fail'], inputs=['fires-2'],
                 replies={'semforge/typePage': RULE_PAGE,
                          'semforge/testCaseOptions': {'ok': True, 'undeclared': [], 'cases': [
                              {'path': 'test_S/bad/fires.jsonld'}]},
                          'semforge/newCase': {'ok': True, 'file': '/pkg/x.jsonld', 'case': 'x', 'passes': False,
                                               'failures': ['no'], 'source': 'the model', 'resource': 'urn:f'}})
    assert seen['errors'] == [], seen['errors']
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/newCase']
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'shape': 'https://x/S', 'name': 'fires-2',
                      'purpose': 'invalid', 'entityType': BASE + 'Filter'}]
    assert seen['inputs'][0]['value'] == 'fires-2', 'the first free name'
    assert any('fails until its data makes S fire on urn:f' in w for w in seen['warnings'])


def test_a_rule_derives_and_gets_no_test(tmp_path):
    seen = _menu(tmp_path, 1, picks=['$(beaker) New test…'], replies={'semforge/typePage': RULE_PAGE})
    assert not [r for r in seen['requests'] if r['method'] == 'semforge/testCaseOptions']


def test_new_test_offers_two_kinds_and_nothing_unanswered_is_written(tmp_path):
    seen = _menu(tmp_path, 0, picks=['$(beaker) New test…'], replies={'semforge/typePage': RULE_PAGE})
    offered = [i['label'] for i in seen['quickPicks'][1]['items']]
    assert offered == ['$(pass) Should conform', '$(error) Should fail']
    assert not [r for r in seen['requests'] if r['method'] == 'semforge/newCase']
    seen = _menu(tmp_path, 0, picks=['$(beaker) New test…', '$(pass) Should conform'], inputs=[],
                 replies={'semforge/typePage': RULE_PAGE,
                          'semforge/testCaseOptions': {'ok': True, 'undeclared': [], 'cases': []}})
    assert seen['inputs'][0]['value'] == 'silent'
    assert not [r for r in seen['requests'] if r['method'] == 'semforge/newCase']


def test_the_message_says_whether_it_passes(tmp_path):
    base = {'semforge/typePage': RULE_PAGE, 'semforge/testCaseOptions': {'ok': True, 'undeclared': [], 'cases': []}}
    for made, said, where in (
            ({'ok': True, 'file': '/pkg/x.jsonld', 'case': 'x', 'passes': True}, 'written, and it passes', 'info'),
            ({'ok': True, 'file': '/pkg/x.jsonld', 'case': 'x', 'passes': False, 'failures': ['urn:c violates']},
             'does not pass yet: urn:c violates', 'warnings'),
            ({'ok': False, 'error': 'not evaluated'}, 'not evaluated', 'errors')):
        seen = _menu(tmp_path, 0, picks=['$(beaker) New test…', '$(pass) Should conform'], inputs=['s'],
                     replies=dict(base, **{'semforge/newCase': made}))
        assert any(said in w for w in seen[where]), (said, seen[where])
