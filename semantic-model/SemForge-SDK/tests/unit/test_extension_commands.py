"""What the commands and the trees actually DO.

`test_extension_activates.py` proves the extension loads and registers its
commands. It cannot see what a handler does with the row it is given -- and that
is where every recent failure has been:

  * the shape icon sent `attributePath[0]`, the PARENT attribute's name, so a
    sub-attribute jumped to the wrong shape;
  * a tree turned the server's "not a SemForge package" into an empty panel with
    no message, which reads as the extension being broken;
  * `reveal()` could not resolve its own node after a refresh, because identity
    was the raw object and a refetch replaces it.

None of those throw and none of them log. So the handlers are driven here
against a stub `vscode` and a canned server.
"""

import json
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
FULL_ONLY = ' && config.semforge.trees.detail == full'
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')

SHAPE_REPLY = {
    'ok': True, 'how': 'found', 'shape': 'http://example.com/FilterShape',
    'shapeName': 'iffBaseShacl:FilterShape', 'file': '/pkg/shacl.ttl',
    'line': 105, 'inherited': False, 'slot': 'ngsild:hasValue', 'exists': True,
}


def _drive(tmp_path, scenario, target='extension.js', workspace=None):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    result = subprocess.run(
        [node, DRIVE, str(workspace or tmp_path),
         os.path.join(SRC, target), str(path)],
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-1500:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def _row(**overrides):
    raw = {
        'kind': 'attribute', 'label': 'hasStrength', 'entity': 'urn:filter:1',
        'entityType': 'iffBaseEntities:Filter', 'editable': True,
        'attributePath': ['iffBaseEntities:hasStrength'],
        'path': ['iffBaseEntities:hasStrength', 0, 'value'],
        'value': '0.6', 'children': [],
    }
    raw.update(overrides)
    return {'raw': raw, 'packageUri': 'file:///pkg/shacl.ttl'}


# --- the shape jump ----------------------------------------------------------

def test_the_shape_icon_asks_for_the_attribute_and_opens_the_line(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.goToShape', 'node': _row(),
        'replies': {'semforge/shapeFor': SHAPE_REPLY},
    })
    asked = [r for r in seen['requests'] if r['method'] == 'semforge/shapeFor']
    assert len(asked) == 1
    assert asked[0]['params']['attribute'] == 'iffBaseEntities:hasStrength'
    assert asked[0]['params']['entityType'] == 'iffBaseEntities:Filter'
    assert asked[0]['params']['create'] is False
    # Line 105 of the file, zero-based in the editor.
    assert seen['shown'] == [{'file': '/pkg/shacl.ttl', 'line': 104,
                              'preserveFocus': False}]
    assert seen['warnings'] == [] and seen['errors'] == []


def test_a_sub_attribute_jumps_to_its_own_shape_not_its_parents(tmp_path):
    """`attributePath[0]` is the TOP attribute.

    hasXXXWorkpiece sits under hasState, and sending `hasState` would open the
    wrong shape while looking like it worked.
    """
    seen = _drive(tmp_path, {
        'command': 'semforge.goToShape',
        'node': _row(label='hasXXXWorkpiece',
                     attributePath=['iffBaseEntities:hasState', 0,
                                    'iffBaseEntities:hasXXXWorkpiece'],
                     path=['iffBaseEntities:hasState', 0,
                           'iffBaseEntities:hasXXXWorkpiece', 0, 'object']),
        'replies': {'semforge/shapeFor': SHAPE_REPLY},
    })
    asked = [r for r in seen['requests'] if r['method'] == 'semforge/shapeFor']
    assert asked[0]['params']['attribute'] == 'iffBaseEntities:hasXXXWorkpiece'


def test_a_missing_shape_is_offered_and_then_created(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.goToShape', 'node': _row(),
        'answer': 'Create an empty one',
        'replies': {'semforge/shapeFor': {'ok': False, 'exists': False,
                                          'error': 'no shape constrains it'}},
    })
    # Asked before writing: this edits shacl.ttl.
    assert any('No shape constrains' in m for m in seen['info'])
    asked = [r for r in seen['requests'] if r['method'] == 'semforge/shapeFor']
    assert [r['params']['create'] for r in asked] == [False, True]


def test_declining_the_offer_writes_nothing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.goToShape', 'node': _row(),
        'replies': {'semforge/shapeFor': {'ok': False, 'exists': False,
                                          'error': 'no shape constrains it'}},
    })
    asked = [r for r in seen['requests'] if r['method'] == 'semforge/shapeFor']
    assert [r['params']['create'] for r in asked] == [False]
    assert seen['shown'] == []


def test_a_server_that_does_not_know_the_method_says_so(tmp_path):
    """An older server than the extension is exactly what happened.

    The request rejected, the rejection was never caught, and the click did
    nothing at all -- no jump, no message, nothing in the log.
    """
    seen = _drive(tmp_path, {
        'command': 'semforge.goToShape', 'node': _row(), 'replies': {},
    })
    assert seen['errors'], 'a rejected request produced no message'
    assert 'Unhandled method semforge/shapeFor' in seen['errors'][0]


def test_a_row_without_a_type_says_which_half_is_missing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.goToShape',
        'node': _row(entityType=''), 'replies': {},
    })
    assert seen['warnings'] and 'entity type' in seen['warnings'][0]
    assert seen['requests'] == []


# --- the value picker --------------------------------------------------------

def test_editing_a_value_offers_the_classes_the_shape_allows(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.editValue',
        'node': _row(label='hasState',
                     attributePath=['iffBaseEntities:hasState'],
                     path=['iffBaseEntities:hasState', 0, 'value'],
                     value='{"@id": "base:state_ON"}'),
        'pick': 'state_OFF',
        'replies': {
            'semforge/valueChoices': {'choices': [
                {'value': '{"@id": "base:state_ON"}', 'label': 'state_ON',
                 'detail': 'MachineState'},
                {'value': '{"@id": "base:state_OFF"}', 'label': 'state_OFF',
                 'detail': 'MachineState'}], 'note': ''},
            'semforge/setValue': {'ok': True, 'old': 'state_ON',
                                  'new': 'state_OFF'},
        },
    })
    assert seen['quickPicks'], 'no picker was offered'
    labels = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert 'state_ON' in labels and 'state_OFF' in labels
    # And an escape hatch, because the list is a convenience not a restriction.
    assert any('Type a value' in label for label in labels)
    assert seen['inputs'] == [], 'asked for free text despite having options'
    written = [r for r in seen['requests'] if r['method'] == 'semforge/setValue']
    assert written[0]['params']['value'] == '{"@id": "base:state_OFF"}'


RELATIONSHIP_ROW = dict(label='hasCartridge', attributePath=['iffBaseEntities:hasCartridge'],
                        path=['iffBaseEntities:hasCartridge', 0, 'object'],
                        value='urn:cartridge:1', file='/pkg/examples/x/good/case.jsonld')
CARTRIDGES = {'choices': [
    {'value': 'urn:cartridge:1', 'label': 'urn:cartridge:1', 'detail': 'FilterCartridge'},
    {'value': 'urn:cartridge:2', 'label': 'urn:cartridge:2', 'detail': 'FilterCartridge'}],
    'note': '',
    'others': [{'value': 'urn:workpiece:1', 'label': 'urn:workpiece:1',
                'detail': 'Workpiece'}]}


def _relationship(tmp_path, **scenario):
    return _drive(tmp_path, dict({
        'command': 'semforge.editValue', 'node': _row(**RELATIONSHIP_ROW),
        'replies': {'semforge/valueChoices': CARTRIDGES,
                    'semforge/setValue': {'ok': True, 'old': 'a', 'new': 'b'}}}, **scenario))


def _written(seen):
    return [r['params']['value'] for r in seen['requests']
            if r['method'] == 'semforge/setValue']


def test_a_relationship_offers_the_shape_s_entities_then_every_other(tmp_path):
    seen = _relationship(tmp_path, pick='urn:workpiece:1')
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/valueChoices']
    assert asked[0]['relationship'] is True
    assert asked[0]['file'] == RELATIONSHIP_ROW['file']
    items = seen['quickPicks'][0]['items']
    labels = [i['label'] for i in items]
    assert labels.index('urn:cartridge:2') < labels.index('urn:workpiece:1')
    assert any(i['separator'] and 'may flag' in i['label'] for i in items)
    assert _written(seen) == ['urn:workpiece:1']


def test_a_typed_iri_is_written_as_typed(tmp_path):
    """Any IRI goes, including one no entity in the package has."""
    seen = _relationship(tmp_path, typed='urn:pump:42', pick='$(edit) Use urn:pump:42')
    assert seen['quickPicks'][0]['items'][0]['label'] == '$(edit) Use urn:pump:42'
    assert _written(seen) == ['urn:pump:42']
    assert seen['inputs'] == []


@pytest.mark.parametrize('typed', ['pump 42', 'pump42', 'urn:'])
def test_what_is_not_an_iri_is_refused_and_says_why(tmp_path, typed):
    seen = _relationship(tmp_path, typed=typed, pick=f'$(error) {typed}')
    first = seen['quickPicks'][0]['items'][0]
    assert first['label'] == f'$(error) {typed}' and 'not an IRI' in first['description']
    assert any(e['type'] == 'quickPickStayedOpen' for e in seen['events'])
    assert _written(seen) == []


def test_a_property_s_typed_value_is_not_held_to_iri_rules(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.editValue',
        'node': _row(label='hasState', attributePath=['iffBaseEntities:hasState'],
                     path=['iffBaseEntities:hasState', 0, 'value'],
                     value='{"@id": "base:state_ON"}'),
        'typed': '{"@id": "base:state_X"}', 'pick': '$(edit) Use {"@id": "base:state_X"}',
        'replies': {'semforge/valueChoices': {'choices': [
            {'value': '{"@id": "base:state_ON"}', 'label': 'state_ON'}], 'note': ''},
            'semforge/setValue': {'ok': True, 'old': 'a', 'new': 'b'}}})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/valueChoices']
    assert asked[0]['relationship'] is False
    assert _written(seen) == ['{"@id": "base:state_X"}']


def test_a_relationship_without_a_class_still_lists_the_entities(tmp_path):
    seen = _relationship(tmp_path, pick='urn:workpiece:1', replies={
        'semforge/valueChoices': {'choices': [], 'note': 'no sh:class',
                                  'others': CARTRIDGES['others']},
        'semforge/setValue': {'ok': True, 'old': 'a', 'new': 'b'}})
    assert seen['inputs'] == []
    assert _written(seen) == ['urn:workpiece:1']


def test_a_value_with_no_class_constraint_still_gets_an_input_box(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.editValue', 'node': _row(),
        'input': '0.8',
        'replies': {
            'semforge/valueChoices': {'choices': [],
                                      'note': 'no sh:class for hasStrength'},
            'semforge/setValue': {'ok': True, 'old': '0.6', 'new': '0.8'},
        },
    })
    assert seen['quickPicks'] == []
    assert seen['inputs'], 'no way to enter a value'
    written = [r for r in seen['requests'] if r['method'] == 'semforge/setValue']
    assert written[0]['params']['value'] == '0.8'


def test_editing_survives_a_server_without_the_choices_method(tmp_path):
    """The picker is an addition; losing it must not cost the edit."""
    seen = _drive(tmp_path, {
        'command': 'semforge.editValue', 'node': _row(), 'input': '0.8',
        'replies': {'semforge/setValue': {'ok': True, 'old': '0.6',
                                          'new': '0.8'}},
    })
    assert seen['inputs'], 'the edit was lost with the picker'
    written = [r for r in seen['requests'] if r['method'] == 'semforge/setValue']
    assert written and written[0]['params']['value'] == '0.8'


# --- the trees ---------------------------------------------------------------

@pytest.mark.parametrize('target,provider,method', [
    ('model.js', 'ModelTreeProvider', 'semforge/model'),
    ('knowledge.js', 'KnowledgeTreeProvider', 'semforge/knowledge'),
    ('tree.js', 'CookedTreeProvider', 'semforge/tree'),
])
def test_a_server_error_reaches_the_panel(tmp_path, target, provider, method):
    """An empty tree with no message is the failure this project keeps meeting.

    The knowledge tree did exactly that: the server said "not a SemForge
    package" and the panel said nothing.
    """
    seen = _drive(tmp_path, {
        'mode': 'tree', 'provider': provider, 'uri': 'file:///pkg/shacl.ttl',
        'replies': {method: {'roots': [], 'error': 'not a SemForge package'}},
    }, target=target)
    assert seen['tree']['roots'] == []
    assert 'not a SemForge package' in (seen['tree']['message'] or '')


