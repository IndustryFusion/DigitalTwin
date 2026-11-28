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
import json
import re
import sqlite3
from pathlib import Path

import pytest
import rdflib

import create_sql_checks_from_shacl
from lib import sparql_ladder as ladder
from lib import sparql_ladder_sql as ladder_sql

HERE = Path(__file__).resolve().parent
VECTORS = HERE / 'sparql-ladder-vectors.json'
JAVA_VECTORS = HERE.parents[2] / 'FlinkSqlGateway' / 'sparql-udf' / 'test' / 'sparql-ladder-vectors.json'
EX = 'https://example.com/'
PREFIXES = {'sh': rdflib.Namespace('http://www.w3.org/ns/shacl#'), 'rdfs': rdflib.RDFS}
HEAD = f'PREFIX ex: <{EX}>\nPREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>\n' \
       'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n'
TURTLE = HEAD.replace('PREFIX', '@prefix').replace('>\n', '> .\n') + '@prefix sh: <http://www.w3.org/ns/shacl#> .\n'
KNOWLEDGE = TURTLE + """
ex:Machine rdfs:subClassOf ex:Machine . ex:Press rdfs:subClassOf ex:Machine , ex:Press .
ex:Part rdfs:subClassOf ex:Part .
ex:ON ex:validFor ex:Machine . ex:OFF ex:validFor ex:Part . ex:ON ex:level 5 .
"""


@pytest.mark.parametrize('function,args,expected', json.loads(VECTORS.read_text()))
def test_vectors(function, args, expected):
    actual = ladder.SQLITE_FUNCTIONS[function][1](*args)
    if function in ('sparql_route', 'sparql_step') and actual is not None:
        actual = json.loads(actual)
    assert actual == expected


def test_flink_runs_the_same_vectors():
    assert JAVA_VECTORS.read_text() == VECTORS.read_text()


def shape(query, kind='sparql', name='S', cls='Machine'):
    body = 'sh:message "found {?v}" ; sh:select' if kind == 'sparql' else 'sh:construct'
    return f'ex:{name} a sh:NodeShape ; sh:targetClass ex:{cls} ; sh:{kind} [ {body} """{HEAD}{query}""" ] .\n'


def build(tmp_path, *shapes):
    shacl, knowledgefile = tmp_path / 'shacl.ttl', tmp_path / 'knowledge.ttl'
    shacl.write_text(TURTLE + ''.join(shapes))
    knowledgefile.write_text(KNOWLEDGE)
    knowledge = rdflib.Graph().parse(knowledgefile)
    return ladder_sql.translate(str(shacl), str(knowledgefile), knowledge, PREFIXES)


TABLES = """
CREATE TABLE rdf(subject TEXT, predicate TEXT, object TEXT, `index` INTEGER);
CREATE TABLE entities_view(id TEXT, `type` TEXT, `deleted` BOOLEAN);
CREATE TABLE attributes(id TEXT, parentId TEXT, entityId TEXT, name TEXT, nodeType TEXT, `type` TEXT,
  attributeValue TEXT, observedAt TEXT, `deleted` BOOLEAN);
CREATE VIEW attributes_view AS SELECT * FROM attributes;
CREATE TABLE alerts_bulk(resource, event, environment, service, severity, customer, `text`, ts,
  PRIMARY KEY(resource, event));
CREATE TABLE attributes_insert_filter(id, parentId, entityId, name, nodeType, valueType, `type`, attributeValue,
  datasetId, unitCode, lang, `deleted`, synced, ts);
"""


