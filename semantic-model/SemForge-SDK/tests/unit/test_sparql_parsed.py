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

"""A query text is parsed once per process; the answers do not change."""

import pyshacl
from rdflib import Graph, Namespace, URIRef
from rdflib.plugins.sparql import parser

import semforge  # noqa: F401  -- installs the processor
from semforge.sparql import parsed

EX = Namespace('http://example.org/')
QUERY = 'PREFIX ex: <http://example.org/>\nSELECT ?o WHERE { $this ex:p ?o }'


def _graph():
    g = Graph()
    for i in range(5):
        g.add((EX[f's{i}'], EX.p, EX[f'o{i}']))
    return g


def _counting(monkeypatch):
    calls = []
    real = parser.parseQuery

    def counted(text):
        calls.append(text)
        return real(text)
    monkeypatch.setattr(parsed, 'parseQuery', counted)
    parsed._translated.cache_clear()
    return calls


def test_installed_on_import():
    from rdflib import plugin
    from rdflib.query import Processor
    assert plugin.get('sparql', Processor) is parsed.CachingSPARQLProcessor


def test_one_parse_per_text(monkeypatch):
    calls = _counting(monkeypatch)
    g = _graph()
    answers = [[str(r.o) for r in g.query(QUERY, initBindings={'this': EX[f's{i}']})]
               for i in range(5)]
    assert answers == [[str(EX[f'o{i}'])] for i in range(5)]
    assert len(calls) == 1
    g.query(QUERY.replace('?o', '?x'))
    assert len(calls) == 2


def test_same_answers_as_rdflib():
    g = _graph()
    mine = sorted(map(str, (r.o for r in g.query(QUERY, initBindings={'this': EX.s3}))))
    parsed.uninstall()
    try:
        theirs = sorted(map(str, (r.o for r in g.query(QUERY, initBindings={'this': EX.s3}))))
    finally:
        parsed.install()
    assert mine == theirs == [str(EX.o3)]


def test_base_and_namespaces_are_part_of_the_key():
    g = _graph()
    relative = 'SELECT ?o WHERE { <s1> <p> ?o }'
    assert list(g.query(relative, base='http://example.org/')) == [(EX.o1,)]
    assert list(g.query(relative, base='http://other.org/')) == []
    prefixed = 'SELECT ?o WHERE { x:s2 x:p ?o }'
    assert list(g.query(prefixed, initNs={'x': EX})) == [(EX.o2,)]
    assert list(g.query(prefixed, initNs={'x': URIRef('http://other.org/')})) == []


def test_pyshacl_parses_a_constraint_once(monkeypatch):
    calls = _counting(monkeypatch)
    shapes = Graph().parse(data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://example.org/> .
        ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:p ;
            sh:sparql [ sh:select "SELECT $this WHERE { $this <http://example.org/p> ?o }" ] .
    """, format='turtle')
    conforms, _, _ = pyshacl.validate(_graph(), shacl_graph=shapes)
    assert not conforms
    assert sum('$this <http://example.org/p>' in c for c in calls) == 1


def test_semforge_imports_without_rdflib():
    """The extension asks an interpreter whether it has SemForge by importing
    it; an interpreter without rdflib must still say yes (and caches nothing)."""
    import os
    import subprocess
    import sys

    sdk = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run([sys.executable, '-S', '-c',
                           'import sys; sys.modules["rdflib"] = None; import semforge; print(semforge._parsed)'],
                          capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=sdk), cwd=sdk)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == 'None'
