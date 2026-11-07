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

"""Relative paths, also those starting with ../, are resolved against the working directory.

rdflib resolves a relative path which doesn't exist as a URL against the working directory, which drops
one directory level, so the error names a file in the wrong directory."""

import asyncio
import importlib.util
import os

import pytest
from rdflib import Graph

import startDataservice

BASE = 'https://industryfusion.github.io/contexts/ontology/v0/base/'
BINDINGS = """@prefix base: <https://industryfusion.github.io/contexts/ontology/v0/base/> .
@prefix opcua: <http://opcfoundation.org/UA/> .
<urn:binding> base:bindsMap <urn:map> .
<urn:map> a base:BoundMap ;
    base:bindsConnectorParameter "nsu=http://example.org/UA/;i=6020" ;
    base:bindsMapDatatype opcua:Double .
"""


@pytest.fixture
def next_to_opcua(tmp_path, monkeypatch):
    """Works in a dataservice directory next to an opcua directory which holds the bindings."""
    (tmp_path / 'opcua').mkdir()
    (tmp_path / 'opcua' / 'bindings.ttl').write_text(BINDINGS)
    (tmp_path / 'dataservice').mkdir()
    monkeypatch.chdir(tmp_path / 'dataservice')
    return tmp_path


def load_server(name):
    """The test servers aren't a package, and need asyncua, which isn't a dependency of the dataservice."""
    pytest.importorskip('asyncua')
    path = os.path.join(os.path.dirname(__file__), 'server', f'{name}.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_path_is_absolute(next_to_opcua):
    assert startDataservice.local_path('../opcua/bindings.ttl') == str(next_to_opcua / 'opcua' / 'bindings.ttl')


def test_local_path_keeps_urls():
    assert startDataservice.local_path(BASE) == BASE


def test_dataservice_reads_relative_bindings(next_to_opcua):
    assert len(Graph().parse(startDataservice.local_path('../opcua/bindings.ttl'))) == 4


def test_dataservice_names_the_missing_file(next_to_opcua):
    with pytest.raises(FileNotFoundError) as error:
        Graph().parse(startDataservice.local_path('../opcua/missing.ttl'))
    assert str(next_to_opcua / 'opcua' / 'missing.ttl') in str(error.value)


def test_dataservice_main_names_the_missing_ontdir(next_to_opcua):
    with pytest.raises(FileNotFoundError) as error:
        asyncio.run(startDataservice.main('../model', 'entities.ttl', '../opcua/bindings.ttl', None, BASE,
                                          None, 7070, True))
    assert str(next_to_opcua / 'model' / 'entities.ttl') in str(error.value)


def test_binding_server_reads_relative_bindings(next_to_opcua):
    server = load_server('binding_server')
    mapping = server.parse_rdf_to_mapping('../opcua/bindings.ttl', BASE)
    assert mapping == {'i=6020': {'namespace': 'http://example.org/UA/', 'datatype': float}}


def test_binding_server_names_the_missing_file(next_to_opcua):
    server = load_server('binding_server')
    with pytest.raises(FileNotFoundError) as error:
        server.parse_rdf_to_mapping('../opcua/missing.ttl', BASE)
    assert str(next_to_opcua / 'opcua' / 'missing.ttl') in str(error.value)


class FakeServer:
    """Records which nodes the nodeset server makes writable."""

    def __init__(self):
        self.writable = []

    async def get_namespace_index(self, namespace):
        return 2

    def get_node(self, nodeid):
        server = self

        class Node:
            async def set_writable(self):
                server.writable.append(nodeid)
        return Node()


def test_nodeset_server_reads_relative_bindings(next_to_opcua):
    server = load_server('nodeset_server')
    fake = FakeServer()
    asyncio.run(server.set_bound_nodes_writable(fake, '../opcua/bindings.ttl', BASE))
    assert fake.writable == ['ns=2;i=6020']


def test_nodeset_server_names_the_missing_file(next_to_opcua):
    server = load_server('nodeset_server')
    with pytest.raises(FileNotFoundError) as error:
        asyncio.run(server.set_bound_nodes_writable(FakeServer(), '../opcua/missing.ttl', BASE))
    assert str(next_to_opcua / 'opcua' / 'missing.ttl') in str(error.value)
