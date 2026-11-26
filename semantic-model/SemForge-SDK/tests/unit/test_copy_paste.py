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

"""Copy an entity, or it and its children, and paste it into a test case."""

import html
import json
import os
import re
import shutil
import subprocess

import pytest

from semforge.cooked.casepage import build_case_page, build_model_page
from semforge.cooked.examples import _document_id, copy_entities, paste_entities
from semforge.editor import edits
from semforge.errors import PackageError
from semforge.expect.store import compose, load_expectations
from semforge.package import load

from test_casepage import SRC
from test_tree_clicks import _drive

CASE = 'test_FilterShape/bad/without-cartridge.jsonld'


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False, ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _docs(kms, path=os.path.join('examples', CASE)):
    with open(os.path.join(kms, path)) as handle:
        return json.load(handle)


def _store(kms, docs, path=os.path.join('examples', CASE)):
    with open(os.path.join(kms, path), 'w') as handle:
        json.dump(docs, handle)


def _ids(kms):
    return [d['id'] for d in _docs(kms)]


def _copy(kms, entity, **kw):
    return copy_entities(load(kms), entity, **kw)['content']


def _both(one, other):
    return dict(one, entities=one['entities'] + other['entities'])


def _with(content, **item):
    return dict(content, entities=[dict(content['entities'][0], **item)])


def test_one_entity_alone_and_the_model_stays(kms):
    before, model = _ids(kms), _docs(kms, 'model-instance.jsonld')
    taken = _copy(kms, 'urn:filter:1')
    plan = paste_entities(load(kms), taken, CASE, check=True)
    assert _ids(kms) == before and plan['pasted'] == ['urn:filter:1'] and not plan['present']
    paste_entities(load(kms), taken, CASE)
    assert _ids(kms) == before + ['urn:filter:1']
    assert _docs(kms)[-1] == next(d for d in model if d['id'] == 'urn:filter:1')
    assert _docs(kms, 'model-instance.jsonld') == model
    example = next(e for e in load_expectations(kms).examples if e.path == CASE)
    assert len(compose(load(kms), example)), 'it still loads'


BASE = 'https://industryfusion.github.io/contexts/ontology/v0/base/'


def _typed(kms, **references):
    """The kms with a reference type on relationships of the shapes."""
    from rdflib import Graph, URIRef
    from rdflib.namespace import SH

    path = os.path.join(kms, 'shacl.ttl')
    graph = Graph().parse(path)
    for path_iri in set(graph.objects(None, SH.path)):
        name = str(path_iri).split('/')[-1].split('#')[-1]
        if name in references:
            for shape in set(graph.subjects(SH.path, path_iri)):
                graph.add((shape, URIRef(BASE + 'hasReferenceType'), URIRef(references[name])))
    graph.serialize(path, format='turtle')


UA = 'http://opcfoundation.org/UA/'


def test_the_subtree_is_the_children_and_theirs(kms):
    assert copy_entities(load(kms), 'urn:plasmacutter:1', subtree=True)['copied'] == ['urn:plasmacutter:1']
    _typed(kms, hasFilter=UA + 'HasComponent', hasCartridge=UA + 'HasOrderedComponent')
    done = copy_entities(load(kms), 'urn:plasmacutter:1', subtree=True)
    assert done['copied'] == ['urn:plasmacutter:1', 'urn:filter:1', 'urn:cartridge:1']
    assert 'urn:workpiece:1' in done['left'], 'pointed at, and no child'
    assert paste_entities(load(kms), done['content'], CASE)['pasted'] == done['copied']
    assert copy_entities(load(kms), 'urn:plasmacutter:1')['copied'] == ['urn:plasmacutter:1']


def test_a_reference_that_is_no_child_is_not_followed(kms):
    _typed(kms, hasFilter=UA + 'Organizes', hasCartridge=UA + 'HasComponent')
    assert copy_entities(load(kms), 'urn:plasmacutter:1', subtree=True)['copied'] == ['urn:plasmacutter:1']
    assert copy_entities(load(kms), 'urn:filter:1', subtree=True)['copied'] == ['urn:filter:1', 'urn:cartridge:1']


def test_a_companion_s_own_child_reference_is_followed(kms):
    _typed(kms, hasFilter='https://x/HasPart')
    with open(os.path.join(kms, 'knowledge.ttl'), 'a') as handle:
        handle.write('''
<https://x/HasPart> <http://www.w3.org/2000/01/rdf-schema#subPropertyOf> <https://x/HasMine> .
<https://x/HasMine> <http://www.w3.org/2000/01/rdf-schema#subPropertyOf> <http://opcfoundation.org/UA/HasChild> .
''')
    done = copy_entities(load(kms), 'urn:plasmacutter:1', subtree=True)
    assert done['copied'] == ['urn:plasmacutter:1', 'urn:filter:1']


def _relate(kms, entity, name, target):
    docs = _docs(kms, 'model-instance.jsonld')
    next(d for d in docs if d['id'] == entity)[name] = {'type': 'Relationship', 'object': target}
    _store(kms, docs, 'model-instance.jsonld')


def test_what_the_type_does_not_declare_another_shape_says(kms):
    docs = _docs(kms, 'model-instance.jsonld')
    name = next(k for k in next(d for d in docs if d['id'] == 'urn:filter:1') if k.endswith('hasCartridge'))
    _relate(kms, 'urn:workpiece:1', name, 'urn:cartridge:1')
    _typed(kms, hasCartridge=UA + 'HasComponent')
    done = copy_entities(load(kms), 'urn:workpiece:1', subtree=True)
    assert done['copied'] == ['urn:workpiece:1', 'urn:cartridge:1'] and not done['assumed'], 'two point at it'


def test_what_no_shape_declares_the_data_says(kms):
    docs = _docs(kms, 'model-instance.jsonld')
    _store(kms, docs + [{'id': 'urn:new:1', 'type': docs[0]['type'], '@context': docs[0]['@context']}],
           'model-instance.jsonld')
    _relate(kms, 'urn:workpiece:1', 'iffBaseEntities:holdsNew', 'urn:new:1')
    _relate(kms, 'urn:workpiece:1', 'iffBaseEntities:sees', 'urn:cartridge:1')
    assert copy_entities(load(kms), 'urn:workpiece:1', subtree=True)['copied'] == ['urn:workpiece:1'], 'no OPC UA'
    _typed(kms, hasFilter=UA + 'HasComponent')
    done = copy_entities(load(kms), 'urn:workpiece:1', subtree=True)
    assert done['copied'] == ['urn:workpiece:1', 'urn:new:1'] and done['assumed'] == ['urn:new:1']
    assert 'urn:cartridge:1' in done['left'], 'its filter points at it too'
    _relate(kms, 'urn:new:1', 'iffBaseEntities:back', 'urn:workpiece:1')
    assert len(copy_entities(load(kms), 'urn:workpiece:1', subtree=True)['copied']) == 2, 'a way back ends'


def test_declared_by_the_type_without_a_reference_type_is_no_child(kms):
    """The type's own shape decides, even when another names a reference type."""
    with open(os.path.join(kms, 'shacl.ttl'), 'a') as handle:
        handle.write(f'''
<https://x/Other> a <http://www.w3.org/ns/shacl#NodeShape> ; <http://www.w3.org/ns/shacl#property> [
  <http://www.w3.org/ns/shacl#path> {_iri(kms, 'hasFilter')} ; <{BASE}hasReferenceType> <{UA}HasComponent> ] .
''')
    done = copy_entities(load(kms), 'urn:plasmacutter:1', subtree=True)
    assert done['copied'] == ['urn:plasmacutter:1'] and 'urn:filter:1' in done['left']


def _iri(kms, name):
    from rdflib import Graph
    from rdflib.namespace import SH

    return next(p.n3() for p in Graph().parse(os.path.join(kms, 'shacl.ttl')).objects(None, SH.path)
                if str(p).endswith(name))


@pytest.mark.parametrize('connective', [
    'sh:or ( [ sh:property _:p ] [ sh:nodeKind sh:IRI ] )', 'sh:xone ( [ sh:nodeKind sh:IRI ] _:p )',
    'sh:and ( [ sh:node <https://x/Inner> ] )', 'sh:node <https://x/Inner>',
    # Shapes that lead back to each other, and lists that do, or stop short.
    'sh:node <https://x/Inner>, <https://x/Outer>',
    'sh:or _:loop', 'sh:or _:short'])
def test_where_a_shape_says_the_reference_type(kms, connective):
    _relate(kms, 'urn:workpiece:1', 'iffBaseEntities:holdsNew', 'urn:cartridge:1')
    path = _iri(kms, 'hasFilter').replace('hasFilter', 'holdsNew')
    workpiece = next(d for d in _docs(kms, 'model-instance.jsonld') if d['id'] == 'urn:workpiece:1')
    kind = workpiece['type'].split(':')[-1]
    with open(os.path.join(kms, 'shacl.ttl'), 'a') as handle:
        handle.write(f'''
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
<https://x/Outer> a sh:NodeShape ; sh:targetClass {path.replace('holdsNew', kind)} ; {connective} .
<https://x/Inner> a sh:NodeShape ; sh:node <https://x/Outer> ; sh:property _:p .
_:p sh:path {path} ; <{BASE}hasReferenceType> <{UA}HasComponent> .
_:loop rdf:first [ sh:property _:p ] ; rdf:rest _:loop .
_:short rdf:first _:p .
[] sh:path [ sh:inversePath {path} ] ; <{BASE}hasReferenceType> <{UA}Organizes> .
''')
    assert copy_entities(load(kms), 'urn:workpiece:1', subtree=True)['copied'] == \
        ['urn:workpiece:1', 'urn:cartridge:1']


def test_a_child_of_a_sub_attribute(kms):
    _typed(kms, hasFilter=UA + 'HasComponent')
    docs = _docs(kms, 'model-instance.jsonld')
    entity = next(d for d in docs if d['id'] == 'urn:workpiece:1')
    entity['iffBaseEntities:mounted'] = {
        'type': 'Property', 'value': 1,
        'iffBaseEntities:hasFilter': {'type': 'Relationship', 'object': 'urn:filter:1'}}
    _store(kms, docs, 'model-instance.jsonld')
    assert copy_entities(load(kms), 'urn:workpiece:1', subtree=True)['copied'] == ['urn:workpiece:1', 'urn:filter:1']


def test_what_only_the_data_says_and_nothing_defines_is_left(kms):
    _typed(kms, hasFilter=UA + 'HasComponent')
    _relate(kms, 'urn:workpiece:1', 'iffBaseEntities:sees', 'urn:elsewhere:1')
    done = copy_entities(load(kms), 'urn:workpiece:1', subtree=True)
    assert not done['missing'] and 'urn:elsewhere:1' in done['left']


