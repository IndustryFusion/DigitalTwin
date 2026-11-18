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
"""
Unit tests for beamsqlstatementsetoperator.py
"""
from unittest import TestCase
import unittest
from bunch_py3 import Bunch
from mock import patch
import kopf
import requests

import beamsqlstatementsetoperator as target


# Mock functions
# --------------

class Logger():
    """
    mock for Logger
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

    def warning(self, message):
        """
        mock for warnings
        """

# pylint: disable=unused-argument
def kopf_info(body, reason, message):
    """
    mock for kopf.info
    """

def check_readiness():
    """mock for check_rediness - successful"""
    return True

class TestInit(TestCase):
    """unit test class for kopf init"""
    @patch('kopf.info', kopf_info)
    def test_init(self):
        """test init of resource"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {}
        }
        patchx = Bunch()
        patchx.status = {}
        result = target.create(body, body["spec"], patchx, Logger())
        self.assertIsNotNone(result['createdOn'])
        self.assertEqual(patchx.status['state'], "INITIALIZED")
        self.assertIsNone(patchx.status['job_id'])


# Validation (openspec gh-955-flink-sql-validation) has its own tests in
# TestValidation; here every request is taken as valid.
@patch('beamsqlstatementsetoperator.refuse_if_invalid', lambda *a: False)
class TestMonitoring(TestCase):
    """Unit test class for monitoring"""
    @staticmethod
    # pylint: disable=unused-argument
    def create_ddl_from_beamsqltables(beamsqltable, logger):
        """mock successful DDL creation"""
        return "DDL;"

    @staticmethod
    # pylint: disable=unused-argument
    def submit_statementset_successful(fullname, statementset, logger):
        """mock successful statementset creation"""
        # Keeping normal assert statement as this does not seem to
        # be an object method after mocking
        #assert statementset == "SET pipeline.name = 'namespace/name';\nDDL;" \
        #    "\nBEGIN STATEMENT SET;\nselect;\nEND;"
        assert statementset == {'sqlsettings': [{'pipeline.name': 'namespace/name'}],
                                'tables': ['DDL;'],
                                'sqlstatementset': ['select;']}
        return "job_id"

    @staticmethod
    # pylint: disable=unused-argument
    def submit_statementset_failed(fullname, statementset, logger):
        """mock submission failed"""
        raise target.DeploymentFailedException("Mock submission failed")

    @staticmethod
    # pylint: disable=unused-argument
    def update_status_not_found(body, patchx, logger):
        """mock status not found"""
        patchx.status["state"] = "NOT_FOUND"

    @patch('beamsqlstatementsetoperator.tables_and_views.create_ddl_from_beamsqltables',
           create_ddl_from_beamsqltables)
    @patch('beamsqlstatementsetoperator.deploy_statementset',
           submit_statementset_successful)
    def test_update_submission(self):
        """test update submissino successful"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"]
            },
            "status": {
                "state": "INITIALIZED",
                "job_id": None
            }
        }

        patchx = Bunch()
        patchx.status = {}

        beamsqltables = {("namespace", "table"): ({}, {})}
        target.monitor(beamsqltables, None, None, patchx,  Logger(),
                       body, body["spec"])
        self.assertEqual(patchx.status['state'], "DEPLOYING")
        self.assertEqual(patchx.status['job_id'], "job_id")

    @patch('beamsqlstatementsetoperator.tables_and_views.create_ddl_from_beamsqltables',
           create_ddl_from_beamsqltables)
    @patch('beamsqlstatementsetoperator.deploy_statementset',
           submit_statementset_successful)
    def test_monitor_finished(self):
        """test monitor finished"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"]
            },
            "status": {
                "state": "FINISHED",
                "job_id": None
            }
        }

        patchx = Bunch()
        patchx.status = {}

        beamsqltables = {("namespace", "table"): ({}, {})}

        target.monitor(beamsqltables, None, None, patchx,  Logger(),
                       body, body["spec"])
        self.assertNotIn('state', patchx.status)
        self.assertNotIn('job_id', patchx.status)

    @patch('beamsqlstatementsetoperator.tables_and_views.create_ddl_from_beamsqltables',
           create_ddl_from_beamsqltables)
    @patch('beamsqlstatementsetoperator.deploy_statementset',
           submit_statementset_failed)
    def test_update_submission_failure(self):
        """test update with submission failure"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"]
            },
            "status": {
                "state": "INITIALIZED",
                "job_id": None
            }
        }

        patchx = Bunch()
        patchx.status = {}

        beamsqltables = {("namespace", "table"): ({}, {})}
        try:
            target.monitor(beamsqltables, None, None, patchx,  Logger(),
                           body, body["spec"])
        except kopf.TemporaryError:
            pass
        self.assertEqual(patchx.status['state'], "DEPLOYMENT_FAILURE")
        self.assertIsNone(patchx.status['job_id'])

    @patch('beamsqlstatementsetoperator.tables_and_views.create_ddl_from_beamsqltables',
           create_ddl_from_beamsqltables)
    @patch('beamsqlstatementsetoperator.deploy_statementset',
           submit_statementset_failed)
    def test_update_table_failure(self):
        """test update table with failure"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"]
            },
            "status": {
                "state": "INITIALIZED",
                "job_id": None
            }
        }

        patchx = Bunch()
        patchx.status = {}

        beamsqltables = {}
        with self.assertRaises(kopf.TemporaryError) as cmx:
            target.monitor(beamsqltables, None, None, patchx, Logger(),
                           body, body["spec"])
            self.assertTrue(str(cmx.exception).startswith(
                "Table DDLs could not be created for namespace/name."))

    @patch('beamsqlstatementsetoperator.tables_and_views.create_ddl_from_beamsqltables',
           create_ddl_from_beamsqltables)
    @patch('beamsqlstatementsetoperator.deploy_statementset',
           submit_statementset_failed)
    @patch('beamsqlstatementsetoperator.refresh_state', update_status_not_found)
    def test_update_handle_unknown(self):
        """test handling unknow job state while update"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"]
            },
            "status": {
                "state": "RUNNING",
                "job_id": "job_id"
            }
        }

        patchx = Bunch()
        patchx.status = {}

        beamsqltables = {}

        target.monitor(beamsqltables, None, None, patchx, Logger(),
                       body, body["spec"])
        self.assertEqual(patchx.status["state"], "INITIALIZED")
        self.assertIsNone(patchx.status["job_id"])

    @staticmethod
    # pylint: disable=unused-argument
    def create_sets(spec, body, namespace, name, logger):
        """mock create sets"""
        return "sets"

    @staticmethod
    # pylint: disable=unused-argument, too-many-arguments
    def create_tables(beamsqltables, spec, body, namespace, name, logger):
        """mock creation of tables"""
        return "tables"

    @patch('beamsqlstatementsetoperator.create_sets', create_sets)
    @patch('beamsqlstatementsetoperator.create_tables', create_tables)
    def test_update_handle_views(self):
        """test handling view during update"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"],
                "views": ["view"]
            },
            "status": {
                "state": "INITIALIZED",
                "job_id": "job_id"
            }
        }

        patchx = Bunch()
        patchx.status = {}

        beamsqltables = {}
        beamsqlviews = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "sqlstatement": "sqlstatement"
        }
        with self.assertRaises(kopf.TemporaryError):
            target.monitor(beamsqltables, beamsqlviews, None, patchx, Logger(),
                       body, body["spec"])

