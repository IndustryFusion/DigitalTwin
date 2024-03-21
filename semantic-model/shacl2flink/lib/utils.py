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
import rdflib
from urllib.parse import urlparse
from enum import Enum


class WrongSparqlStructure(Exception):
    pass


class SparqlValidationFailed(Exception):
    pass


class SQL_DIALECT(Enum):
    SQL = 0
    SQLITE = 1


class DnsNameNotCompliant(Exception):
    """
    Exception for non compliant DNS name
    """


def get_timevars(ctx, vars):
    """calculate time-attribute of variables

    Args:
        bounds (dict): dictionary of varialbe bounds
        vars (list): list of variables
    """
    sqltables = []
    timevars = []
    bounds = ctx['bounds']
    for var in vars:
        sqlvar = bounds[var]
        sqltable = sqlvar.split('.')[0]
        sqltable = sqltable.strip('`')
        sqltables.append(sqltable)
    sqltables = list(set(sqltables))
    for tab in sqltables:
        timevars.append(f'{tab}.ts')
    return timevars


def set_group_by_vars(ctx, vars):
    for var in vars:
        if 'group_by_vars' not in ctx:
            ctx['group_by_vars'] = []
        ctx['group_by_vars'].append(create_varname(var))


def add_group_by_vars(ctx, rdfvar):
    var = create_varname(rdfvar)
    if 'group_by_vars' in ctx:
        if var not in ctx['group_by_vars']:
            ctx['group_by_vars'].append(var)
    else:
        ctx['group_by_vars'] = [var]


def get_group_by_vars(ctx):
    if 'group_by_vars' in ctx:
        return ctx['group_by_vars']
    else:
        return None


def set_is_aggregate_var(ctx, state):
    ctx['is_aggregate_var'] = state


def get_is_aggregate_var(ctx):
    if 'is_aggregate_var' in ctx:
        return ctx['is_aggregate_var']
    else:
        return False


def get_aggregate_vars(ctx):
    vars = None
    if 'aggregate_vars' in ctx:
        vars = ctx['aggregate_vars']
    return vars


def set_aggregate_vars(ctx, vars):
    for var in vars:
        if 'aggregate_vars' not in ctx:
            ctx['aggregate_vars'] = []
        ctx['aggregate_vars'].append(var)


def add_aggregate_var_to_context(ctx, var):
    if 'is_aggregate_var' not in ctx or not ctx['is_aggregate_var']:
        return
    if 'aggregate_vars' not in ctx:
        ctx['aggregate_vars'] = []
    ctx['aggregate_vars'].append(var)


def create_varname(variable):
    """
    creates a plain varname from RDF varialbe
    e.g. ?var => var
    """
    return variable.toPython()[1:]


def check_dns_name(name):
    regex = re.compile('^(?![0-9]+$)(?!-)[a-zA-Z0-9-]{,63}(?<!-)$')
    return regex.match(name) is not None


def camelcase_to_snake_case(name):
    name = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
    return name


def snake_case_to_kebab_case(name):
    name = name.replace('_', '-')
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


def create_configmap(object_name, sqlstatementset):
    # yaml_cm = {}
    # yaml_cm['apiVersion'] = 'v1'
    # yaml_cm['kind'] = 'ConfigMap'
    # metadata = {}
    # yaml_cm['metadata'] = metadata
    # metadata['name'] = object_name
    data = {}
    # yaml_cm['data'] = data
    for index, value in enumerate(sqlstatementset):
        data[index] = value
    return create_configmap_generic(object_name, data)


def create_configmap_generic(object_name, data):
    yaml_cm = {}
    yaml_cm['apiVersion'] = 'v1'
    yaml_cm['kind'] = 'ConfigMap'
    metadata = {}
    yaml_cm['metadata'] = metadata
    metadata['name'] = object_name
    yaml_cm['data'] = data
    return yaml_cm


