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
from unittest.mock import patch, mock_open
import check_sparql_expression



@patch('check_sparql_expression.rdflib')
@patch('check_sparql_expression.owlrl')
def test_main(mock_owlrl, mock_rdflib):
    with patch("builtins.open", mock_open(read_data="data")) as mock_file:
        check_sparql_expression.main('queryfile.txt', 'kms/shacl.ttl', 'kms/knowledge.ttl', 'kms/model.jsonld')
    mock_file.assert_called_with("queryfile.txt", 'r')