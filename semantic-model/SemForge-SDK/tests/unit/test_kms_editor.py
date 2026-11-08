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

"""The editor and directories of packages (openspec gh-939-kms-package).

"The editor warns when a published package changes" and "A directory of
packages lists each package once", on the server and in the extension.
"""

import datetime
import json
import os
import shutil
import subprocess

import pytest

from semforge.editor import published
from semforge.package.discover import packages_below
from semforge.package.releases import publish, raise_version
from semforge.package.scaffold import create_package

HERE = os.path.dirname(os.path.abspath(__file__))
LOCATE = os.path.join(HERE, '..', '..', 'vscode', 'src', 'locate.js')


class _Protocol:
    def __init__(self):
        self.sent = []

    def notify(self, method, params):
        self.sent.append((method, params))


class _Client:
    def __init__(self):
        self.protocol = _Protocol()


def _touch_shapes(root):
    with open(os.path.join(root, 'shacl.ttl'), 'a', encoding='utf-8') as handle:
        handle.write('\n# an edit\n')


@pytest.fixture
def published_package(tmp_path):
    root = str(tmp_path / 'plant')
    create_package(root, name='plant', layout='flat')
    with open(os.path.join(root, 'kms.yaml'), 'a', encoding='utf-8') as handle:
        handle.write('\ntests:\n  coverage: 5\n')
    publish(root, output=str(tmp_path / 'plant.kms.zip'),
            today=datetime.date(2026, 11, 7))
    published.reset()
    yield root
    published.reset()


# --- the warning ----------------------------------------------------------------

def test_first_edit_after_publishing(published_package):
    client = _Client()
    _touch_shapes(published_package)
    told = published.check_after_write(published_package, client)
    assert told['version'] == '0.1.0'
    assert told['next'] == {'patch': '0.1.1', 'minor': '0.2.0', 'major': '1.0.0'}
    assert 'plant 0.1.0 is published' in told['message']
    assert client.protocol.sent[0][0] == 'semforge/publishedChanged'


def test_said_once_per_version(published_package):
    client = _Client()
    _touch_shapes(published_package)
    published.check_after_write(published_package, client)
    _touch_shapes(published_package)
    assert published.check_after_write(published_package, client) is None
    assert len(client.protocol.sent) == 1


def test_draft_version(published_package):
    client = _Client()
    _touch_shapes(published_package)
    raise_version(published_package, 'patch')
    _touch_shapes(published_package)
    assert published.check_after_write(published_package, client) is None
    assert client.protocol.sent == []


def test_unchanged_published_package(published_package):
    assert published.check_after_write(published_package, _Client()) is None


def test_a_package_never_published_costs_nothing(tmp_path):
    root = str(tmp_path / 'plain')
    create_package(root, name='plain', layout='flat')
    assert published.published_change(root) is None


def test_raise_version_over_the_protocol(published_package):
    from semforge.editor.edits import raise_version as handler
    from semforge.editor.protocol import path_to_uri

    uri = path_to_uri(os.path.join(published_package, 'shacl.ttl'))
    done = handler(None, {'uri': uri, 'part': 'minor'})
    assert done == {'ok': True, 'old': '0.1.0', 'new': '0.2.0'}


# --- directories of packages ------------------------------------------------------

@pytest.fixture
def kms_dir(tmp_path):
    base = tmp_path / 'kms'
    base.mkdir()
    create_package(str(base / 'example'), name='example', layout='flat')
    create_package(str(base / 'opcua-pumps'), name='opcua-pumps', layout='flat')
    examples = base / 'SchweissenUndSchneiden'
    examples.mkdir()
    (examples / 'knowledge.ttl').write_text('')
    (examples / 'model-example.jsonld').write_text('[]')
    os.symlink('opcua-pumps', base / 'default')   # not the first by name
    return base


def test_listing_the_packages(kms_dir):
    found = packages_below(str(kms_dir))
    assert [(name, default) for name, _, default in found] == \
        [('example', False), ('opcua-pumps', True)]


def test_directory_of_examples(kms_dir):
    assert 'SchweissenUndSchneiden' not in [n for n, _, _ in packages_below(str(kms_dir))]


NODE_SCRIPT = r"""
const Module = require('module');
const path = require('path');
const folder = process.argv[2];
const stub = {
  workspace: { workspaceFolders: [{ uri: { fsPath: folder } }] },
  Uri: { file: (p) => ({ toString: () => 'file://' + p }) },
};
const resolve = Module._resolveFilename;
Module._resolveFilename = function (request, ...rest) {
  return request === 'vscode' ? 'vscode' : resolve.call(this, request, ...rest);
};
require.cache.vscode = { id: 'vscode', filename: 'vscode', loaded: true, exports: stub };
const locate = require(process.argv[3]);
const listed = locate.listPackages().map((e) => ({ name: e.name, isDefault: e.isDefault }));
console.log(JSON.stringify({ listed, first: locate.findPackageUri() }));
"""


def test_opening_kms_in_the_editor(kms_dir, tmp_path):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    script = tmp_path / 'list.js'
    script.write_text(NODE_SCRIPT)
    done = subprocess.run([node, str(script), str(kms_dir), os.path.abspath(LOCATE)],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout)
    assert result['listed'] == [{'name': 'example', 'isDefault': False},
                                {'name': 'opcua-pumps', 'isDefault': True}]
    # Opening the directory picks the default package, not the first by name.
    assert '/opcua-pumps/' in result['first']
