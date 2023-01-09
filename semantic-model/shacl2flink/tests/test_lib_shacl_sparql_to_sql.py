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
import lib.shacl_sparql_to_sql
from bunch import Bunch


@patch('lib.shacl_sparql_to_sql.Graph')
@patch('lib.shacl_sparql_to_sql.owlrl')
@patch('lib.shacl_sparql_to_sql.translate_sparql')
@patch('lib.shacl_sparql_to_sql.add_variables_to_message')
def test_translate(mock_add_variables_to_message, mock_translate_sparql, mock_owlrl, mock_graph, monkeypatch):
    def mock_add_variables_to_message(message):
        return message
    g = mock_graph.return_value

    monkeypatch.setattr(lib.shacl_sparql_to_sql, "add_variables_to_message", mock_add_variables_to_message)
    message = MagicMock()
    message.toPython.return_value = 'message'
    select = MagicMock()
    select.toPython.return_value = 'select'
    nodeshape = MagicMock()
    nodeshape.toPython.return_value = 'nodeshape'
    targetclass = MagicMock()
    targetclass.toPython.return_value = 'targetclass'
    severitylabel = MagicMock()
    severitylabel.toPython.return_value = 'severitylabel'
    mock_translate_sparql.return_value = ([], [])
    g.__iadd__.return_value.query.return_value = [Bunch()]
    g.__iadd__.return_value.query.return_value[0].message = message
    g.__iadd__.return_value.query.return_value[0].select = select
    g.__iadd__.return_value.query.return_value[0].nodeshape = nodeshape
    g.__iadd__.return_value.query.return_value[0].targetclass = targetclass
    g.__iadd__.return_value.query.return_value[0].severitylabel = severitylabel
    sqlite, (statementsets, tables, views) = \
        lib.shacl_sparql_to_sql.translate('kms/shacl.ttl',
                                          'kms/knowledge.ttl')
    assert tables == ['alerts-bulk', 'rdf']
    assert views == []
    assert len(statementsets) == 1
    lower_sqlite = sqlite.lower()
    assert lower_sqlite.count('select') == 3
    assert "select id as this from targetclass_view" in lower_sqlite
    assert "'severitylabel'" in lower_sqlite
    assert "'message'" in lower_sqlite
