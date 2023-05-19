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

from unittest.mock import MagicMock, patch
import os

import create_ngsild_models


def test_nullify():
    field = MagicMock()
    field.toPython.return_value = 'field'
    result = create_ngsild_models.nullify(None)
    assert result == 'NULL'
    result = create_ngsild_models.nullify(field)
    assert result == "'field'"


@patch('create_ngsild_models.nullify')
@patch('create_ngsild_models.Graph')
@patch('create_ngsild_models.configs')
@patch('create_ngsild_models.utils')
def test_main(mock_utils, mock_configs, mock_graph, mock_nullify, tmp_path):
    def __add__(self, other):
        return self

    mock_nullify.return_value = 'nullify'
    mock_configs.iff_namespace = 'iff_namespace'
    mock_configs.attributes_table_name = 'attributes'
    mock_utils.strip_class.return_value = 'strip_class'
    mock_graph.__add__.return_value = 'xxxx'
    g = mock_graph.return_value.__iadd__.return_value
    g.parse.return_value = 'xx'
    entityId = MagicMock()
    entityId.toPython.return_value = 'entityId'
    name = MagicMock()
    name.toPython.return_value = 'name'
    name.return_value = 'name'
    type = MagicMock()
    type.toPython.return_value = 'type'
    nodeType = MagicMock()
    nodeType.toPython.return_value = 'nodeType'
    valueType = MagicMock()
    valueType.toPython.return_value = 'valueType'
    hasValue = MagicMock()
    hasValue.toPython.return_value = 'hasValue'
    hasObject = MagicMock()
    hasObject.toPython.return_value = 'hasObject'
    observedAt = MagicMock()
    observedAt.toPython.return_value = 'Timestamp'
    index = MagicMock()
    index.toPython.return_value = 'index'
    g.query = MagicMock(side_effect=[
        [(entityId, name, type, nodeType, valueType, hasValue, hasObject, observedAt, index),
         (entityId, name, type, nodeType, valueType, hasValue, hasObject, observedAt, None),
         (entityId, name, type, nodeType, valueType, hasValue, hasObject, observedAt, None)],
        [(entityId, type, name, 1, type)]
    ])

    create_ngsild_models.main('kms/shacl.ttl', 'kms/knowledge.ttl',
                              'kms/model.jsonld', tmp_path)
    assert os.path.exists(os.path.join(tmp_path, 'ngsild-models.sqlite'))\
        is True


def test_parser():
    args = create_ngsild_models.parse_args(['shaclfile.ttl', 'knowledge.ttl', 'model.jsonld'])
    assert args.shaclfile == 'shaclfile.ttl'
    assert args.knowledgefile == 'knowledge.ttl'
    assert args.modelfile == 'model.jsonld'