@pytest.mark.parametrize('target,provider,method', [
    ('model.js', 'ModelTreeProvider', 'semforge/model'),
    ('knowledge.js', 'KnowledgeTreeProvider', 'semforge/knowledge'),
])
def test_a_node_keeps_its_identity_across_a_refetch(tmp_path, target, provider,
                                                    method):
    """reveal() needs the node the view already holds.

    The tree follows the active editor, so opening the file a click selected
    refreshes it -- and with identity tied to the raw object, the node being
    revealed was already a stranger: "Failed to resolve tree node".
    """
    roots = [{'kind': 'group', 'label': 'a root', 'entity': 'urn:x', 'iri': 'i',
              'children': [{'kind': 'class', 'label': 'a child', 'iri': 'c',
                            'entity': 'urn:y', 'children': []}]}]
    seen = _drive(tmp_path, {
        'mode': 'tree', 'provider': provider, 'uri': 'file:///pkg/shacl.ttl',
        'replies': {method: {'roots': roots}},
    }, target=target)
    assert seen['tree']['identityKept'] is True
    assert seen['tree']['childIdentityKept'] is True, \
        'a child node lost its identity, so reveal cannot resolve it'


def test_a_tree_with_no_package_says_what_it_looked_for(tmp_path):
    seen = _drive(tmp_path, {
        'mode': 'tree', 'provider': 'KnowledgeTreeProvider', 'uri': None,
        'replies': {},
    }, target='knowledge.js')
    assert 'No SemForge package found' in (seen['tree']['message'] or '')
    assert 'knowledge.ttl' in seen['tree']['message']


# --- finding the package -----------------------------------------------------

def _package_at(directory):
    os.makedirs(directory, exist_ok=True)
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        with open(os.path.join(directory, name), 'w') as handle:
            handle.write('')


def test_a_package_in_the_opened_folder_is_found(tmp_path):
    _package_at(str(tmp_path))
    seen = _drive(tmp_path, {'mode': 'locate'}, target='locate.js')
    assert seen['locate']['uri'].endswith('shacl.ttl')


def test_a_package_one_level_below_the_opened_folder_is_found(tmp_path):
    """Opening `semantic-model/` rather than `semantic-model/kms/`.

    This is what made the knowledge tree empty: the search looked only IN the
    folder, and the other two trees hid it by waiting for an editor instead.
    """
    _package_at(str(tmp_path / 'kms'))
    os.makedirs(str(tmp_path / 'other'), exist_ok=True)
    seen = _drive(tmp_path, {'mode': 'locate'}, target='locate.js')
    assert seen['locate']['uri'].endswith('kms/shacl.ttl'), seen['locate']


def test_the_folder_itself_wins_over_a_subdirectory(tmp_path):
    _package_at(str(tmp_path))
    _package_at(str(tmp_path / 'kms'))
    seen = _drive(tmp_path, {'mode': 'locate'}, target='locate.js')
    assert not seen['locate']['uri'].endswith('kms/shacl.ttl')


def test_no_package_gives_a_message_naming_what_was_looked_for(tmp_path):
    seen = _drive(tmp_path, {'mode': 'locate'}, target='locate.js')
    assert seen['locate']['uri'] is None
    for expected in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld',
                     'one level below', str(tmp_path)):
        assert expected in seen['locate']['message']


# --- clicking a usage row ----------------------------------------------------

def test_clicking_a_usage_row_opens_the_file_and_shows_the_entity(tmp_path):
    """A row saying "urn:filter:1 uses this term" has to be able to show it.

    Clicking it did nothing: usage rows carried no location, and nothing
    connected them to the examples tree where the entity lives.
    """
    _package_at(str(tmp_path))
    entity = {'kind': 'entity', 'label': 'urn:filter:1', 'entity': 'urn:filter:1',
              'entityType': 'iffBaseEntities:Filter', 'children': []}
    seen = _drive(tmp_path, {
        'mode': 'select', 'view': 'semforgeKnowledge',
        'node': {'key': 'root/0:usage', 'raw': {
            'kind': 'usage', 'label': 'urn:filter:1', 'entity': 'urn:filter:1',
            'detail': 'hasState · model-instance.jsonld',
            'definedAt': f'{tmp_path}/model-instance.jsonld:141',
            'children': []}},
        'replies': {
            'semforge/model': {'roots': [
                {'kind': 'example', 'label': 'a case', 'children': [entity]}]},
            'semforge/knowledge': {'roots': []},
            'semforge/tree': {'roots': []},
        },
    })
    assert seen['shown'] == [{'file': f'{tmp_path}/model-instance.jsonld',
                              'line': 140, 'preserveFocus': True}]
    shown_in_examples = [r for r in seen['revealed']
                         if r['view'] == 'semforgeModel']
    assert shown_in_examples, \
        f'the entity was never shown in the examples tree: {seen["revealed"]}'
    assert shown_in_examples[0]['options'].get('select') is True
    # And it does not re-fetch the tree per level: the root fetch re-validates
    # the whole package, so one click would cost several seconds.
    fetches = [r for r in seen['requests'] if r['method'] == 'semforge/model']
    assert len(fetches) <= 2, f'{len(fetches)} tree fetches for one click'
    # Nothing may refresh a tree before the reveal. VS Code drops its element
    # handles when a tree fires onDidChangeTreeData, so a reveal afterwards
    # resolves nothing and logs "Failed to resolve tree node" -- which is what
    # opening the file used to cause, through the active-editor listener.
    order = [event['type'] for event in seen['events']]
    after = order[order.index('click'):]
    assert 'reveal' in after, order
    assert 'refresh' not in after[:after.index('reveal')], order


def test_clicking_an_instance_row_opens_the_entity_too(tmp_path):
    """An instance row says "this class is instantiated here".

    Same promise as a usage row, so the same two halves: the file, and the row
    in the examples tree.
    """
    _package_at(str(tmp_path))
    entity = {'kind': 'entity', 'label': 'urn:filter:1', 'entity': 'urn:filter:1',
              'entityType': 'iffBaseEntities:Filter', 'children': []}
    seen = _drive(tmp_path, {
        'mode': 'select', 'view': 'semforgeKnowledge',
        'node': {'key': 'root/0:instance', 'raw': {
            'kind': 'instance', 'label': 'urn:filter:1',
            'entity': 'urn:filter:1', 'detail': 'model-instance.jsonld',
            'definedAt': '/pkg/model-instance.jsonld:100', 'children': []}},
        'replies': {
            'semforge/model': {'roots': [
                {'kind': 'example', 'label': 'a case', 'children': [entity]}]},
            'semforge/knowledge': {'roots': []},
            'semforge/tree': {'roots': []},
        },
    })
    assert seen['shown'] == [{'file': '/pkg/model-instance.jsonld', 'line': 99,
                              'preserveFocus': True}]
    assert [r for r in seen['revealed'] if r['view'] == 'semforgeModel'], \
        f'the entity was never shown in the examples tree: {seen["revealed"]}'


def test_clicking_a_class_row_does_not_chase_an_entity(tmp_path):
    """Only a usage row names an entity; the others must not try."""
    _package_at(str(tmp_path))
    seen = _drive(tmp_path, {
        'mode': 'select', 'view': 'semforgeKnowledge',
        'node': {'key': 'root/0:class', 'raw': {
            'kind': 'class', 'label': 'base:MachineState',
            'definedAt': '/pkg/knowledge.ttl:625', 'children': []}},
        'replies': {'semforge/knowledge': {'roots': []},
                    'semforge/tree': {'roots': []}},
    })
    assert seen['shown'] == [{'file': '/pkg/knowledge.ttl', 'line': 624,
                              'preserveFocus': True}]
    assert [r for r in seen['requests']
            if r['method'] == 'semforge/model'] == []


def test_the_revealed_row_is_the_one_in_the_file_that_was_clicked(tmp_path):
    """urn:cartridge:1 exists in the shipped model and in a subobject.

    Revealing the first row with that id would show the wrong occurrence for
    every click on the others -- wrong in the quietest possible way, since both
    rows look identical.
    """
    _package_at(str(tmp_path))

    def entity(file):
        return {'kind': 'entity', 'label': 'urn:cartridge:1',
                'entity': 'urn:cartridge:1', 'file': file, 'children': []}

    seen = _drive(tmp_path, {
        'mode': 'select', 'view': 'semforgeKnowledge',
        'node': {'key': 'k', 'raw': {
            'kind': 'instance', 'label': 'urn:cartridge:1',
            'entity': 'urn:cartridge:1', 'file': '/pkg/cartridge-fresh.jsonld',
            'definedAt': '/pkg/cartridge-fresh.jsonld:2', 'children': []}},
        'replies': {
            'semforge/model': {'roots': [
                {'kind': 'example', 'label': 'shipped',
                 'children': [entity('/pkg/model-instance.jsonld')]},
                {'kind': 'example', 'label': 'subobject',
                 'children': [entity('/pkg/cartridge-fresh.jsonld')]}]},
            'semforge/knowledge': {'roots': []},
            'semforge/tree': {'roots': []},
        },
    })
    revealed = [r for r in seen['revealed'] if r['view'] == 'semforgeModel']
    assert revealed, 'nothing was revealed'
    # Key carries the position, so the second root is the one that was shown.
    assert revealed[0]['key'].startswith('/1:'), revealed[0]['key']


def test_opening_a_file_in_the_package_already_shown_refreshes_nothing(tmp_path):
    """Following the active editor is for REACHING a package, not for churn.

    Every click opens a file, so refreshing on that re-validated the whole
    package on every click -- and the refresh dropped VS Code's element handles,
    which is what broke reveal.
    """
    _package_at(str(tmp_path))
    entity = {'kind': 'entity', 'label': 'urn:filter:1', 'entity': 'urn:filter:1',
              'file': f'{tmp_path}/model-instance.jsonld', 'children': []}
    seen = _drive(tmp_path, {
        'mode': 'select', 'view': 'semforgeKnowledge',
        'node': {'key': 'k', 'raw': {
            'kind': 'instance', 'label': 'urn:filter:1',
            'entity': 'urn:filter:1',
            'file': f'{tmp_path}/model-instance.jsonld',
            'definedAt': f'{tmp_path}/model-instance.jsonld:100',
            'children': []}},
        'replies': {
            'semforge/model': {'roots': [
                {'kind': 'example', 'label': 'shipped', 'children': [entity]}]},
            'semforge/knowledge': {'roots': []},
            'semforge/tree': {'roots': []},
        },
    })
    order = [event['type'] for event in seen['events']]
    after = order[order.index('click'):]
    assert 'refresh' not in after, after


def test_the_reveal_lands_before_any_refresh_the_click_causes(tmp_path):
    """A file in ANOTHER package does refresh -- the reveal must precede it.

    This is the ordering guard: with the reveal after the file is opened, the
    refresh invalidates it and VS Code logs "Failed to resolve tree node".
    """
    _package_at(str(tmp_path))
    # A sibling, not a child: a package nested inside the one being shown
    # counts as the same package, which is what keeps kms/examples quiet.
    elsewhere = tmp_path.parent / (tmp_path.name + '-other')
    _package_at(str(elsewhere))
    entity = {'kind': 'entity', 'label': 'urn:filter:1', 'entity': 'urn:filter:1',
              'file': f'{elsewhere}/model-instance.jsonld', 'children': []}
    seen = _drive(tmp_path, {
        'mode': 'select', 'view': 'semforgeKnowledge',
        'node': {'key': 'k', 'raw': {
            'kind': 'usage', 'label': 'urn:filter:1', 'entity': 'urn:filter:1',
            'file': f'{elsewhere}/model-instance.jsonld',
            'definedAt': f'{elsewhere}/model-instance.jsonld:7',
            'children': []}},
        'replies': {
            'semforge/model': {'roots': [
                {'kind': 'example', 'label': 'case', 'children': [entity]}]},
            'semforge/knowledge': {'roots': []},
            'semforge/tree': {'roots': []},
        },
    })
    order = [event['type'] for event in seen['events']]
    after = order[order.index('click'):]
    assert 'reveal' in after, after
    assert 'refresh' in after, 'a different package should refresh'
    assert after.index('reveal') < after.index('refresh'), after


# --- what a row can actually be asked to do -----------------------------------

def _rows_for(tmp_path, roots):
    """Every rendered row of the examples tree, with its contextValue."""
    return _drive(tmp_path, {
        'mode': 'items', 'provider': 'ModelTreeProvider',
        'uri': 'file:///pkg/shacl.ttl',
        'replies': {'semforge/model': {'roots': roots}},
    }, target='model.js')['rows']


