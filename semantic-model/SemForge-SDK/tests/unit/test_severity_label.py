"""A SPARQL constraint's severity is a label, not a verdict.

`sh:severity` says how serious a result is WHEN the constraint fires; it does
not say that it fires. Shown as a red "violation" chip it read as something
failing -- worse when nobody declared it and SHACL's default stood in. So the
server says whether it was declared, and the pages show "severity: …",
neutral, with "(default)" when it was not.
"""

import json
import os
import shutil
import subprocess

import pytest

from semforge.cooked.shapepage import build_shape_page
from semforge.package import load

CUTTER = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnCutterShape'


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return target


def test_a_declared_severity_is_said_as_declared(kms):
    check = build_shape_page(load(str(kms)), CUTTER)['checks'][0]
    assert check['severity'] == 'critical' and check['severityDeclared'] is True


def test_an_undeclared_one_is_the_default_and_says_so(kms):
    shacl = kms / 'shacl.ttl'
    text = shacl.read_text()
    start = text.index('iffBaseShacl:StateOnCutterShape a')
    head, tail = text[:start], text[start:]
    shacl.write_text(head + tail.replace(' ;\n            sh:severity base:severityCritical', '', 1))
    check = build_shape_page(load(str(kms)), CUTTER)['checks'][0]
    assert check['severity'] == 'violation' and check['severityDeclared'] is False


DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')


def _render(tmp_path, page):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    scenario = tmp_path / 'render.json'
    scenario.write_text(json.dumps({'mode': 'render', 'function': 'renderShapePage',
                                    'payload': page, 'options': {'nonce': 'n'}}))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'shapepage.js'),
                          str(scenario)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout.strip().splitlines()[-1])['html']


@pytest.mark.parametrize('declared, shown', [
    (True, 'severity: critical</span>'),
    (False, 'severity: violation <span class="dim">(default)</span>'),
])
def test_the_shape_page_shows_a_label(tmp_path, kms, declared, shown):
    page = dict(build_shape_page(load(str(kms)), CUTTER), ok=True)
    page['checks'][0].update(severityDeclared=declared,
                             severity='critical' if declared else 'violation')
    html = _render(tmp_path, page)
    assert shown in html
    assert 'chip bad">violation' not in html and 'chip bad">critical' not in html, \
        'never styled as a verdict'
