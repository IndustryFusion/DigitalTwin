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
"""
SPARQL_ENGINE=ladder and the classic method must find the same: every model of
the sql-tests with SPARQL queries runs through both, in one database.
"""
import importlib
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import rdflib

from lib import shacl_construct_to_sql, shacl_sparql_to_sql, sparql_ladder, sparql_ladder_sql

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / 'tests' / 'sql-tests'
CASES = ['kms-constraints/test2', 'kms-constraints/test5', 'kms-constraints/test8', 'kms-constraints/kms',
         'kms-rules/test3', 'kms-rules/test4', 'kms-rules/test7']


def run(tool, *args, cwd):
    subprocess.run([sys.executable, str(ROOT / tool), *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, 'PYTHONPATH': str(ROOT)})


def prefixes_of(context):
    graph = rdflib.Graph()
    graph.parse(context, format='json-ld')
    return {prefix: rdflib.Namespace(ns) for prefix, ns in graph.namespaces()}


def results(scripts, sql, prepare=None):
    connection = sqlite3.connect(':memory:')
    # SPARQL REGEX in the classic SQL, as the other SQLite tests register it
    connection.create_function('REGEXP', 2, lambda pattern, text: text is not None and
                               re.search(pattern, str(text)) is not None)
    if prepare:
        prepare(connection)
    for script in scripts:
        connection.executescript(script)
    connection.executescript(sql)
    alerts = connection.execute('SELECT resource, event, severity, `text` FROM alerts_bulk_view').fetchall()
    written = connection.execute('SELECT id, entityId, name, nodeType, `type`, attributeValue, datasetId '
                                 'FROM attributes_insert_filter').fetchall()
    return sorted(alerts), sorted(set(written))


@pytest.mark.parametrize('case', CASES)
def test_same_results(case, tmp_path):
    folder = FIXTURES / case
    for item in folder.iterdir():
        if item.name != 'output':
            (tmp_path / item.name).symlink_to(item.resolve())
    shacl, knowledgefile = str(folder / 'shacl.ttl'), str(folder / 'knowledge.ttl')
    prefixes = prefixes_of(str(folder / 'context.jsonld'))
    knowledge = rdflib.Graph()
    knowledge.parse(knowledgefile)
    run('create_rdf_table.py', 'knowledge.ttl', cwd=tmp_path)
    run('create_core_tables.py', cwd=tmp_path)
    run('create_ngsild_tables.py', cwd=tmp_path)
    # Reloaded: the unit tests of these modules replace functions in them and leave them replaced.
    classic = importlib.reload(shacl_sparql_to_sql).translate(shacl, knowledgefile, prefixes)[0] + \
        importlib.reload(shacl_construct_to_sql).translate(shacl, knowledge)[0]
    ladder = sparql_ladder_sql.translate(shacl, knowledgefile, knowledge, prefixes)[0]

    models = sorted(folder.glob('model*.jsonld'))
    assert models
    for model in models:
        prepared = folder / (model.name + '_model')
        if not prepared.exists():
            run('create_ngsild_models.py', 'shacl.ttl', 'knowledge.ttl', model.name, cwd=tmp_path)
            prepared = tmp_path / 'output' / 'ngsild-models.sqlite'
        scripts = [(tmp_path / 'output' / f'{name}.sqlite').read_text() for name in ('rdf', 'core', 'ngsild')]
        # one time for both: a model without observedAt is stamped when it is loaded
        scripts.append(prepared.read_text().replace('CURRENT_TIMESTAMP', "'2026-01-02 03:04:05'"))
        expected = results(scripts, classic)
        assert results(scripts, ladder, sparql_ladder.register_sqlite) == expected, model.name
