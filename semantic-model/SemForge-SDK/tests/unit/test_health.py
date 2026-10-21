"""The package health page: the figures, and the list in the right order.

The figures must agree with the commands they summarise (`validate`'s count
of evaluated constraints, `test`'s pass count), and the list must put what is
broken before what is merely untested. A copy of the corpus is broken on
purpose to see errors arrive at the top with the right action.
"""

import json
import os
import shutil
import subprocess

import pytest

from semforge.cooked.health import build_health
from semforge.package import load

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')


@pytest.fixture(scope='module')
def health(corpus):
    return build_health(corpus)


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


# --- the figures ------------------------------------------------------------------

def test_the_figures_agree_with_the_commands(corpus, health):
    from semforge.validate import validate_package

    report = validate_package(corpus, strict=False)
    tiles = health['tiles']
    assert tiles['evaluated'] == len(report.evaluated)
    assert tiles['modelViolations'] == len(report.violations)
    assert tiles['cases'] >= 6 and tiles['casesPassing'] == tiles['cases']
    assert tiles['brokenReferences'] == 0


def test_never_fired_is_counted_per_constraint_and_per_shape(health):
    coverage = [i for i in health['attention'] if i['area'] == 'coverage']
    assert len(coverage) == health['tiles']['neverFiredShapes']
    assert sum(int(i['text'].split(': ')[1].split()[0]) for i in coverage) == \
        health['tiles']['neverFired']


# --- the list --------------------------------------------------------------------------

def test_what_is_broken_comes_before_what_is_untested(health):
    areas = [i['area'] for i in health['attention'] if i['severity'] == 'warning']
    assert areas.index('model') < areas.index('coverage')
    severities = [i['severity'] for i in health['attention']]
    order = {'error': 0, 'warning': 1, 'note': 2}
    assert severities == sorted(severities, key=order.get)


def test_every_item_says_what_to_open(health):
    for item in health['attention']:
        assert item.get('at') or item.get('case') or item.get('type'), item


def test_two_shapes_with_one_name_are_told_apart(health):
    texts = [i['text'] for i in health['attention'] if 'CartridgeShape' in i['text']]
    assert any(t.startswith('iffBaseShacl:CartridgeShape') for t in texts)
    assert any(t.startswith('iffFilterShacl:CartridgeShape') for t in texts)


def test_a_broken_package_puts_its_errors_first(kms):
    path = os.path.join(kms, 'examples', 'test_WorkpieceShape', 'bad', 'expectations.yaml')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text.replace('hasHeight/MaxInclusive', 'hasNoSuchThing/MaxInclusive'))
    health = build_health(load(kms))
    assert health['tiles']['casesPassing'] == health['tiles']['cases'] - 1
    assert health['tiles']['brokenReferences'] == 1
    errors = [i for i in health['attention'] if i['severity'] == 'error']
    assert [i['area'] for i in errors] == ['test', 'reference']
    assert errors[0]['case'].endswith('too-high.jsonld')
    assert errors[1]['at'].split(':')[-2].endswith('expectations.yaml')


# --- the renderer and the clicks --------------------------------------------------------

def _node(tmp_path, scenario, target):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, target), str(path)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _render(tmp_path, page):
    return _node(tmp_path, {'mode': 'render', 'function': 'renderHealthPage',
                            'payload': page, 'options': {'nonce': 'h'}},
                 'healthpage.js')['html']


def test_the_page_shows_the_figures_and_the_list(tmp_path, health):
    html = _render(tmp_path, health)
    tiles = health['tiles']
    for text in (f"{tiles['casesPassing']} / {tiles['cases']}", 'test cases pass',
                 'constraints evaluated', 'never fired', 'broken references',
                 'Needs attention', 'MachineShape'):
        assert text in html, text
    assert "script-src 'nonce-h'" in html


def test_a_healthy_package_says_so(tmp_path, health):
    html = _render(tmp_path, dict(health, attention=[], counts={}))
    assert 'Nothing needs attention' in html


def test_nothing_reaches_the_page_unescaped(tmp_path, health):
    hostile = json.loads(json.dumps(health))
    hostile['name'] = '<script>alert(1)</script>'
    hostile['attention'][0]['text'] = '<img src=x onerror=alert(2)>'
    html = _render(tmp_path, hostile)
    assert '<script>alert' not in html and '<img src=x' not in html


def test_each_button_opens_its_thing(tmp_path, health):
    page = dict(health, ok=True, attention=[
        {'severity': 'error', 'area': 'test', 'text': 'x fails', 'case': '/pkg/examples/x.jsonld'},
        {'severity': 'warning', 'area': 'coverage', 'text': 'Filter…', 'type': 'Filter'},
        {'severity': 'note', 'area': 'vocabulary', 'text': 'typo', 'at': '/pkg/m.jsonld:47'}])
    seen = _node(tmp_path, {
        'command': 'semforge.openHealthPage',
        'node': {'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'case', 'file': '/pkg/examples/x.jsonld'},
                            {'command': 'type', 'name': 'Filter'},
                            {'command': 'open', 'at': '/pkg/m.jsonld:47'},
                            {'command': 'rescan'}],
        'replies': {'semforge/health': page}}, 'extension.js')
    assert seen['errors'] == [], seen['errors']
    executed = [(e['command'], e['args'][0]) for e in seen['executed']]
    assert ('semforge.openCasePage', {'raw': {'kind': 'example', 'label': 'x.jsonld',
                                              'file': '/pkg/examples/x.jsonld'},
                                      'packageUri': 'file:///pkg/shacl.ttl'}) in executed
    assert any(c == 'semforge.openTypePage' and a['raw']['targetClass'] == 'Filter'
               for c, a in executed)
    assert any(c == 'semforge.rescan' for c, _ in executed)
    assert seen['shown'][0]['file'] == '/pkg/m.jsonld'
    assert len([r for r in seen['requests'] if r['method'] == 'semforge/health']) == 2, \
        'the page re-renders after a rescan'


def test_package_health_is_the_first_thing_in_the_status_bar_menu():
    with open(os.path.join(SRC, 'packages.js'), encoding='utf-8') as handle:
        source = handle.read()
    menu = source.split('const MENU = [', 1)[1]
    assert menu.index("'semforge.openHealthPage'") < menu.index("'semforge.selectPackage'")