def _menu(command):
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        menus = json.load(handle)['contributes']['menus']['view/item/context']
    import re

    values = set()
    for entry in menus:
        if entry['command'] != command or 'semforgeModel' not in entry['when']:
            continue
        values |= set(re.findall(r"viewItem\s*==\s*(\w+)", entry['when']))
        for group in re.findall(r"viewItem\s*=~\s*/([^/]+)/", entry['when']):
            values |= set(re.findall(r"\w+", group))
    return values


def test_every_editable_row_can_be_edited(tmp_path, corpus):
    """The bug this exists to catch: clicking hasState offered no way to change
    it.

    Every attribute carries a datasetId -- `@none` is the default instance, a
    real value -- so every attribute landed on a contextValue whose menu had no
    editValue entry. Driven through the real tree and the real provider, because
    the mismatch is between the data, the JavaScript and package.json.
    """
    from semforge.cooked.examples import build_suite
    from semforge.editor.server import _serialise_example

    roots = [_serialise_example(node) for node in build_suite(corpus)]
    rows = _rows_for(tmp_path, roots)
    # EVERY editable row, whatever its kind. Restricting this to attribute rows
    # is what let the second case through: an attribute with sub-attributes does
    # not fold, so its value sits on an `instance` row -- hasState on the
    # plasmacutter could not be edited while hasState on the filter could.
    editable = [r for r in rows if r['editable']]
    assert editable, 'no editable rows at all'
    assert {r['kind'] for r in editable} >= {'attribute', 'instance'}, \
        'the corpus no longer covers both folded and nested attributes'
    offers_edit = _menu('semforge.editValue')
    missing = {(r['kind'], r['label'], r['contextValue']) for r in editable
               if r['contextValue'] not in offers_edit}
    assert not missing, f'editable rows with no way to edit them: {sorted(missing)}'


def test_no_read_only_row_offers_a_write(tmp_path, corpus):
    """A subobject's rows are read-only, and were offered Add Observation."""
    from semforge.cooked.examples import build_suite
    from semforge.editor.server import _serialise_example

    roots = [_serialise_example(node) for node in build_suite(corpus)]
    rows = _rows_for(tmp_path, roots)
    locked = [r for r in rows if not r['editable'] and r['kind'] in
              ('attribute', 'dataset', 'instance', 'meta')]
    assert locked, 'the corpus has no included subobjects any more'
    writes = _menu('semforge.editValue') | _menu('semforge.addObservation')
    offered = {(r['label'], r['contextValue']) for r in locked
               if r['contextValue'] in writes}
    assert not offered, f'read-only rows offered a write: {sorted(offered)}'


def test_only_a_row_standing_for_a_dataset_takes_an_observation(tmp_path, corpus):
    """An observation joins an attribute's series under one datasetId.

    An instance row or a metadata field is not that, and offering it there would
    write with no attribute path -- the command would bail with a warning.
    """
    from semforge.cooked.examples import build_suite
    from semforge.editor.server import _serialise_example

    roots = [_serialise_example(node) for node in build_suite(corpus)]
    rows = _rows_for(tmp_path, roots)
    offers = _menu('semforge.addObservation')
    for row in rows:
        if row['contextValue'] in offers:
            assert row['kind'] in ('attribute', 'dataset'), row
            assert row['datasetId'], row


# --- editing a file several cases include -------------------------------------

def _shared_row(**overrides):
    raw = {
        'kind': 'attribute', 'label': 'hasHeight', 'entity': 'urn:workpiece:1',
        'entityType': 'iffBaseEntities:Workpiece', 'editable': True,
        'attributePath': ['iffBaseEntities:hasHeight'],
        'path': ['iffBaseEntities:hasHeight', 0, 'value'],
        'value': '5', 'children': [],
        'file': '/pkg/examples/subobjects/workpiece-steel.jsonld',
        'sharedBy': ['test_A/good/a.jsonld', 'test_B/bad/b.jsonld',
                     'test_C/bad/c.jsonld'],
    }
    raw.update(overrides)
    return {'key': 'k', 'raw': raw, 'packageUri': 'file:///pkg/shacl.ttl'}


def test_editing_a_shared_file_asks_how_far_it_reaches(tmp_path):
    """A subobject is editable -- refusing was a restriction JSON-LD does not
    have -- but the reach is worth a question: the same workpiece decides the
    verdict of three cases."""
    seen = _drive(tmp_path, {
        'command': 'semforge.editValue', 'node': _shared_row(),
        'answer': 'Edit anyway', 'input': '0.42',
        'replies': {'semforge/valueChoices': {'choices': [], 'note': ''},
                    'semforge/setValue': {'ok': True, 'old': '5', 'new': '0.42'}},
    })
    asked = seen['warnings'] + seen['info']
    assert any('3 cases' in m for m in asked), asked
    written = [r for r in seen['requests'] if r['method'] == 'semforge/setValue']
    assert written and written[0]['params']['value'] == '0.42'
    # And it writes where the row came from, not into model-instance.jsonld.
    assert written[0]['params']['file'].endswith('workpiece-steel.jsonld')


def test_declining_the_shared_warning_writes_nothing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.editValue', 'node': _shared_row(),
        'input': '0.42',
        'replies': {'semforge/valueChoices': {'choices': [], 'note': ''},
                    'semforge/setValue': {'ok': True}},
    })
    assert [r for r in seen['requests']
            if r['method'] == 'semforge/setValue'] == []
    assert seen['inputs'] == [], 'asked for a value before asking about reach'


def test_a_file_only_one_case_includes_asks_nothing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.editValue',
        'node': _shared_row(sharedBy=['test_A/good/a.jsonld']),
        'input': '0.42',
        'replies': {'semforge/valueChoices': {'choices': [], 'note': ''},
                    'semforge/setValue': {'ok': True, 'old': '5',
                                          'new': '0.42'}},
    })
    assert seen['warnings'] == []
    written = [r for r in seen['requests'] if r['method'] == 'semforge/setValue']
    assert written, 'the edit was blocked by a question nobody needed'


def test_an_included_row_offers_the_pencil(tmp_path, corpus):
    """The rows under an include used to carry only the scales."""
    from semforge.cooked.examples import build_suite
    from semforge.editor.server import _serialise_example

    roots = [_serialise_example(node) for node in build_suite(corpus)]
    rows = _rows_for(tmp_path, roots)
    shared = [r for r in rows if r['kind'] == 'attribute'
              and r['contextValue'] in _menu('semforge.editValue')]
    assert shared
    # Nothing value-bearing is locked for being included any more; the only
    # read-only rows left are rows with no value of their own.
    locked = [r for r in rows if r['contextValue'] == 'attributeReadOnly']
    assert all(not r['editable'] for r in locked)


# --- which package am I on ---------------------------------------------------

def _bare_package(directory, name):
    """The three roles, empty. Enough to be FOUND, which is what is under test."""
    root = directory / name
    root.mkdir(parents=True)
    (root / 'knowledge.ttl').write_text('')
    (root / 'shacl.ttl').write_text('')
    (root / 'model-instance.jsonld').write_text('{"@graph": []}')
    return root


def test_the_status_bar_names_the_package_the_views_are_showing(tmp_path):
    """A window with two packages picked one silently, and said which nowhere."""
    _bare_package(tmp_path, 'alpha')
    _bare_package(tmp_path, 'beta')
    seen = _drive(tmp_path, {'command': 'semforge.doctor'})
    assert seen['statusBar'], 'nothing was painted in the status bar'
    assert 'alpha' in seen['statusBar'][-1]


def test_the_package_can_be_switched_and_the_choice_sticks(tmp_path):
    """Switching is the point: reading a second package must not need a window.

    And once chosen it PINS -- following the active editor is right when there
    is one package and exactly wrong while you are reading a second one.
    """
    _bare_package(tmp_path, 'alpha')
    _bare_package(tmp_path, 'beta')
    seen = _drive(tmp_path, {'command': 'semforge.selectPackage', 'pick': 'beta'})

    offered = [item['label'] for item in seen['quickPicks'][0]['items']]
    assert 'alpha' in offered and 'beta' in offered
    assert 'Follow the active editor' in offered, \
        'there is no way back to following the editor'
    assert 'beta (pinned)' in seen['statusBar'][-1], seen['statusBar']


def test_every_view_says_which_package_it_is_showing(tmp_path):
    """The three views used to each resolve a package of their own.

    Nothing on screen named any of them, so a view quietly showing a different
    package than the one beside it looked like a wrong answer.
    """
    _bare_package(tmp_path, 'alpha')
    _bare_package(tmp_path, 'beta')
    seen = _drive(tmp_path, {'command': 'semforge.selectPackage', 'pick': 'beta'})

    subtitles = {view: state.get('description')
                 for view, state in seen['views'].items()}
    assert set(subtitles) == {'semforgeProject', 'semforgeConstraints', 'semforgeShapes',
                              'semforgeModel', 'semforgeKnowledge'}
    for view, subtitle in subtitles.items():
        assert subtitle and 'beta' in subtitle, f'{view} says {subtitle!r}'


def test_a_package_nested_inside_another_is_offered_too(tmp_path):
    """A scaffolded project sits beside the model it is testing.

    `kms/test` is inside `kms`, so a search that stopped at the first package
    it found never offered it -- and it is exactly the one you just made.
    """
    _bare_package(tmp_path, 'kms')
    _bare_package(tmp_path / 'kms', 'test')
    seen = _drive(tmp_path, {'command': 'semforge.selectPackage', 'pick': 'test'})
    offered = [item['description'] for item in seen['quickPicks'][0]['items']]
    assert any(str(tmp_path / 'kms' / 'test') in (text or '')
               for text in offered), offered


# --- the project view --------------------------------------------------------

def _setting(**overrides):
    raw = {
        'kind': 'setting', 'label': 'published context', 'key': 'context.published',
        'value': 'https://example.org/v0/context.jsonld', 'editable': True,
        'doc': 'Where the context will be served.', 'detail': '', 'children': [],
    }
    raw.update(overrides)
    return {'raw': raw, 'packageUri': 'file:///pkg/shacl.ttl'}


def test_editing_a_setting_writes_it_and_opens_the_line(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.editSetting', 'node': _setting(),
        'input': 'https://example.org/v1/context.jsonld',
        'replies': {'semforge/setSetting': {
            'ok': True, 'file': '/pkg/semforge.yaml', 'line': 11}},
    })
    wrote = [r for r in seen['requests'] if r['method'] == 'semforge/setSetting']
    assert wrote, seen['requests']
    assert wrote[0]['params']['key'] == 'context.published'
    assert wrote[0]['params']['value'] == 'https://example.org/v1/context.jsonld'
    # The current value is offered for editing rather than an empty box.
    assert seen['inputs'][0]['value'] == 'https://example.org/v0/context.jsonld'
    assert seen['shown'] and seen['shown'][-1]['line'] == 10


def test_cancelling_the_edit_writes_nothing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.editSetting', 'node': _setting(),
        'replies': {'semforge/setSetting': {'ok': True}},
    })
    assert not [r for r in seen['requests']
                if r['method'] == 'semforge/setSetting']


def test_a_refused_write_is_reported_rather_than_swallowed(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.editSetting', 'node': _setting(), 'input': 'x',
        'replies': {'semforge/setSetting': {
            'ok': False, 'error': 'anything is not an editable setting'}},
    })
    assert any('not an editable setting' in message
               for message in seen['errors']), seen['errors']


def test_a_row_that_is_not_editable_offers_no_write(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.editSetting',
        'node': _setting(kind='fact', editable=False, key=''),
        'replies': {'semforge/setSetting': {'ok': True}},
    })
    assert not seen['inputs'] and not seen['requests']


def test_the_menu_gathers_what_there_is_no_menu_bar_for(tmp_path):
    """VS Code has no contribution point for a menu beside File and Edit.

    So the status bar item is the one place everything hangs off, and it has to
    hold more than the package switcher.
    """
    _bare_package(tmp_path, 'alpha')
    seen = _drive(tmp_path, {'command': 'semforge.menu'})
    offered = ' '.join(item['label'] for item in seen['quickPicks'][0]['items'])
    for wanted in ('Switch package', 'Project settings', 'New project',
                   'Doctor'):
        assert wanted in offered, offered
    assert 'alpha' in seen['quickPicks'][0]['placeHolder']


# --- a type comes from the knowledge, not from a text box --------------------

