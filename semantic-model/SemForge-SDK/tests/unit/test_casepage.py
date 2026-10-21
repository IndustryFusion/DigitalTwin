"""The test case page: claims, outcome, and the data as entity cards.

The payload is checked against the corpus cases -- it must agree with
`semforge test` about whether a case passes, attach every violation to the
attribute it is about (a missing sub-attribute to its parent), and keep values
intact. The renderer and the command are driven through the Node harness.
"""

import json
import os
import shutil
import subprocess

import pytest

from semforge.cooked.casepage import build_case_page
from semforge.errors import PackageError

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')
WITHOUT = 'test_FilterShape/bad/without-cartridge.jsonld'
SHARED = 'test_CartridgeShape/bad/shared-by-two-filters.jsonld'


@pytest.fixture(scope='module')
def without(corpus):
    return build_case_page(corpus, WITHOUT)


@pytest.fixture(scope='module')
def shared(corpus):
    return build_case_page(corpus, SHARED)


def _cards(page):
    return {card['id']: card for file in page['files'] for card in file['cards']}


def _rows(card):
    return {row['name']: row for row in card['attributes']}


# --- claims and outcome ------------------------------------------------------------

def test_the_claim_holds_and_the_case_passes(without):
    assert without['expect'] == 'invalid' and without['passed']
    assert without['failures'] == []
    claim = without['claims'][0]
    assert claim['holds'] and claim['resource'] == 'urn:filter:9'
    assert claim['explained']['text'] == 'hasCartridge is required but missing'


def test_what_fired_unasserted_is_listed_separately(without):
    assert [u['constraint'] for u in without['unasserted']] == [
        'iffBaseShacl:MachineShape/hasXXXWorkpiece/MinCountConstraintComponent']


def test_the_page_agrees_with_semforge_test(corpus):
    from semforge.cli.main import _examples_and_reports
    from semforge.expect import run_tests
    from semforge.expect.store import load_expectations
    from semforge.sanity import known_constraints

    outcomes = {o.example: o.passed for o in run_tests(
        _examples_and_reports(corpus, load_expectations(corpus.path)),
        known_constraints(corpus))}
    for case, passed in outcomes.items():
        assert build_case_page(corpus, case)['passed'] == passed, case


def test_an_undeclared_case_is_refused(corpus):
    with pytest.raises(PackageError, match='not a declared test case'):
        build_case_page(corpus, 'test_Nothing/bad/nope.jsonld')


# --- the data ------------------------------------------------------------------------

def test_a_missing_attribute_lands_on_the_entity(without):
    card = _cards(without)['urn:filter:9']
    assert [v['text'] for v in card['violations']] == ['hasCartridge is required but missing']


def test_a_missing_sub_attribute_lands_on_its_parent(without):
    rows = _rows(_cards(without)['urn:filter:9'])
    assert [v['text'] for v in rows['hasState']['violations']] == [
        'hasXXXWorkpiece is required but missing']
    assert rows['hasState']['violations'][0]['shape'] == 'MachineShape'
    assert rows['hasState']['violations'][0]['detail'], 'the raw message stays as the tooltip'


def test_includes_are_their_own_sections_with_who_shares_them(shared):
    roles = [(f['role'], f['relative']) for f in shared['files']]
    assert roles[0] == ('case', SHARED)
    assert ('include', 'subobjects/cartridge-fresh.jsonld') in roles
    cartridge = next(f for f in shared['files'] if f['relative'].endswith('cartridge-fresh.jsonld'))
    assert len(cartridge['sharedBy']) == 2


def test_values_are_kept_whole(shared):
    rows = _rows(_cards(shared)['urn:cartridge:1'])
    assert rows['isUsedFrom']['value'] == '2024-02-27T13:54:55.400Z', 'a timestamp has colons'
    assert rows['hasWasteclass']['value'] == 'WC1', 'a prefixed name loses its prefix'
    assert _rows(_cards(shared)['urn:filter:1'])['hasCartridge']['value'] == 'urn:cartridge:1'


