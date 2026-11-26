#
# Copyright (c) 2026 IndustryFusion Foundation
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
"""owl2instances.py follows OPC UA Properties by default (openspec gh-1136-properties-by-default)."""

import pytest
from rdflib import Namespace

import owl2instances

OPCUA = Namespace('http://opcfoundation.org/UA/')
REQUIRED = ['-n', 'http://demo.machine/', 'instance.ttl']


@pytest.mark.parametrize('options, follows', [
    ([], True),                          # the default
    (['--no-properties'], False),        # the opt-out
    (['-p'], True),                      # kept for compatibility, no effect
    (['--properties'], True),
    (['-p', '--no-properties'], False),  # -p does not undo the opt-out
    (['--no-properties', '-p'], False),
])
def test_properties_are_followed_unless_opted_out(options, follows):
    args = owl2instances.parse_args(options + REQUIRED)
    assert args.properties is follows
    ignored = owl2instances.get_ignored_hierarchical_references(args.properties, OPCUA)
    assert ignored == ([] if follows else [OPCUA['HasProperty']])


def test_help_names_the_opt_out_and_the_no_op(capsys):
    with pytest.raises(SystemExit):
        owl2instances.parse_args(['--help'])
    text = ' '.join(capsys.readouterr().out.split())
    assert '--no-properties Do not follow OPC UA Properties (HasProperty)' in text
    assert '-p, --properties No effect, kept for compatibility' in text
