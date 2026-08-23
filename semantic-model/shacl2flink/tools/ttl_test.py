#!/usr/bin/env python3
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
Release test for the SHACL/SPARQL validation pipeline.

Not part of CI. Run it against a live cluster before a release, like
tools/loadgen.py. It creates its own entity family under unique UUID-based
ids (no collision with anything already on the cluster), drives it through
Scorpio so the full path is exercised (Scorpio -> Debezium -> bridge ->
Kafka -> Flink -> Alerta), and checks:

  * SPARQL rules      -- StateOnCutterShape, StateOnFilterShape,
                         FilterStrengthShape, StateValueShape: each must raise
                         on its trigger and retract on recovery.
  * SHACL checks      -- ClassConstraint (relationship to a wrong-class
                         entity), CountConstraint.
  * Count churn       -- many delete/insert cycles of the same [1,1]
                         relationship; count 0 and count 1 must both be
                         reported correctly and "Found 2" must never appear
                         in the verdict history.
  * Event time        -- observedAt governs, not arrival time: a newer-2024
                         value beats an older-2024 one regardless of arrival
                         order; a stale re-send does not overwrite; a delete
                         carries the timestamp of the value it deletes (so a
                         same-timestamp re-creation wins by arrival order);
                         once a 2026 value is in, no 2024 write can win again.
  * TTL survival      -- the tool reads the deployed table.exec.state.ttl
                         from the shacl-validation BeamSqlStatementSet and,
                         after the family has been idle for 3x that TTL,
                         re-runs the triggers. The spec is that validation
                         still works; if state expiry has killed the joins,
                         the tool reports exactly which operators swallow the
                         records (see below) instead of a bare failure.
  * Plan statistics   -- before and after every trigger the tool snapshots
                         the running job's per-vertex read/write counters via
                         the Flink REST API into a JSONL file, together with
                         the compiled plan (DAG + operator descriptions).
                         For every failed check it prints the operators that
                         received input but emitted nothing, so an unpinned
                         join or aggregate is visible immediately.

