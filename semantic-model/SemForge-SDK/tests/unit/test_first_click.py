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

"""The first click: what it needs is done before it, and it is never blank.

On the OPC UA pump package the first class click took 2.2 s with the package
already loaded -- the text index of 12.8 MB of ontology -- and paid the package
load (2.6 s) too when the views came from their cache. Now the index is kept
per file content, the editor warms the package as soon as anything asks about
it, and a page that is still waiting says so instead of staying blank.
"""

import json
import os
import shutil
import subprocess
import time

import pytest

from semforge.rdfio import turtle_index
from semforge.rdfio.derived import cache_dir
from semforge.rdfio.turtle_index import index_file

SDK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')

TURTLE = '@prefix ex: <https://example.org/> .\n' + ''.join(
    f'ex:S{n} a ex:Thing ;\n    ex:p "{n}" .\n\n' for n in range(30))


@pytest.fixture
def ttl(tmp_path):
    path = tmp_path / 'pkg' / 'k.ttl'
    path.parent.mkdir()
    path.write_text(TURTLE)
    turtle_index._PARSED.clear()
    return path


def _blocks(index):
    return [(b.subject, b.raw_subject, b.start, b.end, b.start_line, b.end_line)
            for b in index.blocks]


def test_the_index_is_kept_and_read_back_the_same(ttl, monkeypatch):
    root = str(ttl.parent)
    cold = index_file(str(ttl), root)
    assert os.listdir(cache_dir(root, 'index'))

    turtle_index._PARSED.clear()

    def no_parse(source):
        raise AssertionError('indexed again although kept')

    monkeypatch.setattr(turtle_index, '_parse', no_parse)
    warm = index_file(str(ttl), root)
    assert _blocks(warm) == _blocks(cold)
    line = TURTLE[:TURTLE.index('ex:S7 ')].count('\n') + 1
    assert warm.block_for('https://example.org/S7').start_line == line


def test_an_edit_indexes_again_and_keeps_one_version(ttl):
    root = str(ttl.parent)
    index_file(str(ttl), root)
    ttl.write_text(TURTLE.replace('ex:S7 ', 'ex:T7 '))
    turtle_index._PARSED.clear()
    assert index_file(str(ttl), root).block_for('https://example.org/T7') is not None
    entries = [n for n in os.listdir(cache_dir(root, 'index')) if n.endswith('.json')]
    assert len(entries) == 1


def test_without_a_package_nothing_is_kept(ttl):
    index_file(str(ttl))
    assert not os.path.exists(cache_dir(str(ttl.parent), 'index'))


def test_the_package_is_warmed_when_anything_asks(tmp_path, corpus_path):
    from semforge.editor import session, validation

    root = str(tmp_path / 'pkg')
    shutil.copytree(corpus_path, root, ignore=shutil.ignore_patterns('.semforge'))
    session.warm(root)
    deadline = time.time() + 120
    while time.time() < deadline:
        package = session._packages.get(root)
        if package is not None and hasattr(package, '_index_knowledge') \
                and hasattr(package, '_index_shapes'):
            break
        time.sleep(0.1)
    else:
        pytest.fail('the package was not warmed')
    assert os.listdir(cache_dir(root, 'index'))
    validation.service().wait(root, timeout=120)
    assert validation.service().get(root)[1].state == 'ready'

    before = session._packages[root]
    session.warm(root)                              # once per version
    assert session._packages[root] is before


def _open(tmp_path, page):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    scenario = tmp_path / 'scenario.json'
    scenario.write_text(json.dumps({
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'targetClass': 'https://example.org/Pump',
                         'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/typePage': page}}))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(scenario)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


PAGE = {'ok': True, 'iri': 'https://example.org/Pump', 'label': 'Pump', 'term': 'ex:Pump',
        'crumbs': [], 'subtypes': [], 'ownShapes': [], 'ownShape': '', 'ownShapeName': '',
        'shapeAt': '', 'attributes': [], 'rules': [], 'alsoCheckedBy': [],
        'exercisedBy': [], 'instances': [],
        'summary': {'cases': 0, 'casesFailing': 0, 'instances': 0,
                    'instancesViolating': None, 'neverFired': 0},
        'verdicts': {'state': 'evaluating', 'stale': False, 'error': '', 'seconds': 0}}


def test_a_slow_page_says_it_is_loading(tmp_path):
    seen = _open(tmp_path, {'__delay': 600, 'reply': PAGE})
    html = seen['webviews'][0]['html']
    assert 'Loading Pump' in html[0]
    assert 'evaluating' in html[-1] and 'Loading' not in html[-1]


