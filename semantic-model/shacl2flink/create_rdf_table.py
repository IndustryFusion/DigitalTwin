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
    parser = argparse.ArgumentParser(description='create_rdf_table.py --namespace <ns>\
                                                  <knowledge.ttl>')
    parser.add_argument('knowledgefile', help='Path to the knowledge file')
    parser.add_argument('--namespace', help='namespace for configmaps', default='iff')
    parsed_args = parser.parse_args(args)
    return parsed_args


def create_table(sqldialect=utils.SQL_DIALECT.SQL):
    table = []
    if sqldialect in [utils.SQL_DIALECT.SQL, utils.SQL_DIALECT.SQLITE]:
        table.append({"subject": "STRING"})
        table.append({"predicate": "STRING"})
        table.append({"object": "STRING"})
        table.append({"index": "INTEGER"})
    elif sqldialect == utils.SQL_DIALECT.POSTGRES:
        table.append({"subject": "TEXT"})
        table.append({"predicate": "TEXT"})
        table.append({"object": "TEXT"})
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
    connector = 'postgres-cdc'
    cdc = {
        'hostname': '{{.Values.clusterSvcName}}',
        'port': '{{.Values.db.svcPort}}',
        'username': '{{ .Values.flink.db.replicationUser }}',
        'password': '{{ (dig "data" "password" "" $sec | b64dec | default "PLACEHOLDER") }}',
        'database-name': '{{.Values.flink.db.name}}',
        'schema-name': '{{.Values.flink.db.schema}}',
        'table-name': 'rdf',
        'slot.name': '{{.Values.flink.db.rdfSlotName}}',
        'debezium.database.sslmode': 'require'
    }
    primary_key = ['subject', 'predicate', 'index']

    # Create RDF statements to insert data
    g = rdflib.Graph(store="Oxigraph")
    g.parse(knowledgefile)
    g = utils.transitive_closure(g)
    statementsets = create_statementset(g)
    sqlitestatements = ''
    common_data = utils.get_common_data()
    postgresstatements = ''
    postgress_repl_access = grant_reader_access.replace("{{ flink_writer_user }}",
                                                        common_data['flink']['db']['writeUser']) \
        .replace("{{ flink_reader_user }}", common_data['flink']['db']['replicationUser']) + '\n'
    for statementset in statementsets:
        sqlitestatements += f'INSERT OR REPLACE INTO `{spec_name}` VALUES\n' + \
            statementset
        postgresstatements += f'INSERT INTO "{spec_name}" VALUES\n' + \
            statementset
    sqlstatementsets = list(map(lambda statementset: f'INSERT INTO `{spec_name}` VALUES\n' +
                            statementset, statementsets))

    # Kafka topic object for RDF
    config = {}
    config['retention.ms'] = configs.rdf_retention_ms

    # populate sqlite file
    with open(os.path.join(output_folder, "rdf.sqlite"), "w") as fp:
        fp.write(utils.create_sql_table(spec_name, table, primary_key))
        fp.write('\n')
        fp.write(sqlitestatements)

    # populate postgres file
    with open(os.path.join(output_folder, "rdf.postgres"), "w") as fp:
        postgres_table = create_table(utils.SQL_DIALECT.POSTGRES)
        fp.write(postgress_repl_access)
        fp.write('\n')
        fp.write(utils.create_sql_table(spec_name, postgres_table, primary_key, dialect=utils.SQL_DIALECT.POSTGRES))
        fp.write('\n')
        fp.write(postgresstatements)

    with open(os.path.join(output_folder, "rdf.yaml"), "w") as fp, \
            open(os.path.join(output_folder, "rdf-table.yaml"), "w") as ft, \
            open(os.path.join(output_folder, "rdf-kafka.yaml"), "w") as fk, \
            open(os.path.join(output_folder, "rdf-maps.yaml"), "w") as fm:
        ft.write('---\n')
        yamltable = utils.create_yaml_table_cdc(table_name, connector, table,
                                                primary_key, cdc)
        ft.write(golang_function)
        yaml.dump(yamltable, ft)
        num = 0
        statementmap = []
        for statementset in sqlstatementsets:
            num += 1
            fm.write("---\n")
            configmapname = 'rdf-configmap' + str(num)
            yaml.dump(utils.create_configmap(configmapname, [statementset], {'shacl-data': 'rdf-configmap'}), fm)
            statementmap.append(f'{namespace}/{configmapname}')
        fp.write("---\n")
        yaml.dump(utils.create_statementmap('rdf-statements', [table_name],
                                            [], None, statementmap, use_rocksdb=False), fp)
        fk.write("---\n")
        yaml.dump(utils.create_kafka_topic(utils.class_to_obj_name(configs.rdf_topic),
                                           configs.rdf_topic,
                                           configs.kafka_topic_object_label,
                                           config), fk)


if __name__ == '__main__':
    args = parse_args()
    knowledgefile = args.knowledgefile
    namespace = args.namespace
    main(knowledgefile, namespace)