Requirements: kubectl access to the cluster (namespace iff by default) and
the usual local ingress names (ngsild.local, keycloak.local, alerta.local).
The Flink REST API is reached on --flink-rest (default http://localhost:8081)
and falls back to kubectl exec into the jobmanager pod.

  * Trigger latency  -- raise/restore cycles timed from the Kafka record
                        timestamps themselves (no polling error): Scorpio
                        write -> attributes record -> alert record ->
                        visible in Alerta, reported as min/median/p90/max
                        per stage. p90 of the pipeline's own reaction
                        (write to alert record) gates against
                        --latency-target (default 2 s). Runs in 'all',
                        'fresh' and standalone as --phase latency.
  * State growth     -- the growth phase drives tools/loadgen.py churn while
                        sampling the per-operator RocksDB directories on the
                        taskmanager: after a warmup that lets the new keys
                        populate every join, sustained updates must leave the
                        pinned join state on a plateau (updates replace rows,
                        never append them), while the attributes topic offset
                        proves the churn actually flowed.

Usage:
    python3 tools/ttl_test.py                      # full run (~3xTTL + 30 min + growth)
    python3 tools/ttl_test.py --phase fresh        # only the t=0 checks
    python3 tools/ttl_test.py --phase ttl          # create, idle 3xTTL, retest
    python3 tools/ttl_test.py --phase growth       # loadgen churn + state plateau
    python3 tools/ttl_test.py --phase latency      # per-stage trigger latency stats
    python3 tools/ttl_test.py --idle-factor 1      # shorten the idle wait
    python3 tools/ttl_test.py --keep               # leave the family behind
    python3 tools/ttl_test.py --teardown --run-id ab12cd34
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

CONTEXT = 'https://industryfusion.github.io/contexts/staging/example/v0.2/context.jsonld'
NGSILD = 'http://ngsild.local/ngsi-ld/v1'
KEYCLOAK = 'http://keycloak.local/auth/realms'
ALERTA = 'http://alerta.local/api'

ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities'
KNOW = 'https://industryfusion.github.io/contexts/example/v0/base_knowledge'
MATERIAL = 'https://industryfusion.github.io/contexts/ontology/v0/material/EN_1.4301'

RESULTS = []


def log(msg):
    print(f"[{datetime.datetime.now(datetime.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def record(phase, name, ok, detail=''):
    RESULTS.append({'phase': phase, 'name': name, 'ok': ok, 'detail': detail})
    log(f"   {'PASS' if ok else 'FAIL'}  {phase}/{name}  {detail}")


# --------------------------------------------------------------------------- plumbing

def _req(url, method='GET', token=None, body=None, ctype='application/ld+json'):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    if data:
        req.add_header('Content-Type', ctype)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()
    except Exception as err:
        return 0, str(err).encode()


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


class Token:
    """Auto-refreshing bearer token.

    Keycloak access tokens live ~5 minutes; a full run takes over an hour.
    The first live run silently 401'd every write after minute five and the
    post-TTL phases tested nothing -- hence: refresh proactively and pass
    THIS object (not a string) everywhere."""

    def __init__(self, namespace, user, client_id, password):
        self.namespace = namespace
        self.user = user
        self.client_id = client_id
        self.password = password or sh(
            f"kubectl -n {namespace} get secret/credential-iff-realm-user-iff"
            " -o jsonpath='{.data.password}' | base64 -d")
        self.value = None
        self.expires = 0.0

    def get(self):
        if time.time() > self.expires - 60:
            form = urllib.parse.urlencode({'client_id': self.client_id,
                                           'username': self.user,
                                           'password': self.password,
                                           'grant_type': 'password'}).encode()
            req = urllib.request.Request(
                f'{KEYCLOAK}/{self.namespace}/protocol/openid-connect/token',
                data=form, method='POST')
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read())
            self.value = payload['access_token']
            self.expires = time.time() + float(payload.get('expires_in', 300))
        return self.value


def discover_ttl(namespace):
    """Read table.exec.state.ttl from the deployed statementset (seconds)."""
    raw = sh(f"kubectl -n {namespace} get beamsqlstatementsets shacl-validation -o json")
    for setting in json.loads(raw)['spec']['sqlsettings']:
        for key, val in setting.items():
            if key == 'table.exec.state.ttl':
                m = re.match(r'(\d+)\s*(s|min|h)?', str(val))
                mult = {'s': 1, 'min': 60, 'h': 3600}.get(m.group(2) or 's', 1)
                return int(m.group(1)) * mult
    return None


def alerta_key(namespace):
    return sh(f"kubectl -n {namespace} get secret alerta"
              " -o jsonpath='{.data.alerta-admin-key}' | base64 -d")


# --------------------------------------------------------------------------- flink stats

class PlanStats:
    """Per-vertex read/write counters + compiled plan, snapshotted to JSONL."""

    def __init__(self, namespace, rest, statsfile):
        self.namespace = namespace
        self.rest = rest
        self.statsfile = statsfile
        self.jid = None
        self.snaps = []

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.rest + path, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception:
            pod = sh(f"kubectl -n {self.namespace} get pods --no-headers"
                     " -o custom-columns=:metadata.name | grep -m1 -E 'flink-deployment-[0-9a-f]'")
            out = sh(f"kubectl -n {self.namespace} exec {pod} -c flink-main-container --"
                     f" curl -s http://localhost:8081{path}")
            return json.loads(out) if out else {}

    def _find_job(self):
        for job in self._get('/jobs/overview').get('jobs', []):
            if job['state'] == 'RUNNING' and 'shacl' in job['name']:
                return job['jid']
        return None

    def snap(self, label):
        jid = self._find_job()
        if not jid:
            log(f"   stats: no running shacl job for snapshot '{label}'")
            return
        if jid != self.jid:
            self.jid = jid
            plan = self._get(f'/jobs/{jid}/plan')
            with open(self.statsfile.replace('.jsonl', f'.plan-{jid[:8]}.json'), 'w') as f:
                json.dump(plan, f)
        job = self._get(f'/jobs/{jid}')
        counters = {v['name']: [v['metrics']['read-records'], v['metrics']['write-records']]
                    for v in job.get('vertices', [])}
        entry = {'label': label, 'time': time.time(), 'jid': jid, 'counters': counters}
        self.snaps.append(entry)
        with open(self.statsfile, 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def swallowers(self, before_label, after_label):
        """Operators that received records between two snapshots but emitted none."""
        before = next((s for s in self.snaps if s['label'] == before_label), None)
        after = next((s for s in reversed(self.snaps) if s['label'] == after_label), None)
        if not before or not after or before['jid'] != after['jid']:
            return []
        out = []
        for name, (rin, rout) in after['counters'].items():
            bin_, bout = before['counters'].get(name, [0, 0])
            din, dout = rin - bin_, rout - bout
            if din > 0 and dout == 0 and 'Sink' not in name and 'Committer' not in name:
                out.append((din, name))
        return sorted(out, reverse=True)


# --------------------------------------------------------------------------- family

class Family:
    """A private entity family mirroring semantic-model/kms/model-instance.jsonld."""

    def __init__(self, run):
        self.run = run
        self.cutter = f'urn:rt:{run}:cutter'
        self.filter = f'urn:rt:{run}:filter'
        self.workpiece = f'urn:rt:{run}:workpiece'
        self.cartridge = f'urn:rt:{run}:cartridge'
        # a second cutter/filter pair reserved for the event-time check: its
        # hasStrength timeline must stay pristine 2024, and the other checks
        # restore with wall-clock (2026) observedAt -- which would correctly
        # lock every later 2024 write out and void the test.
        self.cutter2 = f'urn:rt:{run}:cutter2'
        self.filter2 = f'urn:rt:{run}:filter2'
        self.all = [self.cutter, self.filter, self.cutter2, self.filter2,
                    self.workpiece, self.cartridge]

    def entities(self):
        return [
            {'@context': CONTEXT, 'id': self.cutter, 'type': 'iffBaseEntities:Cutter',
             'iffBaseEntities:hasState': [{
                 'type': 'Property', 'value': {'@id': 'base:state_PROCESSING'},
                 'iffBaseEntities:hasXXXWorkpiece': {
                     'type': 'Relationship', 'object': self.workpiece}}],
             'iffBaseEntities:hasFilter': [{
                 'type': 'Relationship', 'object': self.filter,
                 'iffBaseEntities:hasTrust': [{
                     'type': 'Property', 'value': 2.1,
                     'iffBaseEntities:hasOutWorkpiecexx': {
                         'type': 'Property', 'value': 2.0, 'datasetId': 'urn:index:1'}}]}],
             'iffBaseEntities:hasInWorkpiece': [{
                 'type': 'Relationship', 'object': self.workpiece}],
             'iffBaseEntities:hasList': {'type': 'ListProperty', 'valueList': []},
             'iffBaseEntities:hasJSON': {'type': 'JsonProperty', 'json': {}}},
            {'@context': CONTEXT, 'id': self.filter, 'type': 'iffBaseEntities:Filter',
             'iffBaseEntities:hasState': [{'type': 'Property',
                                           'value': {'@id': 'base:state_ON'}}],
             'iffBaseEntities:hasCartridge': [{'type': 'Relationship',
                                               'object': self.cartridge}],
             'iffBaseEntities:hasStrength': [{'type': 'Property', 'value': 0.6,
                                              'observedAt': '2024-03-01T00:00:00.000Z'}]},
            {'@context': CONTEXT, 'id': self.cutter2, 'type': 'iffBaseEntities:Cutter',
             'iffBaseEntities:hasState': [{
                 'type': 'Property', 'value': {'@id': 'base:state_PROCESSING'},
                 'iffBaseEntities:hasXXXWorkpiece': {
                     'type': 'Relationship', 'object': self.workpiece}}],
             'iffBaseEntities:hasFilter': [{
                 'type': 'Relationship', 'object': self.filter2,
                 'iffBaseEntities:hasTrust': [{
                     'type': 'Property', 'value': 2.1,
                     'iffBaseEntities:hasOutWorkpiecexx': {
                         'type': 'Property', 'value': 2.0, 'datasetId': 'urn:index:1'}}]}],
             'iffBaseEntities:hasInWorkpiece': [{
                 'type': 'Relationship', 'object': self.workpiece}],
             'iffBaseEntities:hasList': {'type': 'ListProperty', 'valueList': []},
             'iffBaseEntities:hasJSON': {'type': 'JsonProperty', 'json': {}}},
            {'@context': CONTEXT, 'id': self.filter2, 'type': 'iffBaseEntities:Filter',
             'iffBaseEntities:hasState': [{'type': 'Property',
                                           'value': {'@id': 'base:state_ON'}}],
             'iffBaseEntities:hasCartridge': [{'type': 'Relationship',
                                               'object': self.cartridge}],
             'iffBaseEntities:hasStrength': [{'type': 'Property', 'value': 0.6,
                                              'observedAt': '2024-03-01T00:00:00.000Z'}]},
            {'@context': CONTEXT, 'id': self.workpiece, 'type': 'iffBaseEntities:Workpiece',
             'iffBaseEntities:hasMaterial': [{'type': 'Property',
                                              'value': {'@id': MATERIAL}}],
             'iffBaseEntities:hasHeight': [{'type': 'Property', 'value': 5}],
             'iffBaseEntities:hasLength': [{'type': 'Property', 'value': 100}],
             'iffBaseEntities:hasWidth': [{'type': 'Property', 'value': 100}]},
            {'@context': CONTEXT, 'id': self.cartridge,
             'type': 'iffBaseEntities:FilterCartridge',
             'iffBaseEntities:isUsedFrom': [{'type': 'Property',
                                             'value': '2024-02-27 13:54:55.4'}],
             'iffBaseEntities:isUsedUntil': [{'type': 'Property',
                                              'value': '2024-02-27 13:54:55.4'}]},
        ]


def _check_write(code, what):
    """Every silent write failure voids whatever the test asserts next --
    the first live run 401'd for an hour without anyone noticing."""
    if code not in (200, 201, 204, 207):
        log(f"   WRITE FAILED ({code}): {what}")
    return code


def upsert(token, entities):
    code, body = _req(f'{NGSILD}/entityOperations/upsert', 'POST', token.get(), entities)
    _check_write(code, f'upsert of {len(entities)} entities')
    return code, body


def post_attr(token, eid, short, fragment):
    body = {'@context': CONTEXT, f'iffBaseEntities:{short}': fragment}
    code, _ = _req(f'{NGSILD}/entities/{eid}/attrs', 'POST', token.get(), body)
    return _check_write(code, f'POST {short} on {eid}')


def del_attr(token, eid, short):
    enc = urllib.parse.quote(f'{ENT}/{short}', safe='')
    code, _ = _req(f'{NGSILD}/entities/{eid}/attrs/{enc}', 'DELETE', token.get())
    return _check_write(code, f'DELETE {short} on {eid}')


def del_entity(token, eid):
    code, _ = _req(f'{NGSILD}/entities/{eid}', 'DELETE', token.get())
    return code


def set_state(token, eid, state):
    return post_attr(token, eid, 'hasState',
                     {'type': 'Property', 'value': {'@id': f'{KNOW}/{state}'}})


def set_strength(token, eid, value, observed_at):
    return post_attr(token, eid, 'hasStrength',
                     {'type': 'Property', 'value': value, 'observedAt': observed_at})


def now_observed_at():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')


# --------------------------------------------------------------------------- alerta

def alerta_alerts(key, resource):
    url = f'{ALERTA}/alerts?' + urllib.parse.urlencode({'resource': resource})
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Key {key}')
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get('alerts', [])
    except Exception:
        return []


def wait_alert(key, resource, event_frag, want, timeout=150):
    """want: 'open' (any non-ok severity) or 'gone' (closed or absent).

    event_frag may be a string or a list of strings; every fragment must
    occur in the event name. A single component name is often ambiguous --
    e.g. a filter entity without the optional hasXXXWorkpiece sub-attribute
    carries a permanent CountConstraint warning, which must not shadow the
    hasCartridge count under test."""
    frags = [event_frag] if isinstance(event_frag, str) else list(event_frag)
    deadline = time.time() + timeout
    last = 'absent'
    while time.time() < deadline:
        hits = [a for a in alerta_alerts(key, resource)
                if all(f in a['event'] for f in frags)]
        if not hits:
            last = 'absent'
            if want == 'gone':
                return True, last
        else:
            a = sorted(hits, key=lambda x: x['lastReceiveTime'])[-1]
            last = f"{a['status']}/{a['severity']}"
            if want == 'open' and a['status'] == 'open' and a['severity'] != 'ok':
                return True, f"{last}: {a.get('text', '')[:200]}"
            if want == 'gone' and a['status'] != 'open':
                return True, last
        time.sleep(6)
    return False, last


# --------------------------------------------------------------------------- checks

def run_check(stats, key, name, phase, resource, event_frag, trigger, restore):
    """trigger() then expect the alert open; restore() then expect it gone."""
    stats.snap(f'{phase}:{name}:before')
    trigger()
    ok, detail = wait_alert(key, resource, event_frag, 'open')
    stats.snap(f'{phase}:{name}:after')
    record(phase, name, ok, detail)
    if not ok:
        for din, opname in stats.swallowers(f'{phase}:{name}:before',
                                            f'{phase}:{name}:after')[:6]:
            log(f"      swallowed {din:>4} records: {opname[:110]}")
    restore()
    ok2, detail2 = wait_alert(key, resource, event_frag, 'gone')
    record(phase, name + '.retract', ok2, detail2)
    return ok and ok2


def sparql_checks(stats, token, key, fam, phase):
    run_check(stats, key, 'StateOnCutterShape', phase, fam.cutter,
              'StateOnCutterShape',
              lambda: set_state(token, fam.filter, 'state_OFF'),
              lambda: set_state(token, fam.filter, 'state_ON'))
    run_check(stats, key, 'StateOnFilterShape', phase, fam.filter,
              'StateOnFilterShape',
              lambda: set_state(token, fam.cutter, 'state_ON'),
              lambda: set_state(token, fam.cutter, 'state_PROCESSING'))
    run_check(stats, key, 'FilterStrengthShape', phase, fam.filter,
              'FilterStrengthShape',
              lambda: set_strength(token, fam.filter, 0.3, now_observed_at()),
              lambda: set_strength(token, fam.filter, 0.6, now_observed_at()))
    run_check(stats, key, 'StateValueShape', phase, fam.cutter,
              'StateValueShape',
              lambda: set_state(token, fam.cutter, 'state_CLEANING'),
              lambda: set_state(token, fam.cutter, 'state_PROCESSING'))


def class_check(stats, token, key, fam, phase):
    run_check(stats, key, 'ClassConstraint', phase, fam.cutter,
              ['ClassConstraintComponent', 'hasFilter'],
              lambda: post_attr(token, fam.cutter, 'hasFilter',
                                [{'type': 'Relationship', 'object': fam.workpiece}]),
              lambda: post_attr(token, fam.cutter, 'hasFilter',
                                [{'type': 'Relationship', 'object': fam.filter,
                                  'iffBaseEntities:hasTrust': [{
                                      'type': 'Property', 'value': 2.1,
                                      'iffBaseEntities:hasOutWorkpiecexx': {
                                          'type': 'Property', 'value': 2.0,
                                          'datasetId': 'urn:index:1'}}]}]))


def count_churn(stats, token, key, fam, namespace, phase, cycles=5):
    """Delete/create the same [1,1] relationship repeatedly; count must only
    ever be 0 (violation) or 1 (ok), never 2."""
    stats.snap(f'{phase}:churn:before')
    for i in range(cycles):
        del_attr(token, fam.filter, 'hasCartridge')
        time.sleep(4)
        post_attr(token, fam.filter, 'hasCartridge',
                  [{'type': 'Relationship', 'object': fam.cartridge}])
        time.sleep(4)
    del_attr(token, fam.filter, 'hasCartridge')
    ok0, det0 = wait_alert(key, fam.filter,
                           ['CountConstraintComponent', 'hasCartridge'], 'open')
    found0 = 'Found 0' in det0
    record(phase, 'churn.count0', ok0 and found0, det0)
    post_attr(token, fam.filter, 'hasCartridge',
              [{'type': 'Relationship', 'object': fam.cartridge}])
    ok1, det1 = wait_alert(key, fam.filter,
                           ['CountConstraintComponent', 'hasCartridge'], 'gone')
    record(phase, 'churn.count1', ok1, det1)
    stats.snap(f'{phase}:churn:after')

    # audit the full verdict history in the trigger topic: "Found 2" must not exist
    hist = sh("kubectl -n %s exec my-cluster-nodes-0 -- sh -c \"KAFKA_HEAP_OPTS='-Xmx256M'"
              " bin/kafka-console-consumer.sh --bootstrap-server localhost:9092"
              " --topic iff.ngsild.flink.constraint_trigger_table --from-beginning"
              " --max-messages 3000 --timeout-ms 25000\" 2>/dev/null" % namespace)
    counts = set()
    for line in hist.splitlines():
        if fam.filter in line and 'hasCartridge' in line:
            counts.update(re.findall(r'Found (\d+)', line))
    bad = {c for c in counts if int(c) > 1}
    record(phase, 'churn.never2', not bad,
           f"counts seen in history: {sorted(counts) or 'none'}")


def event_time_check(stats, token, key, fam, phase):
    """observedAt governs the outcome, arrival order only breaks exact ties.

    Runs on the dedicated cutter2/filter2 pair: the other checks restore
    hasStrength with wall-clock observedAt, and a single 2026 record in this
    timeline legitimately locks out every later 2024 write."""
    ev = 'FilterStrengthShape'
    flt = fam.filter2
    stats.snap(f'{phase}:eventtime:before')

    set_strength(token, flt, 0.55, '2024-03-01T00:00:00.000Z')
    ok, det = wait_alert(key, flt, ev, 'gone')
    record(phase, 'et.baseline-2024-ok', ok, det)

    set_strength(token, flt, 0.3, '2024-03-01T00:00:01.000Z')
    ok, det = wait_alert(key, flt, ev, 'open')
    record(phase, 'et.newer-2024-wins', ok, det)

    # delete carries the timestamp of the value it deletes (00:00:01).
    # This step must run while Scorpio's stored value IS the event-time
    # incumbent: Scorpio keeps the last WRITTEN value, so a stale write
    # first would make the delete carry the stale timestamp and the
    # incumbent would out-rank it -- a documented semantic hole
    # (stale-write-then-delete leaves the incumbent standing), not a
    # sequencing accident this test should trip over.
    del_attr(token, flt, 'hasStrength')
    ok, det = wait_alert(key, flt, ev, 'gone')
    record(phase, 'et.delete-retracts', ok, det)

    # same event time as the delete -> tie, later arrival (the value) wins
    set_strength(token, flt, 0.3, '2024-03-01T00:00:01.000Z')
    ok, det = wait_alert(key, flt, ev, 'open')
    record(phase, 'et.tie-recreate-wins', ok, det)

    # stale write: older event time must NOT overwrite the newer value
    set_strength(token, flt, 0.55, '2024-03-01T00:00:00.000Z')
    time.sleep(90)
    hits = sorted((a for a in alerta_alerts(key, flt) if ev in a['event']),
                  key=lambda a: a['lastReceiveTime'])
    still = bool(hits) and hits[-1]['status'] == 'open'
    record(phase, 'et.stale-ignored', still,
           hits[-1]['status'] + '/' + hits[-1]['severity'] if hits else 'absent')

    # 2026 beats 2024
    set_strength(token, flt, 0.9, now_observed_at())
    ok, det = wait_alert(key, flt, ev, 'gone')
    record(phase, 'et.2026-wins', ok, det)

    # after 2026, no 2024 write may change the result again
    set_strength(token, flt, 0.3, '2024-03-01T00:00:02.000Z')
    time.sleep(90)
    hits = sorted((a for a in alerta_alerts(key, flt) if ev in a['event']),
                  key=lambda a: a['lastReceiveTime'])
    gone = not hits or hits[-1]['status'] != 'open'
    record(phase, 'et.2024-cannot-return', gone,
           hits[-1]['status'] + '/' + hits[-1]['severity'] if hits else 'absent')
    set_strength(token, flt, 0.6, now_observed_at())
    stats.snap(f'{phase}:eventtime:after')


def watch_resync_cadence(fam, namespace, ttl, wake):
    """While idling, verify the platform's re-feed actually happens.

    Unpinned join state only survives because the kafka-connect-restart cron
    forces a Debezium re-snapshot every TTL/2, republishing every entity.
    Watch iff.ngsild.entities during the idle window and assert that each
    family entity keeps arriving with gaps of at most TTL/2 plus latency
    slack -- a mistuned cron then fails HERE, not two phases later as an
    inexplicable join silence."""
    topic = 'iff.ngsild.entities'

    def end_offset():
        out = sh(f"kubectl -n {namespace} exec my-cluster-nodes-0 -- sh -c"
                 f" \"KAFKA_HEAP_OPTS='-Xmx192M' bin/kafka-get-offsets.sh"
                 f" --bootstrap-server localhost:9092 --topic {topic}\" 2>/dev/null")
        try:
            return int(out.rsplit(':', 1)[1])
        except Exception:
            return None

    last_seen = {eid: time.time() for eid in fam.all}
    gaps = {eid: 0.0 for eid in fam.all}
    pos = end_offset()
    while time.time() < wake:
        time.sleep(min(60, max(1, wake - time.time())))
        now = time.time()
        end = end_offset()
        if pos is None or end is None:
            pos = end
            continue
        if end > pos:
            n = end - pos
            recs = sh(f"kubectl -n {namespace} exec my-cluster-nodes-0 -- sh -c"
                      f" \"KAFKA_HEAP_OPTS='-Xmx192M' bin/kafka-console-consumer.sh"
                      f" --bootstrap-server localhost:9092 --topic {topic} --partition 0"
                      f" --offset {pos} --max-messages {n} --timeout-ms 15000\" 2>/dev/null")
            for eid in fam.all:
                if eid in recs:
                    gaps[eid] = max(gaps[eid], now - last_seen[eid])
                    last_seen[eid] = now
            pos = end
    now = time.time()
    for eid in fam.all:
        gaps[eid] = max(gaps[eid], now - last_seen[eid])
    worst = max(gaps.values())
    # allowed: TTL/2 target + one cron slot + restart-to-snapshot latency +
    # the one-minute sampling of this watcher
    allowed = ttl / 2 + 240
    ok = worst <= allowed
    detail = f"worst republication gap {worst:.0f}s (allowed {allowed:.0f}s, ttl {ttl}s)"
    record('ttl', 'resync-cadence', ok, detail)


def reset_family(token, fam):
    """Force complete re-publication: delete + recreate one attribute per
    entity (the bridge only re-emits the entity record when an attribute is
    inserted or deleted), then re-upsert the full family."""
    del_attr(token, fam.cutter, 'hasInWorkpiece')
    del_attr(token, fam.cutter2, 'hasInWorkpiece')
    del_attr(token, fam.filter, 'hasCartridge')
    del_attr(token, fam.filter2, 'hasCartridge')
    del_attr(token, fam.workpiece, 'hasHeight')
    del_attr(token, fam.cartridge, 'isUsedFrom')
    time.sleep(3)
    upsert(token, fam.entities())


# --------------------------------------------------------------------------- latency

def topic_end(namespace, topic):
    out = sh(f"kubectl -n {namespace} exec my-cluster-nodes-0 -- sh -c"
             f" \"KAFKA_HEAP_OPTS='-Xmx192M' bin/kafka-get-offsets.sh"
             f" --bootstrap-server localhost:9092 --topic {topic}\" 2>/dev/null")
    try:
        return int(out.rsplit(':', 1)[1])
    except Exception:
        return None


def topic_read(namespace, topic, offset, count):
    """[(create_time_ms, payload_json_or_None), ...] from offset, count records."""
    if count <= 0:
        return []
    out = sh(f"kubectl -n {namespace} exec my-cluster-nodes-0 -- sh -c"
             f" \"KAFKA_HEAP_OPTS='-Xmx256M' bin/kafka-console-consumer.sh"
             f" --bootstrap-server localhost:9092 --topic {topic} --partition 0"
             f" --offset {offset} --max-messages {count} --timeout-ms 15000"
             f" --property print.timestamp=true\" 2>/dev/null")
    recs = []
    for line in out.splitlines():
        m = re.match(r'CreateTime:(\d+)\s+(.*)', line)
        if not m:
            continue
        try:
            payload = json.loads(m.group(2))
        except Exception:
            payload = None
        recs.append((int(m.group(1)), payload))
    return recs


def pctl(sorted_vals, q):
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * q))]


