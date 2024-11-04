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

import os.path
from unittest.mock import patch
import lib.utils as utils
import rdflib
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, XSD


def test_check_dns_name():
    result = utils.check_dns_name('name')
    assert result is True
    result = utils.check_dns_name('name_')
    assert result is False


def test_camelcase_to_sname_case():
    result = utils.camelcase_to_snake_case('CamelCase')
    assert result == 'camel_case'


@patch('lib.utils.camelcase_to_snake_case')
def test_class_to_obj_name(mock):
    mock.return_value = "snake_case"
    result = utils.class_to_obj_name('')
    assert result == "snake-case"


@patch('lib.utils.class_to_obj_name')
@patch('lib.utils.check_dns_name')
def test_create_yaml_table(mock_check, mock_class):
    mock_check.return_value = True
    mock_class.return_value = 'object'
    result = utils.create_yaml_table('name', 'connector', ['table'],
                                     'primary_key', 'kafka', 'value')
    assert result == {'apiVersion': 'industry-fusion.com/v1alpha2',
                      'kind': 'BeamSqlTable',
                      'metadata': {'name': 'object'},
                      'spec': {
                          'name': 'name',
                          'connector': 'connector',
                          'fields': ['table'],
                          'kafka': 'kafka',
                          'value': 'value',
                          'primaryKey': 'primary_key'
                      }}
    result = utils.create_yaml_table('name', 'connector', ['table'], None,
                                     'kafka', 'value')
    assert result == {'apiVersion': 'industry-fusion.com/v1alpha2',
                      'kind': 'BeamSqlTable',
                      'metadata': {'name': 'object'},
                      'spec': {
                          'name': 'name',
                          'connector': 'connector',
                          'fields': ['table'],
                          'kafka': 'kafka',
                          'value': 'value'
                      }}


@patch('lib.utils.class_to_obj_name')
@patch('lib.utils.check_dns_name')
def test_create_flink_debug_table(mock_check, mock_class):
    mock_check.return_value = True
    mock_class.return_value = 'object'
    result = utils.create_flink_debug_table('name', 'connector', [{'field': 'type'}, {'ts': 'TIMESTAMP METADATA'}],
                                            {'primary': 'key'}, {'topic': 'topic', 'properties': {'prop1': 'prop1'}},
                                            'value')
    assert result == "DROP TABLE IF EXISTS `name`;\nCREATE TABLE `name` (\n`field` type,\n`ts` TIMESTAMP(3) METADATA \
FROM 'timestamp', \nwatermark FOR `ts` AS `ts`,\nPRIMARY KEY(`primary`)\n) WITH (\n'format' = 'json',\n'connector' = \
'connector',\n'topic' = 'topic',\n'scan.startup.mode' = 'earliest-offset'\n,\n'properties.prop1' = 'prop1'\n);"

    result = utils.create_flink_debug_table('name', 'connector', [{'field': 'type'}, {'ts': 'TIMESTAMP METADATA'}],
                                            None, {'topic': 'topic', 'properties': {'prop1': 'prop1'}}, 'value')
    assert result == "DROP TABLE IF EXISTS `name`;\nCREATE TABLE `name` (\n`field` type,\n`ts` TIMESTAMP(3) METADATA \
FROM 'timestamp', \nwatermark FOR `ts` AS `ts`) WITH (\n'format' = 'json',\n'connector' = 'connector',\n'topic' = \
'topic',\n'scan.startup.mode' = 'earliest-offset'\n,\n'properties.prop1' = 'prop1'\n);"


@patch('lib.utils.class_to_obj_name')
@patch('lib.utils.check_dns_name')
def test_create_yaml_table_exception(mock_check, mock_class):
    mock_check.return_value = False
    mock_class.return_value = 'object'
    try:
        utils.create_yaml_table('name', 'connector', ['table'], 'primary_key',
                                'kafka', 'value')
        assert False
    except utils.DnsNameNotCompliant:
        assert True


