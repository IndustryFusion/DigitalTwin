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
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, XSD, BNode


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
                          'sqlstatement': 'SELECT `type`,\
\n `fieldname` FROM (\
\n  SELECT *,\
\nROW_NUMBER() OVER (PARTITION BY \
\nORDER BY ts DESC) AS rownum\nFROM `name` )\
\nWHERE rownum = 1'
                      }}
    result = utils.create_yaml_view('name', [{'fieldname': 'type'}, ])
    assert result == {'apiVersion': 'industry-fusion.com/v1alpha1',
                      'kind': 'BeamSqlView',
                      'metadata': {'name': 'object-view'},
                      'spec': {
                          'name': 'name_view',
                          'sqlstatement': 'SELECT `type`,\
\n `fieldname` FROM (\
\n  SELECT *,\
\nROW_NUMBER() OVER (PARTITION BY \
\nORDER BY ts DESC) AS rownum\
\nFROM `name` )\
\nWHERE rownum = 1'
                      }}


def test_create_sql_view():
    result = utils.create_sql_view('table_name', [{'fieldname': 'type'}])
    assert result == 'DROP VIEW IF EXISTS `table_name_view`;\
\nCREATE VIEW `table_name_view` AS\
\nSELECT `type`,\
\n`fieldname` FROM (\
\n  SELECT *,\
\nROW_NUMBER() OVER (PARTITION BY \
\nORDER BY ts DESC) AS rownum\
\nFROM `table_name` )\
\nWHERE rownum = 1;\n'

    result = utils.create_sql_view('table_name', [{'fieldname': 'type'},
                                   {'id': 'id'}, {'type': 'type'}])
    assert result == 'DROP VIEW IF EXISTS `table_name_view`;\
\nCREATE VIEW `table_name_view` AS\
\nSELECT `type`,\
\n`fieldname`,\
\n`id` FROM (\
\n  SELECT *,\
\nROW_NUMBER() OVER (PARTITION BY \
\nORDER BY ts DESC) AS rownum\
\nFROM `table_name` )\
\nWHERE rownum = 1;\n'


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
            'sqlsettings': [
                {"table.exec.sink.upsert-materialize": "none"},
                {"execution.savepoint.ignore-unclaimed-state": "true"},
                {"pipeline.object-reuse": "true"},
                {"parallelism.default": "{{ .Values.flink.defaultParalellism }}"},
                {"state.backend.rocksdb.writebuffer.size": "64 kb"},
                {"state.backend.rocksdb.use-bloom-filter": "true"},
                {"state.backend": "rocksdb"},
                {"state.backend.rocksdb.predefined-options": "SPINNING_DISK_OPTIMIZED_HIGH_MEM"}
            ],
            'sqlstatementmaps': ['namespace/configmap'],
            'updateStrategy': 'none'
        }
    }

    result = utils.create_statementmap('object', 'table_object', 'view', 'ttl',
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
            'sqlsettings': [
                {"table.exec.sink.upsert-materialize": "none"},
                {"execution.savepoint.ignore-unclaimed-state": "true"},
                {"pipeline.object-reuse": "true"},
                {"parallelism.default": "{{ .Values.flink.defaultParalellism }}"},
                {"state.backend.rocksdb.writebuffer.size": "64 kb"},
                {"state.backend.rocksdb.use-bloom-filter": "true"},
                {"state.backend": "rocksdb"},
                {"state.backend.rocksdb.predefined-options": "SPINNING_DISK_OPTIMIZED_HIGH_MEM"},
                {"table.exec.state.ttl": 'ttl'}
            ],
            'sqlstatementmaps': ['namespace/configmap'],
            'updateStrategy': 'none'
        }
    }

    result = utils.create_statementmap('object', 'table_object', 'view', None,
                                       ['namespace/configmap'], enable_checkpointing=True)

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
            'sqlsettings': [
                {"table.exec.sink.upsert-materialize": "none"},
                {"execution.savepoint.ignore-unclaimed-state": "true"},
                {"pipeline.object-reuse": "true"},
                {"parallelism.default": "{{ .Values.flink.defaultParalellism }}"},
                {"state.backend.rocksdb.writebuffer.size": "64 kb"},
                {"state.backend.rocksdb.use-bloom-filter": "true"},
                {"state.backend": "rocksdb"},
                {"state.backend.rocksdb.predefined-options": "SPINNING_DISK_OPTIMIZED_HIGH_MEM"},
                {"execution.checkpointing.interval": "{{ .Values.flink.checkpointInterval }}"}
            ],
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


