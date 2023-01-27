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
import re
from urllib.parse import urlparse
from enum import Enum


class SQL_DIALECT(Enum):
    SQL = 0
    SQLITE = 1


class DnsNameNotCompliant(Exception):
    """
    Exception for non compliant DNS name
    """


def check_dns_name(name):
    regex = re.compile('^(?![0-9]+$)(?!-)[a-zA-Z0-9-]{,63}(?<!-)$')
    return regex.match(name) is not None


def camelcase_to_snake_case(name):
    name = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
    return name


def class_to_obj_name(name):
    obj_name = camelcase_to_snake_case(name)
    return obj_name.replace("_", "-")


def create_yaml_table(name, connector, table, primary_key, kafka, value):
    obj_name = class_to_obj_name(name)
    if not check_dns_name(obj_name):
        raise DnsNameNotCompliant
    yaml_table = {}
    yaml_table['apiVersion'] = 'industry-fusion.com/v1alpha2'
    yaml_table['kind'] = 'BeamSqlTable'
    metadata = {}
    yaml_table['metadata'] = metadata
    metadata['name'] = obj_name
    spec = {}
    yaml_table['spec'] = spec
    spec['name'] = name
    spec['connector'] = connector
    spec['fields'] = table
    spec['kafka'] = kafka
    spec['value'] = value
    if primary_key is not None:
        spec['primaryKey'] = primary_key
    return yaml_table


def create_sql_table(name, table, primary_key, dialect=SQL_DIALECT. SQL):
    sqltable = f'DROP TABLE IF EXISTS `{name}`;\n'
    first = True
    sqltable += f'CREATE TABLE `{name}` (\n'
    for field in table:
        for fname, ftype in field.items():
            if fname.lower() == 'watermark':
                break
            if 'metadata' in ftype.lower() and 'timestamp' in ftype.lower():
                if dialect == SQL_DIALECT.SQLITE:
                    ftype = 'DEFAULT CURRENT_TIMESTAMP'
                else:
                    ftype = 'TIMESTAMP(3)'
            if first:
                first = False
            else:
                sqltable += ',\n'
            sqltable += f'`{fname}` {ftype}'
    if primary_key is not None:
        sqltable += ',\nPRIMARY KEY('
        first = True
        for key in primary_key:
            if first:
                first = False
            else:
                sqltable += ','
            sqltable += f'`{key}`'
        sqltable += ')\n'
    sqltable += ');\n'

    return sqltable


def create_yaml_view(name, table, primary_key=['id']):
    table_name = class_to_obj_name(name)
    if not check_dns_name(table_name):
        raise DnsNameNotCompliant
    yaml_view = {}
    yaml_view['apiVersion'] = 'industry-fusion.com/v1alpha1'
    yaml_view['kind'] = 'BeamSqlView'
    metadata = {}
    yaml_view['metadata'] = metadata
    metadata['name'] = f'{table_name}-view'
    spec = {}
    yaml_view['spec'] = spec
    spec['name'] = f'{name}_view'
    sqlstatement = "SELECT `id`, `type`"
    for field in table:
        for field_name, field_type in field.items():
            if ('metadata' not in field_name.lower() and
                    field_name.lower() != "ts" and
                    field_name.lower() != "id" and
                    field_name.lower() != "watermark" and
                    field_name.lower() != "type"):
                sqlstatement += f',\n `{field_name}`'
    sqlstatement += " FROM (\n  SELECT *,\nROW_NUMBER() OVER (PARTITION BY "
    first = True
    for key in primary_key:
        if first:
            first = False
        else:
            sqlstatement += ', '
        sqlstatement += f'`{key}`'
    sqlstatement += "\nORDER BY ts DESC) AS rownum\n"
    sqlstatement += f'FROM `{name}` )\nWHERE rownum = 1'
    spec['sqlstatement'] = sqlstatement
    return yaml_view


def create_sql_view(table_name, table, primary_key=['id'],
                    additional_keys=['id', 'type']):
    sqlstatement = f'DROP VIEW IF EXISTS `{table_name}_view`;\n'
    sqlstatement += f"CREATE VIEW `{table_name}_view` AS\n"
    sqlstatement += "SELECT "
    first = True
    for key in additional_keys:
        if first:
            first = False
        else:
            sqlstatement += ','
        sqlstatement += f'`{key}`'
    if additional_keys:
        sqlstatement += ',\n'
    first = True
    for field in table:
        for field_name, field_type in field.items():
            if ('metadata' not in field_name.lower() and
                    field_name.lower() != "ts" and
                    field_name.lower() != "id" and
                    field_name.lower() != "watermark" and
                    field_name.lower() != "type"):
                if first:
                    first = False
                else:
                    sqlstatement += ',\n'
                sqlstatement += f'`{field_name}`'
    sqlstatement += " FROM (\n  SELECT *,\nROW_NUMBER() OVER (PARTITION BY "
    first = True
    for key in primary_key:
        if first:
            first = False
        else:
            sqlstatement += ','
        sqlstatement += f'`{key}`'
    sqlstatement += "\nORDER BY ts DESC) AS rownum\n"
    sqlstatement += f'FROM `{table_name}` )\nWHERE rownum = 1;\n'
    return sqlstatement


def create_statementset(object_name, table_object_names,
                        view_object_names, statementsets):
    yaml_bsqls = {}
    yaml_bsqls['apiVersion'] = 'industry-fusion.com/v1alpha2'
    yaml_bsqls['kind'] = 'BeamSqlStatementSet'
    metadata = {}
    yaml_bsqls['metadata'] = metadata
    metadata['name'] = object_name

    spec = {}
    yaml_bsqls['spec'] = spec
    spec['tables'] = table_object_names
    spec['views'] = view_object_names
    spec['sqlstatements'] = statementsets
    return yaml_bsqls


def create_kafka_topic(object_name, topic_name, kafka_topic_object_label,
                       config, partitions=1, replicas=1):
    yaml_kafka_topics = {}
    yaml_kafka_topics['apiVersion'] = 'kafka.strimzi.io/v1beta2'
    yaml_kafka_topics['kind'] = 'KafkaTopic'

    metadata = {}
    metadata['name'] = object_name
    labels = {}
    metadata['labels'] = labels
    labels[kafka_topic_object_label[0]] = kafka_topic_object_label[1]
    yaml_kafka_topics['metadata'] = metadata
    spec = {}
    yaml_kafka_topics['spec'] = spec
    spec['partitions'] = partitions
    spec['replicas'] = replicas
    spec['config'] = config
    spec['topicName'] = topic_name
    return yaml_kafka_topics


def strip_class(klass):
    """strip off baseclass
    e.g. http://addr/klass => klass
         http://addr/path#klass => klass

    Args:
        klass (string): url to strip off the baseclass

    Returns:
        string: stripped url
    """
    parsed = urlparse(klass)
    result = os.path.basename(parsed.path)
    if parsed.fragment is not None and parsed.fragment != '':
        result = parsed.fragment

    return result


def create_output_folder(path='output'):
    """
    """
    try:
        os.mkdir(path)
    except FileExistsError:
        pass
