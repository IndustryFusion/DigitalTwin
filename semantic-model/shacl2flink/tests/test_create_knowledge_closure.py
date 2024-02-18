#
# Copyright (c) 2024 Intel Corporation
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
import create_knowledge_closure


@patch('create_knowledge_closure.rdflib')
@patch('create_knowledge_closure.owlrl')
def test_main(mock_owlrl, mock_rdflib, tmp_path):
    create_knowledge_closure.main('kms/knowledge.ttl', 'knowledge_closure.ttl')
