"""
Unittests for tables_and_views.py
"""
from unittest import TestCase
import unittest
from bunch_py3 import Bunch
from mock import patch

import tables_and_views as target


# Mock functions
# --------------
GLOBAL_MESSAGE = ''

class Logger():
    """
    mock for logger
    """
    def info(self, message):
        """
        mock for info
        """

    def debug(self, message):
        """
        mock for debug
        """

    def error(self, message):
        """
        mock for error
        """

   # pylint: disable=global-statement,no-self-use
    def warning(self, message):
        """
        mock for warning
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = message

# pylint: disable=unused-argument
def kopf_info(body, reason, message):
    """
    mock for kopf_info
    """



class TestDdlCreation(TestCase):
    """
    tests for ddl creation
    """
    create_kafka_ddl_used = False
    create_upsert_kafka_ddl_used = False

   # pylint: disable=global-statement, no-self-use, no-self-argument
    def create_kafka_ddl(beamsqltable, logger):
        """
        mock for create_kafka_ddl
        """
        TestDdlCreation.create_kafka_ddl_used = True


    @patch('tables_and_views.create_kafka_ddl',
        create_kafka_ddl)
    def test_create_ddl_from_beamsqltable(self):
        """
        test for create_ddl_from_beamsqltable
        """
        TestDdlCreation.create_kafka_ddl_used = False

        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "kafka"
        }

        target.create_ddl_from_beamsqltables(beamsqltable, Logger())
        self.assertEqual(TestDdlCreation.create_kafka_ddl_used, True)

   # pylint: disable=global-statement, no-self-use, no-self-argument
    def create_upsert_kafka_ddl(beamsqltable, logger):
        """
        mock for create_upsert_kafka_ddl
        """
        TestDdlCreation.create_upsert_kafka_ddl_used = True


    @patch('tables_and_views.create_upsert_kafka_ddl',
        create_upsert_kafka_ddl)
    def test_create_upsert_ddl_from_beamsqltable(self):
        """
        test for create_upsert_ddl_from_beamsqlable
        """
        TestDdlCreation.create_upsert_kafka_ddl_used = False

        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "upsert-kafka"
        }

        target.create_ddl_from_beamsqltables(beamsqltable, Logger())
        self.assertEqual(TestDdlCreation.create_upsert_kafka_ddl_used, True)

    def test_warning(self):
        """
        test warnings for create_ddl_from_beamsqltables without connector spec
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""

        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "wrong"
        }

        target.create_ddl_from_beamsqltables(beamsqltable, Logger())
        self.assertTrue(GLOBAL_MESSAGE.startswith("Beamsqltable name has not supported connector:"))


