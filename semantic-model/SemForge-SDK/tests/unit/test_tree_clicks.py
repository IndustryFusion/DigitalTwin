"""A click on a tree row opens its page; the source is a right-click away.

Driven through the real extension wiring with the Node harness: a selection
in a view, and what it asked VS Code to do. `semforge.trees.click: source`
keeps the old behaviour -- the .ttl/.jsonld editor moves to the row.

Also the symbol set: one icon per kind, status as the icon's colour, and no
hover buttons on rows in summary mode.
"""

import json
import re
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')
PACKAGE_JSON = os.path.join(SDK, 'vscode', 'package.json')
TREES = ('semforgeConstraints', 'semforgeShapes', 'semforgeModel', 'semforgeKnowledge')


def _drive(tmp_path, scenario, target='extension.js'):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    result = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, target),
                             str(path)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-1500:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def _click(tmp_path, view, raw, config=None, key='root/0'):
    return _drive(tmp_path, {
        'mode': 'select', 'view': view, 'config': config or {},
        'node': {'key': key, 'raw': dict({'children': []}, **raw),
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/tree': {'roots': []}, 'semforge/model': {'roots': []},
                    'semforge/shapes': {'roots': []},
                    'semforge/knowledge': {'roots': []}}})


def _opened(seen, command):
    return [e['args'] for e in seen['executed'] if e['command'] == command]


ATTRIBUTE = {'kind': 'attribute', 'label': 'hasStrength',
             'path': ['https://x/hasStrength'], 'typeClass': 'https://x/Filter',
             'definedAt': '/pkg/shacl.ttl:105'}


# --- step A: a click opens the page ------------------------------------------------

def test_an_attribute_click_opens_its_type_page_and_keeps_the_keyboard(tmp_path):
    seen = _click(tmp_path, 'semforgeConstraints', ATTRIBUTE)
    opened = _opened(seen, 'semforge.openTypePage')
    assert len(opened) == 1
    node, options = opened[0]
    assert node['raw']['typeClass'] == 'https://x/Filter'
    assert options == {'preserveFocus': True}
    assert seen['shown'] == [], 'the .ttl stays where it was'


def test_the_source_setting_keeps_the_old_click(tmp_path):
    seen = _click(tmp_path, 'semforgeConstraints', ATTRIBUTE,
                  config={'trees.click': 'source'})
    assert _opened(seen, 'semforge.openTypePage') == []
    assert seen['shown'] == [{'file': '/pkg/shacl.ttl', 'line': 104,
                              'preserveFocus': True}]


def test_a_case_click_opens_the_case_page(tmp_path):
    seen = _click(tmp_path, 'semforgeModel',
                  {'kind': 'example', 'label': 'without-cartridge',
                   'file': '/pkg/examples/test_x/without-cartridge.jsonld',
                   'definedAt': '/pkg/examples/test_x/expectations.yaml:3'})
    opened = _opened(seen, 'semforge.openCasePage')
    assert len(opened) == 1
    assert opened[0][0]['raw']['file'].endswith('without-cartridge.jsonld')
    assert opened[0][1] == {'preserveFocus': True}


def test_the_model_scratchpad_has_no_page_and_opens_its_source(tmp_path):
    seen = _click(tmp_path, 'semforgeModel',
                  {'kind': 'entity', 'label': 'urn:filter:1', 'entity': 'urn:filter:1',
                   'definedAt': '/pkg/model-instance.jsonld:7'})
    assert _opened(seen, 'semforge.openCasePage') == []
    assert seen['shown'][0]['file'] == '/pkg/model-instance.jsonld'


# The Tests tree as the server sends it: the model's data is a GROUP ("Main",
# first), under it one example per model file, without a case file.
TESTS_TREE = [
    {'kind': 'group', 'label': 'Tests', 'children': [
        {'kind': 'suite', 'label': 'test_MachineShape', 'children': [
            {'kind': 'example', 'label': 'too-hot.jsonld',
             'file': '/pkg/examples/test_MachineShape/bad/too-hot.jsonld',
             'definedAt': '/pkg/examples/test_MachineShape/bad/too-hot.jsonld:1',
             'children': []}]}]},
    {'kind': 'group', 'label': 'Main', 'children': [
        {'kind': 'example', 'label': 'main.jsonld', 'file': '', 'children': [
            {'kind': 'entity', 'label': 'urn:m:1', 'entity': 'urn:m:1',
             'file': '/pkg/main.jsonld', 'definedAt': '/pkg/main.jsonld:2',
             'children': [
                 {'kind': 'attribute', 'label': 'hasTemperature', 'entity': 'urn:m:1',
                  'file': '/pkg/main.jsonld', 'definedAt': '/pkg/main.jsonld:4',
                  'children': []}]}]}]}]


def _click_in_tests(tmp_path, label):
    return _drive(tmp_path, {
        'mode': 'select', 'view': 'semforgeModel', 'label': label, 'config': {},
        'replies': {'semforge/tree': {'roots': []}, 'semforge/model': {'roots': TESTS_TREE},
                    'semforge/shapes': {'roots': []}, 'semforge/knowledge': {'roots': []}}})


@pytest.mark.parametrize('label, focus', [
    ('Main', None), ('main.jsonld', None), ('urn:m:1', 'urn:m:1'),
    ('hasTemperature', 'urn:m:1')])
def test_the_model_data_opens_the_model_page(tmp_path, label, focus):
    seen = _click_in_tests(tmp_path, label)
    assert seen['errors'] == [], seen['errors']
    assert _opened(seen, 'semforge.openCasePage') == []
    opened = _opened(seen, 'semforge.openModelPage')
    assert len(opened) == 1, seen['executed']
    expected = {'preserveFocus': True}
    if focus:
        expected['focus'] = focus
    assert opened[0][1] == expected
    assert seen['shown'] == [], 'the source stays where it was'


def test_a_case_in_the_same_tree_still_opens_its_case_page(tmp_path):
    seen = _click_in_tests(tmp_path, 'too-hot.jsonld')
    assert seen['errors'] == [], seen['errors']
    assert len(_opened(seen, 'semforge.openCasePage')) == 1
    assert _opened(seen, 'semforge.openModelPage') == []


def test_an_entity_type_in_the_knowledge_opens_its_page(tmp_path):
    seen = _click(tmp_path, 'semforgeKnowledge',
                  {'kind': 'class', 'role': 'entityType', 'label': 'Filter',
                   'iri': 'https://x/Filter', 'definedAt': '/pkg/knowledge.ttl:40'})
    assert len(_opened(seen, 'semforge.openTypePage')) == 1
    assert seen['shown'] == []


def test_a_knowledge_attribute_opens_its_carrier_s_page(tmp_path):
    seen = _click(tmp_path, 'semforgeKnowledge',
                  {'kind': 'attribute', 'label': 'hasStrength', 'iri': 'https://x/hasStrength',
                   'entityType': 'https://x/Filter', 'definedAt': '/pkg/knowledge.ttl:80'})
    assert len(_opened(seen, 'semforge.openTypePage')) == 1


def test_an_ontology_relation_has_no_page_and_opens_its_source(tmp_path):
    seen = _click(tmp_path, 'semforgeKnowledge',
                  {'kind': 'relation', 'label': 'base:isValidFor',
                   'iri': 'https://x/isValidFor', 'definedAt': '/pkg/knowledge.ttl:625'})
    assert _opened(seen, 'semforge.openTypePage') == []
    assert _opened(seen, 'semforge.openVocabularyPage') == []
    assert seen['shown'][0]['line'] == 624


def test_open_source_goes_to_the_row_s_declaration(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.openSource',
        'node': {'raw': ATTRIBUTE, 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {}})
    assert seen['shown'] == [{'file': '/pkg/shacl.ttl', 'line': 104,
                              'preserveFocus': False}]


def test_the_page_opens_on_the_clicked_attribute(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': ATTRIBUTE, 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/typePage': {
            'ok': True, 'label': 'Filter', 'crumbs': [], 'summary': {},
            'attributes': [
                {'label': 'hasCartridge', 'attribute': 'https://x/hasCartridge',
                 'path': ['https://x/hasCartridge'], 'term': 'x:hasCartridge', 'kind': 'Relationship',
                 'presence': 'required · one', 'value': '→ FilterCartridge', 'verbatim': [],
                 'shapeName': 'x:FilterShape', 'depth': 0, 'violations': []},
                {'label': 'hasStrength', 'attribute': 'https://x/hasStrength',
                 'path': ['https://x/hasStrength'], 'term': 'x:hasStrength', 'kind': 'Property',
                 'presence': 'optional', 'value': 'number', 'verbatim': [],
                 'shapeName': 'x:FilterShape', 'depth': 0, 'violations': []}],
            'rules': [], 'exercisedBy': [], 'instances': [], 'subtypes': []}}})
    assert seen['errors'] == [], seen['errors']
    html = seen['webviews'][0]['html'][-1]
    assert html.count('id="focus"') == 1
    assert '>hasStrength<' in html.split('id="focus"', 1)[1].split('</tr>', 1)[0]


# --- step B: the symbol set ---------------------------------------------------------

PROVIDERS = {'semforgeModel': ('ModelTreeProvider', 'model.js', 'semforge/model'),
             'semforgeKnowledge': ('KnowledgeTreeProvider', 'knowledge.js',
                                   'semforge/knowledge')}


def _items(tmp_path, view, roots):
    provider, target, method = PROVIDERS[view]
    return {'items': _drive(tmp_path, {
        'mode': 'items', 'provider': provider, 'uri': 'file:///pkg/shacl.ttl',
        'replies': {method: {'roots': roots}}}, target=target)['rows']}


def test_a_failing_case_keeps_its_beaker_and_turns_red(tmp_path):
    seen = _items(tmp_path, 'semforgeModel', [
        {'kind': 'group', 'label': 'Tests', 'children': [
            {'kind': 'example', 'label': 'good', 'file': '/pkg/a.jsonld', 'children': []},
            {'kind': 'example', 'label': 'bad', 'file': '/pkg/b.jsonld',
             'severity': 'violation', 'children': []}]}])
    rows = {row['label']: row for row in seen['items']}
    assert rows['good']['icon'] == rows['bad']['icon'] == 'beaker'
    assert rows['bad']['color'] == 'list.errorForeground'
    assert rows['good']['color'] == 'testing.iconPassed'


