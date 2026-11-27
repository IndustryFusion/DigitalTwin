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

"""End to end: `semforge test` on a package whose SPARQL constraint walks a
chain of NGSI-LD relationships. With rdflib's fixed join order the chain is
a cross product and the run takes minutes; picked while evaluated, seconds."""

import json
import os
import re
import shutil
import subprocess
import sys

EX = 'http://example.org/'

CHAIN = """
    SELECT $this ?a ?b ?c ?d WHERE {
        $this <http://example.org/hasBlock> [<https://uri.etsi.org/ngsi-ld/hasObject> ?mb].
        ?mb <http://example.org/hasItem> [<https://uri.etsi.org/ngsi-ld/hasObject> ?mi].
        ?mb <http://example.org/hasMode> [<https://uri.etsi.org/ngsi-ld/hasObject> ?mo].
        ?mi <http://example.org/state> [<https://uri.etsi.org/ngsi-ld/hasValue> ?a].
        ?mo <http://example.org/state> [<https://uri.etsi.org/ngsi-ld/hasValue> ?b].
        $this ?r1 [<https://uri.etsi.org/ngsi-ld/hasObject> ?s1].
        ?s1 ?r2 [<https://uri.etsi.org/ngsi-ld/hasObject> ?s2].
        ?s2 <http://example.org/hasBlock> [<https://uri.etsi.org/ngsi-ld/hasObject> ?sb].
        ?sb <http://example.org/hasItem> [<https://uri.etsi.org/ngsi-ld/hasObject> ?si].
        ?sb <http://example.org/hasMode> [<https://uri.etsi.org/ngsi-ld/hasObject> ?so].
        ?si <http://example.org/state> [<https://uri.etsi.org/ngsi-ld/hasValue> ?c].
        ?so <http://example.org/state> [<https://uri.etsi.org/ngsi-ld/hasValue> ?d].
    }
"""

SHAPE = '''
iffBaseShacl:ChainShape a <http://www.w3.org/ns/shacl#NodeShape> ;
    <http://www.w3.org/ns/shacl#targetClass> <http://example.org/Machine> ;
    <http://www.w3.org/ns/shacl#sparql> [ a <http://www.w3.org/ns/shacl#SPARQLConstraint> ;
        <http://www.w3.org/ns/shacl#message> "chain reached {?d}" ;
        <http://www.w3.org/ns/shacl#select> """%s""" ] .
''' % CHAIN


def _rel(target):
    return {'type': 'Relationship', 'object': target}


def _prop(value):
    return {'type': 'Property', 'value': value}


def _entities():
    """A machine with 6 subsystems of 2 parts each, every one with a block;
    six more machines alike -- the data that makes the fixed order explode."""
    out = []

    def blocked(node):
        block, item, mode = (f'{node}:block', f'{node}:item', f'{node}:mode')
        out.extend([
            {'id': block, 'type': EX + 'Block',
             EX + 'hasItem': _rel(item), EX + 'hasMode': _rel(mode)},
            {'id': item, 'type': EX + 'Item', EX + 'state': _prop('Executing')},
            {'id': mode, 'type': EX + 'Mode', EX + 'state': _prop('Processing')}])
        return _rel(block)

    for name in ['m'] + [f'other{i}' for i in range(6)]:
        root = f'urn:ex:{name}'
        machine = {'id': root, 'type': EX + 'Machine', EX + 'hasBlock': blocked(root)}
        parts = []
        for i in range(6):
            sub = f'{root}:sub{i}'
            grands = []
            for j in range(2):
                grand = f'{sub}:part{j}'
                out.append({'id': grand, 'type': EX + 'Part', EX + 'hasBlock': blocked(grand)})
                grands.append(dict(_rel(grand), datasetId=f'urn:ds:{j}'))
            out.append({'id': sub, 'type': EX + 'Part', EX + 'hasPart': grands})
            parts.append(dict(_rel(sub), datasetId=f'urn:ds:{i}'))
        machine[EX + 'hasPart'] = parts
        out.append(machine)
    context = 'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.6.jsonld'
    return [dict(e, **{'@context': context}) for e in out]


def test_semforge_test_runs_a_relationship_chain_in_seconds(tmp_path, corpus):
    package = tmp_path / 'pkg'
    package.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], package / name)
    for extra in ('context.jsonld', 'kms.yaml'):
        shutil.copy(f'{corpus.path}/{extra}', package / extra)
    shutil.copytree(f'{corpus.path}/vocabulary', package / 'vocabulary')
    with open(package / 'shacl.ttl', 'a', encoding='utf-8') as handle:
        handle.write(SHAPE)
    (package / 'examples').mkdir()
    with open(package / 'examples' / 'chain.jsonld', 'w', encoding='utf-8') as handle:
        json.dump(_entities(), handle)
    with open(package / 'examples' / 'expectations.yaml', 'w', encoding='utf-8') as handle:
        handle.write('examples:\n  - path: chain.jsonld\n    expect: invalid\n    asserts:\n' + ''.join(
            f'      - constraint: iffBaseShacl:ChainShape/SPARQLConstraintComponent\n'
            f'        resource: urn:ex:{name}\n' for name in ['m'] + [f'other{i}' for i in range(6)]))

    env = dict(os.environ, SEMFORGE_HISTORY='off')
    done = subprocess.run([sys.executable, '-m', 'semforge', 'test', str(package)],
                          capture_output=True, text=True, timeout=120, env=env)
    assert re.search(r'^\s*ok\s+chain\.jsonld', done.stdout, re.M), done.stdout[-2000:]
