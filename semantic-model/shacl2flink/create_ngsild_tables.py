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

import os
import sys
import argparse
import ruamel.yaml
import lib.utils as utils
import lib.configs as configs
from ruamel.yaml.scalarstring import (SingleQuotedScalarString as sq)


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='create_ngsild_tables.py')
    parsed_args = parser.parse_args(args)
    return parsed_args


def main(output_folder='output'):
    yaml = ruamel.yaml.YAML()
    utils.create_output_folder(output_folder)

    # Kafka topic object for RDF
    config = {}
    config['retention.ms'] = configs.kafka_topic_ngsi_retention
    with open(os.path.join(output_folder, "ngsild.yaml"), "w") as f, \
            open(os.path.join(output_folder, "ngsild.sqlite"), "w") as sqlitef, \
            open(os.path.join(output_folder, "ngsild-kafka.yaml"), "w") as fk:

        # Create "entities"
        value = {
            'format': 'json',
            'json.fail-on-missing-field': False,
            'json.ignore-parse-errors': True
        }
        kafka = {
            'topic': f'{configs.kafka_topic_ngsi_prefix}',
            'properties': {'bootstrap.servers': configs.kafka_bootstrap},
            'scan.startup.mode': 'latest-offset'
        }

        connector = 'kafka'
        base_entity_table = []
        base_entity_table.append({sq("id"): "STRING"})
        base_entity_table.append({sq("type"): "STRING"})
        base_entity_table.append({sq("deleted"): "BOOLEAN"})
        base_entity_table.append({sq("ts"): "TIMESTAMP(3) METADATA FROM 'timestamp'"})
        base_entity_table.append({"watermark": "FOR `ts` AS `ts`"})

        base_entity_tablename = configs.kafka_topic_ngsi_prefix_name
        base_entity_primary_key = None
        print('---', file=f)
        yaml.dump(utils.create_yaml_table(base_entity_tablename, connector, base_entity_table,
                                          base_entity_primary_key, kafka, value), f)
        print(utils.create_sql_table(base_entity_tablename, base_entity_table, base_entity_primary_key,
                                     utils.SQL_DIALECT.SQLITE),
              file=sqlitef)
        print('---', file=f)
        base_entity_view_primary_key = ['id']
        yaml.dump(utils.create_yaml_view(base_entity_tablename, base_entity_table, base_entity_view_primary_key), f)
        print(utils.create_sql_view(base_entity_tablename, base_entity_table, base_entity_view_primary_key),
              file=sqlitef)
        print('---', file=fk)
        yaml.dump(utils.create_kafka_topic(f'{configs.kafka_topic_ngsi_prefix}',
                                           f'{configs.kafka_topic_ngsi_prefix}', configs.kafka_topic_object_label,
                                           config),
                  fk)

        # Create constraint_checks and and combination tables
        kafka_constraint_checks = {
            'topic': configs.kafka_topic_constraint_table_name,
            'properties': {'bootstrap.servers': configs.kafka_bootstrap},
            'key.format': 'json'
        }

        value = {
            'format': 'json',
            'json.fail-on-missing-field': False,
            'json.ignore-parse-errors': True
        }
        connector = 'upsert-kafka'
        print('---', file=f)
        yaml.dump(utils.create_constraint_yaml_table(connector, kafka_constraint_checks, value), f)

        print(utils.create_constraint_sql_table(),
              file=sqlitef)
        print('---', file=fk)
        yaml.dump(utils.create_kafka_topic(f'{configs.kafka_topic_constraint_table_object}',
                                           f'{configs.kafka_topic_constraint_table_name}',
                                           configs.kafka_topic_object_label,
                                           config),
                  fk)
        # Create constraint trigger table
        kafka_constraint_trigger_checks = {
            'topic': configs.kafka_topic_constraint_trigger_table_name,
            'properties': {'bootstrap.servers': configs.kafka_bootstrap},
            'key.format': 'json'
        }

        value = {
            'format': 'json',
            'json.fail-on-missing-field': False,
            'json.ignore-parse-errors': True
        }
        connector = 'upsert-kafka'
        print('---', file=f)
        yaml.dump(utils.create_constraint_trigger_yaml_table(connector, kafka_constraint_trigger_checks, value), f)

        print(utils.create_constraint_trigger_sql_table(),
              file=sqlitef)
        print('---', file=fk)
        yaml.dump(utils.create_kafka_topic(f'{configs.kafka_topic_constraint_trigger_table_object}',
                                           f'{configs.kafka_topic_constraint_trigger_table_name}',
                                           configs.kafka_topic_object_label,
                                           config),
                  fk)
        # Create constraint combination table
        kafka_constraint_combination_checks = {
            'topic': configs.kafka_topic_constraint_combination_table_name,
            'properties': {'bootstrap.servers': configs.kafka_bootstrap},
            'key.format': 'json'
        }

        value = {
            'format': 'json',
            'json.fail-on-missing-field': False,
            'json.ignore-parse-errors': True
        }
        connector = 'upsert-kafka'
        print('---', file=f)
        yaml.dump(utils.create_constraint_combination_yaml_table(connector,
                                                                 kafka_constraint_combination_checks,
                                                                 value),
                  f)

        print(utils.create_constraint_combination_sql_table(),
              file=sqlitef)
        print('---', file=fk)
        yaml.dump(utils.create_kafka_topic(f'{configs.kafka_topic_constraint_combination_table_object}',
                                           f'{configs.kafka_topic_constraint_combination_table_name}',
                                           configs.kafka_topic_object_label,
                                           config),
                  fk)


if __name__ == '__main__':
    args = parse_args()
    main()