def test_knowledge_tells_entity_types_from_vocabulary_by_icon(tmp_path):
    seen = _items(tmp_path, 'semforgeKnowledge', [
        {'kind': 'group', 'label': 'Entity types', 'children': [
            {'kind': 'class', 'role': 'entityType', 'label': 'Filter', 'children': []}]},
        {'kind': 'group', 'label': 'Vocabulary classes', 'children': [
            {'kind': 'class', 'role': 'vocabulary', 'label': 'MachineState', 'children': [
                {'kind': 'individual', 'label': 'state_ON', 'severity': 'warning',
                 'children': []}]}]}])
    rows = {row['label']: row for row in seen['items']}
    assert rows['Filter']['icon'] == 'symbol-class'
    assert rows['MachineState']['icon'] == 'symbol-enum'
    assert rows['state_ON']['icon'] == 'symbol-enum-member'
    assert rows['state_ON']['color'] == 'list.warningForeground'


def test_only_the_kind_icons_are_used():
    """The review's set; a status icon (warning, error, pencil, lock) on a row
    would say status by shape, which is what the colour is for."""
    allowed = {'symbol-class', 'symbol-interface', 'symbol-field', 'symbol-property',
               'symbol-event', 'symbol-constant', 'beaker', 'symbol-object', 'symbol-enum',
               'symbol-enum-member', 'symbol-namespace', 'project', 'database',
               'settings-gear', 'info', 'pulse'}
    import re
    for name in ('tree.js', 'shapes.js', 'model.js', 'knowledge.js', 'project.js'):
        with open(os.path.join(SRC, name)) as handle:
            source = handle.read()
        assert 'new vscode.ThemeIcon(' not in source, f'{name} bypasses icon()'
        # The first argument of every icon(...) call, ternaries included.
        firsts = re.findall(r"\bicon\(([^,()]*(?:\([^()]*\)[^,()]*)*)[,)]", source)
        used = {name for first in firsts
                for name in re.findall(r"(?<!=== )(?<!== )'([\w-]+)'", first)}
        assert firsts, name
        assert used <= allowed, f'{name}: {used - allowed}'


def test_summary_rows_carry_no_hover_buttons_but_keep_every_action():
    with open(PACKAGE_JSON) as handle:
        menus = json.load(handle)['contributes']['menus']['view/item/context']
    for entry in menus:
        if not entry.get('group', '').startswith('inline'):
            continue
        if not any(f'view == {view}' in entry['when'] for view in TREES):
            continue
        assert entry['when'].endswith(' && config.semforge.trees.detail == full'), entry
        bare = entry['when'][:-len(' && config.semforge.trees.detail == full')]
        assert any(other['command'] == entry['command'] and other['when'] == bare and
                   not other.get('group', '').startswith('inline') for other in menus), \
            f'{entry["command"]} would be unreachable in summary mode'


def test_one_plus_per_view_title():
    with open(PACKAGE_JSON) as handle:
        contributes = json.load(handle)['contributes']
    icons = {c['command']: c.get('icon') for c in contributes['commands']}
    for view in ('semforgeConstraints', 'semforgeModel', 'semforgeKnowledge',
                 'semforgeProject'):
        plus = [e for e in contributes['menus']['view/title']
                if e.get('when') == f'view == {view}' and icons.get(e.get('command')) == '$(add)']
        assert len(plus) <= 1, view


# --- step C: Types and Shapes ---------------------------------------------------------

SHAPE_ROW = {'kind': 'shape', 'label': 'HasValveShape', 'shape': 'https://x/HasValveShape',
             'detail': 'targets subjects of hasValve · 1 attribute(s)',
             'definedAt': '/pkg/shacl.ttl:29'}


def test_a_shape_click_opens_its_page(tmp_path):
    seen = _click(tmp_path, 'semforgeShapes', SHAPE_ROW)
    opened = _opened(seen, 'semforge.openShapePage')
    assert len(opened) == 1 and opened[0][1] == {'preserveFocus': True}
    assert seen['shown'] == []


def test_a_shape_click_in_source_mode_opens_the_ttl(tmp_path):
    seen = _click(tmp_path, 'semforgeShapes', SHAPE_ROW, config={'trees.click': 'source'})
    assert seen['shown'][0]['line'] == 28


def test_a_rule_in_the_types_view_opens_its_shape_page(tmp_path):
    seen = _click(tmp_path, 'semforgeConstraints',
                  {'kind': 'rule', 'label': 'StateOnFilterShape', 'shape': 'https://x/S',
                   'typeClass': 'https://x/Filter', 'definedAt': '/pkg/shacl.ttl:205'})
    assert len(_opened(seen, 'semforge.openShapePage')) == 1
    assert _opened(seen, 'semforge.openTypePage') == []


def test_a_row_belongs_to_its_nearest_type(tmp_path):
    """In the hierarchy, Filter's attribute is Filter's, not Entity's."""
    attribute = {'kind': 'attribute', 'label': 'hasStrength', 'shape': 'https://x/FilterShape',
                 'path': ['https://x/hasStrength'], 'children': []}
    roots = [{'kind': 'type', 'label': 'Entity', 'targetClass': 'https://x/Entity', 'children': [
        {'kind': 'type', 'label': 'Filter', 'targetClass': 'https://x/Filter',
         'children': [attribute]}]}]
    rows = {r['label']: r for r in _drive(tmp_path, {
        'mode': 'items', 'provider': 'CookedTreeProvider', 'uri': 'file:///pkg/shacl.ttl',
        'replies': {'semforge/tree': {'roots': roots}}}, target='tree.js')['rows']}
    assert rows['hasStrength']['typeClass'] == 'https://x/Filter'
    assert rows['Entity']['expanded'], 'a closed root would hide every type'


def test_the_shapes_view_lists_rules_and_shapes_by_their_own_icons(tmp_path):
    rows = _drive(tmp_path, {
        'mode': 'items', 'provider': 'ShapesTreeProvider', 'uri': 'file:///pkg/shacl.ttl',
        'replies': {'semforge/shapes': {'roots': [
            dict(SHAPE_ROW, children=[]),
            dict(SHAPE_ROW, label='StateOnFilterShape', rule=True, severity='violation',
                 children=[])]}}}, target='shapes.js')['rows']
    assert [(r['icon'], r['contextValue']) for r in rows] == [
        ('symbol-interface', 'shape'), ('symbol-event', 'rule')]
    assert rows[1]['color'] == 'list.errorForeground'


SHAPE_PAGE = {
    'ok': True, 'iri': 'https://x/HighPressureShape', 'name': 'ex:HighPressureShape',
    'label': 'HighPressureShape', 'definedAt': '/pkg/shacl.ttl:42',
    'targets': [{'kind': 'sparql', 'value': 'SELECT ?this WHERE { ?this <p> ?o . FILTER(?o > 5) }',
                 'short': 'SPARQL target', 'text': 'the nodes a SPARQL query selects (SHACL-AF)'}],
    'target': 'SPARQL target', 'usedBy': [], 'rule': False,
    'attributes': [{'label': 'hasValve', 'kind': 'Relationship', 'presence': 'at least 1',
                    'value': 'an entity', 'verbatim': [], 'tested': 'untested',
                    'violations': ['urn:pump:2'], 'depth': 0, 'definedAt': '/pkg/shacl.ttl:50'}],
    'rules': [],
    'types': [{'iri': 'https://x/Pump', 'label': 'Pump', 'page': True}],
    'reach': {'model': 1, 'nodes': [{'id': 'urn:pump:2', 'violations': ['hasValve · MinCount']}],
              'more': 0},
    'exercisedBy': [],
    'summary': {'reached': 1, 'violations': 1, 'cases': 0, 'casesFailing': 0, 'neverFired': True}}


def test_the_shape_page_says_its_target_and_links_onwards(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': SHAPE_ROW, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'type', 'name': 'https://x/Pump'}],
        'replies': {'semforge/shapePage': SHAPE_PAGE}})
    assert seen['errors'] == [], seen['errors']
    page = seen['webviews'][0]
    assert page['title'] == 'HighPressureShape · shape'
    html = page['html'][-1]
    for text in ('sh:target', 'the nodes a SPARQL query selects', 'FILTER(?o &gt; 5)',
                 'data-type="https://x/Pump"', 'urn:pump:2', 'never fired',
                 'class="primary" data-action="addAttribute"' if SHAPE_PAGE.get('ownShape')
                 else 'data-action="addCheck"'):
        assert text in html, text
    assert ' style="' not in html, 'the CSP drops inline styles'
    assert _opened(seen, 'semforge.openTypePage')[0][0]['raw']['targetClass'] == 'https://x/Pump'


def test_the_type_page_links_its_shapes_and_the_ones_that_reach_it(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': ATTRIBUTE, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'shape', 'name': 'https://x/HasValveShape'}],
        'replies': {'semforge/typePage': {
            'ok': True, 'label': 'Pump', 'crumbs': [], 'summary': {},
            'attributes': [{'label': 'hasPressure', 'attribute': 'https://x/hasPressure',
                            'path': ['https://x/hasPressure'], 'term': 'x:hasPressure',
                            'kind': 'Property', 'presence': 'required · one', 'value': '≤ 10',
                            'verbatim': [], 'shape': 'https://x/PumpShape',
                            'shapeName': 'ex:PumpShape', 'depth': 0, 'violations': []}],
            'rules': [], 'exercisedBy': [], 'instances': [], 'subtypes': [],
            'alsoCheckedBy': [{'shape': 'https://x/HasValveShape', 'shapeName': 'ex:HasValveShape',
                               'target': 'targets subjects of hasValve',
                               'condition': 'only when it has hasValve', 'reached': 2}]}}})
    html = seen['webviews'][0]['html'][-1]
    assert 'Shapes that apply under a condition' in html and 'only when it has hasValve' in html
    assert 'data-shape="https://x/PumpShape"' in html
    assert _opened(seen, 'semforge.openShapePage')[0][0]['raw']['shape'] == \
        'https://x/HasValveShape'


