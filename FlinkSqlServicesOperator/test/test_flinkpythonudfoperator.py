#
# Copyright (c) 2023 Intel Corporation
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
from bunch import Bunch
from mock import patch
import kopf
import requests
import os.path

import flinkpythonudfoperator as target


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

def postfile_unsuccessful(spec, logger):
    raise target.DeploymentFailedException('No Connection!')

def postfile_successful(spec, logger):
    pass

class TestInit(TestCase):
    """unit test class for kopf init"""
    @patch('flinkpythonudfoperator.post_file', postfile_unsuccessful)
    @patch('kopf.info', kopf_info)
    def test_init_fail(self):
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
        self.assertEqual(patchx.status['state'], "FAILED")

    @patch('flinkpythonudfoperator.post_file', postfile_successful)
    @patch('kopf.info', kopf_info)
    def test_init_successful(self):
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
        self.assertEqual(patchx.status['state'], "SYNCED")

class TestUpdate(TestCase):
    """unit test class for kopf update"""
    @patch('flinkpythonudfoperator.post_file', postfile_unsuccessful)
    @patch('kopf.info', kopf_info)
    def test_update_fail(self):
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
        result = target.update(body, body["spec"], patchx, Logger())
        self.assertIsNotNone(result['updatedOn'])
        self.assertEqual(patchx.status['state'], "FAILED")

    @patch('flinkpythonudfoperator.post_file', postfile_successful)
    @patch('kopf.info', kopf_info)
    def test_update_success(self):
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
        result = target.update(body, body["spec"], patchx, Logger())
        self.assertIsNotNone(result['updatedOn'])
        self.assertEqual(patchx.status['state'], "SYNCED")


def check_file_state_fail(name):
    raise requests.RequestException('Could not request')

def check_file_state_success(name):
    return 200

def check_file_state_notfound(name):
    return 404

class TestMonitor(TestCase):
    """unit test class for kopf monitor"""
    @patch('flinkpythonudfoperator.check_file_state', check_file_state_fail)
    @patch('flinkpythonudfoperator.post_file', postfile_unsuccessful)
    @patch('kopf.info', kopf_info)
    def test_monitor_fail(self):
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {}
        }
        patchx = Bunch()
        patchx.status = {}
        result = target.monitor(patchx, Logger(), body, body["spec"])
        self.assertEqual(patchx.status['state'], "FAILED")

    @patch('flinkpythonudfoperator.check_file_state', check_file_state_notfound)
    @patch('flinkpythonudfoperator.post_file', postfile_successful)
    @patch('kopf.info', kopf_info)
    def test_monitor_notfound_success(self):
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {}
        }
        patchx = Bunch()
        patchx.status = {}
        result = target.monitor(patchx, Logger(), body, body["spec"])
        self.assertEqual(patchx.status['state'], "SYNCED")
        self.assertIsNotNone(result['monitoredOn'])

    @patch('flinkpythonudfoperator.check_file_state', check_file_state_notfound)
    @patch('flinkpythonudfoperator.post_file', postfile_unsuccessful)
    @patch('kopf.info', kopf_info)
    def test_monitor_notfound_fail(self):
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {}
        }
        patchx = Bunch()
        patchx.status = {}
        result = target.monitor(patchx, Logger(), body, body["spec"])
        self.assertEqual(patchx.status['state'], "FAILED")


def requests_get_successful(url, timeout):
    assert(os.path.basename(url) == 'filename')
    result = Bunch()
    result.status_code = 200
    return result

def requests_post_successful(url, timeout, data, headers):
    assert(os.path.basename(url) == 'filename_version')
    result = Bunch()
    result.status_code = 201
    return result

def requests_post_fail(url, timeout, data, headers):
    assert(os.path.basename(url) == 'filename_version')
    result = Bunch()
    result.status_code = 500
    return result

class TestCheckFileState(TestCase):
    """unit test class for check_file_state"""
    @patch('requests.get', requests_get_successful)
    def test_check_request_successful(self):

        result = target.check_file_state('filename')
        self.assertEqual(result, 200)


class TestCheckPostFile(TestCase):
    """unit test class for check_file_state"""
    @patch('requests.post', requests_post_successful)
    def test_check_request_successful(self):
        spec = {
            "filename": "filename",
            "version": "version",
            "class": "class"
        }
        result = target.post_file(spec, Logger())


    @patch('requests.post', requests_post_fail)
    def test_check_request_fail(self):
        spec = {
            "filename": "filename",
            "version": "version",
            "class": "class"
        }
        with self.assertRaises(target.DeploymentFailedException):
            result = target.post_file(spec, Logger())