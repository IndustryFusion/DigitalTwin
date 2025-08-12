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

HELM = os.getenv('IFF_HELM')
helm = False
if HELM is not None:
    helm = True

kafka_topic_bulk_alerts = "{{.Values.kafkaBridge.alerta.bulkTopic}}" if \
                          helm else "iff.alerts.bulk"
kafka_topic_listen_alerts = "{{.Values.kafkaBridge.alerta.listenTopic}}" \
                            if helm else "iff.alerts"
kafka_topic_ngsild_updates = "{{.Values.kafkaBridge.ngsildUpdates.\
listenTopic}}" if helm else "ff.ngsild-updates"
kafka_topic_attributes = "{{.Values.kafkaBridge.debezium.\
attributesTopic}}" if helm else \
                         "iff.ngsild.attributes"
kafka_topic_attributes_insert = "{{.Values.kafkaBridge.debezium.\
attributesTopic}}_insert" if helm else "iff.ngsild.attributes_insert"

kafka_topic_ngsi_prefix = "iff.ngsild.entities"
kafka_topic_ngsi_prefix_name = "entities"
kafka_topic_ngsi_retention = "{{.Values.kafkaBridge.debezium.\
entityTopicRetention}}"
kafka_bootstrap = "{{.Values.kafka.bootstrapServer}}" if helm \
                  else "my-cluster-kafka-bootstrap:9092"
rdf_topic = "iff.rdf"
kafka_topic_constraint_table_name = "{{.Values.kafkaBridge.flink.constraintTopic.topicName}}" if \
    helm else "iff.ngsild.flink.constraint_table"
kafka_topic_constraint_table_object = "{{.Values.kafkaBridge.flink.constraintTopic.objectName}}" if \
    helm else "iff.ngsild.flink.constraint-table"
kafka_topic_constraint_trigger_table_name = "{{.Values.kafkaBridge.flink.constraintTriggerTopic.topicName}}" if \
    helm else "iff.ngsild.flink.constraint_trigger_table"
kafka_topic_constraint_trigger_table_object = "{{.Values.kafkaBridge.flink.constraintTriggerTopic.objectName}}" if \
    helm else "iff.ngsild.flink.constraint-trigger-table"
kafka_topic_constraint_combination_table_name = "{{.Values.kafkaBridge.flink.constraintCombinationTopic.topicName}}" \
    if helm else "iff.ngsild.flink.constraint_combination_table"
kafka_topic_constraint_combination_table_object = \
    "{{.Values.kafkaBridge.flink.constraintCombinationTopic.objectName}}" if \
    helm else "iff.ngsild.flink.constraint-combination-table"
rdf_retention_ms = 86400000
kafka_topic_object_label = ['strimzi.io/cluster', 'my-cluster']
iff_namespace = 'https://industry-fusion.com/types/v0.9/'

attributes_table_name = 'attributes'
attributes_table_obj_name = 'attributes'
attributes_view_obj_name = 'attributes-view'
rdf_table_obj_name = 'rdf'
rdf_table_name = 'rdf'
alerts_bulk_table_name = 'alerts_bulk'
alerts_bulk_table_object_name = 'alerts-bulk'
attributes_insert_table_obj_name = 'attributes-insert'
constraint_table_name = 'constraint_table'
constraint_table_object_name = 'constraint-table'
constraint_combination_table_name = 'constraint_combination_table'
constraint_combination_table_object_name = 'constraint-combination-table'
constraint_trigger_table_name = 'constraint_trigger_table'
constraint_trigger_table_object_name = 'constraint-trigger-table'
rdf_max_per_set = 1500
max_sql_configmap_size = 200000
flink_ttl = '{{.Values.flink.ttl}}'
