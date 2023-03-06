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
    result = utils.create_statementset('object', 'table_object', 'view',
                                       'statementset')
    assert result == {
        'apiVersion': 'industry-fusion.com/v1alpha2',
        'kind': 'BeamSqlStatementSet',
        'metadata': {
            'name': 'object'
        },
        'spec': {
            'tables': 'table_object',
            'views': 'view',
            'sqlstatements': 'statementset'
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
        'property_variables': {rdflib.Variable('var'): True}
    }
    var = rdflib.Variable('var')
    bounds = utils.wrap_ngsild_variable(ctx, var)
    assert bounds == "'<' || TABLE.`id` || '>'"

    ctx = {
        'bounds': {'var': 'TABLE.`id`'},
        'entity_variables': {},
        'property_variables': {rdflib.Variable('var'): False}
    }
    var = rdflib.Variable('var')
    bounds = utils.wrap_ngsild_variable(ctx, var)
    assert bounds == '\'"\' || TABLE.`id` || \'"\''
