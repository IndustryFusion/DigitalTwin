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

"""Published versions and the tests they need (openspec gh-939-kms-package).

The scenarios of "Published versions are immutable", "Only tested versions are
published", "Coverage counts the constraints that fire", "The release record
holds the test results", and of `publish`, `version` and `verify --tests`.

The fixture is a fresh `semforge init` package: two examples, both passing,
and one of its fifteen constraints (MachineShape/hasTemperature/MaxInclusive)
asserted to fire -- 6.7 %. A declared threshold decides whether it may be
published.
"""

import datetime
import json
import os

import pytest
from click.testing import CliRunner

from semforge.cli.main import cli
from semforge.package.archive import PackageInvalid, pack
from semforge.package.conformance import check
from semforge.package.releases import (PublishRefused, next_versions, publish,
                                       raise_version, read_record, record_path,
                                       run_tests, status)
from semforge.package.scaffold import create_package

DAY = datetime.date(2026, 11, 7)
MAX = 'freshShacl:MachineShape/hasTemperature/MaxInclusiveConstraintComponent'


def _set_threshold(root, value):
    with open(os.path.join(root, 'kms.yaml'), 'a', encoding='utf-8') as handle:
        handle.write(f'\ntests:\n  coverage: {value}\n')


def _touch_shapes(root):
    with open(os.path.join(root, 'shacl.ttl'), 'a', encoding='utf-8') as handle:
        handle.write('\n# changed after publishing\n')


@pytest.fixture
def fresh(tmp_path):
    root = str(tmp_path / 'fresh')
    create_package(root, name='fresh', layout='flat')
    return root


@pytest.fixture
def publishable(fresh):
    _set_threshold(fresh, 5)
    return fresh


# --- coverage -------------------------------------------------------------------

def test_fired_as_asserted(fresh):
    run = run_tests(fresh)
    assert run.covered == [MAX]
    assert len(run.constraints) == 15 and run.coverage == 6.7


def test_satisfied_but_never_fired(fresh):
    # MinInclusive holds in both examples; no example asserts it.
    run = run_tests(fresh)
    assert 'freshShacl:MachineShape/hasTemperature/MinInclusiveConstraintComponent' \
        in run.uncovered


def test_fired_but_not_asserted_is_not_covered(fresh):
    """A violation nobody declared proves nothing about the constraint."""
    path = os.path.join(fresh, 'examples', 'test_MachineShape', 'bad', 'expectations.yaml')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text.replace('MaxInclusiveConstraintComponent',
                                  'MinInclusiveConstraintComponent'))
    run = run_tests(fresh)
    assert MAX not in run.covered


def test_scratchpad(fresh):
    # The scratchpad's entities never count, whatever they violate.
    with open(os.path.join(fresh, 'model-instance.jsonld'), encoding='utf-8') as handle:
        doc = json.load(handle)
    doc[0]['freshEntities:hasTemperature']['value'] = 999.0
    with open(os.path.join(fresh, 'model-instance.jsonld'), 'w', encoding='utf-8') as handle:
        json.dump(doc, handle)
    assert run_tests(fresh).covered == [MAX]


def test_no_constraints_is_full_coverage(fresh):
    from semforge.package.releases import TestRun
    assert TestRun(constraints=[]).coverage == 100.0


# --- the gate -----------------------------------------------------------------

def test_publishing_an_undertested_package(fresh, tmp_path):
    with pytest.raises(PublishRefused) as refused:
        publish(fresh, output=str(tmp_path / 'p.kms.zip'), today=DAY)
    assert 'coverage 6.7 % is below the threshold of 80 %' in str(refused.value)
    assert len(refused.value.run.uncovered) == 14
    assert not os.path.exists(tmp_path / 'p.kms.zip')
    assert read_record(record_path(fresh)) == []


def test_failing_example(publishable, tmp_path):
    path = os.path.join(publishable, 'examples', 'test_MachineShape', 'good',
                        'running.jsonld')
    with open(path, encoding='utf-8') as handle:
        doc = json.load(handle)
    doc[0]['freshEntities:hasTemperature']['value'] = 999.0           # now violates MaxInclusive
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(doc, handle)
    with pytest.raises(PublishRefused) as refused:
        publish(publishable, output=str(tmp_path / 'p.kms.zip'), today=DAY)
    assert any('running.jsonld' in p.path for p in refused.value.problems)


def test_declared_lower_threshold(publishable, tmp_path):
    published = publish(publishable, output=str(tmp_path / 'p.kms.zip'), today=DAY)
    [entry] = read_record(record_path(publishable))
    assert entry == {'version': '0.1.0', 'digest': published.digest,
                     'date': '2026-11-07', 'examples': 2, 'met': 2,
                     'coverage': 6.7, 'threshold': 5.0}


