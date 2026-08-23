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
import hashlib
import re
import rdflib
import ruamel.yaml
from urllib.parse import urlparse
from enum import Enum
from rdflib import Graph, RDFS, RDF, OWL, XSD, Literal, SH, Namespace, BNode
from rdflib.collection import Collection
from collections import deque
from lib.configs import constraint_table_name, constraint_trigger_table_name, constraint_combination_table_name
from lib.configs import attribute_hash_length

NGSILD = Namespace('https://uri.etsi.org/ngsi-ld/')
commonyamlfile = '../../../helm/common.yaml'


class WrongSparqlStructure(Exception):
    pass


class SparqlValidationFailed(Exception):
    pass


class UnsupportedShape(Exception):
    """
    A shape the compiler cannot translate.

    Raised at build time rather than skipped. A constraint that is silently not
    compiled is worse than a build failure: validation then reports conformant
    for something it never checked, and nothing anywhere says so.
    """


class SQL_DIALECT(Enum):
    SQL = 0
    SQLITE = 1
    POSTGRES = 2


class DnsNameNotCompliant(Exception):
    """
    Exception for non compliant DNS name
    """


def in_stable_order(rows):
    """
    Sort query results or graph triples into a canonical order.

    Neither SPARQL nor an rdflib graph defines an iteration order, and Python
    randomises string hashing per process, so the same shapes compiled twice
    yield the same rows in a different sequence. Everything downstream inherits
    that: row order in the generated SQL, and -- because ids are handed out as
    rows arrive -- which constraint gets which id.

    Sorting on the stringified bindings makes a build a function of its inputs
    alone.
    """
    return sorted(rows, key=lambda row: tuple(str(value) for value in row))


# How many levels of attribute nesting a shape may use. 1 means an attribute
# and one sub-attribute; the OPC UA generator needs 2 for its
# hasC ==> hasE ==> hasValueList chains.
#
# This is a knob rather than a fact about SHACL. Every level costs one more
# LEFT JOIN of attributes_view in the generated SQL -- and one more join's
# worth of Flink state -- so it is deliberately not set higher than a real
# model has needed. Raising it requires nothing but this number: the path
# columns and the join chain are both generated from it.
MAX_SUBPROPERTY_DEPTH = 2


def path_columns(depth=None):
    """
    The constraint_table columns holding an attribute path, outermost first.

    The first two keep their historical names so that raising the limit does
    not rewrite the columns a two-level model already uses.
    """
    levels = (MAX_SUBPROPERTY_DEPTH if depth is None else depth) + 1
    names = ["propertyPath", "subpropertyPath"]
    names += [f"subpropertyPath{level}" for level in range(2, levels)]
    return names[:levels]


constraint_table_primary_key = ["id"]
constraint_table = [
    {"id": "INTEGER"},
    {"operation": "STRING"},
    {"circuit_level": "INTEGER"},
    {"targetClass": "STRING"},
] + [
    {column: "STRING"} for column in path_columns()
] + [
    {"propertyClass": "STRING"},
    {"propertyNodetype": "STRING"},
    {"attributeType": "STRING"},
    {"maxCount": "STRING"},
    {"minCount": "STRING"},
    {"severity": "STRING"},
    {"minExclusive": "STRING"},
    {"maxExclusive": "STRING"},
    {"minInclusive": "STRING"},
    {"maxInclusive": "STRING"},
    {"minLength": "STRING"},
    {"maxLength": "STRING"},
    {"pattern": "STRING"},
    {"ins": "STRING"},
    {"datatypes": "STRING"},
    {"hasValue": "STRING"},
    {"eventName": "STRING"},
    # sh:message, when the shape gave one. It replaces the generated
    # explanation at publish time; NULL means "use the generated one".
    {"message": "STRING"}
]

constraint_trigger_table_primary_key = ["resource", "constraint_id", "event"]
constraint_trigger_table = [
    {"resource": "STRING"},
    {"event": "STRING"},
    {"constraint_id": "INTEGER"},
    {"triggered": "BOOLEAN"},
    {"severity": "STRING"},
    {"text": "STRING"},
    {'ts': "TIMESTAMP(3) METADATA FROM 'timestamp' VIRTUAL"}
]