class TestcreateKafkaDdl(TestCase):
    """
    tests for create_kafka_ddl
    """
       # pylint: disable=global-statement, no-self-argument
    def test_create_ddl_from_beamsqltable(self):
        """
        test successful kafka_ddl creation
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "kafka",
            "name": "name",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ],
            "value": {
                "format": "json"
            },
            "kafka": {
                "topic": "topic",
                "properties": {
                    "bootstrap.servers": "bootstrap.servers"
                }
            }
        }

        result = target.create_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, "CREATE TABLE `name` (`field1` field1,`field2` field2) WITH "\
            "('connector' = 'kafka','format' = 'json', 'topic' = 'topic',"\
            "'properties.bootstrap.servers' = 'bootstrap.servers');")

    def test_create_ddl_from_beamsqltable_noformat(self):
        """
        test create_ddl_from_eamsqltable withtout format spec
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "kafka",
            "name": "name",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ],
            "value": {
            },
            "kafka": {
                "topic": "topic",
                "properties": {
                    "bootstrap.servers": "bootstrap.servers"
                }
            }
        }

        result = target.create_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, None)

    def test_create_ddl_from_beamsqltable_no_value(self):
        """
        test create_ddl_from_beamsqltable with no value in spec
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "kafka",
            "name": "name",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ],
            "value": {
                "format": "json"
            },
            "kafka": {
                "topic": "topic",
                "properties": {
                    "bootstrap.servers": "bootstrap.servers"
                }
            }
        }

        result = target.create_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, "CREATE TABLE `name` (`field1` field1,`field2` field2) WITH "\
            "('connector' = 'kafka','format' = 'json', 'topic' = 'topic'"\
            ",'properties.bootstrap.servers' = 'bootstrap.servers');")


    def test_create_ddl_from_beamsqltable_notopic(self):
        """
        test create_ddl_from_beamsqltable with no topic in spec
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "kafka",
            "name": "name",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ],
            "value": {
                "format": "json"
            },
            "kafka": {
                "properties": {
                    "bootstrap.servers": "bootstrap.servers"
                }
            }
        }

        result = target.create_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, None)


    def test_create_ddl_from_beamsqltable_noname(self):
        """
        test create_ddl_from_beamsqltable with no name in spec
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "kafka",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ],
            "value": {
                "format": "json"
            },
            "kafka": {
                "topic": "topic",
                "properties": {
                    "bootstrap.servers": "bootstrap.servers"
                }
            }
        }

        result = target.create_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, "CREATE TABLE `name` (`field1` field1,`field2` field2) WITH "\
            "('connector' = 'kafka','format' = 'json', 'topic' = 'topic'"\
            ",'properties.bootstrap.servers' = 'bootstrap.servers');")




    def test_create_ddl_from_beamsqltable_nobootstrap(self):
        """
        test creae_ddl_from_beamsqltable with no bootstrap in spec
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "kafka",
            "name": "name",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ],
            "value": {
                "format": "json"
            },
            "kafka": {
                "topic": "topic",
                "properties": {
                }
            }
        }

        result = target.create_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, None)


    def test_create_ddl_from_beamsqltable_nokafka(self):
        """
        test create_ddl_from_beamsqltable with no kafka in spec
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "kafka",
            "name": "name",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ],
            "value": {
                "format": "json"
            }
        }

        result = target.create_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, None)


    def test_create_ddl_from_beamsqltable_novalue(self):
        """
        test create_ddl_from_beamsqltable wiht no value in spec
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "kafka",
            "name": "name",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ]
        }

        result = target.create_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, None)

    def test_create_upsert_ddl_from_beamsqltable(self):
        """
        test create_upsert_ddl_from_beamsqltable
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "upsert-kafka",
            "name": "name",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ],
            "primaryKey": ["primaryKey"],
            "value": {
                "format": "json"
            },
            "kafka": {
                "topic": "topic",
                "key.format":  "json",
                "properties": {
                    "bootstrap.servers": "bootstrap.servers"
                }
            }
        }

        result = target.create_upsert_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, "CREATE TABLE `name` (`field1` field1,`field2` field2,"\
            " PRIMARY KEY (primaryKey) NOT ENFORCED) WITH "\
            "('connector' = 'upsert-kafka','value.format' = 'json', 'topic' = 'topic',"\
            " 'key.format' = 'json',"\
            "'properties.bootstrap.servers' = 'bootstrap.servers');")


    def test_create_upsert_ddl_from_beamsqltable_novalue(self):
        """
        test create_upsert_ddl_from_beamsqltable with no value in spec
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "upsert-kafka",
            "name": "name",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ],
            "primaryKey": ["primaryKey"],
            "kafka": {
                "topic": "topic",
                "key.format":  "json",
                "properties": {
                    "bootstrap.servers": "bootstrap.servers"
                }
            }
        }

        result = target.create_upsert_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, None)

    def test_create_upsert_ddl_from_beamsqltable_noname(self):
        """
        test create_upsert_ddl_from_beamsqltable with no name in spec
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "upsert-kafka",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ],
            "primaryKey": ["primaryKey"],
            "value": {
                "format": "json"
            },
            "kafka": {
                "topic": "topic",
                "key.format":  "json",
                "properties": {
                    "bootstrap.servers": "bootstrap.servers"
                }
            }
        }

        result = target.create_upsert_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, "CREATE TABLE `name` (`field1` field1,`field2` field2,"\
            " PRIMARY KEY (primaryKey) NOT ENFORCED) WITH "\
            "('connector' = 'upsert-kafka','value.format' = 'json', 'topic' = 'topic',"\
            " 'key.format' = 'json',"\
            "'properties.bootstrap.servers' = 'bootstrap.servers');")

    def test_create_upsert_ddl_from_beamsqltable_fail(self):
        """
        test create_upsert_ddl_from_beamsqltable
        """
        global GLOBAL_MESSAGE
        GLOBAL_MESSAGE = ""
        beamsqltable = Bunch()
        beamsqltable.metadata = Bunch()
        beamsqltable.metadata.name = "name"
        beamsqltable.metadata.namespace = "namespace"
        beamsqltable.spec = {
            "connector": "upsert-kafka",
            "name": "name",
            "fields": [
                {"field1": "field1"},
                {"field2": "field2"}
            ],
            "value": {
                "format": "json"
            },
            "kafka": {
                "topic": "topic",
                "key.format":  "json",
                "properties": {
                    "bootstrap.servers": "bootstrap.servers"
                }
            }
        }

        result = target.create_upsert_kafka_ddl(beamsqltable, Logger())
        self.assertEqual(result, None)

    def test_create_create_view(self):
        """
        test create_view
        """
        beamsqlview = Bunch()
        beamsqlview.metadata = Bunch()
        beamsqlview.metadata.name = "name"
        beamsqlview.metadata.namespace = "namespace"
        beamsqlview.spec = {
            "name": "name",
            "sqlstatement": "sqlstatement"
        }

        result = target.create_view(beamsqlview)
        self.assertEqual(result, "CREATE VIEW `name` AS sqlstatement;")

if __name__ == '__main__':
    unittest.main()
