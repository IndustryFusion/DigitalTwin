#
# Copyright (c) 2023 Intel Corporation
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

from unittest.mock import MagicMock, patch
import lib.shacl_construct_to_sql
from bunch import Bunch


@patch('lib.shacl_construct_to_sql.Graph')
@patch('lib.shacl_construct_to_sql.owlrl')
@patch('lib.shacl_construct_to_sql.translate_sparql')
@patch('lib.shacl_construct_to_sql.add_variables_to_message')
@patch('lib.shacl_construct_to_sql.utils')
def test_translate(mock_utils, mock_add_variables_to_message, mock_translate_sparql,
                   mock_owlrl, mock_graph, monkeypatch):
    def mock_add_variables_to_message(message):
        return message
    g = mock_graph.return_value

    def mock_strip_class(klass):
        return klass

    monkeypatch.setattr(lib.shacl_construct_to_sql, "add_variables_to_message", mock_add_variables_to_message)
    monkeypatch.setattr(mock_utils, "strip_class", mock_strip_class)
    monkeypatch.setattr(mock_utils, "class_to_obj_name", mock_strip_class)
    monkeypatch.setattr(mock_utils, "camelcase_to_snake_case", mock_strip_class)

    message = MagicMock()
    message.toPython.return_value = 'message'
    construct = MagicMock()
    construct.toPython.return_value = 'construct'
    nodeshape = MagicMock()
    nodeshape.toPython.return_value = 'nodeshape'
    targetclass = MagicMock()
    targetclass.toPython.return_value = 'targetclass'
    severitylabel = MagicMock()
    severitylabel.toPython.return_value = 'severitylabel'
    mock_translate_sparql.return_value = ([], [])
    g.__iadd__.return_value.query.return_value = [Bunch()]
    g.__iadd__.return_value.query.return_value[0].message = message
    g.__iadd__.return_value.query.return_value[0].construct = construct
    g.__iadd__.return_value.query.return_value[0].nodeshape = nodeshape
    g.__iadd__.return_value.query.return_value[0].targetclass = targetclass
    g.__iadd__.return_value.query.return_value[0].severitylabel = severitylabel
    mock_utils.process_sql_dialect.return_value = 'adapted_sql_dialect'
    sqlite, (statementsets, tables, views) = \
        lib.shacl_construct_to_sql.translate('kms/shacl.ttl',
                                             'kms/knowledge.ttl')
    assert tables == ['alerts-bulk', 'rdf', 'attributes', 'attributes-insert']
    assert views == []
    assert len(statementsets) == 1
    lower_sqlite = sqlite.lower()
    assert lower_sqlite == '\nadapted_sql_dialect;'