constraint_combination_table_primary_key = ["member_constraint_id", "target_constraint_id"]
constraint_combination_table = [
    {"member_constraint_id": "INTEGER"},
    {"operation": "STRING"},
    {"target_constraint_id": "INTEGER"}
]


def get_common_data():
    commonyaml = ruamel.yaml.YAML()
    try:
        with open(os.path.join(os.path.dirname(__file__), commonyamlfile), "r") as file:
            yaml_dict = commonyaml.load(file)
        return yaml_dict
    except Exception:
        raise Exception("Could not read common.yaml file.")


def shape_parent(g, node):
    """
    The enclosing shape, seen through logical connectives.

    A property shape written inside a connective has that connective's list
    element as its direct sh:property parent, not the attribute shape that owns
    it. Stopping there loses the parent path, the constraint ends up with
    subpropertyPath NULL, and the generated SQL then looks for the
    sub-attribute directly on the entity (parentId IS NULL) -- where it never
    matches, so the constraint silently never fires.
    """
    parent = next(g.subjects(SH.property, node), None)
    if parent is not None:
        return parent
    # `node` may instead be an element of an RDF list a connective points at.
    for cell in g.subjects(RDF.first, node):
        head = cell
        while True:
            previous = next(g.subjects(RDF.rest, head), None)
            if previous is None:
                break
            head = previous
        for predicate in (SH['or'], SH['and'], SH.xone):
            owner = next(g.subjects(predicate, head), None)
            if owner is not None:
                return owner
    return next(g.subjects(SH['not'], node), None)


def get_full_path_of_shacl_property(g, property):
    cur_property = property
    paths = []
    seen = set()
    while (cur_property is not None and cur_property not in seen):
        seen.add(cur_property)
        path = g.value(cur_property, SH.path)
        if path is not None:
            paths.append(path)
        cur_property = shape_parent(g, cur_property)
    return paths


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


def create_yaml_table_cdc(name, connector, table, primary_key, cdc):
    obj_name = class_to_obj_name(name)
    if not check_dns_name(obj_name):
        raise DnsNameNotCompliant
    yaml_table = {}
    yaml_table['apiVersion'] = 'industry-fusion.com/v1alpha3'
    yaml_table['kind'] = 'BeamSqlTable'
    metadata = {}
    yaml_table['metadata'] = metadata
    metadata['name'] = obj_name
    spec = {}
    yaml_table['spec'] = spec
    spec['name'] = name
    spec['connector'] = connector
    spec['fields'] = table
    spec['cdc'] = cdc
    if primary_key is not None:
        spec['primaryKey'] = primary_key
    return yaml_table


