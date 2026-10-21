"""Commands no other test ran: a project from nothing, removing a constraint,
and the jumps from a row to its source.

Driven through the extension with the Node harness, like the other command
tests; what is checked is what the command asks, and what it sends.
"""

import json
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')
PACKAGE = 'file:///pkg/shacl.ttl'


def _drive(tmp_path, scenario, workspace=None):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    result = subprocess.run([node, DRIVE, str(workspace or tmp_path),
                             os.path.join(SRC, 'extension.js'), str(path)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-1500:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def _sent(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


INIT = {'ok': True, 'files': ['shacl.ttl', 'knowledge.ttl'], 'constraints': 3,
        'violations': 1, 'root': '', 'open': '/x/shacl.ttl'}


# --- a new project ----------------------------------------------------------------

def test_new_project_asks_name_namespace_layout_and_creates_it(tmp_path):
    parent = tmp_path / 'projects'
    parent.mkdir()
    seen = _drive(tmp_path, {
        'command': 'semforge.newProject', 'node': {'fsPath': str(parent)},
        'inputs': ['My Pump', 'https://example.org/pump/'],
        'picks': ['flat', '$(check) Stay here'],
        'replies': {'semforge/init': INIT}})
    assert [i['title'] for i in seen['inputs']] == ['Project name', 'Base IRI for My Pump']
    assert seen['inputs'][1]['value'] == 'https://example.org/my-pump/', 'suggested from the name'
    assert _sent(seen, 'semforge/init') == [{
        'path': str(parent / 'my-pump'), 'name': 'My Pump',
        'namespace': 'https://example.org/pump/', 'layout': 'flat'}]
    assert any('2 files' in message for message in seen['info'])


def test_new_project_refuses_a_folder_that_is_not_empty(tmp_path):
    parent = tmp_path / 'projects'
    (parent / 'my-pump').mkdir(parents=True)
    (parent / 'my-pump' / 'notes.txt').write_text('mine')
    seen = _drive(tmp_path, {
        'command': 'semforge.newProject', 'node': {'fsPath': str(parent)},
        'inputs': ['My Pump', 'https://example.org/pump/'],
        'picks': ['model/ groups the data (recommended)'],
        'replies': {'semforge/init': INIT}})
    assert _sent(seen, 'semforge/init') == []
    assert any('not empty' in message for message in seen['errors'])


def test_cancelling_the_name_creates_nothing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.newProject', 'node': {'fsPath': str(tmp_path)},
        'replies': {'semforge/init': INIT}})
    assert _sent(seen, 'semforge/init') == []


def test_init_package_makes_the_open_folder_one_and_opens_its_shapes(tmp_path):
    workspace = tmp_path / 'empty-folder'
    workspace.mkdir()
    seen = _drive(tmp_path, {
        'command': 'semforge.initPackage',
        'inputs': ['empty-folder', 'https://example.org/empty-folder/'],
        'picks': ['flat'],
        'replies': {'semforge/init': dict(INIT, open=str(workspace / 'shacl.ttl'))}},
        workspace=workspace)
    assert seen['inputs'][0]['value'] == 'empty-folder', 'the folder names it'
    sent = _sent(seen, 'semforge/init')
    assert sent and sent[0]['path'] == str(workspace) and sent[0]['layout'] == 'flat'
    assert seen['shown'][0]['file'] == str(workspace / 'shacl.ttl')


# --- removing a constraint ------------------------------------------------------------

CONSTRAINT = {'kind': 'parameter', 'label': 'sh:minCount 1', 'editable': True,
              'parameter': 'sh:minCount', 'path': ['ex:hasValve'], 'shape': 'https://x/PumpShape',
              'children': []}


@pytest.mark.parametrize('answer, removed', [('Remove', True), (None, False)])
def test_removing_a_constraint_asks_first(tmp_path, answer, removed):
    scenario = {'command': 'semforge.removeConstraint',
                'node': {'raw': CONSTRAINT, 'packageUri': PACKAGE},
                'replies': {'semforge/setConstraint': {'ok': True}}}
    if answer:
        scenario['answer'] = answer
    seen = _drive(tmp_path, scenario)
    assert any('Remove sh:minCount from ex:hasValve' in w for w in seen['warnings'])
    sent = _sent(seen, 'semforge/setConstraint')
    assert sent == ([{'uri': PACKAGE, 'shape': 'https://x/PumpShape', 'path': ['ex:hasValve'],
                      'parameter': 'sh:minCount', 'remove': True}] if removed else [])


def test_a_constraint_that_is_not_editable_is_left_alone(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.removeConstraint', 'answer': 'Remove',
                             'node': {'raw': dict(CONSTRAINT, editable=False),
                                      'packageUri': PACKAGE},
                             'replies': {}})
    assert seen['warnings'] == [] and seen['requests'] == []


