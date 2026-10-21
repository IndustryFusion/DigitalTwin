"""The entity type page: one screen per type, in the model's words.

The payload is checked against the corpus (Filter is the example the redesign
was argued from: 39 tree rows that should read as 4 attributes and 3 rules),
the vocabulary on its own, and the renderer through the Node harness -- above
all that nothing from the package reaches the page unescaped.
"""

import json
import os
import shutil
import subprocess

import pytest

from semforge.cooked.typepage import build_type_page, presence, value_text
from semforge.errors import PackageError

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')


@pytest.fixture(scope='module')
def filter_page(corpus):
    return build_type_page(corpus, 'iffBaseEntities:Filter')


def _rows(page):
    return {row['label']: row for row in page['attributes']}


# --- the vocabulary ------------------------------------------------------------

@pytest.mark.parametrize('low, high, said', [
    ('1', '1', 'required · one'), ('0', '1', 'optional'), ('0', None, 'any number'),
    (None, None, 'any number'), ('2', None, 'at least 2'), ('2', '2', 'exactly 2'),
    ('0', '3', 'at most 3'), ('1', '3', '1 to 3'), ('0', '0', 'forbidden')])
def test_presence_reads_as_a_person_would_say_it(low, high, said):
    assert presence(low, high) == said


@pytest.mark.parametrize('kind, params, raw, said', [
    ('Relationship', {'sh:class': 'iffBaseEntities:FilterCartridge'}, [], '→ FilterCartridge'),
    ('Property', {'sh:class': 'base:MachineState'}, [], 'one of MachineState'),
    ('Property', {'sh:datatype': 'xsd:double', 'sh:minInclusive': '0.0',
                  'sh:maxInclusive': '100.0'}, [], 'number · 0 – 100'),
    ('Property', {}, [('sh:or', '([sh:datatype xsd:double] [sh:datatype xsd:integer])')],
     'number'),
    ('Property', {}, [('sh:or', '([sh:datatype xsd:double] [sh:datatype xsd:string])')],
     'any value'),
    ('Property', {'sh:datatype': 'xsd:string'}, [], 'text'),
    ('Property', {'sh:maxInclusive': '5.0'}, [], '≤ 5'),
    ('Relationship', {}, [], 'an entity'),
])
def test_value_reads_in_the_model_s_words(kind, params, raw, said):
    assert value_text(kind, params, raw) == said


# --- the Filter page, from the corpus ---------------------------------------------

def test_the_filter_page_has_its_attributes_own_and_inherited(filter_page):
    rows = _rows(filter_page)
    assert list(rows) == ['hasStrength', 'hasCartridge', 'hasState', 'hasXXXWorkpiece']
    assert rows['hasStrength']['presence'] == 'required · one'
    assert rows['hasStrength']['value'] == 'number · 0 – 100'
    assert rows['hasStrength']['verbatim'] == [], 'a rendered sh:or is not repeated'
    assert rows['hasCartridge']['value'] == '→ FilterCartridge'
    assert rows['hasCartridge']['kind'] == 'Relationship'
    assert rows['hasState']['inherited'] and rows['hasState']['inheritedFrom'] == 'Machine'
    assert rows['hasState']['value'] == 'one of MachineState'
    assert rows['hasXXXWorkpiece']['depth'] == 1, 'a sub-attribute sits under its parent'


def test_every_attribute_of_the_tree_is_on_the_page(corpus, filter_page):
    """The page re-presents the tree; it must not lose a row of it."""
    from semforge.cooked import build_tree

    root = next(r for r in build_tree(corpus) if r.label == 'Filter')

    def attributes(nodes):
        for node in nodes:
            if node.kind == 'attribute':
                yield node
            yield from attributes(node.children)

    assert len(list(attributes(root.children))) == len(filter_page['attributes'])


def test_coverage_is_per_attribute(filter_page):
    rows = _rows(filter_page)
    assert rows['hasCartridge']['tested'] == 'both ways'
    assert rows['hasStrength']['tested'] == 'never fired'


def test_rules_say_what_they_are_and_whether_they_ever_fired(filter_page):
    rules = {r['shapeName'].split(':')[-1]: r for r in filter_page['rules']}
    assert set(rules) == {'FilterStrengthShape', 'StateOnFilterShape', 'StateValueShape'}
    assert rules['StateValueShape']['inherited']
    assert rules['StateOnFilterShape']['text'], 'its sh:message is shown'
    assert all(r['tested'] == 'never fired' for r in rules.values())


def test_the_cases_and_the_model_are_on_the_page(filter_page):
    cases = {c['case'].split('/')[-1]: c for c in filter_page['exercisedBy']}
    assert set(cases) == {'shared-by-two-filters.jsonld', 'without-cartridge.jsonld',
                          'filter-off.jsonld', 'filter-on.jsonld'}
    assert all(c['passed'] for c in cases.values())
    violating = {i['id'] for i in filter_page['instances'] if i['violations']}
    assert violating == {'urn:filter:1', 'urn:filter:2'}
    assert filter_page['summary']['instancesViolating'] == 2


def test_a_supertype_page_counts_its_subtypes_instances(corpus):
    page = build_type_page(corpus, 'iffBaseEntities:Cutter')
    assert {'Lasercutter', 'Plasmacutter'} <= set(page['subtypes'])
    assert any(i['type'] == 'Plasmacutter' for i in page['instances'])