def test_the_shape_page_menu_keeps_the_rare_actions(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': SHAPE_ROW, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'pageMenu', 'row': -1}],
        'picks': ['$(symbol-class) Open the Pump type page'],
        'replies': {'semforge/shapePage': SHAPE_PAGE}})
    assert [i['label'] for i in seen['quickPicks'][0]['items']] == [
        '$(go-to-file) Open in .ttl', '$(symbol-class) Open the Pump type page',
        '$(add) + Target', '$(edit) Rename…', '$(git-merge) Merge into…',
        '$(trash) Delete…', '$(refresh) Refresh']
    assert _opened(seen, 'semforge.openTypePage')[0][0]['raw']['targetClass'] == 'https://x/Pump'


def test_add_check_on_a_shape_of_its_own_offers_an_attribute_first(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': SHAPE_ROW, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'addCheck', 'row': -1}],
        'replies': {'semforge/shapePage': dict(SHAPE_PAGE, ownShape='https://x/HighPressureShape')}})
    html = seen['webviews'][0]['html'][-1]
    assert 'class="primary" data-action="addAttribute"' in html
    assert [i['label'] for i in seen['quickPicks'][0]['items']] == [
        '$(symbol-field) Attribute', '$(beaker) SPARQL constraint']


# --- step D: the rule section and New case… ------------------------------------------

RULE_PAGE = dict(
    SHAPE_PAGE, iri='https://x/StateOnFilterShape', name='ex:StateOnFilterShape',
    label='StateOnFilterShape', attributes=[], canNewCase=True,
    targets=[{'kind': 'class', 'value': 'https://x/Filter', 'short': 'targets Filter',
              'text': 'every Filter, and every subclass of it'}],
    checks=[{'kind': 'constraint', 'severity': 'warning',
             'message': 'Filter running without running assigned machine',
             'query': 'SELECT $this WHERE { $this <p> ?v . FILTER(?v != <on>) }'}],
    exercisedBy=[{'case': 'test_X/good/filter-on.jsonld', 'file': '/pkg/examples/a.jsonld',
                  'description': '', 'expect': 'valid', 'entities': ['urn:filter:1'],
                  'fired': 0, 'firedOn': [], 'passed': True}])


def test_a_rule_that_never_fired_offers_a_new_case(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': dict(SHAPE_ROW, shape=RULE_PAGE['iri']),
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/shapePage': RULE_PAGE}})
    html = seen['webviews'][0]['html'][-1]
    for text in ('<h2>Checks</h2>', '<h2>Applies to</h2>', '<h2>Tested by</h2>',
                 'Filter running without running assigned machine', 'severity: warning</span>',
                 '>never fired</span>', '>holds</span>', 'data-newcase="1"', '+ New case',
                 'Open in workbench', 'data-action="bench"', 'data-action="addCheck"',
                 'data-action="checkMenu"', 'FILTER(?v != &lt;on&gt;)', 'data-action="pageMenu"',
                 'data-type="https://x/Pump"'):
        assert text in html, text
    # The essentials in reading order; the query folded under its check.
    assert html.index('<h2>Checks</h2>') < html.index('Filter running') \
        < html.index('<h2>Applies to</h2>') < html.index('<h2>Tested by</h2>')
    assert '<details class="query"><summary>query</summary>' in html
    head = html.split('<div class="head">', 1)[1].split('</div></div>', 1)[0]
    assert 'class="primary" data-action="bench"' in head, 'a SPARQL shape opens in the workbench'
    for rare in ('data-action="merge"', 'Refresh</button>', 'Open in .ttl</button>'):
        assert rare not in html, f'{rare}: behind the ⋯'


def test_a_rule_that_fires_says_where_and_offers_no_new_case(tmp_path):
    page = dict(RULE_PAGE, exercisedBy=[dict(RULE_PAGE['exercisedBy'][0], fired=1,
                                             firedOn=['urn:filter:1'])])
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': dict(SHAPE_ROW, shape=page['iri']), 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/shapePage': page}})
    html = seen['webviews'][0]['html'][-1]
    assert '>fires</span>' in html and 'on urn:filter:1' in html
    assert '>fires in 1</span>' in html, 'proven one way, no case where it holds'
    assert 'data-newcase="1"' not in html, 'it fires: no new case needed'


def test_new_case_writes_the_case_and_opens_it(tmp_path):
    made = {'ok': True, 'file': '/pkg/examples/test_S/bad/idle.jsonld',
            'case': 'test_S/bad/idle.jsonld', 'source': 'test_X/good/filter-on.jsonld',
            'resource': 'urn:filter:1',
            'constraint': 'ex:StateOnFilterShape/SPARQLConstraintComponent'}
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': dict(SHAPE_ROW, shape=RULE_PAGE['iri']),
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'inputs': ['idle'],
        'webviewMessages': [{'command': 'newCase'}],
        'replies': {'semforge/shapePage': RULE_PAGE, 'semforge/newCase': made}})
    assert seen['errors'] == [], seen['errors']
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/newCase']
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'shape': RULE_PAGE['iri'],
                      'name': 'idle'}]
    opened = _opened(seen, 'semforge.openCasePage')
    assert opened and opened[0][0]['raw']['file'] == made['file']
    assert any('fails until' in text for text in seen['info'])


# --- step E: Package, Tests, Vocabulary ----------------------------------------------

def test_the_views_are_named_for_what_they_hold():
    with open(PACKAGE_JSON) as handle:
        views = json.load(handle)['contributes']['views']['semforge']
    # Instances holds the model's own data (Main) and the test cases (Tests):
    # both are instance data, next to the three views of the schema.
    assert [v['name'] for v in views] == ['Package', 'Types', 'Shapes', 'Instances',
                                          'Vocabulary']


@pytest.mark.parametrize('tiles, detail, severity', [
    ({'cases': 6, 'casesPassing': 6, 'modelViolations': 3, 'neverFired': 67},
     '6/6 cases pass · 3 violation(s) · 67 untested', ''),
    ({'cases': 6, 'casesPassing': 5}, '5/6 cases pass', 'error'),
    ({'cases': 0, 'casesPassing': 0, 'brokenReferences': 2},
     'no test cases · 2 broken reference(s)', 'error'),
])
def test_the_health_row_says_the_package_at_a_glance(tmp_path, tiles, detail, severity):
    row = _drive(tmp_path, {'mode': 'render', 'function': 'healthRow',
                            'payload': {'ok': True, 'tiles': tiles}}, target='project.js')['html']
    assert row['detail'] == detail and row['severity'] == severity
    # Violations in the model data are information; they do not turn it red.


def test_the_health_row_comes_first_and_opens_the_health_page(tmp_path):
    rows = _drive(tmp_path, {
        'mode': 'items', 'provider': 'ProjectTreeProvider', 'uri': 'file:///pkg/shacl.ttl',
        'replies': {'semforge/project': {'roots': [
            {'kind': 'setting', 'label': 'context', 'children': []}]},
            'semforge/health': {'ok': True, 'tiles': {'cases': 1, 'casesPassing': 1}}}},
        target='project.js')['rows']
    assert rows[0]['label'] == 'Health' and rows[0]['icon'] == 'pulse'
    seen = _click(tmp_path, 'semforgeProject', {'kind': 'health', 'label': 'Health'})
    assert len(_opened(seen, 'semforge.openHealthPage')) == 1


# --- vocabulary classes -----------------------------------------------------------------

VOCAB_PAGE = {
    'ok': True, 'iri': 'https://x/MachineState', 'label': 'MachineState',
    'term': 'base:MachineState', 'comment': '', 'definedAt': '/pkg/knowledge.ttl:625',
    'namespace': 'https://x/', 'parents': [], 'subclasses': [],
    'values': [
        {'iri': 'https://x/state_ERROR', 'name': 'state_ERROR', 'term': 'base:state_ERROR',
         'label': 'ERROR', 'properties': [], 'definedAt': '/pkg/knowledge.ttl:150',
         'uses': {'data': 0, 'shapes': 0, 'queries': 0, 'knowledge': 0, 'total': 0,
                  'places': []}},
        {'iri': 'https://x/state_ON', 'name': 'state_ON', 'term': 'base:state_ON',
         'label': '<b>ON</b>', 'definedAt': '/pkg/knowledge.ttl:173',
         'properties': [{'property': 'base:isValidFor', 'value': 'Machine', 'link': ''}],
         'uses': {'data': 7, 'shapes': 0, 'queries': 6, 'knowledge': 0, 'total': 13,
                  'places': [{'kind': 'queries', 'file': 'shacl.ttl', 'line': 222,
                              'at': '/pkg/shacl.ttl:222',
                              'owner': 'iffBaseShacl:StateOnFilterShape'}]}}],
    'constrainedBy': [{'shape': 'https://x/MachineShape', 'shapeName': 'x:MachineShape',
                       'attribute': 'hasState', 'how': 'sh:class'}],
    'relations': [],
    'summary': {'values': 2, 'unused': 1, 'inData': 1, 'constraints': 1}}

VOCAB_NODE = {'raw': {'kind': 'class', 'role': 'vocabulary', 'label': 'MachineState',
                      'iri': 'https://x/MachineState', 'children': []},
              'packageUri': 'file:///pkg/shacl.ttl'}


def test_a_vocabulary_class_click_opens_its_page(tmp_path):
    seen = _click(tmp_path, 'semforgeKnowledge', VOCAB_NODE['raw'])
    opened = _opened(seen, 'semforge.openVocabularyPage')
    assert len(opened) == 1 and opened[0][1]['cls'] == 'https://x/MachineState'
    assert opened[0][1]['preserveFocus'] is True