def create_sql_table(name, table, primary_key, dialect=SQL_DIALECT. SQL):
    if dialect in [SQL_DIALECT.SQL, SQL_DIALECT.SQLITE]:
        sqltable = f'DROP TABLE IF EXISTS `{name}`;\n'
    elif dialect == SQL_DIALECT.POSTGRES:
        sqltable = f'DROP TABLE IF EXISTS "{name}";\n'
    first = True
    if dialect in [SQL_DIALECT.SQL, SQL_DIALECT.SQLITE]:
        sqltable += f'CREATE TABLE `{name}` (\n'
    elif dialect == SQL_DIALECT.POSTGRES:
        sqltable += f'CREATE TABLE "{name}" (\n'
    for field in table:
        for fname, ftype in field.items():
            if fname.lower() == 'watermark':
                break
            if 'metadata' in ftype.lower() and 'timestamp' in ftype.lower():
                if dialect in [SQL_DIALECT.SQLITE, SQL_DIALECT.POSTGRES]:
                    ftype = 'DEFAULT CURRENT_TIMESTAMP'
                else:
                    ftype = 'TIMESTAMP(3)'
            if first:
                first = False
            else:
                sqltable += ',\n'
            if dialect in [SQL_DIALECT.POSTGRES, SQL_DIALECT.SQLITE]:
                # Neither has a STRING type. Postgres rejects it outright;
                # SQLite accepts any type name and derives affinity from the
                # letters in it, and STRING contains no CHAR, CLOB or TEXT, so
                # it lands in NUMERIC affinity -- silently turning '1.0' into
                # 1, '007' into 7 and '1e3' into 1000. Flink keeps the string,
                # so a constraint parameter that looks like a number was
                # compared differently by the two dialects.
                ftype = ftype.replace('STRING', 'TEXT')
            if dialect == SQL_DIALECT.POSTGRES:
                ftype = ftype.replace('INTEGER', 'BIGINT')
                # Postgres does not have INTEGER
            if dialect in [SQL_DIALECT.SQL, SQL_DIALECT.SQLITE]:
                sqltable += f'`{fname}` {ftype}'
            elif dialect == SQL_DIALECT.POSTGRES:
                sqltable += f'"{fname}" {ftype}'
    if primary_key is not None:
        sqltable += ',\nPRIMARY KEY('
        first = True
        for key in primary_key:
            if first:
                first = False
            else:
                sqltable += ','
            if dialect in [SQL_DIALECT.SQL, SQL_DIALECT.SQLITE]:
                sqltable += f'`{key}`'
            elif dialect == SQL_DIALECT.POSTGRES:
                sqltable += f'"{key}"'
        sqltable += ')\n'
    sqltable += ');\n'

    return sqltable


def create_yaml_view(name, table, primary_key=None, ttl=None):
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
    ttl_expression = ''
    if ttl is not None:
        ttl_expression = f"/*+ STATE_TTL('{name}' = '{ttl}') */ "
    sqlstatement = "SELECT `type`"
    for field in table:
        for field_name, field_type in field.items():
            if ('metadata' not in field_name.lower() and
                    field_name.lower() != "watermark" and
                    field_name.lower() != "offset" and
                    field_name.lower() != "type"):
                sqlstatement += f',\n `{field_name}`'
    sqlstatement += f" FROM (\n  SELECT {ttl_expression}*,\nROW_NUMBER() OVER (PARTITION BY "
    first = True
    for key in (primary_key or []):
        if first:
            first = False
        else:
            sqlstatement += ', '
        sqlstatement += f'`{key}`'
    # Kafka offset breaks the tie, where the table offers one.
    #
    # debeziumBridge stamps a DELETE with the timestamp of the value it deletes
    # -- deliberately the SAME timestamp, so that a later re-creation observed
    # at the same instant can still win. That design relies on the tie being
    # broken by ARRIVAL, which held while `ts` was a rowtime and this compiled
    # into Flink's Deduplicate (keep-last-row). Without the watermark it
    # compiles into a general Rank, and Rank keeps the INCUMBENT on a tie: it
    # replaces only on a strictly greater sort key. The delete therefore ties,
    # loses, and is discarded, leaving the attribute live for good.
    #
    # Measured: urn:filter:1's hasXXXWorkpiece was deleted in Scorpio and the
    # delete published, yet the job went on counting it -- reporting a
    # ClassConstraint violation ("not linked to existing entity of type
    # Workpiece"), which only fires when a non-deleted row with a datasetId is
    # present. Republishing the same delete with a CURRENT timestamp cleared it
    # within seconds, and the alert became the correct CountConstraint. Only a
    # strictly greater key displaced the row.
    #
    # The offset is strictly monotonic per partition, so it IS arrival order,
    # stated explicitly rather than inherited from whichever operator Flink
    # happens to choose. The earlier objection to ordering by it -- that a plain
    # BIGINT downgrades Deduplicate to a general rank -- no longer applies:
    # `ts` is no longer a rowtime, so this is a general rank either way.
    # Order on the EVENT time, which now travels in the payload. It used to be
    # read from `ts`, the Kafka record timestamp, because the bridge put
    # observedAt there -- which meant retention.ms, a wall-clock STORAGE policy,
    # was being applied to an event time. The kms model observes at 2024-02-28,
    # so every attribute record was born older than any sane retention and Kafka
    # deleted it on contact: measured, three snapshot bursts of 249 records and
    # logStart == logEnd every time. `ts` is now write time and observedAt is
    # data. The ordering means exactly what it meant before.

    def has(field_name):
        return any(fn.lower() == field_name
                   for field in table for fn in field)

    # COALESCE, not observedAt alone: any writer that does not set it -- the
    # writeback that stamps `synced`, for one -- would otherwise produce NULL,
    # lose every comparison, never win the dedup, and leave the attribute
    # looking unsynced for ever. Falling back to the write time is exactly
    # the behaviour those rows had before.
    order_by = ("COALESCE(`observedAt`, `ts`) DESC"
                if has('observedat') else "ts DESC")
    if has('offset'):
        order_by += ", `offset` DESC"
    sqlstatement += f"\nORDER BY {order_by}) AS rownum\n"
    sqlstatement += f'FROM `{name}` )\nWHERE rownum = 1'
    spec['sqlstatement'] = sqlstatement
    return yaml_view


