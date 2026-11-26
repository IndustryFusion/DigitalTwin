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

"""What holds for every copy and every paste, over small random packages.

Two model files, cases with includes and links, ids defined twice, spelled in
every way (with a prefix only the package names, too), relationships declared
and not; now and then an entity written in a
relationship, or @graph, which are refused: each package is made from its
seed, so a failure is there again.
"""

import json
import os
import random
import subprocess
import sys

import pytest
from rdflib import Graph, URIRef
from rdflib.compare import isomorphic

from semforge.cooked.examples import _Ids, copy_entities, paste_entities
from semforge.cooked.hierarchy import Hierarchy
from semforge.errors import PackageError
from semforge.package import load
from semforge.rdfio.relative import BASE, for_rdflib

EX, NGSI = 'https://example.com/', 'https://uri.etsi.org/ngsi-ld/'
CONTEXT = {'ex': EX, 'ngsi-ld': NGSI, 'id': '@id', 'type': '@type', 'value': 'ngsi-ld:hasValue',
           'object': {'@id': 'ngsi-ld:hasObject', '@type': '@id'}, 'Relationship': 'ngsi-ld:Relationship',
           'Property': 'ngsi-ld:Property'}
SHAPES = """@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <https://example.com/> .
@prefix base: <https://industryfusion.github.io/contexts/ontology/v0/base/> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ;
  sh:property [ sh:path ex:child ; base:hasReferenceType <http://opcfoundation.org/UA/HasComponent> ] ;
  sh:property [ sh:path ex:ref ; base:hasReferenceType <http://opcfoundation.org/UA/Organizes> ] .
"""
KNOWLEDGE = """@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix ex: <https://example.com/> .
ex:T a owl:Class . ex:U a owl:Class .
"""
CASES = {'c1.jsonld': ['sub/i1.jsonld'], 'c2.jsonld': ['sub/i1.jsonld', './sub/i2.jsonld'], 'c3.jsonld': []}


def _spelled(rng, n):
    if n >= 5:
        return rng.choice([f'r{n}', f'./r{n}', f'a/../r{n}', BASE + f'r{n}'])
    return rng.choice([f'{EX}e{n}', f'ex:e{n}', f'pk:e{n}'])       # pk: of kms.yaml, no context's


def _entity(rng, context, n, deep=0):
    out = {'id': _spelled(rng, n), 'type': rng.choice(['ex:T', 'ex:U'])}
    if context is not None:
        out['@context'] = context
    for name in ('child', 'ref', 'free', 'free2'):
        if rng.random() < .35:
            made = []
            for _ in range(rng.choice([1, 1, 2])):
                other = rng.randrange(8)
                inner = deep < 1 and rng.random() < .01
                made.append({'type': 'Relationship',
                             'object': _entity(rng, None, other, deep + 1) if inner else _spelled(rng, other)})
            out[f'ex:{name}'] = made if len(made) > 1 else made[0]
    out['ex:v'] = {'type': 'Property', 'value': rng.choice([1, 1.5, True, 'x'])}
    return out


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as handle:
        json.dump(data, handle, indent=1)


def make(root, seed):
    rng = random.Random(seed)
    os.makedirs(root)
    for name, text in (('shacl.ttl', SHAPES), ('knowledge.ttl', KNOWLEDGE)):
        with open(os.path.join(root, name), 'w') as handle:
            handle.write(text)
    _write(os.path.join(root, 'context.jsonld'), {'@context': CONTEXT})
    with open(os.path.join(root, 'kms.yaml'), 'w') as handle:
        handle.write(f'namespaces:\n  pk: {EX}\n')
    files = {'model-instance/a.jsonld': 5, 'model-instance/b.jsonld': 3, 'examples/sub/i1.jsonld': 1,
             'examples/sub/i2.jsonld': 2, **{f'examples/test_S/good/{c}': 2 for c in CASES}}
    for name, count in files.items():
        relative = os.path.relpath('context.jsonld', os.path.dirname(name))
        docs = [_entity(rng, rng.choice([CONTEXT, relative, [relative]]), rng.randrange(8))
                for _ in range(rng.randrange(count + 1))]
        if docs and 'examples' in name and rng.random() < .04:
            docs = {'@context': CONTEXT, '@graph': docs}
        elif len(docs) == 1 and rng.random() < .5:
            docs = docs[0]
        _write(os.path.join(root, name), docs)
    good = os.path.join(root, 'examples', 'test_S', 'good')
    # A case that is another case's file, by a link, and one that is the model's.
    os.symlink('c1.jsonld', os.path.join(good, 'c4.jsonld'))
    if rng.random() < .2:
        os.remove(os.path.join(good, 'c3.jsonld'))
        os.symlink(os.path.join(root, 'model-instance', 'a.jsonld'), os.path.join(good, 'c3.jsonld'))
    lines = ['examples:']
    for name, include in dict(CASES, **{'c4.jsonld': ['sub/i2.jsonld']}).items():
        lines += [f'  - path: {name}', '    expect: valid'] + (['    include:'] if include else [])
        lines += [f'      - {i}' for i in include]
    with open(os.path.join(good, 'expectations.yaml'), 'w') as handle:
        handle.write('\n'.join(lines) + '\n')
    return root


