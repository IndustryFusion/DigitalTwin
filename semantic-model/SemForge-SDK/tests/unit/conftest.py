import os
import sys

import pytest
from rdflib import Graph

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

CORPUS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'corpus', 'kms'))

# A package that declares no NGSI-LD vocabulary gets the default: the official
# url. Tests never reach the network for it -- every undeclared package here,
# and every server process the harness starts, uses the repo's shared copy.
NGSILD = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'corpus',
                                      'ontology', 'ngsild.ttl'))
os.environ.setdefault('SEMFORGE_NGSILD', NGSILD)


@pytest.fixture(autouse=True)
def _shared_ontology(request):
    """`ontology/` beside every copy of the corpus, as in the repo.

    The kms declares its vocabulary as ../ontology/ngsild.ttl; a test copies
    the corpus to tmp_path/<name>, so the shared copy goes to tmp_path. Only
    for tests that ask for tmp_path -- the others make no copies.
    """
    if 'tmp_path' not in request.fixturenames:
        return
    tmp_path = request.getfixturevalue('tmp_path')
    link = tmp_path / 'ontology'
    if not link.exists():
        link.symlink_to(os.path.dirname(os.path.realpath(NGSILD)),
                        target_is_directory=True)


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
