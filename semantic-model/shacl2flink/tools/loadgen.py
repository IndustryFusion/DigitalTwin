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
NGSI-LD load generator.

Drives entities through Scorpio so the whole pipeline is exercised end to end
(Scorpio -> Postgres -> Debezium -> kafka-bridge -> attributes -> Flink), rather
than injecting into Kafka and skipping the bridge.

Mutations deliberately cover every shape the translator has to handle, because
each one costs differently in the generated SQL:

  * plain Property value                       -> leaf check
  * Relationship object                        -> link check + join to target
  * sub-attribute (Relationship in a Property) -> one extra attributes_view join
  * sub-sub-attribute                          -> two extra joins
  * ListProperty / JsonProperty                -> separate nodeType branches
  * datasetId                                  -> multi-instance keying

Usage:
    python3 tools/loadgen.py --setup --entities 20
    python3 tools/loadgen.py --entities 20 --rate 10 --duration 300
    python3 tools/loadgen.py --teardown --entities 20
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CONTEXT = 'https://industryfusion.github.io/contexts/staging/example/v0.2/context.jsonld'
NGSILD = 'http://ngsild.local/ngsi-ld/v1'
KEYCLOAK = 'http://keycloak.local/auth/realms'

STATES = ['base:state_ON', 'base:state_OFF', 'base:state_PROCESSING']
# Mutation kinds, cycled deterministically so a run is reproducible.
KINDS = ['state', 'substate_link', 'filter_link', 'trust', 'subsub', 'list', 'json']


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
    except Exception as err:                                  # noqa: BLE001
        return 0, str(err).encode()


def get_token(namespace, user, client_id, password):
    form = urllib.parse.urlencode({'client_id': client_id, 'username': user,
                                   'password': password,
                                   'grant_type': 'password'}).encode()
    req = urllib.request.Request(f'{KEYCLOAK}/{namespace}/protocol/openid-connect/token',
                                 data=form, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())['access_token']


def cutter(index):
    """A Cutter carrying every attribute shape the translator supports."""
    return {
        '@context': CONTEXT,
        'id': f'urn:loadcutter:{index}',
        'type': 'iffBaseEntities:Cutter',
        'iffBaseEntities:hasState': [{
            'type': 'Property',
            'value': {'@id': STATES[0]},
            # sub-attribute: a Relationship hanging off a Property
            'iffBaseEntities:hasXXXWorkpiece': {
                'type': 'Relationship',
                'object': f'urn:loadworkpiece:{index}'}}],
        'iffBaseEntities:hasFilter': [{
            'type': 'Relationship',
            'object': f'urn:loadfilter:{index}',
            'iffBaseEntities:hasTrust': [{
                'type': 'Property',
                'value': 2.1,
                # sub-sub-attribute, with an explicit datasetId
                'iffBaseEntities:hasOutWorkpiecexx': {
                    'type': 'Property',
                    'value': 2.0,
                    'datasetId': 'urn:index:1'}}]}],
        'iffBaseEntities:hasInWorkpiece': [{
            'type': 'Relationship',
            'object': f'urn:loadworkpiece:{index}'}],
        'iffBaseEntities:hasList': {'type': 'ListProperty', 'valueList': []},
        'iffBaseEntities:hasJSON': {'type': 'JsonProperty', 'json': {}},
    }


def support(index):
    """The Filter and Workpiece a Cutter links to."""
    return [
        {'@context': CONTEXT, 'id': f'urn:loadfilter:{index}',
         'type': 'iffBaseEntities:Filter',
         'iffBaseEntities:hasState': [{'type': 'Property',
                                       'value': {'@id': STATES[0]}}]},
        {'@context': CONTEXT, 'id': f'urn:loadworkpiece:{index}',
         'type': 'iffBaseEntities:Workpiece'},
        {'@context': CONTEXT, 'id': f'urn:loadworkpiece:alt{index}',
         'type': 'iffBaseEntities:Workpiece'},
        {'@context': CONTEXT, 'id': f'urn:loadfilter:alt{index}',
         'type': 'iffBaseEntities:Filter',
         'iffBaseEntities:hasState': [{'type': 'Property',
                                       'value': {'@id': STATES[1]}}]},
    ]


def mutated_entity(kind, index, tick):
    """
    Full entity with exactly one shape varied.

    Upsert rather than PATCH: Scorpio's merge-patch is picky about array vs
    object form per attribute ("cannot get array length of a scalar"), while
    upsert always accepts the canonical shape. Downstream this is still a
    single-attribute change, because the debezium bridge diffs before/after
    (KafkaBridge/lib/debeziumBridge.js diffAttributes) and only emits what
    actually changed.
    """
    ent = cutter(index)
    ent.update(mutation(kind, index, tick))
    return ent