def _documents(path):
    with open(path) as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else [data]


def _rows(root):
    """Every (id, file) a row of the view could be."""
    for folder, _, names in os.walk(root):
        for name in sorted(names):
            if name.endswith('.jsonld') and name != 'context.jsonld':
                path = os.path.join(folder, name)
                for document in _documents(path):
                    if 'id' in document:
                        yield document['id'], path


def _snapshot(root):
    found = {}
    for folder, _, names in os.walk(root):
        for name in names:
            path = os.path.join(folder, name)
            with open(path, 'rb') as handle:
                found[path] = (handle.read(), os.path.islink(path))
    return found


def _triples(graph, documents, path):
    for document in documents:
        graph.parse(data=json.dumps(for_rdflib(document, path)), format='json-ld', base=BASE)


def _copies(root, seed):
    """The same copies, whoever asks: (id, file, what it gave) of each."""
    package, rng = load(root), random.Random(seed)
    rows = sorted(_rows(root))
    for entity, path in rng.sample(rows, min(6, len(rows))):
        for subtree in (False, True):
            try:
                yield entity, path, copy_entities(package, entity, file=path, subtree=subtree)
            except PackageError as exc:
                yield entity, path, str(exc)


def _defined(ids, documents, folder, count):
    for document in documents:
        iri = ids.iri(document, folder)
        count[iri] = count.get(iri, 0) + 1
    return count


