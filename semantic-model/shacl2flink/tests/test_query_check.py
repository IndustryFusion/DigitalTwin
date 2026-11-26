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

"""A build that cannot compile a SPARQL expression says which one, and why."""

import json
import os
import subprocess
import sys

import pytest
import rdflib

import check_queries
from lib.query_check import check

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHAPES = '''@prefix ex: <https://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
ex:MachineShape a sh:NodeShape ; sh:targetClass ex:Machine ;
    sh:sparql [ sh:message "good one" ; sh:select """
PREFIX ex: <https://example.org/>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
SELECT $this WHERE { $this ?attribute [ ngsild:hasValue ?v ] . FILTER(?v > 5) }
""" ] ;
    sh:sparql [ sh:message "bad one" ; sh:select """
PREFIX ex: <https://example.org/>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
SELECT $this WHERE {
    $this ex:speed [ ngsild:hasValue ?v ] .
    $this ?plain ?thing .
}
""" ] .
ex:PartShape a sh:NodeShape ; sh:targetClass ex:Part ;
    sh:sparql [ sh:message "another" ; sh:select "SELECT $this WHERE { $this " ] ;
    sh:rule [ sh:construct """
PREFIX ex: <https://example.org/>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
CONSTRUCT { $this ex:note [ ngsild:hasValue ?n ] } WHERE { $this ex:speed [ ngsild:unitCode ?n ] }
""" ] .
'''
KNOWLEDGE = '''@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
ex:Machine a owl:Class . ex:Part a owl:Class .
'''
CONTEXT = {'@context': {'ngsi-ld': {'@id': 'https://uri.etsi.org/ngsi-ld/', '@prefix': True},
                        'ex': {'@id': 'https://example.org/', '@prefix': True},
                        'base': {'@id': 'https://example.org/base/', '@prefix': True},
                        'rdfs': {'@id': 'http://www.w3.org/2000/01/rdf-schema#', '@prefix': True},
                        'sh': {'@id': 'http://www.w3.org/ns/shacl#', '@prefix': True}}}


@pytest.fixture
def package(tmp_path):
    (tmp_path / 'shacl.ttl').write_text(SHAPES)
    (tmp_path / 'knowledge.ttl').write_text(KNOWLEDGE)
    (tmp_path / 'context.jsonld').write_text(json.dumps(CONTEXT))
    return str(tmp_path)


def _run(package, script, *args, **more):
    return subprocess.run([sys.executable, os.path.join(TOOLS, script), *args], cwd=package, text=True,
                          capture_output=True, env=dict(os.environ, PYTHONPATH=TOOLS), **more)


def test_the_build_names_every_expression_it_cannot_compile(package):
    done = _run(package, 'create_sql_checks_from_shacl.py', '-c', 'context.jsonld', 'shacl.ttl', 'knowledge.ttl')
    assert done.returncode == 1 and 'Traceback' not in done.stderr, done.stderr
    assert '3 SPARQL expression(s) cannot be compiled' in done.stderr
    for said in ('sh:select of <https://example.org/MachineShape> (shacl.ttl:', 'message : bad one',
                 'target  : <https://example.org/Machine>', 'variable as predicate', 'pattern : ?this ?plain ?thing',
                 '| SELECT $this WHERE {', 'message : another', 'does not parse',
                 'sh:construct of <https://example.org/PartShape>', 'unitCode'):
        assert said in done.stderr, said
    assert 'good one' not in done.stderr
    assert '| PREFIX' not in done.stderr, 'the query, not its prefixes'
    assert not os.path.exists(os.path.join(package, 'output', 'shacl-validation.yaml'))


def test_the_line_is_the_one_of_the_query(package):
    path = os.path.join(package, 'shacl.ttl')
    graph = rdflib.Graph().parse(path)
    problem = next(p for p in check(graph, [path]) if p.message == 'bad one')
    with open(path) as handle:
        assert handle.read().split('\n')[problem.line - 1] == 'PREFIX ex: <https://example.org/>'
    assert problem.line > SHAPES[:SHAPES.index('bad one')].count('\n')
    assert check(graph, ['/nowhere.ttl'])[0].line == 0


