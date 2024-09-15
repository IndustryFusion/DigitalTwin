from unittest import TestCase
import unittest
from bunch_py3 import Bunch
from mock import patch
import os
import util as target


# Mock functions
# --------------

get_environ_ENV = {
    "conf": '{ "a": "b", "c": "@@other_conf"}',
    "other_conf": '{ "d": "e" }',
    "cyclic_conf": '{ "a": "@@cyclic_conf"}'
}

def oisp_token():
    """
    return mock token
    """
    value = Bunch()
    value.value = "token"
    return value

# pylint: disable=unused-argument
def auth_pass(user, password):
    """
    Mock successful auth
    """


def oisp_pass(url):
    """
    Mock successfull oisp auth
    """
    client = Bunch()
    client.auth = auth_pass
    client.get_user_token = oisp_token
    return client


def base64_enc(value):
    """
    Mock base64
    """
    return f"base64+{value}".encode('utf-8')


class TestUtils(TestCase):
    """
    Test class for all util functions
    """
    @patch('os.environ', get_environ_ENV)
    def test_load_config(self):
        """
        test load config
        """
        response = target.load_config_from_env("conf")
        self.assertEqual(response, {"a": "b", "c": {"d": "e"}})

    @patch('os.environ', get_environ_ENV)
    def test_load_config_cyclic(self):
        """
        test load config with cyclic reference
        """
        with self.assertRaises(AssertionError) as context:
            target.load_config_from_env("cyclic_conf")
        self.assertEqual(str(context.exception), "Cyclic config")

    @patch('oisp.Client', oisp_pass)
    def test_get_tokens(self):
        """
        test get tokens
        """
        response = target.get_tokens(
            [{"user": "username", "password": "password"}])
        self.assertEqual(response, {"username": "token"})

    # @patch('config', {})
    @patch('base64.b64encode', base64_enc)
    def test_format_template(self):
        """
        test format_template
        """
        response = target.format_template(
            "string{tokens}", tokens="tokensss", encode='base64')
        self.assertEqual("base64+b'stringtokensss'", response)


if __name__ == '__main__':
    unittest.main()
