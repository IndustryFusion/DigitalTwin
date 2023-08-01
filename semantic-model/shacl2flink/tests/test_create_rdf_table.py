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

import os.path
from unittest.mock import patch, MagicMock
import create_rdf_table


@patch('create_rdf_table.argparse')
def test_input_arguments(mock_argparse):
    parser = mock_argparse.ArgumentParser.return_value
    parser.parse_args.return_value = "args"
    args = create_rdf_table.parse_args(['test'])
    assert args == 'args'


def test_create_table():
    table = create_rdf_table.create_table()
    assert table == [{"subject": "STRING"}, {"predicate": "STRING"},
                     {"object": "STRING"}, {"index": "INTEGER"}]


@patch('create_rdf_table.hashlib')
@patch('create_rdf_table.configs')
@patch('create_rdf_table.utils')
def test_create_statementset(mock_utils, mock_configs, mock_hashlib):
    def format_node_type(x):
        return x.toPython()
    graph = MagicMock()
    s = MagicMock()
    p = MagicMock()
    o = MagicMock()
    s.toPython.return_value = 's'
    p.toPython.return_value = 'p'
    o.toPython.return_value = 'o'
    hash_object = mock_hashlib.sha256.return_value
    hash_object.hex_dig.return_value = 'ABCDEF'
    max_per_set = 1
    mock_configs.rdf_max_per_set = max_per_set
    mock_utils.format_node_type = format_node_type
    graph.triples.return_value = [(s, p, o)]
    graph.__len__.return_value = max_per_set
    statementset = create_rdf_table.create_statementset(graph)
    assert statementset == ['(s, p, o, 0);']
    graph.__len__.return_value = max_per_set + 1
    graph.triples.return_value = [(s, p, o), (s, p, o)]
    statementset = create_rdf_table.create_statementset(graph)
    assert statementset == ['(s, p, o, 0);', '(s, p, o, 1);']


@patch('create_rdf_table.ruamel.yaml')
@patch('create_rdf_table.owlrl')
@patch('create_rdf_table.rdflib')
@patch('create_rdf_table.create_table')
@patch('create_rdf_table.configs')
@patch('create_rdf_table.utils')
def test_main(mock_utils, mock_configs, mock_create_table, mock_rdflib,
              mock_owlrl, mock_yaml, tmp_path):
    mock_utils.create_sql_table.return_value = "sqltable"
    mock_utils.create_yaml_table.return_value = "yamltable"
    mock_utils.create_statementset.return_value = "statementset"
    mock_yaml.dump.return_value = "dump"
    create_rdf_table.main('kms/knowledge.ttl', 'namespace', tmp_path)

    assert os.path.exists(os.path.join(tmp_path, 'rdf.yaml')) is True
    assert os.path.exists(os.path.join(tmp_path, 'rdf.sqlite')) is True
    assert os.path.exists(os.path.join(tmp_path, 'rdf-kafka.yaml')) is True