def test_rows_point_at_their_lines(shared):
    card = _cards(shared)['urn:filter:8']
    with open(card['file'], encoding='utf-8') as handle:
        lines = handle.read().split('\n')
    assert 'urn:filter:8' in lines[card['line'] - 1] or 'urn:filter:8' in lines[card['line']]
    row = _rows(card)['hasStrength']
    assert 'hasStrength' in lines[row['line'] - 1]


# --- the renderer and the command ------------------------------------------------------

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


def _render(tmp_path, page, focus=None):
    return _node(tmp_path, {'mode': 'render', 'function': 'renderCasePage',
                            'payload': page, 'options': {'nonce': 'n1', 'focus': focus}},
                 'casepage.js')['html']


def test_a_clicked_entity_s_card_is_marked(tmp_path, without):
    """A click on an entity in the Model tree opens its case AT that entity."""
    wanted = without['files'][-1]['cards'][-1]['id']
    html = _render(tmp_path, without, focus=wanted)
    assert html.count('id="focus"') == 1
    assert wanted in html.split('id="focus"', 1)[1].split('</div>', 2)[0]
    assert '└' not in _render(tmp_path, without)


def test_the_page_shows_claims_and_cards(tmp_path, without):
    html = _render(tmp_path, without)
    for text in ('expects invalid', 'passes', 'holds', 'also fired',
                 'hasCartridge is required but missing',
                 'hasXXXWorkpiece is required but missing', 'urn:filter:9'):
        assert text in html, text
    assert "script-src 'nonce-n1'" in html


def test_nothing_reaches_the_page_unescaped(tmp_path, without):
    hostile = json.loads(json.dumps(without))
    hostile['description'] = '<script>alert(1)</script>'
    hostile['files'][0]['cards'][0]['attributes'][0]['value'] = '"><img src=x onerror=alert(2)>'
    html = _render(tmp_path, hostile)
    assert '<script>alert' not in html and '<img src=x' not in html


def test_a_case_row_opens_its_page_and_a_type_link_opens_the_type_page(tmp_path, without):
    seen = _node(tmp_path, {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'label': 'without-cartridge.jsonld',
                         'file': without['file'], 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'type', 'name': 'Filter'},
                            {'command': 'open', 'at': f"{without['file']}:2"}],
        'replies': {'semforge/casePage': dict(without, ok=True)}}, 'extension.js')
    assert seen['errors'] == [], seen['errors']
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/casePage']
    assert asked[0]['case'] == without['file']
    assert seen['webviews'][0]['title'] == 'without-cartridge · test case'
    typed = [e for e in seen['executed'] if e['command'] == 'semforge.openTypePage']
    assert typed[0]['args'][0]['raw']['targetClass'] == 'Filter'
    assert seen['shown'][0]['file'] == without['file']


def test_the_case_row_carries_its_file(corpus):
    from semforge.cooked.examples import build_suite

    def walk(nodes):
        for node in nodes:
            yield node
            yield from walk(node.children)

    from semforge.expect.store import load_expectations

    declared = {os.path.basename(e.path) for e in load_expectations(corpus.path).examples}
    rows = [n for n in walk(build_suite(corpus)) if n.kind == 'example']
    cases = [n for n in rows if n.label in declared]
    assert len(cases) == len(declared)
    assert all(os.path.isfile(n.file) for n in cases)
    # The model scratchpad shares the row kind but is not a case: no case file.
    assert all(not n.file for n in rows if n.label not in declared)


