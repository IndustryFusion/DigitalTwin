#
# Copyright (c) 2024 Intel Corporation
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

import sys
import rdflib
import owlrl
import argparse


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='Evalutate sparql expression on knowledge/shacl/entiy files.')
    parser.add_argument('queryfile', help='Path to a file which contains a SPARQL query')
    parser.add_argument('shaclfile', help='Path to the SHACL file')
    parser.add_argument('knowledgefile', help='Path to the knowledge file')
    parser.add_argument('-e', '--entities', help='Path to the jsonld model/entity file')
    parsed_args = parser.parse_args(args)
    return parsed_args


def main(queryfile, shaclfile, knowledgefile, entityfile, output_folder='output'):

    with open(queryfile, "r") as f:
        query = f.read()

    g = rdflib.Graph()
    g.parse(shaclfile)
    h = rdflib.Graph()
    h.parse(knowledgefile)
    owlrl.DeductiveClosure(owlrl.OWLRL_Extension, rdfs_closure=True,
                           axiomatic_triples=True, datatype_axioms=True).expand(h)
    if entityfile is not None:
        i = rdflib.Graph()
        i.parse(entityfile)
        g += i
    g += h

    qres = g.query(query)
    for row in qres:
        print(f'{row}')


if __name__ == '__main__':
    args = parse_args()
    queryfile = args.queryfile
    shaclfile = args.shaclfile
    knowledgefile = args.knowledgefile
    entityfile = args.entities
    main(queryfile, shaclfile, knowledgefile, entityfile)