def create_statementmap(object_name, table_object_names,
                        view_object_names, ttl, statementmaps, refresh_interval="12h"):
    yaml_bsqls = {}
    yaml_bsqls['apiVersion'] = 'industry-fusion.com/v1alpha4'
    yaml_bsqls['kind'] = 'BeamSqlStatementSet'
    metadata = {}
    yaml_bsqls['metadata'] = metadata
    metadata['name'] = object_name

    spec = {}
    yaml_bsqls['spec'] = spec
    spec['tables'] = table_object_names
    spec['refreshInterval'] = refresh_interval
    spec['views'] = view_object_names
    if ttl is not None:
        spec['sqlsettings'] = [
            {"table.exec.state.ttl": f"{ttl}"},
            {"state.backend.rocksdb.writebuffer.size": "64 kb"},
            {"state.backend.rocksdb.use-bloom-filter": "true"},
            {"execution.checkpointing.interval": "{{ .Values.flink.checkpointInterval }}"},
            {"table.exec.sink.upsert-materialize": "none"},
            {"state.backend": "rocksdb"},
            {"execution.savepoint.ignore-unclaimed-state": "true"},
            {"pipeline.object-reuse": "true"},
            {"state.backend.rocksdb.predefined-options": "SPINNING_DISK_OPTIMIZED_HIGH_MEM"},
            {"parallelism.default": "{{ .Values.flink.defaultParalellism }}"}
        ]
    spec['sqlstatementmaps'] = statementmaps
    spec['updateStrategy'] = "none"
    return yaml_bsqls


def create_statementset(object_name, table_object_names,
                        view_object_names, ttl, statementsets, refresh_interval="12h"):
    yaml_bsqls = {}
    yaml_bsqls['apiVersion'] = 'industry-fusion.com/v1alpha4'
    yaml_bsqls['kind'] = 'BeamSqlStatementSet'
    metadata = {}
    yaml_bsqls['metadata'] = metadata
    metadata['name'] = object_name

    spec = {}
    yaml_bsqls['spec'] = spec
    spec['tables'] = table_object_names
    spec['refreshInterval'] = refresh_interval
    spec['views'] = view_object_names
    if ttl is not None:
        spec['sqlsettings'] = [
            {"table.exec.state.ttl": f"{ttl}"},
            {"state.backend.rocksdb.writebuffer.size": "64 kb"},
            {"state.backend.rocksdb.use-bloom-filter": "true"},
            {"execution.checkpointing.interval": "{{ .Values.flink.checkpointInterval }}"},
            {"table.exec.sink.upsert-materialize": "none"},
            {"state.backend": "rocksdb"},
            {"execution.savepoint.ignore-unclaimed-state": "true"},
            {"pipeline.object-reuse": "true"},
            {"state.backend.rocksdb.predefined-options": "SPINNING_DISK_OPTIMIZED_HIGH_MEM"},
            {"parallelism.default": "{{ .Values.flink.defaultParalellism }}"}
        ]
    spec['sqlstatements'] = statementsets
    spec['updateStrategy'] = "none"
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


def format_node_type(node):
    """
    formats node dependent on node-type
    IRI: iri => '<iri>'
    Literal: literal => '"literal"'
    BNodde: id => '_:id'
    """
    if isinstance(node, rdflib.URIRef):
        return f"\'<{node.toPython()}>\'"
    elif isinstance(node, rdflib.Literal):
        if node.datatype == rdflib.XSD.decimal or node.datatype == rdflib.XSD.double or\
                node.datatype == rdflib.XSD.float or node.datatype == rdflib.XSD.integer:
            return node.toPython()
        else:
            quoted_string = node.toPython().replace("'", "''")
            return f'\'"{quoted_string}"\''
    elif isinstance(node, rdflib.BNode):
        return f'\'_:{node.toPython()}\''
    else:
        raise ValueError('Node is not IRI, Literal, BNode')