class TestDeletion(TestCase):
    """Unit test class for job deletion tests"""
    @staticmethod
    # pylint: disable=unused-argument
    def update_status_nochange(body, patchx, logger):
        """mock update with no status change"""

    @staticmethod
    # pylint: disable=unused-argument
    def update_status_change(body, patchx, logger):
        """mock job status change"""
        patchx.status["state"] = "CANCELED"

    @staticmethod
    # pylint: disable=unused-argument
    def cancel_job(logger, job_id):
        """mock cancel job successful"""

    @staticmethod
    # pylint: disable=unused-argument
    def cancel_job_error(logger, job_id):
        """mock cancel_job with error"""
        raise kopf.TemporaryError("Could not cancel job")

    @patch('kopf.info', kopf_info)
    def test_canceled_delete(self):
        """test delete job with CANCELED job"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"]
            },
            "status": {
                "state": "CANCELED",
                "job_id": "job_id"
            }
        }
        patchx = Bunch()
        patchx.status = {}

        target.delete(body, body["spec"], patchx, Logger())
        self.assertEqual(patchx.status, {})

    @patch('kopf.info', kopf_info)
    def test_delete_finished(self):
        """test delete job with FINISHED job"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"]
            },
            "status": {
                "state": "FINISHED",
                "job_id": "job_id"
            }
        }
        patchx = Bunch()
        patchx.status = {}

        target.delete(body, body["spec"], patchx, Logger())
        self.assertEqual(patchx.status, {})

    @patch('kopf.info', kopf_info)
    @patch('beamsqlstatementsetoperator.refresh_state', update_status_nochange)
    def test_canceling_delete(self):
        """test cancel flink job without status change"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"]
            },
            "status": {
                "state": "CANCELING",
                "job_id": "job_id"
            }
        }
        patchx = Bunch()
        patchx.status = {"state": ""}

        with self.assertRaises(kopf.TemporaryError) as cmx:
            target.delete(body, body["spec"], patchx, Logger())
            self.assertTrue(str(cmx.exception).startswith("Cancelling,"))

    @patch('kopf.info', kopf_info)
    @patch('beamsqlstatementsetoperator.refresh_state', update_status_change)
    # pylint: disable=no-self-use
    def test_canceling_delete_change(self):
        """test cancel flink job with CANCELING state"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"]
            },
            "status": {
                "state": "CANCELING",
                "job_id": "job_id"
            }
        }
        patchx = Bunch()
        patchx.status = {"state": ""}

        target.delete(body, body["spec"], patchx, Logger())

    @patch('flink_util.cancel_job', cancel_job)
    @patch('beamsqlstatementsetoperator.refresh_state', update_status_nochange)
    @patch('kopf.info', kopf_info)
    def test_canceling_delete_flink_ok(self):
        """test delete flink job successful"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"]
            },
            "status": {
                "state": "RUNNING",
                "job_id": "job_id"
            }
        }
        patchx = Bunch()
        patchx.status = {"state": ""}

        with self.assertRaises(kopf.TemporaryError) as cmx:
            target.delete(body, body["spec"], patchx, Logger())
            self.assertTrue(str(cmx.exception).startswith("Waiting for"))
        self.assertEqual(patchx.status["state"], "CANCELING")

    @patch('flink_util.cancel_job', cancel_job_error)
    @patch('kopf.info', kopf_info)
    def test_canceling_delete_flink_error(self):
        """test deleting flink target unsuccessful"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "sqlstatements": ["select;"],
                "tables": ["table"]
            },
            "status": {
                "state": "RUNNING",
                "job_id": "job_id"
            }
        }
        patchx = Bunch()
        patchx.status = {"state": ""}

        with self.assertRaises(kopf.TemporaryError) as cmx:
            target.delete(body, body["spec"], patchx, Logger())
            self.assertTrue(str(cmx.exception).startswith("Error trying"))
        self.assertNotEqual(patchx.status["state"], "CANCELING")