def test_the_main_row_opens_the_main_page(tmp_path):
    page = {'ok': True, 'kind': 'model', 'name': 'Main', 'files': [], 'claims': [],
            'unasserted': [], 'file': '/pkg/model-instance.jsonld',
            'summary': {'entities': 0, 'violations': 0}}
    seen = _node(tmp_path, {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'label': 'model-instance.jsonld',
                         'file': '', 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/modelPage': page}}, 'extension.js')
    assert seen['errors'] == [], seen['errors']
    assert [r['method'] for r in seen['requests']] == ['semforge/modelPage']
    assert seen['webviews'][0]['title'] == 'Main · instances'


# --- "Assert it" ------------------------------------------------------------------------

UNASSERTED = 'iffBaseShacl:MachineShape/hasXXXWorkpiece/MinCountConstraintComponent'


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _yaml_of(root):
    return os.path.join(root, 'examples', 'test_FilterShape', 'bad', 'expectations.yaml')


def test_asserting_adds_exactly_the_claim_and_keeps_the_file(kms):
    from semforge.expect.store import add_assert
    from semforge.package import load

    path = _yaml_of(kms)
    with open(path, encoding='utf-8') as handle:
        original = '# kept: a comment the edit must not drop\n' + handle.read()
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(original)

    made = add_assert(load(kms), WITHOUT, UNASSERTED, 'urn:filter:9')
    assert made['note'] == ''
    with open(path, encoding='utf-8') as handle:
        after = handle.read()
    # Two lines more, and they are the new assert -- the existing one's
    # `resource: urn:filter:9` line is identical text, so compare positions.
    old_lines, new_lines = original.splitlines(), after.splitlines()
    assert len(new_lines) == len(old_lines) + 2
    assert [line.strip() for line in new_lines[-2:]] == [f'- constraint: {UNASSERTED}',
                                                         'resource: urn:filter:9']
    assert new_lines[:-2] == old_lines
    assert after.startswith('# kept: a comment the edit must not drop')

    page = build_case_page(load(kms), WITHOUT)
    assert page['unasserted'] == [] and all(c['holds'] for c in page['claims'])
    assert page['passed']


@pytest.mark.parametrize('constraint, resource, says', [
    ('iffBaseShacl:FilterShape/hasCartridge/MinCountConstraintComponent', 'urn:filter:9',
     'already asserts'),
    ('iffBaseShacl:NoSuchShape/hasX/MinCountConstraintComponent', 'urn:filter:9',
     'no shape declares'),
])
def test_an_assert_that_cannot_mean_anything_is_refused(kms, constraint, resource, says):
    from semforge.expect.store import add_assert
    from semforge.package import load

    with open(_yaml_of(kms), encoding='utf-8') as handle:
        before = handle.read()
    with pytest.raises(PackageError, match=says):
        add_assert(load(kms), WITHOUT, constraint, resource)
    with open(_yaml_of(kms), encoding='utf-8') as handle:
        assert handle.read() == before


def test_a_pinned_residue_is_called_out(kms):
    from semforge.expect.store import add_assert
    from semforge.package import load

    path = _yaml_of(kms)
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text.replace('    expect: invalid\n',
                                  '    expect: invalid\n    residue: abc123\n', 1))
    made = add_assert(load(kms), WITHOUT, UNASSERTED, 'urn:filter:9')
    assert 'semforge accept' in made['note']


def test_assert_it_sits_only_on_what_fired_unasserted(tmp_path, without):
    html = _render(tmp_path, without)
    assert html.count('data-assert="') == len(without['unasserted']) == 1
    card = _cards(without)['urn:filter:9']
    assert f'data-open="{card["file"]}:{card["line"]}">Open in .jsonld' in html
    assert 'fix the data instead' in html, 'the tooltip says when not to'


def test_clicking_assert_it_writes_and_re_renders(tmp_path, without):
    scenario = {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'label': 'without-cartridge.jsonld',
                         'file': without['file'], 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'assert', 'index': 0}],
        'replies': {'semforge/casePage': dict(without, ok=True),
                    'semforge/addAssert': {'ok': True, 'file': '/pkg/x.yaml', 'note': ''}}}
    seen = _node(tmp_path, scenario, 'extension.js')
    assert seen['errors'] == [], seen['errors']
    sent = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addAssert']
    assert sent == [{'uri': 'file:///pkg/shacl.ttl', 'case': WITHOUT,
                     'constraint': UNASSERTED, 'resource': 'urn:filter:9'}]
    assert len([r for r in seen['requests'] if r['method'] == 'semforge/casePage']) == 2
    assert any(e['command'] == 'semforge.refreshModel' for e in seen['executed'])


