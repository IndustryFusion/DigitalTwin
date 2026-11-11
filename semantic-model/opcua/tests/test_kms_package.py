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
"""owl2kms.py and lib/kms_package.py (openspec gh-944-opcua-kms-package)."""

import hashlib
import os
import shutil

import pytest
import yaml
from rdflib import Graph, OWL

import owl2kms
from lib.kms_package import PackagingError, _rewrite_imports, build_package, import_closure

HEADER = '@prefix owl: <http://www.w3.org/2002/07/owl#> .\n'


def _ontology(path, *imports, iri=None):
    lines = [HEADER, f'<{iri or "urn:" + os.path.basename(path)}> a owl:Ontology']
    if imports:
        lines.append(' ; owl:imports ' + ', '.join(f'<{i}>' for i in imports))
    path.write_text(''.join(lines) + ' .\n')
    return str(path)


def _inputs(src):
    """A small chain output: core <- di <- instance, as nodeset2owl writes it
    for local inputs (file:/// imports), plus owl2instances' files."""
    src.mkdir(parents=True, exist_ok=True)
    core = _ontology(src / 'core.owl.ttl')
    di = _ontology(src / 'di.owl.ttl', f'file://{core}')
    instance = _ontology(src / 'instance.owl.ttl', f'file://{di}', f'file://{core}')
    (src / 'shacl.ttl').write_text(HEADER)
    (src / 'instances.jsonld').write_text('[]\n')
    (src / 'context.jsonld').write_text('{"@context": {}}\n')
    return instance


def _build(src, out, **kwargs):
    instance = _inputs(src)
    kwargs.setdefault('name', 'opcua-test')
    return build_package(str(out), [instance], str(src / 'shacl.ttl'),
                         str(src / 'instances.jsonld'), str(src / 'context.jsonld'),
                         'https://example.org/context.jsonld', **kwargs)


def _digest(root):
    """The digest semforge pack would give: SHA256SUMS over all files."""
    lines = []
    for here, _, files in os.walk(root):
        for name in files:
            path = os.path.join(here, name)
            rel = os.path.relpath(path, root).replace(os.sep, '/')
            lines.append(f'{hashlib.sha256(open(path, "rb").read()).hexdigest()}  {rel}\n')
    return hashlib.sha256(''.join(sorted(lines, key=str.encode)).encode()).hexdigest()


# --- the closure -------------------------------------------------------------------

def test_the_closure_follows_file_imports_and_puts_imports_first(tmp_path):
    core = _ontology(tmp_path / 'core.owl.ttl')
    di = _ontology(tmp_path / 'di.owl.ttl', f'file://{tmp_path}/core.owl.ttl')
    pumps = _ontology(tmp_path / 'pumps.owl.ttl', f'file://{tmp_path}/di.owl.ttl',
                      f'file://{tmp_path}/core.owl.ttl')
    instance = _ontology(tmp_path / 'instance.owl.ttl', f'file://{tmp_path}/pumps.owl.ttl')
    assert list(import_closure([instance])) == [core, di, pumps, instance]


def test_a_url_import_is_kept_as_a_url_and_a_cycle_ends():
    graph = {'/a.ttl': ['https://example.org/base.ttl', '/b.ttl'],
             '/b.ttl': ['/a.ttl'],
             'https://example.org/base.ttl': []}
    assert list(import_closure(['/a.ttl'], graph.__getitem__)) == \
        ['/b.ttl', 'https://example.org/base.ttl', '/a.ttl']


def test_standard_vocabularies_are_neither_copied_nor_followed():
    graph = {'/i.ttl': ['https://example.org/base.ttl'],
             'https://example.org/base.ttl': ['http://www.w3.org/2000/01/rdf-schema#',
                                              'https://example.org/v0/ngsild.ttl'],
             'http://www.w3.org/2000/01/rdf-schema#': ['/never.ttl'],
             'https://example.org/v0/ngsild.ttl': ['/never.ttl']}
    assert list(import_closure(['/i.ttl'], graph.__getitem__)) == \
        ['https://example.org/base.ttl', '/i.ttl']


# --- The OPC UA chain produces a KMS package ----------------------------------------

def test_the_package_layout(tmp_path):
    _build(tmp_path / 'src', tmp_path / 'pkg')
    out = tmp_path / 'pkg'
    assert sorted(os.listdir(out)) == ['context.jsonld', 'kms.yaml', 'knowledge',
                                       'model-instance.jsonld', 'shacl.ttl', 'vocabulary']
    assert sorted(os.listdir(out / 'knowledge')) == ['core.owl.ttl', 'di.owl.ttl',
                                                     'instance.owl.ttl']
    assert os.listdir(out / 'vocabulary') == ['ngsild.ttl']