def test_data_that_goes_round_in_blank_nodes_ends(kms):
    from rdflib import BNode, Graph, URIRef

    from semforge.cooked.hierarchy import HAS_OBJECT, Hierarchy, pointers

    graph, one, other = Graph(), BNode(), BNode()
    entity, name, target = (URIRef(f'urn:{n}') for n in ('e', 'name', 't'))
    for triple in ((entity, name, one), (one, name, other), (other, name, one), (other, HAS_OBJECT, target)):
        graph.add(triple)
    assert pointers(graph) == {target: {entity}}
    assert Hierarchy(load(kms)).relationships(graph, entity) == {target: None}


def test_one_the_main_model_points_at_too_is_shared(kms):
    """From a case: what else points at it is looked for where it is written."""
    _typed(kms, hasFilter=UA + 'HasComponent')
    docs = _docs(kms)
    docs[0]['iffBaseEntities:sees'] = {'type': 'Relationship', 'object': 'urn:cartridge:1'}
    _store(kms, docs)
    done = copy_entities(load(kms), docs[0]['id'], file=os.path.join(kms, 'examples', CASE), subtree=True)
    assert 'urn:cartridge:1' in done['left'], 'the model has its own filter point at it'


def test_a_circle_of_children_ends(kms):
    _typed(kms, hasFilter=UA + 'HasComponent', hasCartridge=UA + 'HasComponent')
    docs = _docs(kms, 'model-instance.jsonld')
    cutter = next(d for d in docs if d['id'] == 'urn:plasmacutter:1')
    key = next(k for k in cutter if k.endswith('hasFilter'))
    cutter[key] = {'type': 'Relationship', 'object': 'urn:plasmacutter:1'}
    _store(kms, docs, 'model-instance.jsonld')
    assert copy_entities(load(kms), 'urn:plasmacutter:1', subtree=True)['copied'] == ['urn:plasmacutter:1']


def test_a_child_that_is_written_nowhere_is_said(kms):
    _typed(kms, hasCartridge=UA + 'HasComponent')
    docs = _docs(kms, 'model-instance.jsonld')
    entity = next(d for d in docs if d['id'] == 'urn:filter:1')
    key = next(k for k in entity if k.endswith('hasCartridge'))
    entity[key] = {'type': 'Relationship', 'object': 'urn:no'}
    _store(kms, docs, 'model-instance.jsonld')
    assert copy_entities(load(kms), 'urn:filter:1', subtree=True)['missing'] == ['urn:no']


def test_an_opc_ua_package_s_own_hierarchy(corpus_path, tmp_path):
    """Its ids are relative, its relationships' reference types are the package's own."""
    source = os.path.join(os.path.dirname(corpus_path), 'opcua-pumps')
    package = load(shutil.copytree(source, str(tmp_path / 'pumps'), ignore=shutil.ignore_patterns('.semforge')))
    by_type = {d['type'].split(':')[-1]: d['id'] for d in _docs(package.path, 'model-instance.jsonld')}
    pump = copy_entities(package, by_type['PumpType'], subtree=True)
    assert sorted(pump['copied']) == sorted(by_type.values()) and not pump['missing'] and not pump['left']
    ports = copy_entities(package, by_type['PortsGroupType'], subtree=True)
    assert ports['copied'] == [by_type[t] for t in ('PortsGroupType', 'DrivePortType', 'DriveMeasurementsType')]
    case = next(e.path for e in load_expectations(package.path).examples)
    assert paste_entities(package, ports['content'], case)['pasted'] == ports['copied']


def test_what_is_pasted_is_what_it_was_when_copied(kms):
    taken, model = _copy(kms, 'urn:filter:1'), _docs(kms, 'model-instance.jsonld')
    was = next(d for d in model if d['id'] == 'urn:filter:1')
    _store(kms, [d for d in model if d['id'] != 'urn:filter:1'], 'model-instance.jsonld')
    paste_entities(load(kms), taken, CASE)
    assert _docs(kms)[-1] == was
    with pytest.raises(PackageError, match='any more'):
        copy_entities(load(kms), 'urn:filter:1')


def test_one_the_case_has_is_replaced_in_place_only_when_asked(kms):
    taken = _copy(kms, 'urn:filter:1')
    other = {'iffBaseEntities:hasStrength': {'type': 'Property', 'value': 1}}
    changed = [dict(taken['entities'][0]['document'], **other)] + _docs(kms)
    _store(kms, changed)
    both = _both(taken, _copy(kms, 'urn:workpiece:1'))
    plan = paste_entities(load(kms), both, CASE, check=True)
    assert plan['present'] == ['urn:filter:1'] and plan['pasted'] == ['urn:workpiece:1']
    paste_entities(load(kms), both, CASE)
    assert _docs(kms)[0] == changed[0] and _ids(kms)[-1] == 'urn:workpiece:1', 'the other one only'
    paste_entities(load(kms), both, CASE, replace=True)
    assert _docs(kms)[0] == taken['entities'][0]['document'] and _ids(kms).count('urn:filter:1') == 1


def test_pasted_twice_changes_nothing(kms):
    taken = _copy(kms, 'urn:filter:1')
    paste_entities(load(kms), taken, CASE)
    path = os.path.join(kms, 'examples', CASE)
    stamp = os.stat(path).st_mtime_ns
    done = paste_entities(load(kms), taken, CASE, replace=True)
    assert done['same'] == ['urn:filter:1'] and not done['pasted'] and os.stat(path).st_mtime_ns == stamp


def test_one_a_case_includes_is_not_written_twice(kms):
    case = next(e for e in load_expectations(kms).examples if any('cartridge-fresh' in i for i in e.include))
    taken = _both(_copy(kms, 'urn:cartridge:1'), _copy(kms, 'urn:filter:9', file=os.path.join(kms, 'examples', CASE)))
    done = paste_entities(load(kms), taken, case.path, replace=True)
    assert done['included'] == ['urn:cartridge:1'] and done['pasted'] == ['urn:filter:9']


def test_from_another_case_with_what_it_includes(kms):
    case = next(e for e in load_expectations(kms).examples if any('cartridge-fresh' in i for i in e.include))
    source = os.path.join(kms, 'examples', case.path)
    entity = next(d['id'] for d in _docs(kms, os.path.join('examples', case.path)))
    _typed(kms, hasCartridge=UA + 'HasComponent')
    done = copy_entities(load(kms), entity, file=source, subtree=True)
    assert 'urn:cartridge:1' in done['copied']
    assert done['content']['entities'][-1]['from'].startswith('examples'), 'the included one, not the model\'s'
    included = os.path.join(kms, 'examples', next(i for i in case.include if 'cartridge-fresh' in i))
    assert copy_entities(load(kms), 'urn:cartridge:1', file=included, subtree=True)['copied'] == ['urn:cartridge:1']
    own = copy_entities(load(kms), 'urn:filter:9', file=os.path.join(kms, 'examples', CASE))
    assert paste_entities(load(kms), own['content'], case.path)['pasted'] == ['urn:filter:9']


def test_what_is_refused(kms, tmp_path):
    taken = _copy(kms, 'urn:filter:1')
    before = _docs(kms)
    for content, case, why in (
            (taken, 'no.jsonld', 'not a declared'),
            (dict(taken, entities=[]), CASE, 'nothing'),
            (None, CASE, 'not a copy'), ([], CASE, 'not a copy'), ({'entities': {}}, CASE, 'not a copy'),
            (dict(taken, entities=['x']), CASE, 'not a copy'),
            (_with(taken, document=[]), CASE, 'not a copy'), (_with(taken, **{'from': None}), CASE, 'not a copy'),
            (dict(taken, package=str(tmp_path)), CASE, 'another package'),
            (_with(taken, **{'from': str(tmp_path)}), CASE, 'a folder of this package'),
            (_with(taken, **{'from': 'examples/../..'}), CASE, 'a folder of this package'),
            (_with(taken, document={'type': 'T'}), CASE, 'without an id'),
            (_both(taken, taken), CASE, 'twice')):
        with pytest.raises(PackageError, match=why):
            paste_entities(load(kms), content, case)
    for entity, file in (('', None), ('urn:none', None)):
        with pytest.raises(PackageError, match='any more'):
            copy_entities(load(kms), entity, file=file)
    outside = tmp_path / 'other.jsonld'
    outside.write_text(json.dumps(before))
    for file in (str(outside), os.path.join(kms, 'context.jsonld')):
        with pytest.raises(PackageError, match='of this package'):
            copy_entities(load(kms), before[0]['id'], file=file)
    assert _docs(kms) == before


def test_pasted_after_the_package_was_loaded_again_and_not_in_another(kms, tmp_path):
    taken = _copy(kms, 'urn:filter:1')
    other = shutil.copytree(kms, str(tmp_path / 'other'))
    with pytest.raises(PackageError, match='another package'):
        paste_entities(load(other), taken, CASE)
    assert 'urn:filter:1' not in _ids(other)
    paste_entities(load(kms), taken, CASE)


def test_a_package_of_links_is_still_one_package(corpus_path, tmp_path):
    """The corpus' files are links to another folder; so may a package's be."""
    root = tmp_path / 'linked'
    shutil.copytree(corpus_path, root, symlinks=False, ignore=shutil.ignore_patterns('.semforge'))
    data = tmp_path / 'data'
    data.mkdir()
    for name in ('model-instance.jsonld', 'examples'):
        shutil.move(str(root / name), str(data / name))
        os.symlink(data / name, root / name)
    taken = _copy(str(root), 'urn:filter:1')
    assert taken['entities'][0]['from'] == '.'
    paste_entities(load(str(root)), taken, CASE)
    assert 'urn:filter:1' in _ids(str(root)) and (root / 'examples').is_symlink()


def test_a_linked_case_file_stays_a_link(kms, tmp_path):
    path = os.path.join(kms, 'examples', CASE)
    real = str(tmp_path / 'case.jsonld')
    shutil.move(path, real)
    os.symlink(real, path)
    os.chmod(real, 0o640)
    paste_entities(load(kms), _copy(kms, 'urn:filter:1'), CASE)
    assert os.path.islink(path) and 'urn:filter:1' in _ids(kms) and os.stat(real).st_mode & 0o777 == 0o640


def test_a_failed_write_leaves_the_case_as_it_was(kms, monkeypatch):
    taken, path = _copy(kms, 'urn:filter:1'), os.path.join(kms, 'examples', CASE)
    before, beside = open(path).read(), sorted(os.listdir(os.path.dirname(path)))

    def full(*args):
        raise OSError('disk full')
    monkeypatch.setattr(os, 'replace', full)
    with pytest.raises(OSError):
        paste_entities(load(kms), taken, CASE)
    assert open(path).read() == before and sorted(os.listdir(os.path.dirname(path))) == beside


def test_the_order_of_keys_is_no_difference_but_a_type_is(kms):
    taken = _copy(kms, 'urn:filter:1')
    document = taken['entities'][0]['document']

    def turned(value):
        if isinstance(value, dict):
            return {k: turned(v) for k, v in reversed(list(value.items()))}
        return [turned(v) for v in value] if isinstance(value, list) else value
    _store(kms, _docs(kms) + [turned(document)])
    assert paste_entities(load(kms), taken, CASE)['same'] == ['urn:filter:1']
    key = 'iffBaseEntities:hasStrength'
    for value, other in ((1, True), (1, 1.0)):
        _store(kms, [dict(document, **{key: {'type': 'Property', 'value': value}})])
        changed = _with(taken, document=dict(document, **{key: {'type': 'Property', 'value': other}}))
        assert paste_entities(load(kms), changed, CASE, check=True)['present'] == ['urn:filter:1']