TYPES_REPLY = {
    'root': 'https://example.org/e/Entity',
    'types': [
        {'iri': 'https://example.org/e/Entity', 'term': 'e:Entity',
         'label': 'Entity', 'parent': '', 'shape': '', 'instances': 0,
         'isRoot': True},
        {'iri': 'https://example.org/e/Filter', 'term': 'e:Filter',
         'label': 'Filter', 'parent': 'e:Entity', 'shape': 's:FilterShape',
         'instances': 2, 'isRoot': False},
    ],
}

ENTITY_ROW = {'raw': {'kind': 'case', 'label': 'good', 'file': '/pkg/good.jsonld',
                      'children': []},
              'packageUri': 'file:///pkg/shacl.ttl'}


def test_the_type_is_chosen_from_the_knowledge(tmp_path):
    """A typed-in type is the quietest way to break a model.

    No shape targets an undeclared class, so every constraint stays silent and
    the entity reads as validated.
    """
    seen = _drive(tmp_path, {
        'command': 'semforge.addEntity', 'node': ENTITY_ROW,
        'pick': 'e:Filter', 'input': 'urn:filter:3',
        'replies': {'semforge/entityTypes': TYPES_REPLY,
                    'semforge/addEntity': {'ok': True, 'file': '/pkg/good.jsonld',
                                           'count': 2}},
    })
    offered = [item['label'] for item in seen['quickPicks'][0]['items']]
    assert 'e:Filter' in offered and 'e:Entity' in offered
    # What each type means, where it sits, and whether anything judges it.
    filter_row = next(i for i in seen['quickPicks'][0]['items']
                      if i['label'] == 'e:Filter')
    assert 'FilterShape' in filter_row['description']
    assert 'under e:Entity' in filter_row['detail']

    # Exactly one text box, and it is the id -- the type is never typed.
    assert len(seen['inputs']) == 1
    assert 'id' in seen['inputs'][0]['prompt']
    wrote = [r for r in seen['requests'] if r['method'] == 'semforge/addEntity']
    assert wrote[0]['params']['entityType'] == 'e:Filter'


def test_the_suggested_id_follows_the_type(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addEntity', 'node': ENTITY_ROW,
        'pick': 'e:Filter',
        'replies': {'semforge/entityTypes': TYPES_REPLY},
    })
    assert seen['inputs'][0]['value'] == 'urn:filter:3'


def test_a_missing_type_is_declared_in_the_knowledge_first(tmp_path):
    """The way out is to add the class, not to type a name into the data."""
    seen = _drive(tmp_path, {
        'command': 'semforge.addEntity', 'node': ENTITY_ROW,
        # the last row of the type list, then its parent
        'picks': [2, 'e:Filter'],
        'inputs': ['Waterjetcutter', 'urn:waterjetcutter:1'],
        'replies': {
            'semforge/entityTypes': TYPES_REPLY,
            'semforge/addEntityType': {
                'ok': True, 'term': 'e:Waterjetcutter', 'label': 'Waterjetcutter',
                'file': '/pkg/knowledge.ttl', 'line': 42},
            'semforge/addEntity': {'ok': True, 'file': '/pkg/good.jsonld',
                                   'count': 2}},
    })
    declared = [r for r in seen['requests']
                if r['method'] == 'semforge/addEntityType']
    assert declared, seen['requests']
    assert declared[0]['params'] == {'uri': 'file:///pkg/shacl.ttl',
                                     'name': 'Waterjetcutter',
                                     'parent': 'e:Filter'}
    # The new class is shown: one added out of sight is one nobody reviews.
    assert seen['shown'][0]['file'] == '/pkg/knowledge.ttl'
    used = [r for r in seen['requests'] if r['method'] == 'semforge/addEntity']
    assert used[0]['params']['entityType'] == 'e:Waterjetcutter'


def test_no_entity_hierarchy_is_reported_rather_than_guessed(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addEntity', 'node': ENTITY_ROW,
        'replies': {'semforge/entityTypes': {
            'types': [], 'error': 'this package has no entity hierarchy'}},
    })
    assert any('entity hierarchy' in message for message in seen['errors'])
    assert not seen['inputs'], 'it fell back to typing a type'


# --- an attribute comes from the knowledge too --------------------------------

ATTRIBUTES_REPLY = {
    'attributes': [
        {'iri': 'https://example.org/e/hasState', 'term': 'e:hasState',
         'label': 'hasState', 'kind': 'Property', 'domain': 'e:Machine',
         'comment': 'the state it reports', 'constrained': True,
         'definedAt': '/pkg/knowledge.ttl:12', 'scoped': True},
        {'iri': 'https://example.org/e/hasTrust', 'term': 'e:hasTrust',
         'label': 'hasTrust', 'kind': 'Property', 'domain': '',
         'comment': '', 'constrained': False,
         'definedAt': '/pkg/knowledge.ttl:20', 'scoped': False},
    ],
}

ENTITY_NODE = {'raw': {'kind': 'entity', 'entity': 'urn:filter:1',
                       'entityType': 'e:Filter', 'file': '/pkg/good.jsonld',
                       'children': []},
               'packageUri': 'file:///pkg/shacl.ttl'}


def test_the_attribute_is_chosen_from_the_knowledge(tmp_path):
    """An attribute typed by hand is invisible, not wrong: no sh:path selects it."""
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttribute', 'node': ENTITY_NODE,
        'picks': ['e:hasState', 'Default instance'], 'input': '"ON"',
        'replies': {'semforge/attributes': ATTRIBUTES_REPLY,
                    'semforge/addAttribute': {'ok': True, 'kind': 'Property'}},
    })
    asked = [r for r in seen['requests'] if r['method'] == 'semforge/attributes']
    assert asked[0]['params']['entityType'] == 'e:Filter'

    offered = {i['label']: i for i in seen['quickPicks'][0]['items']}
    assert 'e:hasState' in offered
    assert 'Property' in offered['e:hasState']['description']
    assert 'carried by e:Machine' in offered['e:hasState']['detail']
    # One with no domain is offered, and says so rather than claiming a carrier.
    assert 'no domain declared' in offered['e:hasTrust']['detail']

    # Its datasetId is picked (the default instance); only the value is typed.
    assert [i['label'] for i in seen['quickPicks'][1]['items']][0] == 'Default instance'
    assert len(seen['inputs']) == 1
    wrote = [r for r in seen['requests'] if r['method'] == 'semforge/addAttribute']
    assert wrote[0]['params']['name'] == 'e:hasState'
    assert wrote[0]['params']['kind'] == 'Property'
    assert wrote[0]['params']['datasetId'] is None


def test_a_relationship_says_it_wants_an_entity(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttribute', 'node': ENTITY_NODE,
        'picks': ['e:hasState', 'Default instance'],
        'replies': {'semforge/attributes': {'attributes': [
            dict(ATTRIBUTES_REPLY['attributes'][0], kind='Relationship')]}},
    })
    assert 'entity' in seen['inputs'][0]['prompt']


def test_a_missing_attribute_is_declared_in_the_knowledge_first(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttribute', 'node': ENTITY_NODE,
        'picks': [2, 'Property', 'Default instance'],
        'inputs': ['hasPressure', 'bar at the inlet', '1.0'],
        'replies': {
            'semforge/attributes': ATTRIBUTES_REPLY,
            'semforge/addAttributeTerm': {
                'ok': True, 'term': 'e:hasPressure', 'label': 'hasPressure',
                'kind': 'Property', 'domain': 'e:Filter',
                'file': '/pkg/knowledge.ttl', 'line': 42},
            'semforge/addAttribute': {'ok': True, 'kind': 'Property'}},
    })
    declared = [r for r in seen['requests']
                if r['method'] == 'semforge/addAttributeTerm']
    assert declared, seen['requests']
    assert declared[0]['params'] == {
        'uri': 'file:///pkg/shacl.ttl', 'name': 'hasPressure',
        'kind': 'Property', 'domain': 'e:Filter', 'label': 'bar at the inlet',
        # No namespace asked (this canned server offers none): the server's
        # default, the carrying type's namespace.
        'namespace': None}
    assert seen['shown'][0]['file'] == '/pkg/knowledge.ttl'
    used = [r for r in seen['requests'] if r['method'] == 'semforge/addAttribute']
    assert used[0]['params']['name'] == 'e:hasPressure'


def test_the_kind_is_asked_because_it_decides_the_encoding(tmp_path):
    """Property carries `value`, Relationship carries `object`."""
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttribute', 'node': ENTITY_NODE,
        'picks': [2, 'Relationship'], 'inputs': ['hasFilter', ''],
        'replies': {'semforge/attributes': ATTRIBUTES_REPLY,
                    'semforge/addAttributeTerm': {'ok': False, 'error': 'no'}},
    })
    kinds = [i['label'] for i in seen['quickPicks'][1]['items']]
    assert kinds == ['Property', 'Relationship']


def test_a_sub_attribute_says_what_it_hangs_off(tmp_path):
    """Not "carried by anything": it belongs inside one attribute."""
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttribute', 'node': ENTITY_NODE,
        'replies': {'semforge/attributes': {'attributes': [
            {'iri': 'https://example.org/e/hasTrust', 'term': 'e:hasTrust',
             'label': 'hasTrust', 'kind': 'Property',
             'domain': 'ngsild:Relationship', 'carrierKind': 'Relationship',
             'parents': ['e:hasFilter'], 'comment': 'how far it is trusted',
             'constrained': True, 'definedAt': '', 'scoped': False}]}},
    })
    row = seen['quickPicks'][0]['items'][0]
    assert 'a sub-attribute of e:hasFilter' in row['detail']
    assert 'carried by anything' not in row['detail']


def test_an_unplaced_sub_attribute_says_which_kind_carries_it(tmp_path):
    """Declared but not yet nested in a shape: still a sub-attribute.

    `rdfs:domain ngsild:Relationship` says so on its own, which is why it is
    not mistaken for an attribute nobody gave a domain.
    """
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttribute', 'node': ENTITY_NODE,
        'replies': {'semforge/attributes': {'attributes': [
            {'iri': 'https://example.org/e/hasConfidence',
             'term': 'e:hasConfidence', 'label': 'hasConfidence',
             'kind': 'Property', 'domain': 'ngsild:Relationship',
             'carrierKind': 'Relationship', 'parents': [], 'comment': '',
             'constrained': False, 'definedAt': '', 'scoped': False}]}},
    })
    detail = seen['quickPicks'][0]['items'][0]['detail']
    assert 'carried by any Relationship' in detail
    assert 'not placed in a shape yet' in detail


def test_adding_an_attribute_offers_the_values_its_shape_allows(tmp_path):
    """The case where a text box is worst: a new entity, an inherited attribute.

    Adding used to ask for the value with a bare input box while editing an
    existing one offered the shape's individuals -- so the one flow where you
    are least likely to know the vocabulary was the one with no help.
    """
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttribute', 'node': ENTITY_NODE,
        'picks': ['e:hasState', 'Default instance', 'state_ON'],
        'replies': {
            'semforge/attributes': ATTRIBUTES_REPLY,
            'semforge/valueChoices': {'choices': [
                {'label': 'state_ON', 'value': {'@id': 'base:state_ON'},
                 'detail': 'base:MachineState'},
                {'label': 'state_OFF', 'value': {'@id': 'base:state_OFF'},
                 'detail': 'base:MachineState'}]},
            'semforge/addAttribute': {'ok': True, 'kind': 'Property'}},
    })
    asked = [r for r in seen['requests']
             if r['method'] == 'semforge/valueChoices']
    assert asked, seen['requests']
    # The ENTITY's type, so an inherited shape is found by walking its
    # ancestors -- that is what makes hasState offerable on a new subtype.
    assert asked[0]['params']['entityType'] == 'e:Filter'
    assert asked[0]['params']['attribute'] == 'e:hasState'

    offered = [item['label'] for item in seen['quickPicks'][2]['items']]
    assert 'state_ON' in offered and 'state_OFF' in offered
    assert '$(edit) Type a value' in offered      # a way out is always there

    wrote = [r for r in seen['requests'] if r['method'] == 'semforge/addAttribute']
    assert wrote[0]['params']['value'] == {'@id': 'base:state_ON'}