def test_create_sql_table():
    result = utils.create_sql_table('name', [{'field': 'type'}], ['field'])
    assert result == 'DROP TABLE IF EXISTS `name`;\nCREATE TABLE `name` \
(\n`field` type,\nPRIMARY KEY(`field`)\n);\n'
    result = utils.create_sql_table('name', [{'field': 'type',
                                    'watermark': 'mark'}], None)
    assert result == 'DROP TABLE IF EXISTS `name`;\nCREATE TABLE `name` \
(\n`field` type);\n'
    result = utils.create_sql_table('name', [{'field': 'type', 'timestamp':
                                    'timestamp metadata'}], None,
                                    utils.SQL_DIALECT.SQLITE)
    assert result == 'DROP TABLE IF EXISTS `name`;\nCREATE TABLE `name` \
(\n`field` type,\n`timestamp` DEFAULT CURRENT_TIMESTAMP);\n'
    result = utils.create_sql_table('name', [{'field': 'type', 'timestamp':
                                    'timestamp metadata'}], None,
                                    utils.SQL_DIALECT.SQL)
    assert result == 'DROP TABLE IF EXISTS `name`;\nCREATE TABLE `name` \
(\n`field` type,\n`timestamp` TIMESTAMP(3));\n'


@patch('lib.utils.class_to_obj_name')
@patch('lib.utils.check_dns_name')
def test_create_yaml_view(mock_check, mock_class):
    mock_check.return_value = True
    mock_class.return_value = 'object'
    result = utils.create_yaml_view('name', [{'fieldname': 'type'}])
    assert result == {'apiVersion': 'industry-fusion.com/v1alpha1',
                      'kind': 'BeamSqlView',
                      'metadata': {'name': 'object-view'},
                      'spec': {
                          'name': 'name_view',
                          'sqlstatement': 'SELECT `id`, `type`,\n `fieldname` \
FROM (\n  SELECT *,\nROW_NUMBER() OVER (PARTITION BY `id`\nORDER BY ts DESC)\
 AS rownum\nFROM `name` )\nWHERE rownum = 1'
                      }}
    result = utils.create_yaml_view('name', [{'fieldname': 'type'}, ])
    assert result == {'apiVersion': 'industry-fusion.com/v1alpha1',
                      'kind': 'BeamSqlView',
                      'metadata': {'name': 'object-view'},
                      'spec': {
                          'name': 'name_view',
                          'sqlstatement': 'SELECT `id`, `type`,\n `fieldname` \
FROM (\n  SELECT *,\nROW_NUMBER() OVER (PARTITION BY `id`\nORDER BY ts DESC)\
 AS rownum\nFROM `name` )\nWHERE rownum = 1'
                      }}


def test_create_sql_view():
    result = utils.create_sql_view('table_name', [{'fieldname': 'type'}])
    assert result == 'DROP VIEW IF EXISTS `table_name_view`;\nCREATE VIEW \
`table_name_view` AS\nSELECT `id`,`type`,\n`fieldname` \
FROM (\n  SELECT *,\nROW_NUMBER() OVER (PARTITION BY `id`\nORDER BY ts DESC)\
 AS rownum\nFROM `table_name` )\nWHERE rownum = 1;\n'
    result = utils.create_sql_view('table_name', [{'fieldname': 'type'},
                                   {'id': 'id'}, {'type': 'type'}])
    assert result == 'DROP VIEW IF EXISTS `table_name_view`;\nCREATE VIEW \
`table_name_view` AS\nSELECT `id`,`type`,\n`fieldname` \
FROM (\n  SELECT *,\nROW_NUMBER() OVER (PARTITION BY `id`\nORDER BY ts DESC)\
 AS rownum\nFROM `table_name` )\nWHERE rownum = 1;\n'


def test_create_statementset():
    result = utils.create_statementset('object', 'table_object', 'view', None,
                                       'statementset')
    assert result == {
        'apiVersion': 'industry-fusion.com/v1alpha4',
        'kind': 'BeamSqlStatementSet',
        'metadata': {
            'name': 'object'
        },
        'spec': {
            'tables': 'table_object',
            'refreshInterval': "12h",
            'views': 'view',
            'sqlstatements': 'statementset',
            'updateStrategy': 'none'
        }
    }