def test_a_file_other_cases_include_is_said(kms):
    expectations = load_expectations(kms)
    example = next(e for e in expectations.examples if e.path == CASE)
    other = next(e for e in expectations.examples if e.source != example.source)
    assert paste_entities(load(kms), _copy(kms, 'urn:filter:1'), CASE, check=True)['shared'] == []
    from ruamel.yaml import YAML

    yaml = YAML()
    with open(other.source) as handle:
        raw = yaml.load(handle)
    entry = next(e for e in raw['examples'] if os.path.basename(e['path']) == os.path.basename(other.path))
    entry['include'] = [CASE]
    with open(other.source, 'w') as handle:
        yaml.dump(raw, handle)
    assert paste_entities(load(kms), _copy(kms, 'urn:filter:1'), CASE, check=True)['shared'] == [other.path]


def test_an_entity_of_two_definitions_is_said(kms):
    docs = _docs(kms, 'model-instance.jsonld')
    _store(kms, docs + [dict(docs[0])], 'model-instance.jsonld')
    assert copy_entities(load(kms), docs[0]['id'])['repeated'] == [docs[0]['id']]
    assert copy_entities(load(kms), docs[1]['id'])['repeated'] == []


def test_the_row_s_own_file_is_the_one_copied(kms):
    """Two model files define one id: the one of the row is taken."""
    docs = _docs(kms, 'model-instance.jsonld')
    os.remove(os.path.join(kms, 'model-instance.jsonld'))
    os.mkdir(os.path.join(kms, 'model-instance'))
    mine = dict(docs[0], **{'iffBaseEntities:mine': {'type': 'Property', 'value': 7}})
    _store(kms, docs, 'model-instance/a.jsonld')
    _store(kms, [mine], 'model-instance/b.jsonld')
    done = copy_entities(load(kms), docs[0]['id'], file=os.path.join(kms, 'model-instance', 'b.jsonld'))
    assert done['content']['entities'] == [{'document': mine, 'from': 'model-instance'}]
    assert done['repeated'] == [docs[0]['id']]


def test_a_case_that_is_not_json_is_named(kms):
    taken = _copy(kms, 'urn:filter:1')
    with open(os.path.join(kms, 'examples', CASE), 'w') as handle:
        handle.write('[')
    with pytest.raises(PackageError, match='without-cartridge.jsonld is not JSON'):
        paste_entities(load(kms), taken, CASE)


@pytest.mark.parametrize('written', ['./part/../a%20b', 'part-ü', 'urn:x:a?b#c', 'ex:part', 'a&<b>"'])
def test_an_id_however_it_is_written(kms, written):
    """Relative, with a prefix of its context, with special characters."""
    _typed(kms, hasCartridge=UA + 'HasComponent')
    docs = _docs(kms, 'model-instance.jsonld')
    part = next(d for d in docs if d['id'] == 'urn:filter:1')
    key = next(k for k in part if k.endswith('hasCartridge'))
    given = part['@context'] if isinstance(part['@context'], list) else [part['@context']]
    part.update({'@context': given + [{'ex': 'https://example.com/parts/'}], 'id': written})
    part[key] = {'type': 'Relationship', 'object': 'urn:cartridge:1'}
    if written == 'ex:part':
        # Pointed at by the whole IRI, written with the prefix.
        top = next(d for d in docs if d['id'] == 'urn:plasmacutter:1')
        _typed(kms, hasFilter=UA + 'HasComponent', hasCartridge=UA + 'HasComponent')
        top[next(k for k in top if k.endswith('hasFilter'))] = {
            'type': 'Relationship', 'object': 'https://example.com/parts/part'}
    _store(kms, docs, 'model-instance.jsonld')
    copied = copy_entities(load(kms), written, subtree=True)['copied']
    assert copied[0] == written
    if not set(written) & set('<>"'):                 # no IRI has those: its triples are not read
        assert copied == [written, 'urn:cartridge:1']
    if written == 'ex:part':
        assert copy_entities(load(kms), 'urn:plasmacutter:1', subtree=True)['copied'] == \
            ['urn:plasmacutter:1', 'ex:part', 'urn:cartridge:1']
    assert paste_entities(load(kms), _copy(kms, written), CASE)['pasted'] == [written] and written in _ids(kms)


@pytest.mark.parametrize('several', [
    {'type': 'Relationship', 'object': ['urn:cartridge:1', 'urn:cartridge:2']},
    [{'type': 'Relationship', 'object': 'urn:cartridge:1'},
     {'type': 'Relationship', 'object': 'urn:cartridge:2', 'datasetId': 'urn:d:2'}],
    {'type': 'ListRelationship', 'objectList': [{'object': 'urn:cartridge:1'}, {'object': 'urn:cartridge:2'}]},
    {'type': 'ListRelationship', 'ngsi-ld:hasObjectList': {'@list': [
        {'ngsi-ld:hasObject': {'@id': 'urn:cartridge:1'}}, {'@id': 'urn:cartridge:2'}]}}])
def test_a_relationship_to_several(kms, several):
    _typed(kms, hasCartridge=UA + 'HasComponent')
    docs = _docs(kms, 'model-instance.jsonld')
    entity = next(d for d in docs if d['id'] == 'urn:filter:1')
    entity[next(k for k in entity if k.endswith('hasCartridge'))] = several
    given = entity['@context'] if isinstance(entity['@context'], list) else [entity['@context']]
    entity['@context'] = given + [{'ngsi-ld': 'https://uri.etsi.org/ngsi-ld/', 'object': {
        '@id': 'ngsi-ld:hasObject', '@type': '@id'}, 'objectList': {'@id': 'ngsi-ld:hasObjectList',
                                                                    '@container': '@list'}}]
    other = dict(next(d for d in docs if d['id'] == 'urn:cartridge:1'), id='urn:cartridge:2')
    _store(kms, docs + [other], 'model-instance.jsonld')
    assert copy_entities(load(kms), 'urn:filter:1', subtree=True)['copied'] == \
        ['urn:filter:1', 'urn:cartridge:1', 'urn:cartridge:2']


@pytest.mark.parametrize('above', ['HasComponent', 'HasProperty', 'Aggregates'])
def test_a_companion_s_reference_below_a_core_one_the_knowledge_leaves_out(kms, above):
    _typed(kms, hasFilter='https://x/HasPart')
    with open(os.path.join(kms, 'knowledge.ttl'), 'a') as handle:
        handle.write(f'\n<https://x/HasPart> <http://www.w3.org/2000/01/rdf-schema#subPropertyOf> <{UA}{above}> .\n')
    assert copy_entities(load(kms), 'urn:plasmacutter:1', subtree=True)['copied'] == \
        ['urn:plasmacutter:1', 'urn:filter:1']


def test_the_core_s_child_references_are_all_known():
    """As the core nodeset has them: HasSubtype (i=45), below HasChild (i=34)."""
    import xml.etree.ElementTree as ET

    from semforge.cooked.hierarchy import CORE

    tree = ET.parse(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'opcua', 'tests', 'nodeset2owl',
                                 'Opc.Ua.NodeSet2.xml')).getroot()
    ua = {'u': tree.tag[1:].split('}')[0]}
    alias = {a.get('Alias'): a.text for a in tree.iterfind('.//u:Alias', ua)}
    names, above = {}, {}
    for node in tree.iterfind('u:UAReferenceType', ua):
        names[node.get('NodeId')] = node.get('BrowseName')
        for ref in node.iterfind('.//u:Reference', ua):
            kind = alias.get(ref.get('ReferenceType'), ref.get('ReferenceType'))
            if kind == 'i=45' and ref.get('IsForward') == 'false':
                above[node.get('NodeId')] = ref.text.strip()

    def child(node):
        return node == 'i=34' or (node in above and child(above[node]))
    wanted = {UA + name for node, name in names.items() if child(node)}
    assert len(wanted) > 20 and {str(r) for r in CORE} == wanted


def test_a_long_list_of_values_is_no_depth(kms):
    _typed(kms, hasFilter=UA + 'HasComponent')
    docs = _docs(kms, 'model-instance.jsonld')
    top = next(d for d in docs if d['id'] == 'urn:plasmacutter:1')
    top['@context'] = [top['@context'], {'valueList': {'@id': 'https://uri.etsi.org/ngsi-ld/hasValueList',
                                                       '@container': '@list'}}]
    top['iffBaseEntities:series'] = {'type': 'ListProperty', 'valueList': [1] * 10000}
    _store(kms, docs, 'model-instance.jsonld')
    package = load(kms)
    assert len(package.model) > 20000, 'the list is in the graph'
    assert copy_entities(package, 'urn:plasmacutter:1', subtree=True)['copied'] == \
        ['urn:plasmacutter:1', 'urn:filter:1']


def test_a_long_list_of_undeclared_targets_is_in_time(kms):
    import time

    _typed(kms, hasFilter=UA + 'HasComponent')
    docs = _docs(kms, 'model-instance.jsonld')
    top = next(d for d in docs if d['id'] == 'urn:workpiece:1')
    ngsi = 'https://uri.etsi.org/ngsi-ld/'
    top['@context'] = [top['@context'], {'objectList': {'@id': ngsi + 'hasObjectList', '@container': '@list'},
                                         'object': {'@id': ngsi + 'hasObject', '@type': '@id'}}]
    top['iffBaseEntities:many'] = {'type': 'ListRelationship', 'objectList': [
        {'object': f'urn:many:{n}'} for n in range(3000)]}
    given = docs[0]['@context']
    _store(kms, docs + [{'id': f'urn:many:{n}', 'type': 'iffBaseEntities:X', '@context': given} for n in range(3000)],
           'model-instance.jsonld')
    package, started = load(kms), time.time()
    assert len(copy_entities(package, 'urn:workpiece:1', subtree=True)['copied']) == 3001
    assert time.time() - started < 10


def test_shapes_and_types_however_deep(kms):
    """Thousands of shapes that apply the next, and of types above another."""
    _relate(kms, 'urn:workpiece:1', 'iffBaseEntities:holdsNew', 'urn:cartridge:1')
    path = _iri(kms, 'hasFilter').replace('hasFilter', 'holdsNew')
    kind = next(d for d in _docs(kms, 'model-instance.jsonld') if d['id'] == 'urn:workpiece:1')['type'].split(':')[-1]
    sh, sub_class = 'http://www.w3.org/ns/shacl#', '<http://www.w3.org/2000/01/rdf-schema#subClassOf>'
    with open(os.path.join(kms, 'knowledge.ttl'), 'a') as handle:
        handle.write(f"\n{path.replace('holdsNew', kind)} {sub_class} <https://x/T0> .\n")
        handle.writelines(f'<https://x/T{n}> {sub_class} <https://x/T{n + 1}> .\n' for n in range(2000))
    with open(os.path.join(kms, 'shacl.ttl'), 'a') as handle:
        handle.write(f'\n<https://x/S0> a <{sh}NodeShape> ; <{sh}targetClass> <https://x/T2000> .\n')
        handle.writelines(f'<https://x/S{n}> <{sh}node> <https://x/S{n + 1}> .\n' for n in range(2000))
        handle.write(f'<https://x/S2000> <{sh}property> [ <{sh}path> {path} ; '
                     f'<{BASE}hasReferenceType> <{UA}HasComponent> ] .\n')
    assert copy_entities(load(kms), 'urn:workpiece:1', subtree=True)['copied'] == \
        ['urn:workpiece:1', 'urn:cartridge:1']


