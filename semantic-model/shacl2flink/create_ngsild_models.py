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

from rdflib import Graph, URIRef
import os
import sys
import argparse
import lib.utils as utils
import lib.configs as configs
import owlrl


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='create_ngsild_models.py \
                                                  <shacl.ttl> <knowledge.ttl> \
                                                  <model.jsonld>')

    parser.add_argument('shaclfile', help='Path to the SHACL file')
    parser.add_argument('knowledgefile', help='Path to the knowledge file')
    parser.add_argument('modelfile', help='Path to the model file')
    parsed_args = parser.parse_args(args)
    return parsed_args


attributes_query = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
PREFIX sh: <http://www.w3.org/ns/shacl#>
SELECT DISTINCT (?a as ?entityId) (?b as ?name) (?e as ?type) (IF(bound(?g), IF(isIRI(?g), '@id', '@value'), IF(isIRI(?f), '@id', '@value')) as ?nodeType)
(datatype(?g) as ?valueType) (?f as ?hasValue) (?g as ?hasObject) ?observedAt ?index
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?class .
    ?nodeshape sh:property [ sh:path ?b ] .
    ?a a ?subclass .
    ?subclass rdfs:subClassOf* ?class .
    FILTER NOT EXISTS {
        ?class rdfs:subClassOf+ ?further .
        ?subnodeshape sh:targetClass ?further .
        ?subnodeshape sh:property [ sh:path ?b ] .
    } .
    {?a ?b [ ngsild:hasObject ?g ] .
    VALUES ?e {ngsild:Relationship} .
    OPTIONAl{?a ?b [ ngsild:observedAt ?observedAt; ngsild:hasObject ?g  ] .} .
    OPTIONAl{?a ?b [ ngsild:datasetId ?index; ngsild:hasObject ?g  ] .} .
    }
    UNION
    { ?a ?b [ ngsild:hasValue ?f ] .
    VALUES ?d {'@value'} .
    VALUES ?e {ngsild:Property}
    FILTER(!isIRI(?f))
    ?nodeshape sh:property [ sh:path ?b ] .
    OPTIONAl{?a ?b [ ngsild:observedAt ?observedAt; ngsild:hasValue ?f ] .} .
    OPTIONAl{?a ?b [ ngsild:datasetId ?index; ngsild:hasValue ?f ] .} .
    }
    UNION
    { ?a ?b [ ngsild:hasValue ?f ] .
    VALUES ?d {'@id'} .
    VALUES ?e {ngsild:Property}
    FILTER(isIRI(?f))
    OPTIONAl{?a ?b [ ngsild:observedAt ?observedAt;ngsild:hasValue ?f  ] .} .
    OPTIONAl{?a ?b [ ngsild:datasetId ?index;ngsild:hasValue ?f  ] .} .
    }
}
order by ?observedAt
"""  # noqa: E501

ngsild_tables_query_noinference = """
PREFIX iff: <https://industry-fusion.com/types/v0.9/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>

SELECT DISTINCT ?id ?type ?field ?tabletype
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?basetype .
    ?id a ?type .
    ?type rdfs:subClassOf* ?basetype .
    ?tabletype rdfs:subClassOf* ?basetype .
    ?type rdfs:subClassOf* ?tabletype .
    ?nodeshape sh:property [ sh:path ?field ;] .
    FILTER(?tabletype != rdfs:Resource && ?tabletype != owl:Thing && ?tabletype != owl:Nothing )
    }
    ORDER BY ?id STR(?field)
"""


def nullify(field):
    if field is None:
        field = 'NULL'
    else:
        field = "'" + str(field.toPython()) + "'"
    return field


def main(shaclfile, knowledgefile, modelfile, output_folder='output'):
    utils.create_output_folder(output_folder)
    with open(os.path.join(output_folder, "ngsild-models.sqlite"), "w")\
            as sqlitef:
        g = Graph()
        g.parse(shaclfile)
        model = Graph()
        model.parse(modelfile)
        knowledge = Graph()
        knowledge.parse(knowledgefile)
        attributes_model = model + g + knowledge

        qres = attributes_model.query(attributes_query)
        first = True
        if len(qres) > 0:
            print(f'INSERT INTO `{configs.attributes_table_name}` VALUES',
                  file=sqlitef)
        for entityId, name, type, nodeType, valueType, hasValue, \
                hasObject, observedAt, index in qres:
            id = entityId.toPython() + "\\\\" + name.toPython()
            current_index = None
            if index is None:
                current_index = 0
            else:
                current_index = index
                if isinstance(index, URIRef):
                    try:
                        current_index = int(utils.strip_class(current_index.toPython()))
                    except:
                        current_index = 0
            valueType = nullify(valueType)
            hasValue = nullify(hasValue)
            hasObject = nullify(hasObject)
            if "string" in valueType:
                valueType = 'NULL'
            if first:
                first = False
            else:
                print(',', file=sqlitef)
            current_timestamp = "CURRENT_TIMESTAMP"
            if observedAt is not None:
                current_timestamp = f"'{str(observedAt)}'"
            print("('" + id + "', '" + entityId.toPython() + "', '" +
                  name.toPython() +
                  "', '" + nodeType + "', " + valueType + ", " +
                  str(current_index) +
                  ", '" + type.toPython() + "', 'http://example.com/index/" + str(current_index) +
                  "'," + hasValue + ", " +
                  hasObject + ", " + current_timestamp + ")", end='',
                  file=sqlitef)
        print(";", file=sqlitef)

        # Create ngsild tables by sparql
        owlrl.DeductiveClosure(owlrl.OWLRL_Extension, rdfs_closure=True, axiomatic_triples=True,
                               datatype_axioms=True).expand(knowledge)
        table_model = model + knowledge + g
        qres = table_model.query(ngsild_tables_query_noinference)
        tables = {}

        # Now create the entity tables
        for id, type, field, tabletype in qres:
            key = utils.camelcase_to_snake_case(utils.strip_class(tabletype.toPython()))
            if key not in tables:
                table = {}

                tables[key] = table
            idstr = id.toPython()
            if idstr not in tables[key]:
                tables[key][idstr] = []
                tables[key][idstr].append(idstr)
                tables[key][idstr].append(type.toPython())
                tables[key][idstr].append('CURRENT_TIMESTAMP')
            tables[key][idstr].append(idstr + "\\\\" +
                                      field.toPython())
        for type, ids in tables.items():
            for id, table in ids.items():
                print(f'INSERT INTO `{type}` VALUES',
                      file=sqlitef)
                first = True
                print("(", end='', file=sqlitef)
                for field in table:
                    if first:
                        first = False
                    else:
                        print(", ", end='', file=sqlitef)
                    if isinstance(field, str) and not field ==\
                            'CURRENT_TIMESTAMP':
                        print("'" + field + "'", end='', file=sqlitef)
                    else:
                        print(field, end='', file=sqlitef)
                print(");", file=sqlitef)


if __name__ == '__main__':
    args = parse_args()
    shaclfile = args.shaclfile
    knowledgefile = args.knowledgefile
    modelfile = args.modelfile
    main(shaclfile, knowledgefile, modelfile)
