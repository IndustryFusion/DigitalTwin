#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Every request the extension sends, to a real server over stdio.

The harness tests stub the server; the unit tests call the cooked layer.
Neither sees the wire: how pygls hands a request's parameters over (a
namedtuple, where a parameter the client left out came back as the tuple's
own `index` method), or a handler that crashes on the shape the client
really sends. This sweep starts the server once, on a copy of the kms
corpus, and sends each `semforge/…` method as the extension sends it --
reads first, then writes, each checked against the files it changes -- and
drives a SPARQL query document through open, change, completion, hover,
formatting, quick fixes and close.
"""

import json
import os
import shutil

import pytest

from test_lsp_protocol import Session

ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
KNOW = 'https://industryfusion.github.io/contexts/example/v0/base_knowledge/'
BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
NGSILD = 'https://uri.etsi.org/ngsi-ld/'
CUTTER = BASE + 'StateOnCutterShape'
WITHOUT = 'test_FilterShape/bad/without-cartridge.jsonld'


@pytest.fixture(scope='module')
def kms(tmp_path_factory, corpus_path):
    target = tmp_path_factory.mktemp('sweep') / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


class Wire:
    def __init__(self, session, kms):
        self.session, self.kms, self.next_id = session, kms, 50000
        self.uri = f'file://{kms}/shacl.ttl'

    def ask(self, method, params=None, with_uri=True):
        self.next_id += 1
        request_id = self.next_id
        body = dict(params or {})
        if with_uri:
            body.setdefault('uri', self.uri)
        self.session.send({'jsonrpc': '2.0', 'id': request_id, 'method': method,
                           'params': body})
        replies = self.session.wait_for(lambda m: m.get('id') == request_id, seconds=120)
        assert replies, f'no reply to {method}'
        assert 'error' not in replies[0], f'{method}: {replies[0]["error"]}'
        return replies[0]['result']

    def ok(self, method, params=None, **kw):
        result = self.ask(method, params, **kw)
        assert isinstance(result, dict), (method, result)
        assert result.get('ok', True) is not False and not result.get('error'), \
            f'{method}: {result.get("error")}'
        return result

    def read(self, name):
        with open(os.path.join(self.kms, name), encoding='utf-8') as handle:
            return handle.read()


@pytest.fixture(scope='module')
def wire(request, kms):
    session = Session(os.path.join(kms, 'shacl.ttl'))
    request.addfinalizer(session.close)
    session.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                  'params': {'processId': os.getpid(), 'rootUri': f'file://{kms}',
                             'capabilities': {}}})
    assert session.wait_for(lambda m: m.get('id') == 1), 'server did not initialize'
    session.send({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})
    return Wire(session, kms)


# --- every read, as the extension sends it ---------------------------------------------------

READS = [
    ('semforge/methods', {}, 'methods'),
    ('semforge/kinds', {}, None),
    ('semforge/tree', {'detail': 'summary'}, 'roots'),
    ('semforge/tree', {'detail': 'full'}, 'roots'),
    ('semforge/model', {'detail': 'summary'}, 'roots'),
    ('semforge/knowledge', {'detail': 'summary'}, 'roots'),
    ('semforge/project', {}, None),
    ('semforge/shapes', {'detail': 'summary'}, 'roots'),
    ('semforge/health', {}, None),
    ('semforge/cacheStatus', {}, None),
    ('semforge/entityTypes', {}, 'types'),
    ('semforge/attributes', {'all': True}, 'attributes'),
    ('semforge/attributeNamespaces', {'domain': ENT + 'Filter'}, None),
    ('semforge/attributeOptions', {'shape': BASE + 'FilterShape'}, 'options'),
    ('semforge/attributePlaces', {'attribute': ENT + 'hasState'}, 'places'),
    ('semforge/attributeRemovalPlan', {'attribute': ENT + 'hasState'}, None),
    ('semforge/choices', {'path': ['iffBaseEntities:hasState', 'ngsild:hasValue'],
                          'parameter': 'sh:class', 'search': None}, 'choices'),
    ('semforge/valueChoices', {'entityType': 'iffBaseEntities:Filter', 'attribute': 'hasCartridge',
                               'relationship': True}, 'others'),
    ('semforge/shapeFor', {'entityType': 'iffBaseEntities:Filter', 'attribute': 'hasState',
                           'create': False}, None),
    ('semforge/typePage', {'entityType': 'iffBaseEntities:Filter'}, 'attributes'),
    ('semforge/shapePage', {'shape': CUTTER}, 'checks'),
    ('semforge/vocabularyPage', {'cls': KNOW + 'MachineState'}, None),
    ('semforge/vocabularyClasses', {}, 'classes'),
    ('semforge/casePage', {'case': WITHOUT}, 'claims'),
    ('semforge/modelPage', {}, 'files'),
    ('semforge/testCaseOptions', {}, 'suites'),
    ('semforge/attributeTestOptions', {'entityType': ENT + 'Filter',
                                       'path': ['iffBaseEntities:hasStrength']}, None),
    ('semforge/mergePlan', {'shape': BASE + 'StateOnFilterShape'}, None),
    ('semforge/deletionPlan', {}, None),
    # The workbench, as its page sends it: no `index` unless it knows one.
    ('semforge/sparqlBench', {'shape': CUTTER}, 'holder'),
    ('semforge/sparqlBench', {'shape': CUTTER, 'source': WITHOUT, 'kind': 'constraint'}, 'focus'),
    ('semforge/sparqlQuery', {'shape': CUTTER, 'holder': 0}, 'query'),
    ('semforge/sparqlRun', {'shape': CUTTER, 'source': '@main',
                            'query': 'SELECT $this WHERE { $this ?p ?o }'}, 'violating'),
    ('semforge/sparqlInspect', {'shape': CUTTER, 'source': '@main',
                                'query': 'SELECT $this WHERE { $this ?p ?o }'}, 'columns'),
]


@pytest.mark.parametrize('method, params, key', READS,
                         ids=[f'{m}-{i}' for i, (m, _, _) in enumerate(READS)])
def test_every_read_answers_on_the_wire(wire, method, params, key):
    result = wire.ok(method, params)
    if key:
        assert key in result, (method, sorted(result))


def test_the_removal_plan_names_the_query_by_its_text(wire):
    query = wire.ok('semforge/sparqlQuery', {'shape': CUTTER, 'holder': 0})['query']
    plan = wire.ok('semforge/sparqlRemovalPlan', {'shape': CUTTER, 'query': query})
    assert plan['last'] and [a['case'] for a in plan['asserts']] == ['filter-off.jsonld']


# --- a Turtle file: hover and go to definition -----------------------------------------------------

def test_hover_and_definition_on_a_shape_file(wire):
    path = os.path.join(wire.kms, 'shacl.ttl')
    text = wire.read('shacl.ttl')
    wire.session.send({'jsonrpc': '2.0', 'method': 'textDocument/didOpen', 'params': {
        'textDocument': {'uri': f'file://{path}', 'languageId': 'turtle', 'version': 1,
                         'text': text}}})
    lines = text.split('\n')
    line = next(i for i, t in enumerate(lines) if 'sh:path iffBaseEntities:hasStrength' in t)
    at = {'textDocument': {'uri': f'file://{path}'},
          'position': {'line': line, 'character': lines[line].index('hasStrength') + 2}}
    hover = wire.ask('textDocument/hover', at, with_uri=False)
    assert hover and 'hasStrength' in json.dumps(hover)
    found = wire.ask('textDocument/definition', at, with_uri=False)
    assert found and found['uri'].endswith('knowledge.ttl'), found


# --- a SPARQL query document, over the protocol -------------------------------------------------

def test_a_query_document_gets_squiggles_completion_hover_formatting_fixes(wire):
    import base64

    ref = {'p': wire.uri, 's': CUTTER, 'h': 0, 'k': 'constraint'}
    uri = 'semforge-sparql:/StateOnCutterShape.rq?' + base64.urlsafe_b64encode(
        json.dumps(ref).encode()).decode().rstrip('=')
    head = f'PREFIX iffBaseEntities: <{ENT}>\nPREFIX ngsild: <{NGSILD}>\n'
    text = head + 'SELECT $this WHERE { $this iffBaseEntities:hasStat [ ngsild:hasValue ?v ] }'
    send = wire.session.send
    send({'jsonrpc': '2.0', 'method': 'textDocument/didOpen', 'params': {'textDocument': {
        'uri': uri, 'languageId': 'sparql', 'version': 1, 'text': text}}})

    def published(test):
        return wire.session.wait_for(lambda m: m.get('method') == 'textDocument/publishDiagnostics'
                                     and m['params']['uri'] == uri and test(m['params']))
    found = published(lambda p: any('did you mean' in d['message'] for d in p['diagnostics']))
    assert found, 'the typo squiggle'

    fixed = text.replace('hasStat ', 'hasState ')
    send({'jsonrpc': '2.0', 'method': 'textDocument/didChange', 'params': {
        'textDocument': {'uri': uri, 'version': 2}, 'contentChanges': [{'text': fixed}]}})
    assert published(lambda p: p['diagnostics'] == []), 'a clean query clears them'

    line = fixed.count('\n')
    column = len(fixed.split('\n')[-1].split('hasState')[0]) + 3
    hover = wire.ask('textDocument/hover', {'textDocument': {'uri': uri},
                                            'position': {'line': line, 'character': column}},
                     with_uri=False)
    assert '**hasState** · Property' in hover['contents']['value']

    partial = head + 'SELECT $this WHERE { $this iffBaseEntities:hasFilter [ '
    send({'jsonrpc': '2.0', 'method': 'textDocument/didChange', 'params': {
        'textDocument': {'uri': uri, 'version': 3}, 'contentChanges': [{'text': partial}]}})
    lines = partial.split('\n')
    completion = wire.ask('textDocument/completion', {
        'textDocument': {'uri': uri},
        'position': {'line': len(lines) - 1, 'character': len(lines[-1])}}, with_uri=False)
    labels = [i['label'] for i in completion['items']]
    assert labels[0] == 'ngsild:hasObject ?filter', labels[:5]

    squashed = head + 'select $this where{$this iffBaseEntities:hasFilter ?f}'
    send({'jsonrpc': '2.0', 'method': 'textDocument/didChange', 'params': {
        'textDocument': {'uri': uri, 'version': 4}, 'contentChanges': [{'text': squashed}]}})
    edits = wire.ask('textDocument/formatting', {'textDocument': {'uri': uri},
                                                 'options': {'tabSize': 4, 'insertSpaces': True}},
                     with_uri=False)
    assert edits and 'SELECT $this\nWHERE {\n' in edits[0]['newText']

    diagnostics = published(lambda p: any(d['code'] == 'variable-node' for d in p['diagnostics']))
    finding = next(d for d in diagnostics[-1]['params']['diagnostics'] if d['code'] == 'variable-node')
    actions = wire.ask('textDocument/codeAction', {
        'textDocument': {'uri': uri}, 'range': finding['range'],
        'context': {'diagnostics': [finding]}}, with_uri=False)
    assert actions[0]['title'] == 'Read the instance: [ ngsild:hasObject ?f ]'

    send({'jsonrpc': '2.0', 'method': 'textDocument/didClose',
          'params': {'textDocument': {'uri': uri}}})
    assert published(lambda p: p['diagnostics'] == [] and True), 'closing clears them'


# --- writes, as the extension sends them, checked on the files ------------------------------------

def test_the_writes_change_exactly_what_they_say(wire):
    # The knowledge: a type, an attribute, a namespace, a vocabulary.
    wire.ok('semforge/addEntityType', {'name': 'Watercutter', 'parent': 'iffBaseEntities:Cutter'})
    assert 'Watercutter a owl:Class' in wire.read('knowledge.ttl')
    wire.ok('semforge/addAttributeTerm', {'name': 'hasHumidity', 'kind': 'Property',
                                          'domain': ENT + 'Cutter', 'label': 'humidity',
                                          'namespace': ENT})
    assert 'hasHumidity' in wire.read('knowledge.ttl')
    wire.ok('semforge/addNamespace', {'prefix': 'sweep', 'namespace': 'https://example.org/sweep/'})
    wire.ok('semforge/removeNamespace', {'prefix': 'sweep', 'force': True})
    made = wire.ok('semforge/addVocabularyClass', {'name': 'SweepColour', 'parent': None})
    wire.ok('semforge/addVocabularyValue', {'cls': made['iri'], 'name': 'red', 'label': 'Red'})
    value = made['iri'].rsplit('/', 1)[0] + '/red'
    wire.ok('semforge/setValueLabel', {'value': value, 'label': 'Rot'})
    assert 'Rot' in wire.read('knowledge.ttl')
    wire.ok('semforge/removeVocabularyValue', {'value': value, 'force': True})

    # The shapes: a shape, its targets, a constraint, an attribute, an override.
    shape = wire.ok('semforge/addShape', {'name': 'SweepShape', 'targetKind': 'class',
                                          'target': ENT + 'Watercutter'})
    wire.ok('semforge/addTarget', {'shape': shape['iri'], 'targetKind': 'subjectsOf',
                                   'target': ENT + 'hasHumidity'})
    wire.ok('semforge/removeTarget', {'shape': shape['iri'], 'targetKind': 'subjectsOf',
                                      'value': ENT + 'hasHumidity'})
    wire.ok('semforge/addAttributeConstraint', {'shape': shape['iri'], 'entityType': None,
                                                'attribute': ENT + 'hasHumidity',
                                                'required': False, 'datatype': None,
                                                'valueClass': None})
    assert 'sh:path iffBaseEntities:hasHumidity' in wire.read('shacl.ttl')
    wire.ok('semforge/setConstraint', {'shape': shape['iri'],
                                       'path': ['iffBaseEntities:hasHumidity'],
                                       'parameter': 'sh:minCount', 'value': '1'})
    wire.ok('semforge/editAttribute', {'shape': shape['iri'],
                                       'path': ['iffBaseEntities:hasHumidity'],
                                       'presence': 'optional'})
    wire.ok('semforge/removeProperty', {'shape': shape['iri'],
                                        'path': ['iffBaseEntities:hasHumidity']})
    assert 'sh:path iffBaseEntities:hasHumidity' not in wire.read('shacl.ttl')

    # SPARQL: a constraint written, saved, removed.
    added = wire.ok('semforge/addSparqlConstraint', {'shape': shape['iri'], 'message': 'sweep'})
    query = wire.ok('semforge/sparqlQuery', {'shape': shape['iri'],
                                             'holder': added['index']})['query']
    wire.ok('semforge/sparqlSave', {'shape': shape['iri'], 'index': added['index'],
                                    'query': query + '\n# saved\n', 'expected': query})
    assert '# saved' in wire.read('shacl.ttl')
    wire.ok('semforge/sparqlRemove', {'shape': shape['iri'], 'holder': added['index'],
                                      'expected': query + '\n# saved\n', 'dropAsserts': False})
    assert '# saved' not in wire.read('shacl.ttl')

    # The data and the tests.
    wire.ok('semforge/addEntity', {'file': os.path.join(wire.kms, 'model-instance.jsonld'),
                                   'id': 'urn:watercutter:1',
                                   'entityType': 'iffBaseEntities:Watercutter'})
    assert 'urn:watercutter:1' in wire.read('model-instance.jsonld')
    wire.ok('semforge/addTestCase', {'suite': 'test_sweep', 'expect': 'valid', 'start': 'empty',
                                     'source': '', 'name': 'first'})
    assert os.path.exists(os.path.join(wire.kms, 'examples', 'test_sweep', 'good',
                                       'first.jsonld'))
    page = wire.ok('semforge/casePage', {'case': WITHOUT})
    unasserted = page['unasserted'][0]
    wire.ok('semforge/addAssert', {'case': WITHOUT, 'constraint': unasserted['constraint'],
                                   'resource': unasserted['resource']})

    # The package itself.
    wire.ok('semforge/rescan', {})
    wire.ok('semforge/clearCache', {'contexts': False})
    fresh = os.path.join(os.path.dirname(wire.kms), 'fresh')
    # As init.js sends it: a path, no package uri (there is no package yet).
    wire.ok('semforge/init', {'path': fresh, 'name': 'Fresh',
                              'namespace': 'https://example.org/fresh/', 'layout': 'flat'},
            with_uri=False)
    assert os.path.exists(os.path.join(fresh, 'shacl.ttl'))

    # And it all still loads and validates.
    assert wire.ok('semforge/tree', {'detail': 'full'})['roots']


def test_more_writes_data_tests_merge_override_removal(wire):
    """Runs after the first write test: Watercutter, SweepShape and
    urn:watercutter:1 exist."""
    model = os.path.join(wire.kms, 'model-instance.jsonld')

    # Data: a value, an attribute, an observation.
    wire.ok('semforge/setValue', {'entity': 'urn:filter:1', 'file': model, 'value': '0.42',
                                  'path': ['iffBaseEntities:hasStrength', 0, 'value']})
    assert '0.42' in wire.read('model-instance.jsonld')
    wire.ok('semforge/addAttribute', {'entity': 'urn:watercutter:1', 'file': model,
                                      'name': 'iffBaseEntities:hasHumidity', 'kind': 'Property',
                                      'value': '42', 'under': None, 'underDataset': None})
    assert 'hasHumidity' in wire.read('model-instance.jsonld')
    wire.ok('semforge/addObservation', {'entity': 'urn:filter:1', 'file': model,
                                        'attributePath': ['iffBaseEntities:hasStrength'],
                                        'datasetId': None, 'value': '0.5',
                                        'observedAt': '2030-01-01T00:00:00.000Z'})
    assert '2030-01-01T00:00:00.000Z' in wire.read('model-instance.jsonld')

    # Tests: one for an attribute, one for a SPARQL constraint.
    offered = wire.ok('semforge/attributeTestOptions', {'entityType': ENT + 'Filter',
                                                        'path': ['iffBaseEntities:hasStrength']})
    purpose = offered['options'][0]['purpose']
    made = wire.ok('semforge/newAttributeTest', {'entityType': ENT + 'Filter',
                                                 'path': ['iffBaseEntities:hasStrength'],
                                                 'purpose': purpose, 'name': 'sweep-strength'})
    assert os.path.exists(made['file'])
    case = wire.ok('semforge/newCase', {'shape': CUTTER, 'name': 'sweep-case'})
    assert os.path.exists(case['file'])

    # Shapes: a second shape on the same type, merged into the first.
    sweep = wire.ok('semforge/shapes', {'detail': 'full'})
    # A new shape carries a random part: SweepShape-3f9a1c2e.
    first = next(r['shape'] for r in sweep['roots'] if '/SweepShape-' in r['shape'])
    second = wire.ok('semforge/addShape', {'name': 'SweepTwoShape', 'targetKind': 'class',
                                           'target': ENT + 'Watercutter'})
    plan = wire.ok('semforge/mergePlan', {'shape': second['iri']})
    assert first in [c['iri'] for c in plan['candidates']]
    wire.ok('semforge/mergeShape', {'shape': second['iri'], 'into': first})
    assert 'SweepTwoShape' not in wire.read('shacl.ttl')

    # An inherited constraint made stricter on the subtype's own shape.
    page = wire.ok('semforge/typePage', {'entityType': ENT + 'Watercutter'})
    row = next(r for r in page['attributes'] for p in r.get('parameters', [])
               if r.get('inherited') and p['parameter'] == 'sh:minCount' and p['value'] == '0')
    parameter = next(p for p in row['parameters'] if p['parameter'] == 'sh:minCount')
    wire.ok('semforge/override', {'targetShape': first, 'path': parameter['path'],
                                  'parameter': 'sh:minCount', 'inheritedValue': '0',
                                  'value': '1', 'force': False})

    # An attribute deleted: its declaration and its uses.
    plan = wire.ok('semforge/attributeRemovalPlan', {'attribute': ENT + 'hasHumidity'})
    wire.ok('semforge/removeAttribute', {'attribute': plan.get('iri', ENT + 'hasHumidity'),
                                         'force': True, 'declarationOnly': False})
    assert 'hasHumidity' not in wire.read('knowledge.ttl')
    assert 'hasHumidity' not in wire.read('model-instance.jsonld')
    assert wire.ok('semforge/tree', {'detail': 'full'})['roots']


def test_renames_on_the_wire(wire):
    """Rename… as the extension sends it: a shape with its suite, a case and a
    suite, each checked on the files -- then named back, so nothing after
    this test sees a different package."""
    shape = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnCutterShape'
    plan = wire.ok('semforge/renameShapePlan', {'shape': shape, 'name': 'SweepRenamedShape'})
    assert plan['suite']['free'] and plan['asserts']
    done = wire.ok('semforge/renameShape', {'shape': shape, 'name': 'SweepRenamedShape',
                                            'suite': True})
    # The shape had no random part: the rename gives it one, and keeps it.
    renamed = done['newName']
    assert renamed.startswith('SweepRenamedShape-')
    assert f'iffBaseShacl:{renamed}' in wire.read('shacl.ttl')
    assert 'StateOnCutterShape' not in wire.read('shacl.ttl')
    examples = os.path.join(wire.kms, 'examples')
    folder = done['suiteMoved']
    assert folder == f'test_{renamed}' and os.path.isdir(os.path.join(examples, folder))
    case = wire.ok('semforge/renameCase', {'case': f'{folder}/bad/filter-off.jsonld',
                                           'name': 'sweep-off'})
    assert os.path.exists(case['file'])
    suite = wire.ok('semforge/renameSuite', {'suite': folder, 'name': 'sweep'})
    assert os.path.isdir(suite['folder'])
    # And back -- to its name; the random part stays.
    wire.ok('semforge/renameSuite', {'suite': 'sweep', 'name': folder})
    wire.ok('semforge/renameCase', {'case': f'{folder}/bad/sweep-off.jsonld',
                                    'name': 'filter-off'})
    back = wire.ok('semforge/renameShape', {'shape': done['newIri'], 'name': 'StateOnCutterShape',
                                            'suite': True})
    assert back['newName'] == 'StateOnCutterShape' + renamed[len('SweepRenamedShape'):]
    assert f'iffBaseShacl:{back["newName"]}' in wire.read('shacl.ttl')
    assert os.path.isdir(os.path.join(examples, f'test_{back["newName"]}'))


def test_delete_on_the_wire(wire):
    """Delete… as the extension sends it, on the shape this sweep made --
    last, since nothing after it may need that shape."""
    sweep = wire.ok('semforge/shapes', {'detail': 'full'})
    shape = next(r['shape'] for r in sweep['roots'] if '/SweepShape-' in r['shape'])
    plan = wire.ok('semforge/deleteShapePlan', {'shape': shape})
    assert plan['cases'] == []
    done = wire.ok('semforge/deleteShape', {'shape': shape, 'asserts': True, 'cases': True})
    assert done['casesRemoved'] == []
    assert f'{shape.rsplit("/", 1)[-1]} a sh:NodeShape' not in wire.read('shacl.ttl')
    again = wire.ask('semforge/deleteShapePlan', {'shape': shape})
    assert not again['ok'] and 'not a node shape' in again['error']
