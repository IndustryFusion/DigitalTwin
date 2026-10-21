"""Summary trees: one row per meaningful thing, said once.

The slim pass runs over the payloads the server already serialises, so these
tests build the full trees from the corpus exactly as the server does and
check what the summary keeps, what it folds away, and that nothing a reader
needs (an inherited origin, a rule, an ambiguous prefix) is lost on the way.
"""

import json
import os
import shutil
import subprocess

import pytest

from semforge.editor.slim import (drop_prefixes, slim_constraints, slim_knowledge,
                                  slim_model)

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')


@pytest.fixture(scope='module')
def full(corpus):
    from semforge.cooked import build_tree
    from semforge.cooked.examples import build_suite
    from semforge.cooked.knowledge import build_knowledge
    from semforge.editor.server import (_serialise, _serialise_example,
                                        _serialise_knowledge)

    return {'constraints': [_serialise(n) for n in build_tree(corpus)],
            'model': [_serialise_example(n) for n in build_suite(corpus)],
            'knowledge': [_serialise_knowledge(n) for n in build_knowledge(corpus)]}


def _walk(nodes, depth=0):
    for node in nodes:
        yield depth, node
        yield from _walk(node.get('children', []), depth + 1)


def _find(nodes, **match):
    return [n for _, n in _walk(nodes) if all(n.get(k) == v for k, v in match.items())]


# --- constraints ------------------------------------------------------------------------

def test_the_constraint_tree_keeps_attributes_and_drops_parameters(full):
    slim = slim_constraints(full['constraints'])
    kinds = {n['kind'] for _, n in _walk(slim)}
    assert not kinds & {'constraint', 'slot'}
    assert len(list(_walk(slim))) < len(list(_walk(full['constraints']))) / 3
    assert max(d for d, _ in _walk(slim)) <= 3


def test_an_attribute_reads_in_one_line(full):
    slim = slim_constraints(full['constraints'])
    filter_type = _find(slim, kind='type', label='Filter')[0]
    rows = {n['label']: n['detail'] for _, n in _walk([filter_type])
            if n['kind'] == 'attribute'}
    assert rows['hasStrength'] == 'required · one · number · 0 – 100'
    assert rows['hasCartridge'] == 'required · one · → FilterCartridge'
    assert rows['hasState'].endswith('· from Machine'), 'inherited says from where'
    assert filter_type['detail'] == '4 attribute(s) · 3 rule(s)'


def test_a_query_only_shape_is_one_row(full):
    slim = slim_constraints(full['constraints'])
    shape = _find(slim, kind='shape', label='FilterStrengthShape')[0]
    assert shape['detail'] == 'SPARQL constraint' and shape['children'] == []


def test_an_inverse_path_gets_a_readable_label(full):
    slim = slim_constraints(full['constraints'])
    inverse = [n for _, n in _walk(slim) if n['label'] == 'inverse of hasCartridge']
    assert inverse and 'inverse' not in inverse[0]['detail']


def test_an_ambiguous_name_keeps_its_prefix(full):
    slim = slim_constraints(full['constraints'])
    shapes = {n['label'] for _, n in _walk(slim) if n['kind'] == 'shape'}
    assert {'iffBaseShacl:CartridgeShape', 'iffFilterShacl:CartridgeShape'} <= shapes
    assert 'FilterShape' in shapes, 'an unambiguous one loses it'


def test_the_full_payload_is_left_untouched(full):
    before = json.dumps(full['constraints'], sort_keys=True)
    slim_constraints(full['constraints'])
    assert json.dumps(full['constraints'], sort_keys=True) == before


def test_drop_prefixes_only_where_unambiguous():
    nodes = [{'label': 'a:Thing', 'detail': 'b:Other · urn:x:1', 'children': [
        {'label': 'c:Thing', 'detail': '', 'children': []}]}]
    slim = drop_prefixes(nodes)
    assert slim[0]['label'] == 'a:Thing' and slim[0]['children'][0]['label'] == 'c:Thing'
    assert slim[0]['detail'] == 'Other · urn:x:1', 'urns are ids, not prefixed names'


# --- model -----------------------------------------------------------------------------

def test_the_model_folds_type_rows_and_says_each_value_once(full):
    slim = slim_model(full['model'])
    assert not _find(slim, kind='type')
    entity = _find(slim, kind='entity', label='urn:filter:9')[0]
    assert entity['detail'].startswith('Filter')
    values = {n['label']: n['detail'] for n in entity['children']}
    assert values['hasStrength'] == '0.6'
    assert values['hasState'] == 'state_ON'
    cartridge = [n['detail'] for _, n in _walk(slim)
                 if n.get('label') == 'hasCartridge' and n['kind'] == 'attribute']
    assert 'urn:cartridge:1' in cartridge
    assert cartridge and not any(d.startswith('"') for d in cartridge), 'no JSON quotes'
    assert not any('Property' in n.get('detail', '').split(' · ')
                   for _, n in _walk(slim) if n['kind'] == 'attribute')