def test_create_statementmap():
    result = utils.create_statementmap('object', 'table_object', 'view', None,
                                       ['namespace/configmap'])
    assert result == {
        'apiVersion': 'industry-fusion.com/v1alpha4',
        'kind': 'BeamSqlStatementSet',
        'metadata': {
            'name': 'object'
        },
        'spec': {
            'tables': 'table_object',
            'refreshInterval': '12h',
            'views': 'view',
            'sqlstatementmaps': ['namespace/configmap'],
            'updateStrategy': 'none'
        }
    }


def test_create_configmap():
    result = utils.create_configmap('object', ['statementset1', 'statementset2'])
    assert result == {
        'apiVersion': 'v1',
        'kind': 'ConfigMap',
        'metadata': {
            'name': 'object'
        },
        'data': {
            0: 'statementset1',
            1: 'statementset2'
        }
    }


def test_create_kafka_topic():
    result = utils.create_kafka_topic('name', 'topic_name', ['kafka_topic_object_label',
                                      'label'], 'config')
    assert result == {
        'apiVersion': 'kafka.strimzi.io/v1beta2',
        'kind': 'KafkaTopic',
        'metadata': {
            'name': 'name',
            'labels': {
                'kafka_topic_object_label': 'label'
            }
        },
        'spec': {
            'partitions': 1,
            'replicas': 1,
            'config': 'config',
            'topicName': 'topic_name'
        }
    }


def test_strip_class():
    result = utils.strip_class('https://testurl.com/path')
    assert result == 'path'
    result = utils.strip_class('https://testurl.com/path#realPath')
    assert result == 'realPath'


def test_create_output_folder(tmp_path):
    utils.create_output_folder(tmp_path)

    assert os.path.exists(tmp_path) is True
    try:
        utils.create_output_folder(tmp_path)
        assert True
    except FileExistsError:
        assert False


def test_wrap_ngsild_variable():
    ctx = {
        'bounds': {'var': 'TABLE.`id`'},
        'entity_variables': {},
        'time_variables': {},
        'property_variables': {rdflib.Variable('var'): True}
    }
    var = rdflib.Variable('var')
    bounds = utils.wrap_ngsild_variable(ctx, var)
    assert bounds == "'<' || TABLE.`id` || '>'"

    ctx = {
        'bounds': {'var': 'TABLE.`id`'},
        'entity_variables': {},
        'time_variables': {},
        'property_variables': {rdflib.Variable('var'): False}
    }
    var = rdflib.Variable('var')
    bounds = utils.wrap_ngsild_variable(ctx, var)
    assert bounds == '\'"\' || TABLE.`id` || \'"\''