def test_an_unconstrained_value_is_still_typed(tmp_path):
    """No sh:class means no list; a text box is the right answer then."""
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttribute', 'node': ENTITY_NODE,
        'picks': ['e:hasState', 'Default instance'], 'input': '21.5',
        'replies': {'semforge/attributes': ATTRIBUTES_REPLY,
                    'semforge/valueChoices': {'choices': []},
                    'semforge/addAttribute': {'ok': True, 'kind': 'Property'}},
    })
    assert len(seen['quickPicks']) == 2          # the attribute and its datasetId; no value list
    assert seen['inputs'], 'nothing asked for the value'
    wrote = [r for r in seen['requests'] if r['method'] == 'semforge/addAttribute']
    assert wrote[0]['params']['value'] == '21.5'


def test_a_prefix_can_be_defined_from_the_project_view(tmp_path):
    """There was no way to add to the namespace table from the editor at all.

    You found semforge.yaml and typed -- and the table is package-wide, so
    getting it wrong there is wrong everywhere.
    """
    seen = _drive(tmp_path, {
        'command': 'semforge.addNamespace',
        'node': {'raw': {'kind': 'namespaces', 'label': 'namespaces'},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'inputs': ['plant', 'https://example.org/plant/'],
        'replies': {'semforge/addNamespace': {
            'ok': True, 'prefix': 'plant',
            'namespace': 'https://example.org/plant/',
            'file': '/pkg/semforge.yaml', 'line': 29}},
    })
    asked = [r for r in seen['requests'] if r['method'] == 'semforge/addNamespace']
    assert asked[0]['params'] == {'uri': 'file:///pkg/shacl.ttl',
                                  'prefix': 'plant',
                                  'namespace': 'https://example.org/plant/'}
    assert seen['shown'][0]['file'] == '/pkg/semforge.yaml'


def test_a_refused_prefix_is_reported(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addNamespace',
        'node': {'raw': {'kind': 'namespaces'}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'inputs': ['ngsild', 'https://example.org/x/'],
        'replies': {'semforge/addNamespace': {
            'ok': False, 'error': 'ngsild: already means <...>'}},
    })
    assert any('already means' in message for message in seen['errors'])


def test_an_unused_namespace_is_removed_without_asking(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.removeNamespace',
        'node': {'raw': {'kind': 'namespaceEntry', 'label': 'plant'},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/removeNamespace': {
            'ok': True, 'prefix': 'plant', 'survivesAs': '',
            'file': '/pkg/semforge.yaml', 'line': 12}},
    })
    asked = [r for r in seen['requests']
             if r['method'] == 'semforge/removeNamespace']
    assert asked[0]['params'] == {'uri': 'file:///pkg/shacl.ttl',
                                  'prefix': 'plant', 'force': False}
    assert not seen['warnings'], 'it asked about a name nothing uses'
    assert any('plant' in message for message in seen['messages'])


def test_a_namespace_in_use_is_not_removed_without_being_asked_about(tmp_path):
    """Even when removal is safe. The first ask comes back as a question."""
    seen = _drive(tmp_path, {
        'command': 'semforge.removeNamespace',
        'node': {'raw': {'kind': 'namespaceEntry', 'label': 'ngsild'},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'answer': None,                    # the dialog is dismissed
        'replies': {'semforge/removeNamespace': {
            'ok': False, 'confirm': True, 'prefix': 'ngsild',
            'detail': 'ngsild: is in use -- bound in shacl.ttl and names 121 '
                      'term(s). Removing this line is safe anyway.'}},
    })
    assert any('in use' in message for message in seen['warnings'])
    asked = [r for r in seen['requests']
             if r['method'] == 'semforge/removeNamespace']
    # Asked once, not forced, and nothing followed the dismissal.
    assert [r['params']['force'] for r in asked] == [False]


def test_confirming_removes_it(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.removeNamespace',
        'node': {'raw': {'kind': 'namespaceEntry', 'label': 'ngsild'},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'answer': 'Remove',
        # Asked, then asked again with force -- two answers, in order.
        'replies': {'semforge/removeNamespace': [
            {'ok': False, 'confirm': True, 'prefix': 'ngsild',
             'detail': 'ngsild: is in use -- bound in shacl.ttl.'},
            {'ok': True, 'prefix': 'ngsild', 'survivesVia': 'the standard set',
             'file': '/pkg/semforge.yaml', 'line': 12}]},
    })
    asked = [r for r in seen['requests']
             if r['method'] == 'semforge/removeNamespace']
    assert [r['params']['force'] for r in asked] == [False, True]
    assert any('still names it' in message for message in seen['messages'])


def test_removing_a_name_in_use_warns_rather_than_failing_silently(tmp_path):
    """"It is in use" is an answer, not an error: the row is still there."""
    seen = _drive(tmp_path, {
        'command': 'semforge.removeNamespace',
        'node': {'raw': {'kind': 'namespaceEntry', 'label': 'iffBaseShacl'},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/removeNamespace': {
            'ok': False,
            'error': 'iffBaseShacl: cannot be removed -- it is in use. '
                     '<...> is bound in shacl.ttl and names 42 term(s)'}},
    })
    assert any('cannot be removed' in message and 'in use' in message
               for message in seen['warnings']), seen['warnings']
    assert not seen['errors']


# --- deleting a project ------------------------------------------------------

PLAN_REPLY = {
    'ok': True, 'name': 'test', 'path': '/pkg/test', 'files': 10,
    'bytes': 8192, 'strangers': ['notes.md'], 'nested': [],
    'inGit': True, 'tracked': 0, 'untracked': 10,
    'warnings': ['1 item(s) here are not part of the package: notes.md.',
                 'Nothing here is tracked by git, so nothing can bring it back.'],
}


def test_deleting_asks_twice_and_says_what_goes(tmp_path):
    """The one gesture no other gesture undoes, so it says the most."""
    seen = _drive(tmp_path, {
        'command': 'semforge.deleteProject',
        'node': {'packageUri': 'file:///pkg/test/shacl.ttl'},
        'answer': 'Move to Trash', 'input': 'test',
        'replies': {'semforge/deletionPlan': PLAN_REPLY},
    })
    shown = ' '.join(seen['warnings'])
    assert 'Delete the project "test"?' in shown
    assert '10 file(s)' in shown
    assert 'nothing can bring it back' in shown, shown
    assert 'not part of the package' in shown

    # The second ask is typing the folder name.
    assert 'Type test' in seen['inputs'][0]['prompt']
    assert seen['deleted'] == [{'path': '/pkg/test',
                                'options': {'recursive': True,
                                            'useTrash': True}}]


def test_dismissing_the_dialog_deletes_nothing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.deleteProject',
        'node': {'packageUri': 'file:///pkg/test/shacl.ttl'},
        'replies': {'semforge/deletionPlan': PLAN_REPLY},
    })
    assert not seen['deleted']
    assert not seen['inputs'], 'it asked for the name before the confirmation'


def test_typing_the_wrong_name_deletes_nothing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.deleteProject',
        'node': {'packageUri': 'file:///pkg/test/shacl.ttl'},
        'answer': 'Move to Trash', 'input': 'something else',
        'replies': {'semforge/deletionPlan': PLAN_REPLY},
    })
    assert not seen['deleted']


def test_a_directory_that_is_not_a_package_is_refused(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.deleteProject',
        'node': {'packageUri': 'file:///elsewhere/x.ttl'},
        'answer': 'Move to Trash', 'input': 'elsewhere',
        'replies': {'semforge/deletionPlan': {
            'ok': False, 'error': '/elsewhere is not a SemForge package'}},
    })
    assert not seen['deleted']
    assert any('not a SemForge package' in message for message in seen['errors'])


def test_the_project_row_carries_the_delete_action(tmp_path):
    """Buried in a submenu behind a "new folder" icon, it was a button nobody
    could find. It belongs on the row that names the project."""
    import json as _json

    from semforge.cooked.project import build_project
    from semforge.editor.server import _serialise_project
    from semforge.package import load

    corpus = os.path.join(SDK, 'tests', 'corpus', 'kms')
    roots = [_serialise_project(node) for node in build_project(load(corpus))]
    seen = _drive(tmp_path, {
        'mode': 'items', 'provider': 'ProjectTreeProvider',
        'uri': 'file:///pkg/shacl.ttl',
        'replies': {'semforge/project': {'roots': roots}},
    }, target='project.js')

    # The health summary comes first; the project row right after it.
    first = next(r for r in seen['rows'] if r['kind'] != 'health')
    assert first['label'] == 'Project'
    assert first['contextValue'] == 'project'

    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        menus = _json.load(handle)['contributes']['menus']['view/item/context']
    assert any(entry['command'] == 'semforge.deleteProject'
               and 'viewItem == project' in entry['when']
               and entry['group'] == 'inline'
               for entry in menus), menus


def test_after_deleting_the_views_stop_showing_it(tmp_path):
    """"The project I am in is still shown."

    The session could only be SET, never cleared, and a provider's refresh
    ignored a falsy uri -- so a deleted package went on being displayed by all
    four views and named in the status bar.
    """
    _bare_package(tmp_path, 'alpha')
    _bare_package(tmp_path, 'beta')
    seen = _drive(tmp_path, {
        'command': 'semforge.deleteProject',
        'node': {'packageUri': f'file://{tmp_path}/alpha/shacl.ttl'},
        'answer': 'Move to Trash', 'input': 'alpha',
        'replies': {'semforge/deletionPlan': {
            'ok': True, 'name': 'alpha', 'path': f'{tmp_path}/alpha',
            'files': 3, 'bytes': 100, 'strangers': [], 'nested': [],
            'inGit': False, 'tracked': 0, 'untracked': 3,
            'warnings': ['not in a git repository']}},
    })
    assert seen['deleted'], 'nothing was deleted'
    assert not (tmp_path / 'alpha').exists()

    # It moved to the one that is left, rather than staying on the one that
    # is gone.
    assert 'beta' in seen['statusBar'][-1], seen['statusBar']
    assert 'alpha' not in seen['statusBar'][-1]
    for view, state in seen['views'].items():
        assert 'alpha' not in (state.get('description') or ''), view


def test_deleting_the_only_package_leaves_no_package(tmp_path):
    _bare_package(tmp_path, 'only')
    seen = _drive(tmp_path, {
        'command': 'semforge.deleteProject',
        'node': {'packageUri': f'file://{tmp_path}/only/shacl.ttl'},
        'answer': 'Move to Trash', 'input': 'only',
        'replies': {'semforge/deletionPlan': {
            'ok': True, 'name': 'only', 'path': f'{tmp_path}/only',
            'files': 3, 'bytes': 100, 'strangers': [], 'nested': [],
            'inGit': False, 'tracked': 0, 'untracked': 3, 'warnings': []}},
    })
    assert not (tmp_path / 'only').exists()
    assert 'no package' in seen['statusBar'][-1], seen['statusBar']


def test_deleting_another_package_leaves_the_current_one_alone(tmp_path):
    """Only the package you are on is let go of."""
    _bare_package(tmp_path, 'alpha')
    _bare_package(tmp_path, 'beta')
    seen = _drive(tmp_path, {
        'command': 'semforge.deleteProject',
        'node': {'packageUri': f'file://{tmp_path}/beta/shacl.ttl'},
        'answer': 'Move to Trash', 'input': 'beta',
        'replies': {'semforge/deletionPlan': {
            'ok': True, 'name': 'beta', 'path': f'{tmp_path}/beta',
            'files': 3, 'bytes': 100, 'strangers': [], 'nested': [],
            'inGit': False, 'tracked': 0, 'untracked': 3, 'warnings': []}},
    })
    assert not (tmp_path / 'beta').exists()
    assert 'alpha' in seen['statusBar'][-1], seen['statusBar']


# --- adding an attribute to a shape ------------------------------------------

def _shape_row(**overrides):
    raw = {'kind': 'shape', 'label': 'iffBaseShacl:CartridgeShape',
           'shape': 'http://example.com/CartridgeShape', 'path': [],
           'parameter': '', 'value': '', 'editable': False,
           'inheritedFrom': '', 'children': []}
    raw.update(overrides)
    return {'raw': raw, 'packageUri': 'file:///pkg/shacl.ttl'}


ATTRIBUTE_OPTIONS = {'options': [
    {'iri': 'http://example.com/hasWasteclass',
     'term': 'iffFilterEntities:hasWasteclass', 'label': 'hasWasteclass',
     'kind': 'Property', 'comment': '', 'domain': 'iffBaseEntities:FilterCartridge',
     'scoped': True, 'status': 'free', 'by': ''},
    {'iri': 'http://example.com/isUsedFrom', 'term': 'iffFilterEntities:isUsedFrom',
     'label': 'isUsedFrom', 'kind': 'Property', 'comment': '', 'domain': '',
     'scoped': True, 'status': 'here', 'by': ''},
]}