JOB_CANCELED = False

@patch('beamsqlstatementsetoperator.refuse_if_invalid', lambda *a: False)
@patch('beamsqlstatementsetoperator.compose_statementset', lambda *a: {})
class TestUpdate(TestCase):
    """unit test class to test updates"""

    @staticmethod
    # pylint: disable=unused-argument, global-statement
    def cancel_job(logger, job_id):
        """mock cancel_job"""
        global JOB_CANCELED
        JOB_CANCELED = True

    @staticmethod
    # pylint: disable=unused-argument
    def get_job_status(logger, job_id):
        """mock get_job_status running"""
        return {
            "state": "RUNNING"
        }

    @staticmethod
    # pylint: disable=unused-argument
    def get_job_status_not_running(logger, job_id):
        """mock get job_status unknown"""
        return {
            "state": "UNKNOWN"
        }

    @staticmethod
    # pylint: disable=unused-argument
    def cancel_job_and_get_state(logger, body, patchx):
        """mock cancel_job_and_get state successful"""

    @staticmethod
    # pylint: disable=unused-argument
    def cancel_job_and_get_state_fail(logger, body, patchx):
        """mock cancel_job with state fail"""
        raise requests.exceptions.RequestException("Error")

    @staticmethod
    # pylint: disable=unused-argument
    def stop_job(logger, job_id, savepoint_dir):
        """mock stop_job"""
        return "savepoint_id"

    @staticmethod
    # pylint: disable=unused-argument
    def get_savepoint_state_successful(logger, job_id, savepoint_id):
        """mock get savepoint_state return successful"""
        return {
            "status": "SUCCESSFUL",
            "location": "location"
        }

    @staticmethod
    # pylint: disable=unused-argument
    def get_savepoint_state_in_progress(logger, job_id, savepoint_id):
        """mock get_savepoint_state is in progress"""
        return {
            "status": "IN_PROGRESS",
            "location": "location"
        }

    @staticmethod
    # pylint: disable=unused-argument
    def get_savepoint_state_not_found(logger, job_id, savepoint_id):
        """mock savepoint_state_not_found"""
        return {
            "status": "NOT_FOUND",
            "location": "location"
        }

    @staticmethod
    # pylint: disable=unused-argument
    def add_message(logger, body, patchx, reason, mtype):
        """mock add_message"""

    @patch('kopf.info', kopf_info)
    @patch('flink_util.cancel_job', cancel_job)
    @patch('flink_util.get_job_status', get_job_status)
    # pylint: disable=global-statement
    def test_cancel_job_and_get_state_running(self):
        """test cancel_job_and_get_state with getting job_state RUNNING"""
        global JOB_CANCELED
        body = {
            "status": {
                "job_id": "job_id"
            }
        }
        JOB_CANCELED = False
        job_state = target.cancel_job_and_get_state(Logger(), body, None)
        self.assertEqual("RUNNING", job_state)
        self.assertEqual(True, JOB_CANCELED)




    @patch('kopf.info', kopf_info)
    @patch('flink_util.cancel_job', cancel_job)
    @patch('flink_util.get_job_status', get_job_status_not_running)
    # pylint: disable=global-statement
    def test_cancel_job_and_get_state_not_running(self):
        """test cancel_job_and_get_state with non running job"""
        global JOB_CANCELED
        body = {
            "status": {
                "job_id": "job_id"
            }
        }
        JOB_CANCELED = False
        job_state = target.cancel_job_and_get_state(Logger(), body, None)
        self.assertEqual("UNKNOWN", job_state)
        self.assertEqual(False, JOB_CANCELED)


    @patch('kopf.info', kopf_info)
    @patch('beamsqlstatementsetoperator.cancel_job_and_get_state', cancel_job_and_get_state)
    def test_update_no_savepoint(self):
        """test update without savepoint when update strategy is not given"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
            },
            "status": {
                "job_id": "job_id",
                "state": "RUNNING",
            }
        }
        patchx = Bunch()
        patchx.status = {}
        target.update(body, body["spec"], patchx, Logger())
        self.assertEqual(patchx.status["state"], "UPDATING")
        self.assertIsNone(patchx.status["savepoint_id"])
        self.assertIsNone(patchx.status["location"])


    @patch('kopf.info', kopf_info)
    @patch('beamsqlstatementsetoperator.cancel_job_and_get_state', cancel_job_and_get_state)
    def test_update_none_savepoint(self):
        """test update without savepoint successful"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "updateStrategy": None
            },
            "status": {
                "job_id": "job_id",
                "state": "RUNNING",
            }
        }
        patchx = Bunch()
        patchx.status = {}
        target.update(body, body["spec"], patchx, Logger())
        self.assertEqual(patchx.status["state"], "UPDATING")
        self.assertIsNone(patchx.status["savepoint_id"])
        self.assertIsNone(patchx.status["location"])

    @patch('kopf.info', kopf_info)
    @patch('beamsqlstatementsetoperator.cancel_job_and_get_state', cancel_job_and_get_state_fail)
    def test_update_none_savepoint_fail(self):
        """test update without savepoint fail"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "updateStrategy": None
            },
            "status": {
                "job_id": "job_id",
                "state": "RUNNING",
            }
        }
        patchx = Bunch()
        patchx.status = {}
        with self.assertRaises(kopf.TemporaryError):
            target.update(body, body["spec"], patchx, Logger())

    @patch('kopf.info', kopf_info)
    @patch('flink_util.stop_job', stop_job)
    @patch('flink_util.get_savepoint_state', get_savepoint_state_successful)
    @patch('beamsqlstatementsetoperator.add_message', add_message)
    def test_update_savepoint_successful(self):
        """test update_savepoint successful"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "updateStrategy": "savepoint"
            },
            "status": {
                "job_id": "job_id",
                "state": "RUNNING",
            }
        }
        patchx = Bunch()
        patchx.status = {}
        target.update(body, body["spec"], patchx, Logger())
        self.assertEqual(patchx.status["savepoint_id"], "savepoint_id")
        self.assertEqual(patchx.status["state"], "UPDATING")
        self.assertEqual(patchx.status["location"], "location")


    @patch('kopf.info', kopf_info)
    @patch('flink_util.stop_job', stop_job)
    @patch('flink_util.get_savepoint_state', get_savepoint_state_in_progress)
    @patch('beamsqlstatementsetoperator.add_message', add_message)
    def test_update_savepoint_in_progress(self):
        """test update_savepoint when savepointing is in progress"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "updateStrategy": "savepoint"
            },
            "status": {
                "job_id": "job_id",
                "state": "RUNNING",
            }
        }
        patchx = Bunch()
        patchx.status = {}
        with self.assertRaises(kopf.TemporaryError):
            target.update(body, body["spec"], patchx, Logger())
        self.assertEqual(patchx.status["savepoint_id"], "savepoint_id")
        self.assertEqual(patchx.status["state"], "SAVEPOINTING")


    @patch('kopf.info', kopf_info)
    @patch('flink_util.stop_job', stop_job)
    @patch('flink_util.get_savepoint_state', get_savepoint_state_not_found)
    @patch('beamsqlstatementsetoperator.add_message', add_message)
    def test_update_savepoint_not_found(self):
        """test savepoint update strategy where savepoint not found"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "updateStrategy": "savepoint"
            },
            "status": {
                "job_id": "job_id",
                "state": "RUNNING",
            }
        }
        patchx = Bunch()
        patchx.status = {}
        target.update(body, body["spec"], patchx, Logger())
        self.assertIsNone(patchx.status["savepoint_id"])
        self.assertEqual(patchx.status["state"], "RUNNING")
        self.assertIsNone(patchx.status["location"])

