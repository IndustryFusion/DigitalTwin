"""The extension against what the server REALLY sends.

The harness tests elsewhere feed hand-written payloads, and a hand-written
payload agrees with the code it was written for: a click that looked for a
"Model data" example passed its test and matched no row the server sends.
Here every payload comes from the server's own handlers, on a copy of the kms
corpus, in both tree modes -- so a change on either side that breaks the
other fails here.

The end-to-end tests (vscode/test/e2e, `npm run test:e2e`) go further, in a
real VS Code; these are the fast half that runs with every `pytest`.
"""

import json
import os
import shutil
import subprocess
from unittest import mock

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')


@pytest.fixture(scope='module')
def kms(tmp_path_factory, corpus_path):
    # Followed, not linked: the corpus files are symlinks into semantic-model/kms.
    target = tmp_path_factory.mktemp('contracts') / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _uri(kms):
    return f'file://{kms}/shacl.ttl'


def _server(feature, kms, **params):
    from semforge.editor import server
    return getattr(server, feature)(mock.MagicMock(), dict({'uri': _uri(kms)}, **params))


def _drive(tmp_path, scenario):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    # The extension's session needs a package in its workspace to show one.
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    result = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                             str(path)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-1500:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def _executed(seen, command):
    return [e['args'] for e in seen['executed'] if e['command'] == command]


# --- the Instances view: every kind of row, as the server sends it ------------------

@pytest.fixture(scope='module', params=['summary', 'full'])
def instances(request, kms):
    payload = _server('model', kms, detail=request.param)
    assert not payload.get('error'), payload
    return request.param, payload


def _click(tmp_path, kms, instances, label_path):
    detail, payload = instances
    return _drive(tmp_path, {
        'mode': 'select', 'view': 'semforgeModel', 'labelPath': label_path,
        'config': {'trees.detail': detail},
        'replies': {'semforge/model': payload, 'semforge/tree': {'roots': []},
                    'semforge/shapes': {'roots': []}, 'semforge/knowledge': {'roots': []}}})


def _first(nodes, kind):
    return next(n for n in nodes if n['kind'] == kind)


def test_the_view_holds_main_then_tests(instances):
    _, payload = instances
    assert [r['label'] for r in payload['roots']] == ['Main', 'Tests']


def test_every_row_under_main_opens_the_main_page(tmp_path, kms, instances):
    _, payload = instances
    main = payload['roots'][0]
    document = main['children'][0]
    entity = _first(document['children'], 'entity')
    for path, focus in [(['Main'], None), (['Main', document['label']], None),
                        (['Main', document['label'], entity['label']], entity['entity'])]:
        seen = _click(tmp_path, kms, instances, path)
        assert seen['errors'] == [], seen['errors']
        opened = _executed(seen, 'semforge.openModelPage')
        assert len(opened) == 1, (path, seen['executed'])
        assert opened[0][1].get('focus') == focus, path
        assert _executed(seen, 'semforge.openCasePage') == []
        assert seen['shown'] == [], f'{path} jumped to the source instead'


def test_a_case_and_its_rows_open_the_case_page(tmp_path, kms, instances):
    _, payload = instances
    tests = payload['roots'][1]
    suite = _first(tests['children'], 'suite')
    case = _first(suite['children'], 'example')
    entity = _first(case['children'], 'entity')
    for path in (['Tests', suite['label'], case['label']],
                 ['Tests', suite['label'], case['label'], entity['label']]):
        seen = _click(tmp_path, kms, instances, path)
        assert seen['errors'] == [], seen['errors']
        opened = _executed(seen, 'semforge.openCasePage')
        assert len(opened) == 1, (path, seen['executed'])
        assert opened[0][0]['raw']['file'] == case['file']
        assert _executed(seen, 'semforge.openModelPage') == []


# --- the pages, from their real payloads --------------------------------------------