def test_adding_an_attribute_asks_presence_and_value_then_writes(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttributeConstraint', 'node': _shape_row(),
        'picks': ['hasWasteclass', 'Required', 'Wasteclass'],
        'replies': {
            'semforge/attributeOptions': ATTRIBUTE_OPTIONS,
            # Asked twice for a Property: the datatypes, then the classes.
            'semforge/choices': [
                {'choices': [{'value': 'xsd:string', 'label': 'xsd:string',
                              'detail': ''}]},
                {'choices': [{'value': 'iffFilterKnowledge:Wasteclass',
                              'label': 'Wasteclass', 'detail': 'vocabulary class'}]}],
            'semforge/addAttributeConstraint': {
                'ok': True, 'file': '/pkg/shacl.ttl', 'line': 45},
        },
    })
    assert seen['errors'] == []
    first = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert 'isUsedFrom' in first, 'a constrained attribute must still be listed'
    written = [r for r in seen['requests']
               if r['method'] == 'semforge/addAttributeConstraint']
    assert len(written) == 1
    params = written[0]['params']
    assert params['attribute'] == 'http://example.com/hasWasteclass'
    assert params['shape'] == 'http://example.com/CartridgeShape'
    assert params['required'] is True
    assert params['valueClass'] == 'iffFilterKnowledge:Wasteclass'
    assert params['datatype'] is None
    assert seen['shown'], 'the new constraint was not opened'


def test_picking_an_attribute_already_constrained_explains_and_writes_nothing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttributeConstraint', 'node': _shape_row(),
        'picks': ['isUsedFrom'],
        'replies': {'semforge/attributeOptions': ATTRIBUTE_OPTIONS},
    })
    assert any('already constrained' in m for m in seen['info'])
    assert not [r for r in seen['requests']
                if r['method'] == 'semforge/addAttributeConstraint']


SHARED_OPTIONS = {'targets': ['iffBaseEntities:FilterCartridge'], 'options': [
    dict(ATTRIBUTE_OPTIONS['options'][0]),
    {'iri': 'http://example.com/hasPressure', 'term': 'iffBaseEntities:hasPressure',
     'label': 'hasPressure', 'kind': 'Property', 'comment': '',
     'domain': 'iffBaseEntities:Machine', 'scoped': True, 'status': 'elsewhere',
     'by': 'Machine'},
]}


def _share(tmp_path, answer):
    return _drive(tmp_path, {
        'command': 'semforge.addAttributeConstraint', 'node': _shape_row(),
        'picks': ['hasPressure', 'Optional', 'xsd:double'], 'answer': answer,
        'replies': {
            'semforge/attributeOptions': SHARED_OPTIONS,
            'semforge/choices': [
                {'choices': [{'value': 'xsd:double', 'label': 'xsd:double', 'detail': ''}]},
                {'choices': []}],
            'semforge/addAttributeConstraint': {
                'ok': True, 'file': '/pkg/shacl.ttl', 'line': 45,
                'domainAdded': ['iffBaseEntities:FilterCartridge']}}})


def test_another_type_s_attribute_is_offered_in_its_own_section(tmp_path):
    seen = _share(tmp_path, None)
    items = seen['quickPicks'][0]['items']
    labels = [i['label'] for i in items]
    section = 'Declared for other types — adding one gives it to this type too'
    assert labels.index(section) < labels.index('hasPressure')
    detail = next(i['detail'] for i in items if i['label'] == 'hasPressure')
    assert detail == 'declared for Machine; adding it extends its domain to FilterCartridge too'


def test_giving_it_to_this_type_asks_first_and_says_the_union(tmp_path):
    seen = _share(tmp_path, None)
    said = seen['warnings'][0]
    assert said.startswith('Give hasPressure to FilterCartridge too?')
    assert '"Machine or FilterCartridge"' in said and 'owl:unionOf' in said
    assert not [r for r in seen['requests'] if r['method'] == 'semforge/addAttributeConstraint'], \
        'declined: nothing written'


def test_confirmed_it_is_added_with_the_domain_extended(tmp_path):
    seen = _share(tmp_path, 'Give it to this type too')
    written = [r['params'] for r in seen['requests']
               if r['method'] == 'semforge/addAttributeConstraint']
    assert len(written) == 1 and written[0]['extendDomain'] is True
    assert written[0]['attribute'] == 'http://example.com/hasPressure'
    assert any('its domain now includes iffBaseEntities:FilterCartridge' in m
               for m in seen['messages'])


def test_an_attribute_of_this_type_is_added_without_extending(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttributeConstraint', 'node': _shape_row(),
        'picks': ['hasWasteclass', 'Required', 'Wasteclass'],
        'replies': {
            'semforge/attributeOptions': ATTRIBUTE_OPTIONS,
            'semforge/choices': [
                {'choices': []},
                {'choices': [{'value': 'iffFilterKnowledge:Wasteclass',
                              'label': 'Wasteclass', 'detail': 'vocabulary class'}]}],
            'semforge/addAttributeConstraint': {'ok': True, 'file': '/pkg/shacl.ttl'}}})
    written = [r['params'] for r in seen['requests']
               if r['method'] == 'semforge/addAttributeConstraint']
    assert written[0]['extendDomain'] is False
    assert seen['warnings'] == [], 'nothing to ask'


def test_an_inherited_shape_takes_no_attribute(tmp_path):
    """Adding to an inherited shape would write into the SUPERTYPE's shape."""
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttributeConstraint',
        'node': _shape_row(inheritedFrom='http://example.com/MachineShape'),
        'replies': {'semforge/attributeOptions': ATTRIBUTE_OPTIONS},
    })
    assert seen['requests'] == []


def test_a_refused_add_reaches_the_user(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttributeConstraint', 'node': _shape_row(),
        'picks': ['hasWasteclass', 'Optional', 'Any value'],
        'replies': {
            'semforge/attributeOptions': ATTRIBUTE_OPTIONS,
            'semforge/choices': {'choices': []},
            'semforge/addAttributeConstraint': {
                'ok': False, 'error': 'the knowledge gives hasWasteclass to X'},
        },
    })
    assert any('gives hasWasteclass' in e for e in seen['errors'])


# --- "SemForge: New attribute…" ------------------------------------------------

ENTITY_TYPES = {'root': 'http://example.com/Entity', 'types': [
    {'iri': 'http://example.com/Filter', 'term': 'iffBaseEntities:Filter',
     'label': 'Filter', 'parent': 'iffBaseEntities:Machine',
     'shape': 'iffBaseShacl:FilterShape',
     'ownShape': 'http://example.com/FilterShape', 'instances': 2,
     'isRoot': False},
    {'iri': 'http://example.com/Lasercutter', 'term': 'iffBaseEntities:Lasercutter',
     'label': 'Lasercutter', 'parent': 'iffBaseEntities:Cutter',
     'shape': 'iffBaseShacl:CutterShape', 'ownShape': '', 'instances': 0,
     'isRoot': False}]}

DECLARED = {'ok': True, 'iri': 'http://example.com/hasPressure',
            'term': 'iffBaseEntities:hasPressure', 'label': 'hasPressure',
            'kind': 'Property', 'domain': 'iffBaseEntities:Filter',
            'file': '/pkg/knowledge.ttl', 'line': 80}


def _new_attribute(tmp_path, picks, inputs, extra=None):
    _package_at(str(tmp_path))
    replies = {'semforge/entityTypes': ENTITY_TYPES,
               'semforge/addAttributeTerm': DECLARED,
               'semforge/choices': {'choices': [
                   {'value': 'xsd:double', 'label': 'xsd:double', 'detail': ''}]},
               'semforge/addAttributeConstraint': {
                   'ok': True, 'file': '/pkg/shacl.ttl', 'line': 120}}
    replies.update(extra or {})
    return _drive(tmp_path, {'command': 'semforge.newAttribute',
                             'picks': picks, 'inputs': inputs,
                             'replies': replies})


def _sent(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


def test_new_attribute_declares_then_constrains_in_one_flow(tmp_path):
    seen = _new_attribute(
        tmp_path, picks=['Filter', 'Property', 'Required', 'xsd:double'],
        inputs=['hasPressure', 'bar, absolute'])
    assert seen['errors'] == [], seen['errors']
    declared = _sent(seen, 'semforge/addAttributeTerm')
    assert declared and declared[0]['domain'] == 'iffBaseEntities:Filter'
    assert declared[0]['name'] == 'hasPressure'
    assert declared[0]['kind'] == 'Property'
    constrained = _sent(seen, 'semforge/addAttributeConstraint')
    assert len(constrained) == 1
    # From a type rather than a tree row: the server picks the type's OWN shape.
    assert constrained[0]['entityType'] == 'iffBaseEntities:Filter'
    assert constrained[0]['shape'] is None
    assert constrained[0]['attribute'] == 'iffBaseEntities:hasPressure'
    assert constrained[0]['required'] is True
    assert constrained[0]['datatype'] == 'xsd:double'
    # Declared before constrained: the order the model needs.
    methods = [r['method'] for r in seen['requests']]
    assert methods.index('semforge/addAttributeTerm') < \
        methods.index('semforge/addAttributeConstraint')


NAMESPACES = {'namespaces': [
    {'prefix': 'iffBaseEntities', 'namespace': 'http://example.com/base/',
     'attributes': 17, 'default': True},
    {'prefix': 'iffFilterEntities', 'namespace': 'http://example.com/filter/',
     'attributes': 1, 'default': False}]}


def test_the_namespace_is_asked_and_shows_the_full_name(tmp_path):
    seen = _new_attribute(
        tmp_path, picks=['Filter', 'iffFilterEntities:hasPressure', 'Property',
                         'Not now'],
        inputs=['hasPressure', ''],
        extra={'semforge/attributeNamespaces': NAMESPACES})
    offered = [i['label'] for i in seen['quickPicks'][1]['items']]
    assert offered[1] == 'iffBaseEntities:hasPressure', 'the default comes first'
    assert 'iffFilterEntities:hasPressure' in offered
    declared = _sent(seen, 'semforge/addAttributeTerm')
    assert declared[0]['namespace'] == 'iffFilterEntities'


def test_the_default_namespace_is_sent_as_the_servers_default(tmp_path):
    seen = _new_attribute(
        tmp_path, picks=['Filter', 'iffBaseEntities:hasPressure', 'Property',
                         'Not now'],
        inputs=['hasPressure', ''],
        extra={'semforge/attributeNamespaces': NAMESPACES})
    assert _sent(seen, 'semforge/addAttributeTerm')[0]['namespace'] is None


def test_a_prefix_typed_into_the_name_is_not_asked_again(tmp_path):
    seen = _new_attribute(
        tmp_path, picks=['Filter', 'Property', 'Not now'],
        inputs=['iffFilterEntities:hasPressure', ''],
        extra={'semforge/attributeNamespaces': NAMESPACES})
    assert not _sent(seen, 'semforge/attributeNamespaces')
    assert _sent(seen, 'semforge/addAttributeTerm')[0]['name'] == \
        'iffFilterEntities:hasPressure'


def test_new_attribute_may_stop_at_the_declaration(tmp_path):
    seen = _new_attribute(tmp_path, picks=['Filter', 'Property', 'Not now'],
                          inputs=['hasPressure', ''])
    assert _sent(seen, 'semforge/addAttributeTerm')
    assert not _sent(seen, 'semforge/addAttributeConstraint')


def test_a_type_without_its_own_shape_is_declared_and_says_so(tmp_path):
    """Writing it into the INHERITED shape would demand it of every sibling."""
    seen = _new_attribute(tmp_path, picks=['Lasercutter', 'Property'],
                          inputs=['hasPower', ''])
    assert _sent(seen, 'semforge/addAttributeTerm')
    assert not _sent(seen, 'semforge/addAttributeConstraint')
    assert any('No shape targets Lasercutter' in m for m in seen['info'])


def test_new_attribute_without_a_package_says_so(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.newAttribute', 'replies': {}})
    assert seen['requests'] == []
    assert any('no package is open' in w for w in seen['warnings'])


def test_the_constraint_picker_can_declare_a_new_attribute(tmp_path):
    """From a shape's +: the type comes from the shape, the constraint goes
    into THAT shape, and there is no "Not now" -- the author asked for one."""
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttributeConstraint', 'node': _shape_row(),
        'picks': ['$(add) New attribute…', 'Property', 'Optional', 'Any value'],
        'inputs': ['hasLifetime', ''],
        'replies': {
            'semforge/attributeOptions': dict(
                ATTRIBUTE_OPTIONS, targets=['iffBaseEntities:FilterCartridge']),
            'semforge/addAttributeTerm': dict(DECLARED, term='iffBaseEntities:hasLifetime',
                                              label='hasLifetime'),
            'semforge/choices': {'choices': []},
            'semforge/addAttributeConstraint': {
                'ok': True, 'file': '/pkg/shacl.ttl', 'line': 40},
        },
    })
    assert seen['errors'] == [], seen['errors']
    declared = _sent(seen, 'semforge/addAttributeTerm')
    assert declared[0]['domain'] == 'iffBaseEntities:FilterCartridge'
    constrained = _sent(seen, 'semforge/addAttributeConstraint')
    assert constrained[0]['shape'] == 'http://example.com/CartridgeShape'
    assert constrained[0]['attribute'] == 'iffBaseEntities:hasLifetime'
    presence = [i['label'] for i in seen['quickPicks'][2]['items']]
    assert presence == ['Optional', 'Required']