def test_an_error_nobody_foresaw_still_names_its_expression(package, monkeypatch):
    def fail(*args):
        raise KeyError('x')
    monkeypatch.setattr('lib.query_check.translate_sparql', fail)
    problems = check(rdflib.Graph().parse(os.path.join(package, 'shacl.ttl')))
    assert len(problems) == 4 and all('defect of shacl2flink' in p.reason for p in problems)


def test_the_check_alone(package, capsys):
    path = os.path.join(package, 'shacl.ttl')
    assert check_queries.main([path]) == 1
    said = capsys.readouterr().out
    assert 'ERROR: 3 SPARQL' in said and '3) ' in said
    assert check_queries.main([path], as_json=True) == 1
    assert {p['message'] for p in json.loads(capsys.readouterr().out)} == {'bad one', 'another', ''}
    draft = {'target': 'https://example.org/Machine', 'query': 'SELECT $this WHERE { $this a <https://example.org/X> }'}
    assert check_queries.main([path], draft=draft) == 0
    assert 'Every SPARQL expression can be compiled' in capsys.readouterr().out
    done = _run(package, 'check_queries.py', '--json', '--draft', 'shacl.ttl',
                input=json.dumps(dict(draft, query='SELECT $this WHERE { $this ?p ?o }')))
    assert done.returncode == 1 and 'variable as predicate' in json.loads(done.stdout)[0]['reason']


@pytest.mark.parametrize('bound, text, kind', [
    ('BIND(IF(?v > 5, "hi", "lo") AS ?n)', 'hi', '@value'),
    ('BIND(?v AS ?n)', '9', '@value'),
    ('BIND(ex:good AS ?n)', 'https://example.org/good', '@id')])
def test_a_rule_writes_a_value_of_unknown_kind_as_what_it_is(bound, text, kind):
    """One shape says ex:note is an IRI, another that it is a literal."""
    import sqlite3

    import lib.utils as utils
    from lib.sparql_to_sql import translate_sparql

    shapes = '''@prefix ex: <https://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
ex:A a sh:NodeShape ; sh:targetClass ex:Machine ; sh:property [ sh:path ex:note ;
    sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:IRI ] ] .
ex:B a sh:NodeShape ; sh:property [ sh:path ex:note ;
    sh:property [ sh:path ngsild:hasValue ; sh:nodeKind sh:Literal ] ] .
'''
    query = f'''PREFIX ex: <https://example.org/> PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
CONSTRUCT {{ $this ex:note [ ngsild:hasValue ?n ] }} WHERE {{ $this ex:speed [ ngsild:hasValue ?v ] . {bound} }}'''
    graph = rdflib.Graph().parse(data=shapes, format='turtle')
    sql, _ = translate_sparql(None, None, query, rdflib.URIRef('https://example.org/Machine'), graph)
    database = sqlite3.connect(':memory:')
    database.create_function('REGEXP', 2, lambda pattern, value: value is not None)
    database.executescript('''create table rdf (subject text, predicate text, object text);
create table entities_view (id text, type text, deleted boolean);
create table attributes_view (id text, parentId text, entityId text, name text, nodeType text, valueType text,
    type text, attributeValue text, deleted boolean, observedAt text);
insert into rdf values ('<https://example.org/Machine>', '<http://www.w3.org/2000/01/rdf-schema#subClassOf>',
    '<https://example.org/Machine>');
insert into entities_view values ('urn:m:1', 'https://example.org/Machine', NULL);
insert into attributes_view values ('a', NULL, 'urn:m:1', 'https://example.org/speed', '@value', NULL,
    'https://uri.etsi.org/ngsi-ld/Property', '9', NULL, NULL);''')
    select = utils.process_sql_dialect(sql, True).replace('INSERT OR REPLACE INTO attributes_insert_filter', '')
    (row,) = database.execute(select).fetchall()
    assert text in row and kind in row
