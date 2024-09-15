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


class TestMonitoring(TestCase):
    """Unit test class for monitoring"""
    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def create_ddl_from_beamsqltables(beamsqltable, logger):
        """mock successful DDL creation"""
        return "DDL;"

    # pylint: disable=no-self-use, unused-argument, no-self-argument
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

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def submit_statementset_failed(fullname, statementset, logger):
        """mock submission failed"""
        raise target.DeploymentFailedException("Mock submission failed")

    # pylint: disable=no-self-use, unused-argument, no-self-argument
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

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def create_sets(spec, body, namespace, name, logger):
        """mock create sets"""
        return "sets"

    # pylint: disable=no-self-use, unused-argument, no-self-argument, too-many-arguments
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
    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def update_status_nochange(body, patchx, logger):
        """mock update with no status change"""

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def update_status_change(body, patchx, logger):
        """mock job status change"""
        patchx.status["state"] = "CANCELED"

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def cancel_job(logger, job_id):
        """mock cancel job successful"""

    # pylint: disable=no-self-use, unused-argument, no-self-argument
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

class TestUpdate(TestCase):
    """unit test class to test updates"""

    # pylint: disable=no-self-use, unused-argument, no-self-argument, global-statement
    def cancel_job(logger, job_id):
        """mock cancel_job"""
        global JOB_CANCELED
        JOB_CANCELED = True

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def get_job_status(logger, job_id):
        """mock get_job_status running"""
        return {
            "state": "RUNNING"
        }

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def get_job_status_not_running(logger, job_id):
        """mock get job_status unknown"""
        return {
            "state": "UNKNOWN"
        }

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def cancel_job_and_get_state(logger, body, patchx):
        """mock cancel_job_and_get state successful"""

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def cancel_job_and_get_state_fail(logger, body, patchx):
        """mock cancel_job with state fail"""
        raise requests.exceptions.RequestException("Error")

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def stop_job(logger, job_id, savepoint_dir):
        """mock stop_job"""
        return "savepoint_id"

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def get_savepoint_state_successful(logger, job_id, savepoint_id):
        """mock get savepoint_state return successful"""
        return {
            "status": "SUCCESSFUL",
            "location": "location"
        }

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def get_savepoint_state_in_progress(logger, job_id, savepoint_id):
        """mock get_savepoint_state is in progress"""
        return {
            "status": "IN_PROGRESS",
            "location": "location"
        }

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def get_savepoint_state_not_found(logger, job_id, savepoint_id):
        """mock savepoint_state_not_found"""
        return {
            "status": "NOT_FOUND",
            "location": "location"
        }

    # pylint: disable=no-self-use, unused-argument, no-self-argument
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
    # pylint: disable=no-self-use, no-self-argument
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

    # pylint: disable=no-self-use, no-self-argument
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

    # pylint: disable=no-self-use, no-self-argument
    def get_job_status(logger, jobid):
        """mock get job status"""
        return {
            "state": "ok"
        }
    # pylint: disable=no-self-use, no-self-argument
    def get_job_status_none(logger, jobid):
        """mock no job_status found"""
        return None

    # pylint: disable=no-self-use, no-self-argument
    def send_exception(test, json, timeout=0):
        """mock send_exception"""
        raise requests.RequestException("Error")

    # pylint: disable=no-self-use, no-self-argument
    def get_job_from_name(logger, jobname):
        """mock get_job_from_name"""
        return "jobid"
    # pylint: disable=no-self-use, no-self-argument
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
if __name__ == '__main__':
    unittest.main()
