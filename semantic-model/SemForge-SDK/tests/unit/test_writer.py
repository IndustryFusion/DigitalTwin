"""Invariant P2: an edit touches only the element edited."""

import pytest

from semforge.errors import PackageError
from semforge.rdfio import add_property_constraint

SOURCE = '''@prefix ex: <https://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .

# This comment explains why FirstShape needs a two-hop inverse path, and it is
# the only place that reasoning is written down.
ex:FirstShape a sh:NodeShape ;
    sh:targetClass ex:C ;
    sh:property [ sh:path ex:existing ; sh:minCount 1 ] .

# SecondShape is untouched by the edit below.
ex:SecondShape a sh:NodeShape ;
    sh:targetClass ex:D .
'''


def test_p2_only_the_edited_shape_changes():
    updated = add_property_constraint(
        None, 'https://example.org/FirstShape', 'ex:added',
        [('sh:minCount', '1'), ('sh:datatype', 'xsd:string')], source=SOURCE)

    before = SOURCE.split('ex:SecondShape', 1)[1]
    after = updated.split('ex:SecondShape', 1)[1]
    assert before == after, 'an unrelated shape was modified'


def test_p2_comments_survive_byte_identical():
    """rdflib would have deleted all of these on reserialisation."""
    updated = add_property_constraint(
        None, 'https://example.org/FirstShape', 'ex:added',
        [('sh:minCount', '1')], source=SOURCE)
    for line in SOURCE.splitlines():
        if line.startswith('#'):
            assert line in updated


def test_the_constraint_is_actually_added_and_parses():
    from rdflib import Graph
    updated = add_property_constraint(
        None, 'https://example.org/FirstShape', 'ex:added',
        [('sh:minCount', '1')], source=SOURCE)
    assert 'ex:added' in updated

    graph = Graph()
    graph.parse(data=updated, format='turtle')     # still valid Turtle
    assert (None, None, None) in graph
    assert len(graph) > len(Graph().parse(data=SOURCE, format='turtle'))


def test_editing_an_absent_shape_is_an_error_not_a_new_statement():
    """Appending a second statement for an unknown subject is valid Turtle and
    a confusing diff, so it is refused instead."""
    with pytest.raises(PackageError):
        add_property_constraint(None, 'https://example.org/Nope', 'ex:x',
                                [('sh:minCount', '1')], source=SOURCE)


def test_the_real_shapes_file_can_be_edited(corpus, tmp_path):
    from rdflib import Graph
    original = open(corpus.sources['shapes']).read()
    updated = add_property_constraint(
        corpus.sources['shapes'],
        'https://industryfusion.github.io/contexts/example/v0/base_shacl/FilterShape',
        'iffBaseEntities:hasStrength', [('sh:minCount', '1')])

    assert len(updated) > len(original)
    graph = Graph()
    graph.parse(data=updated, format='turtle')

    # Everything before the edited shape is byte-identical.
    marker = ':CutterShape'
    assert original.split(marker)[0] == updated.split(marker)[0]
