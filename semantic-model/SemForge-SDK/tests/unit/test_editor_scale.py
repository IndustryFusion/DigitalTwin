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

"""What the editor derives from a package is derived once per version of it
(issue #991).

Each test names one of the causes the issue found and counts what the old code
did per item -- a classification per entity type, a scan of the shapes text
per attribute, a parse of the model per request or per edit, a validation
inside the SHACL Shapes view -- so that it fails on that code, not only when a
machine happens to be slow. tests/unit/test_scale_e2e.py runs the same flow
through the real language server.
"""

import json
import os
import shutil
from unittest import mock

import pytest
from rdflib import Graph, URIRef
from rdflib.compare import isomorphic

import scale_package
from semforge.package import load

ENTITIES = scale_package.ENTITIES
SHACL = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'


@pytest.fixture
def large(tmp_path):
    """A package with 40 generated types and 120 generated entities."""
    return scale_package.make(str(tmp_path / 'large'), types=40, entities=120)


@pytest.fixture
def root(tmp_path, corpus_path):
    """The kms corpus, examples included, as files of its own."""
    copy = tmp_path / 'pkg'
    shutil.copytree(corpus_path, copy, ignore=shutil.ignore_patterns('.semforge'))
    return str(copy)


def _uri(root):
    return 'file://' + os.path.join(root, 'kms.yaml')


def _counting(monkeypatch, module, name):
    calls = []
    original = getattr(module, name)

    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, name, counted)
    return calls


def _forget(root):
    from semforge.editor import session
    for table in (session._packages, session._stamps, session._previous):
        table.pop(root, None)


def _rewrite(path, change=lambda text: text + '\n'):
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(change(text))


# --- 1. the type picker: one classification, not one per type -------------------

def test_the_type_picker_classifies_the_knowledge_once(large, monkeypatch):
    """`own_shape()` looked every type up by computing all entity types again:
    458 classifications of the knowledge for one picker on the OPC UA demo."""
    from semforge.cooked import choices
    from semforge.editor import views

    _forget(large)
    calls = _counting(monkeypatch, choices, 'classify_classes')
    answer = views.entity_types_feature(None, {'uri': _uri(large)})
    assert 'error' not in answer, answer
    generated = [t for t in answer['types'] if t['iri'].startswith(ENTITIES + 'GenType')]
    assert len(generated) == 40
    assert all(t['ownShape'] == f"{SHACL}{t['label']}Shape" for t in generated)
    assert len(calls) == 1, f'{len(calls)} classifications for one request'

    views.entity_types_feature(None, {'uri': _uri(large)})
    assert len(calls) == 1, 'the second request derived it again'


def test_own_shape_is_the_shape_with_the_most_groups_of_the_type_itself(root):
    """The kept map answers what the scan over every shape answered."""
    from rdflib.namespace import SH

    from semforge.cooked.choices import entity_types
    from semforge.cooked.constrain import own_shape
    from semforge.validate.shapes import class_targets, node_shapes

    package = load(root)
    answered = 0
    for entry in entity_types(package)[0]:
        candidates = [s for s in node_shapes(package.shapes)
                      if entry.iri in {str(t) for t in class_targets(package.shapes, s)}]
        candidates.sort(key=lambda s: (-len(list(package.shapes.objects(s, SH.property))), str(s)))
        expected = str(candidates[0]) if candidates else None
        for name in (entry.iri, entry.term, entry.label):
            assert own_shape(package, name) == expected, (name, expected)
        answered += expected is not None
    assert answered >= 3
    assert own_shape(package, '') is None
    assert own_shape(package, ENTITIES + 'NoSuchType') is None


def test_a_new_shape_is_seen_by_the_kept_types(root):
    """Kept with the graphs, not beside them: the shapes file a new shape is
    written into is a new graph, so the next answer names it."""
    from semforge.cooked.choices import entity_types
    from semforge.cooked.shapes import add_shape
    from semforge.editor import session

    _forget(root)
    before = {t.iri: t for t in entity_types(session.package_for(root))[0]}
    bare = next(iri for iri, t in before.items() if not t.shape)
    made = add_shape(session.package_for(root), 'ScaleNew', 'class', bare, None)
    session.forget(root)
    after = {t.iri: t for t in entity_types(session.package_for(root))[0]}
    assert after[bare].shape.endswith(made['name'].split(':')[-1])


