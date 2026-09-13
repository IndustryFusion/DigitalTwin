"""The server driven over real stdio.

Every other editor test calls the analysis layer directly, which is what keeps
that layer honest. This one is the opposite check: that the wiring actually
speaks LSP, so "the extension works" is verified rather than assumed. It is the
only test here that starts a process.
"""

import json
import os
import subprocess
import sys
import threading
import time

import pytest

SDK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INTERPRETER = os.path.join(SDK, 'venv', 'bin', 'python')


def _framed(message):
    body = json.dumps(message).encode()
    return b'Content-Length: %d\r\n\r\n' % len(body) + body


class Session:
    def __init__(self, document):
        self.messages = []
        # NOT cwd=SDK. The server is launched by an editor with the folder the
        # USER opened as its working directory, and running it from the SDK
        # directory hid a real failure: `semforge` was importable only because
        # the package happened to sit in the current directory, so the server
        # died instantly for every actual user while this test passed.
        self.process = subprocess.Popen(
            [INTERPRETER if os.path.exists(INTERPRETER) else sys.executable,
             '-m', 'semforge.editor.server'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=os.path.dirname(SDK))
        threading.Thread(target=self._read, daemon=True).start()
        self.document = document

    def send(self, message):
        self.process.stdin.write(_framed(message))
        self.process.stdin.flush()

    def _read(self):
        stream = self.process.stdout
        while True:
            header = b''
            while b'\r\n\r\n' not in header:
                byte = stream.read(1)
                if not byte:
                    return
                header += byte
            length = int(next(line for line in header.decode().split('\r\n')
                              if 'Content-Length' in line).split(':')[1])
            self.messages.append(json.loads(stream.read(length)))

    def wait_for(self, predicate, seconds=45):
        deadline = time.time() + seconds
        while time.time() < deadline:
            found = [m for m in self.messages if predicate(m)]
            if found:
                return found
            time.sleep(0.2)
        return []

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()


@pytest.fixture(scope='module')
def session(request):
    document = os.path.join(SDK, 'tests', 'corpus', 'kms', 'shacl.ttl')
    session = Session(document)
    request.addfinalizer(session.close)

    session.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                  'params': {'processId': os.getpid(),
                             'rootUri': 'file://' + SDK, 'capabilities': {}}})
    assert session.wait_for(lambda m: m.get('id') == 1), 'server did not initialize'
    session.send({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})
    with open(document) as handle:
        text = handle.read()
    session.send({'jsonrpc': '2.0', 'method': 'textDocument/didOpen',
                  'params': {'textDocument': {
                      'uri': 'file://' + document, 'languageId': 'turtle',
                      'version': 1, 'text': text}}})
    return session


def test_the_server_advertises_what_the_extension_relies_on(session):
    reply = [m for m in session.messages if m.get('id') == 1][0]
    capabilities = reply['result']['capabilities']
    for capability in ('hoverProvider', 'definitionProvider',
                       'documentSymbolProvider', 'textDocumentSync'):
        assert capabilities.get(capability), f'{capability} not advertised'


def test_opening_a_shapes_file_publishes_diagnostics(session):
    published = session.wait_for(
        lambda m: m.get('method') == 'textDocument/publishDiagnostics')
    assert published, 'no diagnostics arrived'
    diagnostics = published[0]['params']['diagnostics']
    assert diagnostics
    assert all(d['range']['start']['line'] >= 0 for d in diagnostics)


def test_the_server_starts_from_a_directory_that_is_not_the_sdk(session):
    """The regression guard for the failure this test used to hide.

    An editor starts the server wherever the user's folder is. If `semforge` is
    not installed, the process exits before saying anything -- and a language
    server that exits immediately is indistinguishable from one that found
    nothing to report.
    """
    assert session.process.poll() is None, (
        'the server exited: '
        + session.process.stderr.read().decode()[-400:])


def test_the_diagnostics_carry_the_semforge_source_and_a_kind(session):
    published = session.wait_for(
        lambda m: m.get('method') == 'textDocument/publishDiagnostics')
    sources = {d['source'] for d in published[0]['params']['diagnostics']}
    assert sources
    assert all(s.startswith('semforge (') for s in sources)
    assert any('unexercised' in s for s in sources), \
        'the dead-shape warning should reach the editor'