def test_draft_below_the_threshold(fresh, tmp_path):
    assert check(fresh).ok
    assert pack(fresh, output=str(tmp_path / 'p.kms.zip')).digest
    assert status(fresh) == 'draft'


# --- immutability ------------------------------------------------------------------

def test_changed_after_publishing(publishable, tmp_path):
    publish(publishable, output=str(tmp_path / 'p.kms.zip'), today=DAY)
    assert status(publishable) == 'published'
    _touch_shapes(publishable)
    problems = [str(p) for p in check(publishable).problems]
    assert any('fresh 0.1.0 is published' in p and 'raise the version' in p
               for p in problems), problems


def test_raised_after_a_change(publishable, tmp_path):
    publish(publishable, output=str(tmp_path / 'p.kms.zip'), today=DAY)
    _touch_shapes(publishable)
    raise_version(publishable, 'patch')
    assert check(publishable).ok
    assert status(publishable) == 'draft'


def test_packing_a_changed_published_version(publishable, tmp_path):
    publish(publishable, output=str(tmp_path / 'p.kms.zip'), today=DAY)
    _touch_shapes(publishable)
    with pytest.raises(PackageInvalid):
        pack(publishable, output=str(tmp_path / 'q.kms.zip'))
    assert not os.path.exists(tmp_path / 'q.kms.zip')


def test_publishing_again_unchanged(publishable, tmp_path):
    first = publish(publishable, output=str(tmp_path / 'a.kms.zip'), today=DAY)
    before = open(record_path(publishable), encoding='utf-8').read()
    again = publish(publishable, output=str(tmp_path / 'b.kms.zip'),
                    today=DAY + datetime.timedelta(days=3))
    assert again.unchanged
    assert open(record_path(publishable), encoding='utf-8').read() == before
    with open(first.path, 'rb') as a, open(again.path, 'rb') as b:
        assert a.read() == b.read()


def test_the_record_is_not_a_member(publishable, tmp_path):
    digest = check(publishable).digest
    publish(publishable, output=str(tmp_path / 'p.kms.zip'), today=DAY)
    assert check(publishable).digest == digest


# --- versions ------------------------------------------------------------------------

def test_minor_raise(fresh):
    path = os.path.join(fresh, 'kms.yaml')
    text = open(path, encoding='utf-8').read().replace('version: 0.1.0', 'version: 1.2.3')
    open(path, 'w', encoding='utf-8').write(text)
    assert raise_version(fresh, 'minor') == ('1.2.3', '1.3.0')
    after = open(path, encoding='utf-8').read()
    assert after == text.replace('version: 1.2.3', 'version: 1.3.0')


def test_next_versions():
    assert next_versions('1.2.3') == {'patch': '1.2.4', 'minor': '1.3.0',
                                      'major': '2.0.0'}


# --- commands --------------------------------------------------------------------------

def test_cli_publish_refused(fresh, tmp_path):
    result = CliRunner().invoke(cli, ['publish', fresh, '-o', str(tmp_path / 'p.kms.zip')])
    assert result.exit_code == 2
    assert '6.7 % is below the threshold of 80 %' in result.output
    assert MAX not in result.output.split('not covered:')[-1]


def test_cli_publish_and_version(publishable, tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ['publish', publishable, '-o', str(tmp_path / 'p.kms.zip')])
    assert result.exit_code == 0, result.output
    assert 'recorded in .kms/releases.yaml' in result.output
    _touch_shapes(publishable)
    assert runner.invoke(cli, ['verify', publishable]).exit_code == 2
    raised = runner.invoke(cli, ['version', 'patch', publishable])
    assert raised.exit_code == 0 and '0.1.0 -> 0.1.1' in raised.output
    assert runner.invoke(cli, ['verify', publishable]).exit_code == 0


def test_re_running_an_archive_against_its_record(publishable, tmp_path):
    out = str(tmp_path / 'p.kms.zip')
    publish(publishable, output=out, today=DAY)
    result = CliRunner().invoke(cli, ['verify', '--tests', out, '--record',
                                      record_path(publishable), '--format', 'json'])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data['tests']['examples'] == 2 and data['tests']['coverage'] == 6.7
    assert data['record'].startswith('matches')


def test_re_running_an_archive_alone(publishable, tmp_path):
    out = str(tmp_path / 'p.kms.zip')
    publish(publishable, output=out, today=DAY)
    result = CliRunner().invoke(cli, ['verify', '--tests', out])
    assert result.exit_code == 0, result.output
    assert 'no release record was compared' in result.output
    assert 'coverage 6.7 %' in result.output