@pytest.mark.parametrize('seed', range(60))
def test_copy_and_paste_of_a_random_package(tmp_path, seed):
    root = make(str(tmp_path / 'p'), seed)
    package, ids, rng = load(root), _Ids(load(root)), random.Random(seed)
    examples = os.path.join(root, 'examples')
    good = os.path.join(examples, 'test_S', 'good')
    models = {os.path.join(root, 'model-instance', n) for n in ('a.jsonld', 'b.jsonld')}
    for entity, path, done in list(_copies(root, seed)):
        if isinstance(done, str):
            assert any(w in done for w in ('graph', 'no model file', "relationship's object")), done
            continue
        content = done['content']
        _reachable(package, ids, root, done)
        name = rng.choice(['c1.jsonld', 'c2.jsonld', 'c3.jsonld', 'c4.jsonld'])
        replace, case = rng.random() < .5, os.path.join(good, name)
        include = [os.path.join(examples, i) for i in dict(CASES, **{'c4.jsonld': ['sub/i2.jsonld']})[name]]
        if name in ('c1.jsonld', 'c4.jsonld'):                          # one file: what either includes
            beside = [os.path.join(examples, 'sub', n) for n in ('i1.jsonld', 'i2.jsonld')]
        else:
            beside = include
        before, own = _snapshot(root), _documents(case)
        try:                    # the question, as the editor asks it, and as it would be with Replace
            asked = [paste_entities(package, content, case, replace=r, check=True) for r in (False, True)]
        except PackageError as exc:
            asked = str(exc)
        assert _snapshot(root) == before
        try:
            pasted = paste_entities(package, content, case, replace=replace,
                                    plan=None if isinstance(asked, str) else asked[0]['plan'])
        except PackageError as exc:
            assert _snapshot(root) == before
            assert any(w in str(exc) for w in ('graph', 'main model', "relationship's object")), exc
            assert asked == str(exc), 'refused after the question, not before'
            continue
        assert not isinstance(asked, str), ('refused before the question, not after', asked)
        assert asked[0]['plan'] == asked[1]['plan'] and asked[0]['present'] == asked[1]['present']
        assert pasted['pasted'] == asked[replace]['pasted'], (pasted, asked)
        after = _snapshot(root)
        changed = {p for p in after if after[p] != before.get(p)} | (set(before) - set(after))
        assert changed <= {p for p in before if os.path.realpath(p) == os.path.realpath(case)}, changed
        assert bool(changed) == bool(pasted['pasted']), (changed, pasted)
        assert os.path.realpath(case) not in models or not changed
        # The case's graph is what it was, with what was pasted -- in the place of
        # what it replaced.
        written = set(pasted['pasted'])
        taken = [i for i in content['entities'] if i['document']['id'] in written]
        gone = {ids.iri(i['document'], os.path.normpath(os.path.join(root, i['from']))) for i in taken}
        expected, found = Graph(), Graph()
        for source in include:
            _triples(expected, _documents(source), source)
            _triples(found, _documents(source), source)
        _triples(expected, [d for d in own if ids.iri(d, good) not in gone], case)
        for item in taken:
            _triples(expected, [item['document']], os.path.join(root, item['from'], 'x'))
        _triples(found, _documents(case), case)
        assert isomorphic(found, expected)
        # Nothing has two definitions that had not before, or in the copy.
        had, has, copy = {}, {}, {}
        for source in beside:
            _defined(ids, _documents(source), os.path.dirname(source), had)
            _defined(ids, _documents(source), os.path.dirname(source), has)
        _defined(ids, own, good, had)
        _defined(ids, _documents(case), good, has)
        for item in content['entities']:
            _defined(ids, [item['document']], os.path.normpath(os.path.join(root, item['from'])), copy)
        doubled = {i for i, n in has.items() if n > max(1, had.get(i, 0), copy.get(i, 0))}
        assert not doubled, (doubled, pasted)


def _reachable(package, ids, root, done):
    """Every entity copied is a child of one copied before it."""
    graph, wanted, terms = Graph(), [], {}
    for item in done['content']['entities']:
        folder = os.path.normpath(os.path.join(root, item['from']))
        _triples(graph, [item['document']], os.path.join(folder, 'x'))
        term = ids.term(item['document'], folder)
        wanted.append(ids.canonical(term))
        terms.setdefault(wanted[-1], []).append(URIRef(term))
    hierarchy, seen, pending = Hierarchy(package), set(), [wanted[0]]
    while pending:
        iri = pending.pop()
        if iri not in seen:
            seen.add(iri)
            pending += [ids.canonical(str(t)) for node in terms.get(iri, [])
                        for t, child in hierarchy.relationships(graph, node).items() if child is not False]
    assert set(wanted) <= seen and len(set(wanted)) == len(wanted)


def test_copying_again_gives_the_same(tmp_path):
    """In processes that hash, and so order their sets, otherwise."""
    roots = [make(str(tmp_path / f'p{seed}'), seed) for seed in range(8)]
    script = ('import json, sys; sys.path.insert(0, sys.argv[1]); import test_copy_paste_properties as t; '
              'print(json.dumps([list(t._copies(r, n)) for n, r in enumerate(sys.argv[2:])]))')
    said = set()
    for hashing in ('0', '1', '2', '3'):
        run = subprocess.run([sys.executable, '-c', script, os.path.dirname(__file__)] + roots, text=True,
                             capture_output=True, timeout=120, env=dict(os.environ, PYTHONHASHSEED=hashing))
        assert run.returncode == 0, run.stderr[-1500:]
        said.add(run.stdout)
    assert len(said) == 1 and len(next(iter(said))) > 1000


def test_the_packages_are_refused_now_and_then(tmp_path):
    """The generator is no tame one: some packages have what is refused."""
    said = [done for seed in range(60) for _, _, done in _copies(make(str(tmp_path / f'p{seed}'), seed), seed)]
    refused = [d for d in said if isinstance(d, str)]
    assert any("relationship's object" in d for d in refused) and any('@graph' in d for d in refused)
    assert len(refused) < len(said) / 3