def execute(sql, entities, attributes):
    """attributes: (entity, name, kind V|I|R, value)"""
    db = sqlite3.connect(':memory:')
    ladder.register_sqlite(db)
    db.executescript(TABLES)
    for s, p, o in rdflib.Graph().parse(data=KNOWLEDGE, format='turtle'):
        o = ladder.term(o) if not isinstance(o, rdflib.Literal) else str(o)
        db.execute('INSERT INTO rdf VALUES(?,?,?,0)', (f'<{s}>', f'<{p}>', o))
    for entity, cls, *deleted in entities:
        db.execute('INSERT INTO entities_view VALUES(?,?,?)', (entity, EX + cls, bool(deleted)))
    for entity, name, kind, value in attributes:
        db.execute('INSERT INTO attributes VALUES(?,NULL,?,?,?,?,?,?,0)',
                   (entity + name, entity, EX + name, '@value' if kind == 'V' else '@id',
                    'https://uri.etsi.org/ngsi-ld/' + ('Relationship' if kind == 'R' else 'Property'),
                    value, '2026-01-02 03:04:05'))
    db.executescript(sql)
    return db


def alerts(sql, entities, attributes):
    db = execute(sql, entities, attributes)
    return {(r, re.search(r'\((.*)\)', e)[1]): (s, t) for r, e, s, t in
            db.execute('SELECT resource, event, severity, `text` FROM alerts_bulk')}


STATE = '$this ex:state [ ngsild:hasValue ?v ] .'


def test_constraint(tmp_path):
    sql, (flink, tables, views), rows = build(
        tmp_path, shape(f'SELECT $this ?v WHERE {{ {STATE} FILTER NOT EXISTS {{ ?v ex:validFor ?c . $this a ?t . '
                        '?t rdfs:subClassOf* ?c . } }'))
    found = alerts(sql, [('u:1', 'Press'), ('u:2', 'Press'),
                         ('u:3', 'Machine', True), ('u:4', 'Part'), ('u:5', 'Press')],
                   [('u:1', 'state', 'I', EX + 'ON'), ('u:2', 'state', 'I', EX + 'OFF'),
                    ('u:3', 'state', 'I', EX + 'OFF'), ('u:4', 'state', 'I', EX + 'OFF')])
    assert found == {('u:1', 'S'): ('ok', 'All ok'), ('u:2', 'S'): ('warning', f'found {EX}OFF'),
                     # a deleted entity keeps a row, which closes its alert
                     ('u:3', 'S'): ('ok', 'All ok'), ('u:5', 'S'): ('ok', 'All ok')}
    assert len(flink) == 1 and 'STATE_TTL' in flink[0] and flink[0].startswith('INSERT INTO alerts_bulk')
    assert rows.startswith('INSERT INTO "rdf"') and 'urn:iff:sparql-ladder:pattern:current' in rows
    assert 'entities-view' in views and 'rdf' in tables


def test_numbers_of_the_knowledge_join_with_attribute_values(tmp_path):
    sql = build(tmp_path, shape('SELECT $this ?v WHERE { $this ex:num [ ngsild:hasValue ?v ] . ?x ex:level ?v . }'))[0]
    assert alerts(sql, [('u:1', 'Machine')], [('u:1', 'num', 'V', '5')])[('u:1', 'S')] == ('warning', 'found 5')


def test_optional_bind_and_numeric_filter(tmp_path):
    sql = build(tmp_path, shape(f'SELECT $this ?v WHERE {{ {STATE} OPTIONAL {{ $this ex:num [ ngsild:hasValue ?n ] }} '
                                'BIND(IF(bound(?n), ?n + 1, 0) AS ?m) FILTER(?m >= 0 && (?m < 3 || ?m IN (10))) }'))[0]
    found = alerts(sql, [(f'u:{i}', 'Machine') for i in range(4)],
                   [(f'u:{i}', 'state', 'I', EX + 'ON') for i in range(4)] +
                   [('u:1', 'num', 'V', '1.5'), ('u:2', 'num', 'V', '7'), ('u:3', 'num', 'V', '9')])
    assert [found[(f'u:{i}', 'S')][0] for i in range(4)] == ['warning', 'warning', 'ok', 'warning']


