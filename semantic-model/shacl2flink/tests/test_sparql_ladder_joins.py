#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""The join count of SPARQL_ENGINE=ladder: what the build writes and what a Flink plan holds."""
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import rdflib

import sparql_ladder_joins
from lib import sparql_ladder_sql
import test_e2e_without_shapes as e2e
import test_sparql_ladder as unit

HERE = Path(__file__).resolve().parent
# The Join nodes of a job of tests/e2e-kms on Flink 1.20.4: the ladder's five
# and a dozen of the other validations.
PLAN = json.loads((HERE / 'sparql-ladder-plan.json').read_text())


def test_the_ladder_joins_of_a_real_plan():
    assert len(sparql_ladder_joins.ladder_joins(PLAN)) == 5
    assert len(PLAN['plan']['nodes']) > 5


def test_a_copied_level_is_one_join_more():
    plan = copy.deepcopy(PLAN)
    level = next(node for node in plan['plan']['nodes'] if 'k0' in node['description'])
    plan['plan']['nodes'].append(dict(level, id='copy'))
    assert len(sparql_ladder_joins.ladder_joins(plan)) == 6


def test_the_joins_of_other_validations_do_not_count():
    plan = {'plan': {'nodes': [node for node in PLAN['plan']['nodes']
                               if not sparql_ladder_joins.ladder_joins({'plan': {'nodes': [node]}})]}}
    assert plan['plan']['nodes'] and sparql_ladder_joins.ladder_joins(plan) == []


def test_main_prints_the_number(tmp_path, capsys):
    (tmp_path / 'plan.json').write_text(json.dumps(PLAN))
    sparql_ladder_joins.main(str(tmp_path / 'plan.json'))
    assert capsys.readouterr().out == '5\n'


def test_the_build_counts_the_joins_of_the_e2e_kms(tmp_path):
    e2e.without_shapes.main(str(e2e.KMS), str(tmp_path / 'kms'), [e2e.DROPPED])
    shacl, knowledgefile = str(tmp_path / 'kms' / 'shacl.ttl'), str(tmp_path / 'kms' / 'knowledge.ttl')
    sparql_ladder_sql.translate(shacl, knowledgefile, rdflib.Graph().parse(knowledgefile), unit.PREFIXES)
    assert sparql_ladder_sql.joins == 5


def test_statements_on_one_ladder_count_its_levels_once(tmp_path):
    """A constraint and a rule share the levels of the current ladder: the job holds them once."""
    query = 'SELECT $this ?v WHERE { $this ex:state [ ngsild:hasValue ?v ] . }'
    rule = 'CONSTRUCT { $this ex:copy [ ngsild:hasValue ?v ] } WHERE { $this ex:state [ ngsild:hasValue ?v ] }'
    _, (flink, _, _), _ = unit.build(tmp_path, unit.shape(query), unit.shape(rule, 'rule', name='R'))
    assert len(flink) == 2
    total = sum(sparql_ladder_sql.count_joins(statement) for statement in flink)
    assert 0 < sparql_ladder_sql.joins < total
    _, (flink, _, _), _ = unit.build(tmp_path, unit.shape(query))
    assert sparql_ladder_sql.joins == sparql_ladder_sql.count_joins(flink[0])


def test_the_same_package_builds_the_same_in_every_process(tmp_path):
    """A deploy of an unchanged package keeps the job only if its build is the same (#1165's
    fingerprint): the ladder's rows may not follow the order of a process's hash seed."""
    e2e.without_shapes.main(str(e2e.KMS), str(tmp_path / 'kms'), [e2e.DROPPED])
    root = HERE.parent
    outputs = []
    for seed in ('1', '2', '3', '4'):
        work = tmp_path / f'build-{seed}'
        work.mkdir()
        subprocess.run([sys.executable, str(root / 'create_sql_checks_from_shacl.py'), '--sparql-engine', 'ladder',
                        '-c', str(root.parent / 'kms' / 'example' / 'context.jsonld'),
                        str(tmp_path / 'kms' / 'shacl.ttl'), str(tmp_path / 'kms' / 'knowledge.ttl')],
                       cwd=work, check=True, capture_output=True,
                       env={**os.environ, 'PYTHONHASHSEED': seed, 'PYTHONPATH': str(root)})
        outputs.append({path.name: path.read_bytes() for path in sorted((work / 'output').iterdir())})
    assert outputs[0] and all(output == outputs[0] for output in outputs[1:])