def test_existing_output(tmp_path):
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / 'x').write_text('')
    with pytest.raises(PackagingError, match='exists and is not empty'):
        _build(tmp_path / 'src', tmp_path / 'pkg')
    assert os.listdir(tmp_path / 'pkg') == ['x']


def test_no_examples_suite(tmp_path):
    _build(tmp_path / 'src', tmp_path / 'pkg')
    assert not any(os.path.exists(tmp_path / 'pkg' / d) for d in ('examples', 'model'))


# --- The descriptor names and versions the package -------------------------------------

def test_default_version(tmp_path):
    _build(tmp_path / 'src', tmp_path / 'pkg', name='opcua-pumps')
    text = (tmp_path / 'pkg' / 'kms.yaml').read_text()
    for line in ('name: opcua-pumps', 'version: 0.1.0', 'format: 1',
                 'published: "https://example.org/context.jsonld"',
                 'source: vocabulary/ngsild.ttl', '  local: context.jsonld'):
        assert line in text


@pytest.mark.parametrize('version', ['1.0', 'v1.0.0', '01.0.0'])
def test_invalid_version(tmp_path, version):
    with pytest.raises(PackagingError, match='MAJOR.MINOR.PATCH'):
        _build(tmp_path / 'src', tmp_path / 'pkg', version=version)
    assert not os.path.exists(tmp_path / 'pkg')


@pytest.mark.parametrize('name', ['', '-pumps', 'opcua pumps'])
def test_invalid_name(tmp_path, name):
    with pytest.raises(PackagingError, match='name'):
        _build(tmp_path / 'src', tmp_path / 'pkg', name=name)


# --- Nothing refers to the machine that built the package -----------------------------

def test_local_inputs(tmp_path):
    src = tmp_path / 'deep' / 'build' / 'src'
    _build(src, tmp_path / 'pkg')
    out = tmp_path / 'pkg'
    for here, _, files in os.walk(out):
        for name in files:
            text = open(os.path.join(here, name), encoding='utf-8').read()
            assert 'file:' not in text, name
            assert str(src) not in text, name
    graph = Graph().parse(out / 'knowledge' / 'instance.owl.ttl')
    assert sorted(str(o) for o in graph.objects(None, OWL.imports)) == \
        ['urn:core.owl.ttl', 'urn:di.owl.ttl']
    assert 'knowledge/core.owl.ttl <- core.owl.ttl' in (out / 'kms.yaml').read_text()


def test_only_the_imports_change(tmp_path):
    _build(tmp_path / 'src', tmp_path / 'pkg')
    assert (tmp_path / 'pkg' / 'knowledge' / 'core.owl.ttl').read_text() == \
        (tmp_path / 'src' / 'core.owl.ttl').read_text()


# --- Assembly is reproducible -----------------------------------------------------------

def test_two_builds(tmp_path):
    _build(tmp_path / 'one' / 'src', tmp_path / 'one' / 'pkg')
    _build(tmp_path / 'two' / 'deeper' / 'src', tmp_path / 'two' / 'deeper' / 'pkg')
    assert _digest(tmp_path / 'one' / 'pkg') == _digest(tmp_path / 'two' / 'deeper' / 'pkg')


def test_two_sources_with_one_file_name_do_not_collide(tmp_path):
    (tmp_path / 'a').mkdir()
    (tmp_path / 'b').mkdir()
    first = _ontology(tmp_path / 'a' / 'base.ttl', iri='urn:a:base')
    second = _ontology(tmp_path / 'b' / 'base.ttl', f'file://{first}', iri='urn:b:base')
    for name in ('shacl.ttl', 'm.jsonld', 'c.jsonld'):
        (tmp_path / name).write_text('{}' if name.endswith('jsonld') else HEADER)
    out = tmp_path / 'pkg'
    build_package(str(out), [second], str(tmp_path / 'shacl.ttl'), str(tmp_path / 'm.jsonld'),
                  str(tmp_path / 'c.jsonld'), 'https://example.org/c.jsonld', name='x')
    assert sorted(os.listdir(out / 'knowledge')) == ['base-2.ttl', 'base.ttl']


# --- The package holds the model and its whole type system ----------------------------

def test_unreadable_import(tmp_path):
    src = tmp_path / 'src'
    instance = _inputs(src)
    os.unlink(src / 'core.owl.ttl')
    with pytest.raises(PackagingError, match='core.owl.ttl'):
        build_package(str(tmp_path / 'pkg'), [instance], str(src / 'shacl.ttl'),
                      str(src / 'instances.jsonld'), str(src / 'context.jsonld'),
                      'https://example.org/context.jsonld', name='x')
    assert not os.path.exists(tmp_path / 'pkg')


