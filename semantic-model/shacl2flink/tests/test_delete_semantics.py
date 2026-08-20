#
# Copyright (c) 2026 Intel Corporation
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

"""
Deleting an entity must retract the alerts raised against it.

Reported from a running cluster: deleting an object left its alerts standing
and produced new ones reading

    Model validation for relationship ...hasCartridge failed for urn:filter:1 .
    Found -1 relationships instead of [1, 1]!

-1 is the diagnosis. The count is `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`, whose
every term is 0 or 1, so in batch it cannot go below zero -- which is exactly
why the SQLite oracle and the pyshacl comparison agreed throughout while Flink
was wrong. On Flink the same expression is an incremental aggregate over a
changelog, and it reads -1 when it has applied one more retraction than it has
accumulations for that group.

What this file pins is the GROUPING half of that: a deleted entity must empty
its group rather than migrate to a muted one. It is asserted on the generated
SQL rather than end to end because the failure needs an hour of wall clock to
appear, and the e2e runs minutes after a deploy.

It deliberately does NOT pin the state TTL to "never expire". That was tried
and reverted -- expiry is the repair mechanism, not the fault. kafka-connect is
bounced every ttl/2 and Debezium rebuilds every live key from Postgres before
its state ages out, which sweeps drift; with the TTL disabled the same cluster
reported "Found 2" and "Found 3" for attributes existing exactly once, and kept
reporting them. What the tests below pin instead is that each view and the job
NAME the setting they use, so the choice is visible in the generated artefact
rather than silently inherited.

The behaviour these settings produce is covered by
tests/sql-tests/sql-cases/deleted-entities (batch semantics) and by the
deletion tests in the Flink e2e (the changelog path).
"""

import pathlib
import re

import ruamel.yaml

import create_ngsild_tables
import lib.configs as configs
import lib.shacl_properties_to_sql as props


def _entities_view_statement(tmp_path):
    """
    The entities_view as actually GENERATED -- create_ngsild_tables.py is run
    and its output read back.

    Rebuilding the view here by calling create_yaml_view with a ttl of our own
    would assert nothing about the call site: the hint would be present because
    the test put it there, and dropping it from the generator would still pass.
    """
    create_ngsild_tables.main(output_folder=str(tmp_path))
    document = (tmp_path / 'ngsild.yaml').read_text()
    for section in ruamel.yaml.YAML(typ='safe').load_all(document):
        if section and section.get('spec', {}).get('name') == 'entities_view':
            return section['spec']['sqlstatement']
    raise AssertionError('create_ngsild_tables.py emitted no entities_view')


def test_entity_dedup_names_its_own_state_ttl(tmp_path):
    """
    The view keeping the latest row per entity id carried no STATE_TTL hint at
    all, so whatever the job was set to applied to it silently. That is the
    part worth pinning: the value is a tuning decision, but it should be a
    VISIBLE one, stated in the generated artefact and changeable without
    touching every operator that happens to share the job.
    """
    statement = _entities_view_statement(tmp_path)
    assert 'STATE_TTL' in statement, \
        'entities_view has no STATE_TTL hint and silently inherits the job TTL'
    assert configs.view_state_ttl in statement, \
        'entities_view is not bound to the dedicated view TTL setting'


def test_view_and_job_ttl_are_separate_settings():
    """
    Separate knobs so the two can be moved independently while investigating.
    They default to the same value; this only pins that they can differ.
    """
    assert configs.view_state_ttl != configs.flink_ttl
    assert configs.shacl_state_ttl != configs.flink_ttl


def _helm_value(name):
    """The default of a flink.* key in the umbrella values file."""
    values = pathlib.Path(__file__).parents[3] / 'helm' / 'values.yaml.gotmpl'
    match = re.search(rf'^\s+{name}:\s*"([^"]*)"', values.read_text(),
                      re.MULTILINE)
    assert match, f'{name} is not defined in {values}'
    return match.group(1)


def test_deployed_state_ttls_still_expire():
    """
    None of these may be shipped as 0 ("never expire").

    Expiry is the repair mechanism: charts/kafka/templates/connect-restarter
    bounces kafka-connect every ttl/2, so Debezium rebuilds every live key from
    Postgres before its state ages out, and anything that has drifted -- an
    aggregate that lost a retraction, a dedup holding a row later records
    should have replaced -- is swept and reconstructed from a source of truth.

    Setting these to 0 was tried on a live cluster. Counts that should read 1
    reported "Found 2" and "Found 3" for attributes existing exactly once and
    stayed wrong across redeploys, because nothing swept them any more. It does
    not make bad state correct; it makes it permanent.
    """
    for name in ('ttl', 'viewTtl', 'shaclTtl'):
        value = _helm_value(name)
        assert not value.lstrip().startswith('0'), \
            f'flink.{name} = {value!r} disables expiry, so drifted state is ' \
            f'never rebuilt and becomes permanent'