def test_the_cooked_tree_arrives_over_the_protocol(session):
    """semforge/tree is what the VS Code TreeView renders."""
    session.send({'jsonrpc': '2.0', 'id': 10, 'method': 'semforge/tree',
                  'params': {'uri': 'file://' + session.document}})
    replies = session.wait_for(lambda m: m.get('id') == 10)
    assert replies, 'no reply to semforge/tree'
    result = replies[0]['result']
    assert not result.get('error'), result.get('error')

    labels = {root['label'] for root in result['roots']}
    assert {'Filter', 'Cutter'} <= labels

    def walk(nodes):
        for node in nodes:
            yield node
            yield from walk(node['children'])

    editable = [n for n in walk(result['roots']) if n['editable']]
    assert editable, 'nothing is editable, so the tree is read-only'
    for node in editable:
        assert node['shape'] and node['path'] and node['parameter']


def test_an_edit_over_the_protocol_rewrites_the_file(tmp_path, corpus):
    """The full cooked path: request the tree, edit a node, see the bytes move."""
    import shutil

    package = tmp_path / 'pkg'
    package.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], package / name)
    document = str(package / 'shacl.ttl')

    live = Session(document)
    try:
        live.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                   'params': {'processId': os.getpid(),
                              'rootUri': 'file://' + str(package),
                              'capabilities': {}}})
        assert live.wait_for(lambda m: m.get('id') == 1)
        live.send({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})

        before = open(document).read()
        live.send({'jsonrpc': '2.0', 'id': 11, 'method': 'semforge/setConstraint',
                   'params': {
                       'uri': 'file://' + document,
                       'shape': ('https://industryfusion.github.io/contexts/'
                                 'example/v0/base_shacl/FilterShape'),
                       'path': ['iffBaseEntities:hasStrength'],
                       'parameter': 'sh:minCount', 'value': '0'}})
        replies = live.wait_for(lambda m: m.get('id') == 11)
        assert replies, 'no reply to semforge/setConstraint'
        result = replies[0]['result']
        assert result['ok'], result.get('error')
        assert result['bytesChanged'] == 1

        after = open(document).read()
        assert len(after) == len(before)
        assert sum(1 for a, b in zip(before, after) if a != b) == 1
    finally:
        live.close()


def test_a_refused_edit_reports_instead_of_corrupting(tmp_path, corpus):
    """Structure is not editable through the cooked channel."""
    import shutil

    package = tmp_path / 'pkg'
    package.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], package / name)
    document = str(package / 'shacl.ttl')

    live = Session(document)
    try:
        live.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                   'params': {'processId': os.getpid(),
                              'rootUri': 'file://' + str(package),
                              'capabilities': {}}})
        assert live.wait_for(lambda m: m.get('id') == 1)
        before = open(document).read()

        live.send({'jsonrpc': '2.0', 'id': 12, 'method': 'semforge/setConstraint',
                   'params': {
                       'uri': 'file://' + document,
                       'shape': ('https://industryfusion.github.io/contexts/'
                                 'example/v0/base_shacl/FilterShape'),
                       'path': ['iffBaseEntities:hasStrength'],
                       'parameter': 'sh:or', 'value': 'nonsense'}})
        replies = live.wait_for(lambda m: m.get('id') == 12)
        assert replies and replies[0]['result']['ok'] is False
        assert 'not editable' in replies[0]['result']['error']
        assert open(document).read() == before
    finally:
        live.close()


def test_class_choices_arrive_over_the_protocol_and_respect_the_slot(session):
    """What the picker shows: entity types for a relationship, vocabulary for a value."""
    session.send({'jsonrpc': '2.0', 'id': 20, 'method': 'semforge/choices',
                  'params': {'uri': 'file://' + session.document,
                             'path': ['iffBaseEntities:hasFilter',
                                      'ngsild:hasObject'],
                             'parameter': 'sh:class'}})
    entity = session.wait_for(lambda m: m.get('id') == 20)[0]['result']
    entity_labels = {c['label'] for c in entity['choices']}
    assert 'Filter' in entity_labels and 'MachineState' not in entity_labels

    session.send({'jsonrpc': '2.0', 'id': 21, 'method': 'semforge/choices',
                  'params': {'uri': 'file://' + session.document,
                             'path': ['iffBaseEntities:hasState',
                                      'ngsild:hasValue'],
                             'parameter': 'sh:class'}})
    vocabulary = session.wait_for(lambda m: m.get('id') == 21)[0]['result']
    labels = {c['label'] for c in vocabulary['choices']}
    assert 'MachineState' in labels and 'Filter' not in labels

    # Spelled for the shapes file, not the knowledge file: `default1:` is what
    # knowledge.ttl calls that namespace and shacl.ttl would not resolve it.
    values = {c['value'] for c in vocabulary['choices']}
    assert 'base:MachineState' in values
    assert not any(v.startswith('default') for v in values)