def test_the_entity_root_is_read_once_per_version_of_kms_yaml(root, monkeypatch):
    """And kept apart from the prefix table that reads the same file: sharing
    its cache handed the prefix table {'entityRoot': None}."""
    from semforge.cooked import choices
    from semforge.package.prefixes import names_by_namespace

    reads = _counting(monkeypatch, choices, '_read_entity_root')
    for _ in range(3):
        assert choices.declared_entity_root(root) is None
    assert len(reads) == 1, f'kms.yaml read {len(reads)} times'
    names = names_by_namespace(root)
    assert names and all(isinstance(k, str) and isinstance(v, str) for k, v in names.items())

    config = os.path.join(root, 'kms.yaml')
    _rewrite(config, lambda text: text + '\nentityRoot: iffBaseEntities:Machine\n')
    assert choices.declared_entity_root(root) == URIRef(ENTITIES + 'Machine')
    assert len(reads) == 2, 'the edited kms.yaml was not read again'
    assert names_by_namespace(root) == names
    os.remove(config)
    assert choices.declared_entity_root(root) is None


def test_the_kept_places_follow_an_edit_of_the_shapes(large):
    """The places are kept per shapes graph; an edit that moves a group makes
    a new graph, and the jump goes to the new line."""
    from semforge.cooked.shapelink import find_property_shape
    from semforge.editor import session

    _forget(large)
    before = find_property_shape(session.package_for(large), 'iffBaseEntities:GenType5',
                                 'iffBaseEntities:hasGen5')
    _rewrite(os.path.join(large, 'shacl.ttl'), lambda text: text.replace(
        'iffBaseShacl:GenType5Shape a sh:NodeShape ;',
        '# moved down\n# by two lines\niffBaseShacl:GenType5Shape a sh:NodeShape ;', 1))
    session.forget(large)
    after = find_property_shape(session.package_for(large), 'iffBaseEntities:GenType5',
                                'iffBaseEntities:hasGen5')
    assert after['line'] == before['line'] + 2


def test_the_kept_superclasses_follow_an_edit_of_the_knowledge(large):
    """A type moved under another one is judged by that one's shapes too."""
    from semforge.cooked.shapelink import find_property_shape
    from semforge.editor import session

    _forget(large)
    package = session.package_for(large)
    assert find_property_shape(package, 'iffBaseEntities:GenType8', 'iffBaseEntities:hasGen9') is None
    _rewrite(os.path.join(large, 'knowledge.ttl'), lambda text: text.replace(
        'iffBaseEntities:GenType8 a owl:Class ;\n    rdfs:subClassOf iffBaseEntities:Machine .',
        'iffBaseEntities:GenType8 a owl:Class ;\n    rdfs:subClassOf iffBaseEntities:GenType9 .', 1))
    session.forget(large)
    found = find_property_shape(session.package_for(large), 'iffBaseEntities:GenType8',
                                'iffBaseEntities:hasGen9')
    assert found['shape'] == SHACL + 'GenType9Shape' and found['inherited']


# --- 2. the Knowledge view: the shapes text scanned once ---------------------------

def test_finding_property_shapes_scans_each_shape_once(large, monkeypatch):
    """The Knowledge view asks for every attribute; each question walked every
    node shape and parsed its text again (~800 x 86 on the OPC UA demo)."""
    from semforge.cooked import shapelink
    from semforge.validate.shapes import node_shapes

    package = load(large)
    scans = _counting(monkeypatch, shapelink, 'property_blocks')
    for i in range(40):
        own = shapelink.find_property_shape(package, f'iffBaseEntities:GenType{i}',
                                            f'iffBaseEntities:hasGen{i}')
        assert own['shape'] == f'{SHACL}GenType{i}Shape' and not own['inherited'], own
        assert own['file'].endswith('shacl.ttl') and own['line'] > 1 and own['exists']
        inherited = shapelink.find_property_shape(package, f'iffBaseEntities:GenType{i}',
                                                  'iffBaseEntities:hasState')
        assert inherited['shape'] == SHACL + 'MachineShape' and inherited['inherited']
        assert inherited['slot']
    assert shapelink.find_property_shape(package, 'iffBaseEntities:GenType3',
                                         'iffBaseEntities:hasGen4') is None
    assert len(scans) <= len(list(node_shapes(package.shapes))), f'{len(scans)} scans'


def test_the_knowledge_view_reads_the_loaded_model(large, monkeypatch):
    """Nothing but the model: the loaded graph itself, not a second parse."""
    from semforge.cooked import knowledge

    package = load(large)
    parses = _counting(monkeypatch, Graph, 'parse')
    assert knowledge._data_graph(package) is package.model
    assert parses == []


