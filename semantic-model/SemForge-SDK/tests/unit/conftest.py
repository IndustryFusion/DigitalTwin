import os
import sys

import pytest
from rdflib import Graph

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

CORPUS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'corpus', 'kms'))


@pytest.fixture(scope='session')
def corpus_path():
    return CORPUS


@pytest.fixture(scope='session')
def corpus():
    from semforge.package import load
    return load(CORPUS)


TARGETS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'corpus',
                                       'targets'))


@pytest.fixture(scope='session')
def targets():
    """A package with one shape per SHACL target kind (the kms has only
    sh:targetClass)."""
    from semforge.package import load
    return load(TARGETS)


@pytest.fixture
def model_graph(corpus):
    graph = Graph()
    for triple in corpus.model:
        graph.add(triple)
    return graph
