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
"""Handle table and view objects"""


class ViewParsingErrorException(Exception):
    """Exception for a failed parsing of a BeamSQLView"""


class TableParsingErrorException(Exception):
    """Exception for a failed parsing of a BeamSQLTable"""


def create_ddl_from_beamsqltables(beamsqltable, logger):
    """
    creates an sql ddl object out of a beamsqltables object
    Works only with kafka connector
    column names (fields) are not expected to be escaped with ``.
    This is inserted explicitly.
    The value of the fields are supposed to be prepared to pass SQL parsing
    value: STRING # will be translated into `value` STRING,
    value is an SQL keyword (!)
    dvalue: AS CAST(`value` AS DOUBLE) # will b translated into `dvalue`
        AS CAST(`value` AS DOUBLE), `value` here is epected to be masqued

    Parameters
    ----------
    body: dict
        Beamsqlstatementset which is currently processed
    beamsqltable: dict
        Beamsqltable object
    logger: log object
        Local log object provided from framework
    """
    name = beamsqltable.metadata.name
    connector = beamsqltable.spec.get("connector")

    if connector == "kafka":
        return create_kafka_ddl(beamsqltable, logger)
    if connector == "upsert-kafka":
        return create_upsert_kafka_ddl(beamsqltable, logger)
    if connector.endswith("-cdc"):
        # cdc is a special case, it is not a kafka connector
        # but a postgres-cdc or mysql-cdc
        # the ddl is created in the same way as for upsert-kafka
        return create_cdc_ddl(beamsqltable, connector, logger)
    message = f"Beamsqltable {name} has not supported connector: \
        {connector}. Only supported: kafka, upsert-kafka"
    logger.warning(message)
    return None


def create_cdc_ddl(beamsqltable, connector, logger):
    """
    creates ddl table for cdc connector
    """
    metadata_name = beamsqltable.metadata.name
    namespace = beamsqltable.metadata.namespace
    name = beamsqltable.spec.get("name")
    if not name:
        message = f"BeamsqlTable {namespace}/{metadata_name}"\
                  f" has no defined name in spec:"
        logger.warning(message)
        name = metadata_name
    ddl = f"CREATE TABLE `{name}` ("
    ddl += ",".join(f"{k} {v}" if k.lower() == "watermark" else f"`{k}` {v}"
                    for k, v in {k: v for x in beamsqltable.spec.get("fields")
                                 for k, v in x.items()}.items())
    primary_key = beamsqltable.spec.get("primaryKey")
    if primary_key:
        ddl += ", PRIMARY KEY (" + ",".join(
               f"{v}" for v in primary_key) + ") "\
               "NOT ENFORCED"
        # Flink will not enforce the key in foreseeable future
    ddl += ") WITH ("
    ddl += f"'connector' = '{connector}'"

    # loop through the cdc structure
    # map all key value pairs to 'key' = 'value',
    cdc = beamsqltable.spec.get("cdc")
    if not cdc:
        message = f"Beamsqltable {metadata_name} has no cdc "\
                  f"connector descriptor."
        logger.warning(message)
        return None

    # insert cdc fields
    for cdc_key, cdc_value in cdc.items():
        ddl += f", '{cdc_key}' = '{cdc_value}'"
    ddl += ");"
    logger.debug(f"Created ddl for table {name}: {ddl}")
    return ddl


def create_kafka_ddl(beamsqltable, logger):
    """
    creates ddl table for kafka connector
    """
    metadata_name = beamsqltable.metadata.name
    namespace = beamsqltable.metadata.namespace
    name = beamsqltable.spec.get("name")
    if not name:
        message = f"BeamsqlTable {namespace}/{metadata_name}"\
                  f" has no defined name in spec:"
        logger.warning(message)
        name = metadata_name
    ddl = f"CREATE TABLE `{name}` ("
    ddl += ",".join(f"{k} {v}" if k.lower() == "watermark" else f"`{k}` {v}"
                    for k, v in {k: v for x in beamsqltable.spec.get("fields")
                                 for k, v in x.items()}.items())
    ddl += ") WITH ("
    ddl += "'connector' = 'kafka'"
    # loop through the value structure
    # value.format is mandatory
    value = beamsqltable.spec.get("value")
    if value is None:
        message = f"Beamsqltable {metadata_name} has no value description."
        logger.warning(message)
        return None
    if not value.get("format"):
        message = f"Beamsqltable {metadata_name} has no"\
                  f"value.format description."
        logger.warning(message)
        return None

    ddl += "," + ",".join(f"'{k}' = '{v}'" for k, v in value.items())
    # loop through the kafka structure
    # map all key value pairs to 'key' = 'value',
    # except properties
    kafka = beamsqltable.spec.get("kafka")
    if not kafka:
        message = f"Beamsqltable {metadata_name} has no Kafka "\
                  f"connector descriptor."
        logger.warning(message)
        return None
    # check mandatory fields in Kafka, topic, bootstrap.server
    if not kafka.get("topic"):
        message = f"Beamsqltable {metadata_name} has no kafka topic."
        logger.warning(message)
        return None

    try:
        _ = kafka["properties"]["bootstrap.servers"]
    except KeyError:
        message = f"Beamsqltable {metadata_name} has no kafka"\
                  f" bootstrap servers found"
        logger.warning(message)
        return None
    # the other fields are inserted, there is not a check for valid fields yet
    for kafka_key, kafka_value in kafka.items():
        # properties are iterated separately
        if kafka_key == 'properties':
            for property_key, property_value in kafka_value.items():
                ddl += f",'properties.{property_key}' = '{property_value}'"
        else:
            ddl += f", '{kafka_key}' = '{kafka_value}'"
    ddl += ");"
    logger.debug(f"Created table ddl for table {name}: {ddl}")
    return ddl


