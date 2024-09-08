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
import math
import hashlib
import owlrl
import ruamel.yaml
import rdflib
from lib import utils
from lib import configs


filter_out = """
PREFIX iff: <https://industry-fusion.com/types/v0.9/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>

CONSTRUCT {?s ?p ?o}
where {
    ?s ?p ?o .
    FILTER((?o = rdfs:Class || ?p = rdfs:subClassOf)
    && ?o != rdfs:Resource
    && ?o != rdfs:Thing
    && ?o != owl:Thing
    && ?o != owl:Class)
}
"""


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='create_rdf_table.py --namespace <ns>\
                                                  <knowledge.ttl>')
    parser.add_argument('knowledgefile', help='Path to the knowledge file')
    parser.add_argument('--namespace', help='namespace for configmaps', default='iff')
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
    statementsets = []
    max_per_set = configs.rdf_max_per_set
    num_sets = math.ceil(len(graph) / max_per_set)
    for num in range(num_sets):
        statementsets.append('')
    hash_counter = {}
    num = 0
    for s, p, o in graph.triples((None, None, None)):
        if isinstance(s, rdflib.Literal):
            continue
        index = math.floor(num / max_per_set)
        hash_object = hashlib.sha256(f'{s}{p}'.encode('utf-8'))
        hex_dig = hash_object.hexdigest()
        if hex_dig not in hash_counter:
            hash_counter[hex_dig] = 0
        else:
            hash_counter[hex_dig] += 1
        if not (num / max_per_set).is_integer():
            statementsets[index] += ",\n"
        else:
            pass
        statementsets[index] += "(" + utils.format_node_type(s) + ", " + utils.format_node_type(p) + \
                                ", " + utils.format_node_type(o) + ", " + str(hash_counter[hex_dig]) + ")"
        num += 1
    for num in range(num_sets):
        if statementsets[num] != '':
            statementsets[num] += ";"
        else:
            # Why is this needed? Looks like RDFS-Closure creates Literal subjects
            # which are filtered out by the continue above. This can lead to mismatch between
            # calculated sets and real-sets.
            del statementsets[num]
    return statementsets


def main(knowledgefile, namespace, output_folder='output'):
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
    g = rdflib.Graph()
    g.parse(knowledgefile)
    owlrl.DeductiveClosure(owlrl.OWLRL_Extension, rdfs_closure=True, axiomatic_triples=True,
                           datatype_axioms=True).expand(g)

    statementsets = create_statementset(g)
    sqlstatements = ''
    for statementset in statementsets:
        sqlstatements += f'INSERT OR REPLACE INTO `{spec_name}` VALUES\n' + \
                         statementset
    statementsets = list(map(lambda statementset: f'INSERT INTO `{spec_name}` VALUES\n' +
                             statementset, statementsets))

    # Kafka topic object for RDF
    config = {}
    config['retention.ms'] = configs.rdf_retention_ms

    # populate sqlite file
    with open(os.path.join(output_folder, "rdf.sqlite"), "w") as fp:
        fp.write(utils.create_sql_table(spec_name, table, primary_key))
        fp.write('\n')
        fp.write(sqlstatements)

    with open(os.path.join(output_folder, "rdf.yaml"), "w") as fp, \
            open(os.path.join(output_folder, "rdf-kafka.yaml"), "w") as fk, \
            open(os.path.join(output_folder, "rdf-maps.yaml"), "w") as fm:
        fp.write('---\n')
        yaml.dump(utils.create_yaml_table(table_name, connector, table,
                  primary_key, kafka, value), fp)
        num = 0
        statementmap = []
        for statementset in statementsets:
            num += 1
            fm.write("---\n")
            configmapname = 'rdf-configmap' + str(num)
            yaml.dump(utils.create_configmap(configmapname, [statementset]), fm)
            statementmap.append(f'{namespace}/{configmapname}')
        fp.write("---\n")
        yaml.dump(utils.create_statementmap('rdf-statements', [table_name],
                                            [], None, statementmap), fp)
        fk.write("---\n")
        yaml.dump(utils.create_kafka_topic(utils.class_to_obj_name(configs.rdf_topic),
                                           configs.rdf_topic,
                                           configs.kafka_topic_object_label,
                                           config), fk)
    with open(os.path.join(output_folder, "knowledge-configmap.yaml"), "w") as fp:
        qres = g.query(filter_out)
        class_ttl = {}
        class_ttl['knowledge.ttl'] = qres.serialize(format='turtle').decode("utf-8")
        fp.write("---\n")
        yaml.dump(utils.create_configmap_generic('knowledge', class_ttl), fp)


if __name__ == '__main__':
    args = parse_args()
    knowledgefile = args.knowledgefile
    namespace = args.namespace
    main(knowledgefile, namespace)
