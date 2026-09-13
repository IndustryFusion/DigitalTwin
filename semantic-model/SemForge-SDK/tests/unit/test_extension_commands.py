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
    assert set(subtitles) == {'semforgeConstraints', 'semforgeModel',
                              'semforgeKnowledge'}
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