class TestHelpers(TestCase):
    """unit test class for helpers"""
    @staticmethod
    def send_successful(test, json, timeout=0):
        """mock send job successful"""
        def jsonp():
            jsonres = Bunch()
            jsonres.job_id = "jobid"
            return jsonres
        response = Bunch()
        response.status_code = 200
        response.json = jsonp
        return response

    @staticmethod
    def send_unsuccessful(test, json, timeout=0):
        """mock send job unsuccessful"""
        def jsonp():
            jsonres = Bunch()
            jsonres.job_id = "jobid"
            return jsonres
        response = Bunch()
        response.status_code = 400
        response.json = jsonp
        return response

    @staticmethod
    def get_job_status(logger, jobid):
        """mock get job status"""
        return {
            "state": "ok"
        }
    @staticmethod
    def get_job_status_none(logger, jobid):
        """mock no job_status found"""
        return None

    @staticmethod
    def send_exception(test, json, timeout=0):
        """mock send_exception"""
        raise requests.RequestException("Error")

    @staticmethod
    def get_job_from_name(logger, jobname):
        """mock get_job_from_name"""
        return "jobid"
    @staticmethod
    def get_no_job_from_name(logger, jobname):
        """mock get_job_from_name"""
        return None

    @patch('kopf.info', kopf_info)
    @patch('requests.post', send_successful)
    @patch('flink_util.get_job_from_name', get_job_from_name)
    # pylint: disable=no-self-use
    def test_deploy_statementset(self):
        """test deploy_statementset successful"""
        statementset = 'statementset'
        target.deploy_statementset('jobname', statementset, Logger())

    @patch('kopf.info', kopf_info)
    @patch('requests.post', send_unsuccessful)
    @patch('flink_util.get_job_from_name', get_no_job_from_name)
    def test_deploy_statementset_unsuccessful(self):
        """test deploy_statementset unsuccessful"""
        statementset = 'statementset'
        with self.assertRaises(target.DeploymentFailedException):
            target.deploy_statementset('jobname', statementset, Logger())

    @patch('kopf.info', kopf_info)
    @patch('requests.post', send_exception)
    @patch('flink_util.get_job_from_name', get_no_job_from_name)
    def test_deploy_statementset_exception(self):
        """test deploy_stamenetset with exception"""
        statementset = 'statementset'
        with self.assertRaises(target.DeploymentFailedException):
            target.deploy_statementset('jobid', statementset, Logger())

    def test_add_message(self):
        """test add_message with string message"""
        reason = 'reason'
        body = Bunch()
        body.status = Bunch()
        body.status.messages = []
        mtype = 'mtype'
        patchx = Bunch()
        patchx.status = {}
        target.add_message(Logger(), body, patchx, reason, mtype)
        self.assertEqual(patchx.status.get('messages')[0].get('message'), reason)

    def test_add_message_none(self):
        """"test add_message with None"""
        reason = 'reason'
        body = Bunch()
        body.status = Bunch()
        mtype = 'mtype'
        patchx = Bunch()
        patchx.status = {}
        target.add_message(Logger(), body, patchx, reason, mtype)
        self.assertEqual(patchx.status.get('messages')[0].get('message'), reason)

    @patch('flink_util.get_job_status', get_job_status)
    def test_get_job_state(self):
        """test get_job_state"""
        body = Bunch()
        body.status = {
            "job_id": "job_id"
        }
        job_state = target.get_job_state(Logger(), body)
        self.assertEqual(job_state, "ok")

    @patch('flink_util.get_job_status', get_job_status)
    def test_refresh_state(self):
        """test refresh_state"""
        body = Bunch()
        patchx = Bunch()
        patchx.status = {}
        body.status = { "job_id": "job_id" }

        target.refresh_state(body, patchx, Logger())
        self.assertEqual("ok", patchx.status.get('state'))
    @patch('flink_util.get_job_status', get_job_status_none)
    def test_refresh_state_none(self):
        """test refresh_state with return None"""
        body = Bunch()
        patchx = Bunch()
        patchx.status = {}
        body.status = { "job_id": "job_id" }

        target.refresh_state(body, patchx, Logger())
        self.assertEqual("UNKNOWN", patchx.status.get('state'))

