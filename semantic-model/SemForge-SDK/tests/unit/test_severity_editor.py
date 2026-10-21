"""Severity in the editor: the Problems panel's checks, the server, the picker.

The picker offers SHACL's three levels, then each severity class's own, then
"no severity" (SHACL's default), "+ New severity level…" and "+ New severity
class…"; the Problems panel reports a severity that is no level and offers to
link a class of levels to sh:Severity. Run on copies of the kms corpus.
"""

import json
import os
import shutil
import subprocess
from unittest import mock

import pytest
from rdflib import URIRef
from rdflib.namespace import SH

from semforge.cooked.severity import link_class, set_severity
from semforge.cooked.sparqlbench import holders
from semforge.package import load

KNOW = 'https://industryfusion.github.io/contexts/example/v0/base_knowledge/'
SHAPES = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
CUTTER = SHAPES + 'StateOnCutterShape'
FILTER = SHAPES + 'FilterShape'


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return target


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


# --- the Problems panel -----------------------------------------------------------------

def test_a_class_of_levels_not_linked_is_reported_with_a_fix(kms):
    from semforge.sanity import sanity

    finding = next(f for f in sanity(load(str(kms))) if f.code == 'severity-unlinked')
    assert finding.severity == 'information' and finding.file.endswith('knowledge.ttl')
    assert finding.fix == {'link': KNOW + 'SeverityClass'}
    link_class(load(str(kms)), KNOW + 'SeverityClass')
    assert not [f for f in sanity(load(str(kms))) if f.code == 'severity-unlinked']


def test_a_severity_that_is_no_level_is_reported(kms):
    from semforge.sanity import sanity

    shacl = kms / 'shacl.ttl'
    shacl.write_text(_read(shacl).replace('base:severityCritical', 'base:severityNowhere', 1))
    finding = next(f for f in sanity(load(str(kms))) if f.code == 'severity-unknown')
    assert 'base:severityNowhere' in finding.message and 'StateOnCutterShape' in finding.message


def test_the_quick_fix_links_the_class():
    from lsprotocol import types

    from semforge.editor import server

    diagnostic = types.Diagnostic(
        range=types.Range(types.Position(1, 0), types.Position(1, 9)), message='x',
        source='semforge', data={'code': 'severity-unlinked', 'subject': KNOW + 'SeverityClass',
                                 'link': KNOW + 'SeverityClass'})
    actions = server._fixes_for(diagnostic, 'file:///pkg/knowledge.ttl')
    assert [a.title for a in actions] == ['Declare SeverityClass a kind of sh:Severity']
    assert actions[0].command.command == 'semforge.linkSeverityClass'


# --- the server ------------------------------------------------------------------------

def test_the_server_lists_sets_adds_and_links(kms):
    from semforge.editor import server

    uri = f'file://{kms}/shacl.ttl'
    with mock.patch.object(server, '_publish'):
        listed = server.severity_levels_feature(mock.MagicMock(), {'uri': uri})
        assert listed['ok'] and listed['levels'][0]['term'] == 'sh:Violation'
        query = holders(load(str(kms)), CUTTER)[0]['query']
        done = server.set_severity_feature(mock.MagicMock(), {
            'uri': uri, 'shape': CUTTER, 'query': query, 'severity': 'sh:Warning'})
        assert done['ok'], done
        for feature, params in (
                (server.add_severity_level_feature,
                 {'cls': 'sh:Severity', 'name': 'severityMajor', 'label': 'major'}),
                (server.add_severity_class_feature, {'name': 'AlarmLevel', 'parent': ''}),
                (server.link_severity_class_feature, {'cls': KNOW + 'SeverityClass'})):
            answer = feature(mock.MagicMock(), dict(params, uri=uri))
            assert answer['ok'], answer
    shapes = load(str(kms)).shapes
    holder = next(shapes.objects(URIRef(CUTTER), SH.sparql))
    assert (holder, SH.severity, SH.Warning) in shapes


# --- the extension ----------------------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
LEVELS = {'ok': True, 'levels': [
    {'iri': str(SH.Violation), 'term': 'sh:Violation', 'label': 'violation',
     'class': 'sh:Severity', 'builtin': True, 'used': 0, 'note': 'the default'},
    {'iri': str(SH.Warning), 'term': 'sh:Warning', 'label': 'warning', 'class': 'sh:Severity',
     'builtin': True, 'used': 0, 'note': ''},
    {'iri': KNOW + 'severityCritical', 'term': 'base:severityCritical', 'label': 'critical',
     'class': 'base:SeverityClass', 'builtin': False, 'used': 1, 'note': ''}],
    'classes': [{'iri': str(SH.Severity), 'term': 'sh:Severity', 'linked': True, 'parent': ''}]}