def _vocab(tmp_path, **scenario):
    return _drive(tmp_path, dict({
        'command': 'semforge.openVocabularyPage', 'node': VOCAB_NODE,
        'replies': {'semforge/vocabularyPage': VOCAB_PAGE}}, **scenario))


def test_the_vocabulary_page_shows_values_uses_and_what_draws_from_it(tmp_path):
    seen = _vocab(tmp_path)
    page = seen['webviews'][0]
    assert page['title'] == 'MachineState · vocabulary'
    html = page['html'][-1]
    for text in ('2 values', '1 unused', 'drawn from by', 'unused',
                 '7 in data', '6 in queries', 'data-shape="https://x/MachineShape"',
                 'hasState', '+ Value', 'data-action="rowMenu"', 'data-action="pageMenu"',
                 'StateOnFilterShape'):
        assert text in html, text
    assert 'Delete…</button>' not in html, 'Delete waits behind each value\'s ⋯'
    # The values in use first; an unused one is a question, kept for last.
    rows = html.split('<tbody>', 1)[1]
    names = re.findall(r'title="https://x/(state_\w+)"', rows)
    used = [v['name'] for v in VOCAB_PAGE['values'] if v['uses']['total']]
    assert names[:len(used)] == used
    assert '<b>ON</b>' not in html and '&lt;b&gt;ON&lt;/b&gt;' in html
    assert ' style="' not in html, 'the CSP drops inline styles'


def test_a_value_s_menu_holds_label_open_and_delete(tmp_path):
    seen = _vocab(tmp_path, webviewMessages=[{'command': 'rowMenu', 'row': 1}],
                  picks=['$(go-to-file) Open in .ttl'])
    items = seen['quickPicks'][0]['items']
    assert [i['label'] for i in items] == ['$(edit) Label…', '$(go-to-file) Open in .ttl',
                                           '$(trash) Delete…']
    assert items[2]['description'] == 'used in 13 place(s)', 'what Delete would break'
    assert seen['shown'][0]['line'] == 172


def test_a_value_s_type_opens_the_type_page(tmp_path):
    page = json.loads(json.dumps(VOCAB_PAGE))
    page['values'][1]['properties'] = [{
        'property': 'base:isValidFor', 'value': 'x:Machine', 'name': 'valid for',
        'shortValue': 'Machine', 'link': '', 'type': 'https://x/Machine'}]
    seen = _vocab(tmp_path, webviewMessages=[{'command': 'type', 'iri': 'https://x/Machine'}],
                  replies={'semforge/vocabularyPage': page})
    html = seen['webviews'][0]['html'][-1]
    assert '<span class="dim">valid for</span> <a href="#" data-type="https://x/Machine"' in html
    assert _opened(seen, 'semforge.openTypePage')[0][0]['raw']['targetClass'] == \
        'https://x/Machine'


def test_the_vocabulary_page_menu(tmp_path):
    seen = _vocab(tmp_path, webviewMessages=[{'command': 'pageMenu', 'row': -1}])
    assert [i['label'] for i in seen['quickPicks'][0]['items']] == [
        '$(go-to-file) Open in .ttl', '$(refresh) Refresh']


def test_a_value_click_marks_it_on_its_class_page(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.openVocabularyPage', 'node': VOCAB_NODE,
        'args': [{'cls': 'https://x/MachineState', 'focus': 'https://x/state_ON'}],
        'replies': {'semforge/vocabularyPage': VOCAB_PAGE}})
    html = seen['webviews'][0]['html'][-1]
    assert html.count('id="focus"') == 1
    assert 'state_ON' in html.split('id="focus"', 1)[1].split('</tr>', 1)[0]


def test_plus_value_asks_name_and_label_and_writes(tmp_path):
    seen = _vocab(tmp_path, inputs=['state_IDLE', 'IDLE'],
                  webviewMessages=[{'command': 'addValue', 'row': -1}],
                  replies={'semforge/vocabularyPage': VOCAB_PAGE,
                           'semforge/addVocabularyValue': {'ok': True,
                                                           'iri': 'https://x/state_IDLE'}})
    asked = [r['params'] for r in seen['requests']
             if r['method'] == 'semforge/addVocabularyValue']
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'cls': 'https://x/MachineState',
                      'name': 'state_IDLE', 'label': 'IDLE', 'namespace': None}]
    assert 'semforge.refreshKnowledge' in [e['command'] for e in seen['executed']]


def test_deleting_a_used_value_shows_its_uses_and_needs_a_yes(tmp_path):
    message = [{'command': 'delete', 'row': 1}]
    declined = _vocab(tmp_path, webviewMessages=message)
    assert 'used in 13 place(s)' in declined['warnings'][0]
    assert 'StateOnFilterShape' in declined['warnings'][0]
    assert not [r for r in declined['requests']
                if r['method'] == 'semforge/removeVocabularyValue']
    confirmed = _vocab(tmp_path, webviewMessages=message, answer='Delete anyway',
                       replies={'semforge/vocabularyPage': VOCAB_PAGE,
                                'semforge/removeVocabularyValue': {'ok': True, 'left': 13}})
    asked = [r['params'] for r in confirmed['requests']
             if r['method'] == 'semforge/removeVocabularyValue']
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'value': 'https://x/state_ON',
                      'force': True}]


def test_a_label_is_edited_from_the_page(tmp_path):
    seen = _vocab(tmp_path, inputs=['Running'],
                  webviewMessages=[{'command': 'label', 'row': 1}],
                  replies={'semforge/vocabularyPage': VOCAB_PAGE,
                           'semforge/setValueLabel': {'ok': True, 'changed': True}})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/setValueLabel']
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'value': 'https://x/state_ON',
                      'label': 'Running'}]


def test_a_new_vocabulary_class_is_reachable_and_written(tmp_path):
    with open(PACKAGE_JSON) as handle:
        menus = json.load(handle)['contributes']['menus']
    assert any(e.get('command') == 'semforge.newVocabularyClass' and
               e.get('when') == 'view == semforgeKnowledge' and
               not e.get('group', '').startswith('navigation')
               for e in menus['view/title']), 'in the "…" menu: the + is New attribute'
    seen = _drive(tmp_path, {
        'command': 'semforge.newVocabularyClass', 'picks': ['(none)'], 'inputs': ['Shift'],
        'replies': {'semforge/vocabularyClasses': {'classes': []},
                    'semforge/addVocabularyClass': {'ok': True, 'iri': 'https://x/Shift'},
                    'semforge/vocabularyPage': dict(VOCAB_PAGE, label='Shift', values=[])}})
    asked = [r['params'] for r in seen['requests']
             if r['method'] == 'semforge/addVocabularyClass']
    assert asked[0]['name'] == 'Shift' and asked[0]['parent'] is None
    assert seen['webviews'][0]['title'] == 'Shift · vocabulary'


# --- New test… for an attribute --------------------------------------------------------

PRESSURE = {'kind': 'attribute', 'label': 'hasPressure',
            'path': ['myModelEntities:hasPressure'], 'shape': 'https://x/MachineShape',
            'typeClass': 'https://x/Machine', 'children': []}
OPTIONS = {'ok': True, 'type': 'Machine', 'attribute': 'hasPressure',
           'shape': 'myModelShacl:MachineShape', 'options': [
               {'purpose': 'valid', 'label': 'valid', 'detail': 'present', 'automatic': True,
                'name': 'pressure-valid'},
               {'purpose': 'myModelShacl:MachineShape/hasPressure/DatatypeConstraintComponent',
                'label': 'fires: Datatype', 'detail': 'a text where xsd:double is expected',
                'automatic': True, 'name': 'pressure-wrong-datatype'}]}


def test_new_test_is_on_an_attribute_row_of_the_types_view():
    with open(PACKAGE_JSON) as handle:
        menus = json.load(handle)['contributes']['menus']
    entry = next(e for e in menus['view/item/context']
                 if e['command'] == 'semforge.newAttributeTest')
    assert 'view == semforgeConstraints' in entry['when'] and 'attribute' in entry['when']
    assert not entry['group'].startswith('inline'), 'a right-click entry, not a hover icon'


def test_new_test_asks_what_to_prove_and_writes_it(tmp_path):
    made = {'ok': True, 'file': '/pkg/examples/test_MachineShape/bad/p.jsonld',
            'case': 'test_MachineShape/bad/p.jsonld', 'expect': 'invalid',
            'constraint': OPTIONS['options'][1]['purpose'], 'resource': 'urn:m:1',
            'source': 'test_MachineShape/good/running.jsonld', 'automatic': True,
            'passes': True, 'failures': []}
    seen = _drive(tmp_path, {
        'command': 'semforge.newAttributeTest',
        'node': {'raw': PRESSURE, 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': [1], 'inputs': ['pressure-wrong-datatype'],
        'replies': {'semforge/attributeTestOptions': OPTIONS,
                    'semforge/newAttributeTest': made}})
    assert seen['errors'] == [], seen['errors']
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/newAttributeTest']
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'entityType': 'https://x/Machine',
                      'path': ['myModelEntities:hasPressure'],
                      'purpose': OPTIONS['options'][1]['purpose'],
                      'name': 'pressure-wrong-datatype'}]
    assert seen['inputs'][0]['value'] == 'pressure-wrong-datatype', 'the name is suggested'
    assert _opened(seen, 'semforge.openCasePage')[0][0]['raw']['file'] == made['file']
    assert any('it passes' in text for text in seen['info'])