def create_sql_view(table_name, table, primary_key=None,
                    additional_keys=['type']):
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
                    field_name.lower() != "watermark" and
                    field_name.lower() != "type"):
                if first:
                    first = False
                else:
                    sqlstatement += ',\n'
                sqlstatement += f'`{field_name}`'
    sqlstatement += " FROM (\n  SELECT *,\nROW_NUMBER() OVER (PARTITION BY "
    first = True
    for key in (primary_key or []):
        if first:
            first = False
        else:
            sqlstatement += ','
        sqlstatement += f'`{key}`'
    # rowid is SQLite's insertion order, so this mirrors the Kafka offset the
    # streaming view orders by: on equal ts the later-inserted row wins. Without
    # it a tie is resolved arbitrarily and the oracle could disagree with Flink
    # on exactly the delete-vs-value case the tie-break exists for.
    order_col = ('COALESCE(`observedAt`, `ts`)'
                 if any(fn.lower() == 'observedat'
                        for field in table for fn in field)
                 else 'ts')
    sqlstatement += f"\nORDER BY {order_col} DESC, rowid DESC) AS rownum\n"
    sqlstatement += f'FROM `{table_name}` )\nWHERE rownum = 1;\n'
    return sqlstatement


def create_configmap(object_name, sqlstatementset, labels=None):
    data = {}
    for index, value in enumerate(sqlstatementset):
        data[index] = value
    return create_configmap_generic(object_name, data, labels)


def create_configmap_generic(object_name, data, labels=None):
    yaml_cm = {}
    yaml_cm['apiVersion'] = 'v1'
    yaml_cm['kind'] = 'ConfigMap'
    metadata = {}
    if labels is not None:
        metadata['labels'] = labels
    yaml_cm['metadata'] = metadata
    metadata['name'] = object_name
    yaml_cm['data'] = data
    return yaml_cm