def test_a_class_that_is_not_an_entity_type_is_refused(corpus):
    with pytest.raises(PackageError, match='not an entity type'):
        build_type_page(corpus, 'base:MachineState')


# --- the renderer ------------------------------------------------------------------

def _render(tmp_path, payload, nonce='TESTNONCE', focus=None):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    scenario = tmp_path / 'scenario.json'
    scenario.write_text(json.dumps({'mode': 'render', 'function': 'renderTypePage',
                                    'payload': payload,
                                    'options': {'nonce': nonce, 'focus': focus}}))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'typepage.js'),
                          str(scenario)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout.strip().splitlines()[-1])['html']


def test_the_page_renders_the_filter_payload(tmp_path, filter_page):
    html = _render(tmp_path, filter_page)
    for text in ('hasStrength', 'number · 0 – 100', '→ FilterCartridge',
                 'one of MachineState', 'From Machine', 'never fired',
                 'without-cartridge', 'urn:filter:1', 'Machine</a> ›'):
        assert text in html, text


def test_the_page_runs_only_its_own_script(tmp_path, filter_page):
    html = _render(tmp_path, filter_page, nonce='abc123')
    assert "default-src 'none'" in html
    assert "script-src 'nonce-abc123'" in html
    assert html.count('<script') == html.count('<script nonce="abc123"')


def test_nothing_from_the_package_reaches_the_page_unescaped(tmp_path, filter_page):
    hostile = json.loads(json.dumps(filter_page))
    hostile['label'] = '<img src=x onerror=alert(1)>'
    hostile['attributes'][0]['value'] = '"><script>alert(2)</script>'
    hostile['rules'][0]['text'] = "</span><script>alert(3)</script>"
    html = _render(tmp_path, hostile)
    assert '<img src=x' not in html
    assert '<script>alert' not in html
    assert '&lt;script&gt;alert(2)' in html


def _focused_row(html):
    assert html.count('id="focus"') == 1, 'exactly one row is marked'
    return html.split('id="focus"', 1)[1].split('</tr>', 1)[0]


def test_a_clicked_attribute_is_marked_and_scrolled_to(tmp_path, filter_page):
    """Clicking an attribute in a tree opens its type's page AT that attribute."""
    row = filter_page['attributes'][-1]
    html = _render(tmp_path, filter_page, focus={'path': row['path']})
    assert f'>{row["label"]}<' in _focused_row(html)
    assert "getElementById('focus')" in html and 'scrollIntoView' in html


def test_a_constraint_row_marks_the_attribute_it_belongs_to(tmp_path, filter_page):
    """A full-mode constraint row's path runs below its attribute's: the
    deepest row on the page that the path passes through is the one meant."""
    row = filter_page['attributes'][0]
    html = _render(tmp_path, filter_page,
                   focus={'path': row['path'] + ['https://example.com/hasValue']})
    assert f'>{row["label"]}<' in _focused_row(html)


def test_the_knowledge_tree_marks_by_attribute_alone(tmp_path, filter_page):
    row = filter_page['attributes'][-1]
    html = _render(tmp_path, filter_page, focus={'attribute': row['attribute']})
    assert f'>{row["label"]}<' in _focused_row(html)


def test_no_focus_marks_nothing_and_glyphs_are_gone(tmp_path, filter_page):
    html = _render(tmp_path, filter_page)
    assert 'id="focus"' not in html
    # Indentation is a class: the CSP drops inline style attributes, which is
    # why the page used to fall back on a "└" glyph.
    assert '└' not in html and ' style="' not in html


def test_an_empty_type_says_so_instead_of_rendering_nothing(tmp_path):
    html = _render(tmp_path, {'label': 'Lonely', 'term': 'x:Lonely', 'crumbs': [],
                              'attributes': [], 'rules': [], 'exercisedBy': [],
                              'instances': [], 'subtypes': [], 'summary': {}})
    assert 'No shape constrains an attribute of this type.' in html
    assert 'nothing proves its constraints can fire.' in html


# --- the command ------------------------------------------------------------------

def _drive(tmp_path, scenario):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(path)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_a_type_row_opens_its_page_and_links_navigate(tmp_path, filter_page):
    page = dict(filter_page, ok=True)
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'label': 'Filter',
                         'targetClass': filter_page['iri'], 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'open', 'at': '/pkg/shacl.ttl:105'},
                            {'command': 'type', 'name': 'Machine'}],
        'replies': {'semforge/typePage': page}})
    assert seen['errors'] == [], seen['errors']
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/typePage']
    assert asked[0]['entityType'] == filter_page['iri']
    assert asked[1]['entityType'] == 'Machine', 'a breadcrumb opens that type'
    assert len(seen['webviews']) == 1, 'one panel, reused'
    assert seen['webviews'][0]['title'] == 'Filter · type'
    assert seen['shown'][0]['file'] == '/pkg/shacl.ttl'


def test_a_failed_page_says_why_in_the_panel(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'class', 'iri': 'http://x/Nope', 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/typePage': {'ok': False,
                                          'error': 'http://x/Nope is not an entity type'}}})
    assert 'is not an entity type' in seen['webviews'][0]['html'][-1]