def test_the_type_page_offers_new_test_in_the_tested_column(tmp_path):
    page = {'ok': True, 'iri': 'https://x/Machine', 'label': 'Machine', 'crumbs': [],
            'summary': {}, 'rules': [], 'exercisedBy': [], 'instances': [], 'subtypes': [],
            'attributes': [{'label': 'hasPressure', 'attribute': 'https://x/hasPressure',
                            'path': PRESSURE['path'], 'term': 'x:hasPressure',
                            'kind': 'Property', 'presence': 'optional', 'value': 'number',
                            'verbatim': [], 'shape': 'https://x/MachineShape',
                            'shapeName': 'x:MachineShape', 'depth': 0, 'violations': [],
                            'tested': 'untested'}]}
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'label': 'Machine', 'targetClass': 'https://x/Machine',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'test', 'row': 0}],
        'replies': {'semforge/typePage': page}})
    html = seen['webviews'][0]['html'][-1]
    assert 'data-action="test"' in html and 'New test…' in html
    asked = _opened(seen, 'semforge.newAttributeTest')
    assert asked and asked[0][0]['raw']['typeClass'] == 'https://x/Machine'
    assert asked[0][0]['raw']['path'] == PRESSURE['path']


# --- the shape page edits like the type page -------------------------------------------

EDITABLE_SHAPE = dict(
    SHAPE_PAGE, iri='https://x/MachineShape', name='x:MachineShape', label='MachineShape',
    rule=False, checks=[], ownShape='https://x/MachineShape', ownShapeName='x:MachineShape',
    testType='https://x/Machine',
    attributes=[{'label': 'hasPressure', 'attribute': 'https://x/hasPressure',
                 'path': ['x:hasPressure'], 'term': 'x:hasPressure', 'kind': 'Property',
                 'presence': 'optional', 'value': 'number', 'valueEditable': True,
                 'verbatim': [], 'shape': 'https://x/MachineShape',
                 'shapeName': 'x:MachineShape', 'inherited': False, 'depth': 0,
                 'violations': [], 'tested': 'untested', 'parameters': [],
                 'definedAt': '/pkg/shacl.ttl:40'}])


def _shape(tmp_path, **scenario):
    return _drive(tmp_path, dict({
        'command': 'semforge.openShapePage',
        'node': {'raw': dict(SHAPE_ROW, shape=EDITABLE_SHAPE['iri']),
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/shapePage': EDITABLE_SHAPE}}, **scenario))


def test_the_shape_page_rows_carry_the_type_page_s_actions(tmp_path):
    html = _shape(tmp_path)['webviews'][0]['html'][-1]
    for action in ('data-action="presence"', 'data-action="value"', 'data-action="menu"',
                   'data-action="test"', 'data-action="addAttribute"'):
        assert action in html, action
    assert 'Declared in' not in html, 'one shape: the column would repeat its name'


def test_plus_attribute_on_the_shape_page_adds_to_this_shape(tmp_path):
    seen = _shape(tmp_path, webviewMessages=[{'command': 'addAttribute', 'row': -1}])
    added = _opened(seen, 'semforge.addAttributeConstraint')
    assert added and added[0][0]['raw']['shape'] == 'https://x/MachineShape'


def test_new_test_from_the_shape_page_uses_the_targeted_type(tmp_path):
    seen = _shape(tmp_path, webviewMessages=[{'command': 'test', 'row': 0}])
    asked = _opened(seen, 'semforge.newAttributeTest')
    assert asked and asked[0][0]['raw']['typeClass'] == 'https://x/Machine'


def test_a_shape_targeting_no_type_says_why_it_cannot_start_a_test(tmp_path):
    page = dict(EDITABLE_SHAPE, testType='')
    seen = _shape(tmp_path, webviewMessages=[{'command': 'test', 'row': 0}],
                  replies={'semforge/shapePage': page})
    assert _opened(seen, 'semforge.newAttributeTest') == []
    assert any('targets no entity type' in text for text in seen['info'])


def test_an_edit_on_the_shape_page_writes_and_rerenders(tmp_path):
    seen = _shape(tmp_path, picks=['Required'],
                  webviewMessages=[{'command': 'presence', 'row': 0}],
                  replies={'semforge/shapePage': EDITABLE_SHAPE,
                           'semforge/editAttribute': {'ok': True}})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/editAttribute']
    assert asked and asked[0]['shape'] == 'https://x/MachineShape'
    assert len(seen['webviews'][0]['html']) == 2, 'rendered again after the write'


# --- Constraints…: add, change, remove ---------------------------------------------------

def _constraint_menu(tmp_path, picks, inputs, reply=None):
    row = dict(EDITABLE_SHAPE['attributes'][0], parameters=[
        {'parameter': 'sh:maxCount', 'value': '1', 'path': ['x:hasPressure'],
         'layer': 'attribute'},
        {'parameter': 'sh:datatype', 'value': 'xsd:double',
         'path': ['x:hasPressure', 'ngsild:hasValue'], 'layer': 'value'}])
    page = dict(EDITABLE_SHAPE, attributes=[row])
    seen = _shape(tmp_path, picks=['$(edit) Constraints…'] + picks, inputs=inputs,
                  webviewMessages=[{'command': 'menu', 'row': 0}],
                  replies={'semforge/shapePage': page,
                           'semforge/setConstraint': reply or {'ok': True, 'note': ''},
                           'semforge/choices': {'choices': []}})
    return seen, [r['params'] for r in seen['requests']
                  if r['method'] == 'semforge/setConstraint']


def test_the_constraint_menu_offers_what_is_missing(tmp_path):
    seen, _ = _constraint_menu(tmp_path, [], [])
    offered = [item['label'] for item in seen['quickPicks'][1]['items']]
    for label in ('$(add) sh:minInclusive', '$(add) sh:maxExclusive', '$(add) sh:pattern',
                  '$(add) sh:minLength', 'sh:maxCount 1'):
        assert label in offered, label
    assert '$(add) sh:datatype' not in offered, 'already there: changed, not added'


def test_adding_an_exclusive_bound_sends_an_add_on_the_value(tmp_path):
    _, asked = _constraint_menu(tmp_path, ['$(add) sh:minExclusive'], ['0'])
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'shape': 'https://x/MachineShape',
                      'path': ['x:hasPressure'], 'parameter': 'sh:minExclusive',
                      'value': '0', 'add': True, 'layer': 'value'}]


def test_a_contradiction_is_said_after_the_write(tmp_path):
    seen, _ = _constraint_menu(tmp_path, ['$(add) sh:minExclusive'], ['500'],
                               reply={'ok': True, 'note': 'sh:minExclusive 500 and '
                                      'sh:maxInclusive 16 admit no value'})
    assert any('admit no value' in text for text in seen['warnings'])


def test_an_existing_constraint_can_be_removed(tmp_path):
    _, asked = _constraint_menu(tmp_path, ['sh:maxCount 1', '$(trash) Remove sh:maxCount'],
                                [])
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'shape': 'https://x/MachineShape',
                      'path': ['x:hasPressure'], 'parameter': 'sh:maxCount',
                      'remove': True}]


# --- New shape… ---------------------------------------------------------------------------

MADE_SHAPE = {'ok': True, 'iri': 'https://x/PumpShape', 'name': 'x:PumpShape',
              'file': '/pkg/shacl.ttl', 'line': 47}


def test_the_shapes_view_has_its_plus():
    with open(PACKAGE_JSON) as handle:
        contributes = json.load(handle)['contributes']
    entry = next(e for e in contributes['menus']['view/title']
                 if e.get('command') == 'semforge.newShape')
    assert entry['when'] == 'view == semforgeShapes' and entry['group'].startswith('navigation')
    icons = {c['command']: c.get('icon') for c in contributes['commands']}
    assert icons['semforge.newShape'] == '$(add)'


def test_new_shape_for_an_entity_type(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.newShape',
        'picks': ['$(symbol-class) An entity type', 'Pump'], 'inputs': ['PumpShape'],
        'replies': {'semforge/entityTypes': {'types': [
            {'iri': 'https://x/Pump', 'term': 'x:Pump', 'label': 'Pump', 'ownShape': ''}]},
            'semforge/addShape': MADE_SHAPE,
            'semforge/shapePage': dict(SHAPE_PAGE, label='PumpShape')}})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addShape']
    assert asked == [{'uri': seen['requests'][-1]['params']['uri'], 'name': 'PumpShape',
                      'targetKind': 'class', 'target': 'https://x/Pump'}]
    assert seen['inputs'][0]['value'] == 'PumpShape', 'the name is suggested'
    assert _opened(seen, 'semforge.openShapePage')[0][0]['raw']['shape'] == MADE_SHAPE['iri']


@pytest.mark.parametrize('pick, inputs, kind, target', [
    ('$(symbol-object) One entity', ['urn:my-model:machine:1', 'Machine1Shape'], 'node',
     'urn:my-model:machine:1'),
    ('$(references) Everything a relationship points at', ['RelationshipTargetShape'],
     'objectsOf', 'ngsild:hasObject'),
])
def test_new_shape_for_other_targets(tmp_path, pick, inputs, kind, target):
    seen = _drive(tmp_path, {
        'command': 'semforge.newShape', 'picks': [pick], 'inputs': inputs,
        'replies': {'semforge/addShape': MADE_SHAPE, 'semforge/shapePage': SHAPE_PAGE}})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addShape']
    assert asked[0]['targetKind'] == kind and asked[0]['target'] == target
    assert seen['inputs'][-1]['value'] == inputs[-1], 'the suggested name'


TYPE_WITH_RULES = dict(SHAPE_PAGE, iri='https://x/Pump', label='Pump', crumbs=['Machine'],
                       term='x:Pump', subtypes=['BigPump'], ownShape='https://x/PumpShape',
                       ownShapeName='x:PumpShape', shapeAt='/pkg/shacl.ttl:40',
                       alsoCheckedBy=[], instances=[
                           {'id': 'urn:pump:1', 'type': 'Pump', 'violations': []}],
                       exercisedBy=[{'case': 'test_P/good/ok.jsonld', 'file': '/pkg/examples/ok.jsonld',
                                     'description': '', 'expect': 'valid', 'passed': True,
                                     'entities': ['urn:pump:9']}],
                       rules=[{'shape': 'https://x/PumpRuleShape', 'shapeName': 'x:PumpRuleShape',
                               'kind': 'constraint', 'text': 'Pump running dry',
                               'inherited': False, 'inheritedFrom': '', 'tested': 'never fired',
                               'definedAt': '/pkg/shacl.ttl:80'},
                              {'shape': 'https://x/MachineRule', 'shapeName': 'x:MachineRule',
                               'kind': 'rule', 'text': '', 'inherited': True,
                               'inheritedFrom': 'Machine', 'tested': '',
                               'definedAt': '/pkg/shacl.ttl:90'}],
                       summary={'cases': 1, 'casesFailing': 0, 'instances': 1,
                                'instancesViolating': 0, 'neverFired': 1})