def test_two_relationships_to_one_target_whatever_comes_first():
    from itertools import permutations

    from semforge.cooked.hierarchy import weightier

    for one, other in permutations([True, None, False], 2):
        assert weightier(one, other) is (True if True in (one, other) else None)


@pytest.mark.parametrize('turned', [False, True])
def test_declared_as_no_child_and_undeclared_to_one_target(kms, turned):
    """What one relationship is declared not to be, another may still be."""
    _typed(kms, hasCartridge=UA + 'Organizes')
    docs = _docs(kms, 'model-instance.jsonld')
    entity = next(d for d in docs if d['id'] == 'urn:filter:1')
    entity['iffBaseEntities:a' if turned else 'iffBaseEntities:zz'] = {
        'type': 'Relationship', 'object': 'urn:cartridge:1'}
    docs = [d for d in docs if d['id'] == 'urn:filter:1' or 'urn:cartridge:1' not in json.dumps(
        {k: v for k, v in d.items() if k != 'id'})]
    _store(kms, docs, 'model-instance.jsonld')
    done = copy_entities(load(kms), 'urn:filter:1', subtree=True)
    assert done['assumed'] == ['urn:cartridge:1']


SPELLED = {'@context': {'ex': 'https://example.com/', 'type': '@type', 'id': '@id'}}


@pytest.mark.parametrize('copied, there', [
    ('ex:a', 'https://example.com/a'), ('https://example.com/a', 'ex:a'), ('part', './part'), ('x/../part', 'part')])
def test_one_the_case_spells_otherwise_is_found(kms, copied, there):
    document = {'id': copied, 'type': 'https://example.com/T', '@context': SPELLED['@context'],
                'https://example.com/v': {'type': 'https://uri.etsi.org/ngsi-ld/Property'}}
    _store(kms, _docs(kms, 'model-instance.jsonld') + [document], 'model-instance.jsonld')
    taken, before = _copy(kms, copied), _docs(kms)
    _store(kms, [dict(document, id=there)] + before)
    assert paste_entities(load(kms), taken, CASE)['same'] == [copied], 'the id is all that differs'
    _store(kms, [dict(document, id=there, other=1)] + before)
    plan = paste_entities(load(kms), taken, CASE, check=True)
    assert plan['present'] == [copied] and plan['spelled'] == {copied: there} and not plan['pasted']
    paste_entities(load(kms), taken, CASE, replace=True)
    assert _docs(kms) == [document] + before, 'in its place, as it was copied'
    # ... and in a file it includes.
    case = next(e for e in load_expectations(kms).examples if any('cartridge-fresh' in i for i in e.include))
    include = os.path.join('examples', next(i for i in case.include if 'cartridge-fresh' in i))
    _store(kms, [dict(document, id=there)], include)
    assert paste_entities(load(kms), taken, case.path, check=True)['included'] == [copied]


def test_a_copy_that_spells_one_entity_twice_is_refused(kms):
    document = {'id': 'ex:a', 'type': 'T', '@context': SPELLED['@context']}
    both = _with(_copy(kms, 'urn:filter:1'), document=document)
    with pytest.raises(PackageError, match='twice'):
        paste_entities(load(kms), _both(both, _with(both, document=dict(document, id='https://example.com/a'))), CASE)


def test_the_case_s_own_definition_first_however_it_is_spelled(kms):
    """The model spells it as the data points at it; the case, with a prefix."""
    _typed(kms, hasCartridge=UA + 'HasComponent')
    model = _docs(kms, 'model-instance.jsonld')
    part = dict(next(d for d in model if d['id'] == 'urn:cartridge:1'), id='https://example.com/a')
    _store(kms, model + [part], 'model-instance.jsonld')
    holder = dict(next(d for d in model if d['id'] == 'urn:filter:1'))
    holder[next(k for k in holder if k.endswith('hasCartridge'))] = {
        'type': 'Relationship', 'object': 'https://example.com/a'}
    given = part['@context'] if isinstance(part['@context'], list) else [part['@context']]
    own = dict(part, **{'id': 'ex:a', '@context': given + [SPELLED['@context']], 'iffBaseEntities:mine': {
        'type': 'Property', 'value': 1}})
    _store(kms, [holder, own])
    done = copy_entities(load(kms), 'urn:filter:1', file=os.path.join(kms, 'examples', CASE), subtree=True)
    assert done['copied'] == ['urn:filter:1', 'ex:a'] and done['content']['entities'][1]['document'] == own


def test_a_context_that_is_not_to_be_had_does_not_stop_a_paste(kms):
    taken = _with(_copy(kms, 'urn:filter:1'), document={'id': 'urn:n', 'type': 'T', '@context': 'no-such.jsonld'})
    assert paste_entities(load(kms), taken, CASE)['pasted'] == ['urn:n']


def _in_graph(kms, path):
    docs = _docs(kms, path)
    docs = docs if isinstance(docs, list) else [docs]
    _store(kms, {'@context': docs[0]['@context'], '@graph': docs}, path)
    with open(os.path.join(kms, path)) as handle:
        return handle.read()


@pytest.mark.parametrize('where', ['case', 'include', 'list'])
def test_entities_inside_a_graph_are_not_pasted_a_second_time(kms, where):
    case = next(e for e in load_expectations(kms).examples if any('cartridge-fresh' in i for i in e.include))
    include = os.path.join('examples', next(i for i in case.include if 'cartridge-fresh' in i))
    own = os.path.join('examples', case.path)
    taken = _copy(kms, 'urn:cartridge:1')
    path = include if where == 'include' else own
    if where == 'list':
        _store(kms, _docs(kms, own) + [{'@context': {}, '@graph': []}], own)
    else:
        _in_graph(kms, path)
    before = open(os.path.join(kms, own)).read()
    for check in (True, False):
        with pytest.raises(PackageError, match=f'{os.path.basename(path)} has its entities inside "@graph"'):
            paste_entities(load(kms), taken, case.path, replace=True, check=check)
    assert open(os.path.join(kms, own)).read() == before


@pytest.mark.parametrize('where', ['case', 'include', 'model'])
def test_entities_inside_a_graph_are_not_left_out_of_a_copy(kms, where):
    case = next(e for e in load_expectations(kms).examples if any('cartridge-fresh' in i for i in e.include))
    include = os.path.join('examples', next(i for i in case.include if 'cartridge-fresh' in i))
    own = os.path.join('examples', case.path)
    entity = _docs(kms, own)[0]['id']
    path = {'case': own, 'include': include, 'model': 'model-instance.jsonld'}[where]
    _in_graph(kms, path)
    with pytest.raises(PackageError, match=f'{os.path.basename(path)} has its entities inside "@graph"'):
        copy_entities(load(kms), entity, file=os.path.join(kms, own), subtree=True)


def test_the_row_s_file_is_where_it_is_copied_from(kms):
    """Gone from that file, it is not taken from another instead."""
    case = os.path.join(kms, 'examples', CASE)
    with pytest.raises(PackageError, match='any more'):
        copy_entities(load(kms), 'urn:workpiece:1', file=case)
    docs = _docs(kms, 'model-instance.jsonld')
    os.remove(os.path.join(kms, 'model-instance.jsonld'))
    os.mkdir(os.path.join(kms, 'model-instance'))
    _store(kms, docs, 'model-instance/a.jsonld')
    _store(kms, docs[:1], 'model-instance/b.jsonld')
    with pytest.raises(PackageError, match='any more'):
        copy_entities(load(kms), docs[1]['id'], file=os.path.join(kms, 'model-instance', 'b.jsonld'))
    assert copy_entities(load(kms), docs[1]['id'])['copied'] == [docs[1]['id']]


def _second_case(kms, name, include=()):
    """Another declared case, a link to CASE's file."""
    example = next(e for e in load_expectations(kms).examples if e.path == CASE)
    path = os.path.join(os.path.dirname(os.path.join(kms, 'examples', CASE)), name)
    os.symlink(os.path.join(kms, 'examples', CASE), path)
    with open(example.source, 'a') as handle:
        handle.write(f'  - path: {name}\n    expect: invalid\n')
        if include:
            handle.write('    include:\n' + ''.join(f'      - {i}\n' for i in include))
    return os.path.join(os.path.dirname(CASE), name)


def test_the_case_that_is_named_and_the_one_that_is_the_same_file(kms):
    include = next(i for e in load_expectations(kms).examples for i in e.include if 'cartridge-fresh' in i)
    other = _second_case(kms, 'linked.jsonld', [include])
    taken = _copy(kms, 'urn:cartridge:1')
    for case, twin in ((CASE, other), (other, CASE), (os.path.join(kms, 'examples', other), CASE)):
        plan = paste_entities(load(kms), taken, case, check=True)
        assert plan['case'] == os.path.relpath(os.path.join(kms, 'examples', case), os.path.join(kms, 'examples'))
        assert plan['shared'] == [twin] and plan['included'] == ['urn:cartridge:1'] and not plan['pasted']


def test_of_two_definitions_only_the_copied_one_s_relationships_count(kms):
    _typed(kms, hasCartridge=UA + 'HasComponent', hasFilter=UA + 'HasComponent')
    docs = _docs(kms, 'model-instance.jsonld')
    first = next(d for d in docs if d['id'] == 'urn:workpiece:1')
    second = dict(first, **{'iffBaseEntities:hasFilter': {'type': 'Relationship', 'object': 'urn:filter:1'}})
    _store(kms, docs + [second], 'model-instance.jsonld')
    done = copy_entities(load(kms), 'urn:workpiece:1', subtree=True)
    assert done['copied'] == ['urn:workpiece:1'] and done['repeated'] == ['urn:workpiece:1']
    # ... and what only the other one points at is nobody's.
    new = dict(first, id='urn:new:1')
    lone = {'iffBaseEntities:holds': {'type': 'Relationship', 'object': 'urn:new:1'}}
    top = next(d for d in docs if d['id'] == 'urn:cartridge:1')
    _store(kms, docs + [dict(first, **lone), new, dict(first, id='urn:more:1'), dict(
        next(d for d in docs if d['id'] == 'urn:filter:1'), id='urn:holder:1', **lone)], 'model-instance.jsonld')
    assert top and copy_entities(load(kms), 'urn:holder:1', subtree=True)['assumed'] == ['urn:new:1']


