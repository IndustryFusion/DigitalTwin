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
"""Tests of submitjob/job.py's validation mode (openspec gh-955-flink-sql-validation).

They need Flink, so they run in the SQL Gateway image, without network:

    docker run --rm --network none --entrypoint python3 \\
        -v $PWD/FlinkSqlGateway:/src:ro <flink-sql-gateway image> \\
        -m unittest discover -s /src/test -p 'test_job.py'

The tables point at addresses that cannot be reached: validation must not
need Kafka or a database.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SUBMITJOB = os.path.join(HERE, '..', 'submitjob')
sys.path.insert(0, SUBMITJOB)
import job  # noqa: E402

KAFKA = ("CREATE TABLE `attributes` (`id` STRING, `entityId` STRING, `val` STRING, "
         "`ts` TIMESTAMP(3) METADATA FROM 'timestamp', watermark FOR `ts` AS `ts`) WITH ("
         "'connector' = 'kafka', 'format' = 'json', "
         "'properties.bootstrap.servers' = 'nowhere.invalid:9092', 'topic' = 'iff.attributes', "
         "'scan.startup.mode' = 'earliest-offset');")
UPSERT = ("CREATE TABLE `alerts` (`resource` STRING, `event` STRING, `text` STRING, "
          "PRIMARY KEY (`resource`, `event`) NOT ENFORCED) WITH ("
          "'connector' = 'upsert-kafka', 'key.format' = 'json', 'value.format' = 'json', "
          "'properties.bootstrap.servers' = 'nowhere.invalid:9092', 'topic' = 'iff.alerts');")
CDC = ("CREATE TABLE `entities` (`id` STRING, `type` STRING, PRIMARY KEY (`id`) NOT ENFORCED) WITH ("
       "'connector' = 'postgres-cdc', 'hostname' = 'nowhere.invalid', 'port' = '5432', "
       "'username' = 'u', 'password' = 'p', 'database-name' = 'd', 'schema-name' = 'public', "
       "'table-name' = 'entities', 'slot.name' = 'validate', 'decoding.plugin.name' = 'pgoutput');")
VIEW = "CREATE VIEW `attributes_view` AS SELECT `id`, `entityId`, `val` FROM `attributes`;"
FROM = "FROM `attributes_view` a JOIN `entities` e ON a.`entityId` = e.`id`"
INSERT = f"INSERT INTO `alerts` SELECT a.`entityId`, e.`type`, a.`val` {FROM};"
UDF = '''from pyflink.table import DataTypes
from pyflink.table.udf import ScalarFunction, udf


class Shout(ScalarFunction):
    def eval(self, s):
        return None if s is None else s.upper()


def register(table_env):
    table_env.create_temporary_function("shout", udf(Shout(), result_type=DataTypes.STRING()))
'''


def request(*statements, tables=(KAFKA, UPSERT, CDC), views=(VIEW,)):
    return {'sqlsettings': [{'pipeline.name': 'validate-test'}, {'table.exec.state.ttl': '3600000'}],
            'tables': list(tables), 'views': list(views), 'sqlstatementset': list(statements)}


class TestValidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.udfdir = tempfile.mkdtemp()
        with open(os.path.join(cls.udfdir, 'shout_v1.py'), 'w') as f:
            f.write(UDF)

    def validate(self, d):
        return job.validate(d, self.udfdir)

    def test_a_valid_statement_set(self):
        # Kafka, Upsert-Kafka and Postgres CDC at unreachable addresses.
        self.assertIsNone(self.validate(request(INSERT)))

    def test_a_statement_flink_rejects(self):
        bad = f"INSERT INTO `alerts` SELECT a.`entityId`, e.`type`, a.`val` {FROM} " \
              "WHERE POSITION(',' || a.`val` IN ',x,') > 0;"
        problem = self.validate(request(INSERT, bad))
        self.assertEqual((problem['kind'], problem['index'], problem['text']), ('statement', 1, bad))
        self.assertIn('SQL parse failed', problem['message'])
        self.assertNotIn('An error occurred while calling', problem['message'])

    def test_a_statement_flink_cannot_plan(self):
        for bad in (f"INSERT INTO `alerts` SELECT a.`nosuchcolumn`, e.`type`, a.`val` {FROM};",
                    f"INSERT INTO `alerts` SELECT nosuchfunction(a.`entityId`), e.`type`, a.`val` {FROM};"):
            problem = self.validate(request(bad))
            self.assertEqual((problem['kind'], problem['index']), ('statement', 0))
            self.assertIn('SQL validation failed', problem['message'])

    def test_a_statement_that_fails_only_when_planned(self):
        # Parses and resolves, but its columns do not fit the sink: found by
        # explaining the statement set, then attributed to the statement.
        problem = self.validate(request(INSERT, "INSERT INTO `alerts` SELECT 1, 2;"))
        self.assertEqual((problem['kind'], problem['index']), ('statement', 1))
        self.assertIn('do not match', problem['message'])

    def test_user_defined_functions(self):
        statement = f"INSERT INTO `alerts` SELECT shout(a.`entityId`), e.`type`, a.`val` {FROM};"
        self.assertIsNone(self.validate(request(statement)))

    def test_a_udf_that_cannot_be_registered(self):
        udfdir = tempfile.mkdtemp()
        with open(os.path.join(udfdir, 'broken_v1.py'), 'w') as f:
            f.write('def register(table_env):\n    raise RuntimeError("no")\n')
        problem = job.validate(request(INSERT), udfdir)
        self.assertEqual((problem['kind'], problem['text']), ('udf', 'broken_v1.py'))

    def test_a_table_and_a_view_flink_rejects(self):
        problem = self.validate(request(INSERT, tables=(KAFKA, UPSERT, "CREATE TABLE `entities` (;")))
        self.assertEqual((problem['kind'], problem['index']), ('table', 2))
        problem = self.validate(request(INSERT, views=("CREATE VIEW `attributes_view` AS SELECT nope FROM x;",)))
        self.assertEqual((problem['kind'], problem['index']), ('view', 0))

    def test_the_command_line(self):
        directory = tempfile.mkdtemp()
        good, bad = os.path.join(directory, 'good.json'), os.path.join(directory, 'bad.json')
        with open(good, 'w') as f:
            json.dump(request(INSERT), f)
        with open(bad, 'w') as f:
            json.dump(request("INSERT INTO `alerts` SELECT 1, 2;"), f)
        out = subprocess.run([sys.executable, os.path.join(SUBMITJOB, 'job.py'), '--validate', good, bad,
                              '--udf-dir', self.udfdir], capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)
        results = [json.loads(line[len(job.RESULT_PREFIX):]) for line in out.stdout.splitlines()
                   if line.startswith(job.RESULT_PREFIX)]
        self.assertEqual([(r['file'], r['valid']) for r in results], [(good, True), (bad, False)])


class TestSettings(unittest.TestCase):
    def test_maps_and_the_savepoint_string(self):
        # The operator adds a savepoint path as `SET key = 'value';`.
        d = {'sqlsettings': [{'pipeline.name': 'p'},
                             "SET execution.savepoint.path = 's3://bucket/savepoint-1';"]}
        self.assertEqual(list(job.settings_of(d)),
                         [('pipeline.name', 'p'), ('execution.savepoint.path', 's3://bucket/savepoint-1')])


class TestMessage(unittest.TestCase):
    def test_flinks_message_without_py4j_stack_or_causes(self):
        error = ('An error occurred while calling o290.addInsertSql.\n'
                 ': org.apache.flink.table.api.SqlParserException: SQL parse failed. Encountered "||"\n'
                 'Was expecting one of:\n    "IN" ...\n'
                 '\tat org.apache.flink.Foo.bar(Foo.java:1)\n'
                 'Caused by: org.apache.calcite.sql.parser.SqlParseException: Encountered "||"\n')
        self.assertEqual(job.message_of(error),
                         'org.apache.flink.table.api.SqlParserException: SQL parse failed. Encountered "||"\n'
                         'Was expecting one of:\n    "IN" ...')


if __name__ == '__main__':
    unittest.main()
