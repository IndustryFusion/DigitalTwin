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

import argparse
import os.path
import sys
import hashlib
import owlrl
import ruamel.yaml
import rdflib
from lib import utils
from lib import configs


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='create_rdf_table.py \
                                                  <knowledge.ttl>')
    parser.add_argument('knowledgefile', help='Path to the knowledge file')
    parsed_args = parser.parse_args(args)
    return parsed_args


def create_table():
    table = []
    table.append({"subject": "STRING"})
    table.append({"predicate": "STRING"})
    table.append({"object": "STRING"})
    table.append({"index": "INTEGER"})
    return table


def create_statementset(graph):
    """
    """
    statementset = ''
    first = True
    hash_counter = {}
    for s, p, o in graph.triples((None, None, None)):
        hash_object = hashlib.sha256(f'{s}{p}'.encode('utf-8'))
        hex_dig = hash_object.hexdigest()
        if hex_dig not in hash_counter:
            hash_counter[hex_dig] = 0
        else:
            hash_counter[hex_dig] += 1
        if not first:
            statementset += ",\n"
        else:
            first = False
        statementset += "(" + "'" + s.toPython() + "', '" + p.toPython() + \
                        "', '" + o.toPython() + "', " + \
                        str(hash_counter[hex_dig]) + ")"
    statementset += ";"
    return statementset


def main(knowledgefile, output_folder='output'):
    yaml = ruamel.yaml.YAML()

    utils.create_output_folder(output_folder)

    # Create RDF table object
    table_name = configs.rdf_table_obj_name
    spec_name = configs.rdf_table_name
    table = create_table()
    connector = 'upsert-kafka'
    kafka = {
        'topic': configs.rdf_topic,
        'properties': {
            'bootstrap.servers': configs.kafka_bootstrap
        },
        'key.format': 'json'
    }
    value = {'format': 'json',
             'json.fail-on-missing-field': False,
             'json.ignore-parse-errors': True}
    primary_key = ['subject', 'predicate', 'index']

    # Create RDF statements to insert data
    statementsets = []
    g = rdflib.Graph()
    g.parse(knowledgefile)
    owlrl.RDFSClosure.RDFS_Semantics(g, axioms=True, daxioms=False,
                                     rdfs=False).closure()

    statementset = create_statementset(g)
    sqlstatements = f'INSERT OR REPLACE INTO `{spec_name}` VALUES\n' + \
                    statementset
    statementset = f'INSERT INTO `{spec_name}` VALUES\n' + \
                   statementset
    statementsets.append(statementset)

    # Kafka topic object for RDF
    config = {}
    config['retention.ms'] = configs.rdf_retention_ms

    # populate sqlite file
    with open(os.path.join(output_folder, "rdf.sqlite"), "w") as fp:
        fp.write(utils.create_sql_table(spec_name, table, primary_key))
        fp.write('\n')
        fp.write(sqlstatements)

    with open(os.path.join(output_folder, "rdf.yaml"), "w") as fp:
        fp.write('---\n')
        yaml.dump(utils.create_yaml_table(table_name, connector, table,
                  primary_key, kafka, value), fp)
        fp.write("---\n")
        yaml.dump(utils.create_statementset('rdf-statements', [table_name],
                  [], statementsets), fp)
        fp.write("---\n")
        yaml.dump(utils.create_kafka_topic(utils.class_to_obj_name(
                                           configs.rdf_topic),
                                           configs.rdf_topic,
                                           configs.kafka_topic_object_label,
                                           config), fp)


if __name__ == '__main__':
    args = parse_args()
    knowledgefile = args.knowledgefile
    main(knowledgefile)
