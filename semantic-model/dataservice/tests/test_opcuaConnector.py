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

# asyncua is not a dependency of the dataservice (see README), so the connector is tested with a fake server.
import asyncio
import dataclasses
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from rdflib.namespace import RDF

import external_services.opcuaConnector as connector

NAMESPACE = 'http://example.org/ns/'
CONNECTOR_ATTRIBUTE = f'nsu={NAMESPACE};i=1'


@dataclasses.dataclass
class FakeNodeId:
    identifier: int = 0


@dataclasses.dataclass
class FakeQualifiedName:
    name: str = ''


@dataclasses.dataclass
class FakeStatusCode:
    value: int = 0


@dataclasses.dataclass
class FakeLocalizedText:
    Text: str = ''
    Locale: str = ''


@dataclasses.dataclass
class OptionSet:
    Value: bytes = b''
    ValidBits: bytes = b''


class FakeServer:
    """State of the server, shared by all clients: it can go down, come back and change its namespace table."""
    def __init__(self, value=1.5):
        self.up = True
        self.value = value
        self.namespaces = ['http://opcfoundation.org/UA/', NAMESPACE]
        self.read_nodeids = []
        self.connects = 0

    def client(self, url, timeout):
        return FakeClient(self)


class FakeNode:
    def __init__(self, server, nodeid):
        self.server = server
        self.nodeid = nodeid

    async def read_value(self):
        if not self.server.up:
            raise ConnectionError('client is disconnected')
        return self.server.value

    async def get_value(self):
        self.server.read_nodeids.append(self.nodeid)
        return await self.read_value()


class FakeClient:
    def __init__(self, server):
        self.server = server

    async def connect(self):
        if not self.server.up:
            raise ConnectionRefusedError('server is down')
        self.server.connects += 1

    async def disconnect(self):
        raise ConnectionError('disconnecting a lost connection fails')

    async def get_namespace_array(self):
        return self.server.namespaces

    def get_node(self, nodeid):
        return FakeNode(self.server, nodeid)


@pytest.fixture
def server(monkeypatch):
    fake = FakeServer()
    monkeypatch.setattr(connector, 'asyncua_client', fake.client)
    monkeypatch.setattr(connector, 'ua', SimpleNamespace(
        LocalizedText=FakeLocalizedText, NodeId=FakeNodeId, QualifiedName=FakeQualifiedName,
        StatusCode=FakeStatusCode, ObjectIds=SimpleNamespace(Server_ServerStatus_State=2259)), raising=False)
    monkeypatch.setattr(connector.OPCUAClientManager, '_client_instance', None)
    return fake


def run_steps(map, steps, sleeptime=0.01):
    """Run the connector and execute every step after the connector had time for some reads."""
    async def scenario():
        task = asyncio.create_task(connector.subscribe(map, 'firmware', sleeptime=sleeptime))
        for step in steps:
            await asyncio.sleep(sleeptime * 5)
            step()
        await asyncio.sleep(sleeptime * 5)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def new_map():
    return {'connectorAttribute': CONNECTOR_ATTRIBUTE, 'updated': False}


def test_value_is_handed_over(server):
    map = new_map()
    run_steps(map, [])
    assert map['value'].toPython() == 1.5
    assert map['updated'] is True
    assert map['lang'] is None
    assert server.read_nodeids[0] == 'ns=1;i=1'


def test_unset_node_hands_over_nothing(server):
    server.value = None
    map = new_map()
    run_steps(map, [])
    assert 'value' not in map
    assert map['updated'] is False


def test_outage_keeps_last_value_and_hands_over_nothing(server):
    map = new_map()

    def outage():
        server.up = False
        map['updated'] = False

    run_steps(map, [outage])
    assert map['value'].toPython() == 1.5
    assert map['updated'] is False


def test_reconnects_when_server_comes_back(server):
    map = new_map()

    def outage():
        server.up = False

    def comeback():
        map['updated'] = False
        server.value = 2.5
        server.up = True

    run_steps(map, [outage, comeback])
    assert map['value'].toPython() == 2.5
    assert map['updated'] is True
    assert server.connects == 2


def test_namespace_index_is_resolved_again_after_reconnect(server):
    map = new_map()

    def outage():
        server.up = False

    def comeback():
        server.namespaces = ['http://opcfoundation.org/UA/', 'http://other/', NAMESPACE]
        server.up = True

    run_steps(map, [outage, comeback])
    assert server.read_nodeids[-1] == 'ns=2;i=1'


def test_server_is_down_at_start(server):
    server.up = False
    map = new_map()

    def start():
        server.up = True

    run_steps(map, [start])
    assert map['value'].toPython() == 1.5


def test_failure_of_single_node_keeps_the_connection(server):
    map = new_map()
    server.namespaces = ['http://opcfoundation.org/UA/']  # this node cannot be resolved, the server is still fine
    run_steps(map, [])
    assert 'value' not in map
    assert server.connects == 1


def test_localized_text(server):
    server.value = FakeLocalizedText('text', 'en')
    map = new_map()
    run_steps(map, [])
    assert str(map['value']) == 'text'
    assert map['lang'] == 'en'


def test_structure_is_json_in_the_form_of_the_instances(server):
    server.value = OptionSet(Value=b'\x01\x00', ValidBits=b'\x80\x0f')
    map = new_map()
    run_steps(map, [])
    assert map['value'].datatype == RDF.JSON
    assert json.loads(str(map['value'])) == {
        'xsd:Body': {'xsd:OptionSet': {'xsd:Value': 'AQA=', 'xsd:ValidBits': 'gA8='}}}


def test_scalar_dataclass_is_no_structure(server):
    server.value = FakeNodeId(5)
    map = new_map()
    run_steps(map, [])
    assert map['value'].datatype != RDF.JSON


def test_to_literal_of_datetime_and_boolean(server):
    # the lexical form is what is sent to the agent
    assert str(connector.to_literal(True)) == 'true'
    assert str(connector.to_literal(datetime(2025, 7, 14, 8, 30, tzinfo=timezone.utc))) == '2025-07-14T08:30:00+00:00'