def never_called(*args, **kwargs):
    """mock that must not be reached"""
    raise AssertionError("must not be called")


class Response():
    """mock for requests.Response"""
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.body = body

    def json(self):
        """mock json"""
        return self.body


REJECTED = {'valid': False, 'kind': 'statement', 'index': 1,
            'text': 'INSERT INTO x SELECT 1;', 'message': 'SQL parse failed.'}
REQUEST = {'sqlsettings': [], 'tables': [], 'sqlstatementset': ['INSERT INTO x SELECT 1;']}


def running_body(spec=None, validation=None):
    """a running statement set"""
    status = {"job_id": "job_id", "state": "RUNNING"}
    if validation is not None:
        status["validation"] = validation
    return Bunch({"metadata": {"name": "name", "namespace": "namespace"},
                  "spec": spec if spec is not None else {},
                  "status": Bunch(status)})


class TestValidation(TestCase):
    """openspec gh-955-flink-sql-validation: validate before cancelling or submitting"""

    def test_validate_statementset_answers(self):
        """200 is valid, 422 the rejection, anything else no answer"""
        with patch('requests.post', lambda *a, **k: Response(200, {'valid': True})):
            self.assertIsNone(target.validate_statementset(REQUEST, Logger()))
        with patch('requests.post', lambda *a, **k: Response(422, REJECTED)):
            self.assertEqual(target.validate_statementset(REQUEST, Logger()), REJECTED)
        with patch('requests.post', lambda *a, **k: Response(500)):
            with self.assertRaises(target.ValidationUnavailableException):
                target.validate_statementset(REQUEST, Logger())

        def unreachable(*a, **k):
            raise requests.exceptions.ConnectionError("down")
        with patch('requests.post', unreachable):
            with self.assertRaises(target.ValidationUnavailableException):
                target.validate_statementset(REQUEST, Logger())

    def test_refuse_if_invalid(self):
        """a rejection is recorded with Flink's message, a valid request too"""
        patchx = Bunch()
        patchx.status = {}
        with patch('beamsqlstatementsetoperator.validate_statementset', lambda s, l: REJECTED):
            self.assertTrue(target.refuse_if_invalid(REQUEST, running_body(), patchx, Logger()))
        self.assertEqual(patchx.status["state"], "VALIDATION_FAILED")
        self.assertEqual(patchx.status["validation"]["message"], 'SQL parse failed.')
        self.assertEqual(patchx.status["validation"]["digest"], target.digest_of(REQUEST))
        self.assertFalse(patchx.status["validation"]["valid"])
        patchx.status = {}
        with patch('beamsqlstatementsetoperator.validate_statementset', lambda s, l: None):
            self.assertFalse(target.refuse_if_invalid(REQUEST, running_body(), patchx, Logger()))
        self.assertEqual(patchx.status["validation"], {'digest': target.digest_of(REQUEST), 'valid': True})
        self.assertNotIn("state", patchx.status)

    def test_long_statements_are_cut_in_the_status(self):
        """the status holds at most MAX_VALIDATION_TEXT characters of the statement"""
        patchx = Bunch()
        patchx.status = {}
        rejected = dict(REJECTED, text='x' * 5000)
        with patch('beamsqlstatementsetoperator.validate_statementset', lambda s, l: rejected):
            target.refuse_if_invalid(REQUEST, running_body(), patchx, Logger())
        self.assertEqual(len(patchx.status["validation"]["text"]), target.MAX_VALIDATION_TEXT + 3)

    def test_the_same_statements_are_not_validated_again(self):
        """the recorded digest decides, without asking the gateway"""
        digest = target.digest_of(REQUEST)
        patchx = Bunch()
        patchx.status = {}
        with patch('beamsqlstatementsetoperator.validate_statementset', never_called):
            self.assertTrue(target.refuse_if_invalid(
                REQUEST, running_body(validation={'digest': digest, 'valid': False}), patchx, Logger()))
            self.assertFalse(target.refuse_if_invalid(
                REQUEST, running_body(validation={'digest': digest, 'valid': True}), patchx, Logger()))

    def test_a_gateway_without_answer_is_a_temporary_error(self):
        """nothing is cancelled while the gateway cannot be asked"""
        def unavailable(statementset, logger):
            raise target.ValidationUnavailableException("down")
        patchx = Bunch()
        patchx.status = {}
        with patch('beamsqlstatementsetoperator.validate_statementset', unavailable):
            with self.assertRaises(kopf.TemporaryError):
                target.refuse_if_invalid(REQUEST, running_body(), patchx, Logger())

    @patch('kopf.info', kopf_info)
    @patch('beamsqlstatementsetoperator.compose_statementset', lambda *a: REQUEST)
    @patch('beamsqlstatementsetoperator.validate_statementset', lambda s, l: REJECTED)
    @patch('beamsqlstatementsetoperator.cancel_job_and_get_state', never_called)
    @patch('flink_util.stop_job', never_called)
    def test_an_update_flink_rejects(self):
        """the job keeps running, nothing is submitted, the status says why"""
        for spec in ({}, {"updateStrategy": "savepoint"}):
            body = running_body(spec)
            patchx = Bunch()
            patchx.status = {}
            target.update(body, body["spec"], patchx, Logger())
            self.assertEqual(patchx.status["state"], "VALIDATION_FAILED")
            self.assertEqual(patchx.status["validation"]["message"], 'SQL parse failed.')
            self.assertNotIn("job_id", patchx.status)

    @patch('kopf.info', kopf_info)
    @patch('beamsqlstatementsetoperator.compose_statementset', lambda *a: REQUEST)
    @patch('beamsqlstatementsetoperator.validate_statementset', lambda s, l: None)
    @patch('beamsqlstatementsetoperator.cancel_job_and_get_state', lambda logger, body, patch: "RUNNING")
    def test_a_valid_update(self):
        """deployed as before: the old job is cancelled"""
        body = running_body()
        patchx = Bunch()
        patchx.status = {}
        target.update(body, body["spec"], patchx, Logger())
        self.assertEqual(patchx.status["state"], "UPDATING")
        self.assertTrue(patchx.status["validation"]["valid"])

    @patch('beamsqlstatementsetoperator.compose_statementset', lambda *a: REQUEST)
    @patch('beamsqlstatementsetoperator.validate_statementset', lambda s, l: REJECTED)
    @patch('beamsqlstatementsetoperator.deploy_statementset', never_called)
    def test_a_new_statement_set_flink_rejects(self):
        """no job is started"""
        body = Bunch({"metadata": {"name": "name", "namespace": "namespace"},
                      "spec": {"sqlstatements": ["INSERT INTO x SELECT 1;"]},
                      "status": Bunch({"state": "INITIALIZED", "job_id": None})})
        patchx = Bunch()
        patchx.status = {}
        target.monitor(None, None, None, patchx, Logger(), body, body["spec"])
        self.assertEqual(patchx.status["state"], "VALIDATION_FAILED")

    @patch('beamsqlstatementsetoperator.compose_statementset', lambda *a: REQUEST)
    @patch('beamsqlstatementsetoperator.validate_statementset', never_called)
    @patch('beamsqlstatementsetoperator.deploy_statementset', never_called)
    @patch('beamsqlstatementsetoperator.refresh_state', never_called)
    def test_a_rejection_waits_for_new_statements(self):
        """the same statements: no validation, no deployment, the state stays"""
        body = running_body(validation={'digest': target.digest_of(REQUEST), 'valid': False})
        body["status"]["state"] = "VALIDATION_FAILED"
        patchx = Bunch()
        patchx.status = {}
        target.monitor(None, None, None, patchx, Logger(), body, body["spec"])
        self.assertNotIn("state", patchx.status)

    @patch('beamsqlstatementsetoperator.compose_statementset', lambda *a: REQUEST)
    @patch('beamsqlstatementsetoperator.validate_statementset', lambda s, l: None)
    @patch('beamsqlstatementsetoperator.refresh_state', never_called)
    def test_fixed_after_a_rejection(self):
        """changed statements that validate are deployed: an old job is replaced"""
        cancelled = []
        with patch('beamsqlstatementsetoperator.cancel_job_and_get_state',
                   lambda logger, body, patch: cancelled.append(True) or "RUNNING"):
            body = running_body(validation={'digest': 'an older request', 'valid': False})
            body["status"]["state"] = "VALIDATION_FAILED"
            patchx = Bunch()
            patchx.status = {}
            target.monitor(None, None, None, patchx, Logger(), body, body["spec"])
            self.assertEqual(patchx.status["state"], "UPDATING")
            self.assertEqual(cancelled, [True])
        body = running_body(validation={'digest': 'an older request', 'valid': False})
        body["status"]["state"] = "VALIDATION_FAILED"
        body["status"]["job_id"] = None
        patchx = Bunch()
        patchx.status = {}
        target.monitor(None, None, None, patchx, Logger(), body, body["spec"])
        self.assertEqual(patchx.status["state"], "INITIALIZED")
        self.assertIsNone(patchx.status["job_id"])


if __name__ == '__main__':
    unittest.main()