def test_two_definitions_keep_the_package_s_own_context(kms):
    """The published context is the package's file, also where a copy parses."""
    _typed(kms, hasCartridge=UA + 'HasComponent')
    docs = _docs(kms, 'model-instance.jsonld')
    _store(kms, docs + [dict(next(d for d in docs if d['id'] == 'urn:filter:1'))], 'model-instance.jsonld')
    done = copy_entities(load(kms), 'urn:filter:1', subtree=True)
    assert done['copied'] == ['urn:filter:1', 'urn:cartridge:1'] and done['repeated'] == ['urn:filter:1']


INSIDE = {'id': 'urn:inside:1', 'type': 'iffBaseEntities:Cartridge'}


@pytest.mark.parametrize('relationship', [
    {'type': 'Relationship', 'object': INSIDE},
    {'type': 'Relationship', 'object': ['urn:cartridge:1', INSIDE]},
    {'type': 'Relationship', 'object': {'type': 'iffBaseEntities:Cartridge', 'iffBaseEntities:x': 1}},
    {'type': 'ListRelationship', 'objectList': [{'object': INSIDE}]},
    {'type': 'Relationship', 'ngsi-ld:hasObject': INSIDE},
    {'type': 'ngsi-ld:Relationship', 'object': INSIDE},
    {'type': 'https://uri.etsi.org/ngsi-ld/ListRelationship', 'objectList': {'@list': [{'object': INSIDE}]}},
    [{'type': 'Relationship', 'object': 'urn:cartridge:1'}, {'type': 'Relationship', 'object': INSIDE,
                                                             'datasetId': 'urn:d:2'}],
    {'type': 'Property', 'value': 1, 'iffBaseEntities:sub': {'type': 'Relationship', 'object': INSIDE}}])
def test_an_entity_written_in_a_relationship_is_refused(kms, relationship):
    """Not copied or pasted from or beside such a file: it would be missed, or doubled."""
    taken = _copy(kms, 'urn:filter:1')
    case = next(e for e in load_expectations(kms).examples if any('cartridge-fresh' in i for i in e.include))
    include = os.path.join('examples', next(i for i in case.include if 'cartridge-fresh' in i))
    for path in ('model-instance.jsonld', include, os.path.join('examples', case.path)):
        saved = open(os.path.join(kms, path)).read()
        docs = _docs(kms, path)
        docs[0]['iffBaseEntities:holds'] = relationship
        _store(kms, docs, path)
        said = f'{os.path.basename(path)}: {docs[0]["id"]} has '
        with pytest.raises(PackageError, match=said + ".* written in a relationship's object"):
            copy_entities(load(kms), docs[0]['id'], file=os.path.join(kms, path))
        if path != 'model-instance.jsonld':
            before = _snapshot(kms)
            with pytest.raises(PackageError, match=said):
                paste_entities(load(kms), taken, case.path, check=True)
            with pytest.raises(PackageError, match=said):
                paste_entities(load(kms), taken, case.path)
            assert _snapshot(kms) == before
        with open(os.path.join(kms, path), 'w') as handle:
            handle.write(saved)


def _snapshot(root):
    found = {}
    for folder, _, names in os.walk(root):
        for name in names:
            with open(os.path.join(folder, name), 'rb') as handle:
                found[os.path.join(folder, name)] = handle.read()
    return found


@pytest.mark.parametrize('value', [
    {'type': 'Property', 'value': {'id': 'urn:x', 'type': 'T', 'a': 1}},
    {'type': 'JsonProperty', 'json': {'id': 'urn:x', 'type': 'T', 'object': {'id': 'urn:y', 'type': 'T'}}},
    {'type': 'VocabProperty', 'vocab': {'id': 'urn:x', 'type': 'T'}},
    {'type': 'VocabProperty', 'vocab': {'id': 'urn:x', 'type': 'T', 'r': {'type': 'Relationship', 'object': INSIDE}}},
    {'type': 'LanguageProperty', 'languageMap': {'en': 'a'}},
    {'type': 'GeoProperty', 'value': {'type': 'Point', 'coordinates': [1, 2]}},
    {'type': 'Property', 'value': [{'id': 'urn:x', 'type': 'T', 'object': {'id': 'urn:y', 'type': 'T'}}]},
    {'type': 'Relationship', 'object': {'@id': 'urn:cartridge:1'}},
    {'type': 'Relationship', 'object': [{'id': 'urn:cartridge:1'}]}])
def test_values_that_hold_objects_are_no_entities(kms, value):
    docs = _docs(kms, 'model-instance.jsonld')
    docs[0]['iffBaseEntities:holds'] = value
    _store(kms, docs, 'model-instance.jsonld')
    taken = _copy(kms, docs[0]['id'])
    assert paste_entities(load(kms), taken, CASE)['pasted'] == [docs[0]['id']]


SHACL = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'


def test_an_open_prefix_is_expanded_by_the_package_s_names(kms):
    """D6: a prefix the context does not declare is expanded by the package's
    names (kms.yaml), as the trees do: the case has the entity, by its IRI."""
    docs = _docs(kms, 'model-instance.jsonld')
    opened = dict(docs[0], id='iffBaseShacl:one')            # named by kms.yaml, not by the context
    whole = dict(docs[0], id=SHACL + 'one')
    _store(kms, docs + [opened], 'model-instance.jsonld')
    _store(kms, [whole])
    taken = _copy(kms, opened['id'])
    assert paste_entities(load(kms), taken, CASE)['same'] == [opened['id']]
    _store(kms, [dict(whole, **{'iffBaseEntities:x': {'type': 'Property', 'value': 2}})])
    plan = paste_entities(load(kms), taken, CASE, check=True)
    assert plan['present'] == [opened['id']] and plan['spelled'] == {opened['id']: whole['id']}
    assert not plan['pasted']
    paste_entities(load(kms), taken, CASE, replace=True)
    assert _docs(kms) == [opened]


def test_a_child_named_with_an_open_prefix_is_found(kms):
    """Pointed at by its IRI and defined with the open prefix, or the other way."""
    _typed(kms, hasCartridge=UA + 'HasComponent')
    docs = _docs(kms, 'model-instance.jsonld')
    name = next(k for k in next(d for d in docs if d['id'] == 'urn:filter:1') if k.endswith('hasCartridge'))
    cartridge = next(d for d in docs if d['id'] == 'urn:cartridge:1')
    for defined, pointed in (('iffBaseShacl:c', SHACL + 'c'), (SHACL + 'd', 'iffBaseShacl:d')):
        _store(kms, _docs(kms, 'model-instance.jsonld') + [dict(cartridge, id=defined)], 'model-instance.jsonld')
        _relate(kms, 'urn:filter:1', name, pointed)
        done = copy_entities(load(kms), 'urn:filter:1', subtree=True)
        assert done['copied'] == ['urn:filter:1', defined] and not done['missing'], done
    _relate(kms, 'urn:filter:1', name, 'iffBaseShacl:nowhere')
    assert copy_entities(load(kms), 'urn:filter:1', subtree=True)['missing'] == ['iffBaseShacl:nowhere']


@pytest.mark.parametrize('spelled', ['plain', 'dotted'])
def test_a_case_is_read_from_the_folder_it_is_named_by(kms, tmp_path, spelled):
    """A case that is another's file, by a link from elsewhere: its relative
    context is from the folder of the path the row has."""
    docs = _docs(kms, 'model-instance.jsonld')
    linked = os.path.join(kms, 'examples', 'test_FilterShape', 'other')
    os.makedirs(linked)
    real = os.path.join(kms, 'examples', CASE)
    _store(kms, [dict(docs[0], **{'@context': '../../../context.jsonld'})])
    os.symlink(real, os.path.join(linked, 'twin.jsonld'))
    example = next(e for e in load_expectations(kms).examples if e.path == CASE)
    with open(example.source, 'a') as handle:
        handle.write('  - path: ../other/twin.jsonld\n    expect: invalid\n')
    named = os.path.join(linked, 'twin.jsonld') if spelled == 'plain' else os.path.join(linked, '.', 'twin.jsonld')
    done = copy_entities(load(kms), docs[0]['id'], file=named)
    assert done['content']['entities'][0]['from'] == os.path.join('examples', 'test_FilterShape', 'other')
    assert copy_entities(load(kms), docs[0]['id'], file=real)['content']['entities'][0]['from'] == \
        os.path.dirname(os.path.join('examples', CASE))


def test_a_linked_case_has_its_own_includes(kms):
    """A case that is another case's file, by a link: a copy from it takes
    what it includes, not what the other case includes."""
    _typed(kms, hasCartridge=UA + 'HasComponent')
    shared = os.path.join(kms, 'examples', 'test_CartridgeShape', 'bad', 'shared-by-two-filters.jsonld')
    twin = os.path.join(kms, 'examples', 'test_CartridgeShape', 'twin')
    os.makedirs(twin)
    os.symlink(shared, os.path.join(twin, 'twin.jsonld'))
    with open(os.path.join(twin, 'expectations.yaml'), 'w') as handle:
        handle.write('examples:\n  - path: twin.jsonld\n    expect: invalid\n')

    def cartridge_from(file):
        done = copy_entities(load(kms), 'urn:filter:1', file=file, subtree=True)
        return {_document_id(e['document']): e['from'] for e in done['content']['entities']}['urn:cartridge:1']
    assert cartridge_from(shared) == os.path.join('examples', 'subobjects'), 'the case\'s include'
    assert cartridge_from(os.path.join(twin, 'twin.jsonld')) == '.', 'no include: the main model\'s'


def test_one_that_points_at_itself_is_still_a_child(kms):
    _typed(kms, hasFilter=UA + 'HasComponent')
    docs = _docs(kms, 'model-instance.jsonld')
    new = dict(docs[0], id='urn:new:1', **{'iffBaseEntities:self': {'type': 'Relationship', 'object': 'urn:new:1'}})
    _store(kms, docs + [new], 'model-instance.jsonld')
    _relate(kms, 'urn:workpiece:1', 'iffBaseEntities:holds', 'urn:new:1')
    assert copy_entities(load(kms), 'urn:workpiece:1', subtree=True)['assumed'] == ['urn:new:1']


def test_a_case_that_is_the_main_model_is_not_written(kms):
    path = os.path.join(kms, 'examples', CASE)
    taken = _copy(kms, 'urn:filter:1', file=None)
    os.remove(path)
    os.symlink(os.path.join(kms, 'model-instance.jsonld'), path)
    model = _docs(kms, 'model-instance.jsonld')
    with pytest.raises(PackageError, match='main model'):
        paste_entities(load(kms), _with(taken, document=dict(taken['entities'][0]['document'], id='urn:n:1')), CASE)
    assert _docs(kms, 'model-instance.jsonld') == model