def test_process_sql_dialect():
    expression = "SQL_DIALECT_STRIP_IRI{stripme}xxSQL_DIALECT_STRIP_LITERAL{literal}\
yySQL_DIALECT_TIME_TO_MILLISECONDS{time}\
zzSQL_DIALECT_CURRENT_TIMESTAMP, SQL_DIALECT_INSERT_ATTRIBUTES,SQL_DIALECT_SQLITE_TIMESTAMP, SQL_DIALECT_CAST"
    isSqlite = False
    result_expression = utils.process_sql_dialect(expression, isSqlite)
    assert result_expression == "REGEXP_REPLACE(CAST(stripme as STRING), '>|<', '')\
xxREGEXP_REPLACE(CAST(literal as STRING), '\\\"', '')\
yy1000 * UNIX_TIMESTAMP(TRY_CAST(time AS STRING)) + EXTRACT(MILLISECOND FROM TRY_CAST(time as TIMESTAMP))\
zzCURRENT_TIMESTAMP, INSERT into attributes_insert, TRY_CAST"

    isSqlite = True
    result_expression = utils.process_sql_dialect(expression, isSqlite)
    assert result_expression == 'ltrim(rtrim(stripme, \'>\'), \'<\')xxtrim(literal, \'\\"\')yyCAST(julianday(time) \
* 86400000 as INTEGER)zzdatetime(), INSERT OR REPLACE INTO attributes_insert_filter,CURRENT_TIMESTAMP, CAST'

    # Check recursive strutures

    isSqlite = False
    expression = "SQL_DIALECT_STRIP_IRI{SQL_DIALECT_STRIP_IRI{SQL_DIALECT_STRIP_IRI{stripme}}}"
    result_expression = utils.process_sql_dialect(expression, isSqlite)
    assert result_expression == "REGEXP_REPLACE(CAST(REGEXP_REPLACE(CAST(REGEXP_REPLACE(CAST(stripme as STRING), \
'>|<', '') as STRING), '>|<', '') as STRING), '>|<', '')"

    isSqlite = True
    result_expression = utils.process_sql_dialect(expression, isSqlite)
    assert result_expression == "ltrim(rtrim(ltrim(rtrim(ltrim(rtrim(stripme, '>'), '<'), '>'), '<'), '>'), '<')"

    isSqlite = False
    expression = "SQL_DIALECT_STRIP_LITERAL{SQL_DIALECT_TIME_TO_MILLISECONDS{SQL_DIALECT_STRIP_IRI{test}}}"
    result_expression = utils.process_sql_dialect(expression, isSqlite)
    assert result_expression == 'REGEXP_REPLACE(CAST(1000 * UNIX_TIMESTAMP(TRY_CAST(REGEXP_REPLACE(CAST(test \
as STRING), \'>|<\', \'\') AS STRING)) + EXTRACT(MILLISECOND FROM TRY_CAST(REGEXP_REPLACE(CAST(test as STRING), \
\'>|<\', \'\') as TIMESTAMP)) as STRING), \'\\"\', \'\')'

    isSqlite = True
    result_expression = utils.process_sql_dialect(expression, isSqlite)
    assert result_expression == 'trim(CAST(julianday(ltrim(rtrim(test, \'>\'), \'<\')) * 86400000 as INTEGER), \'\\"\')'


def test_transitive_closure():
    # Define a custom namespace for testing
    TEST = Namespace("http://example.org/test#")

    # Create an RDF graph for testing
    g = Graph()
    g.bind("test", TEST)

    # Add some initial triples
    g.add((TEST.A, RDF.type, RDFS.Class))
    g.add((TEST.B, RDF.type, RDFS.Class))
    g.add((TEST.A, RDFS.subClassOf, TEST.B))

    g.add((TEST.C, RDF.type, OWL.Class))
    g.add((TEST.C, RDFS.subClassOf, TEST.A))

    # Add a transitive property
    g.add((TEST.transitiveProp, RDF.type, OWL.TransitiveProperty))
    g.add((TEST.X, TEST.transitiveProp, TEST.Y))
    g.add((TEST.Y, TEST.transitiveProp, TEST.Z))

    # Add a container type
    g.add((TEST.container, RDF.type, RDF.Bag))
    g.add((TEST.container, RDF._1, Literal("value1")))
    g.add((TEST.container, RDF._2, Literal("value2")))

    # Apply the transitive_closure function to the graph
    closure_graph = utils.transitive_closure(g)
    for s, p, o in closure_graph:
        print((s, p, o))
    # Check if the reflexive relationships are added
    assert (TEST.A, RDFS.subClassOf, TEST.A) in closure_graph
    assert (TEST.B, RDFS.subClassOf, TEST.B) in closure_graph
    assert (TEST.C, RDFS.subClassOf, TEST.C) in closure_graph

    # Check if the transitive relationships are added
    assert (TEST.A, RDFS.subClassOf, TEST.B) in closure_graph
    assert (TEST.C, RDFS.subClassOf, TEST.B) in closure_graph

    # Check transitive property propagation
    assert (TEST.X, TEST.transitiveProp, TEST.Z) in closure_graph

    # Check container relationships
    assert (TEST.container, RDF.type, RDFS.Container) in closure_graph
    assert (TEST.container, RDFS.member, Literal("value1", datatype=XSD.string)) in closure_graph
    assert (TEST.container, RDFS.member, Literal("value2", datatype=XSD.string)) in closure_graph
