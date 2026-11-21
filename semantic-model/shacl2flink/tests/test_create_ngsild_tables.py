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

from unittest.mock import patch, MagicMock
from rdflib import Namespace
import create_ngsild_tables
import os
import ruamel.yaml

ex = Namespace("http://example.com#")
sh = Namespace("http://www.w3.org/ns/shacl#")


class dotdict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


@patch('create_ngsild_tables.ruamel.yaml')
@patch('create_ngsild_tables.configs')
@patch('create_ngsild_tables.utils')
def test_main(mock_utils, mock_configs,
              mock_yaml, tmp_path, monkeypatch):
    def identity(val):
        return val
    mock_configs.kafka_topic_ngsi_prefix = 'ngsild_prefix'
    mock_configs.kafka_bootstrap = 'bootstrap'
    mock_utils.create_sql_table.return_value = "sqltable"
    mock_utils.create_yaml_table.return_value = "yamltable"
    mock_utils.create_sql_view.return_value = "sqlview"
    mock_utils.create_yaml_view.return_value = "yamlview"
    mock_utils.camelcase_to_snake_case.return_value = 'shacltype'
    mock_utils.get_common_data.return_value = {
        'flink': {
            'db': {
                'replicationUser': 'replication_user',
                'writeUser': 'write_user'
            }
        }
    }
    monkeypatch.setattr(mock_utils, "transitive_closure", identity)

    mock_yaml.dump.return_value = "dump"
    shacltype = MagicMock()
    shacltype.toPython.return_value = 'shacltype'
    row = {'shacltype': shacltype, 'path': 'path'}
    row = dotdict(row)
    create_ngsild_tables.main(tmp_path)

    assert os.path.exists(os.path.join(tmp_path, 'ngsild.yaml')) is True
    assert os.path.exists(os.path.join(tmp_path, 'ngsild.sqlite')) is True
    assert os.path.exists(os.path.join(tmp_path, 'ngsild-kafka.yaml')) is True


def kafka_topics(path):
    yaml = ruamel.yaml.YAML(typ='safe')
    with open(path) as f:
        return [doc for doc in yaml.load_all(f) if doc and doc.get('kind') == 'KafkaTopic']


def test_only_the_shared_topic_is_kept(tmp_path):
    # iff.ngsild.entities is written and read by the bridges, so undeploying
    # the validation must leave it; the topics of the validation's own tables
    # go with the release.
    create_ngsild_tables.main(tmp_path)

    shared = kafka_topics(os.path.join(tmp_path, create_ngsild_tables.shared_kafka_file))
    assert [t['spec']['topicName'] for t in shared] == ['iff.ngsild.entities']
    assert shared[0]['metadata']['annotations'] == {'helm.sh/resource-policy': 'keep'}

    own = kafka_topics(os.path.join(tmp_path, 'ngsild-kafka.yaml'))
    assert len(own) == 3
    assert 'iff.ngsild.entities' not in [t['spec']['topicName'] for t in own]
    for topic in own:
        assert 'annotations' not in topic['metadata']