def test_the_knowledge_view_parses_the_examples_once(root):
    from semforge.cooked import knowledge

    package = load(root)
    graph = knowledge._data_graph(package)
    assert graph is knowledge._data_graph(package), 'parsed again'
    assert any(part is package.model for part in graph.graphs), 'the model is copied'
    assert set(package.model) <= set(graph), 'the model is part of it'
    assert len(graph) > len(package.model), 'and so are the examples'
    triples = list(graph)
    assert len(triples) == len(set(triples)), 'a triple of the model and an example counted twice'

    case = next(p for p in knowledge.example_files(package)
                if os.path.abspath(p) not in {os.path.abspath(m) for m in package.files('model')})
    _rewrite(case)
    assert knowledge._data_graph(package) is not graph, 'an edited example is read again'


def test_the_knowledge_view_scans_the_example_files_once(root, monkeypatch):
    """Where each entity and attribute is written: located once per version of
    the files (3.6 s per request on 9,330 entities), not per request."""
    from semforge.cooked import jsonloc, knowledge

    package = load(root)
    located = _counting(monkeypatch, jsonloc, 'locate')
    first = knowledge._scan_examples(package)
    files = len(located)
    assert files >= 2 and knowledge._scan_examples(package) is first
    assert len(located) == files, 'located again'
    instances, places = first
    assert instances and places
    _rewrite(knowledge.example_files(package)[-1])
    assert knowledge._scan_examples(package) is not first


def test_line_numbers_are_counted_once_per_text():
    from semforge.cooked.tree import _line_counter

    text = json.dumps([{'id': 'urn:a', 'x': 1}], indent=1)
    assert _line_counter(text) is _line_counter(text)
    assert _line_counter(text)(text.index('"x"')) == 4


# --- 3. the SHACL Shapes view: no validation in the request ------------------------

def _verdicts(monkeypatch, state, model=None):
    from semforge.editor import validation
    from semforge.editor.verdicts import State, Verdicts

    verdicts = Verdicts(stamp='s', model=model, cases={}, seconds=0.0) if model else None
    stale = model is not None and state != 'ready'
    monkeypatch.setattr(validation, 'verdicts_for',
                        lambda root: (verdicts, State(state, stale=stale)))


def test_the_shapes_view_answers_while_the_verdicts_are_evaluated(root, monkeypatch):
    import semforge.validate as validate
    from semforge.editor import session, views

    _forget(root)
    session.package_for(root)
    monkeypatch.setattr(session, 'warm', lambda root: None)
    monkeypatch.setattr(validate, 'validate_package', mock.Mock(
        side_effect=AssertionError('the SHACL Shapes view validated in the request')))
    _verdicts(monkeypatch, 'evaluating')

    answer = views.shapes_feature(None, {'uri': _uri(root)})
    assert 'error' not in answer, answer
    assert answer['verdicts']['state'] == 'evaluating' and not answer['cached']
    assert answer['roots'] and not any('violation' in row['detail'] for row in answer['roots'])

    summary = views.shapes_feature(None, {'uri': _uri(root), 'detail': 'summary'})
    assert summary['detail'] == 'summary'


def test_the_shapes_view_counts_from_the_verdicts(root, monkeypatch):
    import semforge.validate as validate
    from semforge.editor import session, views

    _forget(root)
    report = validate.validate_package(session.package_for(root), strict=False)
    failing = {str(v.shape) for v in report.violations}
    assert failing
    monkeypatch.setattr(session, 'warm', lambda root: None)
    monkeypatch.setattr(validate, 'validate_package', mock.Mock(
        side_effect=AssertionError('the SHACL Shapes view validated in the request')))
    _verdicts(monkeypatch, 'ready', report)

    answer = views.shapes_feature(None, {'uri': _uri(root)})
    assert answer['verdicts']['state'] == 'ready'
    counted = {row['shape'] for row in answer['roots'] if 'violation(s)' in row['detail']}
    assert counted == failing & {row['shape'] for row in answer['roots']}

    # While the next run goes, the last counts stay, uncached and said stale,
    # as the pages show them -- not twenty seconds of no counts after a save.
    _verdicts(monkeypatch, 'evaluating', report)
    answer = views.shapes_feature(None, {'uri': _uri(root)})
    assert answer['verdicts'] == dict(answer['verdicts'], state='evaluating', stale=True)
    assert not answer['cached']
    assert {row['shape'] for row in answer['roots'] if 'violation(s)' in row['detail']} == counted