def create_upsert_kafka_ddl(beamsqltable, logger):
    """
    creates ddl table for upsert-kafka connector
    """
    metadata_name = beamsqltable.metadata.name
    namespace = beamsqltable.metadata.namespace
    name = beamsqltable.spec.get("name")
    if not name:
        message = f"BeamsqlTable {namespace}/{metadata_name}"\
                  f" has no defined name in spec:"
        logger.warning(message)
        name = metadata_name
    ddl = f"CREATE TABLE `{name}` ("
    ddl += ",".join(f"{k} {v}" if k.lower() == "watermark" else f"`{k}` {v}"
                    for k, v in {k: v for x in beamsqltable.spec.get("fields")
                                 for k, v in x.items()}.items())
    primary_key = beamsqltable.spec.get("primaryKey")
    if primary_key:
        ddl += ", PRIMARY KEY (" + ",".join(
               f"{v}" for v in primary_key) + ") "\
               "NOT ENFORCED"
        # Flink will not enforce the key in foreseeable future
    else:
        message = f"Beamsqltable {namespace}/{metadata_name} has no valid "\
                  f"Primary Key but this is"\
                  "needed for upsert-kafka. (Primarykey needs key section and"\
                  "optional enforced field)"
        logger.warning(message)
        return None
    ddl += ") WITH ("
    ddl += "'connector' = 'upsert-kafka'"
    # loop through the value structure
    # value.format is mandatory
    value = beamsqltable.spec.get("value")
    if not value:
        message = f"Beamsqltable {namespace}/{metadata_name} has no value"\
                  f" description."
        logger.warning(message)
        return None
    if not value.get("format"):
        message = f"Beamsqltable {namespace}/{metadata_name} has no "\
                  f"value.format description."
        logger.warning(message)

    ddl += "," + ",".join(f"'value.{k}' = '{v}'" for k, v in value.items())
    kafka_ddl = parse_kafka_table(beamsqltable, metadata_name, logger)
    if kafka_ddl is None:
        return None
    ddl += kafka_ddl
    ddl += ");"
    logger.debug(f"Created table ddl for table {namespace}/{metadata_name}:"
                 f" {ddl}")
    return ddl


def parse_kafka_table(beamsqltable, name, logger):
    # loop through the kafka structure
    # map all key value pairs to 'key' = 'value',
    # except properties
    """
    parse kafka parameter
    """
    ddl = ""
    kafka = beamsqltable.spec.get("kafka")
    if not kafka:
        message = f"Beamsqltable {name} has no Kafka connector descriptor."
        logger.warning(message)
        return None
    # check mandatory fields in Kafka, topic, bootstrap.server
    if not kafka.get("topic"):
        message = f"Beamsqltable {name} has no kafka topic."
        logger.warning(message)
        return None

    try:
        _ = kafka["properties"]["bootstrap.servers"]
    except KeyError:
        message = f"Beamsqltable {name} has no kafka bootstrap servers found"
        logger.warning(message)
        return None
    # the other fields are inserted, there is not a check for valid fields yet
    for kafka_key, kafka_value in kafka.items():
        # properties are iterated separately
        if kafka_key == 'properties':
            for property_key, property_value in kafka_value.items():
                ddl += f",'properties.{property_key}' = '{property_value}'"
        else:
            ddl += f", '{kafka_key}' = '{kafka_value}'"
    key_format = kafka.get("key.format")
    if key_format is None:
        message = f"Beamsqltable {name} has no key.format but it is mandatory \
            for upsert-kafka"
        logger.warning(message)
        return None
    return ddl


def create_view(beamsqlview):
    """
    creates an sql view object out of a beamsqlview object
    Views create so called 'versioned tables'. They are applied to regular
    SQL tables (no upsert tables!) and do deduplication of lines.
    Typical structure:
    CREATE VIEW [viewName] AS
        SELECT [column list]
        FROM (
            SELECT *,
            ROW_NUMBER() OVER (PARTITION BY [primary key]
            ORDER BY [rowtime column] DESC) AS rownum
        FROM [table])
    WHERE rownum = 1;


    Parameters
    ----------
    body: dict
        Beamsqlstatementset which is currently processed
    beamsqlview: dict
        BeamSqlview object
    beamsqltable: dict
        Beamsqltable objects
    logger: log object
        Local log object provided from framework
    """
    metadata_name = beamsqlview.metadata.name
    namespace = beamsqlview.metadata.namespace
    name = beamsqlview.spec.get("name")
    sqlstatement = beamsqlview.spec.get("sqlstatement")
    if not name:
        message = f"BeamsqlView {namespace}/{metadata_name} has no defined "\
                  f"name in spec:"
        raise ViewParsingErrorException(
            f"Could not create SQL View: {message}")
    if not sqlstatement:
        message = f"BeamsqlView {namespace}/{metadata_name} has no "\
                  f"sqlstatement defined in spec:"
        raise ViewParsingErrorException(
            f"Could not create SQL View: {message}")

    view = f"CREATE VIEW `{name}` AS {sqlstatement};"

    return view
