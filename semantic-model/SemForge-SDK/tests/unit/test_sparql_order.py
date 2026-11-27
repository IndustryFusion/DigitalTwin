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

"""BGPs pick their join order while evaluated: same solutions, no cross product."""

import time

import pytest
from rdflib import BNode, Graph, Literal, Namespace, URIRef

import semforge  # noqa: F401  -- installs the order
from semforge.sparql import order

EX = Namespace('http://example.org/')
NGSI = Namespace('https://uri.etsi.org/ngsi-ld/')

PREFIXES = 'PREFIX ex: <http://example.org/>\nPREFIX ngsi-ld: <https://uri.etsi.org/ngsi-ld/>\n'

# A machine, its building block's two states, and the same again two
# relationships down -- the shape of the query that took minutes.
CHAIN = PREFIXES + """
SELECT $this ?a ?b ?c ?d WHERE {
    $this ex:hasBlock [ngsi-ld:hasObject ?mb].
    ?mb ex:hasItem [ngsi-ld:hasObject ?mi].
    ?mb ex:hasMode [ngsi-ld:hasObject ?mo].
    ?mi ex:state [ngsi-ld:hasValue ?a].
    ?mo ex:state [ngsi-ld:hasValue ?b].
    $this ?r1 [ngsi-ld:hasObject ?s1].
    ?s1 ?r2 [ngsi-ld:hasObject ?s2].
    ?s2 ex:hasBlock [ngsi-ld:hasObject ?sb].
    ?sb ex:hasItem [ngsi-ld:hasObject ?si].
    ?sb ex:hasMode [ngsi-ld:hasObject ?so].
    ?si ex:state [ngsi-ld:hasValue ?c].
    ?so ex:state [ngsi-ld:hasValue ?d].
}
"""


def _rel(g, subject, predicate, target):
    b = BNode()
    g.add((subject, predicate, b))
    g.add((b, NGSI.hasObject, target))


def _prop(g, subject, predicate, value):
    b = BNode()
    g.add((subject, predicate, b))
    g.add((b, NGSI.hasValue, Literal(value)))


def _machine(g, name, subsystems):
    """`name` with a block and states, and `subsystems` x 2 grandchildren alike."""
    def blocked(node):
        block, item, mode = (URIRef(f'{node}/{p}') for p in ('block', 'item', 'mode'))
        _rel(g, node, EX.hasBlock, block)
        _rel(g, block, EX.hasItem, item)
        _rel(g, block, EX.hasMode, mode)
        _prop(g, item, EX.state, 'Executing')
        _prop(g, mode, EX.state, 'Processing')
    root = EX[name]
    blocked(root)
    for i in range(subsystems):
        sub = URIRef(f'{root}/sub{i}')
        _rel(g, root, EX.hasPart, sub)
        for j in range(2):
            grand = URIRef(f'{sub}/part{j}')
            _rel(g, sub, EX.hasPart, grand)
            blocked(grand)
    return root


def _rows(g, query, this):
    return sorted(tuple(map(str, row)) for row in g.query(query, initBindings={'this': this}))


@pytest.fixture
def stock():
    """rdflib's own order for the duration of a block."""
    class _Stock:
        def __enter__(self):
            order.uninstall()

        def __exit__(self, *exc):
            order.install()
    return _Stock()


def test_installed_on_import():
    from rdflib.plugins.sparql import CUSTOM_EVALS
    assert CUSTOM_EVALS.get(order.NAME) is order._custom


def test_same_solutions_as_rdflib(stock):
    g = Graph()
    this = _machine(g, 'm', 1)
    _machine(g, 'other', 1)
    mine = _rows(g, CHAIN, this)
    with stock:
        theirs = _rows(g, CHAIN, this)
    assert mine == theirs
    assert len(mine) == 2                   # one subsystem, two parts with a block


@pytest.mark.parametrize('query', [
    'SELECT ?x WHERE { ?x ?p ?x }',                                     # a variable twice
    'SELECT * WHERE { ?s ex:hasPart ?b . ?b ngsi-ld:hasObject ?o }',    # unbound start
    'SELECT ?s WHERE { ?s ex:hasPart ?b OPTIONAL { ?b ex:none ?z } FILTER(!bound(?z)) }',
    'SELECT * WHERE { }',
])
def test_other_shapes_agree(stock, query):
    g = Graph()
    _machine(g, 'm', 2)
    g.add((EX.loop, EX.self, EX.loop))

    def run():
        return sorted(tuple(map(str, r)) for r in g.query(PREFIXES + query))
    mine = run()
    with stock:
        assert run() == mine


def test_chain_is_not_a_cross_product():
    g = Graph()
    this = _machine(g, 'm', 6)
    for i in range(6):
        _machine(g, f'other{i}', 6)
    started = time.perf_counter()
    rows = _rows(g, CHAIN, this)
    assert len(rows) == 12
    assert time.perf_counter() - started < 2    # rdflib's fixed order: far beyond a minute


def test_semforge_imports_without_rdflib():
    """The extension asks an interpreter whether it has SemForge by importing
    it; an interpreter without rdflib must still say yes (and orders nothing)."""
    import os
    import subprocess
    import sys

    sdk = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run([sys.executable, '-S', '-c',
                           'import sys; sys.modules["rdflib"] = None; import semforge; print(semforge._order)'],
                          capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=sdk), cwd=sdk)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == 'None'