def test_a_relationship_counts_only_when_its_object_exists(tmp_path):
    sql = build(tmp_path, shape('SELECT $this ?v WHERE { $this ex:part [ ngsild:hasObject ?v ] }'))[0]
    found = alerts(sql, [('u:1', 'Machine'), ('u:2', 'Machine'), ('u:p', 'Part')],
                   [('u:1', 'part', 'R', 'u:p'), ('u:2', 'part', 'R', 'u:gone')])
    assert found == {('u:1', 'S'): ('warning', 'found u:p'), ('u:2', 'S'): ('ok', 'All ok')}


def test_a_filter_variable_bound_by_bind_is_part_of_the_not_exists_key(tmp_path):
    sql = build(tmp_path, shape(f'SELECT $this ?v WHERE {{ {STATE} BIND(IF(bound(?v), ?v, ex:OFF) AS ?w) '
                                'FILTER NOT EXISTS { ?w ex:level ?l } }'))[0]
    found = alerts(sql, [('u:1', 'Machine'), ('u:2', 'Machine')],
                   [('u:1', 'state', 'I', EX + 'ON'), ('u:2', 'state', 'I', EX + 'OFF')])
    assert [found[(f'u:{i}', 'S')][0] for i in (1, 2)] == ['ok', 'warning']


def test_construct(tmp_path):
    sql, (flink, tables, _), _ = build(tmp_path, shape(
        'CONSTRUCT { $this ex:copy [ ngsild:hasValue ?v ] } WHERE { $this ex:state [ ngsild:hasValue ?v ] }', 'rule'))
    db = execute(sql, [('u:1', 'Press'), ('u:4', 'Part')],
                 [('u:1', 'state', 'I', EX + 'ON'), ('u:4', 'state', 'I', EX + 'ON')])
    assert db.execute('SELECT entityId, name, nodeType, attributeValue FROM attributes_insert_filter').fetchall() == \
        [('u:1', EX + 'copy', '@id', EX + 'ON')]
    assert flink[0].startswith('INSERT INTO attributes_insert\n') and 'attributes-insert' in tables


def test_aggregate(tmp_path):
    query = 'CONSTRUCT { $this ex:total [ ngsild:hasValue ?t ] } WHERE { $this ex:num [ ngsild:hasValue ?n ] . ' \
            'BIND(SUM(xsd:integer(?n)) * 2 AS ?t) } GROUP BY $this'
    sql, (flink, _, _), _ = build(tmp_path, shape(query, 'rule'))
    db = execute(sql, [('u:1', 'Machine')], [('u:1', 'num', 'V', '3'), ('u:1', 'num', 'V', '4')])
    assert db.execute('SELECT attributeValue FROM attributes_insert_filter').fetchall() == [('14',)]
    # attribute history is unbounded: no join which sees it may be pinned
    assert 'history_o1' in flink[0] and 'STATE_TTL' not in flink[0] and 'FROM attributes WHERE' in flink[0]


def test_the_sql_depends_on_the_highest_tree_only(tmp_path):
    one = build(tmp_path, shape(f'SELECT $this ?v WHERE {{ {STATE} $this ex:num [ ngsild:hasValue 1 ] }}'))[1][0]
    many = build(tmp_path, *[shape(f'SELECT $this ?v WHERE {{ {STATE} $this ex:num [ ngsild:hasValue {i} ] }}',
                                   name=f'S{i}') for i in range(20)])[1][0]
    assert many == one


def test_nothing_to_compile(tmp_path):
    assert build(tmp_path) == ('', ([], [], []), '')