def create_statementmap(object_name, table_object_names,
                        view_object_names, ttl, statementmaps, enable_checkpointing=False, refresh_interval=None,
                        use_rocksdb=True):
    yaml_bsqls = {}
    yaml_bsqls['apiVersion'] = 'industry-fusion.com/v1alpha4'
    yaml_bsqls['kind'] = 'BeamSqlStatementSet'
    metadata = {}
    yaml_bsqls['metadata'] = metadata
    metadata['name'] = object_name

    spec = {}
    yaml_bsqls['spec'] = spec
    spec['tables'] = table_object_names
    if refresh_interval:
        spec['refreshInterval'] = refresh_interval
    spec['views'] = view_object_names
    spec['sqlsettings'] = [
        # AUTO inserts a SinkUpsertMaterializer that remembers the last row
        # emitted per key and drops updates that do not change it. Without it
        # every intermediate changelog state is written to Kafka: measured ~25
        # msg/s reaching alerts_bulk to produce ~0.5 useful alerts/min, i.e.
        # roughly 2900:1 write amplification that CoreServices' AlertsFilter
        # then had to absorb downstream. Suppressing at the sink keeps those
        # records out of Kafka entirely.
        {"table.exec.sink.upsert-materialize": "auto"},
        # Mini-batch buffers changelog records per key and emits once per
        # window, collapsing the convergence churn of a multi-level constraint
        # circuit (measured: 76% of verdict changes land within 2ms of the
        # previous one). All three keys are required for it to take effect.
        #
        # DISABLED until Flink >= 1.19.2: on 1.19.1 the MiniBatchAssigner
        # nodes drop the alias-keyed STATE_TTL hints on their way to the
        # joins (FLINK-36238 / FLINK-36417, fixed in 1.19.2/1.20.1), so the
        # '0d' pins on the validation joins never reach the operators and
        # every join-based rule dies for good once its state passes
        # table.exec.state.ttl. Measured with tools/ttl_test.py at a 600 s
        # TTL: with mini-batch on, all four SPARQL rules were silent after a
        # 3x TTL idle (11/11 checks pass with it off, identical SQL). The
        # sink-side upsert materializer above stays on and remains the main
        # defense against write amplification.
        {"table.exec.mini-batch.enabled": "false"},
        {"table.exec.mini-batch.allow-latency": "100 ms"},
        {"table.exec.mini-batch.size": "1000"},
        {"execution.savepoint.ignore-unclaimed-state": "true"},
        {"pipeline.object-reuse": "true"},
        {"parallelism.default": "{{ .Values.flink.defaultParalellism }}"},
        {"table.exec.source.idle-timeout": "{{ .Values.flink.idleTimeout }}"}
    ]
    if use_rocksdb:
        spec['sqlsettings'].append({"state.backend": "rocksdb"})
        spec['sqlsettings'].append({"state.backend.rocksdb.writebuffer.size": "64 kb"})
        spec['sqlsettings'].append({"state.backend.rocksdb.use-bloom-filter": "true"})
        spec['sqlsettings'].append({"state.backend.rocksdb.predefined-options": "SPINNING_DISK_OPTIMIZED_HIGH_MEM"})
    if ttl is not None:
        spec['sqlsettings'].append({"table.exec.state.ttl": f"{ttl}"})
    if enable_checkpointing:
        spec['sqlsettings'].append({"execution.checkpointing.interval": "{{ .Values.flink.checkpointInterval }}"})
    spec['sqlstatementmaps'] = statementmaps
    spec['updateStrategy'] = "none"
    return yaml_bsqls


def create_statementset(object_name, table_object_names,
                        view_object_names, ttl, statementsets, refresh_interval=None):
    yaml_bsqls = {}
    yaml_bsqls['apiVersion'] = 'industry-fusion.com/v1alpha4'
    yaml_bsqls['kind'] = 'BeamSqlStatementSet'
    metadata = {}
    yaml_bsqls['metadata'] = metadata
    metadata['name'] = object_name

    spec = {}
    yaml_bsqls['spec'] = spec
    spec['tables'] = table_object_names
    if refresh_interval:
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
            return f"'{node.toPython()}'"
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
    while "SQL_DIALECT_STRIP" in result_expression or "SQL_DIALECT_CAST" in result_expression \
            or "SQL_DIALECT_ATTRIBUTE_ID" in result_expression:
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
            result_expression = re.sub(r'SQL_DIALECT_ATTRIBUTE_ID{([^{}]*)}',
                                       lambda m: "'" + attribute_id_suffix(m.group(1), sqlite=True) + "'",
                                       result_expression)
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
            result_expression = re.sub(r'SQL_DIALECT_ATTRIBUTE_ID{([^{}]*)}',
                                       lambda m: "'" + attribute_id_suffix(m.group(1)) + "'",
                                       result_expression)
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
    elif var in time_variables:
        if varname in bounds:
            return f"SQL_DIALECT_TIME_TO_MILLISECONDS{{{bounds[varname]}}}"
    else:  # plain RDF variable
        return bounds[varname]