def test_every_row_of_a_case_offers_paste(kms, tmp_path):
    """What package.json matches is what the rows are, whatever they are."""
    from semforge.cooked.examples import build_suite
    from semforge.editor.views import _serialise_example

    with open(os.path.join(SRC, '..', 'package.json')) as handle:
        rows = json.load(handle)['contributes']['menus']['view/item/context']
    when = next(m['when'] for m in rows if m['command'] == 'semforge.pasteEntity')
    offered = re.compile(re.search('=~ /(.*?)/', when).group(1))
    case = os.path.join(kms, 'examples', CASE)
    docs = _docs(kms)
    docs[0].update({'iffBaseEntities:several': [
        {'type': 'Property', 'value': n, 'datasetId': f'urn:d:{n}', 'observedAt': '2026-01-01T00:00:00Z',
         'iffBaseEntities:sub': {'type': 'Property', 'value': {'a': 1}}} for n in range(2)],
        'iffBaseEntities:series': [{'type': 'Property', 'value': n, 'observedAt': f'2026-01-0{n + 1}T00:00:00Z'}
                                   for n in range(2)],
        'iffBaseEntities:none': {'type': 'Property'},
        'iffBaseEntities:list': {'type': 'ListProperty', 'valueList': []}})
    _store(kms, docs)
    roots = [_serialise_example(n) for n in build_suite(load(kms))]
    cases = []

    def walk(nodes):
        for node in nodes:
            if node['kind'] == 'example' and node['file']:
                cases.append(node)
            else:
                walk(node['children'])
    walk(roots)
    assert any(c['file'] == case for c in cases)
    seen = _drive(tmp_path, {'mode': 'items', 'provider': 'ModelTreeProvider', 'uri': 'file:///pkg/shacl.ttl',
                             'config': {'trees.detail': 'full'}, 'replies': {'semforge/model': {'roots': cases}}},
                  'model.js')
    kinds = {row['contextValue'] for row in seen['rows']}
    assert {'example', 'entity', 'type', 'include'} <= kinds and len(kinds) > 6, kinds
    assert [k for k in kinds if not offered.search(k)] == []


def test_a_case_of_one_object_stays_one(kms):
    taken = _copy(kms, 'urn:filter:1')
    _store(kms, dict(taken['entities'][0]['document'], other=1))
    paste_entities(load(kms), taken, CASE, replace=True)
    assert _docs(kms) == taken['entities'][0]['document']
    paste_entities(load(kms), _copy(kms, 'urn:workpiece:1'), CASE)
    assert _ids(kms) == ['urn:filter:1', 'urn:workpiece:1']
    _store(kms, [dict(taken['entities'][0]['document'], other=1)])
    paste_entities(load(kms), taken, CASE, replace=True)
    assert _docs(kms) == [taken['entities'][0]['document']], 'a list stays a list'


def test_a_file_included_twice_is_not_a_second_definition(kms):
    case = next(e for e in load_expectations(kms).examples if any('cartridge-fresh' in i for i in e.include))
    with open(case.source) as handle:
        text = handle.read()
    from ruamel.yaml import YAML
    raw = YAML().load(text)
    for entry in raw['examples']:
        if os.path.basename(entry['path']) == os.path.basename(case.path):
            entry['include'] = list(entry['include']) + [
                i.replace('subobjects', './subobjects') for i in entry['include']]
    with open(case.source, 'w') as handle:
        YAML().dump(raw, handle)
    _typed(kms, hasCartridge=UA + 'HasComponent')
    entity = _docs(kms, os.path.join('examples', case.path))[0]['id']
    done = copy_entities(load(kms), entity, file=os.path.join(kms, 'examples', case.path), subtree=True)
    assert 'urn:cartridge:1' in done['copied'] and not done['repeated']


def test_a_case_that_includes_the_model_is_one_graph(kms):
    """The case's own graph, also where its file is the model's."""
    _typed(kms, hasFilter=UA + 'HasComponent')
    from ruamel.yaml import YAML
    example = next(e for e in load_expectations(kms).examples if e.path == CASE)
    with open(example.source) as handle:
        raw = YAML().load(handle)
    next(e for e in raw['examples'] if e['path'].endswith('without-cartridge.jsonld'))['include'] = [
        'model-instance.jsonld']
    with open(example.source, 'w') as handle:
        YAML().dump(raw, handle)
    model = _docs(kms, 'model-instance.jsonld')
    _store(kms, model + [dict(model[0], id='urn:only:1')], 'model-instance.jsonld')
    _relate(kms, 'urn:workpiece:1', 'iffBaseEntities:holds', 'urn:only:1')
    docs = _docs(kms)
    docs[0]['iffBaseEntities:sees'] = {'type': 'Relationship', 'object': 'urn:only:1'}
    docs[0]['iffBaseEntities:hasFilter'] = {'type': 'Relationship', 'object': 'urn:workpiece:1'}
    _store(kms, docs)
    done = copy_entities(load(kms), docs[0]['id'], file=os.path.join(kms, 'examples', CASE), subtree=True)
    assert 'urn:workpiece:1' in done['copied'] and 'urn:only:1' in done['left'], 'the case points at it too'


def test_what_was_asked_about_is_what_is_written(kms):
    """The case, or what it includes, changed between the question and the answer."""
    taken = _copy(kms, 'urn:filter:1')
    plan = paste_entities(load(kms), taken, CASE, check=True)['plan']
    before = _docs(kms)
    changed = before + [dict(taken['entities'][0]['document'], other=1)]
    _store(kms, changed)
    with pytest.raises(PackageError, match='changed meanwhile'):
        paste_entities(load(kms), taken, CASE, replace=True, plan=plan)
    assert _docs(kms) == changed
    plan = paste_entities(load(kms), taken, CASE, check=True)['plan']
    paste_entities(load(kms), taken, CASE, replace=True, plan=plan)
    assert _docs(kms)[-1] == taken['entities'][0]['document']


def test_a_question_about_included_files_is_checked_too(kms):
    case = next(e for e in load_expectations(kms).examples if any('cartridge-fresh' in i for i in e.include))
    include = os.path.join('examples', next(i for i in case.include if 'cartridge-fresh' in i))
    taken = _copy(kms, 'urn:cartridge:1')
    plan = paste_entities(load(kms), taken, case.path, check=True)
    _store(kms, [], include)
    with pytest.raises(PackageError, match='changed meanwhile'):
        paste_entities(load(kms), taken, case.path, plan=plan['plan'])


def test_one_entity_of_a_package_with_many_is_found_in_time(tmp_path):
    """Thousands of children, decided by the data: no time grows with their square."""
    import time

    from scale_package import make

    root = str(tmp_path / 'big')
    make(root, types=100, entities=3000)
    docs = _docs(root, 'model-instance.jsonld')
    some = [d for d in docs if d['id'].startswith('urn:gen:')]
    for n, document in enumerate(some[1:], 1):
        some[(n - 1) // 10].setdefault('iffBaseEntities:holds', []).append(
            {'type': 'Relationship', 'object': document['id'], 'datasetId': f'urn:d:{n}'})
    _store(root, docs, 'model-instance.jsonld')
    _typed(root, hasFilter=UA + 'HasComponent')
    package = load(root)
    started = time.time()
    done = copy_entities(package, 'urn:gen:0', subtree=True)
    assert len(done['copied']) == 3000 and len(done['assumed']) == 2999
    assert time.time() - started < 20


def test_a_relative_context_still_names_the_same_file(kms):
    docs = _docs(kms, 'model-instance.jsonld')
    docs[0]['@context'] = 'context.jsonld'
    _store(kms, docs, 'model-instance.jsonld')
    paste_entities(load(kms), _copy(kms, docs[0]['id']), CASE)
    assert _docs(kms)[-1]['@context'] == '../../../context.jsonld'


def test_the_server_copies_and_pastes(kms, monkeypatch):
    monkeypatch.setattr(edits.validation, 'publish', lambda *a, **k: None)
    uri = {'uri': f'file://{kms}/shacl.ttl'}
    taken = edits.copy_entities_feature(None, dict(uri, entity='urn:plasmacutter:1', subtree=True))
    assert taken['ok'] and taken['copied'] == ['urn:plasmacutter:1'] and taken['left']
    asked = dict(uri, content=taken['content'], case=os.path.join(kms, 'examples', CASE))
    assert edits.paste_entities_feature(None, dict(asked, check=True))['ok'] and 'urn:plasmacutter:1' not in _ids(kms)
    assert edits.paste_entities_feature(None, asked)['ok'] and 'urn:plasmacutter:1' in _ids(kms)
    for call in (edits.copy_entities_feature, edits.paste_entities_feature):
        assert not call(None, dict(asked, uri='file:///nowhere/x'))['ok']
        assert not call(None, dict(asked, content='[', entity='urn:none'))['ok']


# --- the extension -----------------------------------------------------------------

NODE = """
const Module = require('module');
const s = JSON.parse(process.argv[1]);
if (s.platform) { Object.defineProperty(process, 'platform', { value: s.platform }); }
const out = { asked: [], said: [], context: [], done: 0 };
const say = (kind) => async (text, options) => {
  out.said.push([kind, text, (options || {}).detail || '']); return s.answer; };
const load = Module._load;
Module._load = (name, ...rest) => name !== 'vscode' ? load(name, ...rest) : {
  window: { showInformationMessage: say('info'), showErrorMessage: say('error'), showWarningMessage: say('warning'),
    setStatusBarMessage: (text) => out.said.push(['status', text, '']) },
  workspace: { textDocuments: s.open || [] },
  commands: { executeCommand: async (...a) => out.context.push(a) } };
const { Clipboard } = require(s.src + '/clipboard.js');
const client = { sendRequest: async (method, params) => { out.asked.push([method, params]);
  const reply = s.replies[method.split('/')[1]].shift();
  if (reply.wait) { await new Promise((go) => setTimeout(go, reply.wait)); }
  if (reply.throws) { throw new Error(reply.throws); }
  return reply; } };
(async () => {
  const clip = new Clipboard({ client }, () => { out.done += 1; });
  if (s.script) {
    await new Function('clip', 'out', 's', `return (async () => { ${s.script} })()`)(clip, out, s);
    console.log(JSON.stringify(out));
    return;
  }
  if (s.node) { await clip.copy(s.node, s.subtree); }
  await clip.paste('file:///p/shacl.ttl', s.file);
  console.log(JSON.stringify(out));
})();
"""
TAKEN = {'ok': True, 'copied': ['urn:f', 'urn:g'], 'missing': [], 'content': '[1]'}
ROW = {'raw': {'kind': 'entity', 'entity': 'urn:f', 'file': '/p/m.jsonld'}, 'packageUri': 'file:///p/shacl.ttl'}