@pytest.mark.parametrize('where,problem', [
    (f'{STATE} FILTER(regex(?v, "x"))', 'Builtin_REGEX'),
    (f'{{ {STATE} }} UNION {{ $this ex:b [ ngsild:hasValue ?v ] }}', 'Union'),
    (f'{STATE} OPTIONAL {{ $this ex:b [ ngsild:hasValue ?w ] FILTER(?w = ?v) }}', 'FILTER inside OPTIONAL'),
    (f'{STATE} FILTER NOT EXISTS {{ $this ex:b [ ngsild:hasValue ?w ] FILTER(?w = ?v) }}', r'\?v where nothing binds'),
    (f'{STATE} FILTER(?nowhere = 1)', r'\?nowhere where nothing binds'),
    ('$this ex:a [ ngsild:hasValue ?v ; ngsild:unitCode ?u ]', 'unitCode'),
    ('$this ex:a [ ngsild:hasJSON ?v ]', 'hasJSON'),
    (f'{STATE} $this ex:a/ex:b ?w', 'predicate'),
    (f'{STATE} ?w ex:a ?w', 'subject and object'),
    (f'{STATE} FILTER(<https://industry-fusion.com/functions/v0.9/hash>(?v) = 1)', 'function'),
    ('', 'no triple'),
])
def test_what_cannot_be_compiled_fails_and_names_the_shape(tmp_path, where, problem):
    with pytest.raises(ladder.UnsupportedQuery, match=problem) as err:
        build(tmp_path, shape(f'SELECT $this ?v WHERE {{ {where} }}'))
    if where:
        assert EX + 'S' in str(err.value) and 'classic' in str(err.value)


@pytest.mark.parametrize('query', [
    'CONSTRUCT { $this ex:a [ ngsild:hasObject ?v ] } WHERE { $this ex:state [ ngsild:hasValue ?v ] }',
    'CONSTRUCT { $this ex:a ?v } WHERE { $this ex:state [ ngsild:hasValue ?v ] }',
    'CONSTRUCT { $this ex:a [ ngsild:hasValue ?v ] } WHERE { $this ex:state [ ngsild:hasValue ?v ] } GROUP BY $this',
])
def test_unsupported_construct(tmp_path, query):
    with pytest.raises(ladder.UnsupportedQuery):
        build(tmp_path, shape(query, 'rule'))


def test_the_default_is_classic():
    args = ['shacl.ttl', 'knowledge.ttl']
    assert create_sql_checks_from_shacl.parse_args(args).sparql_engine == 'classic'
    assert create_sql_checks_from_shacl.parse_args(args + ['--sparql-engine', 'ladder']).sparql_engine == 'ladder'
    with pytest.raises(SystemExit):
        create_sql_checks_from_shacl.parse_args(args + ['--sparql-engine', 'other'])


def test_switch(tmp_path):
    """Only the SPARQL part differs, and a query which cannot be compiled stops the build."""
    folder = HERE / 'sql-tests' / 'kms-constraints' / 'test8'
    inputs = [str(folder / name) for name in ('shacl.ttl', 'knowledge.ttl', 'context.jsonld')]
    output = {}
    for engine in ('classic', 'ladder'):
        out = tmp_path / engine
        create_sql_checks_from_shacl.main(*inputs, 'iff', str(out), sparql_engine=engine)
        output[engine] = {f.name: f.read_text() for f in out.iterdir()}
    for text in output['classic'].values():
        assert 'sparql_' not in text and 'sparql-ladder' not in text
    assert output['ladder']['shacl-validation-maps.yaml'].count('INSERT INTO alerts_bulk\\n') + \
        output['ladder']['shacl-validation-maps.yaml'].count('INSERT INTO alerts_bulk\n') == 1
    assert output['ladder']['shacl-constraints.postgres'].startswith(
        output['classic']['shacl-constraints.postgres'].rstrip())
    bad = tmp_path / 'shacl.ttl'
    bad.write_text(TURTLE + shape(f'SELECT $this ?v WHERE {{ {STATE} FILTER(regex(?v, "x")) }}'))
    with pytest.raises(SystemExit):
        create_sql_checks_from_shacl.main(str(bad), inputs[1], inputs[2], 'iff', str(tmp_path / 'b'),
                                          sparql_engine='ladder')
