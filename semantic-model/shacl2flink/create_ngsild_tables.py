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
from lib.configs import constraint_table_name, constraint_combination_table_name
from ruamel.yaml.scalarstring import (SingleQuotedScalarString as sq)


golang_function = """
{{- $canLookup := not (empty (lookup "v1" "Namespace" "" "kube-system")) -}}
{{- $password := "PLACEHOLDER" -}}
{{- $secName := trim (required "Set .Values.flink.db.replicationUserSecret" .Values.flink.db.replicationUserSecret) -}}
{{- $sec := lookup "v1" "Secret" .Release.Namespace $secName -}}
{{- if and $canLookup (not $sec) -}}
  {{- fail (printf "Secret %q not found in %s" $secName .Release.Namespace) -}}
{{- end -}}
{{- if $canLookup -}}
  {{- $password := b64dec (get $sec.data "password") -}}
{{- end }}
"""

grant_reader_access = """
ALTER DEFAULT PRIVILEGES FOR ROLE {{ flink_writer_user }} IN SCHEMA public
  GRANT SELECT ON TABLES TO {{ flink_reader_user }};
ALTER DEFAULT PRIVILEGES FOR ROLE {{ flink_writer_user }} IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO {{ flink_reader_user }};
"""


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
            open(os.path.join(output_folder, "ngsild.postgres"), "w") as pgf, \
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
        connector = 'postgres-cdc'
        cdc = {
            'hostname': '{{.Values.clusterSvcName}}',
            'port': '{{.Values.db.svcPort}}',
            'username': '{{ .Values.flink.db.replicationUser }}',
            'password': '{{ (dig "data" "password" "" $sec | b64dec | default "PLACEHOLDER") }}',
            'database-name': '{{.Values.flink.db.name}}',
            'schema-name': '{{.Values.flink.db.schema}}',
            'table-name': constraint_table_name,
            'slot.name': '{{.Values.flink.db.constraintSlotName}}',
            'debezium.database.sslmode': 'require'
        }
        common_data = utils.get_common_data()

        f.write(golang_function)
        yaml.dump(utils.create_constraint_yaml_table(connector, kafka_constraint_checks, value, cdc), f)

        print(utils.create_constraint_sql_table(),
              file=sqlitef)
        postgres_repl_access = grant_reader_access.replace("{{ flink_writer_user }}",
                                                           common_data['flink']['db']['writeUser']) \
            .replace("{{ flink_reader_user }}", common_data['flink']['db']['replicationUser']) + '\n'
        print(postgres_repl_access, file=pgf)
        print(utils.create_constraint_sql_table(utils.SQL_DIALECT.POSTGRES),
              file=pgf)
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
        cdc['table-name'] = constraint_combination_table_name
        cdc['slot.name'] = '{{.Values.flink.db.constraintCombinationSlotName}}'
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
        connector = 'postgres-cdc'
        print('---', file=f)
        yaml.dump(utils.create_constraint_combination_yaml_table(connector,
                                                                 kafka_constraint_combination_checks,
                                                                 value, cdc), f)
        print(utils.create_constraint_combination_sql_table(utils.SQL_DIALECT.POSTGRES),
              file=pgf)
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