def mutation(kind, index, tick):
    """Smallest fragment that changes exactly one shape."""
    alt = 'alt' if tick % 2 else ''
    if kind == 'state':
        return {'iffBaseEntities:hasState': [{
            'type': 'Property', 'value': {'@id': STATES[tick % len(STATES)]}}]}
    if kind == 'substate_link':
        return {'iffBaseEntities:hasState': [{
            'type': 'Property', 'value': {'@id': STATES[tick % len(STATES)]},
            'iffBaseEntities:hasXXXWorkpiece': {
                'type': 'Relationship',
                'object': f'urn:loadworkpiece:{alt}{index}'}}]}
    if kind == 'filter_link':
        return {'iffBaseEntities:hasFilter': [{
            'type': 'Relationship', 'object': f'urn:loadfilter:{alt}{index}'}]}
    if kind == 'trust':
        return {'iffBaseEntities:hasFilter': [{
            'type': 'Relationship', 'object': f'urn:loadfilter:{index}',
            'iffBaseEntities:hasTrust': [{
                'type': 'Property', 'value': round(1.0 + (tick % 50) / 10.0, 2)}]}]}
    if kind == 'subsub':
        return {'iffBaseEntities:hasFilter': [{
            'type': 'Relationship', 'object': f'urn:loadfilter:{index}',
            'iffBaseEntities:hasTrust': [{
                'type': 'Property', 'value': 2.1,
                'iffBaseEntities:hasOutWorkpiecexx': {
                    'type': 'Property', 'value': float(tick % 30),
                    'datasetId': 'urn:index:1'}}]}]}
    if kind == 'list':
        return {'iffBaseEntities:hasList': {
            'type': 'ListProperty', 'valueList': list(range(tick % 4))}}
    return {'iffBaseEntities:hasJSON': {
        'type': 'JsonProperty', 'json': {'tick': tick, 'idx': index}}}


def upsert(token, entities):
    return _req(f'{NGSILD}/entityOperations/upsert', 'POST', token, entities)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--entities', type=int, default=10)
    ap.add_argument('--rate', type=float, default=5.0, help='updates per second')
    ap.add_argument('--duration', type=float, default=120.0, help='seconds')
    ap.add_argument('--namespace', default='iff')
    ap.add_argument('--user', default='realm_user')
    ap.add_argument('--client-id', default='scorpio')
    # Prefer the environment: a --password argument is visible to any user via
    # `ps`, which matters even on a dev cluster because this is a real Keycloak
    # credential.
    ap.add_argument('--password', default=None,
                    help='realm user password; prefer LOADGEN_PASSWORD in the '
                         'environment, since argv is world-readable via ps')
    ap.add_argument('--setup', action='store_true', help='create entities and exit')
    ap.add_argument('--teardown', action='store_true', help='delete entities and exit')
    ap.add_argument('--kinds', default=','.join(KINDS),
                    help='comma separated subset of: ' + ','.join(KINDS))
    args = ap.parse_args()

    password = args.password or os.environ.get('LOADGEN_PASSWORD')
    if not password:
        print('need --password or LOADGEN_PASSWORD', file=sys.stderr)
        return 2

    token = get_token(args.namespace, args.user, args.client_id, password)

    if args.setup:
        batch = []
        for i in range(args.entities):
            batch += support(i)
            batch.append(cutter(i))
        code, body = upsert(token, batch)
        print(f'setup {args.entities} cutters (+{len(batch) - args.entities} support) -> {code}')
        if code >= 400:
            print(body[:400].decode(errors='replace'))
            return 1
        return 0

    if args.teardown:
        removed = 0
        for i in range(args.entities):
            for eid in (f'urn:loadcutter:{i}', f'urn:loadfilter:{i}',
                        f'urn:loadfilter:alt{i}', f'urn:loadworkpiece:{i}',
                        f'urn:loadworkpiece:alt{i}'):
                code, _ = _req(f'{NGSILD}/entities/{eid}', 'DELETE', token)
                removed += 1 if code < 400 else 0
        print(f'teardown: deleted {removed} entities')
        return 0

    kinds = [k.strip() for k in args.kinds.split(',') if k.strip()]
    interval = 1.0 / args.rate
    started = time.monotonic()
    tick = 0
    sent = 0
    failed = 0
    last_token = started

    print(f'load: {args.entities} entities, {args.rate}/s, {args.duration}s, kinds={kinds}')
    while time.monotonic() - started < args.duration:
        index = tick % args.entities
        kind = kinds[tick % len(kinds)]
        code, body = upsert(token, [mutated_entity(kind, index, tick)])
        if code >= 400 or code == 0:
            failed += 1
            if failed <= 3:
                print(f'  {kind} -> {code}: {body[:200].decode(errors="replace")}')
        else:
            sent += 1
        tick += 1
        # tokens are short lived; refresh well before expiry
        if time.monotonic() - last_token > 240:
            token = get_token(args.namespace, args.user, args.client_id, password)
            last_token = time.monotonic()
        target = started + tick * interval
        delay = target - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    elapsed = time.monotonic() - started
    print(f'done: sent={sent} failed={failed} in {elapsed:.1f}s '
          f'({sent / elapsed:.2f}/s effective)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