def latency_phase(args, token, key, fam):
    """Per-stage trigger latency from Kafka broker timestamps.

    A validation platform whose alert arrives a minute late is useless, and
    the ordinary checks cannot see the difference: they poll alerta every
    6 s. This phase drives one rule through raise/restore cycles and takes
    the timestamps from the records themselves -- everything runs on one
    host, so the clocks agree:

        t1  attribute record lands in iff.ngsild.attributes
            (Scorpio commit + Debezium CDC + bridge)
        t2  alert record lands in iff.alerts.bulk (Flink evaluation)
        t3  alert visible via the Alerta API (bridge + alerta ingest),
            measured by fast polling (0.25 s), so an upper bound

    The pass/fail criterion is t2 -- the pipeline's own reaction time; the
    alerta hop is reported alongside because it is a consumer like any
    other."""
    ns = args.namespace
    ev = 'SPARQLConstraintComponent(StateOnCutterShape)'
    raises = []
    retracts = []

    def fast_wait(resource, want, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            hits = [a for a in alerta_alerts(key, resource) if ev in a['event']]
            is_open = bool(hits) and hits[-1]['status'] == 'open' \
                and hits[-1]['severity'] != 'ok'
            if (want == 'open') == is_open:
                return time.time()
            time.sleep(0.25)
        return None

    log(f"=== phase LATENCY: {args.latency_samples} raise/restore cycles on StateOnCutterShape ===")
    set_state(token, fam.filter, 'state_ON')
    fast_wait(fam.cutter, 'gone')
    for i in range(args.latency_samples):
        time.sleep(3)
        attr0 = topic_end(ns, 'iff.ngsild.attributes')
        bulk0 = topic_end(ns, 'iff.alerts.bulk')
        t0 = time.time()
        set_state(token, fam.filter, 'state_OFF')
        t3 = fast_wait(fam.cutter, 'open')
        t1 = t2 = None
        for ts, d in topic_read(ns, 'iff.ngsild.attributes', attr0,
                                (topic_end(ns, 'iff.ngsild.attributes') or attr0) - attr0):
            if d and d.get('entityId') == fam.filter and 'hasState' in str(d.get('name')):
                t1 = ts / 1000.0
                break
        for ts, d in topic_read(ns, 'iff.alerts.bulk', bulk0,
                                (topic_end(ns, 'iff.alerts.bulk') or bulk0) - bulk0):
            if d and d.get('resource') == fam.cutter and ev in str(d.get('event')) \
                    and d.get('severity') != 'ok':
                t2 = ts / 1000.0
                break
        raises.append({'attr': t1 - t0 if t1 else None,
                       'flink': t2 - t0 if t2 else None,
                       'alerta': t3 - t0 if t3 else None})
        r0 = time.time()
        set_state(token, fam.filter, 'state_ON')
        r3 = fast_wait(fam.cutter, 'gone')
        retracts.append(r3 - r0 if r3 else None)
        log(f"   sample {i + 1}: attr {fmt(raises[-1]['attr'])}, flink {fmt(raises[-1]['flink'])},"
            f" alerta {fmt(raises[-1]['alerta'])}, retract {fmt(retracts[-1])}")

    def dist(vals):
        vals = sorted(v for v in vals if v is not None)
        if not vals:
            return 'no data', None
        return (f"min {vals[0]:.2f}s median {pctl(vals, .5):.2f}s"
                f" p90 {pctl(vals, .9):.2f}s max {vals[-1]:.2f}s"), pctl(vals, .9)

    for stage in ('attr', 'flink', 'alerta'):
        text, _ = dist([s[stage] for s in raises])
        log(f"   raise->{stage:<6}: {text}")
    rtext, _ = dist(retracts)
    log(f"   retract(alerta): {rtext}")

    _, p90_flink = dist([s['flink'] for s in raises])
    record('latency', 'flink-p90',
           p90_flink is not None and p90_flink <= args.latency_target,
           f"p90 write->alert-record {p90_flink and f'{p90_flink:.2f}'}s"
           f" (target {args.latency_target:.1f}s)")
    _, p90_e2e = dist([s['alerta'] for s in raises])
    record('latency', 'alerta-e2e-p90', p90_e2e is not None,
           f"p90 write->alerta-visible {p90_e2e and f'{p90_e2e:.2f}'}s (informational)")


def fmt(v):
    return f'{v:.2f}s' if v is not None else '-'


# --------------------------------------------------------------------------- growth

def rocksdb_sizes(namespace):
    """(total_kb, join_kb, top_join_dirs) of the running job's RocksDB dirs.

    du of a live RocksDB fluctuates with WAL and compaction churn, so callers
    compare samples with slack rather than exactly."""
    pod = sh(f"kubectl -n {namespace} get pods --no-headers"
             " -o custom-columns=:metadata.name | grep -m1 taskmanager")
    out = sh(f"kubectl -n {namespace} exec {pod} -c flink-main-container --"
             " sh -c \"du -sk /tmp/rocksdb/* 2>/dev/null\"")
    total = joins = 0
    top = []
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        kb, path = int(parts[0]), parts[1]
        total += kb
        if 'StreamingJoinOperator' in path:
            joins += kb
            top.append((kb, path.rsplit('_op_', 1)[-1][:44]))
    return total, joins, sorted(top, reverse=True)


def attributes_end(namespace):
    out = sh(f"kubectl -n {namespace} exec my-cluster-nodes-0 -- sh -c"
             " \"KAFKA_HEAP_OPTS='-Xmx192M' bin/kafka-get-offsets.sh"
             " --bootstrap-server localhost:9092 --topic iff.ngsild.attributes\" 2>/dev/null")
    try:
        return int(out.rsplit(':', 1)[1])
    except Exception:
        return None


def growth_phase(args, token):
    """Churn the pipeline with loadgen and assert the pinned join state
    PLATEAUS: updates must replace rows, never append them.

    The warmup sample is taken after the loadgen entities exist and their
    keys have populated every join, so the assertion isolates growth caused
    by UPDATES from the legitimate one-time step of new keys."""
    ns = args.namespace
    here = os.path.dirname(os.path.abspath(__file__))
    loadgen = os.path.join(here, 'loadgen.py')
    env = dict(os.environ, LOADGEN_PASSWORD=token.password)

    def run_loadgen(extra):
        cmd = [sys.executable, loadgen, '--namespace', ns,
               '--entities', str(args.growth_entities)] + extra
        return subprocess.run(cmd, env=env, capture_output=True, text=True)

    log(f"=== phase GROWTH: {args.growth_entities} entities, "
        f"{args.growth_rate}/s for {args.growth_duration:.0f}s ===")
    r = run_loadgen(['--setup'])
    log('   loadgen setup: ' + (r.stdout.strip() or r.stderr.strip())[:120])
    log(f"   warmup {args.growth_warmup:.0f}s (new keys populate the joins)")
    time.sleep(args.growth_warmup)

    total_w, joins_w, _ = rocksdb_sizes(ns)
    a0 = attributes_end(ns)
    log(f"   warm sample: joins {joins_w} KB, all state {total_w} KB, attributes offset {a0}")

    proc = subprocess.Popen(
        [sys.executable, loadgen, '--namespace', ns,
         '--entities', str(args.growth_entities),
         '--rate', str(args.growth_rate),
         '--duration', str(args.growth_duration)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    samples = []
    while proc.poll() is None:
        time.sleep(180)
        total_i, joins_i, _ = rocksdb_sizes(ns)
        samples.append(joins_i)
        log(f"   sample: joins {joins_i} KB (all state {total_i} KB)")
    tail = (proc.stdout.read() or '').strip().splitlines()
    log('   loadgen: ' + (tail[-1] if tail else 'no output'))

    time.sleep(60)
    total_e, joins_e, top = rocksdb_sizes(ns)
    a1 = attributes_end(ns)
    log(f"   end sample: joins {joins_e} KB, all state {total_e} KB, attributes offset {a1}")
    for kb, name in top[:5]:
        log(f"      {kb:>7} KB  {name}")

    sent = (a1 - a0) if a0 is not None and a1 is not None else None
    expect = args.growth_rate * args.growth_duration * 0.5
    record('growth', 'updates-flowed', bool(sent and sent >= expect),
           f"{sent} attribute records during churn (expected >= {expect:.0f})")

    allowed = max(2048, int(joins_w * 0.05))
    grew = joins_e - joins_w
    record('growth', 'join-plateau', grew <= allowed,
           f"join state {joins_w} -> {joins_e} KB (delta {grew} KB, allowed {allowed} KB); "
           f"samples {samples}")

    r = run_loadgen(['--teardown'])
    log('   loadgen teardown: ' + (r.stdout.strip() or r.stderr.strip())[:120])


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--namespace', default='iff')
    ap.add_argument('--user', default='realm_user')
    ap.add_argument('--client-id', default='scorpio')
    ap.add_argument('--password', default=None)
    ap.add_argument('--flink-rest', default='http://localhost:8081')
    ap.add_argument('--phase', choices=['all', 'fresh', 'ttl', 'growth', 'latency'],
                    default='all')
    ap.add_argument('--latency-samples', type=int, default=10)
    ap.add_argument('--latency-target', type=float, default=2.0,
                    help='p90 write-to-alert-record budget in seconds')
    ap.add_argument('--idle-factor', type=float, default=3.0,
                    help='idle for this multiple of the deployed TTL (default 3)')
    ap.add_argument('--growth-entities', type=int, default=50)
    ap.add_argument('--growth-rate', type=float, default=10.0,
                    help='loadgen updates per second during the growth phase')
    ap.add_argument('--growth-duration', type=float, default=1800.0)
    ap.add_argument('--growth-warmup', type=float, default=240.0,
                    help='seconds between loadgen setup and the warm state sample')
    ap.add_argument('--settle', type=float, default=90.0,
                    help='seconds to wait after family creation')
    ap.add_argument('--run-id', default=None, help='reuse an existing family')
    ap.add_argument('--keep', action='store_true', help='do not delete the family')
    ap.add_argument('--teardown', action='store_true')
    ap.add_argument('--stats-file', default=None)
    args = ap.parse_args()

    run = args.run_id or uuid.uuid4().hex[:8]
    fam = Family(run)
    token = Token(args.namespace, args.user, args.client_id, args.password)
    key = alerta_key(args.namespace)

    if args.teardown:
        for eid in fam.all:
            log(f"delete {eid} -> {del_entity(token, eid)}")
        return 0

    ttl = discover_ttl(args.namespace)
    statsfile = args.stats_file or f'/tmp/ttl_test.{run}.stats.jsonl'
    stats = PlanStats(args.namespace, args.flink_rest, statsfile)
    log(f"run id {run}, deployed table.exec.state.ttl = {ttl} s, stats -> {statsfile}")
    if ttl is None:
        log('could not discover the TTL; aborting')
        return 2

    # the growth phase drives its own loadgen entities; no family needed
    if args.phase == 'growth':
        growth_phase(args, token)
        log('=== RESULTS ===')
        fails = 0
        for r in RESULTS:
            fails += 0 if r['ok'] else 1
            log(f"  {'PASS' if r['ok'] else 'FAIL'}  {r['phase']:>8}/{r['name']:<28} {r['detail'][:100]}")
        log(f"{len(RESULTS) - fails}/{len(RESULTS)} checks passed")
        return 1 if fails else 0

    log('creating family ' + ', '.join(fam.all))
    code, body = upsert(token, fam.entities())
    if code not in (200, 201, 204, 207):
        log(f'family creation failed: {code} {body[:200]}')
        return 2
    log(f'settling {args.settle:.0f}s')
    time.sleep(args.settle)
    stats.snap('baseline')
    last_write = time.time()

    if args.phase == 'latency':
        latency_phase(args, token, key, fam)

    if args.phase in ('all', 'fresh'):
        log('=== phase FRESH: full checks right after creation ===')
        sparql_checks(stats, token, key, fam, 'fresh')
        class_check(stats, token, key, fam, 'fresh')
        count_churn(stats, token, key, fam, args.namespace, 'fresh')
        event_time_check(stats, token, key, fam, 'fresh')
        latency_phase(args, token, key, fam)
        last_write = time.time()

    if args.phase in ('all', 'ttl'):
        idle = ttl * args.idle_factor
        wake = last_write + idle
        log(f"=== phase TTL: idling {idle:.0f}s ({args.idle_factor:.1f} x {ttl}s TTL) ===")
        watch_resync_cadence(fam, args.namespace, ttl, wake)
        log(f"idle over ({idle:.0f}s since last family write); re-running triggers")
        stats.snap('postttl:baseline')
        sparql_checks(stats, token, key, fam, 'postttl')
        class_check(stats, token, key, fam, 'postttl')

        failed = [r for r in RESULTS if r['phase'] == 'postttl' and not r['ok']]
        if failed:
            log(f"=== phase RESET: {len(failed)} post-TTL failures; full re-publication ===")
            reset_family(token, fam)
            time.sleep(45)
            sparql_checks(stats, token, key, fam, 'reset')

    if args.phase == 'all':
        growth_phase(args, token)

    if not args.keep:
        for eid in fam.all:
            del_entity(token, eid)
        log('family deleted (use --keep to retain it)')

    log('=== RESULTS ===')
    fails = 0
    for r in RESULTS:
        mark = 'PASS' if r['ok'] else 'FAIL'
        fails += 0 if r['ok'] else 1
        log(f"  {mark}  {r['phase']:>8}/{r['name']:<28} {r['detail'][:90]}")
    log(f"{len(RESULTS) - fails}/{len(RESULTS)} checks passed; stats in {statsfile}")
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
