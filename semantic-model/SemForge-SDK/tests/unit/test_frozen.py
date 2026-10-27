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

"""Loaded graphs are frozen; what is derived from one is kept with it."""

import pytest
from rdflib import Graph, Literal, URIRef

from semforge.rdfio.frozen import FrozenGraphError, derived, freeze, is_frozen

EX = 'https://example.org/'


def _graph(*names):
    graph = Graph()
    for name in names:
        graph.add((URIRef(EX + name), URIRef(EX + 'p'), Literal(1)))
    return graph


def _counter():
    calls = []

    def compute():
        calls.append(1)
        return len(calls)
    return compute


def test_kept_while_the_graphs_and_the_key_are_the_same():
    knowledge, shapes = freeze(_graph('a')), freeze(_graph('s'))
    compute = _counter()
    assert derived(knowledge, 'x', compute, depends=(shapes,)) == 1
    assert derived(knowledge, 'x', compute, depends=(shapes,)) == 1
    # Another shapes graph, even an equal one, is another version.
    assert derived(knowledge, 'x', compute, depends=(freeze(_graph('s')),)) == 2
    assert derived(knowledge, 'x', compute, depends=(shapes,), key=('other',)) == 3
    # Another name is another value.
    assert derived(knowledge, 'y', compute, depends=(shapes,)) == 4


def test_keep_holds_that_many_most_recent_last():
    graph = freeze(_graph('a'))
    compute = _counter()
    for key in ('one', 'two', 'one', 'three'):
        derived(graph, 'x', compute, key=(key,), keep=2)
    assert derived(graph, 'x', compute, key=('one',), keep=2) == 1, 'used again: kept'
    assert derived(graph, 'x', compute, key=('two',), keep=2) == 4, 'the oldest went'


def test_a_graph_that_may_still_change_keeps_nothing():
    graph, frozen = _graph('a'), freeze(_graph('b'))
    compute = _counter()
    assert derived(graph, 'x', compute) == 1 and derived(graph, 'x', compute) == 2
    assert derived(frozen, 'x', compute, depends=(graph,)) == 3
    assert derived(frozen, 'x', compute, depends=(graph,)) == 4
    assert not is_frozen(graph)


def test_a_frozen_graph_refuses_every_write():
    graph = freeze(_graph('a'))
    triple = (URIRef(EX + 'b'), URIRef(EX + 'p'), Literal(2))
    for write in (lambda: graph.add(triple), lambda: graph.remove(triple),
                  lambda: graph.set(triple), lambda: graph.addN([triple + (graph,)]),
                  lambda: graph.parse(data='<a:x> <a:y> <a:z> .', format='turtle')):
        with pytest.raises(FrozenGraphError):
            write()
    with pytest.raises(FrozenGraphError):
        graph += _graph('c')
    assert len(graph) == 1
    # Reading, copying and binding a prefix are all still fine.
    graph.bind('ex', EX)
    assert len(graph | _graph('c')) == 2


def test_a_loaded_package_is_frozen(corpus):
    for role in ('knowledge', 'shapes', 'model', 'vocabulary'):
        assert is_frozen(getattr(corpus, role)), role


def test_a_case_edit_does_not_recompute_the_declared_attributes(tmp_path, corpus):
    """The editor's analysis after a case edit reuses what the knowledge says."""
    import shutil

    from semforge.cooked import choices
    from semforge.package import load

    root = tmp_path / 'pkg'
    shutil.copytree(corpus.path, root, ignore=shutil.ignore_patterns('.semforge'))
    first = load(str(root))
    terms = choices.attribute_terms(first)
    again = load(str(root), reuse={role: (first.files(role), getattr(first, role))
                                   for role in ('knowledge', 'shapes')})
    computed = []
    real = choices._attribute_terms
    choices._attribute_terms = lambda package: computed.append(1) or real(package)
    try:
        assert choices.attribute_terms(again) == terms
    finally:
        choices._attribute_terms = real
    assert computed == []