def test_a_record_that_disagrees(publishable, tmp_path):
    out = str(tmp_path / 'p.kms.zip')
    publish(publishable, output=out, today=DAY)
    record = record_path(publishable)
    text = open(record, encoding='utf-8').read().replace('coverage: 6.7', 'coverage: 90.0')
    open(record, 'w', encoding='utf-8').write(text)
    result = CliRunner().invoke(cli, ['verify', '--tests', out, '--record', record])
    assert result.exit_code == 2 and 'coverage is 6.7' in result.output


def test_publishing_an_archive_is_refused(publishable, tmp_path):
    out = str(tmp_path / 'p.kms.zip')
    pack(publishable, output=out)
    result = CliRunner().invoke(cli, ['publish', out])
    assert result.exit_code == 2 and 'read-only' in result.output


def test_default_threshold_shown(fresh):
    from semforge.package.config import settings
    row = {s.key: s for s in settings(fresh)}['tests.coverage']
    assert row.value == '' and row.default == '80' and row.editable
    result = CliRunner().invoke(cli, ['where', fresh])
    assert 'coverage threshold 80 %  (the default)' in result.output
    assert 'version  0.1.0  (draft)' in result.output


# --- what CI runs: `semforge verify --tests` on every package (make kms-check) ---

def test_ci_broken_example(publishable):
    path = os.path.join(publishable, 'examples', 'test_MachineShape', 'good',
                        'running.jsonld')
    with open(path, encoding='utf-8') as handle:
        doc = json.load(handle)
    doc[0]['freshEntities:hasTemperature']['value'] = 999.0
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(doc, handle)
    result = CliRunner().invoke(cli, ['verify', '--tests', publishable])
    assert result.exit_code == 2 and 'running.jsonld' in result.output


def test_ci_changed_published_version(publishable, tmp_path):
    publish(publishable, output=str(tmp_path / 'p.kms.zip'), today=DAY)
    _touch_shapes(publishable)
    result = CliRunner().invoke(cli, ['verify', '--tests', publishable])
    assert result.exit_code == 2
    assert 'fresh 0.1.0 is published' in result.output


def test_ci_draft_with_low_coverage(fresh):
    result = CliRunner().invoke(cli, ['verify', '--tests', fresh])
    assert result.exit_code == 0, result.output
    assert 'coverage 6.7 % of 15 constraints (threshold 80 %)' in result.output


def test_ci_published_below_its_threshold(publishable, tmp_path):
    """Raising the threshold of a published version changes its descriptor,
    so the version must be raised -- the threshold cannot move under it."""
    publish(publishable, output=str(tmp_path / 'p.kms.zip'), today=DAY)
    path = os.path.join(publishable, 'kms.yaml')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text.replace('coverage: 5', 'coverage: 50'))
    assert CliRunner().invoke(cli, ['verify', '--tests', publishable]).exit_code == 2


# --- `semforge test --coverage` reports the coverage publish gates on ------------

KMS_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           '..', '..', '..', 'kms', 'default')


def _summary(result):
    return [x for x in result.output.splitlines() if x.startswith('coverage ')][-1]


@pytest.mark.parametrize('which', ['fresh', 'kms'])
def test_test_coverage_reports_what_verify_reports(fresh, which):
    root = fresh if which == 'fresh' else KMS_DEFAULT
    runner = CliRunner()
    tested = runner.invoke(cli, ['test', root, '--coverage'])
    verified = runner.invoke(cli, ['verify', '--tests', root, '--format', 'json'])
    data = json.loads(verified.output[verified.output.index('{'):])['tests']
    assert _summary(tested).startswith(
        f"coverage {data['coverage']:g} % of {data['constraints']} constraints: "
        f"{data['covered']} fire")
    assert 'not publishable' in tested.output


def test_test_coverage_reconciles_with_the_list(fresh):
    result = CliRunner().invoke(cli, ['test', fresh, '--coverage'])
    listed = [x for x in result.output.splitlines()
              if x.startswith('  ') and x.rstrip().endswith(']')]
    summary = _summary(result)
    total = int(summary.split(' of ')[1].split(' ')[0])
    unevaluated = int(summary.split(', ')[-1].split(' ')[0])
    assert len(listed) == total - unevaluated


def test_test_coverage_says_publishable(publishable):
    result = CliRunner().invoke(cli, ['test', publishable, '--coverage'])
    assert 'threshold 5 % -- publishable' in result.output