# --- "SemForge: Delete attribute…" ---------------------------------------------

def _dependent(kind, where, detail, removable=True):
    return {'kind': kind, 'file': '/pkg/' + where.split(':')[0],
            'where': where, 'line': int(where.split(':')[1]),
            'detail': detail, 'removable': removable}


IN_USE_PLAN = {'ok': True, 'iri': 'http://example.com/hasWidth', 'label': 'hasWidth',
               'inUse': True, 'blocking': 0, 'dependents': [
                   _dependent('declaration', 'knowledge.ttl:75', 'the declaration of hasWidth'),
                   _dependent('constraint', 'shacl.ttl:296',
                              'iffBaseShacl:WorkpieceShape: the property shape on the entity'),
                   _dependent('data', 'model-instance.jsonld:252', 'urn:workpiece:1 carries it')]}

BLOCKED_PLAN = dict(IN_USE_PLAN, label='hasStrength', blocking=1, dependents=[
    _dependent('declaration', 'knowledge.ttl:69', 'the declaration of hasStrength'),
    _dependent('sparql', 'shacl.ttl:142',
               'iffBaseShacl:FilterStrengthShape: a SPARQL body reads it', False)])

UNUSED_PLAN = dict(IN_USE_PLAN, label='hasNothing', inUse=False, dependents=[
    _dependent('declaration', 'knowledge.ttl:90', 'the declaration of hasNothing')])


def _knowledge_row():
    return {'raw': {'kind': 'attribute', 'label': 'hasWidth',
                    'iri': 'http://example.com/hasWidth', 'children': []},
            'packageUri': 'file:///pkg/shacl.ttl'}


def _delete(tmp_path, plan, answer=None, node=None, picks=None):
    return _drive(tmp_path, {
        'command': 'semforge.deleteAttribute', 'node': node or _knowledge_row(),
        'answer': answer, 'picks': picks,
        'replies': {'semforge/attributeRemovalPlan': plan,
                    'semforge/attributes': {'attributes': [
                        {'iri': 'http://example.com/hasWidth', 'term': 'iffBaseEntities:hasWidth',
                         'kind': 'Property', 'domain': 'iffBaseEntities:Workpiece',
                         'comment': ''}]},
                    'semforge/removeAttribute': dict(plan, notes=[])}})


def test_deleting_an_attribute_in_use_lists_every_dependent_first(tmp_path):
    seen = _delete(tmp_path, IN_USE_PLAN, answer='Delete with 2 dependent(s)')
    warning = seen['warnings'][0]
    assert 'hasWidth is in use' in warning
    for where in ('shacl.ttl:296', 'model-instance.jsonld:252', 'knowledge.ttl:75'):
        assert where in warning, f'{where} not shown before deleting'
    sent = _sent(seen, 'semforge/removeAttribute')
    assert sent == [{'uri': 'file:///pkg/shacl.ttl',
                     'attribute': 'http://example.com/hasWidth', 'force': True,
                     'declarationOnly': False}]


def test_declining_deletes_nothing(tmp_path):
    seen = _delete(tmp_path, IN_USE_PLAN, answer=None)
    assert not _sent(seen, 'semforge/removeAttribute')


def test_a_blocked_attribute_is_not_deleted_and_says_where(tmp_path):
    seen = _delete(tmp_path, BLOCKED_PLAN, answer='Open the first one')
    assert 'cannot be deleted with its dependents' in seen['warnings'][0]
    assert 'FilterStrengthShape' in seen['warnings'][0]
    assert not _sent(seen, 'semforge/removeAttribute')
    assert seen['shown'] and seen['shown'][0]['file'] == '/pkg/shacl.ttl'


def test_an_unused_attribute_gets_a_plain_confirmation(tmp_path):
    seen = _delete(tmp_path, UNUSED_PLAN, answer='Delete')
    assert 'used nowhere' in seen['warnings'][0]
    assert _sent(seen, 'semforge/removeAttribute')


def test_from_the_palette_the_attribute_is_picked_first(tmp_path):
    _package_at(str(tmp_path))
    seen = _drive(tmp_path, {
        'command': 'semforge.deleteAttribute', 'node': None,
        'picks': ['iffBaseEntities:hasWidth'], 'answer': None,
        'replies': {'semforge/attributes': {'attributes': [
            {'iri': 'http://example.com/hasWidth', 'term': 'iffBaseEntities:hasWidth',
             'kind': 'Property', 'domain': 'iffBaseEntities:Workpiece', 'comment': ''}]},
            'semforge/attributeRemovalPlan': IN_USE_PLAN}})
    asked = _sent(seen, 'semforge/attributeRemovalPlan')
    assert asked and asked[0]['attribute'] == 'http://example.com/hasWidth'


def test_a_constraint_row_is_deleted_by_its_path(tmp_path):
    node = {'raw': {'kind': 'attribute', 'label': 'hasTrust',
                    'shape': 'http://example.com/CutterShape',
                    'path': ['iffBaseEntities:hasFilter', 'iffBaseEntities:hasTrust'],
                    'children': []},
            'packageUri': 'file:///pkg/shacl.ttl'}
    seen = _delete(tmp_path, IN_USE_PLAN, node=node)
    asked = _sent(seen, 'semforge/attributeRemovalPlan')
    assert asked[0]['attribute'] == 'iffBaseEntities:hasTrust'


def test_the_declaration_alone_can_be_deleted_and_the_uses_stay(tmp_path):
    seen = _delete(tmp_path, IN_USE_PLAN, answer='Delete declaration only')
    sent = _sent(seen, 'semforge/removeAttribute')
    assert sent and sent[0]['declarationOnly'] is True and sent[0]['force'] is True


def test_a_blocked_attribute_can_still_lose_its_declaration(tmp_path):
    """The SPARQL that blocks the full delete is not touched by this one."""
    seen = _delete(tmp_path, BLOCKED_PLAN, answer='Delete declaration only')
    assert 'declaration alone' in seen['warnings'][0]
    sent = _sent(seen, 'semforge/removeAttribute')
    assert sent and sent[0]['declarationOnly'] is True


def test_an_unused_attribute_is_not_offered_the_declaration_only_choice(tmp_path):
    seen = _delete(tmp_path, UNUSED_PLAN, answer='Delete declaration only')
    assert not _sent(seen, 'semforge/removeAttribute'), \
        'there are no uses to leave behind, so the choice must not exist'


# --- the sanity quick fixes ------------------------------------------------------

def test_declare_it_takes_the_name_from_the_use_and_asks_only_the_rest(tmp_path):
    _package_at(str(tmp_path))
    seen = _drive(tmp_path, {
        'command': 'semforge.newAttribute',
        'node': {'packageUri': 'file:///pkg/shacl.ttl',
                 'iri': 'https://example.org/entities/hasWidth'},
        'picks': ['Filter', 'Property', 'Not now'], 'inputs': [''],
        'replies': {'semforge/entityTypes': ENTITY_TYPES,
                    'semforge/attributeNamespaces': NAMESPACES,
                    'semforge/addAttributeTerm': DECLARED}})
    declared = _sent(seen, 'semforge/addAttributeTerm')
    assert declared, seen['errors']
    assert declared[0]['name'] == 'hasWidth'
    assert declared[0]['namespace'] == 'https://example.org/entities/'
    assert [i['title'] for i in seen['inputs']] != ['New attribute'], \
        'the name was asked again'
    assert not _sent(seen, 'semforge/attributeNamespaces')


def test_declare_it_keeps_a_prefixed_term_whole(tmp_path):
    _package_at(str(tmp_path))
    seen = _drive(tmp_path, {
        'command': 'semforge.newAttribute',
        'node': {'packageUri': 'file:///pkg/shacl.ttl',
                 'iri': 'iffBaseEntities:hasWidth'},
        'picks': ['Filter', 'Property', 'Not now'], 'inputs': [''],
        'replies': {'semforge/entityTypes': ENTITY_TYPES,
                    'semforge/attributeNamespaces': NAMESPACES,
                    'semforge/addAttributeTerm': DECLARED}})
    declared = _sent(seen, 'semforge/addAttributeTerm')
    assert declared[0]['name'] == 'iffBaseEntities:hasWidth'


def test_remove_this_use_sends_the_marked_place_and_shows_the_note(tmp_path):
    fix = {'uri': 'file:///pkg/x.yaml', 'kind': 'assert', 'file': '/pkg/x.yaml',
           'case': 'too-high.jsonld', 'index': 0, 'label': 'S/a/C'}
    seen = _drive(tmp_path, {
        'command': 'semforge.removeUse', 'node': fix,
        'replies': {'semforge/removeUse': {
            'ok': True, 'file': '/pkg/x.yaml',
            'note': 'too-high.jsonld expects a violation but no longer asserts one'}}})
    assert _sent(seen, 'semforge/removeUse') == [fix]
    assert any('no longer asserts' in w for w in seen['warnings'])


def test_a_refused_removal_reaches_the_user(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.removeUse',
        'node': {'uri': 'file:///pkg/x', 'kind': 'key', 'label': 'hasWidth'},
        'replies': {'semforge/removeUse': {'ok': False,
                                           'error': 'the file has changed'}}})
    assert any('has changed' in e for e in seen['errors'])


def test_remove_this_use_is_not_in_the_palette():
    """It only means something with the finding it was offered on."""
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        menus = json.load(handle)['contributes']['menus']
    hidden = {e['command'] for e in menus['commandPalette'] if e['when'] == 'false'}
    # Open source likewise: it opens the row it was invoked on. Removing a
    # SPARQL query needs the shape and the query it was offered on; a rename,
    # the shape, case or suite it was offered on.
    assert hidden == {'semforge.removeUse', 'semforge.openSource', 'semforge.newAttributeTest',
                      'semforge.mergeShape', 'semforge.removeSparqlQuery',
                      'semforge.nestForFlink', 'semforge.renameShape',
                      'semforge.renameTestCase', 'semforge.renameSuite',
                      'semforge.deleteShape', 'semforge.cloneTestCase',
                      'semforge.deleteTestCase', 'semforge.deleteSuite',
                      'semforge.removeCaseValue', 'semforge.linkSeverityClass'}


# --- sub-attributes ---------------------------------------------------------------

def _constraint_attribute_row():
    return {'raw': {'kind': 'attribute', 'label': 'iffBaseEntities:hasFilter',
                    'shape': 'http://example.com/CutterShape',
                    'path': ['iffBaseEntities:hasFilter'], 'parameter': '',
                    'value': '', 'editable': False, 'inheritedFrom': '',
                    'children': []},
            'packageUri': 'file:///pkg/shacl.ttl'}


SUB_OPTIONS = {'targets': ['iffBaseEntities:hasFilter'],
               'carrier': 'iffBaseEntities:hasFilter', 'options': [
                   {'iri': 'http://example.com/hasConfidence',
                    'term': 'iffBaseEntities:hasConfidence', 'label': 'hasConfidence',
                    'kind': 'Property', 'comment': '', 'domain': 'ngsild:Relationship',
                    'scoped': False, 'status': 'free', 'by': ''},
                   {'iri': 'http://example.com/hasTrust',
                    'term': 'iffBaseEntities:hasTrust', 'label': 'hasTrust',
                    'kind': 'Property', 'comment': '', 'domain': 'ngsild:Relationship',
                    'scoped': True, 'status': 'here', 'by': ''}]}