def split_statementsets(statementsets, max_map_size):
    grouped_strings = []  # This will hold the final list of grouped strings
    current_group = []    # Temporary list to hold the current group of strings
    current_size = 0       # Keep track of the total size of the current group

    for string in statementsets:
        string_size = len(string)  # Calculate the size of the current string

        # If adding the current string exceeds the max_map_size, save the current group
        if current_size + string_size > max_map_size and current_size > 0:
            grouped_strings.append(current_group)
            current_group = []    # Start a new group
            current_size = 0      # Reset the size counter for the new group

        # Add the current string to the group and update the size
        current_group.append(string)
        current_size += string_size

    # Don't forget to add the last group if it's not empty
    if current_group:
        grouped_strings.append(current_group)

    return grouped_strings


def create_constraint_yaml_table(connector, kafka, value, cdc=None):
    """
    Create a YAML table for constraints.
    If is_cdc is True, it creates a CDC table.
    """
    if cdc is None:
        return create_yaml_table(constraint_table_name, connector, constraint_table,
                                 constraint_table_primary_key, kafka, value)
    return create_yaml_table_cdc(constraint_table_name, connector, constraint_table,
                                 constraint_table_primary_key, cdc)


def create_constraint_sql_table(sql_dialect=SQL_DIALECT.SQLITE):
    return create_sql_table(constraint_table_name, constraint_table, constraint_table_primary_key,
                            sql_dialect)


def create_constraint_trigger_yaml_table(connector, kafka, value):
    return create_yaml_table(constraint_trigger_table_name,
                             connector,
                             constraint_trigger_table,
                             constraint_trigger_table_primary_key,
                             kafka, value)


def create_constraint_trigger_sql_table():
    return create_sql_table(constraint_trigger_table_name,
                            constraint_trigger_table,
                            constraint_trigger_table_primary_key,
                            SQL_DIALECT.SQLITE)


def create_constraint_combination_yaml_table(connector, kafka, value, cdc=None):
    """Create a YAML table for constraint combinations.

    Args:
        connector (Any): Connector configuration.
        kafka (Any): Kafka configuration.
        value (Any): Value configuration.
        cdc (Any, optional): CDC configuration. Defaults to None.

    Returns:
        dict: YAML table definition.
    """
    if cdc is None:
        return create_yaml_table(constraint_combination_table_name,
                                 connector,
                                 constraint_combination_table,
                                 constraint_combination_table_primary_key, kafka, value)

    return create_yaml_table_cdc(constraint_combination_table_name,
                                 connector,
                                 constraint_combination_table,
                                 constraint_combination_table_primary_key, cdc)


def create_constraint_combination_sql_table(sql_dialect=SQL_DIALECT.SQLITE):
    return create_sql_table(constraint_combination_table_name,
                            constraint_combination_table,
                            constraint_combination_table_primary_key,
                            sql_dialect)


def add_table_values(values, table, sqldialect, table_name, max_size=500):
    """
    Create a list of SQL insert statements, each with at most max_size rows.

    Args:
        values (list of dict): Each dict contains field names and values.
        table (list of dict): Table schema, each dict maps field name to type.
        sqldialect (SQL_DIALECT): SQL dialect to use.
        table_name (str): Name of the table.
        max_size (int): Maximum number of rows per statement.

    Returns:
        list of str: List of SQL insert statements.
    """
    statements = []
    total_values = len(values)
    for start in range(0, total_values, max_size):
        chunk = values[start:start + max_size]
        if sqldialect == SQL_DIALECT.SQLITE:
            statement = f'INSERT OR REPLACE INTO {table_name} VALUES'
        else:
            statement = f'INSERT INTO {table_name} VALUES'
        first_row = True
        for value in chunk:
            lcheck = {}
            for k, v in value.items():
                try:
                    datatype = next((typ[k] for typ in table if k in typ))
                except Exception:
                    print(f"Error: You provided a table field {k} which does not have a type in the given table \
schema {table}.")
                    datatype = "STRING"
                if sqldialect == SQL_DIALECT.POSTGRES:
                    datatype = "TEXT"
                if v is None:
                    lcheck[k] = f'CAST (NULL as {datatype})'
                else:
                    if datatype in ("STRING", "TEXT"):
                        lcheck[k] = f"'{v}'"
                    else:
                        lcheck[k] = f"{v}"
            if first_row:
                first_row = False
            else:
                statement += ', '
            statement += '('
            first_col = True
            for col in table:
                col_name = next(iter(col))
                if first_col:
                    first_col = False
                else:
                    statement += ','
                statement += lcheck[col_name]
            statement += ')'
        statement += ';'
        statements.append(statement)
    return statements


