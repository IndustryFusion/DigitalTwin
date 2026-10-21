"""What export and the cross-check promise -- the review's findings 2-4.

* Broker export keeps one instance per (attribute, datasetId): the one
  validation reads (the latest point in time, an unstamped one counting as
  now), sub-attributes too; a tie for the latest is refused, never guessed.
* The sh:nodeKind sh:BlankNode export adds is a SHACL constraint the author did
  not write: the export names every shape it changed, and the corpus
  validates identically with and without the added constraints.
* The SQLite cross-check compares with counts, and reports what the compiler
  is known not to compile as expected, not as a divergence.
"""

import json
import re
import shutil

import pytest
from rdflib import Graph

from semforge.package import load
from semforge.target.crosscheck import compare
from semforge.target.export import (AmbiguousInstances, EmissionMode, collapse_for_broker,
                                    complete_node_kinds, export)
from semforge.validate.orchestrator import validate_graphs
from semforge.validate.results import Result


def _entity(*instances, **extra):
    return [dict({'id': 'urn:e:1', 'type': 'E', 'hasX': list(instances)}, **extra)]


# --- finding 4: broker export ----------------------------------------------------------

def test_the_broker_gets_the_instance_validation_reads():
    stamped = {'type': 'Property', 'value': 1, 'observedAt': '2999-01-01T00:00:00.000Z'}
    bare = {'type': 'Property', 'value': 2}
    entities = _entity(stamped, bare)
    assert collapse_for_broker(entities) == 1
    assert entities[0]['hasX'] == [bare], 'an unstamped instance is now, and supersedes'


def test_times_are_compared_as_points_in_time():
    earlier = {'type': 'Property', 'value': 1, 'observedAt': '2024-02-28T14:00:00.000+02:00'}
    later = {'type': 'Property', 'value': 2, 'observedAt': '2024-02-28T13:00:00.000Z'}
    entities = _entity(earlier, later)
    collapse_for_broker(entities)
    assert entities[0]['hasX'] == [later], '14:00+02:00 is 12:00 UTC'


def test_datasetids_are_kept_apart_and_sub_attributes_collapse_too():
    old = {'type': 'Property', 'value': 1, 'observedAt': '2024-01-01T00:00:00.000Z'}
    new = dict(old, value=2, observedAt='2024-02-01T00:00:00.000Z')
    holder = dict(old, hasY=[old, new])
    entities = _entity(holder, dict(old, datasetId='urn:d:b'))
    assert collapse_for_broker(entities) == 1
    assert [i.get('datasetId') for i in entities[0]['hasX']] == [None, 'urn:d:b']
    assert entities[0]['hasX'][0]['hasY'] == [new]


@pytest.mark.parametrize('first, second', [
    ({'value': 1}, {'value': 2}),
    ({'value': 1, 'observedAt': '2024-01-01T00:00:00.000Z'},
     {'value': 2, 'observedAt': '2024-01-01T01:00:00+01:00'})])
def test_a_tie_for_the_latest_is_refused_not_guessed(first, second):
    with pytest.raises(AmbiguousInstances, match=r'urn:e:1 hasX \(default\)'):
        collapse_for_broker(_entity(first, second))


def test_a_refused_export_writes_nothing(tmp_path, corpus_path):
    package = tmp_path / 'kms'
    shutil.copytree(corpus_path, package, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    model = package / 'model-instance.jsonld'
    document = json.loads(model.read_text())
    entity = next(e for e in document if e.get('id') == 'urn:filter:1')
    key = next(k for k in entity if k.endswith('hasStrength'))
    entity[key] = [{k: v for k, v in i.items() if k != 'observedAt'} for i in entity[key]]
    model.write_text(json.dumps(document))
    out = tmp_path / 'out'
    with pytest.raises(AmbiguousInstances):
        export(load(str(package)), str(out), EmissionMode.BROKER)
    assert not out.exists()


def test_the_kms_model_exports_for_the_broker(corpus, tmp_path):
    written = export(corpus, str(tmp_path / 'out'), EmissionMode.BROKER)
    assert written['collapsed'] == 3


# --- finding 3: the constraint export adds ----------------------------------------------

def _stripped(corpus):
    with open(corpus.sources['shapes']) as handle:
        text = handle.read()
    stripped = re.sub(r'sh:nodeKind sh:BlankNode ;\s*', '', text)
    assert stripped != text
    return stripped


def test_the_export_names_every_shape_it_changed(corpus):
    places = []
    completed, added = complete_node_kinds(_stripped(corpus), places)
    assert added == len(places) > 0
    assert all(' › ' in place and place.split(' › ')[0].endswith('Shape') for place in places)
    assert 'iffBaseShacl:FilterShape › iffBaseEntities:hasStrength' in places


def test_the_added_constraint_changes_no_verdict_on_the_corpus(corpus):
    """The contract: on NGSI-LD data an attribute IS a blank node, so stating
    it decides nothing -- the corpus validates identically without and with."""
    stripped = _stripped(corpus)
    completed, _ = complete_node_kinds(stripped)

    def verdicts(text):
        report = validate_graphs(corpus.model, Graph().parse(data=text, format='turtle'),
                                 corpus.knowledge, strict=False)
        return sorted((r.resource, r.attribute, r.component) for r in report.violations)

    assert verdicts(stripped) == verdicts(completed)


# --- finding 2: the cross-check ---------------------------------------------------------

def _result(attribute, component, resource='urn:e:1'):
    return Result(resource=resource, attribute=attribute, component=component,
                  shape='urn:s:S', severity='violation')


def test_the_cross_check_keeps_counts():
    """Two minCount violations on one attribute (the attribute's and its
    value's) against one in the SQL: still a difference."""
    rows = [('urn:e:1', 'CountConstraintComponent(hasX)', 'violation')]
    ours = [_result('hasX', 'MinCountConstraintComponent')] * 2
    [found] = compare(rows, ours)
    assert found.code == 'SF-XCHK-EXTRA'


def test_what_the_compiler_does_not_compile_is_expected_not_a_divergence():
    found = compare([], [_result('hasX.unitCode', 'InConstraintComponent'),
                         _result('hasX', 'NodeConstraintComponent'),
                         _result('hasX', 'MaxInclusiveConstraintComponent')])
    assert [(f.code, f.severity, f.message.split(' on ')[0]) for f in found] == [
        ('SF-XCHK-EXTRA', 'warning', 'pyshacl reports MaxInclusiveConstraintComponent(hasX)'),
        ('SF-XCHK-EXPECTED', 'info', 'pyshacl reports NodeConstraintComponent(hasX)'),
        ('SF-XCHK-EXPECTED', 'info', 'pyshacl reports InConstraintComponent(hasX.unitCode)')]
    assert 'expected, not a compiler bug' in found[1].message


def test_agreement_is_silent():
    rows = [('urn:e:1', 'CountConstraintComponent(hasX)', 'violation'),
            ('urn:e:1', 'Something(hasY)', 'ok')]
    assert compare(rows, [_result('hasX', 'MinCountConstraintComponent')]) == []
