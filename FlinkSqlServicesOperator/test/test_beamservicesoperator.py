"""Unit test for beamservicesoperator.py"""
from unittest import TestCase, mock
import unittest
from bunch import Bunch
from mock import patch, mock_open
import aiounittest

import beamservicesoperator as target



# Mock functions
# --------------

class Logger():
    """mock logger class"""
    def info(self, message):
        """info"""

    def debug(self, message):
        """debug"""

    def error(self, message):
        """error"""

    def warning(self, message):
        """warning"""

def getjsn():
    """get job description RUNNING"""
    return {"jobs": [{"id": "id", "status": "RUNNING"}]}
def getjsn_fail():
    """get job description FAILED"""
    return {"jobs": [{"id": "id", "status": "FAILED"}]}
def getjson_post():
    """post filename"""
    return {"filename": "/filename"}
def getjson_put():
    """put name"""
    return {"name": "name"}
# pylint: disable=unused-argument
def kopf_info(body, reason, message):
    """mock kopf info"""

THAT = None

def check_readiness():
    """mock check readiniess successful"""
    return True

class TestCreate(TestCase):
    """Unit test class for create resource"""
    @patch('kopf.info', kopf_info)
    def test_create(self):
        """test create resource successful"""
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
        response = target.create(body, body["spec"], patchx)
        self.assertTrue(response.get("createdOn"))


class TestUpdates(aiounittest.AsyncTestCase):
    """Unit test class for updates"""
    @patch('kopf.info', kopf_info)
    async def test_update_none(self):
        """test update unsuccessful"""
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
        response = await target.updates(None, patchx, Logger(), body, body["spec"], body["status"])
        self.assertEqual(response, {'deployed': False, 'jobCreated': False})

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def delete_jar(body, jarfile):
        """mock delete jar"""
    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def deploy(body, spec, patchx):
        """mock deploy"""
        return "deploy"

    @patch('kopf.info', kopf_info)
    @patch('beamservicesoperator.delete_jar', delete_jar)
    @patch('beamservicesoperator.deploy', deploy)
    async def test_update_deployed(self):
        """test update deployed"""
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
                "job_id": "job_id",
                "updates": {},
                "jarfile": "jarfile"
            }
        }
        patchx = Bunch()
        patchx.status = {}
        response = await target.updates(None, patchx, Logger(), body, body["spec"], body["status"])
        self.assertEqual(response, {'deployed': True, 'jarId': 'deploy'})

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def check_readiness(body):
        """mock readiness of 1 slot"""
        return 1

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def create_job(body, spec, update_status):
        """mock create job successful"""
        return "job_id"

    @patch('kopf.info', kopf_info)
    @patch('beamservicesoperator.check_readiness', check_readiness)
    @patch('beamservicesoperator.create_job', create_job)
    async def test_update_not_jobcreated(self):
        """test update no job created"""
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
                "job_id": "job_id",
                "updates": {"deployed": "1234", "jarId": "jarId"},
                "jarfile": "jarfile"
            }
        }
        patchx = Bunch()
        patchx.status = {}
        response = await target.updates(None, patchx, Logger(), body, body["spec"], body["status"])
        self.assertEqual(response, {'jobCreated': True, 'jobId': 'job_id'})

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def check_readiness_0(body):
        """mock no ready task slots"""
        return 0
    @patch('kopf.info', kopf_info)
    @patch('beamservicesoperator.check_readiness', check_readiness_0)
    @patch('beamservicesoperator.create_job', create_job)
    async def test_update_not_jobcreated_not_ready(self):
        """test update job not ready"""
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
                "job_id": "job_id",
                "updates": {"deployed": "1234", "jarId": "jarId"},
                "jarfile": "jarfile"
            }
        }
        patchx = Bunch()
        patchx.status = {}
        response = await target.updates(None, patchx, Logger(), body, body["spec"], body["status"])
        self.assertEqual(response, None)

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def create_job_none(body, spec, update_status):
        """mock create job unsuccessful"""
        return None

    @patch('kopf.info', kopf_info)
    @patch('beamservicesoperator.check_readiness', check_readiness)
    @patch('beamservicesoperator.create_job', create_job_none)
    async def test_update_not_jobcreated_not_ready_no_jobid(self):
        """test update job without job id"""
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
                "job_id": "job_id",
                "updates": {"deployed": "1234", "jarId": "jarId"},
                "jarfile": "jarfile"
            }
        }
        patchx = Bunch()
        patchx.status = {}
        response = await target.updates(None, patchx, Logger(), body, body["spec"], body["status"])
        self.assertEqual(response, {'deployed': False, 'jobCreated': False})

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def requestsget(url):
        """mock get jobs"""
        result = Bunch()
        result.json = getjsn
        return result

    @patch('kopf.info', kopf_info)
    @patch('requests.get', requestsget)
    async def test_update_not_jobcreated_not_ready_then_running(self):
        """test update not ready job"""
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
                "job_id": "job_id",
                "updates":
                    {"deployed": "1234", "jarId": "jarId", "jobCreated": "2345", "jobId": "id"},
                "jarfile": "jarfile"
            }
        }
        patchx = Bunch()
        patchx.status = {}
        await target.updates(None, patchx, Logger(), body, body["spec"], body["status"])
        self.assertEqual(patchx["status"].get("state"), "RUNNING")

    # pylint: disable=no-self-use, no-self-argument
    def requestsget_fail(url):
        """mock get jobs fail"""
        result = Bunch()
        result.json = getjsn_fail
        return result

    @patch('kopf.info', kopf_info)
    @patch('requests.get', requestsget_fail)
    async def test_update_not_jobcreated_not_ready_no_jobid_requestget_getfailed(self):
        """test update job failed"""
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
                "job_id": "job_id",
                "updates":
                    {"deployed": "1234", "jarId": "jarId", "jobCreated": "2345", "jobId": "id"},
                "jarfile": "jarfile"
            }
        }
        patchx = Bunch()
        patchx.status = {}
        await target.updates(None, patchx, Logger(), body, body["spec"], body["status"])
        self.assertEqual(patchx["status"].get("state"), None)

    # pylint: disable=no-self-argument
    def requestsget_good(url):
        """mock get jobs"""
        result = Bunch()
        try:
            url.index("/jobs/")
        except ValueError:
            result.json = getjsn
        else:
            result.json = getjson_put
        return result

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def get_jobname_prefix(body, spec):
        """mock get jobname prefix"""
        return "nam"
    # pylint: disable=no-self-argument
    def cancel_job(job_id):
        """mock cancel job successful"""

    @patch('kopf.info', kopf_info)
    @patch('requests.get', requestsget_good)
    @patch('beamservicesoperator.get_jobname_prefix', get_jobname_prefix)
    @patch('beamservicesoperator.cancel_job', cancel_job)
    async def test_update_not_jobcreated_not_ready_not_matching_joid(self):
        """test updating not ready job"""
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
                "job_id": "job_id",
                "updates":
                    {"deployed": "1234", "jarId": "jarId",
                        "jobCreated": "2345", "jobId": "otherid"},
                "jarfile": "jarfile"
            }
        }
        patchx = Bunch()
        patchx.status = {}
        await target.updates(None, patchx, Logger(), body, body["spec"], body["status"])
        self.assertEqual(patchx["status"].get("state"), None)