# --- knowledge -------------------------------------------------------------------------

def test_the_entity_types_are_the_types_view_s_not_the_knowledge_s(full):
    """The hierarchy is drawn once, in Types; the Knowledge summary keeps the
    vocabulary and the attributes."""
    groups = [n['label'] for n in slim_knowledge(full['knowledge'])
              if n['kind'] == 'group']
    assert 'Entity types' not in groups
    assert 'Vocabulary classes' in groups and 'Attributes' in groups
    full_groups = [n['label'] for n in full['knowledge'] if n['kind'] == 'group']
    assert 'Entity types' in full_groups, 'full mode keeps everything'


def test_instances_are_main_then_tests(full):
    slim = slim_model(full['model'])
    assert [n['label'] for n in slim] == ['Main', 'Tests']
    main, tests = slim
    assert main['detail'] == '8 entities · 3 violation(s)'
    assert main['severity'] == 'warning'
    suites = [n for n in tests['children'] if n['kind'] == 'suite']
    assert 'FilterShape' in [s['label'] for s in suites]
    assert all(s.get('term', '').startswith('test_') for s in suites)


def test_a_vocabulary_class_counts_values(full):
    slim = slim_knowledge(full['knowledge'])
    state = _find(slim, kind='class', label='MachineState')[0]
    assert state['detail'].startswith('7 values')


def _vocabulary(*children, detail=''):
    return [{'kind': 'group', 'label': 'Vocabulary classes', 'detail': '', 'children': [
        {'kind': 'class', 'label': 'Kind', 'detail': detail, 'children': list(children)}]}]


def test_an_id_in_several_files_is_one_row():
    rows = [{'kind': 'instance', 'label': 'urn:x:1', 'detail': f'f{i}.jsonld',
             'children': []} for i in range(4)]
    slim = slim_knowledge(_vocabulary(*rows))
    kind = _find(slim, kind='class', label='Kind')[0]
    assert len(kind['children']) == 1 and kind['children'][0]['detail'] == 'in 4 files'
    assert len(kind['children'][0]['children']) == 4


def test_a_list_of_shapes_becomes_a_count():
    slim = slim_knowledge(_vocabulary(detail='a:One + b:Two + c:Three'))
    assert _find(slim, kind='class', label='Kind')[0]['detail'].startswith('3 shape(s)')


# --- over the protocol and in the extension ---------------------------------------------

def test_the_server_slims_only_when_asked(corpus_path):
    from test_lsp_protocol import Session

    document = os.path.join(corpus_path, 'shacl.ttl')
    live = Session(document)
    try:
        live.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                   'params': {'processId': os.getpid(), 'rootUri': 'file://' + corpus_path,
                              'capabilities': {}}})
        assert live.wait_for(lambda m: m.get('id') == 1)
        replies = {}
        for number, detail in ((71, None), (72, 'summary')):
            params = {'uri': 'file://' + document}
            if detail:
                params['detail'] = detail
            live.send({'jsonrpc': '2.0', 'id': number, 'method': 'semforge/tree',
                       'params': params})
            replies[detail] = live.wait_for(lambda m, n=number: m.get('id') == n)[0]['result']
    finally:
        live.close()
    full_kinds = {n['kind'] for _, n in _walk(replies[None]['roots'])}
    slim_kinds = {n['kind'] for _, n in _walk(replies['summary']['roots'])}
    assert 'constraint' in full_kinds, 'an older client still gets the full tree'
    assert 'constraint' not in slim_kinds and replies['summary']['detail'] == 'summary'


def _drive(tmp_path, scenario, target='extension.js'):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, target), str(path)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_trees_ask_for_the_summary_by_default(tmp_path):
    seen = _drive(tmp_path, {'mode': 'tree', 'provider': 'CookedTreeProvider',
                             'uri': 'file:///pkg/shacl.ttl',
                             'replies': {'semforge/tree': {'roots': []}}}, target='tree.js')
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/tree']
    assert asked and asked[0]['detail'] == 'summary'


def test_override_on_a_summary_row_goes_to_the_type_page(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.overrideHere',
        'node': {'raw': {'kind': 'attribute', 'label': 'hasState', 'shape': 'x:S',
                         'path': ['iffBaseEntities:hasState'], 'parameter': '',
                         'inheritedFrom': 'x:MachineShape', 'typeClass': 'x:Filter',
                         'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {}})
    opened = [e for e in seen['executed'] if e['command'] == 'semforge.openTypePage']
    assert opened and opened[0]['args'][0]['raw']['targetClass'] == 'x:Filter'
    assert seen['requests'] == [], 'nothing is written from a summary row'
