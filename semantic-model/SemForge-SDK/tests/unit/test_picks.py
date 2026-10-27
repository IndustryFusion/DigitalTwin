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

"""Actions first: after hundreds of OPC UA datatypes, classes or attributes,
an action at the end of a picker is never seen."""

import json
import os
import re
import shutil
import subprocess

import pytest

SDK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(SDK, 'vscode', 'src')

SCRIPT = '''
const Module = require('module');
const original = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') { return { QuickPickItemKind: { Separator: -1 } }; }
  return original(request, parent, isMain);
};
const { withActions } = require(process.argv[1] + '/picks.js');
const list = Array.from({ length: 300 }, (_, i) => ({ label: 'xsd:type' + i }));
const headed = [{ label: 'Declared for this type', kind: -1 }, { label: 'a' }];
console.log(JSON.stringify({
  plain: withActions([{ label: 'Act' }], list, 'Offered').slice(0, 3),
  headed: withActions([{ label: 'Act' }, null], headed, 'Offered'),
  none: withActions([], [{ label: 'a' }], 'Offered')
}));
'''


def test_actions_come_first_and_the_list_under_its_heading():
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    out = subprocess.run([node, '-e', SCRIPT, SRC], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    seen = json.loads(out.stdout.strip().splitlines()[-1])
    assert seen['plain'] == [{'alwaysShow': True, 'label': 'Act'},
                             {'label': 'Offered', 'kind': -1}, {'label': 'xsd:type0'}]
    # A list with its own headings keeps them; a missing action is no row.
    assert [i['label'] for i in seen['headed']] == ['Act', 'Declared for this type', 'a']
    assert seen['none'] == [{'label': 'a'}]


def test_no_picker_appends_an_action_after_its_list():
    """The pattern this replaced -- an action pushed after a list -- is gone."""
    offenders = []
    for name in sorted(os.listdir(SRC)):
        if not name.endswith('.js'):
            continue
        with open(os.path.join(SRC, name), encoding='utf-8') as handle:
            text = handle.read()
        for match in re.finditer(r"items\.push\(\{\s*label: [^,]*'\$\((?:add|edit|new-folder)\) "
                                 r"(?:New|Enter|Another)", text):
            offenders.append(f'{name}:{text.count(chr(10), 0, match.start()) + 1}')
    assert offenders == []