# --- editing from the page ----------------------------------------------------------------

def _first_editable(page):
    for f, file in enumerate(page['files']):
        for c, card in enumerate(file['cards']):
            for r, row in enumerate(card['attributes']):
                if (row.get('node') or {}).get('editable'):
                    return f'{f}.{c}.{r}', card, row
    raise AssertionError('no editable row')


def test_every_card_and_row_carries_the_tree_row_it_edits(without):
    for file in without['files']:
        for card in file['cards']:
            assert card['node']['kind'] == 'entity' and card['node']['entity'] == card['id']
            assert 'children' not in card['node']
    _, card, row = _first_editable(without)
    assert row['node']['entity'] == card['id']
    assert row['attributeNode']['attributePath'][-1] == row['term']


def test_the_page_offers_editing(tmp_path, without):
    html = _render(tmp_path, without)
    at, _, _ = _first_editable(without)
    assert f'data-edit="{at}"' in html and f'data-rowmenu="{at}"' in html
    assert 'data-addattr="0.0"' in html and 'data-addentity="0"' in html


def _edit(tmp_path, page, messages, **extra):
    scenario = dict({
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'label': 'without-cartridge.jsonld',
                         'file': page['file'], 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': messages,
        'replies': {'semforge/casePage': dict(page, ok=True)}}, **extra)
    seen = _node(tmp_path, scenario, 'extension.js')
    assert seen['errors'] == [], seen['errors']
    return seen


def _ran(seen, command):
    return [e['args'][0] for e in seen['executed'] if e['command'] == command]


def test_a_value_click_runs_edit_value_and_re_renders(tmp_path, without):
    at, _, row = _first_editable(without)
    seen = _edit(tmp_path, without, [{'command': 'edit', 'at': at}])
    assert _ran(seen, 'semforge.editValue') == [
        {'raw': row['node'], 'packageUri': 'file:///pkg/shacl.ttl'}]
    assert len([r for r in seen['requests'] if r['method'] == 'semforge/casePage']) == 2


def test_add_attribute_and_add_entity_use_the_tree_commands(tmp_path, without):
    seen = _edit(tmp_path, without, [{'command': 'addAttribute', 'at': '0.0'},
                                     {'command': 'addEntity', 'at': '0'}])
    card = without['files'][0]['cards'][0]
    raw = _ran(seen, 'semforge.addAttribute')[0]['raw']
    # The entity's row, and what it already has by datasetId -- an attribute
    # it has is added again as another instance or another observation.
    assert {k: v for k, v in raw.items() if k != 'children'} == \
        {k: v for k, v in card['node'].items() if k != 'children'}
    assert {c['attributePath'][0]: c['datasets'] for c in raw['children']} == {
        a['term']: ['@none'] for a in card['attributes']}
    assert _ran(seen, 'semforge.addEntity')[0]['raw'] == {
        'kind': 'example', 'file': without['files'][0]['path']}


@pytest.mark.parametrize('pick, command, which', [
    (1, 'semforge.addSubAttribute', 'attributeNode'),
    (2, 'semforge.addObservation', 'attributeNode'),
    (3, 'semforge.addInstance', 'attributeNode'),
    (4, 'semforge.setUnitCode', 'attributeNode'),
    (5, 'semforge.setDatasetId', 'attributeNode'),
    (6, 'semforge.goToShape', 'node'),
    (8, 'semforge.removeCaseValue', 'attributeNode')])
