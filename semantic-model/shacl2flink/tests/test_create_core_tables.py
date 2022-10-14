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

from unittest.mock import patch, call
import create_core_tables


@patch('create_core_tables.ruamel.yaml')
@patch('create_core_tables.configs')
@patch('create_core_tables.utils')
def test_main(mock_utils, mock_configs, mock_yaml):
    mock_configs.kafka_topic_bulk_alerts = 'bulk_alerts'
    mock_configs.kafa_topic_listen_alerts = 'listen_alerts'
    mock_configs.kafka_topic_ngsild_updates = 'ngsild_updates'
    mock_configs.kafka_topic_attributes = 'attributes'
    mock_configs.kafka_bootstrap = 'bootstrap'
    mock_utils.create_sql_table.return_value = "sqltable"
    mock_utils.create_yaml_table.return_value = "yamltable"
    mock_utils.create_sql_view.return_value = "sqlview"
    mock_utils.create_yaml_view.return_value = "yamlview"
    mock_yaml.dump.return_value = "dump"

    with patch('builtins.open') as mocked_open:
        create_core_tables.main()

        mocked_open.assert_has_calls([call("output/core.yaml", "w"),
                                      call("output/core.sqlite", 'w')])
