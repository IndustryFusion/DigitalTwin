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

import asyncio
import json
from types import SimpleNamespace

import pytest
from rdflib import Graph, Literal, Namespace, URIRef, Variable
from rdflib.namespace import RDF, XSD

import startDataservice
from startDataservice import gather_connectors, send

NGSILD = Namespace('https://uri.etsi.org/ngsi-ld/')
BASE = Namespace('https://industryfusion.github.io/contexts/ontology/v0/base/')
PUMPS = Namespace('http://opcfoundation.org/UA/Pumps/')
ATTRIBUTE = 'http://example.org/attribute'
ENTITY = 'urn:example:1'


def test_gather_connectors():
    """Test the gather_connectors function."""
    connector_attributes = [
        {'connector': 'ConnectorA'},
        {'connector': 'ConnectorB'},
        {'connector': 'ConnectorA'}  # Duplicate to check deduplication
    ]

    expected = {'ConnectorA', 'ConnectorB'}

    # Call the gather_connectors function
    result = gather_connectors(connector_attributes)

    # Assert the result matches expected output
    assert result == expected


@pytest.fixture
def sent(monkeypatch):
    """The messages which are sent to the device agent."""
    messages = []

    class FakeSocket:
        def __init__(self, *args):
            pass

        def connect(self, address):
            pass

        def sendall(self, data):
            messages.extend(json.loads(data.decode('ascii')))

        def close(self):
            pass

    monkeypatch.setattr(startDataservice, 'socket', SimpleNamespace(socket=FakeSocket, AF_INET=0, SOCK_STREAM=0))
    monkeypatch.setitem(startDataservice.prefixes, 'ngsi-ld', NGSILD)
    return messages


def send_value(value, type=NGSILD.Property):
    send({'@none': {'value': value, 'type': type, 'trustLevel': 1.0}}, ATTRIBUTE, ENTITY, False, 7070)


@pytest.mark.parametrize('value, expected', [
    (Literal(True), 'true'),
    (Literal(False), 'false'),
    (Literal(71.25), '71.25'),
    (Literal(17), '17'),
    (Literal('text'), 'text'),
    (Literal('a "quoted" text'), 'a "quoted" text'),
    (Literal('2025-07-14T08:30:00+00:00', datatype=XSD.dateTime), '2025-07-14T08:30:00+00:00'),
])
def test_send_uses_the_lexical_form(sent, value, expected):
    send_value(value)
    assert sent == [{'n': ATTRIBUTE, 'v': expected, 't': 'Property', 'i': ENTITY}]


def test_send_iri(sent):
    send_value(URIRef('http://example.org/value'))
    assert sent[0]['v'] == 'http://example.org/value'
    assert sent[0]['t'] == 'IriProperty'


def test_send_json(sent):
    send_value(Literal('{"a": 1}', datatype=RDF.JSON), NGSILD.JsonProperty)
    assert sent[0]['t'] == 'JsonProperty'
    assert json.loads(sent[0]['v']) == {'a': 1}


def test_send_relationship(sent):
    send_value(URIRef('urn:example:2'), NGSILD.Relationship)
    assert sent[0]['t'] == 'Relationship'


def run_binding(monkeypatch, binding, knowledge=None):
    """Run one binding until the first message was sent."""
    monkeypatch.setitem(startDataservice.owl_bindings, 'binding', {'firmware': binding})
    if knowledge is not None:
        monkeypatch.setattr(startDataservice, 'g', knowledge)
    monkeypatch.setattr(startDataservice, 'update_poll_interval', 0.001)

    async def scenario():
        task = asyncio.create_task(startDataservice.calculate_attribute(ATTRIBUTE, 'binding', 'firmware', 1.0, 5,
                                                                        7070, False))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def direct_binding(value, attribute_type=NGSILD.Property):
    return {'maps': {'map': {'logicVar': 'var1', 'value': value, 'updated': False, 'logicVarType': PUMPS.Any}},
            'logic': None, 'entityId': ENTITY, 'attribute': ATTRIBUTE, 'attributeType': str(attribute_type)}


def test_binding_without_logic_takes_over_attribute_type(monkeypatch, sent):
    run_binding(monkeypatch, direct_binding(Literal('{"a": 1}', datatype=RDF.JSON), NGSILD.JsonProperty))
    assert sent[0]['t'] == 'JsonProperty'


def test_waiting_for_updates_does_not_block_the_event_loop(monkeypatch, sent):
    # The update loop must really sleep, otherwise it runs at 100% CPU.
    assert startDataservice.update_poll_interval > 0
    run_binding(monkeypatch, direct_binding(Literal(1.5)))
    assert len(sent) == 1


ENUM_LOGIC = f"""WHERE {{
  ?value a <{PUMPS.PumpClassEnum}> ;
      <{BASE.hasValueNode}> ?valueNode .
  ?valueNode <{BASE.hasEnumValue}> ?enumValue .
  FILTER(?enumValue = ?var1)
  BIND(<{NGSILD.Property}> AS ?type)
  BIND(1.0 AS ?trustLevel)
}}"""


def enum_knowledge():
    g = Graph()
    for iri, number in ((PUMPS.LiquidPump, 5), (PUMPS.PositiveDisplacementPump, 1)):
        node = URIRef(f'{iri}/valueNode')
        g.add((iri, RDF.type, PUMPS.PumpClassEnum))
        g.add((iri, BASE.hasValueNode, node))
        g.add((node, BASE.hasEnumValue, Literal(number)))
    return g


@pytest.mark.parametrize('number, expected', [(5, str(PUMPS.LiquidPump)), (1, str(PUMPS.PositiveDisplacementPump))])
def test_enum_logic_translates_number_to_iri(monkeypatch, sent, number, expected):
    binding = direct_binding(Literal(number))
    binding['logic'] = ENUM_LOGIC
    run_binding(monkeypatch, binding, enum_knowledge())
    assert sent[0]['v'] == expected
    assert sent[0]['t'] == 'IriProperty'


def test_enum_logic_with_unknown_number_sends_nothing(monkeypatch, sent):
    binding = direct_binding(Literal(99))
    binding['logic'] = ENUM_LOGIC
    run_binding(monkeypatch, binding, enum_knowledge())
    assert sent == []


def test_query_variable_is_used_by_logic():
    # Guard for the query interface used by calculate_attribute
    result = enum_knowledge().query('SELECT ?type ?value ?object ?datasetId ?trustLevel ' + ENUM_LOGIC,
                                    initBindings={Variable('var1'): Literal(5)})
    assert [row.value for row in result] == [PUMPS.LiquidPump]
