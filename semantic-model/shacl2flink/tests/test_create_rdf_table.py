import os.path
from unittest.mock import patch, MagicMock
import create_rdf_table


@patch('create_rdf_table.argparse')
def test_input_arguments(mock_argparse):
    parser = mock_argparse.ArgumentParser.return_value
    parser.parse_args.return_value = "args"
    args = create_rdf_table.parse_args(['test'])
    parser.add_argument.assert_called_with('knowledgefile',
                                           help='Path to the knowledge file')
    assert args == 'args'


def test_create_table():
    table = create_rdf_table.create_table()
    assert table == [{"subject": "STRING"}, {"predicate": "STRING"},
                     {"object": "STRING"}, {"index": "INTEGER"}]


@patch('create_rdf_table.hashlib')
def test_create_statementset(mock_hashlib):
    graph = MagicMock()
    s = MagicMock()
    p = MagicMock()
    o = MagicMock()
    s.toPython.return_value = 's'
    p.toPython.return_value = 'p'
    o.toPython.return_value = 'o'
    hash_object = mock_hashlib.sha256.return_value
    hash_object.hex_dig.return_value = 'ABCDEF'
    graph.triples.return_value = [(s, p, o)]
    statementset = create_rdf_table.create_statementset(graph)
    assert statementset == "('s', 'p', 'o', 0);"
    graph.triples.return_value = [(s, p, o), (s, p, o)]
    statementset = create_rdf_table.create_statementset(graph)
    assert statementset == "('s', 'p', 'o', 0),\n('s', 'p', 'o', 1);"


@patch('create_rdf_table.ruamel.yaml')
@patch('create_rdf_table.owlrl')
@patch('create_rdf_table.rdflib')
@patch('create_rdf_table.create_table')
@patch('create_rdf_table.configs')
@patch('create_rdf_table.utils')
def test_main(mock_utils, mock_configs, mock_create_table, mock_rdflib,
              mock_owlrl, mock_yaml, tmp_path):
    mock_utils.create_sql_table.return_value = "sqltable"
    mock_utils.create_yaml_table.return_value = "yamltable"
    mock_utils.create_statementset.return_value = "statementset"
    mock_yaml.dump.return_value = "dump"
    create_rdf_table.main('kms/knowledge.ttl', tmp_path)

    assert os.path.exists(os.path.join(tmp_path, 'rdf.yaml')) is True
    assert os.path.exists(os.path.join(tmp_path, 'rdf.sqlite')) is True
