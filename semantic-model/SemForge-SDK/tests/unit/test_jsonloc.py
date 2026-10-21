"""Line numbers inside a JSON document, and the nodes that use them."""

import json

import pytest

from semforge.cooked.examples import build_suite, flatten
from semforge.cooked.jsonloc import entity_index, locate


def test_it_locates_keys_and_values(corpus):
    with open(corpus.sources['model']) as handle:
        text = handle.read()
    lines = text.splitlines()
    index = locate(text)

    position = entity_index(text, 'urn:filter:1')
    assert position is not None

    key = (position, 'iffBaseEntities:hasStrength')
    assert 'hasStrength' in lines[index[key] - 1]

    value = (position, 'iffBaseEntities:hasStrength', 0, 'value')
    assert '"value"' in lines[index[value] - 1]


def test_each_observation_gets_its_own_line(corpus):
    """A series that pointed every row at one line would be useless."""
    with open(corpus.sources['model']) as handle:
        text = handle.read()
    index = locate(text)
    position = entity_index(text, 'urn:filter:1')

    seen = {index[(position, 'iffBaseEntities:hasStrength', i, 'value')]
            for i in range(4)}
    assert len(seen) == 4


def test_a_string_containing_braces_does_not_derail_the_scan():
    text = '[{"id": "urn:x:1", "note": "a } and a { inside", "n": 1}]'
    index = locate(text)
    assert index[(0, 'n')] == 1
    assert index[(0, 'note')] == 1


def test_escapes_keep_the_scan_aligned():
    """An escaped quote must not end the string early.

    Built with json.dumps so the fixture is valid by construction -- the first
    hand-written version was not, and the scanner was blamed for it.
    """
    document = [{'a': 'x"y', 'b': 2}]
    text = '[\n ' + json.dumps(document[0]) + '\n]'
    assert json.loads(text) == document
    index = locate(text)
    assert index[(0, 'b')] == 2
    assert index[(0, 'a')] == 2


def test_an_unknown_entity_has_no_index(corpus):
    with open(corpus.sources['model']) as handle:
        text = handle.read()
    assert entity_index(text, 'urn:nope:1') is None


# --- what the tree does with them -------------------------------------------

def test_every_example_node_can_be_pointed_at(corpus):
    """Selecting a row moves the editor, so a row without a location is dead."""
    for _, node in flatten(build_suite(corpus)):
        if node.kind in ('entity', 'attribute', 'instance', 'dataset', 'meta'):
            assert node.defined_at, f'{node.kind} {node.label} has no location'
            file_part, _, line = node.defined_at.rpartition(':')
            assert file_part.endswith(('.jsonld', '.json')) and line.isdigit()


def test_an_attribute_points_at_the_attribute_not_its_current_value(corpus):
    """Even when the row was folded onto the current instance's value.

    That is where you would edit the whole attribute.
    """
    with open(corpus.sources['model']) as handle:
        text = handle.read()
    index = locate(text)
    position = entity_index(text, 'urn:filter:1')
    expected = index[(position, 'iffBaseEntities:hasStrength')]

    node = next(n for _, n in flatten(build_suite(corpus))
                if n.kind == 'attribute' and n.label == 'hasStrength'
                and n.entity == 'urn:filter:1'
                and n.file.endswith('model-instance.jsonld'))
    assert int(node.defined_at.rpartition(':')[2]) == expected


def test_observations_point_at_their_own_values(corpus):
    node = next(n for _, n in flatten(build_suite(corpus))
                if n.kind == 'attribute' and n.label == 'hasStrength'
                and n.entity == 'urn:filter:1'
                and n.file.endswith('model-instance.jsonld'))
    lines = [int(c.defined_at.rpartition(':')[2]) for c in node.children]
    assert len(set(lines)) == len(lines) == 4
    assert lines == sorted(lines)


def test_the_location_names_the_file_the_node_came_from(corpus):
    """An example's rows point into the example, not into the shipped model."""
    for _, node in flatten(build_suite(corpus)):
        if node.defined_at and node.file:
            assert node.defined_at.startswith(node.file)


@pytest.mark.parametrize('source', ['tree.js', 'model.js'])
def test_clicking_a_row_does_not_open_an_editor_prompt(source):
    """A single click should show you the row, not pop an input box.

    Clicking used to fire the edit command, which both surprised and replaced
    the one thing a click should do. Editing is the inline pencil.
    """
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), '..', 'vscode', 'src', source)
    with open(os.path.abspath(path)) as handle:
        text = handle.read()
    assert 'onDidChangeSelection' in text, 'selection must reveal the row'
    assert "command: 'semforge.editValue'" not in text
    assert "command: 'semforge.editConstraint'," not in text
