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
import lib.utils as utils
from lib.shacl_properties_to_sql import translate as translate_properties
from lib.shacl_sparql_to_sql import translate as translate_sparql
from lib.shacl_construct_to_sql import translate as translate_construct
import ruamel.yaml
import rdflib
import argparse

commonyamlfile = '../../helm/common.yaml'


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='\
create_sql_checks_from_shacl.py <shacl.ttl> <knowledge.ttl>')

    parser.add_argument('shaclfile', help='Path to the SHACL file')
    parser.add_argument('knowledgefile', help='Path to the knowledge file')
    parser.add_argument('-c', '--context', help='Context URI. If not given it is derived implicitly \
from the common helmfile configs.')
    parsed_args = parser.parse_args(args)
    return parsed_args


def main(shaclfile, knowledgefile, context, output_folder='output'):
    # If no context is defined, try to derive it from common.yaml
    prefixes = {}
    if context is None:
        commonyaml = ruamel.yaml.YAML()
        try:
            with open(commonyamlfile, "r") as file:
                yaml_dict = commonyaml.load(file)
                context = yaml_dict['ontology']['baseUri'] + 'context.jsonld'
        except:
            print("Could neither derive context file implicitly, nor by commandline. Check if common.yaml \
is accessible.")
            exit(1)
    try:
        context_graph = rdflib.Graph()
        context_graph.parse(context, format="json-ld")
        for prefix, namespace in context_graph.namespaces():
            prefixes[prefix] = rdflib.Namespace(namespace)
    except:
        print(f"Could not derive prefixes from context file. Check if contextfile {context} is valid and accessible.")
        exit(1)
    if 'base' not in prefixes.keys():
        print(f"No prefix 'base:' is found in your given context {context}. This is needed!")
        exit(1)
    utils.create_output_folder(output_folder)

    yaml = ruamel.yaml.YAML()

    sqlite3, (statementsets3, tables3, views3) = \
        translate_construct(shaclfile, knowledgefile)

    sqlite, (statementsets, tables, views) = \
        translate_properties(shaclfile, knowledgefile, prefixes)

    sqlite2, (statementsets2, tables2, views2) = \
        translate_sparql(shaclfile, knowledgefile, prefixes)

    tables = list(set(tables2).union(set(tables)).union(set(tables3)))  # deduplication
    views = list(set(views2).union(set(views)).union(set(views3)))  # deduplication

    ttl = '{{.Values.flink.ttl}}'
    with open(os.path.join(output_folder, "shacl-validation.yaml"), "w") as f:
        yaml.dump(utils.create_statementset('shacl-validation', tables, views, ttl,
                                            statementsets + statementsets2 + statementsets3), f)
    with open(os.path.join(output_folder, "shacl-validation.sqlite"), "w") \
            as sqlitef:
        print(sqlite + sqlite2 + sqlite3, file=sqlitef)


if __name__ == '__main__':
    args = parse_args()
    shaclfile = args.shaclfile
    knowledgefile = args.knowledgefile
    context = args.context
    main(shaclfile, knowledgefile, context)