def test_the_main_page_payload_renders_with_its_edits(tmp_path, kms):
    page = _server('model_page_feature', kms)
    assert page['ok'] and page['kind'] == 'model' and page['name'] == 'Main'
    seen = _drive(tmp_path, {
        'command': 'semforge.openModelPage', 'replies': {'semforge/modelPage': page},
        'webviewMessages': [{'command': 'addEntity', 'at': '0'},
                            {'command': 'addAttribute', 'at': '0.0'}]})
    assert seen['errors'] == [], seen['errors']
    html = seen['webviews'][0]['html'][0]
    assert seen['webviews'][0]['title'] == 'Main · instances'
    assert 'data-addentity="0"' in html and 'data-edit="0.' in html
    assert _executed(seen, 'semforge.addEntity')[0][0]['raw']['file'] == page['files'][0]['path']
    raw = _executed(seen, 'semforge.addAttribute')[0][0]['raw']
    # The entity's row -- plus what it already has, by datasetId (children).
    assert {k: v for k, v in raw.items() if k != 'children'} == \
        {k: v for k, v in page['files'][0]['cards'][0]['node'].items() if k != 'children'}


def test_a_shapeless_subtype_s_page_offers_plus_attribute(tmp_path, kms):
    page = _server('type_page_feature', kms, entityType='iffBaseEntities:Plasmacutter')
    assert page['ok'] and page['ownShape'] == '' and page['attributes']
    made = {'ok': True, 'iri': 'https://x/PlasmacutterShape', 'name': 'PlasmacutterShape'}
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'label': 'Plasmacutter', 'targetClass': page['iri'],
                         'children': []}, 'packageUri': _uri(kms)},
        'webviewMessages': [{'command': 'addAttribute', 'row': -1}],
        'commandResults': {'semforge.newShape': made},
        'replies': {'semforge/typePage': page}})
    assert seen['errors'] == [], seen['errors']
    assert 'data-action="addAttribute"' in seen['webviews'][0]['html'][0]
    assert _executed(seen, 'semforge.newShape')[0][0]['raw']['targetClass'] == page['iri']
    assert _executed(seen, 'semforge.addAttributeConstraint')[0][0]['raw']['shape'] == made['iri']


# --- a relationship's picker, from a real row and the real choices -------------------

def _relationship_row(kms):
    from semforge.cooked.examples import build_suite
    from semforge.editor.server import _serialise_example
    from semforge.package import load

    def walk(node):
        yield node
        for child in node.get('children', []):
            yield from walk(child)

    roots = [_serialise_example(n) for n in build_suite(load(kms))]
    return next(n for root in roots for n in walk(root)
                if n.get('editable') and (n.get('path') or [None])[-1] == 'object'
                and 'hasCartridge' in str(n['path'][0]))


def test_a_real_relationship_row_gets_every_entity_and_takes_a_typed_iri(tmp_path, kms):
    row = _relationship_row(kms)
    attribute = [p for p in row['path'] if isinstance(p, str) and ':' in p][-1]
    choices = _server('value_choices_feature', kms, entityType=row['entityType'],
                      attribute=attribute.split(':')[-1], relationship=True, file=row['file'])
    assert choices['choices'] and choices['others'], choices
    scenario = {
        'command': 'semforge.editValue', 'node': {'raw': row, 'packageUri': _uri(kms)},
        'replies': {'semforge/valueChoices': choices,
                    'semforge/setValue': {'ok': True, 'old': 'a', 'new': 'b'}}}

    other = choices['others'][0]['value']
    seen = _drive(tmp_path, dict(scenario, pick=other))
    labels = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert labels.index(choices['choices'][-1]['label']) < labels.index(other)
    sent = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/setValue']
    assert sent[0]['value'] == other and sent[0]['path'] == row['path']

    seen = _drive(tmp_path, dict(scenario, typed='urn:pump:42', pick='$(edit) Use urn:pump:42'))
    sent = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/setValue']
    assert sent[0]['value'] == 'urn:pump:42'