VIEW = {'root': '/pkg', 'roots': [{'kind': 'shape', 'label': 'ns:S', 'shape': 'urn:s', 'iri': 'urn:s',
                                   'detail': '', 'children': []}]}


@pytest.mark.parametrize('answered, notice, root, again', [
    ('evaluating', 'ready', '/pkg', True),       # the counts were pending: drawn with them
    ('ready', 'ready', '/pkg', True),            # a run another view's edit started: once per run
    ('evaluating', 'evaluating', '/pkg', False),  # a run overtaken: nothing new yet
    ('evaluating', 'failed', '/pkg', False),
    ('ready', 'ready', '/other', False),         # another package's verdicts
])
def test_the_shapes_view_is_drawn_again_when_its_verdicts_arrive(tmp_path, answered, notice, root, again):
    from test_rename_followups import _drive

    reply = dict(VIEW, verdicts={'state': answered, 'stale': False})
    scenario = {'replies': {'semforge/shapes': reply}, 'drawTrees': ['semforgeShapes']}
    runs = {}
    for name, notify in (('quiet', []), ('told', [{'method': 'semforge/verdicts',
                                                   'params': {'state': notice, 'root': root}}])):
        (tmp_path / name).mkdir()
        runs[name] = _drive(tmp_path / name, dict(scenario, notify=notify))
        assert runs[name]['errors'] == [], runs[name]['errors']

    def drawn(seen):        # the view's own refreshes; activation fires some too
        return len([e for e in seen['events'] if e['type'] == 'refresh' and e['from'] == 'shapes.js'])
    assert drawn(runs['told']) - drawn(runs['quiet']) == (1 if again else 0)
    if answered == 'evaluating':
        assert runs['quiet']['views']['semforgeShapes'].get('message', '').startswith('⟳ Validating')


def test_the_shapes_view_says_when_its_counts_are_not_current(tmp_path):
    from test_rename_followups import _drive

    reply = dict(VIEW, verdicts={'state': 'failed', 'stale': True, 'error': 'boom'})
    seen = _drive(tmp_path, {'replies': {'semforge/shapes': reply}, 'drawTrees': ['semforgeShapes']})
    assert seen['views']['semforgeShapes'].get('message', '').startswith('⚠ Validation failed')


# --- 4. an edit keeps the model ------------------------------------------------------

def test_an_edit_to_a_shape_keeps_the_model_graph(large):
    from semforge.cooked.shapes import add_shape
    from semforge.editor import session

    _forget(large)
    model = session.package_for(large).model
    add_shape(session.package_for(large), 'KeepModel', 'class', ENTITIES + 'GenType1', None)
    session.forget(large)
    assert session.package_for(large).model is model, 'the model was parsed again'


@pytest.mark.parametrize('changed', ['model-instance.jsonld', 'context.jsonld', 'kms.yaml'])
def test_an_edit_to_what_the_model_means_reads_it_again(large, changed):
    from semforge.editor import session

    _forget(large)
    model = session.package_for(large).model
    _rewrite(os.path.join(large, changed))
    session.forget(large)
    again = session.package_for(large).model
    assert again is not model
    assert len(again) == len(model)


def test_a_descriptor_that_appears_after_the_load_reads_the_model_again(large):
    """Absent at the load is a state too: kms.yaml added later may name
    another context, so the model it was read without is not kept."""
    from semforge.editor import session

    config = os.path.join(large, 'kms.yaml')
    kept = open(config, encoding='utf-8').read()
    os.remove(config)
    _forget(large)
    model = session.package_for(large).model
    with open(config, 'w', encoding='utf-8') as handle:
        handle.write(kept)
    session.forget(large)
    assert session.package_for(large).model is not model


def test_a_save_during_the_load_is_not_taken_for_the_loaded_version(large, monkeypatch):
    """The model saved while it is parsed: what was parsed is the old file, so
    the reload after must read the new one, not keep the old graph."""
    from semforge.editor import session
    from semforge.package import loader

    _forget(large)
    path = os.path.join(large, 'model-instance.jsonld')
    real = loader.load

    def saved_meanwhile(root, reuse=None):
        package = real(root, reuse=reuse)
        _rewrite(path, lambda text: text.replace('"urn:gen:0"', '"urn:gen:saved"', 1))
        return package
    monkeypatch.setattr(loader, 'load', saved_meanwhile)
    import semforge.package as package_module
    monkeypatch.setattr(package_module, 'load', saved_meanwhile)
    first = session.package_for(large)
    monkeypatch.setattr(package_module, 'load', real)
    monkeypatch.setattr(loader, 'load', real)
    assert large not in session._previous
    again = session.package_for(large)
    assert again is not first
    subjects = {str(s) for s in again.model.subjects()}
    assert 'urn:gen:saved' in subjects and 'urn:gen:0' not in subjects


