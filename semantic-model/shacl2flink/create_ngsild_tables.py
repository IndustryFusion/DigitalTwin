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

from rdflib import Graph, Namespace
from rdflib.namespace import RDF
import os
import sys
import argparse
from urllib.parse import urlparse
import ruamel.yaml
import lib.utils as utils
import lib.configs as configs
from ruamel.yaml.scalarstring import (SingleQuotedScalarString as sq)


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='create_ngsild_tables.py \
                                                  <shacl.ttl>')
    parser.add_argument('shaclfile', help='Path to the SHACL file')
    parsed_args = parser.parse_args(args)
    return parsed_args


def main(shaclfile, output_folder='output'):
    yaml = ruamel.yaml.YAML()
    utils.create_output_folder(output_folder)
    g = Graph()
    g.parse(shaclfile)
    sh = Namespace("http://www.w3.org/ns/shacl#")
    tables = {}
    for s, p, o in g.triples((None, RDF.type, sh.NodeShape)):
        for _, _, target_class in g.triples((s, sh.targetClass, None)):
            if (s, sh.property, None) not in g:
                break
            stripped_class = utils.strip_class(target_class.toPython())
            if stripped_class not in tables:
                table = []
                tables[stripped_class] = table
            else:
                table = tables[stripped_class]
            table.append({sq("id"): "STRING"})
            table.append({sq("type"): "STRING"})

            for _, _, target_property in g.triples((s, sh.property, None)):
                target_path = g.value(target_property, sh.path)
                table.append({sq(f'{target_path}'): "STRING"})
            table.append({sq("ts"): "TIMESTAMP(3) METADATA FROM 'timestamp'"})
            table.append({sq("WATERMARK"): "FOR `ts` AS `ts`"})

    # Kafka topic object for RDF
    config = {}
    config['retention.ms'] = configs.kafka_topic_ngsi_retention
    with open(os.path.join(output_folder, "ngsild.yaml"), "w") as f,\
            open(os.path.join(output_folder, "ngsild.sqlite"), "w") as sqlitef:
        for table_name, table in tables.items():
            connector = 'kafka'
            primary_key = None
            kafka = {'topic':
                     f'{configs.kafka_topic_ngsi_prefix}.{table_name}',
                     'properties': {'bootstrap.servers':
                                    configs.kafka_bootstrap},
                     'scan.startup.mode': 'earliest-offset'
                     }
            value = {
                'format': 'json',
                'json.fail-on-missing-field': False,
                'json.ignore-parse-errors': True
            }
            print('---', file=f)
            yaml.dump(utils.create_yaml_table(table_name, connector, table,
                                              primary_key, kafka, value), f)
            print(utils.create_sql_table(table_name, table, primary_key,
                                         utils.SQL_DIALECT.SQLITE),
                  file=sqlitef)
            print('---', file=f)
            yaml.dump(utils.create_yaml_view(table_name, table), f)
            print(utils.create_sql_view(table_name, table), file=sqlitef)
            print('---', file=f)
            yaml.dump(utils.create_kafka_topic(f'{configs.kafka_topic_ngsi_prefix}.\
{utils.class_to_obj_name(table_name)}',
                                               f'{configs.kafka_topic_ngsi_prefix}.\
{table_name}', configs.kafka_topic_object_label,
                                               config), f)


if __name__ == '__main__':
    args = parse_args()
    shaclfile = args.shaclfile
    main(shaclfile)