def test_rdf_list_to_pylist():
    # Define a custom namespace for testing
    TEST = Namespace("http://example.org/test#")

    # Create an RDF graph for testing
    g = Graph()
    g.bind("test", TEST)

    # Test empty list
    empty_list = BNode()
    g.add((empty_list, RDF.first, RDF.nil))
    result = utils.rdf_list_to_pylist(g, RDF.nil)
    assert result == []

    # Test flat list
    flat_list = BNode()
    g.add((flat_list, RDF.first, Literal("item1")))
    g.add((flat_list, RDF.rest, BNode()))
    g.add((flat_list, RDF.rest, RDF.nil))
    result = utils.rdf_list_to_pylist(g, flat_list)
    assert result == ["item1"]

    # Test nested list
    nested_list = BNode()
    inner_list = BNode()
    g.add((nested_list, RDF.first, inner_list))
    g.add((nested_list, RDF.rest, RDF.nil))
    g.add((inner_list, RDF.first, Literal("nested_item")))
    g.add((inner_list, RDF.rest, RDF.nil))
    result = utils.rdf_list_to_pylist(g, nested_list)
    assert result == [["nested_item"]]

    # Test list with URIRef
    uri_list = BNode()
    g.add((uri_list, RDF.first, TEST.item))
    g.add((uri_list, RDF.rest, RDF.nil))
    result = utils.rdf_list_to_pylist(g, uri_list)
    assert result == [str(TEST.item)]

    # Test invalid head type
    result = utils.rdf_list_to_pylist(g, Literal("invalid"))
    assert result == Literal("invalid")


def test_split_statementsets():
    # Test case 1: Simple split
    statementsets = ["short", "mediumlength", "longstatement"]
    max_map_size = 10
    result = utils.split_statementsets(statementsets, max_map_size)
    assert result == [["short"], ["mediumlength"], ["longstatement"]]

    # Test case 2: Grouping strings
    statementsets = ["short", "medium", "long"]
    max_map_size = 14
    result = utils.split_statementsets(statementsets, max_map_size)
    assert result == [["short", "medium"], ["long"]]

    # Test case 3: All strings fit in one group
    statementsets = ["short", "medium", "long"]
    max_map_size = 50
    result = utils.split_statementsets(statementsets, max_map_size)
    assert result == [["short", "medium", "long"]]

    # Test case 4: Empty input
    statementsets = []
    max_map_size = 10
    result = utils.split_statementsets(statementsets, max_map_size)
    assert result == []

    # Test case 5: Single string larger than max_map_size
    statementsets = ["verylongstatement"]
    max_map_size = 10
    result = utils.split_statementsets(statementsets, max_map_size)
    assert result == [["verylongstatement"]]

    # Test case 6: Strings with exact fit
    statementsets = ["short", "medium"]
    max_map_size = len("short") + len("medium")
    result = utils.split_statementsets(statementsets, max_map_size)
    assert result == [["short", "medium"]]


def test_add_table_values():
    # Test case 1: Basic SQL dialect (SQLITE)
    values = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    table = [{"id": "INTEGER"}, {"name": "STRING"}]
    sqldialect = utils.SQL_DIALECT.SQLITE
    table_name = "test_table"
    result = utils.add_table_values(values, table, sqldialect, table_name)
    expected = [
        "INSERT OR REPLACE INTO test_table VALUES"
        "(1,'Alice'),"
        " (2,'Bob');"
    ]
    assert result == expected

    # Test case 2: Basic SQL dialect (SQL)
    sqldialect = utils.SQL_DIALECT.SQL
    result = utils.add_table_values(values, table, sqldialect, table_name)
    expected = [
        "INSERT INTO test_table VALUES"
        "(1,'Alice'),"
        " (2,'Bob');"
    ]
    assert result == expected

    # Test case 3: Null values
    values = [{"id": None, "name": "Alice"}, {"id": 2, "name": None}]
    result = utils.add_table_values(values, table, sqldialect, table_name)
    expected = [
        "INSERT INTO test_table VALUES"
        "(CAST (NULL as INTEGER),'Alice'),"
        " (2,CAST (NULL as STRING));"
    ]
    assert result == expected

    # Test case 4: Empty values
    values = []
    result = utils.add_table_values(values, table, sqldialect, table_name)
    expected = []
    assert result == expected


def test_get_full_path_of_shacl_property():
    """Test get_full_path_of_shacl_property function"""
    from rdflib import Graph, Namespace
    from rdflib.namespace import SH
    
    g = Graph()
    TEST = Namespace("http://example.org/test#")
    
    # Test with property that has no path
    prop1 = TEST.property1
    result = utils.get_full_path_of_shacl_property(g, prop1)
    assert result == []
    
    # Test with property that has a path
    prop2 = TEST.property2
    path2 = TEST.path2
    g.add((prop2, SH.path, path2))
    result = utils.get_full_path_of_shacl_property(g, prop2)
    assert result == [path2]


def test_get_group_by_vars():
    """Test get_group_by_vars function"""
    # Test with no group_by_vars
    ctx = {}
    result = utils.get_group_by_vars(ctx)
    assert result is None
    
    # Test with group_by_vars
    ctx['group_by_vars'] = ['var1']
    result = utils.get_group_by_vars(ctx)
    assert result == ['var1']


def test_set_group_by_vars():
    """Test set_group_by_vars function"""
    import rdflib
    
    # Test setting first variable
    ctx = {}
    var1 = rdflib.Variable('var1')
    utils.set_group_by_vars(ctx, [var1])
    assert 'group_by_vars' in ctx
    assert len(ctx['group_by_vars']) == 1
    
    # Test adding to existing group_by_vars
    var2 = rdflib.Variable('var2')
    utils.set_group_by_vars(ctx, [var2])
    assert len(ctx['group_by_vars']) == 2