# --- from a row to where it is written -------------------------------------------------

def test_show_shape_for_a_class_opens_its_shape(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.showShapeForClass',
                             'node': {'raw': {'kind': 'class', 'label': 'Pump',
                                              'shape': 'https://x/PumpShape',
                                              'shapeAt': '/pkg/shacl.ttl:12', 'children': []},
                                      'packageUri': PACKAGE},
                             'replies': {}})
    assert (seen['shown'][0]['file'], seen['shown'][0]['line']) == ('/pkg/shacl.ttl', 11)
    assert seen['errors'] == [], 'the Types view was never loaded, and that is fine'


@pytest.mark.parametrize('detail, says', [('1 shape inherited', 'further up the hierarchy'),
                                          ('', 'Nothing checks it')])
def test_a_class_without_its_own_shape_says_what_checks_it(tmp_path, detail, says):
    seen = _drive(tmp_path, {'command': 'semforge.showShapeForClass',
                             'node': {'raw': {'kind': 'class', 'label': 'Lasercutter',
                                              'detail': detail, 'children': []},
                                      'packageUri': PACKAGE},
                             'replies': {}})
    assert seen['shown'] == []
    assert any(says in message for message in seen['info'])


def test_go_to_definition_opens_where_the_row_is_written(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.goToDefinition',
                             'node': {'raw': {'kind': 'attribute', 'label': 'hasValve',
                                              'definedAt': '/pkg/shacl.ttl:40', 'children': []},
                                      'packageUri': PACKAGE},
                             'replies': {'semforge/tree': {'roots': []}}})
    assert seen['shown'][-1]['file'] == '/pkg/shacl.ttl' and seen['shown'][-1]['line'] == 39


# --- revalidate, refresh ----------------------------------------------------------------------

def test_revalidate_saves_the_active_file_so_the_server_analyses_it(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.openSource',
        'node': {'raw': {'kind': 'attribute', 'label': 'x', 'definedAt': '/pkg/shacl.ttl:3',
                         'children': []}, 'packageUri': PACKAGE},
        'then': [{'command': 'semforge.revalidate'}], 'replies': {}})
    assert seen['errors'] == [], seen['errors']
    assert {'type': 'saved', 'uri': 'file:///pkg/shacl.ttl'} in seen['events']


def test_revalidate_without_an_editor_does_nothing(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.revalidate', 'replies': {}})
    assert seen['errors'] == [] and not [e for e in seen['events'] if e['type'] == 'saved']


@pytest.mark.parametrize('command', ['semforge.refreshProject', 'semforge.refreshTree',
                                     'semforge.refreshShapes', 'semforge.refreshModel',
                                     'semforge.refreshKnowledge'])
def test_refresh_redraws_its_view(tmp_path, command):
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    seen = _drive(tmp_path, {'command': command, 'replies': {}})
    assert seen['errors'] == [], seen['errors']
    before = len([e for e in _drive(tmp_path, {'command': 'semforge.revalidate',
                                               'replies': {}})['events']
                  if e['type'] == 'refresh'])
    assert len([e for e in seen['events'] if e['type'] == 'refresh']) > before
