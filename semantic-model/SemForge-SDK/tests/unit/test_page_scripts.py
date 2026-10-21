"""Every page's own script parses.

A page's script is written inside a JavaScript template string, where `\\'`
loses its backslash and `${…}` is the outer string's: one slip and the
generated script is a syntax error. The webview shows the page all the same
-- and NO click on it does anything. That happened to the case page (an
apostrophe in a button title), and nothing that drives a page from the
extension side could see it. So each page is rendered from a real payload and
its scripts are handed to node to parse.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

from semforge.cooked.casepage import build_case_page, build_model_page
from semforge.cooked.shapepage import build_shape_page
from semforge.cooked.typepage import build_type_page
from semforge.cooked.vocabulary import build_vocabulary_page
from semforge.package import load

SDK = os.path.join(os.path.dirname(__file__), '..', '..')
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')
ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
SHACL = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
KNOW = 'https://industryfusion.github.io/contexts/example/v0/base_knowledge/'


def _render(tmp_path, command, raw, method, payload):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps({
        'command': command, 'node': {'raw': raw, 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {method: dict(payload, ok=True)}}))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(path)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])['webviews'][0]['html'][-1]


def _scripts_parse(tmp_path, html):
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
    assert scripts, 'the page has a script'
    for index, script in enumerate(scripts):
        file = tmp_path / f'script{index}.js'
        file.write_text(script)
        out = subprocess.run([shutil.which('node'), '--check', str(file)],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr[-800:]


@pytest.fixture(scope='module')
def kms(corpus_path):
    return load(corpus_path)


def test_the_case_page_script_parses(tmp_path, kms):
    case = next(e.path for e in __import__('semforge.expect.store', fromlist=['x'])
                .load_expectations(kms.path).examples)
    page = build_case_page(kms, case)
    html = _render(tmp_path, 'semforge.openCasePage',
                   {'kind': 'example', 'file': page['file'], 'children': []},
                   'semforge/casePage', page)
    assert 'data-stamp=' in html, 'the time links are on it'
    _scripts_parse(tmp_path, html)


def test_the_main_page_script_parses(tmp_path, kms):
    page = build_model_page(kms)
    html = _render(tmp_path, 'semforge.openModelPage', {}, 'semforge/modelPage', page)
    _scripts_parse(tmp_path, html)


def test_the_type_page_script_parses(tmp_path, kms):
    page = build_type_page(kms, f'{ENT}Filter')
    html = _render(tmp_path, 'semforge.openTypePage',
                   {'kind': 'type', 'targetClass': f'{ENT}Filter', 'children': []},
                   'semforge/typePage', page)
    _scripts_parse(tmp_path, html)


def test_the_shape_page_script_parses(tmp_path, kms):
    page = build_shape_page(kms, f'{SHACL}FilterShape')
    html = _render(tmp_path, 'semforge.openShapePage',
                   {'kind': 'shape', 'shape': f'{SHACL}FilterShape', 'children': []},
                   'semforge/shapePage', page)
    _scripts_parse(tmp_path, html)


def test_a_click_on_a_time_opens_the_picker_and_set_sends_it():
    """The case page's own script, on a minimal DOM: the time link opens the
    date-and-time picker, and Set posts the time for that row."""
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    out = subprocess.run([node, os.path.join(SDK, 'tests', 'harness', 'click_stamp.js'),
                          os.path.join(SRC, 'casepage.js')],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
    assert 'picker: div stampedit | datetime-local 2026-01-01T00:00:00.000 | ' \
        'Set | Now | Just after the latest | Remove | ×' in out.stdout
    assert 'posted: [{"command":"stamp","at":"0.0.0","value":"2026-03-04T05:06:07.890Z"}]' \
        in out.stdout


def test_the_vocabulary_page_script_parses(tmp_path, kms):
    page = build_vocabulary_page(kms, f'{KNOW}MachineState')
    html = _render(tmp_path, 'semforge.openVocabularyPage',
                   {'kind': 'class', 'iri': f'{KNOW}MachineState', 'children': []},
                   'semforge/vocabularyPage', page)
    _scripts_parse(tmp_path, html)