def test_an_ontology_without_a_header_cannot_be_named(tmp_path):
    src = tmp_path / 'src'
    instance = _inputs(src)
    (src / 'core.owl.ttl').write_text(HEADER)
    with pytest.raises(PackagingError, match='declares no owl:Ontology'):
        build_package(str(tmp_path / 'pkg'), [instance], str(src / 'shacl.ttl'),
                      str(src / 'instances.jsonld'), str(src / 'context.jsonld'),
                      'https://example.org/context.jsonld', name='x')


# --- the command line ---------------------------------------------------------------------

def test_the_command_line(tmp_path, capsys):
    src = tmp_path / 'src'
    instance = _inputs(src)
    code = owl2kms.main(owl2kms.parse_args([instance, '-s', str(src / 'shacl.ttl'),
                                            '-m', str(src / 'instances.jsonld'),
                                            '-c', str(src / 'context.jsonld'),
                                            '-n', 'opcua-test', '-o', str(tmp_path / 'pkg')]))
    assert code == 0 and (tmp_path / 'pkg' / 'kms.yaml').exists()
    bad = owl2kms.main(owl2kms.parse_args([instance, '-s', str(src / 'shacl.ttl'),
                                           '-m', str(src / 'instances.jsonld'),
                                           '-c', str(src / 'context.jsonld'),
                                           '-n', 'x', '-v', '1.0', '-o', str(tmp_path / 'p2')]))
    assert bad == 1 and 'MAJOR.MINOR.PATCH' in capsys.readouterr().err


def test_the_default_vocabulary_is_the_repository_copy(tmp_path):
    from lib.kms_package import DEFAULT_NGSILD
    _build(tmp_path / 'src', tmp_path / 'pkg')
    assert open(tmp_path / 'pkg' / 'vocabulary' / 'ngsild.ttl', 'rb').read() == \
        open(DEFAULT_NGSILD, 'rb').read()
    shutil.rmtree(tmp_path / 'pkg')


# --- the review of #945: speed and layout ---------------------------------------------

def test_create_list_builds_an_rdf_list_with_counter_labels():
    """create_list must not go through rdflib's Collection, whose list nodes
    are random; the counter labels keep shacl.ttl in a stable order."""
    from rdflib import Graph, Literal, RDF
    from rdflib.collection import Collection
    from lib.utils import create_list, new_bnode

    g = Graph()
    head = create_list(g, [1, 2, 3], int)
    assert list(Collection(g, head)) == [Literal(1), Literal(2), Literal(3)]
    assert str(head).startswith('n')
    first, second = new_bnode(), new_bnode()
    assert int(str(second)[1:]) == int(str(first)[1:]) + 1
    assert (None, RDF.rest, RDF.nil) in g


def test_origins_do_not_depend_on_the_layout(tmp_path):
    """An import outside the input directory: kms.yaml, and so the digest,
    must not change with the directory depth."""
    def chain(where):
        deps = where / 'deps'
        deps.mkdir(parents=True)
        core = _ontology(deps / 'core.owl.ttl')
        src = where / 'a' / 'b' / 'src'
        src.mkdir(parents=True)
        instance = _ontology(src / 'instance.owl.ttl', f'file://{core}')
        for name in ('shacl.ttl', 'instances.jsonld', 'context.jsonld'):
            (src / name).write_text('[]\n' if name.endswith('jsonld') else HEADER)
        build_package(str(where / 'pkg'), [instance], str(src / 'shacl.ttl'),
                      str(src / 'instances.jsonld'), str(src / 'context.jsonld'),
                      'https://example.org/context.jsonld', name='x')
        return where / 'pkg'

    one = chain(tmp_path / 'one')
    two = chain(tmp_path / 'two' / 'much' / 'deeper')
    assert (one / 'kms.yaml').read_text() == (two / 'kms.yaml').read_text()
    assert 'knowledge/core.owl.ttl <- core.owl.ttl' in (one / 'kms.yaml').read_text()
    assert _digest(one) == _digest(two)


def test_one_ontology_reached_at_two_paths_is_one_file(tmp_path):
    """Build outputs copied from another directory still import the originals
    there: the same ontology must not end up twice in the package."""
    original = tmp_path / 'original'
    original.mkdir()
    core_there = _ontology(original / 'core.owl.ttl')
    copy = tmp_path / 'copy'
    copy.mkdir()
    core_here = _ontology(copy / 'core.owl.ttl')
    di = _ontology(copy / 'di.owl.ttl', f'file://{core_there}')
    instance = _ontology(copy / 'instance.owl.ttl', f'file://{di}', f'file://{core_here}')
    for name in ('shacl.ttl', 'instances.jsonld', 'context.jsonld'):
        (copy / name).write_text('[]\n' if name.endswith('jsonld') else HEADER)
    build_package(str(tmp_path / 'pkg'), [instance], str(copy / 'shacl.ttl'),
                  str(copy / 'instances.jsonld'), str(copy / 'context.jsonld'),
                  'https://example.org/context.jsonld', name='x')
    assert sorted(os.listdir(tmp_path / 'pkg' / 'knowledge')) == \
        ['core.owl.ttl', 'di.owl.ttl', 'instance.owl.ttl']