def circuit_level_of(constraint_checks, member_ids):
    """
    Level of an internal circuit node: 1 + max(level of its members).

    Levels are assigned by LONGEST path from a leaf, so a node is never
    evaluated before every one of its members has been. The evaluator is
    unrolled once per level, which is what keeps the whole thing expressible
    without recursion.
    """
    levels = [check['circuit_level'] for check in constraint_checks
              if check.get('id') in member_ids]
    return 1 + max(levels, default=0)


def init_constraint_check():
    check = {}
    # `operation` is NULL for leaf constraints and holds the boolean connective
    # ('OR', 'AND', 'NOT', 'XONE') for internal nodes of the constraint circuit.
    # `circuit_level` is 0 for leaves and 1 + max(level of members) for internal
    # nodes, so the evaluator can be unrolled one statement per level.
    check["operation"] = None
    check["circuit_level"] = 0
    check["targetClass"] = None
    for column in path_columns():
        check[column] = None
    check["propertyClass"] = None
    check["propertyNodetype"] = None
    check["attributeType"] = None
    check["maxCount"] = None
    check["minCount"] = None
    check["severity"] = None
    check["minExclusive"] = None
    check["maxExclusive"] = None
    check["minInclusive"] = None
    check["maxInclusive"] = None
    check["minLength"] = None
    check["maxLength"] = None
    check["pattern"] = None
    check["ins"] = None
    check["datatypes"] = None
    check["hasValue"] = None
    check["eventName"] = None
    check["message"] = None
    return check


# This creates a transitive closure of all OWL.TransitiveProperty elements given in the ontology
# plus rdfs:subClassOf. In addition is makes sure that every rdfs:Class and owl:Class are reflexive
def transitive_closure(g):
    closure_graph = Graph(store="Oxigraph")
    closure_graph += g

    # Ensure rdfs:subClassOf is defined as an OWL.TransitiveProperty if it is not already defined
    if (RDFS.subClassOf, RDF.type, OWL.TransitiveProperty) not in closure_graph:
        closure_graph.add((RDFS.subClassOf, RDF.type, OWL.TransitiveProperty))

    # Handle subClassOf separately
    # Add reflexive subClassOf relationships for all classes
    for s in closure_graph.subjects(predicate=RDFS.subClassOf):
        if (s, RDFS.subClassOf, s) not in closure_graph:
            closure_graph.add((s, RDFS.subClassOf, s))

    # Add reflexive subClassOf relationships for every element of type rdfs:Class and owl:Class
    for s in closure_graph.subjects(predicate=RDF.type, object=RDFS.Class):
        if (s, RDFS.subClassOf, s) not in closure_graph:
            closure_graph.add((s, RDFS.subClassOf, s))
    for s in closure_graph.subjects(predicate=RDF.type, object=OWL.Class):
        if (s, RDFS.subClassOf, s) not in closure_graph:
            closure_graph.add((s, RDFS.subClassOf, s))

    # Handle other transitive properties
    transitive_properties = set(closure_graph.subjects(predicate=RDF.type, object=OWL.TransitiveProperty))
    for prop in transitive_properties:
        # Use a queue for BFS for each transitive property
        queue = deque(closure_graph.triples((None, prop, None)))
        visited = set(queue)

        while queue:
            s1, _, o1 = queue.popleft()

            # Find all objects that o1 is related to via the same property
            for _, _, o2 in closure_graph.triples((o1, prop, None)):
                if (s1, prop, o2) not in visited:
                    # Add new inferred triple
                    closure_graph.add((s1, prop, o2))
                    queue.append((s1, prop, o2))
                    visited.add((s1, prop, o2))

    # Handle generalization of rdf:Bag/rdf:Container
    for bag in closure_graph.subjects(predicate=RDF.type, object=RDF.Bag):
        # Add rdf:Bag and rdfs:Container types
        closure_graph.add((bag, RDF.type, RDFS.Container))

        # Collect all rdf:_n properties (e.g., rdf:_1, rdf:_2, etc.)
        members = []
        for p, o in closure_graph.predicate_objects(subject=bag):
            if p.startswith(str(RDF) + "_"):
                members.append(o)
                # Ensure all values are xsd:string literals
                if not isinstance(o, Literal) or o.datatype != XSD.string:
                    closure_graph.set((bag, p, Literal(str(o), datatype=XSD.string)))

        # Add rdfs:member relationships
        if members:
            closure_graph.add((bag, RDFS.member, Literal(members[0], datatype=XSD.string)))
            for member in members[1:]:
                closure_graph.add((bag, RDFS.member, Literal(member, datatype=XSD.string)))

    return closure_graph