def test_choices_can_be_searched_and_capped_over_the_protocol(session):
    """What the picker does as you type when the ontology is too big to send."""
    session.send({'jsonrpc': '2.0', 'id': 22, 'method': 'semforge/choices',
                  'params': {'uri': 'file://' + session.document,
                             'path': ['iffBaseEntities:hasState',
                                      'ngsild:hasValue'],
                             'parameter': 'sh:class', 'limit': 3}})
    capped = session.wait_for(lambda m: m.get('id') == 22)[0]['result']
    assert len(capped['choices']) == 3
    assert capped['total'] == 12
    assert 'keep typing' in capped['note']
    # The three that survive a cap of three are the ranked ones.
    assert [c['label'] for c in capped['choices']] == \
        ['MachineState', 'Wasteclass', 'Material']

    session.send({'jsonrpc': '2.0', 'id': 23, 'method': 'semforge/choices',
                  'params': {'uri': 'file://' + session.document,
                             'path': ['iffBaseEntities:hasState',
                                      'ngsild:hasValue'],
                             'parameter': 'sh:class', 'search': 'was'}})
    searched = session.wait_for(lambda m: m.get('id') == 23)[0]['result']
    assert [c['label'] for c in searched['choices']] == ['Wasteclass']
    assert searched['total'] == 1


def test_the_shape_for_an_attribute_arrives_over_the_protocol(session):
    """The icon on an example row has to get a file and a line, or it cannot
    jump anywhere."""
    session.send({'jsonrpc': '2.0', 'id': 30, 'method': 'semforge/shapeFor',
                  'params': {'uri': 'file://' + session.document,
                             'entityType': 'iffBaseEntities:Filter',
                             'attribute': 'hasStrength'}})
    found = session.wait_for(lambda m: m.get('id') == 30)[0]['result']
    assert found['ok'], found.get('error')
    assert found['shapeName'] == 'iffBaseShacl:FilterShape'
    assert found['inherited'] is False
    assert found['line'] > 0 and found['file'].endswith('shacl.ttl')

    session.send({'jsonrpc': '2.0', 'id': 31, 'method': 'semforge/shapeFor',
                  'params': {'uri': 'file://' + session.document,
                             'entityType': 'iffBaseEntities:Filter',
                             'attribute': 'hasState'}})
    inherited = session.wait_for(lambda m: m.get('id') == 31)[0]['result']
    assert inherited['shapeName'] == 'iffBaseShacl:MachineShape'
    assert inherited['inherited'] is True

    session.send({'jsonrpc': '2.0', 'id': 32, 'method': 'semforge/shapeFor',
                  'params': {'uri': 'file://' + session.document,
                             'entityType': 'iffBaseEntities:Filter',
                             'attribute': 'hasNothingAtAll'}})
    absent = session.wait_for(lambda m: m.get('id') == 32)[0]['result']
    # exists:False is what tells the client to offer creating one; a bare
    # failure would leave it with nothing to offer.
    assert absent['ok'] is False and absent['exists'] is False


def test_creating_a_missing_shape_writes_the_file(tmp_path, corpus):
    import shutil

    package = tmp_path / 'pkg'
    package.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], package / name)
    document = str(package / 'shacl.ttl')

    live = Session(document)
    try:
        live.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                   'params': {'processId': os.getpid(),
                              'rootUri': 'file://' + str(package),
                              'capabilities': {}}})
        assert live.wait_for(lambda m: m.get('id') == 1)
        live.send({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})

        live.send({'jsonrpc': '2.0', 'id': 33, 'method': 'semforge/shapeFor',
                   'params': {'uri': 'file://' + document,
                              'entityType': 'iffBaseEntities:Filter',
                              'attribute': 'iffBaseEntities:hasBrandNew',
                              'create': True}})
        made = live.wait_for(lambda m: m.get('id') == 33)[0]['result']
        assert made['ok'], made.get('error')
        assert made['how'] == 'created'

        text = open(document).read()
        assert 'hasBrandNew' in text
        # The reported line is the one to open: it has to be the new property.
        assert 'hasBrandNew' in text.splitlines()[made['line'] - 1]
    finally:
        live.close()


