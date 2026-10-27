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

"""Parsed Turtle, kept: the same graph as a parse, in half the time.

On the OPC UA pump package a warm load takes 3 s instead of 7.4 s, and the
cache is 7.3 MB for 12.8 MB of Turtle. Nothing about the result may differ
from rdflib's own parse: triples, blank node structure, prefixes.
"""

import json
import os
import shutil

import pytest
from rdflib import BNode, Graph
from rdflib.compare import isomorphic

from semforge.package import graphcache
from semforge.package.graphcache import graphs_dir, parse_turtle

TURTLE = '''@prefix ex: <https://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:S a sh:NodeShape ;
    sh:targetClass ex:C ;
    sh:property [ sh:path ( ex:a ex:b ) ; sh:minCount 1 ;
                  sh:in ( "x"@en 2 3.5 "2024-01-01T00:00:00Z"^^xsd:dateTime ) ] .
'''


@pytest.fixture
def ttl(tmp_path):
    path = tmp_path / 'pkg' / 'shapes.ttl'
    path.parent.mkdir()
    path.write_text(TURTLE)
    return path


def _cached(path):
    root = str(path.parent)
    return parse_turtle(Graph(), str(path), root), root


def test_a_miss_and_a_hit_give_what_a_parse_gives(ttl):
    parsed = Graph().parse(str(ttl), format='turtle')
    miss, root = _cached(ttl)
    hit, _ = _cached(ttl)
    assert isomorphic(parsed, miss) and isomorphic(parsed, hit)
    assert dict(parsed.namespaces()) == dict(miss.namespaces()) == dict(hit.namespaces())
    assert len(os.listdir(graphs_dir(root))) == 2          # the entry and its .gitignore


def test_the_corpus_comes_back_the_same(corpus_path, tmp_path):
    for name in ('knowledge.ttl', 'shacl.ttl'):
        path = os.path.join(corpus_path, name)
        parsed = Graph().parse(path, format='turtle')
        first = parse_turtle(Graph(), path, str(tmp_path))
        again = parse_turtle(Graph(), path, str(tmp_path))
        assert isomorphic(parsed, first) and isomorphic(parsed, again)
        assert dict(parsed.namespaces()) == dict(again.namespaces())


def test_a_hit_does_not_parse(ttl, monkeypatch):
    _cached(ttl)

    def no_parse(*args, **kwargs):
        raise AssertionError('parsed although cached')

    monkeypatch.setattr(Graph, 'parse', no_parse)
    graph, _ = _cached(ttl)
    assert len(graph) > 5


def test_blank_nodes_are_fresh_on_every_load(ttl):
    _cached(ttl)
    first, _ = _cached(ttl)
    second, _ = _cached(ttl)
    blanks = {t for g in (first,) for triple in g for t in triple if isinstance(t, BNode)}
    others = {t for triple in second for t in triple if isinstance(t, BNode)}
    assert blanks and not blanks & others


def test_an_edit_misses_and_replaces_the_old_entry(ttl):
    _, root = _cached(ttl)
    ttl.write_text(TURTLE.replace('sh:minCount 1', 'sh:minCount 2'))
    graph, _ = _cached(ttl)
    assert any(str(o) == '2' for o in graph.objects(None, None) if not isinstance(o, BNode))
    entries = [n for n in os.listdir(graphs_dir(root)) if n.endswith('.json')]
    assert len(entries) == 1, 'one version per file'


def test_a_torn_or_foreign_entry_is_parsed_again(ttl):
    parsed = Graph().parse(str(ttl), format='turtle')
    _, root = _cached(ttl)
    entry = next(os.path.join(graphs_dir(root), n) for n in os.listdir(graphs_dir(root))
                 if n.endswith('.json'))
    with open(entry, 'w') as handle:
        handle.write('{"format": 2, "rdflib"')
    assert isomorphic(parsed, _cached(ttl)[0])
    with open(entry) as handle:
        stored = json.load(handle)
    stored['format'] = graphcache.FORMAT + 1
    with open(entry, 'w') as handle:
        json.dump(stored, handle)
    assert isomorphic(parsed, _cached(ttl)[0])


def test_the_cache_is_never_committed(ttl):
    _, root = _cached(ttl)
    assert '*' in open(os.path.join(graphs_dir(root), '.gitignore')).read().split()


def test_a_read_only_package_still_loads(ttl):
    os.chmod(ttl.parent, 0o555)
    try:
        graph, root = _cached(ttl)
        assert len(graph) > 5 and not os.path.exists(graphs_dir(root))
    finally:
        os.chmod(ttl.parent, 0o755)


def test_bad_turtle_fails_as_a_parse_does(ttl):
    ttl.write_text('ex:S a .')
    with pytest.raises(Exception):
        _cached(ttl)


def test_a_loaded_package_is_the_same_cold_and_warm(corpus_path, tmp_path):
    from semforge.package import load

    copy = tmp_path / 'pkg'
    shutil.copytree(corpus_path, copy, ignore=shutil.ignore_patterns('.semforge'))
    cold = load(str(copy))
    assert os.listdir(graphs_dir(str(copy)))
    warm = load(str(copy))
    assert isomorphic(cold.knowledge, warm.knowledge)
    assert isomorphic(cold.shapes, warm.shapes)
    assert dict(cold.shapes.namespaces()) == dict(warm.shapes.namespaces())


def test_delete_cache_removes_it(ttl):
    from semforge.editor.cache import clear

    _, root = _cached(ttl)
    assert clear(root) > 0 and not os.path.exists(graphs_dir(root))
