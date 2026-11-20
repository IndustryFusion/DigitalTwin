#
# Copyright (c) 2026 IndustryFusion Foundation
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
"""Every KafkaTopic the generators write rolls its segments at its retention,
but not more often than hourly.

Kafka deletes only whole segments, and only once the newest record in a
segment is older than retention.ms. A topic that is written to keeps its open
segment until segment.ms, which defaults to 7 days, so a topic with a 1 h
retention held days of records. These tests run the generators unmocked and
read back the topic manifests they write.
"""
import os

import ruamel.yaml

import create_ngsild_tables
import create_rdf_table


def _topics(path):
    with open(path) as f:
        docs = list(ruamel.yaml.YAML(typ='safe').load_all(f))
    return [d for d in docs if d and d.get('kind') == 'KafkaTopic']


def _assert_segments_roll_within_retention(topics):
    assert topics, 'no KafkaTopic was generated'
    for topic in topics:
        name = topic['spec']['topicName']
        config = topic['spec']['config']
        assert 'retention.ms' in config, f'{name} has no retention.ms'
        assert 'segment.ms' in config, f'{name} has no segment.ms'
        retention, segment = config['retention.ms'], config['segment.ms']
        if isinstance(retention, int):
            assert segment == max(retention, 3600000), f'{name}: segment.ms {segment} retention.ms {retention}'
        else:
            # a helm placeholder: the chart's expression for max(retention, 1 h)
            value = retention.strip('{} ')
            assert segment == f'{{{{ max 3600000 (int64 {value}) }}}}', \
                f'{name}: segment.ms {segment!r} retention.ms {retention!r}'


def test_ngsild_topics_roll_at_their_retention(tmp_path):
    create_ngsild_tables.main(str(tmp_path))
    topics = _topics(os.path.join(tmp_path, 'ngsild-kafka.yaml'))
    names = {t['spec']['topicName'] for t in topics}
    assert names == {'iff.ngsild.entities',
                     'iff.ngsild.flink.constraint_table',
                     'iff.ngsild.flink.constraint_trigger_table',
                     'iff.ngsild.flink.constraint_combination_table'}
    _assert_segments_roll_within_retention(topics)


def test_rdf_topic_rolls_at_its_retention(tmp_path):
    knowledge = tmp_path / 'knowledge.ttl'
    knowledge.write_text('<http://example.com/a> <http://example.com/b> <http://example.com/c> .\n')
    create_rdf_table.main(str(knowledge), 'iff', str(tmp_path / 'out'), create_kafka_topic=True)
    topics = _topics(os.path.join(tmp_path, 'out', 'rdf-kafka.yaml'))
    assert [t['spec']['topicName'] for t in topics] == ['iff.rdf']
    _assert_segments_roll_within_retention(topics)