def process_sql_dialect(expression, isSqlite):
    result_expression = expression
    max_recursion = 10
    while "SQL_DIALECT_STRIP" in result_expression:
        max_recursion = max_recursion - 1
        if max_recursion == 0:
            raise WrongSparqlStructure("Unexpected problem with SQL_DIALECT macros.")
        if isSqlite:

            result_expression = re.sub(r'SQL_DIALECT_STRIP_IRI{([^{}]*)}',
                                       r"ltrim(rtrim(\1, '>'), '<')",
                                       result_expression)
            result_expression = re.sub(r'SQL_DIALECT_STRIP_LITERAL{([^{}]*)}', r"trim(\1, '\"')",
                                       result_expression)
            result_expression = re.sub(r'SQL_DIALECT_TIME_TO_MILLISECONDS{([^{}]*)}',
                                       r"CAST(julianday(\1) * 86400000 as INTEGER)",
                                       result_expression)
            result_expression = result_expression.replace('SQL_DIALECT_CURRENT_TIMESTAMP', 'datetime()')
            result_expression = result_expression.replace('SQL_DIALECT_INSERT_ATTRIBUTES',
                                                          'INSERT OR REPLACE INTO attributes_insert_filter')
            result_expression = result_expression.replace('SQL_DIALECT_SQLITE_TIMESTAMP', 'CURRENT_TIMESTAMP')
            result_expression = result_expression.replace('SQL_DIALECT_CAST', 'CAST')
        else:
            result_expression = re.sub(r'SQL_DIALECT_STRIP_IRI{([^{}]*)}',
                                       r"REGEXP_REPLACE(CAST(\1 as STRING), '>|<', '')",
                                       result_expression)
            result_expression = re.sub(r'SQL_DIALECT_STRIP_LITERAL{([^{}]*)}',
                                       r"REGEXP_REPLACE(CAST(\1 as STRING), '\"', '')",
                                       result_expression)
            result_expression = re.sub(r'SQL_DIALECT_TIME_TO_MILLISECONDS{([^{}]*)}',
                                       r"1000 * UNIX_TIMESTAMP(TRY_CAST(\1 AS STRING)) + " +
                                       r"EXTRACT(MILLISECOND FROM TRY_CAST(\1 as TIMESTAMP))",
                                       result_expression)
            result_expression = result_expression.replace('SQL_DIALECT_CURRENT_TIMESTAMP',
                                                          'CURRENT_TIMESTAMP')
            result_expression = result_expression.replace('SQL_DIALECT_INSERT_ATTRIBUTES',
                                                          'INSERT into attributes_insert')
            result_expression = result_expression.replace(',SQL_DIALECT_SQLITE_TIMESTAMP', '')
            result_expression = result_expression.replace('SQL_DIALECT_CAST', 'TRY_CAST')
    return result_expression


def unwrap_variables(ctx, var):
    """unwrap variables for arithmetic operations
       ngsild variables are not touched except times variables
       rdf variables are assumed to be Simple Literals and are treatet
       as strings when not casted
    Args:
        ctx (hash): context
        var (Variable): RDFLib variable
    """
    bounds = ctx['bounds']
    time_variables = ctx['time_variables']
    varname = create_varname(var)
    add_aggregate_var_to_context(ctx, varname)

    if var in time_variables:
        return f"SQL_DIALECT_TIME_TO_MILLISECONDS{{{bounds[varname]}}}"
    return bounds[varname]


def wrap_ngsild_variable(ctx, var):
    """
    Wrap NGSI_LD variables into RDF
    e.g. if var is literal => '"' || bounds[var] || '"'
    if var is IRI => '<' || bounds[var] || '>'

    ctx: context containing property_variables, entity_variables, bounds
    var: variable
    """
    if not isinstance(var, rdflib.Variable):
        raise TypeError("NGSI-LD Wrapping of non-variables is not allowed.")
    bounds = ctx['bounds']
    property_variables = ctx['property_variables']
    entity_variables = ctx['entity_variables']
    time_variables = ctx['time_variables']
    varname = create_varname(var)
    add_aggregate_var_to_context(ctx, varname)
    if varname not in bounds:
        raise SparqlValidationFailed(f'Could not resolve variable \
?{varname} in expression {ctx["query"]}.')
    if var in property_variables:
        if property_variables[var]:
            return "'<' || " + bounds[varname] + " || '>'"
        else:
            return "'\"' || " + bounds[varname] + " || '\"'"
    elif var in entity_variables:
        raise SparqlValidationFailed(f'Cannot bind enttiy variable {varname} to \
plain RDF context')
    elif var in time_variables:
        if varname in bounds:
            return f"SQL_DIALECT_TIME_TO_MILLISECONDS{{{bounds[varname]}}}"
    else:  # plain RDF variable
        return bounds[varname]
