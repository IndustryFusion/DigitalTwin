"""A relationship may point at any entity, not only the shape's choices.

`other_entities` lists the rest: the model's own entities, named by their most
specific type, and those of the document being edited -- a case's entities
are not in the model. The server reads that document only inside the package.
"""

import json
from unittest import mock

from semforge.cooked.shapelink import other_entities, value_choices


def test_every_other_model_entity_by_its_most_specific_type(corpus):
    found, _ = value_choices(corpus, 'iffBaseEntities:Filter', 'hasCartridge')
    others = {o['value']: o['detail'] for o in other_entities(
        corpus, [c['value'] for c in found])}
    assert 'urn:cartridge:1' not in others, 'the shape\'s choices are listed apart'
    assert others['urn:plasmacutter:2'] == 'Plasmacutter'
    assert others['urn:workpiece:1'] == 'Workpiece'
    assert others['urn:filter:1'] == 'Filter'


def test_the_edited_document_s_entities_count_too(corpus, tmp_path):
    case = tmp_path / 'case.jsonld'
    case.write_text(json.dumps([
        {'id': 'urn:pump:7', 'type': 'Pump'},
        {'@id': 'urn:valve:3', '@type': ['Valve']},
        {'type': 'NoId'}]))
    others = {o['value']: o['detail'] for o in other_entities(corpus, (), str(case))}
    assert others['urn:pump:7'] == 'Pump' and others['urn:valve:3'] == 'Valve'


def test_the_server_reads_only_files_inside_the_package(corpus_path, tmp_path):
    from semforge.editor import server

    outside = tmp_path / 'elsewhere.jsonld'
    outside.write_text(json.dumps([{'id': 'urn:secret:1', 'type': 'X'}]))
    uri = f'file://{corpus_path}/shacl.ttl'
    answer = server.value_choices_feature(mock.MagicMock(), {
        'uri': uri, 'entityType': 'iffBaseEntities:Filter', 'attribute': 'hasCartridge',
        'relationship': True, 'file': str(outside)})
    values = [o['value'] for o in answer['others']]
    assert 'urn:secret:1' not in values and 'urn:workpiece:1' in values
    plain = server.value_choices_feature(mock.MagicMock(), {
        'uri': uri, 'entityType': 'iffBaseEntities:Filter', 'attribute': 'hasCartridge'})
    assert 'others' not in plain, 'a Property is offered no entities'
