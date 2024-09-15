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

from unittest.mock import patch, mock_open
import os
import create_sql_checks_from_shacl
from create_sql_checks_from_shacl import parse_args


@patch('create_sql_checks_from_shacl.translate_sparql')
@patch('create_sql_checks_from_shacl.translate_properties')
@patch('create_sql_checks_from_shacl.translate_construct')
@patch('create_sql_checks_from_shacl.ruamel.yaml')
@patch('create_sql_checks_from_shacl.utils')
@patch('create_sql_checks_from_shacl.rdflib')
def test_main(mock_rdflib, mock_utils, mock_yaml, mock_translate_construct, mock_translate_properties,
              mock_translate_sparql, tmp_path):
    def __add__(self, other):
        return self

    mock_utils.create_statementset.return_value = 'create_statementsets'

    mock_translate_properties.return_value = 'sqlite', ('statementsets',
                                                        ['tables'], ['views'])
    mock_translate_sparql.return_value = 'sqlite2', ('statementsets2',
                                                     ['tables2'], ['views2'])
    mock_translate_construct.return_value = 'sqlite3', ('statementsets3',
                                                        ['tables3'], ['views3'])
    mock_rdflib.Graph.return_value = mock_rdflib
    mock_rdflib.namespaces.return_value = [['base', 'baseurl']]
    with patch("builtins.open", mock_open(read_data="data")) as mock_file:
        create_sql_checks_from_shacl.main('kms/shacl.ttl', 'kms/knowledge.ttl', 'iff', None,
                                          tmp_path)
    mock_file.assert_called_with(os.path.join(tmp_path, 'shacl-validation.sqlite'), 'w')
    assert mock_yaml.YAML().dump.called


def test_parse_args_minimal():
    # Simulate minimal command-line arguments
    test_args = [
        "path/to/shacl.ttl",
        "path/to/knowledge.ttl"
    ]
    parsed_args = parse_args(test_args)

    assert parsed_args.shaclfile == "path/to/shacl.ttl"
    assert parsed_args.knowledgefile == "path/to/knowledge.ttl"
    assert parsed_args.context is None
    assert parsed_args.namespace == "iff"
    assert parsed_args.enable_checkpointing is False
