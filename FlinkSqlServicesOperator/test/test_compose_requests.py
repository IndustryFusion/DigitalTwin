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
Unit tests for compose_requests.py (openspec gh-955-flink-sql-validation)
"""
import json
import os
import tempfile
import unittest
from unittest import TestCase

import compose_requests as target

RENDERED = """
apiVersion: industry-fusion.com/v1alpha2
kind: BeamSqlTable
metadata:
  name: attributes
spec:
  name: attributes
  connector: kafka
  fields:
  - id: STRING
  - val: STRING
  kafka:
    topic: iff.attributes
    properties:
      bootstrap.servers: my-cluster-kafka-bootstrap:9092
    scan.startup.mode: latest-offset
  value:
    format: json
---
apiVersion: industry-fusion.com/v1alpha1
kind: BeamSqlView
metadata:
  name: attributes-view
spec:
  name: attributes_view
  sqlstatement: SELECT id, val FROM attributes
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: shacl-validation-configmap1
data:
  '0': INSERT INTO attributes SELECT id, val FROM attributes_view;
---
apiVersion: industry-fusion.com/v1alpha4
kind: BeamSqlStatementSet
metadata:
  name: shacl-validation
spec:
  name: shacl-validation
  tables: [attributes]
  views: [attributes-view]
  sqlsettings:
  - table.exec.state.ttl: '3600000'
  sqlstatementmaps: [iff/shacl-validation-configmap1]
  updateStrategy: none
---
apiVersion: industry-fusion.com/v1alpha1
kind: flinkpythonudf
metadata:
  name: hash
spec:
  filename: hash
  version: v1
  class: 'def register(table_env): pass'
"""


class TestComposeRequests(TestCase):
    """compose the requests the operator would send"""

    def run_main(self, rendered):
        """write the manifests, run main, return (exit code, outdir)"""
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'rendered.yaml')
        with open(path, 'w', encoding='utf-8') as file:
            file.write(rendered)
        outdir = os.path.join(directory, 'out')
        return target.main(['compose_requests.py', path, outdir]), outdir

    def test_a_statement_set_and_its_udf(self):
        """one request with DDL, view and the ConfigMap's statements, and the UDF file"""
        code, outdir = self.run_main(RENDERED)
        self.assertEqual(code, 0)
        with open(os.path.join(outdir, 'requests', 'iff_shacl-validation.json'), encoding='utf-8') as file:
            request = json.load(file)
        self.assertEqual(len(request['tables']), 1)
        self.assertIn('CREATE TABLE `attributes`', request['tables'][0])
        self.assertIn('CREATE VIEW `attributes_view`', request['views'][0])
        self.assertEqual(request['sqlstatementset'],
                         ['INSERT INTO attributes SELECT id, val FROM attributes_view;'])
        self.assertIn({'table.exec.state.ttl': '3600000'}, request['sqlsettings'])
        with open(os.path.join(outdir, 'udf', 'hash_v1.py'), encoding='utf-8') as file:
            self.assertEqual(file.read(), 'def register(table_env): pass')

    def test_a_missing_table_is_reported(self):
        """a statement set naming a table that is not there cannot be composed"""
        code, _ = self.run_main(RENDERED.replace('tables: [attributes]', 'tables: [nosuchtable]'))
        self.assertEqual(code, 1)

    def test_no_statement_set(self):
        """manifests without a statement set are an error"""
        code, _ = self.run_main(RENDERED.split('---')[0])
        self.assertEqual(code, 1)

    def test_tables_from_another_chart(self):
        """the tables may be rendered from another chart (sql-core)"""
        directory = tempfile.mkdtemp()
        first, rest = RENDERED.split('---', 1)
        paths = [os.path.join(directory, 'core.yaml'), os.path.join(directory, 'shacl.yaml')]
        for path, text in zip(paths, (first, rest)):
            with open(path, 'w', encoding='utf-8') as file:
                file.write(text)
        outdir = os.path.join(directory, 'out')
        self.assertEqual(target.main(['compose_requests.py', *paths, outdir]), 0)
        self.assertTrue(os.path.exists(os.path.join(outdir, 'requests', 'iff_shacl-validation.json')))

    def test_the_newest_udf_version(self):
        """as the SQL Gateway: the last of the sorted file names per UDF"""
        udfs = [target.resource({'spec': {'filename': 'hash', 'version': v, 'class': v}})
                for v in ('v1', 'v2')]
        self.assertEqual(target.newest_udfs(udfs), {'hash_v2.py': 'v2'})


if __name__ == '__main__':
    unittest.main()