def _clip(**scenario):
    if shutil.which('node') is None:
        pytest.skip('node is not installed')
    scenario = dict({'src': SRC, 'node': ROW, 'file': '/p/c.jsonld', 'subtree': True}, **scenario)
    run = subprocess.run(['node', '-e', NODE, json.dumps(scenario)], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def _plan(**kw):
    return dict({'ok': True, 'file': '/p/c.jsonld', 'case': CASE, 'pasted': ['urn:f', 'urn:g'],
                 'present': [], 'included': [], 'same': [], 'shared': []}, **kw)


def test_copied_then_pasted_without_a_question():
    out = _clip(replies={'copyEntities': [TAKEN], 'pasteEntities': [_plan(), _plan()]})
    assert out['context'] == [['setContext', 'semforge.canPaste', False], ['setContext', 'semforge.canPaste', True]]
    assert out['done'] == 1
    assert out['asked'][0][1] == {'uri': ROW['packageUri'], 'entity': 'urn:f', 'file': '/p/m.jsonld', 'subtree': True}
    assert out['asked'][2][1]['content'] == '[1]' and out['asked'][2][1]['case'] == '/p/c.jsonld'
    assert [kind for kind, *_ in out['said']] == ['status', 'status']


@pytest.mark.parametrize('answer, replace', [('Replace', True), ('Paste only the other 1', False), (None, None)])
def test_it_asks_before_it_replaces(answer, replace):
    plan = _plan(pasted=['urn:g'], present=['urn:f'])
    out = _clip(answer=answer, replies={'copyEntities': [TAKEN], 'pasteEntities': [plan, plan]})
    written = [p for m, p in out['asked'] if m.endswith('pasteEntities') and 'check' not in p]
    assert [p['replace'] for p in written] == ([] if replace is None else [replace])
    assert 'urn:f' in next(text + detail for kind, text, detail in out['said'] if kind == 'warning')


@pytest.mark.parametrize('scenario, kind, text', [
    ({'node': None, 'replies': {}}, 'info', 'nothing to paste'),
    ({'file': None, 'replies': {'copyEntities': [TAKEN]}}, 'info', 'works in a test case'),
    ({'replies': {'copyEntities': [{'ok': False, 'error': 'gone'}]}}, 'error', 'gone'),
    ({'replies': {'copyEntities': [TAKEN], 'pasteEntities': [{'ok': False, 'error': 'shut'}]}}, 'error', 'shut'),
    ({'node': {'raw': {'kind': 'attribute'}}, 'replies': {}}, 'info', 'works on an entity'),
    ({'replies': {'copyEntities': [TAKEN], 'pasteEntities': [_plan(pasted=[], same=['urn:f'])]}},
     'info', 'just like that'),
    ({'replies': {'copyEntities': [TAKEN], 'pasteEntities': [_plan(pasted=[], included=['urn:f'])]}},
     'info', 'in a file it includes'),
    ({'open': [{'isDirty': True, 'uri': {'fsPath': '/p/c.jsonld'}}],
      'replies': {'copyEntities': [TAKEN], 'pasteEntities': [_plan()]}}, 'error', 'unsaved edits')])
def test_what_it_says_instead(scenario, kind, text):
    out = _clip(**scenario)
    assert any(k == kind and text in t for k, t, _ in out['said']), out['said']
    assert out['done'] == 0


OTHER = dict(TAKEN, content='[2]', copied=['urn:o'])


def _pasted(out):
    return [p['content'] for m, p in out['asked'] if m.endswith('pasteEntities')]


def test_a_paste_waits_for_the_copy_under_way():
    out = _clip(script="const c = clip.copy(s.node, true); await clip.paste('u', '/p/c.jsonld'); await c;",
                replies={'copyEntities': [dict(TAKEN, wait=50)], 'pasteEntities': [_plan(), _plan()]})
    assert _pasted(out) == ['[1]', '[1]'] and not any('nothing to paste' in t for _, t, _ in out['said'])


@pytest.mark.parametrize('failed', [{'ok': False, 'error': 'gone'}, {'throws': 'the server stopped'}])
def test_a_failed_copy_leaves_nothing_to_paste(failed):
    out = _clip(script="await clip.copy(s.node, true); await clip.copy(s.node, true).catch(() => 0); "
                       "await clip.paste('u', '/p/c.jsonld');",
                replies={'copyEntities': [TAKEN, failed]})
    assert _pasted(out) == [] and any('nothing to paste' in t for _, t, _ in out['said'])
    assert out['context'][-1] == ['setContext', 'semforge.canPaste', False]


def test_the_last_copy_started_is_the_one_held():
    out = _clip(script="await Promise.all([clip.copy(s.node, true), clip.copy(s.node, true)]); "
                       "out.held = clip.held.content; await clip.paste('u', '/p/c.jsonld');",
                replies={'copyEntities': [dict(TAKEN, wait=60), OTHER], 'pasteEntities': [_plan(), _plan()]})
    assert out['held'] == '[2]' and _pasted(out) == ['[2]', '[2]']
    assert [t for k, t, _ in out['said'] if k == 'status'][0].startswith('SemForge: urn:f copied')


def test_a_paste_keeps_what_was_copied_when_it_was_asked_for():
    out = _clip(script="await clip.copy(s.node, true); const p = clip.paste('u', '/p/c.jsonld'); "
                       "await clip.copy(s.node, true); await p;",
                replies={'copyEntities': [TAKEN, OTHER], 'pasteEntities': [dict(_plan(), wait=50), _plan()]})
    assert _pasted(out) == ['[1]', '[1]']


def test_two_pastes_are_one_after_the_other():
    out = _clip(script="await clip.copy(s.node, true); await Promise.all([clip.paste('u', '/p/a'), "
                       "clip.paste('u', '/p/b')]);",
                replies={'copyEntities': [TAKEN], 'pasteEntities': [dict(_plan(), wait=40)] + [_plan()] * 3})
    assert [p['case'] for m, p in out['asked'] if m.endswith('pasteEntities')] == ['/p/a', '/p/a', '/p/b', '/p/b']


def test_a_failed_paste_does_not_stop_the_next():
    out = _clip(script="await clip.copy(s.node, true); await clip.paste('u', '/p/a').catch(() => 0); "
                       "await clip.paste('u', '/p/b');",
                replies={'copyEntities': [TAKEN], 'pasteEntities': [{'throws': 'no'}, _plan(), _plan()]})
    assert out['done'] == 1


def test_the_write_carries_what_was_asked_about():
    out = _clip(replies={'copyEntities': [TAKEN], 'pasteEntities': [_plan(plan='p1'), _plan()]})
    assert [p.get('plan') for m, p in out['asked'] if m.endswith('pasteEntities')] == [None, 'p1']


def test_the_question_says_how_the_case_spells_the_id():
    plan = _plan(present=['ex:a'], pasted=[], spelled={'ex:a': 'https://e/a'})
    out = _clip(answer='Replace', replies={'copyEntities': [TAKEN], 'pasteEntities': [plan, plan]})
    detail = next(d for k, _, d in out['said'] if k == 'warning')
    assert 'ex:a (https://e/a there)' in detail and 'the id is spelled as copied' in detail


def test_unsaved_edits_are_found_behind_links(tmp_path):
    (tmp_path / 'real.jsonld').write_text('[]')
    os.symlink(tmp_path / 'real.jsonld', tmp_path / 'link.jsonld')
    real, link = str(tmp_path / 'real.jsonld'), str(tmp_path / 'link.jsonld')
    for opened, case in ((real, link), (link, real), (link, link)):
        out = _clip(file=case, open=[{'isDirty': True, 'uri': {'fsPath': opened}}], replies={
            'copyEntities': [TAKEN], 'pasteEntities': [_plan(file=case, real=real)]})
        assert any('unsaved edits' in t for _, t, _ in out['said']), (opened, case)


def test_on_windows_a_name_is_the_same_in_any_case():
    case = 'C:\\Pkg\\Examples\\c.jsonld'
    open_ = [{'isDirty': True, 'uri': {'fsPath': 'c:\\pkg\\examples\\C.jsonld'}}]

    def said(platform):
        out = _clip(file=case, open=open_, platform=platform, replies={
            'copyEntities': [TAKEN], 'pasteEntities': [_plan(file=case, real=case), _plan(file=case, real=case)]})
        return any('unsaved edits' in t for _, t, _ in out['said'])
    assert said('win32')
    assert not said('linux'), 'elsewhere case matters'


def test_edits_made_while_it_asked_are_not_lost():
    out = _clip(script="const doc = { isDirty: false, uri: { fsPath: '/p/c.jsonld' } }; s.open.push(doc); "
                       "await clip.copy(s.node, true); clip.askToReplace = async () => { doc.isDirty = true; "
                       "return true; }; await clip.paste('u', '/p/c.jsonld');", open=[],
                replies={'copyEntities': [TAKEN], 'pasteEntities': [_plan(present=['urn:f'], pasted=[])]})
    assert len(_pasted(out)) == 1 and any('unsaved edits' in t for _, t, _ in out['said'])


def test_nothing_pasted_says_what_was_left_out_too():
    taken = dict(TAKEN, missing=['urn:m'], left=['urn:l', 'urn:n'])
    out = _clip(replies={'copyEntities': [taken], 'pasteEntities': [_plan(pasted=[], same=['urn:f'])]})
    said = next(t for k, t, _ in out['said'] if k == 'info')
    assert 'urn:m written nowhere' in said and '2 entities pointed at, not copied' in said


def test_a_dropped_entity_defined_more_than_once_is_said():
    out = _clip(script="await clip.paste('u', '/p/c.jsonld', await clip.take(s.node, false));", replies={
        'copyEntities': [dict(TAKEN, copied=['urn:f'], repeated=['urn:f'])], 'pasteEntities': [_plan(), _plan()]})
    assert any('urn:f defined more than once' in t for k, t, _ in out['said'] if k == 'status')


def test_what_was_left_out_is_said():
    taken = dict(TAKEN, missing=['urn:m'], left=['urn:l', 'urn:n'], assumed=['urn:g'], repeated=['urn:f'])
    done = _plan(included=['urn:g'], pasted=['urn:f'])
    out = _clip(replies={'copyEntities': [taken], 'pasteEntities': [done, done]})
    copied, pasted = [text for kind, text, _ in out['said'] if kind == 'status']
    for words in ('urn:f and 1 below it copied', '1 of them by the data', '1 child is written nowhere',
                  '2 others pointed at', 'urn:f defined more than once'):
        assert words in copied, copied
    for words in ('urn:g left, in a file it includes', 'urn:m written nowhere', '2 entities pointed at, not copied'):
        assert words in pasted, pasted
    alone = _clip(replies={'copyEntities': [dict(TAKEN, copied=['urn:f'])], 'pasteEntities': [done, done]})
    assert 'it has no children' in alone['said'][0][1]


@pytest.mark.parametrize('answer, writes', [('Paste anyway', 2), (None, 1)])
def test_it_asks_before_it_changes_other_cases(answer, writes):
    plan = _plan(shared=['a.jsonld'])
    out = _clip(answer=answer, replies={'copyEntities': [TAKEN], 'pasteEntities': [plan, plan]})
    assert len([m for m, _ in out['asked'] if m.endswith('pasteEntities')]) == writes
    assert any(kind == 'warning' and 'a.jsonld' in detail for kind, _, detail in out['said'])


def test_the_commands_take_the_row_and_the_case(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.copySubtree', 'node': ROW,
                             'replies': {'semforge/copyEntities': TAKEN}})
    assert [r['params']['subtree'] for r in seen['requests'] if r['method'] == 'semforge/copyEntities'] == [True]
    seen = _drive(tmp_path, {'command': 'semforge.pasteEntity',
                             'node': {'file': '/p/c.jsonld', 'packageUri': 'file:///p/shacl.ttl'}, 'replies': {}})
    assert any('nothing to paste' in text for text in seen['info'])


