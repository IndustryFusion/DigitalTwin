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

import lib.configs as configs
import ruamel.yaml
import lib.utils as utils
yaml = ruamel.yaml.YAML()


def main():
    utils.create_output_folder()

    kafka_topic_bulk_alerts = configs.kafka_topic_bulk_alerts
    kafka_topic_listen_alerts = configs.kafka_topic_listen_alerts
    kafka_topic_ngsild_updates = configs.kafka_topic_ngsild_updates
    kafka_topic_attributes = configs.kafka_topic_attributes
    kafka_topic_attributes_insert = configs.kafka_topic_attributes_insert
    kafka_bootstrap = configs.kafka_bootstrap

    f = open("output/core.yaml", "w")
    sqlitef = open("output/core.sqlite", "w")

    # Kafka topic object for RDF
    config = {}
    config['retention.ms'] = configs.kafka_topic_ngsi_retention

    # alerts table
    table_name = "alerts"
    connector = 'upsert-kafka'
    table = [{'resource': 'STRING'},
             {'event': 'STRING'},
             {'environment': 'STRING'},
             {'service': 'ARRAY<STRING>'},
             {'severity': 'STRING'},
             {'customer': 'STRING'},
             {'text': 'STRING'}]
    table_sqlite = [{'resource': 'STRING'},
                    {'event': 'STRING'},
                    {'environment': 'STRING'},
                    {'service': 'STRING'},
                    {'severity': 'STRING'},
                    {'customer': 'STRING'},
                    {'text': 'STRING'}]
    primary_key = ['resource', 'event']
    kafka = {
        'topic': kafka_topic_listen_alerts,
        'properties': {'bootstrap.servers': kafka_bootstrap},
        'key.format': 'json'
    }
    value = {
        'format': 'json',
        'json.fail-on-missing-field': False,
        'json.ignore-parse-errors': True
    }

    print('---', file=f)
    yaml.dump(utils.create_yaml_table(table_name, connector, table,
                                      primary_key, kafka, value), f)
    print(utils.create_sql_table(table_name, table_sqlite,
                                 primary_key), file=sqlitef)

    # alerts-bulk table
    table_name = "alerts-bulk"
    spec_name = "alerts_bulk"
    connector = 'upsert-kafka'
    table = [{'resource': 'STRING'},
             {'event': 'STRING'},
             {'environment': 'STRING'},
             {'service': 'ARRAY<STRING>'},
             {'severity': 'STRING'},
             {'customer': 'STRING'},
             {'text': 'STRING'},
             {'watermark': 'FOR `ts` AS `ts`'},
             {'ts': ' TIMESTAMP(3) METADATA VIRTUAL'}]
    table_sqlite = [{'resource': 'STRING'},
                    {'event': 'STRING'},
                    {'environment': 'STRING'},
                    {'service': 'STRING'},
                    {'severity': 'STRING'},
                    {'customer': 'STRING'},
                    {'text': 'STRING'},
                    {'watermark': 'FOR `ts` AS `ts`'},
                    {'ts': ' TIMESTAMP(3) METADATA VIRTUAL'}]
    primary_key = ['resource', 'event']
    kafka = {'topic': kafka_topic_bulk_alerts,
             'properties': {'bootstrap.servers': kafka_bootstrap},
             'key.format': 'json'
             }
    value = {
        'format': 'json',
        'json.fail-on-missing-field': False,
        'json.ignore-parse-errors': True
    }

    print('---', file=f)
    yaml.dump(utils.create_yaml_table(spec_name, connector, table,
                                      primary_key, kafka, value), f)
    print(utils.create_sql_table(spec_name, table_sqlite,
                                 primary_key, utils.SQL_DIALECT.SQLITE),
          file=sqlitef)
    print(utils.create_sql_view(spec_name, table_sqlite, primary_key, []),
          file=sqlitef)

    # ngsild-updates table
    table_name = "ngsild-updates"
    spec_name = "ngsild_updates"
    connector = 'kafka'
    table = [{'op': 'STRING'},
             {'overwirteOrReplace': 'BOOLEAN'},
             {'noForward': 'BOOLEAN'},
             {'entities': 'STRING'}]
    primary_key = None
    kafka = {
        'topic': kafka_topic_ngsild_updates,
        'properties': {'bootstrap.servers': kafka_bootstrap},
        'scan.startup.mode': 'latest-offset'
    }
    value = {
        'format': 'json',
        'json.fail-on-missing-field': False,
        'json.ignore-parse-errors': True
    }

    print('---', file=f)
    yaml.dump(utils.create_yaml_table(spec_name, connector, table,
                                      primary_key, kafka, value), f)
    print(utils.create_sql_table(spec_name, table, primary_key),
          file=sqlitef)

    # attributes table
    table_name = "attributes"
    spec_name = "attributes"
    connector = 'kafka'
    table = [
        {'id': 'STRING'},
        {'parentId': 'STRING'},
        {'entityId': 'STRING'},
        {'name': 'STRING'},
        {'nodeType': 'STRING'},
        {'valueType': 'STRING'},
        {'type': 'STRING'},
        {'attributeValue': 'STRING'},
        {'datasetId': 'STRING'},
        {'unitCode': 'STRING'},
        {'lang': 'STRING'},
        {'deleted': 'BOOLEAN'},
        {'synced': 'BOOLEAN'},
        # The EVENT time, carried in the payload by debeziumBridge as epoch
        # millis. `ts` is the WRITE time (the Kafka record timestamp), which is
        # what retention.ms -- a wall-clock STORAGE policy -- must act on: while
        # observedAt lived there, the kms model's 2024 observations were born
        # older than any sane retention and Kafka deleted them on contact.
        # The two are separated for that reason; `eventTime` below is what the
        # dedup orders by.
        {'observedAt': 'TIMESTAMP(3)'},
        {'ts': "TIMESTAMP(3) METADATA FROM 'timestamp'"},
        # The event time as a ROWTIME attribute, which is what makes the
        # attributes_view dedup compile into Flink's Deduplicate (keep-last-row)
        # instead of a general Rank. That matters twice:
        #
        #   ties     -- Deduplicate accepts a later row of EQUAL eventTime,
        #               a Rank keeps the incumbent. Same-instant records are
        #               real (bridge-stamped receive times, snapshot
        #               re-emissions), which is why a tie-break was needed at
        #               all. Deduplicate breaks them by arrival for free, so the
        #               `offset` column this table used to carry is gone.
        #   soundness -- from Flink 2.1 a top-1 ROW_NUMBER whose ORDER BY is not
        #               a single time attribute is wrongly declared INSERT_ONLY
        #               and its retractions are silently dropped: alerts raise
        #               and never clear. A two-column key hit that; a rowtime
        #               single-column key does not. See
        #               docs/flink-2.3-retraction-bug.md.
        #
        # COALESCE, not observedAt alone: a writer that sets no observedAt --
        # the writeback stamping `synced`, for one -- would otherwise produce
        # NULL, lose every comparison and never win the dedup. Falling back to
        # the write time is what those rows did before.
        {'eventTime': "AS COALESCE(`observedAt`, `ts`)"},
        # Nothing windows over this table, so the watermark is not consumed by
        # any operator here; declaring it is what promotes eventTime to a
        # rowtime. Deduplicate compares rowtimes, it does not drop late rows,
        # so out-of-order event times (a 2024 model observation arriving after
        # live data) are ordered, not discarded.
        {'watermark': "FOR `eventTime` AS `eventTime`"}
    ]
    sqlite_table = [
        {'id': 'TEXT'},
        {'parentId': 'TEXT'},
        {'entityId': 'TEXT'},
        {'name': 'TEXT'},
        {'nodeType': 'TEXT'},
        {'valueType': 'TEXT'},
        {'type': 'TEXT'},
        {'attributeValue': 'TEXT'},
        {'datasetId': 'TEXT'},
        {'unitCode': 'TEXT'},
        {'lang': 'TEXT'},
        {'deleted': 'BOOLEAN'},
        {'synced': 'BOOLEAN'},
        {'observedAt': 'TIMESTAMP(3)'},
        {'ts': "TIMESTAMP(3) METADATA FROM 'timestamp'"}
    ]
    primary_key = None
    kafka = {
        'topic': kafka_topic_attributes,
        'properties': {'bootstrap.servers': kafka_bootstrap},
        'scan.startup.mode': 'latest-offset'
    }
    value = {
        'format': 'json',
        'json.fail-on-missing-field': False,
        'json.ignore-parse-errors': True
    }
    print('---', file=f)
    yaml.dump(utils.create_yaml_table(table_name, connector, table,
                                      primary_key, kafka, value), f)
    print(utils.create_sql_table(table_name, sqlite_table, primary_key,
                                 utils.SQL_DIALECT.SQLITE), file=sqlitef)
    print('---', file=f)
    # Names its own TTL setting for the same reason as entities_view, and
    # defaults to the same value. Not to be set to never-expire -- see
    # lib/configs.py.
    yaml.dump(utils.create_yaml_view(table_name, table, ['id', 'datasetId'],
                                     ttl=configs.view_state_ttl), f)
    print(utils.create_sql_view(table_name, sqlite_table, ['id', 'datasetId']),
          file=sqlitef)
    # attributes_insert upsert-table
    table_name = "attributes-insert"
    spec_name = "attributes_insert"
    connector = 'upsert-kafka'
    table = [
        {'id': 'STRING'},
        {'parentId': 'STRING'},
        {'entityId': 'STRING'},
        {'name': 'STRING'},
        {'nodeType': 'STRING'},
        {'valueType': 'STRING'},
        {'type': 'STRING'},
        {'attributeValue': 'STRING'},
        {'datasetId': 'STRING'},
        {'unitCode': 'STRING'},
        {'lang': 'STRING'},
        {'deleted': 'BOOLEAN'},
        {'synced': 'BOOLEAN'}
    ]
    kafka = {
        'topic': kafka_topic_attributes_insert,
        'properties': {'bootstrap.servers': kafka_bootstrap},
        'key.format': 'json'
    }
    value = {
        'format': 'json',
        'json.fail-on-missing-field': False,
        'json.ignore-parse-errors': True
    }
    primary_key = ['id', 'datasetId']

    print('---', file=f)
    yaml.dump(utils.create_yaml_table(spec_name, connector, table,
                                      primary_key, kafka, value), f)
    yaml.dump(utils.create_kafka_topic(f'{configs.kafka_topic_ngsi_prefix}.\
        {utils.class_to_obj_name(table_name)}', f'{configs.kafka_topic_ngsi_prefix}.\
        {spec_name}', configs.kafka_topic_object_label, config), f)

    # attributes_insert plain table to copy data
    table_name = "attributes-insert-filter"
    spec_name = "attributes_insert_filter"
    connector = 'kafka'
    table = [
        {'id': 'STRING'},
        {'parentId': 'STRING'},
        {'entityId': 'STRING'},
        {'name': 'STRING'},
        {'nodeType': 'STRING'},
        {'valueType': 'STRING'},
        {'type': 'STRING'},
        {'attributeValue': 'STRING'},
        {'datasetId': 'STRING'},
        {'unitCode': 'STRING'},
        {'lang': 'STRING'},
        {'deleted': 'BOOLEAN'},
        {'synced': 'BOOLEAN'},
        {'ts': "TIMESTAMP(3) METADATA FROM 'timestamp'"},
        {'watermark': 'FOR `ts` AS `ts`'}
    ]
    kafka = {
        'topic': f'{kafka_topic_attributes_insert}',
        'properties': {'bootstrap.servers': kafka_bootstrap},
        'scan.startup.mode': 'latest-offset'
    }
    value = {
        'format': 'json',
        'json.fail-on-missing-field': False,
        'json.ignore-parse-errors': True
    }
    primary_key = None

    print('---', file=f)
    yaml.dump(utils.create_yaml_table(spec_name, connector, table,
                                      primary_key, kafka, value), f)
    print(utils.create_sql_table(spec_name, table, primary_key,
                                 utils.SQL_DIALECT.SQLITE), file=sqlitef)
    print('---', file=f)

    # alerts table
    table_name = "constraints"
    connector = 'kafka'
    table = [{'id': 'STRING'},
             {'event': 'STRING'},
             {'environment': 'STRING'},
             {'service': 'ARRAY<STRING>'},
             {'severity': 'STRING'},
             {'customer': 'STRING'},
             {'text': 'STRING'}]
    table_sqlite = [{'resource': 'STRING'},
                    {'event': 'STRING'},
                    {'environment': 'STRING'},
                    {'service': 'STRING'},
                    {'severity': 'STRING'},
                    {'customer': 'STRING'},
                    {'text': 'STRING'}]
    primary_key = ['resource', 'event']
    kafka = {
        'topic': kafka_topic_listen_alerts,
        'properties': {'bootstrap.servers': kafka_bootstrap},
        'key.format': 'json'
    }
    value = {
        'format': 'json',
        'json.fail-on-missing-field': False,
        'json.ignore-parse-errors': True
    }

    print('---', file=f)
    yaml.dump(utils.create_yaml_table(table_name, connector, table,
                                      primary_key, kafka, value), f)
    print(utils.create_sql_table(table_name, table_sqlite,
                                 primary_key), file=sqlitef)


if __name__ == '__main__':
    main()