def _generated_checks():
    """The relationship and property checks, exactly as generated."""
    flink_relationship, _ = props.create_relationship_sql()
    flink_property, _ = props.create_property_sql()
    return {'relationship': flink_relationship, 'property': flink_property}


def test_count_checks_do_not_group_by_edeleted():
    """
    `edeleted` as a grouping key means a deleted entity MIGRATES its rows from
    group (id, false) to group (id, true) instead of emptying the first, and
    the `NOT edeleted` in the HAVING then mutes only the new group. The old one
    is retracted only if every row it holds is retracted -- which is what stops
    happening once state expires. A retraction landing in a group whose
    accumulator was rebuilt from fewer rows is what produced "-1".
    """
    for name, sql in _generated_checks().items():
        clauses = re.findall(r'GROUP\s+BY\s(.*?)\sHAVING', sql,
                             re.IGNORECASE | re.DOTALL)
        assert clauses, f'{name}: no GROUP BY ... HAVING found to check'
        for group_by in clauses:
            assert 'edeleted' not in group_by.lower(), \
                f'{name}: edeleted is a grouping key again in {group_by.strip()}'


def test_count_checks_read_edeleted():
    """
    A count of zero means two different things and the count cannot tell them
    apart: an entity that is alive and has lost its mandatory attribute must
    alert, and an entity that has been deleted must not. Only `edeleted`
    separates them, so every counting HAVING has to read it.

    Filtering deleted entities out of A1 was tried instead, and made
    correctness depend on the rows disappearing and a retraction propagating
    through a LEFT JOIN and a COUNT(DISTINCT). Deleting the kms model in
    Scorpio then raised thirteen CountConstraint alerts that never cleared,
    while every row-level check -- each carrying `NOT edeleted` -- stayed
    correctly silent.
    """
    for name, sql in _generated_checks().items():
        clauses = re.findall(r'HAVING\s(.*?)(?:UNION\s+ALL|$)', sql,
                             re.IGNORECASE | re.DOTALL)
        assert clauses, f'{name}: no HAVING found to check'
        for having in clauses:
            assert 'edeleted' in having.lower(), \
                f'{name}: a counting HAVING ignores edeleted, so it cannot ' \
                f'tell "attribute gone" from "entity gone": {having.strip()[:120]}'


def test_edeleted_is_aggregated_not_filtered_in_counts():
    """
    Reading `edeleted` in a HAVING only works if it is aggregated. A bare
    column reference there would have to be a grouping key, which is the
    migration bug test_count_checks_do_not_group_by_edeleted exists to prevent.
    """
    for name, sql in _generated_checks().items():
        for having in re.findall(r'HAVING\s(.*?)(?:UNION\s+ALL|$)', sql,
                                 re.IGNORECASE | re.DOTALL):
            if 'edeleted' not in having.lower():
                continue
            assert re.search(r'(MAX|MIN|SUM|COUNT)\s*\([^)]*edeleted',
                             having, re.IGNORECASE), \
                f'{name}: edeleted appears unaggregated in a HAVING, which ' \
                f'forces it into the GROUP BY: {having.strip()[:120]}'


def test_counted_expressions_exclude_deleted_entities():
    """A count must count live data, not merely decline to report.

    `edeleted` in the HAVING decides whether to raise the alert; it does not
    change what was counted. With rows for a deleted incarnation left in A1 --
    which is deliberate, so the flag is there to read -- and only `adeleted`
    tested inside the CASE, those rows kept contributing. Deleting a model and
    reinstalling it under the same ids then reported "Found 2 relationships"
    for hasCartridge, hasFilter and hasXXXWorkpiece, each of which had exactly
    one row in tsdb. The duplicate was in the accumulator, not in the data.

    So every SUM/COUNT that counts attribute rows has to exclude deleted
    entities in the counted expression itself.
    """
    for name, sql in _generated_checks().items():
        counted = re.findall(r'(?:SUM|COUNT)\s*\(\s*(?:DISTINCT\s+)?CASE\s+WHEN(.*?)THEN',
                             sql, re.IGNORECASE | re.DOTALL)
        assert counted, f'{name}: no counted CASE expression found to check'
        for cond in counted:
            # Only the ones that count attributes; other CASEs may exist.
            if 'adeleted' not in cond.lower():
                continue
            assert 'edeleted' in cond.lower(), \
                f'{name}: a counted expression tests adeleted but not edeleted, so ' \
                f'rows of a deleted entity still contribute: {" ".join(cond.split())[:110]}'