def test_the_row_menu(tmp_path, without, pick, command, which):
    at, _, row = _first_editable(without)
    seen = _edit(tmp_path, without, [{'command': 'rowMenu', 'at': at}], pick=pick)
    labels = [item['label'] for item in seen['quickPicks'][0]['items']]
    assert labels == ['$(edit) Edit value', '$(add) Add sub-attribute',
                      '$(history) Add observation', '$(layers) Add instance…',
                      '$(symbol-ruler) Unit…', '$(symbol-key) Change datasetId…',
                      '$(symbol-ruler) Go to the SHACL rule',
                      '$(go-to-file) Open in .jsonld', f'$(trash) Remove {row["name"]}…']
    ran = _ran(seen, command)[0]['raw']
    if command == 'semforge.setUnitCode':
        # The instance, with the unit it says now and its entity type.
        ran = {k: v for k, v in ran.items() if k not in ('current', 'entityType')}
        assert ran == {k: v for k, v in row[which].items() if k != 'entityType'}
    else:
        assert ran == row[which]


def test_a_dismissed_row_menu_changes_nothing(tmp_path, without):
    at, _, _ = _first_editable(without)
    seen = _edit(tmp_path, without, [{'command': 'rowMenu', 'at': at}])
    assert len([r for r in seen['requests'] if r['method'] == 'semforge/casePage']) == 1


# --- the Main page ----------------------------------------------------------------

@pytest.fixture(scope='module')
def model(corpus):
    from semforge.cooked.casepage import build_model_page
    return build_model_page(corpus)


def test_the_model_page_shows_the_model_files_and_their_violations(model):
    assert model['kind'] == 'model' and model['claims'] == []
    assert model['files'] and all(f['role'] == 'model' for f in model['files'])
    cards = _cards(model)
    assert cards and all(c['node']['kind'] == 'entity' for c in cards.values())
    counted = sum(len(c['violations']) for c in cards.values()) + sum(
        _violations(row) for c in cards.values() for row in c['attributes'])
    assert counted == model['summary']['violations']


def _violations(row):
    return len(row['violations']) + sum(_violations(c) for c in row.get('children', []))


def test_the_model_page_has_no_claims_or_verdict(tmp_path, model):
    html = _render(tmp_path, model)
    assert 'Claims' not in html and 'expects' not in html and 'passes' not in html
    assert 'Open the model file' in html and 'data-addentity="0"' in html


def test_sub_attributes_get_their_own_rows(model):
    nested = [(row, child) for file in model['files'] for card in file['cards']
              for row in card['attributes'] for child in row.get('children', [])]
    assert nested
    for row, child in nested:
        assert child['node'] and child['attributeNode']['attributePath'][-1] == child['term']
        assert len(child['attributeNode']['attributePath']) > len(
            row['attributeNode']['attributePath'])


def test_an_edit_shows_on_the_next_render_of_the_model_page(kms, monkeypatch):
    from unittest import mock

    from semforge.editor import server

    monkeypatch.setattr(server, '_publish', lambda *args: None)
    uri = 'file://' + os.path.join(kms, 'shacl.ttl')
    page = server.model_page_feature(mock.MagicMock(), {'uri': uri})
    assert page['ok'], page
    card, row = next((c, r) for f in page['files'] for c in f['cards']
                     for r in c['attributes']
                     if (r.get('node') or {}).get('editable') and str(r['value'])[:1].isdigit())
    node = row['node']
    done = server.set_example_value(mock.MagicMock(), {
        'uri': uri, 'entity': node['entity'], 'path': node['path'],
        'file': node['file'], 'value': '77'})
    assert done['ok'], done
    again = server.model_page_feature(mock.MagicMock(), {'uri': uri})
    assert not again['cached']
    after = _rows(_cards(again)[card['id']])[row['name']]
    assert after['value'] == '77' and after['value'] != row['value']