def _sent(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


def test_the_keyboard_takes_the_selected_row(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.copyEntity', 'selection': dict(ROW, key='k'),
                             'replies': {'semforge/copyEntities': TAKEN}})
    assert [p['entity'] for p in _sent(seen, 'semforge/copyEntities')] == ['urn:f']
    assert not _sent(_drive(tmp_path, {'command': 'semforge.copyEntity', 'replies': {}}), 'semforge/copyEntities')


CASE_ROW = {'kind': 'example', 'label': 'c.jsonld', 'file': '/p/c.jsonld', 'children': [
    {'kind': 'entity', 'label': 'urn:h', 'entity': 'urn:h', 'file': '/p/c.jsonld', 'children': []}]}
TREE = {'ok': True, 'roots': [
    {'kind': 'group', 'label': 'Main', 'children': [
        {'kind': 'example', 'label': 'm.jsonld', 'children': [
            {'kind': 'entity', 'label': 'urn:f', 'entity': 'urn:f', 'file': '/p/m.jsonld', 'children': []}]}]},
    {'kind': 'group', 'label': 'Tests', 'children': [CASE_ROW]}]}


def test_paste_takes_the_case_of_the_selected_row(tmp_path):
    row = {'key': 'k', 'raw': CASE_ROW, 'packageUri': 'file:///p/shacl.ttl'}
    seen = _drive(tmp_path, {'command': 'semforge.copyEntity', 'node': ROW, 'selection': row,
                             'then': [{'command': 'semforge.pasteEntity'}],
                             'replies': {'semforge/copyEntities': TAKEN, 'semforge/pasteEntities': _plan(),
                                         'semforge/model': TREE}})
    assert [p['case'] for p in _sent(seen, 'semforge/pasteEntities')] == ['/p/c.jsonld'] * 2, seen['errors']


@pytest.mark.parametrize('onto, pasted', [(['Tests', 'c.jsonld'], True), (['Tests', 'c.jsonld', 'urn:h'], True),
                                          (['Main'], False), (['Main', 'm.jsonld', 'urn:f'], False), ([], False)])
def test_a_row_dragged_onto_a_case_is_pasted_there(tmp_path, onto, pasted):
    seen = _drive(tmp_path, {'mode': 'drop', 'drag': ['Main', 'm.jsonld', 'urn:f'], 'onto': onto, 'replies': {
        'semforge/model': TREE, 'semforge/copyEntities': TAKEN, 'semforge/pasteEntities': _plan()}})
    assert seen['errors'] == [], seen['errors']
    assert [p['subtree'] for p in _sent(seen, 'semforge/copyEntities')] == ([False] if pasted else [])
    assert [p['case'] for p in _sent(seen, 'semforge/pasteEntities')] == (['/p/c.jsonld'] * 2 if pasted else [])
    assert pasted or any('drop an entity on a test case' in text for text in seen['info'])


def test_a_dragged_row_that_is_no_entity_does_nothing(tmp_path):
    seen = _drive(tmp_path, {'mode': 'drop', 'drag': ['Main'], 'onto': ['Tests', 'c.jsonld'],
                             'replies': {'semforge/model': TREE}})
    assert seen['errors'] == [] and not _sent(seen, 'semforge/pasteEntities')


def test_the_menus_and_the_keys():
    with open(os.path.join(SRC, '..', 'package.json')) as handle:
        contributes = json.load(handle)['contributes']
    keys = {k['command']: (k['key'], k['mac'], k['when']) for k in contributes['keybindings']}
    # In the view's list only: never where text is typed, its find box included.
    when = 'focusedView == semforgeModel && listFocus && !inputFocus'
    assert keys['semforge.copyEntity'] == ('ctrl+c', 'cmd+c', when)
    assert keys['semforge.copySubtree'] == ('ctrl+shift+c', 'cmd+shift+c', when)
    assert keys['semforge.pasteEntity'] == ('ctrl+v', 'cmd+v', when)
    rows = {m['command']: m['when'] for m in contributes['menus']['view/item/context']}
    assert rows['semforge.copyEntity'] == rows['semforge.copySubtree'] == 'view == semforgeModel && viewItem == entity'
    assert rows['semforge.pasteEntity'].endswith('&& semforge.canPaste')
    for kind in ('example', 'entity', 'include', 'type', 'exampleEditable', 'exampleDataset', 'exampleSeries',
                 'attributeReadOnly'):
        assert kind in rows['semforge.pasteEntity']


def _page(kms, tmp_path, messages, paste=None):
    page = build_case_page(load(kms), os.path.join(kms, 'examples', CASE))
    node = {'raw': {'kind': 'example', 'file': page['file']}, 'packageUri': 'file:///p/shacl.ttl'}
    return page, _drive(tmp_path, {'command': 'semforge.openCasePage', 'node': node, 'webviewMessages': messages,
                                   'replies': {'semforge/casePage': dict(page, ok=True)},
                                   'commandReplies': {'semforge.pasteEntity': paste}})


def test_the_page_s_buttons_run_the_commands(kms, tmp_path):
    page, seen = _page(kms, tmp_path, [{'command': 'copyEntity', 'at': '0.0'}, {'command': 'copySubtree', 'at': '0.0'},
                                       {'command': 'paste'}])
    ran = {e['command']: e['args'][0] for e in seen['executed'] if re.search('(Entity|Subtree)$', e['command'])}
    card = page['files'][0]['cards'][0]
    entity = {'raw': {'kind': 'entity', 'entity': card['id'], 'file': page['file']},
              'packageUri': 'file:///p/shacl.ttl'}
    assert ran == {'semforge.copyEntity': entity, 'semforge.copySubtree': entity,
                   'semforge.pasteEntity': {'file': page['file'], 'packageUri': 'file:///p/shacl.ttl'}}


def _pressed(kms, tmp_path, page, script):
    from headless_chromium import chrome

    browser = chrome()
    (tmp_path / 'page.json').write_text(json.dumps(page))
    (tmp_path / 'after.js').write_text(script)
    out = tmp_path / 'page.html'
    run = subprocess.run(['node', os.path.join(SRC, '..', '..', 'tests', 'harness', 'render_casepage.js'), SRC,
                          str(tmp_path / 'page.json'), str(out), str(tmp_path / 'after.js')],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    dom = subprocess.run([browser, '--headless=new', '--no-sandbox', '--disable-gpu', '--virtual-time-budget=2000',
                          '--dump-dom', f'file://{out}'], capture_output=True, text=True, timeout=120).stdout
    found = re.search('data-posted="([^"]*)"', dom)
    posted = json.loads(html.unescape(found.group(1))) if found else []
    return [m for m in posted if m['command'] in ('paste', 'copyEntity', 'copySubtree')]


KEY = ("function key(on, more) { on.dispatchEvent(new KeyboardEvent('keydown', Object.assign("
       "{ key: 'v', ctrlKey: true, bubbles: true, cancelable: true }, more || {}))); }\n")


def test_the_key_and_the_buttons_in_the_page_itself(kms, tmp_path):
    case = build_case_page(load(kms), os.path.join(kms, 'examples', CASE))
    assert _pressed(kms, tmp_path, case, KEY + 'key(document.body); key(document);') == [{'command': 'paste'}] * 2
    assert _pressed(kms, tmp_path, case, KEY + 'key(document.body, { ctrlKey: false, metaKey: true });') == \
        [{'command': 'paste'}]
    for more in ('{ key: "c" }', '{ ctrlKey: false }', '{ altKey: true }', '{ shiftKey: true }', '{ repeat: true }'):
        assert _pressed(kms, tmp_path, case, KEY + f'key(document.body, {more});') == [], more
    # What is typed, or pasted, into a field is the field's.
    assert _pressed(kms, tmp_path, case, KEY + 'key(document.querySelector("input"));') == []
    assert _pressed(kms, tmp_path, dict(build_model_page(load(kms))), KEY + 'key(document.body);') == []
    clicked = _pressed(kms, tmp_path, case, 'for (const at of ["[data-copyentity]", "[data-copysubtree]", '
                       '"[data-pagecmd=paste]"]) { document.querySelector(at).click(); }')
    assert clicked == [{'command': 'copyEntity', 'at': '0.0'}, {'command': 'copySubtree', 'at': '0.0'},
                       {'command': 'paste'}]


def test_a_case_page_pastes_and_the_main_page_does_not(kms, tmp_path):
    from test_casepage import _render

    case = _render(tmp_path, build_case_page(load(kms), os.path.join(kms, 'examples', CASE)))
    main = _render(tmp_path, build_model_page(load(kms)))
    assert 'data-pagecmd="paste"' in case and 'data-pagecmd="paste"' not in main.split('<script')[0]
    for page in (case, main):
        assert 'data-copyentity=' in page and 'data-copysubtree=' in page


@pytest.mark.parametrize('at, file', [
    ({'webview': 'semforgeCasePage', 'entity': 'urn:filter:1'}, 'its card'),
    ({'webview': 'semforgeCasePage', 'entity': 'urn:elsewhere:1'}, 'the case'),
    ({'webview': 'semforgeShapePage', 'entity': 'urn:filter:1', 'case': '/p/examples/c.jsonld',
      'packageUri': 'file:///q/shacl.ttl'}, '/p/examples/c.jsonld'),
    ({'webview': 'semforgeTypePage', 'entity': 'urn:filter:1', 'packageUri': 'file:///q/shacl.ttl'}, None)])
def test_copy_from_an_id_on_a_page(kms, tmp_path, at, file):
    """Right-clicked on a page, the id is copied as the page has it."""
    page = build_case_page(load(kms), os.path.join(kms, 'examples', CASE))
    page['files'][-1]['cards'].append(dict(page['files'][0]['cards'][0], id='urn:filter:1',
                                           file='/p/examples/included.jsonld'))
    seen = _drive(tmp_path, {'command': 'semforge.openCasePage',
                             'node': {'raw': {'kind': 'example', 'file': page['file']},
                                      'packageUri': 'file:///p/shacl.ttl'},
                             'replies': {'semforge/casePage': dict(page, ok=True),
                                         'semforge/copyEntities': dict(TAKEN, ok=True)},
                             'then': [{'command': 'semforge.copyEntity', 'node': at}]})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/copyEntities']
    expected = {'its card': next(c['file'] for f in page['files'] for c in f['cards'] if c['id'] == 'urn:filter:1'),
                'the case': page['file']}.get(file, file)
    assert asked == [{'uri': at.get('packageUri', 'file:///p/shacl.ttl'), 'entity': at['entity'],
                      'file': expected, 'subtree': False}] if expected else \
        [{'uri': at['packageUri'], 'entity': at['entity'], 'subtree': False}]