def test_value_choices_arrive_over_the_protocol(session):
    """Editing a value offers what the shape allows, in the form the file
    wants."""
    session.send({'jsonrpc': '2.0', 'id': 34, 'method': 'semforge/valueChoices',
                  'params': {'uri': 'file://' + session.document,
                             'entityType': 'iffBaseEntities:Filter',
                             'attribute': 'hasState'}})
    states = session.wait_for(lambda m: m.get('id') == 34)[0]['result']
    labels = [c['label'] for c in states['choices']]
    assert 'state_ON' in labels
    assert all(c['value'].startswith('{"@id": "') for c in states['choices'])

    session.send({'jsonrpc': '2.0', 'id': 35, 'method': 'semforge/valueChoices',
                  'params': {'uri': 'file://' + session.document,
                             'entityType': 'iffBaseEntities:Filter',
                             'attribute': 'hasStrength'}})
    free = session.wait_for(lambda m: m.get('id') == 35)[0]['result']
    assert free['choices'] == []
    assert 'no sh:class' in free['note']


def test_the_examples_tree_carries_the_entity_type_over_the_protocol(session):
    """Serialised or not, this is the difference between the icon working and
    the icon doing nothing."""
    session.send({'jsonrpc': '2.0', 'id': 36, 'method': 'semforge/model',
                  'params': {'uri': 'file://' + session.document}})
    tree = session.wait_for(lambda m: m.get('id') == 36)[0]['result']

    rows = []

    def walk(nodes):
        for node in nodes:
            rows.append(node)
            walk(node.get('children') or [])

    walk(tree['roots'])
    attributes = [r for r in rows if r['kind'] == 'attribute']
    assert attributes
    assert all(r['entityType'] for r in attributes), \
        [r['label'] for r in attributes if not r['entityType']]


def test_the_knowledge_tree_arrives_over_the_protocol(session):
    """The third view: hierarchy, vocabularies, and the locations that connect
    them to the other two."""
    session.send({'jsonrpc': '2.0', 'id': 37, 'method': 'semforge/knowledge',
                  'params': {'uri': 'file://' + session.document}})
    tree = session.wait_for(lambda m: m.get('id') == 37)[0]['result']
    assert not tree.get('error'), tree.get('error')
    assert [r['label'] for r in tree['roots']] == ['Entity types',
                                                   'Vocabulary classes']

    rows = []

    def walk(nodes):
        for node in nodes:
            rows.append(node)
            walk(node.get('children') or [])

    walk(tree['roots'])
    classes = [r for r in rows if r['kind'] == 'class']
    assert len(classes) > 10
    # Both jumps have to survive serialisation: the class in knowledge.ttl and
    # the shape in shacl.ttl.
    assert all(r['definedAt'] for r in classes)
    filters = next(r for r in classes if r['label'] == 'iffBaseEntities:Filter')
    assert filters['shapeAt'].endswith(tuple('0123456789'))
    assert filters['shapeName'].endswith('FilterShape')
    assert any(r['kind'] == 'instance' and r['entity'].startswith('urn:')
               for r in rows)


def test_the_server_says_which_methods_it_has(session):
    """So "the server is older than the extension" is one line in the doctor.

    That state is otherwise invisible: the new icon is there, the request comes
    back method-not-found, and the click does nothing at all.
    """
    session.send({'jsonrpc': '2.0', 'id': 38, 'method': 'semforge/methods',
                  'params': {}})
    reported = session.wait_for(lambda m: m.get('id') == 38)[0]['result']
    for expected in ('semforge/tree', 'semforge/model', 'semforge/knowledge',
                     'semforge/shapeFor', 'semforge/valueChoices'):
        assert expected in reported['methods'], expected
    assert reported['module'].endswith('semforge')
    assert reported['version']


def test_the_outline_symbols_obey_the_clients_containment_rule(session):
    """A selection range not contained in its range makes the client throw.

    It throws on the BATCH, so one bad symbol empties the whole Outline and the
    log says only "provider FAILED" -- which is what a one-line statement did:
    range (L,0)-(L,0) around selectionRange (L,0)-(L,1).
    """
    session.send({'jsonrpc': '2.0', 'id': 39,
                  'method': 'textDocument/documentSymbol',
                  'params': {'textDocument':
                             {'uri': 'file://' + session.document}}})
    symbols = session.wait_for(lambda m: m.get('id') == 39)[0]['result']
    assert symbols

    def position(point):
        return (point['line'], point['character'])

    for symbol in symbols:
        assert symbol['name'].strip(), symbol
        whole, subject = symbol['range'], symbol['selectionRange']
        assert position(whole['start']) <= position(subject['start'])
        assert position(subject['end']) <= position(whole['end']), symbol
        assert position(whole['start']) <= position(whole['end'])