def _pump(tmp_path, **scenario):
    return _drive(tmp_path, dict({
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'label': 'Pump', 'targetClass': 'https://x/Pump',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/typePage': TYPE_WITH_RULES}}, **scenario))


def test_the_type_page_says_the_essentials_first(tmp_path):
    html = _pump(tmp_path)['webviews'][0]['html'][-1]
    body = html.split('<body>', 1)[1]
    # One status line, one primary action, the rest behind the ⋯.
    assert '1 in the main-model, all valid' in body and '1 case(s), all pass' in body
    assert 'class="primary" data-action="addAttribute"' in body
    assert 'data-action="pageMenu"' in body
    for rare in ('data-action="newSubtype"', 'Refresh</button>', 'Open the shape in .ttl</button>'):
        assert rare not in body, rare
    # Subtypes are navigation, next to the crumbs.
    crumbs = body.split('<div class="crumbs">', 1)[1].split('</div>', 1)[0]
    assert 'subtypes: <a href="#" data-type="BigPump">' in crumbs
    # The sections, in reading order.
    assert body.index('>Attributes</h2>') < body.index('>Rules</h2>') < body.index('>Instances</h2>')
    # A rule says what it checks first, then where; inherited ones grouped.
    assert 'Pump running dry <span class="dim">·</span> <a href="#" class="mono" ' \
        'data-shape="https://x/PumpRuleShape"' in body
    assert '<div class="group">From Machine</div>' in body
    assert 'data-action="addSparql"' in body
    # Model entities first, then the cases, one row each.
    assert body.index('urn:pump:1') < body.index('data-case="/pkg/examples/ok.jsonld"')


def test_test_coverage_is_one_column_and_the_model_marks_the_name(tmp_path):
    """The column says how well the cases prove an attribute; what the model's
    data does is a different question, answered beside the attribute's name."""
    html = _pump(tmp_path)['webviews'][0]['html'][-1]
    assert '>Test coverage</th>' in html and '<th>Status</th>' not in html
    row = html.split('data-open="/pkg/shacl.ttl:50"', 1)[1].split('</tr>', 1)[0]
    name, *cells = row.split('<td')
    # A link: what violates it is in the main-model, and that has a page.
    assert 'class="violates" data-model=""' in name and '✗ 1</a>' in name
    assert 'Violated in the main-model by:\nurn:pump:2' in name
    coverage = next(c for c in cells if c.startswith(' class="coverage"'))
    assert 'main-model' not in coverage and 'data-action="test"' in coverage


def test_the_type_page_menu_keeps_the_rare_actions(tmp_path):
    seen = _pump(tmp_path, webviewMessages=[{'command': 'pageMenu', 'row': -1}],
                 picks=['$(type-hierarchy-sub) New subtype…'])
    assert [i['label'] for i in seen['quickPicks'][0]['items']] == [
        '$(type-hierarchy-sub) New subtype…', '$(go-to-file) Open the shape in .ttl',
        '$(refresh) Refresh']
    assert _opened(seen, 'semforge.newSubtype')


def test_a_rule_s_menu_opens_it_where_it_is_edited(tmp_path):
    seen = _pump(tmp_path, webviewMessages=[{'command': 'ruleMenu', 'row': 1}],
                 picks=['$(beaker) Open in SPARQL workbench'])
    assert [i['label'] for i in seen['quickPicks'][0]['items']] == [
        '$(beaker) Open in SPARQL workbench', '$(symbol-interface) Open its shape page',
        '$(go-to-file) Open in .ttl']
    opened = _opened(seen, 'semforge.openSparqlBench')
    assert opened[0][0]['raw']['shape'] == 'https://x/MachineRule' and \
        opened[0][1] == {'kind': 'rule'}


def test_plus_sparql_constraint_goes_on_the_type_s_own_shape(tmp_path):
    seen = _pump(tmp_path, webviewMessages=[{'command': 'addSparql', 'row': -1}])
    assert _opened(seen, 'semforge.addSparqlConstraint')[0][0]['raw']['shape'] == \
        'https://x/PumpShape'


def test_a_case_on_the_type_page_opens_its_case_page(tmp_path):
    seen = _pump(tmp_path, webviewMessages=[{'command': 'case', 'file': '/pkg/examples/ok.jsonld'}])
    assert _opened(seen, 'semforge.openCasePage')[0][0]['raw']['file'] == '/pkg/examples/ok.jsonld'


def test_a_type_without_a_shape_offers_to_create_it(tmp_path):
    page = {'ok': True, 'iri': 'https://x/Pump', 'label': 'Pump', 'crumbs': [],
            'summary': {}, 'attributes': [], 'rules': [], 'exercisedBy': [],
            'instances': [], 'subtypes': [], 'ownShape': ''}
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'label': 'Pump', 'targetClass': 'https://x/Pump',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'createShape', 'row': -1}],
        'replies': {'semforge/typePage': page}})
    html = seen['webviews'][0]['html'][0]
    assert 'data-action="pageMenu"' in html, 'Create its shape waits behind the ⋯'
    asked = _opened(seen, 'semforge.newShape')
    assert asked and asked[0][0]['raw']['targetClass'] == 'https://x/Pump'
    assert asked[0][1] == {'stay': True}, 'the type page stays, for + Attribute'


SHAPELESS_PAGE = {'ok': True, 'iri': 'https://x/Watercutter', 'label': 'Watercutter',
                  'crumbs': [], 'summary': {}, 'attributes': [], 'rules': [],
                  'exercisedBy': [], 'instances': [], 'subtypes': [], 'ownShape': ''}
CREATED = {'ok': True, 'iri': 'https://x/WatercutterShape', 'name': 'WatercutterShape'}


def _type_page_plus(tmp_path, page, **scenario):
    return _drive(tmp_path, dict({
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'label': page['label'], 'targetClass': page['iri'],
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'addAttribute', 'row': -1}],
        'replies': {'semforge/typePage': page}}, **scenario))


def test_plus_attribute_is_offered_before_the_type_has_a_shape(tmp_path):
    seen = _type_page_plus(tmp_path, SHAPELESS_PAGE,
                           commandResults={'semforge.newShape': CREATED})
    html = seen['webviews'][0]['html'][0]
    assert 'data-action="addAttribute"' in html, 'not only "Create its shape"'
    made = _opened(seen, 'semforge.newShape')
    assert made[0][0]['raw']['targetClass'] == 'https://x/Watercutter'
    assert made[0][1] == {'stay': True, 'quiet': True}
    added = _opened(seen, 'semforge.addAttributeConstraint')
    assert added[0][0]['raw'] == {'kind': 'shape', 'shape': CREATED['iri'],
                                  'label': 'WatercutterShape', 'inheritedFrom': ''}
    assert len([r for r in seen['requests'] if r['method'] == 'semforge/typePage']) == 2


def test_no_shape_name_no_attribute(tmp_path):
    seen = _type_page_plus(tmp_path, SHAPELESS_PAGE)
    assert _opened(seen, 'semforge.newShape')
    assert _opened(seen, 'semforge.addAttributeConstraint') == []


def test_a_type_with_its_own_shape_adds_to_it(tmp_path):
    page = dict(SHAPELESS_PAGE, ownShape='https://x/CutterShape', ownShapeName='ex:CutterShape')
    seen = _type_page_plus(tmp_path, page)
    assert _opened(seen, 'semforge.newShape') == []
    added = _opened(seen, 'semforge.addAttributeConstraint')
    assert added[0][0]['raw']['shape'] == 'https://x/CutterShape'


def test_plus_attribute_on_a_types_row_that_only_inherits(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addTypeAttribute',
        'node': {'raw': {'kind': 'type', 'label': 'Watercutter',
                         'targetClass': 'https://x/Watercutter', 'children': [
                             {'kind': 'shape', 'label': 'ex:CutterShape',
                              'shape': 'https://x/CutterShape', 'inheritedFrom': 'Cutter',
                              'children': []}]},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'commandResults': {'semforge.newShape': CREATED}, 'replies': {}})
    assert seen['errors'] == [], seen['errors']
    assert _opened(seen, 'semforge.newShape'), 'the inherited CutterShape is not its own'
    added = _opened(seen, 'semforge.addAttributeConstraint')
    assert added[0][0]['raw']['shape'] == CREATED['iri']


# --- the shape page's node selector ---------------------------------------------------------

SELECTING = dict(EDITABLE_SHAPE, targets=[
    {'kind': 'class', 'value': 'https://x/Machine', 'short': 'targets Machine',
     'text': 'every Machine, and every subclass of it'},
    {'kind': 'sparql', 'value': 'SELECT ?this WHERE {}', 'short': 'SPARQL target',
     'text': 'the nodes a SPARQL query selects (SHACL-AF)'}])


def test_the_selector_lists_targets_each_removable_but_a_query(tmp_path):
    html = _shape(tmp_path, replies={'semforge/shapePage': SELECTING})['webviews'][0]['html'][-1]
    applies = html.split('<h2>Applies to</h2>', 1)[1].split('<h2>Tested by</h2>', 1)[0]
    edit = applies.split('<summary>Edit targets</summary>', 1)[1]
    assert edit.count('data-action="removeTarget"') == 1, 'not the SPARQL one'
    assert 'data-action="addTarget"' in edit


def test_plus_target_adds_what_is_picked(tmp_path):
    seen = _shape(tmp_path, picks=['$(symbol-object) One entity'], inputs=['urn:m:7'],
                  webviewMessages=[{'command': 'addTarget', 'row': -1}],
                  replies={'semforge/shapePage': SELECTING,
                           'semforge/addTarget': {'ok': True, 'note': ''}})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addTarget']
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'shape': SELECTING['iri'],
                      'targetKind': 'node', 'target': 'urn:m:7'}]
    assert len(seen['webviews'][0]['html']) == 2, 'rendered again'