def test_the_plus_on_an_attribute_row_nests_inside_it(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttributeConstraint',
        'node': _constraint_attribute_row(),
        'picks': ['hasConfidence', 'Optional', 'Any value'],
        'replies': {'semforge/attributeOptions': SUB_OPTIONS,
                    'semforge/choices': {'choices': []},
                    'semforge/addAttributeConstraint': {
                        'ok': True, 'file': '/pkg/shacl.ttl', 'line': 68}}})
    assert seen['errors'] == [], seen['errors']
    asked = _sent(seen, 'semforge/attributeOptions')
    assert asked[0]['parentPath'] == ['iffBaseEntities:hasFilter']
    written = _sent(seen, 'semforge/addAttributeConstraint')
    assert written[0]['parentPath'] == ['iffBaseEntities:hasFilter']
    assert written[0]['shape'] == 'http://example.com/CutterShape'
    offered = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert '$(add) New sub-attribute…' in offered


def test_new_sub_attribute_declares_it_carried_by_the_parent(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttributeConstraint',
        'node': _constraint_attribute_row(),
        'picks': ['$(add) New sub-attribute…', 'Property', 'Optional', 'Any value'],
        'inputs': ['hasLatency', ''],
        'replies': {'semforge/attributeOptions': SUB_OPTIONS,
                    'semforge/addAttributeTerm': dict(
                        DECLARED, term='iffBaseEntities:hasLatency', label='hasLatency'),
                    'semforge/choices': {'choices': []},
                    'semforge/addAttributeConstraint': {
                        'ok': True, 'file': '/pkg/shacl.ttl', 'line': 70}}})
    assert seen['errors'] == [], seen['errors']
    declared = _sent(seen, 'semforge/addAttributeTerm')
    assert declared[0]['domain'] == 'iffBaseEntities:hasFilter', \
        'a sub-attribute is declared with its parent attribute as carrier'
    written = _sent(seen, 'semforge/addAttributeConstraint')
    assert written[0]['parentPath'] == ['iffBaseEntities:hasFilter']
    assert written[0]['attribute'] == 'iffBaseEntities:hasLatency'


def _model_attribute_row(**overrides):
    raw = {'kind': 'attribute', 'label': 'hasFilter', 'entity': 'urn:plasmacutter:1',
           'entityType': 'iffBaseEntities:Plasmacutter', 'editable': True,
           'attributePath': ['iffBaseEntities:hasFilter'],
           'path': ['iffBaseEntities:hasFilter', 0, 'object'],
           'datasetId': '@none', 'file': '/pkg/model-instance.jsonld',
           'value': 'urn:filter:1', 'children': []}
    raw.update(overrides)
    return {'raw': raw, 'packageUri': 'file:///pkg/shacl.ttl'}


def test_add_sub_attribute_in_the_data_goes_under_the_row(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addSubAttribute', 'node': _model_attribute_row(),
        'picks': ['iffBaseEntities:hasConfidence', 'Default instance'], 'input': '0.9',
        'replies': {
            'semforge/attributes': {'attributes': [
                {'iri': 'http://example.com/hasConfidence',
                 'term': 'iffBaseEntities:hasConfidence', 'kind': 'Property',
                 'constrained': True, 'parents': ['iffBaseEntities:hasFilter'],
                 'comment': ''}]},
            'semforge/valueChoices': {'choices': [], 'note': ''},
            'semforge/addAttribute': {'ok': True, 'kind': 'Property'}}})
    assert seen['errors'] == [], seen['errors']
    asked = _sent(seen, 'semforge/attributes')
    assert asked[0].get('parent') == 'iffBaseEntities:hasFilter'
    added = _sent(seen, 'semforge/addAttribute')
    assert added[0]['under'] == ['iffBaseEntities:hasFilter']
    assert added[0]['underDataset'] == '@none'
    assert added[0]['name'] == 'iffBaseEntities:hasConfidence'


def test_add_sub_attribute_is_offered_on_value_rows_only(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addSubAttribute',
        'node': _model_attribute_row(kind='entity', attributePath=[]),
        'replies': {}})
    assert seen['requests'] == []
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        menus = json.load(handle)['contributes']['menus']['view/item/context']
    rows = [e for e in menus if e.get('command') == 'semforge.addSubAttribute']
    assert rows and all(e['group'] != 'inline' for e in rows)
    plus = [e for e in menus if e.get('command') == 'semforge.addAttributeConstraint']
    assert {e['when'].replace(FULL_ONLY, '') for e in plus} == {
        'view == semforgeConstraints && viewItem == shape',
        'view == semforgeConstraints && viewItem == attribute'}


def _knowledge_attribute_row():
    return {'raw': {'kind': 'attribute', 'label': 'iffBaseEntities:hasFilter',
                    'iri': 'http://example.com/hasFilter', 'children': []},
            'packageUri': 'file:///pkg/shacl.ttl'}


PLACES = {'places': [{'shape': 'http://example.com/CutterShape',
                      'shapeName': 'iffBaseShacl:CutterShape',
                      'path': ['iffBaseEntities:hasFilter'],
                      'file': '/pkg/shacl.ttl', 'line': 47}]}


def test_the_knowledge_view_declares_a_sub_attribute_and_nests_it(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.newSubAttribute', 'node': _knowledge_attribute_row(),
        'picks': ['Property',
                  'Constrain inside iffBaseShacl:CutterShape › iffBaseEntities:hasFilter',
                  'Optional', 'Any value'],
        'inputs': ['hasLatency', ''],
        'replies': {'semforge/attributeNamespaces': {'namespaces': []},
                    'semforge/addAttributeTerm': dict(
                        DECLARED, term='iffBaseEntities:hasLatency', label='hasLatency'),
                    'semforge/attributePlaces': PLACES,
                    'semforge/choices': {'choices': []},
                    'semforge/addAttributeConstraint': {
                        'ok': True, 'file': '/pkg/shacl.ttl', 'line': 70}}})
    assert seen['errors'] == [], seen['errors']
    declared = _sent(seen, 'semforge/addAttributeTerm')
    assert declared[0]['domain'] == 'http://example.com/hasFilter'
    written = _sent(seen, 'semforge/addAttributeConstraint')
    assert written[0]['shape'] == 'http://example.com/CutterShape'
    assert written[0]['parentPath'] == ['iffBaseEntities:hasFilter']


def test_a_parent_constrained_nowhere_is_declared_and_says_so(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.newSubAttribute', 'node': _knowledge_attribute_row(),
        'picks': ['Property'], 'inputs': ['hasLatency', ''],
        'replies': {'semforge/attributeNamespaces': {'namespaces': []},
                    'semforge/addAttributeTerm': dict(
                        DECLARED, term='iffBaseEntities:hasLatency', label='hasLatency'),
                    'semforge/attributePlaces': {'places': []}}})
    assert _sent(seen, 'semforge/addAttributeTerm')
    assert not _sent(seen, 'semforge/addAttributeConstraint')
    assert any('No shape constrains hasFilter' in m for m in seen['info'])


def test_the_knowledge_view_offers_new_sub_attribute_on_attribute_rows():
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        menus = json.load(handle)['contributes']['menus']['view/item/context']
    rows = [e for e in menus if e.get('command') == 'semforge.newSubAttribute']
    assert {e['group'] for e in rows} == {'inline', '1_add@1'}
    assert all('semforgeKnowledge' in e['when'] for e in rows)


# --- the cache ---------------------------------------------------------------------

CACHE_ROW = {'raw': {'kind': 'cache', 'label': 'Cache', 'children': []},
             'packageUri': 'file:///pkg/shacl.ttl'}
CACHE_STATE = {'ok': True, 'path': '/pkg/.semforge/cache/views', 'bytes': 40960,
               'current': 5, 'entries': [{'view': v, 'current': True} for v in
                                         ('constraints', 'diagnostics', 'knowledge',
                                          'model', 'project')]}


def test_rescan_asks_the_server_to_start_over(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.rescan', 'node': CACHE_ROW,
                             'replies': {'semforge/rescan': {'ok': True}}})
    assert _sent(seen, 'semforge/rescan') == [{'uri': 'file:///pkg/shacl.ttl'}]
    assert any('rescanned' in m for m in seen['messages'])


def test_deleting_the_cache_says_what_and_where_first(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.deleteCache', 'node': CACHE_ROW,
                             'answer': 'Delete the cache',
                             'replies': {'semforge/cacheStatus': CACHE_STATE,
                                         'semforge/clearCache': {'ok': True,
                                                                 'bytes': 40960}}})
    assert '5 stored view(s), 40 KB' in seen['warnings'][0]
    assert '/pkg/.semforge/cache/views' in seen['warnings'][0]
    assert _sent(seen, 'semforge/clearCache') == [
        {'uri': 'file:///pkg/shacl.ttl', 'contexts': False}]


def test_the_downloaded_contexts_go_only_when_asked(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.deleteCache', 'node': CACHE_ROW,
                             'answer': 'Also delete downloaded contexts',
                             'replies': {'semforge/cacheStatus': CACHE_STATE,
                                         'semforge/clearCache': {'ok': True,
                                                                 'bytes': 0}}})
    assert _sent(seen, 'semforge/clearCache')[0]['contexts'] is True


def test_declining_keeps_the_cache(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.deleteCache', 'node': CACHE_ROW,
                             'answer': None,
                             'replies': {'semforge/cacheStatus': CACHE_STATE}})
    assert not _sent(seen, 'semforge/clearCache')


def test_the_cache_row_carries_rescan_and_delete():
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        menus = json.load(handle)['contributes']['menus']['view/item/context']
    on_row = {e['command'] for e in menus
              if e.get('when') == 'view == semforgeProject && viewItem == cache'}
    assert on_row == {'semforge.rescan', 'semforge.deleteCache'}


# --- New entity type… / New subtype… -------------------------------------------------

TYPE_DECLARED = {'ok': True, 'term': 'e:Waterjetcutter', 'label': 'Waterjetcutter',
                 'iri': 'https://example.org/e/Waterjetcutter', 'parent': 'e:Filter',
                 'file': '/pkg/knowledge.ttl', 'line': 42}


def _executed(seen, command):
    return [e['args'] for e in seen['executed'] if e['command'] == command]


def test_a_new_entity_type_needs_no_entity(tmp_path):
    # From the toolbar there is no row: the package is the session's.
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    seen = _drive(tmp_path, {
        'command': 'semforge.newEntityType',
        'pick': 'e:Filter', 'inputs': ['Waterjetcutter'],
        'answer': 'Create its shape',
        'replies': {'semforge/entityTypes': TYPES_REPLY,
                    'semforge/addEntityType': TYPE_DECLARED}})
    declared = [r['params'] for r in seen['requests']
                if r['method'] == 'semforge/addEntityType']
    assert declared == [{'uri': f'file://{tmp_path}/shacl.ttl', 'name': 'Waterjetcutter',
                         'parent': 'e:Filter'}]
    assert not [r for r in seen['requests'] if r['method'] == 'semforge/addEntity']
    assert seen['shown'][0]['file'] == '/pkg/knowledge.ttl'
    assert any('kind of e:Filter' in message for message in seen['info'])
    shaped = _executed(seen, 'semforge.newShape')
    assert shaped[0][0]['raw'] == {'kind': 'type', 'label': 'Waterjetcutter',
                                   'targetClass': 'https://example.org/e/Waterjetcutter'}


def test_a_subtype_takes_its_parent_from_the_row(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.newSubtype',
        'node': {'raw': {'kind': 'type', 'label': 'Filter',
                         'typeClass': 'https://example.org/e/Filter', 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'inputs': ['Waterjetcutter'], 'answer': 'Open its type page',
        'replies': {'semforge/addEntityType': TYPE_DECLARED}})
    assert seen['quickPicks'] == [], 'the parent is not asked again'
    declared = [r['params'] for r in seen['requests']
                if r['method'] == 'semforge/addEntityType']
    assert declared[0]['parent'] == 'https://example.org/e/Filter'
    opened = _executed(seen, 'semforge.openTypePage')
    assert opened[0][0]['raw'] == {'targetClass': 'https://example.org/e/Waterjetcutter'}


def test_a_dismissed_name_declares_nothing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.newSubtype',
        'node': {'raw': {'kind': 'type', 'typeClass': 'https://example.org/e/Filter',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {}})
    assert seen['requests'] == []


def test_the_types_view_offers_both(tmp_path):
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        menus = json.load(handle)['contributes']['menus']
    title = {e['command'] for e in menus['view/title']
             if e.get('when') == 'view == semforgeConstraints'}
    row = {e['command'] for e in menus['view/item/context']
           if e.get('when') == 'view == semforgeConstraints && viewItem == type'}
    assert 'semforge.newEntityType' in title and 'semforge.newSubtype' in row
