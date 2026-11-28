#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
Every query of tests/test_sparql_semantics.py through SPARQL_ENGINE=ladder
(ALPHA): either the ladder refuses it by name, or it answers as SPARQL does
and as the classic method does, the text of every alert included.
"""
import importlib
import json
import os
import re
import sqlite3
import subprocess
import sys

import pytest
import rdflib

import lib.utils as utils
from lib import shacl_construct_to_sql, shacl_sparql_to_sql, sparql_ladder, sparql_ladder_sql
from lib.jsonld_numbers import read_jsonld
import test_sparql_semantics as semantics

TOOLS = semantics.TOOLS
EX = semantics.EX
SH_PREFIXES = {'sh': rdflib.SH, 'rdfs': rdflib.RDFS}

# What the ladder does not compile, and the words it says so with. Anything
# else it refuses fails the test: nothing is refused unnoticed.
LADDER_REFUSED = {
    'a named instance in not exists': 'a FILTER without a triple',
    'a relationship between two known': 'the predicate',
    'any attribute': 'the predicate',
    'any property': 'the predicate',
    'any property, by knowledge': 'the predicate',
    'any property, by name': 'the predicate',
    'any property, by number': 'the predicate',
    'any property, by text': 'the predicate',
    'any property, by value': 'the predicate',
    'any property, name known first': 'the predicate',
    'any property, none of': 'the predicate',
    'any property, one of': 'the predicate',
    'any relationship': 'the predicate',
    'any relationship, on': 'the predicate',
    'any value in concat': 'the predicate',
    'backwards, then on': 'the predicate Path(',
    'cast': 'the function <http://www.w3.org/2001/XMLSchema#double>',
    'cast against a variable': 'the function <http://www.w3.org/2001/XMLSchema#double>',
    'decimal cast': 'the function <http://www.w3.org/2001/XMLSchema#decimal>',
    'exists': 'a FILTER without a triple',
    'exists, in two': 'the expression Builtin_EXISTS',
    'exists, the same attribute': 'the expression Builtin_EXISTS',
    'exists, the same attribute of another': 'the expression Builtin_EXISTS',
    'exists, the same relationship': 'the expression Builtin_EXISTS',
    'inverse path': 'the predicate Path(',
    'not a target that does not exist': 'a FILTER without a triple',
    'not exists': 'a FILTER without a triple',
    'not exists any': 'a FILTER without a triple',
    'not exists, any of the same': 'the predicate',
    'not exists, with an outer value': 'the variable ?v where nothing binds it',
    'one time in two attributes': 'the predicate',
    'optional in optional': 'a FILTER inside OPTIONAL',
    'optional three': 'a FILTER inside OPTIONAL',
    'optional with a filter': 'a FILTER inside OPTIONAL',
    'path': 'the predicate Path(',
    'path in the knowledge': 'the predicate Path(',
    'the same attribute of another': 'the predicate',
    'three steps': 'the predicate Path(',
    'two attributes, one value': 'the predicate',
}


@pytest.fixture(scope='module')
def platform(tmp_path_factory):
    """(folder, graph the queries are written against, database with the data)."""
    root = tmp_path_factory.mktemp('ladder-platform')
    (root / 'knowledge.ttl').write_text(semantics.KNOWLEDGE)
    (root / 'shacl.ttl').write_text(semantics.SHAPES)
    (root / 'model.jsonld').write_text(json.dumps([dict(entity, **semantics.CONTEXT) for entity in semantics.MODEL]))
    (root / 'output').mkdir()
    for script, args in (('create_rdf_table.py', ['knowledge.ttl']), ('create_core_tables.py', []),
                         ('create_ngsild_tables.py', []),
                         ('create_ngsild_models.py', ['shacl.ttl', 'knowledge.ttl', 'model.jsonld'])):
        subprocess.run([sys.executable, os.path.join(TOOLS, script)] + args, cwd=root, check=True,
                       env=dict(os.environ, PYTHONPATH=TOOLS), capture_output=True)
    database = sqlite3.connect(':memory:')
    for name in ('rdf', 'core', 'ngsild', 'ngsild-models'):
        database.executescript((root / 'output' / f'{name}.sqlite').read_text())
    written = rdflib.Graph()
    text, base = read_jsonld(str(root / 'model.jsonld'))
    written.parse(data=text, format='json-ld', publicID=base)
    written.parse(data=semantics.KNOWLEDGE, format='turtle')
    return root, written, database


def shape_file(platform, name, kind, query):
    message = '{?text}' if '?text' in query.split('WHERE')[0] else 'found'
    body = f'sh:message "{message}" ; sh:select' if kind == 'sparql' else 'a sh:SPARQLRule ; sh:construct'
    folder = platform[0] / re.sub(r'\W+', '-', f'{kind}-{name}')
    folder.mkdir(exist_ok=True)
    escaped = query.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
    (folder / 'shacl.ttl').write_text(
        semantics.SHAPES + f'ex:Checked a sh:NodeShape ; sh:targetClass ex:Machine ; '
        f'sh:{"sparql" if kind == "sparql" else "rule"} [ {body} """{escaped}""" ] .\n')
    return str(folder / 'shacl.ttl'), str(platform[0] / 'knowledge.ttl')


def run(platform, sql, ladder):
    database = sqlite3.connect(':memory:')
    platform[2].backup(database)
    database.create_function('REGEXP', 2, lambda pattern, text: text is not None and
                             re.search(pattern, str(text)) is not None)
    if ladder:
        sparql_ladder.register_sqlite(database)
    database.executescript(sql)
    alerts = database.execute("SELECT resource, severity, `text` FROM alerts_bulk "
                              "WHERE event LIKE '%Checked%'").fetchall()
    written = database.execute(f"SELECT entityId, attributeValue FROM attributes_insert_filter "
                               f"WHERE name = '{EX}summary'").fetchall()
    return sorted(alerts), sorted(set(written))


def both(platform, name, kind, query):
    """(classic, ladder) results, or (classic, the refusal) when the ladder refuses."""
    shacl, knowledgefile = shape_file(platform, name, kind, query)
    knowledge = rdflib.Graph().parse(knowledgefile)
    classic = importlib.reload(shacl_sparql_to_sql).translate(shacl, knowledgefile, SH_PREFIXES)[0] + \
        importlib.reload(shacl_construct_to_sql).translate(shacl, knowledge)[0]
    try:
        ladder = sparql_ladder_sql.translate(shacl, knowledgefile, knowledge, SH_PREFIXES)[0]
    except utils.UnsupportedShape as refusal:
        return run(platform, classic, False), refusal
    return run(platform, classic, False), run(platform, ladder, True)


def check(platform, name, kind, query):
    classic, ladder = both(platform, name, kind, query)
    if isinstance(ladder, Exception):
        assert name in LADDER_REFUSED, f'refused unexpectedly: {ladder}'
        assert LADDER_REFUSED[name] in str(ladder) and 'SPARQL_ENGINE=classic' in str(ladder)
        return classic, None
    assert name not in LADDER_REFUSED, 'compiled now: take it off the list'
    assert ladder == classic
    return classic, ladder


def select(where, text=True):
    return f'{semantics.PREFIXES}SELECT $this {"?text " if text else ""}WHERE {{ {where} }}'


@pytest.mark.parametrize('name', sorted(semantics.SAME))
def test_a_query_answers_as_sparql_and_as_classic(platform, name):
    where = semantics.SAME[name]
    (alerts, _), ladder = check(platform, name, 'sparql', select(where, text=False))
    if ladder is not None:
        violating = sorted({resource for resource, severity, _ in alerts if severity != 'ok'})
        assert violating == semantics.in_sparql(platform[1], where)


@pytest.mark.parametrize('name', sorted(semantics.TEXTS))
def test_a_text_is_the_text_of_classic(platform, name):
    (alerts, _), ladder = check(platform, name, 'sparql', select(semantics.TEXTS[name]))
    assert any(severity != 'ok' for _, severity, _ in alerts), 'a query nothing answers proves nothing'


@pytest.mark.parametrize('name', sorted(semantics.RULES))
def test_a_rule_writes_the_text_of_classic(platform, name):
    query = f'{semantics.PREFIXES}CONSTRUCT {{ $this ex:summary [ ngsild:hasValue ?text ] }} ' \
            f'WHERE {{ {semantics.RULES[name]} }}'
    (_, written), _ = check(platform, name, 'construct', query)
    assert written


def test_a_pattern_may_start_with_optional(platform):
    """Optional limits first, as a check of a value against them may be written: the
    target is read from its type."""
    where = ('OPTIONAL { $this ex:bound [ ngsild:hasValue ?max ] } '
             'OPTIONAL { $this ex:limit [ ngsild:hasValue ?min ] } '
             '$this ex:speed [ ngsild:hasValue ?v ] . '
             'FILTER((bound(?max) && ?v > ?max) || (bound(?min) && ?v < ?min)) '
             'BIND(CONCAT("violation: ", STR(?v), IF(BOUND(?min) && ?v < ?min, '
             'CONCAT(" < ", STR(?min)), CONCAT(" > ", STR(?max)))) AS ?text)')
    (alerts, _), ladder = check(platform, 'leading optional', 'sparql', select(where))
    assert ladder is not None
    violating = sorted({resource for resource, severity, _ in alerts if severity != 'ok'})
    assert violating == semantics.in_sparql(platform[1], where)
    assert violating


@pytest.mark.parametrize('op, holds', [('=', False), ('!=', True), ('<', False)])
def test_a_text_and_a_number_are_never_equal_and_not_ordered(platform, op, holds):
    """Scenario "A text and a number": = does not hold, != does, < is an error."""
    where = f'$this ex:limit [ ngsild:hasValue ?l ] . FILTER(STR(?l) {op} 10)'
    (alerts, _), ladder = check(platform, f'text {op} number', 'sparql', select(where, text=False))
    assert ladder is not None
    with_limit = sorted(entity for entity in semantics.MACHINES
                        if platform[1].query(f'{semantics.PREFIXES}ASK {{ <{entity}> ex:limit [] }}').askAnswer)
    violating = sorted({resource for resource, severity, _ in alerts if severity != 'ok'})
    assert with_limit
    assert violating == (with_limit if holds else [])