def test_a_package_can_be_created_over_the_protocol(tmp_path, corpus):
    """The editor asks the SDK for the scaffold rather than shelling out.

    A package created by a second code path would drift from the one
    `semforge init` produces, and the drift would show up as "it works from the
    CLI but not from the editor".
    """
    import json as _json

    document = str(corpus.sources['shapes'])
    target = str(tmp_path / 'fresh')

    live = Session(document)
    try:
        live.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                   'params': {'processId': os.getpid(),
                              'rootUri': 'file://' + str(tmp_path),
                              'capabilities': {}}})
        assert live.wait_for(lambda m: m.get('id') == 1)
        live.send({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})

        live.send({'jsonrpc': '2.0', 'id': 40, 'method': 'semforge/init',
                   'params': {'path': target, 'name': 'Fresh Start',
                              'layout': 'grouped'}})
        made = live.wait_for(lambda m: m.get('id') == 40)[0]['result']
        assert made['ok'], made.get('error')
        assert made['violations'] == 0 and made['constraints'] > 0
        assert made['open'].endswith('shacl.ttl')
        assert len(made['files']) >= 8

        # And the server can immediately answer about it, which is the point.
        live.send({'jsonrpc': '2.0', 'id': 41, 'method': 'semforge/tree',
                   'params': {'uri': 'file://' + made['open']}})
        tree = live.wait_for(lambda m: m.get('id') == 41)[0]['result']
        assert tree['roots'], tree.get('error')
        assert any('Machine' in root['label'] for root in tree['roots'])

        live.send({'jsonrpc': '2.0', 'id': 42, 'method': 'semforge/model',
                   'params': {'uri': 'file://' + made['open']}})
        model = live.wait_for(lambda m: m.get('id') == 42)[0]['result']
        sections = {root['label']: root for root in model['roots']}
        assert set(sections) == {'Tests', 'Main'}, list(sections)
        suites = [n['label'] for n in sections['Tests']['children']]
        assert any('test_MachineShape' in label for label in suites), suites
        assert [n['label'] for n in sections['Main']['children']] == \
            ['main.jsonld']

        _json.loads(open(made['files'][1], encoding='utf-8').read())
    finally:
        live.close()


def test_the_project_is_answered_and_a_setting_can_be_written(tmp_path, corpus):
    """The fourth view, over the wire: what the package IS, and changing it.

    The settings are read and written by the SDK, not by the extension: a
    second writer would drift from the one `semforge init` produces, and the
    comments in semforge.yaml are the documentation -- a YAML round-trip in the
    editor layer would quietly delete them.
    """
    import shutil

    target = tmp_path / 'pkg'
    shutil.copytree(os.path.dirname(str(corpus.sources['shapes'])), str(target))
    document = str(target / 'shacl.ttl')

    live = Session(document)
    try:
        live.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                   'params': {'processId': os.getpid(),
                              'rootUri': 'file://' + str(tmp_path),
                              'capabilities': {}}})
        assert live.wait_for(lambda m: m.get('id') == 1)
        live.send({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})

        live.send({'jsonrpc': '2.0', 'id': 50, 'method': 'semforge/project',
                   'params': {'uri': 'file://' + document}})
        card = live.wait_for(lambda m: m.get('id') == 50)[0]['result']
        assert not card.get('error'), card
        sections = {root['label']: root for root in card['roots']}
        assert set(sections) == {'Project', 'Settings', 'Contents'}

        rows = {row['label']: row for row in sections['Project']['children']}
        assert rows['path']['value'] == str(target)
        assert rows['name']['editable']

        live.send({'jsonrpc': '2.0', 'id': 51, 'method': 'semforge/setSetting',
                   'params': {'uri': 'file://' + document,
                              'key': 'name', 'value': 'Cutting cell'}})
        written = live.wait_for(lambda m: m.get('id') == 51)[0]['result']
        assert written['ok'], written.get('error')
        assert written['file'].endswith('semforge.yaml')
        assert written['line'] > 0

        # Asked again, the answer has changed -- the server must not be serving
        # a package it loaded before the write.
        live.send({'jsonrpc': '2.0', 'id': 52, 'method': 'semforge/project',
                   'params': {'uri': 'file://' + document}})
        again = live.wait_for(lambda m: m.get('id') == 52)[0]['result']
        name = {row['label']: row
                for root in again['roots'] if root['label'] == 'Project'
                for row in root['children']}['name']
        assert name['value'] == 'Cutting cell'

        # A key that is not a setting is refused rather than written.
        live.send({'jsonrpc': '2.0', 'id': 53, 'method': 'semforge/setSetting',
                   'params': {'uri': 'file://' + document,
                              'key': 'anything', 'value': 'x'}})
        refused = live.wait_for(lambda m: m.get('id') == 53)[0]['result']
        assert not refused['ok']
    finally:
        live.close()