def cancel_job(job_id):
    """mock cancel job"""
    assert job_id == "id"

class TestDelete(TestCase):
    """Unit test class for delete tests"""
    @patch('kopf.info', kopf_info)
    def test_delete(self):
        """test delete resource"""
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
        response = target.delete(body)
        self.assertEqual(response, None)

    @patch('kopf.info', kopf_info)
    @patch('beamservicesoperator.cancel_job', cancel_job)
    def test_delete_successful(self):
        """test delete resource successfully"""
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
                "job_id": "job_id",
                "updates":
                    {"deployed": "1234", "jarId": "jarId", "jobCreated": "2345", "jobId": "id"}
            }
        }
        patchx = Bunch()
        patchx.status = {}
        response = target.delete(body)
        self.assertEqual(response, None)

class TestHelpers(TestCase):
    """Unit test class for helpers"""
    # pylint: disable=no-self-argument
    def requestget(url):
        """mock get content"""
        assert url == 'url'
        result = Bunch()
        result.content = b'content'
        return result

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def download_file_via_ftp(url, username, password):
        """mock downloaded file with path"""
        return "jarfilepath"

    @patch('requests.get', requestget)
    def test_download_file_http(self):
        """test download job with http"""
        mxx = mock_open()
        with patch('__main__.open', mxx, create=True):
            with open('foo', 'wb') as hxx:
                hxx.write(b'some stuff')
        response = target.download_file_via_http('url')
        self.assertRegex(response, r"/tmp/[a-f0-9-]*\.jar")

    @patch('ftplib.FTP', autospec=True)
    def test_download_file_ftp(self, mock_ftp_constructor):
        """test download job with ftp"""
        mxx = mock_open()
        with patch('__main__.open', mxx, create=True):
            with open('foo', 'wb') as hxx:
                hxx.write(b'some stuff')
        response = target.download_file_via_ftp('ftp://url', 'username', 'password')
        mock_ftp_constructor.assert_called_with('url', 'username', 'password')
        self.assertRegex(response, r"/tmp/[a-f0-9-]*\.jar")

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def requestpost(url, files):
        """mock successful post of job"""
        response = Bunch()
        response.status_code = 200
        response.json = getjson_post
        return response

    @patch('requests.post', requestpost)
    @patch('kopf.info', kopf_info)
    @patch('beamservicesoperator.download_file_via_ftp', download_file_via_ftp)
    def test_deploy_ftp(self):
        """test deploy job via ftp"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                'package': {
                    'url': 'ftp://url',
                    'username': 'username',
                    'password': 'password'
                }
            },
            "status": {
            }
        }
        patchx = Bunch()
        patchx.status = {}
        mxx = mock_open(read_data='data')
        with mock.patch('builtins.open', mxx, create=True):
            with open('jarfilepath', encoding='UTF-8'):
                response = target.deploy(body, body["spec"], patchx)
        self.assertEqual(response, "filename")

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def util_format_template(string, tokens, encode):
        """mock format template"""
        return "format"

    @patch('util.format_template', util_format_template)
    def test_build_args(self):
        """test build_args"""
        args_dict = {
           "key1": "value1",
           "key2": "value2",
           "config": {
               "format": "value"
           }
        }
        tokens = {
            "key": "value"
        }
        response = target.build_args(args_dict, tokens)
        self.assertEqual(response, '--key1=value1 --key2=value2 --config=format ')

    @patch('kopf.info', kopf_info)
    @patch('util.format_template', util_format_template)
    def test_get_jobname_prefix(self):
        """test get_jobname_prefix"""
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "entryClass": "org.entryClass"
            },
            "status": {
            }
        }
        response = target.get_jobname_prefix(body, body["spec"])
        self.assertEqual(response, 'entryclass')
    # pylint: disable=no-self-argument
    # pylint: disable=E1136
    def get_tokens(users):
        """mock get_tokens"""
        THAT.assertDictEqual(users[0], {"user": "user", "password": "password"})
        return {"user1": "token1", "user2": "token2"}
    # pylint: disable=no-self-argument
    def build_args(args_dict, tokens):
        """mock build_args"""
        THAT.assertDictEqual(args_dict, {"runner": "runner"})
        THAT.assertDictEqual(tokens, {"user1": "token1", "user2": "token2"})

    # pylint: disable=no-self-use, unused-argument, no-self-argument
    def request_post_run(url, json):
        """mock post to create job successfully"""
        def json_run():
            """mock json result of post"""
            return {"jobid": "jobid"}
        result = Bunch()
        result.status_code = 200
        result.json = json_run
        return result
    @patch('kopf.info', kopf_info)
    @patch('requests.post', request_post_run)
    @patch('util.get_tokens', get_tokens)
    @patch('beamservicesoperator.build_args', build_args)
    # pylint: disable=global-statement
    def test_create_job(self):
        """test create_job successful"""
        global THAT
        THAT = self
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            },
            "spec": {
                "entryClass": "org.entryClass",
                "tokens": [
                    {
                        "user": "user",
                        "password": "password"
                    }
                ],
                "args": {"runner": "runner"}
            },
            "status": {
            }
        }
        response = target.create_job(body, body['spec'], 'jar_id')
        self.assertEqual(response, 'jobid')

    # pylint: disable=no-self-use, no-self-argument
    def request_get_overview(url):
        """mock get overview path of flink"""
        def json_get():
            """mock return of 5 worker slots"""
            return {"slots-total": 5}
        result = Bunch()
        result.status_code = 200
        result.json = json_get
        return result

    @patch('kopf.info', kopf_info)
    @patch('requests.get', request_get_overview)
    # pylint: disable=global-statement
    def test_check_readiness(self):
        """test check_readiness with 5 slots"""
        global THAT
        THAT = self
        body = {
            "metadata": {
                "name": "name",
                "namespace": "namespace"
            }
        }
        response = target.check_readiness(body)
        self.assertEqual(response, 5)


if __name__ == '__main__':
    unittest.main()