def test_results_wait_for_an_open_edit():
    """Results arriving while an edit is open never redraw the page under it.

    Driven on the type, shape and case pages: during a picker of the
    extension's and during the page's own editor the redraw waits, and comes
    once when the edit ends; with nothing open it comes at once; a page whose
    results are final is not redrawn -- until a run for its package finishes:
    an edit made on another page writes the file with no editor save, and the
    type page kept showing the verdicts from before it. Hidden, it is marked
    and drawn when shown.
    """
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    out = subprocess.run([node, os.path.join(SDK, 'tests', 'harness', 'defer.js'), SRC],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    seen = json.loads(out.stdout.strip().splitlines()[-1])
    for page in ('type', 'shape', 'case'):
        assert seen[page] == {'duringPicker': 0, 'afterPicker': 1, 'duringEditor': 1,
                              'afterEditor': 2, 'idle': 3, 'final': 3, 'newer': 4,
                              'other': 4, 'hidden': 4, 'marked': True}, (page, seen[page])


def test_a_quick_page_does_not_flicker(tmp_path):
    seen = _open(tmp_path, PAGE)
    assert not any('Loading' in h for h in seen['webviews'][0]['html'])


# --- what is being changed says so ----------------------------------------------------

def test_a_click_that_writes_marks_its_claim_until_the_extension_is_done(tmp_path):
    """'Assert it' marks its claim "⟳ updating…"; the extension's idle clears it."""
    import glob
    import re

    chrome = next((c for c in [os.environ.get('SEMFORGE_CHROME', '')] + sorted(glob.glob(
        os.path.expanduser('~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome')))
        if c and os.path.exists(c)), None)
    if chrome is None:
        pytest.skip('no headless Chromium (set SEMFORGE_CHROME)')
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    page = {'kind': 'case', 'name': 'too-high', 'case': 'c.jsonld', 'expect': 'invalid',
            'group': '', 'suite': '', 'description': '', 'passed': True, 'failures': [],
            'claims': [], 'residuePinned': False, 'file': '/pkg/c.jsonld', 'expectations': '',
            'verdicts': {'state': 'ready'},
            'summary': {'entities': 0, 'violations': 1, 'includes': 0},
            'unasserted': [{'constraint': 'ex:S/hasHeight/MaxInclusiveConstraintComponent',
                            'resource': 'urn:w:1',
                            'explained': {'text': 'too high', 'shape': 'ex:S'}}],
            'files': []}
    json_path = tmp_path / 'page.json'
    json_path.write_text(json.dumps(page))

    def dom(after):
        script = tmp_path / 'after.js'
        script.write_text(after)
        out = tmp_path / 'page.html'
        run = subprocess.run([node, os.path.join(SDK, 'tests', 'harness', 'render_casepage.js'),
                              SRC, str(json_path), str(out), str(script)],
                             capture_output=True, text=True, timeout=60)
        assert run.returncode == 0, run.stderr[-1500:]
        return subprocess.run([chrome, '--headless=new', '--no-sandbox', '--disable-gpu',
                               '--virtual-time-budget=2000', '--dump-dom', 'file://' + str(out)],
                              capture_output=True, text=True, timeout=120).stdout

    clicked = dom('document.querySelector("[data-assert]").click();')
    claim = re.search(r'<div class="claim(?: [^"]*)?"', clicked).group(0)
    assert 'busy' in claim and '<span class="updating">⟳ updating…</span>' in clicked

    done = dom('document.querySelector("[data-assert]").click();'
               'window.postMessage({ command: "idle" }, "*");')
    assert '<span class="updating">' not in done and 'busy' not in re.search(
        r'<div class="claim(?: [^"]*)?"', done).group(0)


def test_diagnostics_are_never_worked_out_on_the_server_thread(tmp_path, corpus_path,
                                                               monkeypatch):
    """They come from the validation worker, with the verdicts."""
    from semforge.editor import analysis, validation

    root = str(tmp_path / 'pkg')
    shutil.copytree(corpus_path, root, ignore=shutil.ignore_patterns('.semforge'))

    def forbidden(*args, **kwargs):
        raise AssertionError('diagnostics computed on the server thread')

    validation.findings_of(root)                # starts the worker; nothing yet
    validation.service().wait(root, timeout=120)
    monkeypatch.setattr(analysis, 'analyse', forbidden)
    findings = validation.findings_of(root)
    kinds = {f.kind for items in findings.values() for f in items}
    assert 'unexercised' in kinds, kinds


def test_the_status_bar_says_while_a_validation_runs():
    """The server says when a run starts and ends; the status bar spins until
    every package's run has ended, then says how long it took, then goes."""
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    out = subprocess.run([node, os.path.join(SDK, 'tests', 'harness', 'validating.js'), SRC],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    seen = json.loads(out.stdout.strip().splitlines()[-1])
    spin = {'text': '$(sync~spin) SemForge: validating…', 'visible': True, 'timer': False}
    assert seen[:3] == [spin, spin, spin]
    assert seen[3] == {'text': '$(check) SemForge: validated in 1.3 s', 'visible': True,
                       'timer': True}
    assert seen[4]['visible'] is False and seen[4]['timer'] is False
    assert seen[5] == spin
    assert seen[6]['text'] == '$(error) SemForge: validation failed'
    assert seen[7] == {'tooltip': 'boom'}