def rdf_list_to_pylist(graph, head):
    """
    Recursively convert an RDF Collection (starting at `head`)
    into a Python list. If an element is itself a blank‐node list,
    recurse; otherwise, convert Literals/URIs to str.
    """
    if not isinstance(head, BNode) and head != RDF.nil:
        # allow returning of potentially wrong list elements to allow
        # debugging
        return head
    py_list = []
    if head == RDF.nil:
        # empty list
        return py_list
    if not isinstance(head, BNode):
        raise TypeError("Head of RDF list must be a blank node or RDF.nil")
    col = Collection(graph, head)
    for item in col:
        if isinstance(item, BNode) and (item, RDF.first, None) in graph:
            # nested list
            py_list.append(rdf_list_to_pylist(graph, item))
        else:
            # leaf node: Literal or URIRef
            if isinstance(item, Literal):
                py_list.append(item.toPython())
            else:
                # you can choose .n3(), .toPython(), or str(item) for URIs
                py_list.append(str(item))
    return py_list


def attribute_id_suffix(name, datasetId='@none', sqlite=False):
    """The id an attribute must carry to BE the attribute the platform already
    knows, rather than a second one beside it.

    A rule writing an attribute back has to name it exactly as its other writer
    does. attributes_view partitions on (id, datasetId), so two spellings land
    as two rows and a [1,1] property is reported as "Found 2" for a value that
    exists once. Measured: the rule wrote urn:cartridge:1\\<full IRI> while the
    bridge wrote urn:cartridge:1\\6fb7b362d0a8eebcf7344a43, and isUsedUntil was
    counted twice.

    The two readers spell it differently, so this does too. Flink reads what
    debeziumBridge.js wrote, which hashes everything after the urn prefix --
    sha256("<name>\\<datasetId>") truncated to kafkaBridge.hashlength. The
    SQLite oracle reads what create_ngsild_models.py wrote, which keeps the
    parts verbatim. Both are computed here rather than in SQL, because name and
    datasetId are known while generating and neither dialect needs a hash.
    """
    if sqlite:
        return f'\\{name}\\{datasetId}'
    hashed = hashlib.sha256(f'{name}\\{datasetId}'.encode()).hexdigest()
    return '\\' + hashed[:attribute_hash_length]


def get_state_ttl_metadata(tablenames):
    """
    Create STATE_TTL metadata for a list of tables.
    For instance, if we get tablenames ['D', 'C'], we return:
    /*+ STATE_TTL('D' = '0d', 'C' = '0d') */

    Args:
        tablenames (list): A list of table names.
    """
    ttl_expr = ', '.join([f"'{name}' = '0d'" for name in tablenames])
    return f"/*+ STATE_TTL({ttl_expr}) */"
