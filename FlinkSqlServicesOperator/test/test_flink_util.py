"""
Unittest for flink_util.yp
"""
from unittest import TestCase
import unittest
from bunch import Bunch
from mock import patch
import requests

import flink_util as target


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

def raise_for_status_success():
    """
    mock for successful status
    """
    return


def raise_for_status_fail():
    """
    mock for unsuccessful status get
    """
    raise requests.exceptions.HTTPError

def get_json():
    """
    retrieve empty JSON
    """
    return "{}"

def get_json_status():
    """
    retrieve JSON with status
    """
    return {'status': {
        'id': 'id'
        },
        'operation': {
            'location': "location"
        }
    }

def get_json_request_id():
    """
    result of get request
    """
    requestid = Bunch()
    requestid['request-id'] = 'request-id'
    return requestid

def request_get_successful(url):
    """
    get response from get request
    """
    response = Bunch()
    response.raise_for_status = raise_for_status_success
    response.json = get_json
    response.status_code = 200
    return response

def request_get_failed(url):
    """
    get request failed
    """
    response = Bunch()
    response.raise_for_status = raise_for_status_fail
    response.json = get_json
    response.status_code = 404
    return response

def request_get_successful_job_status(url):
    """
    get job status
    """
    response = Bunch()
    response.raise_for_status = raise_for_status_success
    response.json = get_json_status
    response.status_code = 200
    return response

def request_post_successful(url, json):
    """
    post request
    """
    response = Bunch()
    response.raise_for_status = raise_for_status_success
    response.json = get_json_request_id
    response.status_code = 202
    return response

def request_patch_successful(url):
    """
    send patch request
    """
    response = Bunch()
    response.status_code = 202
    return response

class TestJobStatus(TestCase):
    """
    Test class for job stati
    """
    @patch('requests.get', request_get_successful)
    def test_job_status(self):
        """
        test job_status
        """
        job_id ="job_id"
        response = target.get_job_status(Logger(), job_id)
        self.assertEqual(response, "{}")

    @patch('requests.get', request_get_successful_job_status)
    def test_get_savepoint_state(self):
        """
        test for get_savepoint_state
        """
        job_id ="job_id"
        savepoint_dir = "savepoint_dir"
        response = target.get_savepoint_state(Logger(), job_id, savepoint_dir)
        self.assertEqual(response, {'status': 'id', 'location': 'location'})

    # pylint: disable=global-statement,no-self-use
    @patch('requests.patch', request_patch_successful)
    def test_cancel_job(self):
        """
        test for cancel_job
        """
        job_id ="job_id"
        target.cancel_job(Logger(), job_id)

    @patch('requests.post', request_post_successful)
    def test_stop_job(self):
        """
        test for stop_job
        """
        job_id ="job_id"
        savepoint_dir = "savepoint_dir"
        response = target.stop_job(Logger(), job_id, savepoint_dir)
        self.assertEqual(response, 'request-id')

    #@patch('requests.get', request_get_successful_job_status)
    #def test_get_savepoint_state(self):
    #    """
    #    test for get_savepoint
    #    """
    #    job_id ="job_id"
    #    savepoint_dir = "savepoint_dir"
    #    response = target.get_savepoint_state(Logger(), job_id, savepoint_dir)
    #    self.assertEqual(response, {'status': 'id', 'location': 'location'})

    @patch('requests.get', request_get_failed)
    def test_get_savepoint_state_fail(self):
        """
        test for get_savepoint_state with fail
        """
        job_id ="job_id"
        savepoint_dir = "savepoint_dir"
        response = target.get_savepoint_state(Logger(), job_id, savepoint_dir)
        self.assertEqual(response, {'status': 'NOT_FOUND', 'location': None})

if __name__ == '__main__':
    unittest.main()