def test_two_different_files_with_one_ontology_iri(tmp_path):
    a = tmp_path / 'a'
    a.mkdir()
    one = _ontology(a / 'core.owl.ttl', iri='urn:core')
    b = tmp_path / 'b'
    b.mkdir()
    (b / 'core.owl.ttl').write_text(HEADER + '<urn:core> a owl:Ontology .\n<urn:x> a owl:Class .\n')
    instance = _ontology(b / 'instance.owl.ttl', f'file://{one}', f'file://{b}/core.owl.ttl')
    for name in ('shacl.ttl', 'instances.jsonld', 'context.jsonld'):
        (b / name).write_text('[]\n' if name.endswith('jsonld') else HEADER)
    with pytest.raises(PackagingError, match='both declare the ontology urn:core'):
        build_package(str(tmp_path / 'pkg'), [instance], str(b / 'shacl.ttl'),
                      str(b / 'instances.jsonld'), str(b / 'context.jsonld'),
                      'https://example.org/context.jsonld', name='x')


# --- which imports are followed ----------------------------------------------------

def test_a_url_cannot_make_the_tool_read_a_local_file():
    graph = {'/i.ttl': ['https://example.org/base.ttl'],
             'https://example.org/base.ttl': ['file:///home/someone/secret.ttl']}
    with pytest.raises(PackagingError, match='only http'):
        import_closure(['/i.ttl'], graph.__getitem__)


@pytest.mark.parametrize('iri', ['ftp://example.org/x.ttl', 'urn:x', 'data:,x'])
def test_other_schemes_are_refused(iri):
    with pytest.raises(PackagingError, match='only http'):
        import_closure(['/i.ttl'], {'/i.ttl': [iri]}.__getitem__)
    graph = {'/i.ttl': ['https://example.org/base.ttl'], 'https://example.org/base.ttl': [iri]}
    with pytest.raises(PackagingError, match='only http'):
        import_closure(['/i.ttl'], graph.__getitem__)


def test_an_excluded_import_of_another_scheme_is_left_alone():
    graph = {'/i.ttl': ['urn:x']}
    assert list(import_closure(['/i.ttl'], graph.__getitem__, exclude=('urn:',))) == ['/i.ttl']


def _side_files(src):
    (src / 'shacl.ttl').write_text(HEADER)
    (src / 'instances.jsonld').write_text('[]\n')
    (src / 'context.jsonld').write_text('{"@context": {}}\n')


def test_a_relative_import_resolves_against_its_file(tmp_path, monkeypatch):
    src = tmp_path / 'src'
    src.mkdir()
    _ontology(src / 'core.owl.ttl', iri='urn:core')
    instance = _ontology(src / 'instance.owl.ttl', 'core.owl.ttl')
    _side_files(src)
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    build_package(str(tmp_path / 'pkg'), [instance], str(src / 'shacl.ttl'),
                  str(src / 'instances.jsonld'), str(src / 'context.jsonld'),
                  'https://example.org/context.jsonld', name='x')
    text = (tmp_path / 'pkg' / 'knowledge' / 'instance.owl.ttl').read_text()
    assert '<urn:core>' in text and 'core.owl.ttl>' not in text


def test_the_rewrite_does_not_depend_on_the_order_of_the_imports(tmp_path):
    # b's new IRI is what a writes for c: the import of c, once rewritten,
    # must not be rewritten again, and b's must not be taken for c's.
    c = _ontology(tmp_path / 'c.ttl')
    b = _ontology(tmp_path / 'b.ttl')
    a = _ontology(tmp_path / 'a.ttl', f'file://{b}', f'file://{c}')
    closure = import_closure([a])
    iri_of = {c: 'urn:c', b: f'file://{c}', a: 'urn:a'}
    text = _rewrite_imports(a, open(a, 'rb').read(), closure[a], iri_of).decode()
    assert f'owl:imports <file://{c}>, <urn:c>' in text


def test_the_published_context_is_quoted_in_kms_yaml(tmp_path):
    src = tmp_path / 'src'
    instance = _inputs(src)
    build_package(str(tmp_path / 'pkg'), [instance], str(src / 'shacl.ttl'),
                  str(src / 'instances.jsonld'), str(src / 'context.jsonld'),
                  'https://example.org/c.jsonld\nversion: 9.9.9', name='x')
    config = yaml.safe_load((tmp_path / 'pkg' / 'kms.yaml').read_text())
    assert config['version'] == '0.1.0'
    assert config['context']['published'] == 'https://example.org/c.jsonld\nversion: 9.9.9'