def _drive(tmp_path, scenario):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(path)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _row_menu(tmp_path, kms, picks, inputs=None, replies=None):
    from semforge.cooked.typepage import build_type_page

    page = dict(build_type_page(load(str(kms)), ENT + 'Filter'), ok=True)
    row = next(i for i, a in enumerate(page['attributes']) if a['label'] == 'hasStrength')
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'targetClass': ENT + 'Filter', 'label': 'Filter',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'menu', 'row': row}] if picks else [],
        'picks': picks, 'inputs': inputs or [],
        'replies': dict({'semforge/typePage': page, 'semforge/severityLevels': LEVELS,
                         'semforge/setSeverity': {'ok': True, 'file': '/f', 'severity': 'x'}},
                        **(replies or {}))})
    return seen, page['attributes'][row]


def _asked(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


def test_severity_on_an_attribute_row_offers_shacl_s_and_the_package_s(tmp_path, kms):
    seen, row = _row_menu(tmp_path, kms, ['$(warning) Severity…', 'warning'])
    assert '$(warning) Severity…' in [i['label'] for i in seen['quickPicks'][0]['items']]
    labels = [i['label'] for i in seen['quickPicks'][1]['items']]
    assert labels[:4] == ['SHACL', 'violation', 'warning', 'base:SeverityClass']
    for offered in ('$(circle-slash) No severity', '$(add) New severity level…',
                    '$(type-hierarchy-sub) New severity class…'):
        assert offered in labels, offered
    assert _asked(seen, 'semforge/setSeverity') == [{
        'uri': 'file:///pkg/shacl.ttl', 'severity': 'sh:Warning', 'shape': row['shape'],
        'path': row['path']}]


def test_no_severity_clears_it_back_to_the_default(tmp_path, kms):
    seen, _ = _row_menu(tmp_path, kms, ['$(warning) Severity…', '$(circle-slash) No severity'])
    assert _asked(seen, 'semforge/setSeverity')[0]['severity'] == ''


def test_a_new_level_is_made_and_set(tmp_path, kms):
    seen, _ = _row_menu(tmp_path, kms, ['$(warning) Severity…', '$(add) New severity level…'],
                        inputs=['severityMajor', 'major'],
                        replies={'semforge/addSeverityLevel': {
                            'ok': True, 'iri': KNOW + 'severityMajor',
                            'term': 'base:severityMajor'}})
    assert _asked(seen, 'semforge/addSeverityLevel') == [{
        'uri': 'file:///pkg/shacl.ttl', 'cls': 'sh:Severity', 'name': 'severityMajor',
        'label': 'major', 'namespace': None}]
    assert _asked(seen, 'semforge/setSeverity')[0]['severity'] == 'base:severityMajor'


def test_severity_has_its_own_column_and_is_edited_in_it(tmp_path, kms):
    set_severity(load(str(kms)), FILTER, path=['iffBaseEntities:hasStrength'],
                 severity='sh:Warning')
    seen, _ = _row_menu(tmp_path, kms, [])
    html = seen['webviews'][0]['html'][-1]
    assert '>Severity</th>' in html
    row = html.split('>hasStrength</a>', 1)[1].split('</tr>', 1)[0]
    assert 'data-action="severity"' in row and '>warning</a>' in row
    other = html.split('>hasCartridge</a>', 1)[1].split('</tr>', 1)[0]
    assert '<span class="dim">violation (default)</span>' in other


def test_clicking_the_severity_cell_opens_the_picker(tmp_path, kms):
    from semforge.cooked.typepage import build_type_page

    page = dict(build_type_page(load(str(kms)), ENT + 'Filter'), ok=True)
    row = next(i for i, a in enumerate(page['attributes']) if a['label'] == 'hasStrength')
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'targetClass': ENT + 'Filter', 'label': 'Filter',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'severity', 'row': row}], 'picks': ['info'],
        'replies': {'semforge/typePage': page, 'semforge/severityLevels': dict(
            LEVELS, levels=LEVELS['levels'] + [{
                'iri': str(SH.Info), 'term': 'sh:Info', 'label': 'info', 'class': 'sh:Severity',
                'builtin': True, 'used': 0, 'note': ''}]),
            'semforge/setSeverity': {'ok': True, 'file': '/f', 'severity': 'x'}}})
    assert _asked(seen, 'semforge/setSeverity')[0]['severity'] == 'sh:Info'


def test_the_shape_page_s_check_menu_sets_it_by_the_query(tmp_path, kms):
    from semforge.cooked.shapepage import build_shape_page

    page = dict(build_shape_page(load(str(kms)), CUTTER), ok=True)
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': {'shape': CUTTER}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'checkMenu', 'row': 0}],
        'picks': ['$(warning) Severity…', 'warning'],
        'replies': {'semforge/shapePage': page, 'semforge/severityLevels': LEVELS,
                    'semforge/setSeverity': {'ok': True, 'file': '/f', 'severity': 'x'}}})
    assert _asked(seen, 'semforge/setSeverity') == [{
        'uri': 'file:///pkg/shacl.ttl', 'severity': 'sh:Warning', 'shape': CUTTER,
        'query': page['checks'][0]['query']}]