def test_removing_a_target_asks_first(tmp_path):
    message = [{'command': 'removeTarget', 'row': 0}]
    declined = _shape(tmp_path, webviewMessages=message,
                      replies={'semforge/shapePage': SELECTING})
    assert not [r for r in declined['requests'] if r['method'] == 'semforge/removeTarget']
    confirmed = _shape(tmp_path, webviewMessages=message, answer='Remove',
                       replies={'semforge/shapePage': SELECTING,
                                'semforge/removeTarget': {'ok': True, 'note': ''}})
    asked = [r['params'] for r in confirmed['requests']
             if r['method'] == 'semforge/removeTarget']
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'shape': SELECTING['iri'],
                      'targetKind': 'class', 'value': 'https://x/Machine'}]


def test_the_type_page_marks_a_conditional_row_and_sends_it_to_its_shape(tmp_path):
    row = dict(EDITABLE_SHAPE['attributes'][0], inherited=True, inheritedFrom='',
               via='x:HasValveShape', condition='only when it has hasValve',
               shape='https://x/HasValveShape', shapeName='x:HasValveShape')
    page = {'ok': True, 'iri': 'https://x/Pump', 'label': 'Pump', 'crumbs': [],
            'summary': {}, 'attributes': [row], 'rules': [], 'exercisedBy': [],
            'instances': [], 'subtypes': [], 'ownShape': 'https://x/PumpShape',
            'alsoCheckedBy': []}
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'label': 'Pump', 'targetClass': 'https://x/Pump',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/typePage': page}})
    html = seen['webviews'][0]['html'][-1]
    assert 'only when it has hasValve' in html
    assert 'Open shape' in html and 'data-action="override"' not in html
    assert '<tr class="group"><td colspan="7"><a href="#" class="mono" ' \
        'data-shape="https://x/HasValveShape"' in html, 'grouped under its shape'
    assert '>Rules</h2>' in html


# --- New test case… ------------------------------------------------------------------------

CASE_OPTIONS = {'ok': True, 'root': '/pkg/examples', 'suites': ['test_MachineShape'],
                'shapes': [{'iri': 'https://x/MachineShape', 'name': 'x:MachineShape',
                            'label': 'MachineShape'},
                           {'iri': 'https://x/PumpShape', 'name': 'x:PumpShape',
                            'label': 'PumpShape'}],
                'cases': [{'path': 'test_MachineShape/good/running.jsonld', 'expect': 'valid',
                           'description': ''}],
                'entities': ['urn:m:1'],
                'types': [{'iri': 'https://x/Machine', 'label': 'Machine', 'term': 'x:Machine'}],
                'undeclared': ['test_MachineShape/good/by-hand.jsonld']}
MADE_CASE = {'ok': True, 'file': '/pkg/examples/test_PumpShape/good/running-copy.jsonld',
             'case': 'test_PumpShape/good/running-copy.jsonld', 'expect': 'valid',
             'violations': 0, 'passes': True, 'failures': []}


def test_the_tests_view_has_its_plus():
    with open(PACKAGE_JSON) as handle:
        menus = json.load(handle)['contributes']['menus']
    assert any(e.get('command') == 'semforge.newTestCase' and e['when'] == 'view == semforgeModel'
               and e['group'].startswith('navigation') for e in menus['view/title'])
    assert any(e.get('command') == 'semforge.newTestCase' and 'viewItem == suite' in e['when']
               for e in menus['view/item/context'])


def test_new_test_case_in_a_new_suite_from_a_copy(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.newTestCase',
        'picks': ['$(add) test_PumpShape', '$(pass) Should conform', '$(copy) A copy of a case',
                  'test_MachineShape/good/running.jsonld'],
        'inputs': ['running-copy'],
        'replies': {'semforge/testCaseOptions': CASE_OPTIONS,
                    'semforge/addTestCase': MADE_CASE}})
    assert seen['errors'] == [], seen['errors']
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addTestCase']
    assert asked[0]['suite'] == 'test_PumpShape' and asked[0]['expect'] == 'valid'
    assert asked[0]['start'] == 'copy'
    assert asked[0]['source'] == 'test_MachineShape/good/running.jsonld'
    assert seen['inputs'][0]['value'] == 'running-copy', 'the name is suggested'
    assert _opened(seen, 'semforge.openCasePage')[0][0]['raw']['file'] == MADE_CASE['file']


def test_a_suite_row_presets_the_suite(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.newTestCase',
        'node': {'raw': {'kind': 'suite', 'label': 'MachineShape', 'term': 'test_MachineShape',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': ['$(error) Should violate', '$(file) An empty file'], 'inputs': ['too-cold'],
        'replies': {'semforge/testCaseOptions': CASE_OPTIONS,
                    'semforge/addTestCase': dict(MADE_CASE, expect='invalid', passes=False,
                                                 failures=['nothing fired'])}})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addTestCase']
    assert asked[0]['suite'] == 'test_MachineShape' and asked[0]['expect'] == 'invalid'
    assert any('Nothing fires yet' in text for text in seen['warnings'])


NEW_SUITE_ITEM = '$(new-folder) New suite…'


def _new_suite_case(tmp_path, **scenario):
    return _drive(tmp_path, dict({
        'command': 'semforge.newTestCase',
        'picks': [NEW_SUITE_ITEM, '$(pass) Should conform', '$(file) An empty file'],
        'inputs': ['pump limits', 'first'],
        'replies': {'semforge/testCaseOptions': CASE_OPTIONS,
                    'semforge/addTestCase': MADE_CASE}}, **scenario))


def test_new_suite_takes_any_name(tmp_path):
    seen = _new_suite_case(tmp_path)
    assert NEW_SUITE_ITEM in [i['label'] for i in seen['quickPicks'][0]['items']]
    assert seen['inputs'][0]['title'] == 'New suite'
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addTestCase']
    assert asked[0]['suite'] == 'test_pump-limits', 'test_ in front, the space a dash'
    assert asked[0]['name'] == 'first'


def test_new_suite_is_offered_when_every_shape_has_a_suite(tmp_path):
    every = dict(CASE_OPTIONS, suites=['test_MachineShape', 'test_PumpShape'])
    seen = _new_suite_case(tmp_path, replies={'semforge/testCaseOptions': every,
                                              'semforge/addTestCase': MADE_CASE})
    items = seen['quickPicks'][0]['items']
    assert not any(i['label'].startswith('$(add) test_') for i in items)
    new = next(i for i in items if i['label'] == NEW_SUITE_ITEM)
    assert 'every shape has a suite already' in new['description']


def test_the_tests_group_s_new_suite_asks_the_name_first(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.newSuite',
        'node': {'raw': {'kind': 'group', 'label': 'Tests', 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': ['$(error) Should violate', '$(file) An empty file'],
        'inputs': ['test_overheat', 'too-hot'],
        'replies': {'semforge/testCaseOptions': CASE_OPTIONS,
                    'semforge/addTestCase': MADE_CASE}})
    assert [q['items'][0]['label'] for q in seen['quickPicks']][0] == '$(pass) Should conform', \
        'no suite list: the name is asked instead'
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addTestCase']
    assert asked[0]['suite'] == 'test_overheat' and asked[0]['expect'] == 'invalid'


def test_cancelling_the_suite_name_writes_nothing(tmp_path):
    seen = _new_suite_case(tmp_path, inputs=[])
    assert [r for r in seen['requests'] if r['method'] == 'semforge/addTestCase'] == []


@pytest.mark.parametrize('typed, suite', [
    ('pump limits', 'test_pump-limits'), ('test_x', 'test_x'), ('Pump_2.v1', 'test_Pump_2.v1'),
    ('a/b', None), ('../up', None), ('---', None), ('', None), ('pump!', None)])
def test_a_suite_name_is_a_folder_name(tmp_path, typed, suite):
    seen = _drive(tmp_path, {'mode': 'render', 'function': 'suiteName', 'payload': typed},
                  target='testcases.js')
    assert seen.get('html') == suite


def test_the_tests_group_carries_new_suite():
    with open(PACKAGE_JSON) as handle:
        menus = json.load(handle)['contributes']['menus']['view/item/context']
    on_group = {e['command'] for e in menus
                if e.get('when') == 'view == semforgeModel && viewItem == testsGroup'}
    assert {'semforge.newSuite', 'semforge.newTestCase'} <= on_group


def test_an_undeclared_file_can_be_declared(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.newTestCase',
        'picks': ['$(file-add) Declare a file under examples/ that nothing runs',
                  'test_MachineShape/good/by-hand.jsonld', '$(pass) Should conform'],
        'replies': {'semforge/testCaseOptions': CASE_OPTIONS,
                    'semforge/addTestCase': MADE_CASE}})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addTestCase']
    assert asked[0]['start'] == 'existing'
    assert asked[0]['source'] == 'test_MachineShape/good/by-hand.jsonld'


# --- several shapes on one attribute --------------------------------------------------------

def _contribution(shape, presence, value, no_effect):
    return dict(EDITABLE_SHAPE['attributes'][0], shape=f'https://x/{shape}',
                shapeName=f'x:{shape}', presence=presence, value=value, noEffect=no_effect)


GROUPED = dict(EDITABLE_SHAPE['attributes'][0], presence='required · one',
               value='number · ≥ 0 and < 100', shapes=['x:MachineShape', 'x:MachineShape2'],
               notes=[], contributions=[
                   _contribution('MachineShape', 'optional', 'number · ≥ 0 and < 100',
                                 ['sh:minCount 0']),
                   _contribution('MachineShape2', 'required · one', '< 200',
                                 ['sh:maxExclusive 200'])])
TYPE_WITH_TWO = {'ok': True, 'iri': 'https://x/Machine', 'label': 'Machine', 'crumbs': [],
                 'summary': {}, 'attributes': [GROUPED], 'rules': [], 'exercisedBy': [],
                 'instances': [], 'subtypes': [], 'ownShape': 'https://x/MachineShape',
                 'alsoCheckedBy': []}


def _machine(tmp_path, **scenario):
    return _drive(tmp_path, dict({
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'label': 'Machine', 'targetClass': 'https://x/Machine',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/typePage': TYPE_WITH_TWO}}, **scenario))


def test_one_row_with_each_shape_beneath_it(tmp_path):
    html = _machine(tmp_path)['webviews'][0]['html'][-1]
    assert html.count('data-shape="https://x/MachineShape"') == 1
    assert html.count('data-shape="https://x/MachineShape2"') == 1
    assert 'several shapes' in html and 'all apply' in html
    assert 'sh:maxExclusive 200: no effect' in html and 'sh:minCount 0: no effect' in html
    assert html.count('class="contrib"') == 2
    assert 'required · one' in html.split('class="contrib"')[0], 'the combined row first'


def test_editing_the_combined_row_asks_which_shape(tmp_path):
    seen = _machine(tmp_path, picks=['MachineShape2', 'Optional'],
                    webviewMessages=[{'command': 'presence', 'row': 0}],
                    replies={'semforge/typePage': TYPE_WITH_TWO,
                             'semforge/editAttribute': {'ok': True}})
    assert [i['label'] for i in seen['quickPicks'][0]['items']] == \
        ['MachineShape', 'MachineShape2'], 'both shapes offered'
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/editAttribute']
    assert asked and asked[0]['shape'] == 'https://x/MachineShape2'
    assert asked[0]['presence'] == 'optional'


def test_a_shape_s_own_line_edits_that_shape(tmp_path):
    page = json.loads(json.dumps(TYPE_WITH_TWO))
    page['attributes'][0]['contributions'][0]['parameters'] = [
        {'parameter': 'sh:maxCount', 'value': '1', 'path': ['x:hasPressure'],
         'layer': 'attribute'}]
    seen = _machine(tmp_path, picks=['$(edit) Constraints…', 'sh:maxCount 1',
                                     '$(trash) Remove sh:maxCount'],
                    webviewMessages=[{'command': 'menu', 'row': 0, 'contrib': 0}],
                    replies={'semforge/typePage': page,
                             'semforge/setConstraint': {'ok': True},
                             'semforge/choices': {'choices': []}})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/setConstraint']
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'shape': 'https://x/MachineShape',
                      'path': ['x:hasPressure'], 'parameter': 'sh:maxCount',
                      'remove': True}]


def test_each_shape_s_name_leads_its_own_line(tmp_path):
    """No Declared-in column: each shape's line beneath the combined row
    starts with the shape, where the attribute's name stands above."""
    html = _machine(tmp_path)['webviews'][0]['html'][-1]
    line = html.split('<tr class="contrib">', 2)[1].split('</tr>', 1)[0]
    cells = line.split('<td')[1:]
    assert '↳' in cells[0] and 'data-shape="https://x/MachineShape"' in cells[0]
    assert len(cells) == 7, 'the table has seven columns'


# --- Merge into… ---------------------------------------------------------------------------

MERGE_NODE = {'raw': {'shape': 'https://x/MachineShape2'}, 'packageUri': 'file:///pkg/shacl.ttl'}
PLANNED = {'ok': True, 'said': ['hasPressure: sh:minCount 1 on the attribute replaces the '
                                'weaker sh:minCount 0'], 'asserts': 2,
           'name': 'x:MachineShape2', 'intoName': 'x:MachineShape'}


def _merge(tmp_path, answer, replies):
    return _drive(tmp_path, {'command': 'semforge.mergeShape', 'node': MERGE_NODE,
                             'answer': answer, 'replies': replies})


def test_merge_says_what_it_will_do_and_needs_a_yes(tmp_path):
    seen = _merge(tmp_path, None, {'semforge/mergePlan': {
        'ok': True, 'candidates': [{'iri': 'https://x/MachineShape', 'name': 'x:MachineShape'}],
        'said': PLANNED['said'], 'asserts': 2, 'name': 'x:MachineShape2',
        'intoName': 'x:MachineShape'}})
    warning = seen['warnings'][0]
    assert 'Merge x:MachineShape2 into x:MachineShape?' in warning
    assert 'replaces the weaker sh:minCount 0' in warning and '2 test-case assert' in warning
    assert not [r for r in seen['requests'] if r['method'] == 'semforge/mergeShape']


def test_merge_writes_and_opens_the_shape_it_went_into(tmp_path):
    seen = _merge(tmp_path, 'Merge', {
        'semforge/mergePlan': {'ok': True, 'candidates': [
            {'iri': 'https://x/MachineShape', 'name': 'x:MachineShape'}],
            'said': PLANNED['said'], 'asserts': 0, 'name': 'x:MachineShape2',
            'intoName': 'x:MachineShape'},
        'semforge/mergeShape': {'ok': True, 'into': 'https://x/MachineShape',
                                'intoName': 'x:MachineShape', 'said': [], 'asserts': 0,
                                'notes': []},
        'semforge/shapePage': SHAPE_PAGE})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/mergeShape']
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'shape': 'https://x/MachineShape2',
                      'into': 'https://x/MachineShape'}]
    assert _opened(seen, 'semforge.openShapePage')[0][0]['raw']['shape'] == \
        'https://x/MachineShape'