def test_the_verdict_worker_keeps_the_model_across_a_shape_edit(large):
    from semforge.editor.incremental import Session

    worker = Session(load)
    worker.run(large, 'v1')
    model = worker._last[large].package.model
    _rewrite(os.path.join(large, 'shacl.ttl'), lambda text: text.replace(
        'sh:path iffBaseEntities:hasGen3 ;', 'sh:path iffBaseEntities:hasGen3 ;\n            sh:order 3 ;', 1))
    worker.run(large, 'v2')
    assert worker._last[large].package.model is model, 'the worker parsed the model again'

    _rewrite(os.path.join(large, 'model-instance.jsonld'))
    worker.run(large, 'v3')
    assert worker._last[large].package.model is not model


def test_the_files_a_model_means_through(large):
    from semforge.package.loader import model_meaning_files

    files = model_meaning_files(load(large))
    assert [os.path.basename(f) for f in files] == [
        'model-instance.jsonld', 'context.jsonld', 'kms.yaml', 'semforge.yaml']
    assert all(os.path.isabs(f) for f in files)
    assert not os.path.exists(files[-1]), 'named although it is not there'


# --- 5. one @context, processed once --------------------------------------------------

CONTEXT = {'ex': 'http://example.org/', 'value': 'ex:value'}


def _entities(contexts):
    return [{'@context': context, '@id': f'urn:e:{n}', '@type': 'ex:Thing',
             'ex:has': {'value': n}}           # a blank node, as an NGSI-LD attribute is
            for n, context in enumerate(contexts)]


def test_a_shared_context_is_said_once_and_the_triples_stay():
    from semforge.package.loader import hoist_context

    document = _entities([CONTEXT] * 5)
    hoisted = hoist_context(document)
    assert hoisted['@context'] == CONTEXT and len(hoisted['@graph']) == 5
    assert all('@context' not in entity for entity in hoisted['@graph'])
    each, once = Graph(), Graph()
    each.parse(data=json.dumps(document), format='json-ld')
    once.parse(data=json.dumps(hoisted), format='json-ld')
    assert len(each) == 15 and isomorphic(each, once)


@pytest.mark.parametrize('document', [
    _entities([CONTEXT, dict(CONTEXT, other='ex:other')]),     # two contexts
    _entities([CONTEXT])[:1] + [{'@id': 'urn:e:9', '@type': 'ex:Thing'}],   # one without
    _entities([CONTEXT])[0],                                   # not a list
    [],
    _entities([dict(CONTEXT, **{'@propagate': False})] * 2),  # scoped to its entity
])
def test_anything_else_is_parsed_as_it_is(document):
    from semforge.package.loader import hoist_context

    assert hoist_context(document) is document


def test_the_package_load_parses_the_model_with_its_context_once(large, monkeypatch):
    """Cause 5 where it costs: what load() hands rdflib for the model."""
    parsed = []
    real = Graph.parse

    def spy(self, *args, **kwargs):
        if kwargs.get('format') == 'json-ld':
            parsed.append(json.loads(kwargs['data']))
        return real(self, *args, **kwargs)
    monkeypatch.setattr(Graph, 'parse', spy)
    package = load(large)
    assert len(parsed) == 1
    document = parsed[0]
    assert isinstance(document, dict) and '@context' in document
    assert len(document['@graph']) == 8 + 120
    assert not any('@context' in entity for entity in document['@graph'])
    assert len(package.model) > 0


def test_the_loaded_model_is_the_model_parsed_entity_by_entity(large):
    """What the package load builds, against the same documents parsed as
    they are written: the same graph, blank nodes and all."""
    from semforge.package.context import context_config, resolve_model_document
    from semforge.rdfio.relative import BASE, for_rdflib

    package = load(large)
    source = package.files('model')[0]
    document, _ = resolve_model_document(large, source, context_config(large))
    plain = Graph()
    plain.parse(data=json.dumps(for_rdflib(document, source)), format='json-ld', base=BASE)
    assert len(plain) == len(package.model)
    assert isomorphic(plain, package.model)
