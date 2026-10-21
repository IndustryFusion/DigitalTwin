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