def test_no_candidate_says_why(tmp_path):
    seen = _merge(tmp_path, None, {'semforge/mergePlan': {'ok': True, 'candidates': []}})
    assert any('nothing it can be merged into' in text for text in seen['info'])


def test_merge_is_offered_where_shapes_are(tmp_path):
    seen = _shape(tmp_path, webviewMessages=[{'command': 'pageMenu', 'row': -1}])
    assert 'data-action="pageMenu"' in seen['webviews'][0]['html'][-1]
    assert '$(git-merge) Merge into…' in [i['label'] for i in seen['quickPicks'][0]['items']]
    with open(PACKAGE_JSON) as handle:
        menus = json.load(handle)['contributes']['menus']['view/item/context']
    assert any(e['command'] == 'semforge.mergeShape' and 'semforgeShapes' in e['when']
               for e in menus)


# --- sh:in in the Constraints menu ---------------------------------------------------------

STATE_ROW = dict(EDITABLE_SHAPE['attributes'][0], label='hasState', path=['x:hasState'],
                 parameters=[{'parameter': 'sh:class', 'value': 'x:MachineState',
                              'path': ['x:hasState', 'ngsild:hasValue'], 'layer': 'value'}])
VOCAB_VALUES = dict(VOCAB_PAGE, values=[
    dict(VOCAB_PAGE['values'][0], name='state_OFF', term='x:state_OFF', label='OFF'),
    dict(VOCAB_PAGE['values'][1], name='state_ON', term='x:state_ON', label='ON')])


def _state_menu(tmp_path, row, picks, inputs=None):
    page = dict(EDITABLE_SHAPE, attributes=[row])
    seen = _shape(tmp_path, picks=['$(edit) Constraints…'] + picks, inputs=inputs or [],
                  webviewMessages=[{'command': 'menu', 'row': 0}],
                  replies={'semforge/shapePage': page,
                           'semforge/setConstraint': {'ok': True, 'note': ''},
                           'semforge/vocabularyPage': VOCAB_VALUES,
                           'semforge/choices': {'choices': []}})
    return seen, [r['params'] for r in seen['requests']
                  if r['method'] == 'semforge/setConstraint']


def test_a_list_of_vocabulary_values_is_ticked(tmp_path):
    seen, asked = _state_menu(tmp_path, STATE_ROW, ['$(add) sh:in', ['state_ON']])
    offered = [i['label'] for i in seen['quickPicks'][2]['items']]
    assert offered == ['state_OFF', 'state_ON'], 'the vocabulary values'
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'shape': 'https://x/MachineShape',
                      'path': ['x:hasState'], 'parameter': 'sh:in', 'value': ['x:state_ON'],
                      'add': True, 'layer': 'value'}]


def test_without_a_vocabulary_the_list_is_typed(tmp_path):
    _, asked = _state_menu(tmp_path, EDITABLE_SHAPE['attributes'][0], ['$(add) sh:in'],
                           inputs=['1.5, 2, "off"'])
    assert asked[0]['parameter'] == 'sh:in' and asked[0]['value'] == '1.5, 2, "off"'


def test_an_existing_list_is_edited_with_its_values_ticked(tmp_path):
    row = dict(STATE_ROW, inList={'items': ['x:state_ON'], 'path': ['x:hasState',
                                                                    'ngsild:hasValue'],
                                  'value': '( x:state_ON )'})
    seen, asked = _state_menu(tmp_path, row, ['sh:in ( x:state_ON )', '$(edit) Edit the list…',
                                              ['state_ON', 'state_OFF']])
    ticks = {i['label']: i['picked'] for i in seen['quickPicks'][3]['items']}
    assert ticks == {'state_OFF': False, 'state_ON': True}
    assert asked[0]['value'] == ['x:state_OFF', 'x:state_ON']
    assert asked[0]['add'] is True, 'the list is written anew in place'


def test_an_existing_list_can_be_removed(tmp_path):
    row = dict(STATE_ROW, inList={'items': ['x:state_ON'], 'path': ['x:hasState',
                                                                    'ngsild:hasValue'],
                                  'value': '( x:state_ON )'})
    _, asked = _state_menu(tmp_path, row, ['sh:in ( x:state_ON )', '$(trash) Remove sh:in'])
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'shape': 'https://x/MachineShape',
                      'path': ['x:hasState', 'ngsild:hasValue'], 'parameter': 'sh:in',
                      'remove': True}]


def test_the_click_setting_defaults_to_the_page():
    with open(PACKAGE_JSON) as handle:
        props = json.load(handle)['contributes']['configuration']['properties']
    assert props['semforge.trees.click']['default'] == 'page'
    assert props['semforge.trees.click']['enum'] == ['page', 'source']
