#
# Copyright (c) 2022 Intel Corporation
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

from unittest.mock import patch
from rdflib import Namespace
from rdflib.namespace import RDF
import create_ngsild_tables
import os

ex = Namespace("http://example.com#")
sh = Namespace("http://www.w3.org/ns/shacl#")


@patch('create_ngsild_tables.ruamel.yaml')
@patch('create_ngsild_tables.Graph')
@patch('create_ngsild_tables.configs')
@patch('create_ngsild_tables.utils')
def test_main(mock_utils, mock_configs, mock_graph,
              mock_yaml, tmp_path):
    mock_configs.kafka_topic_ngsi_prefix = 'ngsild_prefix'
    mock_configs.kafka_bootstrap = 'bootstrap'
    mock_utils.create_sql_table.return_value = "sqltable"
    mock_utils.create_yaml_table.return_value = "yamltable"
    mock_utils.create_sql_view.return_value = "sqlview"
    mock_utils.create_yaml_view.return_value = "yamlview"
    mock_yaml.dump.return_value = "dump"
    g = mock_graph.return_value
    g.__contains__.return_value = True
    g.triples.return_value = [(ex.test, RDF.type, sh.NodeShape)]
    g.value.return_value = [(ex.test, sh.targetClass, ex.test2)]
    g.return_value = [(ex.test, sh.property, None)]

    create_ngsild_tables.main('kms/shacl.ttl', tmp_path)

    assert os.path.exists(os.path.join(tmp_path, 'ngsild.yaml')) is True
    assert os.path.exists(os.path.join(tmp_path, 'ngsild.sqlite')) is True
