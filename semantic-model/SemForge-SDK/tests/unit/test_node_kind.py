"""`sh:nodeKind sh:BlankNode` on an attribute restates the NGSI-LD encoding.

An attribute IS a blank node carrying hasValue/hasObject, so writing it decides
nothing. The cooked view hides it; export puts it back, because a SHACL
consumer knows nothing of the convention.
"""

import re
import shutil

import pytest
from rdflib import Graph
from rdflib.compare import isomorphic

from semforge.cooked.tree import (VALUE_PATHS, build_tree, flatten,
                                  forward_attribute_path)
from semforge.package import load
from semforge.rdfio import index_file, property_blocks
from semforge.target.export import complete_node_kinds, export
from semforge.validate.shapes import node_shapes


def _levels(package):
    """(attribute-level, value-level) nodeKind values found in the shapes."""
    with open(package.sources['shapes']) as handle:
        text = handle.read()
    index = index_file(package.sources['shapes'])
    attribute, value = [], []

    def walk(block, is_value):
        found = block.parameters.get('sh:nodeKind')
        (value if is_value else attribute).append(
            found[2] if found else None)
        for child in block.children:
            walk(child, child.path in VALUE_PATHS)

    for shape in node_shapes(package.shapes):
        block = index.block_for(shape)
        if block:
            for group in property_blocks(text, block):
                walk(group, False)
    return attribute, value


def test_the_claim_holds_at_the_attribute_level(corpus):
    attribute, _ = _levels(corpus)
    stated = [v for v in attribute if v is not None]
    assert stated and set(stated) == {'sh:BlankNode'}


def test_but_not_at_the_value_level(corpus):
    """A value's nodeKind is a real decision, and the kms uses three."""
    _, value = _levels(corpus)
    stated = {v for v in value if v is not None}
    assert 'sh:IRI' in stated and 'sh:Literal' in stated
    assert len(stated) > 1


def test_an_inverse_path_is_not_an_attribute_node(corpus):
    """CartridgeShape's exclusivity rule walks BACK to the filters pointing here.

    Its focus is an entity IRI, so BlankNode there would be wrong rather than
    missing -- which is why completion is scoped to forward paths.
    """
    assert not forward_attribute_path(
        '( [ sh:inversePath ngsild:hasObject ] [ sh:inversePath iff:hasCartridge ] )')
    assert not forward_attribute_path('ngsild:hasValue')
    assert forward_attribute_path('iffBaseEntities:hasStrength')
    assert forward_attribute_path('<https://example.org/hasThing>')


# --- the tree ----------------------------------------------------------------

def test_the_implied_node_kind_is_hidden(corpus):
    shown = [n for _, n in flatten(build_tree(corpus))
             if n.parameter == 'sh:nodeKind']
    assert shown, 'value-level nodeKind must still be shown'
    for node in shown:
        slot = node.path_chain[-1] if node.path_chain else ''
        assert slot in VALUE_PATHS, \
            f'attribute-level nodeKind should be hidden, saw {node.value} at {slot}'


def test_a_non_blanknode_attribute_kind_stays_visible(tmp_path, corpus):
    """Hiding that would hide a modelling error rather than boilerplate."""
    package = tmp_path / 'pkg'
    package.mkdir()
    shutil.copy(corpus.sources['knowledge'], package / 'knowledge.ttl')
    shutil.copy(corpus.sources['model'], package / 'model-instance.jsonld')
    (package / 'shacl.ttl').write_text('''
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://example.org/> .
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
    sh:property [ sh:path ex:odd ; sh:nodeKind sh:IRI ; sh:minCount 1 ] .
''')
    shown = [n for _, n in flatten(build_tree(load(str(package))))
             if n.parameter == 'sh:nodeKind']
    assert [n.value for n in shown] == ['sh:IRI']


# --- export ------------------------------------------------------------------

def test_a_complete_package_exports_byte_identically(corpus, tmp_path):
    """H5 survives: completion that adds nothing changes nothing."""
    with open(corpus.sources['shapes']) as handle:
        source = handle.read()
    completed, added = complete_node_kinds(source)
    assert added == 0 and completed == source


def test_a_missing_attribute_kind_is_restored(tmp_path, corpus):
    with open(corpus.sources['shapes']) as handle:
        source = handle.read()

    # Drop it from one attribute block only.
    marker = 'sh:nodeKind sh:BlankNode ;\n            sh:order 10 ;\n            sh:path iffBaseEntities:hasStrength'
    assert marker in source
    stripped = source.replace(
        marker, 'sh:order 10 ;\n            sh:path iffBaseEntities:hasStrength', 1)
    assert stripped != source

    completed, added = complete_node_kinds(stripped)
    assert added == 1

    original, restored = Graph(), Graph()
    original.parse(data=source, format='turtle')
    restored.parse(data=completed, format='turtle')
    assert isomorphic(original, restored), 'completion should restore exactly'


def test_completion_never_touches_the_inverse_path(corpus):
    """The one attribute-level block without a nodeKind must stay without one."""
    with open(corpus.sources['shapes']) as handle:
        source = handle.read()
    completed, added = complete_node_kinds(source)
    assert added == 0
    assert completed.count('sh:inversePath') == source.count('sh:inversePath')


def test_export_reports_what_it_completed(tmp_path, corpus):
    package = tmp_path / 'pkg'
    package.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], package / name)
    for extra in ('context.jsonld', 'semforge.yaml'):
        shutil.copy(f'{corpus.path}/{extra}', package / extra)

    shapes = package / 'shacl.ttl'
    shapes.write_text(re.sub(r'\n\s*sh:nodeKind sh:BlankNode ;', '',
                             shapes.read_text(), count=2))

    written = export(load(str(package)), str(tmp_path / 'out'))
    assert written.get('node_kinds_added') == 2
    Graph().parse(written['shapes'], format='turtle')


def test_the_exported_shapes_always_state_it(tmp_path, corpus):
    """A SHACL consumer knows nothing of the NGSI-LD convention."""
    written = export(corpus, str(tmp_path / 'out'))
    with open(written['shapes']) as handle:
        exported = handle.read()
    index = index_file(written['shapes'])

    def walk(block, is_value):
        if not is_value and forward_attribute_path(block.path):
            assert 'sh:nodeKind' in block.parameters, \
                f'{block.path} exported without a nodeKind'
        for child in block.children:
            walk(child, child.path in VALUE_PATHS)

    for shape in node_shapes(corpus.shapes):
        block = index.block_for(shape)
        if block:
            for group in property_blocks(exported, block):
                walk(group, False)


@pytest.mark.parametrize('path,expected', [
    ('iff:hasState', True),
    ('ngsild:hasObject', False),
    ('( [ sh:inversePath ngsild:hasObject ] )', False),
    ('[ sh:inversePath iff:x ]', False),
    ('', False),
])
def test_forward_attribute_path(path, expected):
    assert forward_attribute_path(path) is expected
