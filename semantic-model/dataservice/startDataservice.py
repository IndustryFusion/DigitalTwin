#
# Copyright (c) 2024 Intel Corporation
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

import sys
import urllib
import asyncio
import re
import socket
import rdflib
import argparse
from rdflib import Variable, URIRef, Namespace
import services.testConnector as testConnector
try:
    import external_services.opcuaConnector as opcuaConnector
except Exception as e:
    print(f"Import error: {e}")
    opcuaConnector = None

get_maps_query = """
SELECT ?map ?binding ?attribute ?connectorAttribute ?logicVar ?logicVarType ?connector ?firmwareVersion  WHERE  {
    ?attribute base:boundBy ?binding .
    ?binding base:bindsEntity ?entityId .
    ?binding base:bindsMap ?map .
    ?binding base:bindsFirmware ?firmwareVersion .
    ?map base:bindsConnectorAttribute ?connectorAttribute .
    ?map base:bindsLogicVar ?logicVar .
    ?map base:bindsConnector ?connector .
    ?map base:bindsMapDatatype ?logicVarType .
}

"""

get_attributes_query = """
SELECT ?attribute ?binding ?attributeType ?entityId ?apiVersion ?firmwareVersion ?logic WHERE  {
    ?attribute base:boundBy ?binding .
    ?binding base:bindsEntity ?entityId .
    ?binding base:bindsMap ?map .
    OPTIONAL {?binding base:bindsLogic ?logic . } .
    ?binding base:bindingVersion ?apiVersion .
    ?binding base:bindsFirmware ?firmwareVersion .
    ?binding base:bindsAttributeType ?attributeType .
}
"""


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='Start a Dataservice based on ontology and binding information.')
    parser.add_argument('ontdir', help='Directory containing the context.jsonld, entities.ttl, and knowledge.ttl \
files.')
    parser.add_argument('entityId', help='ID of entity to start service for, e.g. urn:iff:cutter:1 .')
    parser.add_argument('binding', help='Resources which describe the contex binding to the type.')
    parser.add_argument('-r', '--resources', help='List of additional knowledge resources from the ontdir directory, \
e.g. -r "material.ttl"')
    parser.add_argument('-f', '--firmwareVersion', help='Firmware version of system to connect to. If no given, \
the most recent firmware is selected.')
    parser.add_argument('-p', '--port', help='TCP port to forward data to device agent', default=7070, type=int)
    parser.add_argument('-e', '--entities', help='Name of the entities file', default='entities.ttl', type=str)
    parser.add_argument('-d', '--dryrun', help='Do not send data.', action='store_true')
    parser.add_argument('-b', '--baseOntology', help='Name of base ontology. Default: \
"https://industryfusion.github.io/contexts/ontology/v0/base/"',
                        default='https://industryfusion.github.io/contexts/ontology/v0/base/')
    parsed_args = parser.parse_args(args)
    return parsed_args


attributes = {}
prefixes = {}
tasks = []
query_prefixes = ''
g = rdflib.Graph()
supported_versions = ["0.1", "0.9"]
owl_bindings = {}


async def main(entityId, ontdir, entitiesfile, binding_name, entity_id, resources, baseOntology,
               requestedFirmwareVersion, port, dryrun):
    global attributes
    global prefixes
    global query_prefixes
    global g

    if not ontdir.endswith('/'):
        ontdir += '/'

    entities_name = f'{ontdir}{entitiesfile}'
    knowledge_name = f'{ontdir}knowledge.ttl'

    g = rdflib.Graph()
    g.parse(entities_name)
    knowledge = rdflib.Graph()
    try:
        knowledge.parse(knowledge_name)
    except:
        print("Warning: No knowledge file found.")
        pass
    g += knowledge
    if resources:
        for item in resources.split(','):
            parsefile = ontdir + item
            print(f'Parsing resource {parsefile}')
            resource = rdflib.Graph()
            resource.parse(parsefile)
            g += resource
    print(f'Parsing binding {binding_name}')
    bindings = rdflib.Graph()
    bindings.parse(binding_name)
    g += bindings

    # Get Context Prefixes
    context = ontdir + 'context.jsonld'
    context_graph = rdflib.Graph()
    try:
        context_graph.parse(context, format="json-ld")
    except urllib.error.HTTPError as e:
        print(f"Error in retrieving and parsing context: {context}: {str(e)}")
        exit(1)

    for prefix, namespace in context_graph.namespaces():
        query_prefixes += f'PREFIX {prefix}: <{namespace}>\n'
        prefixes[prefix] = Namespace(namespace)
    if 'base' not in prefixes:
        prefixes['base'] = Namespace(baseOntology)

    # Add official Context to attribute query and try to find bindings
    # sparql_bindings = {Variable("entityId"): entityId}
    qres = g.query(get_attributes_query, initNs=prefixes)
    for row in qres:
        print(f'Found attributes: {row.attribute}, {row.entityId}')
    if len(qres) == 0:
        print("Warning: No bindings found. Exiting.")
        exit(1)

    # Create Attribute strucuture
    tasks = []
    for row in qres:
        attribute = row.attribute.toPython()
        logic = row.logic.toPython() if row.logic is not None else None
        attributeType = row.attributeType.toPython()
        apiVersion = row.apiVersion.toPython()
        firmwareVersion = row.firmwareVersion.toPython()
        entityId = row.entityId.toPython()
        binding = str(row.binding)
        if binding not in owl_bindings.keys():
            owl_bindings[binding] = {}
        if firmwareVersion not in owl_bindings[binding]:
            owl_bindings[binding][firmwareVersion] = {}
        current_binding = owl_bindings[binding][firmwareVersion]
        if 'maps' not in current_binding.keys():
            current_binding['maps'] = {}
        current_binding['apiVersion'] = apiVersion
        current_binding['attributeType'] = attributeType
        current_binding['logic'] = logic
        current_binding['entityId'] = entityId
        current_binding['attribute'] = attribute

        # Basic checks
        if apiVersion not in supported_versions:
            print(f"Error: found binding API version {apiVersion} not in list of supported API versions \
{supported_versions}")
            exit(1)

    # Add official Context to mapping query and try to find bindings
    qres = g.query(get_maps_query, initNs=prefixes)
    for row in qres:
        print(f'Found mappings: {row.attribute}, {row.connectorAttribute}, {row.logicVar}, {row.connector}')
    if len(qres) == 0:
        print("Warning: No bindings found. Exiting.")
        exit(1)
# Create maps strucuture
    tasks = []
    for row in qres:
        attribute = row.attribute.toPython()
        binding = str(row.binding)
        connectorAttribute = row.connectorAttribute.toPython()
        map = str(row.map)
        logicVar = row.logicVar.toPython()
        connector = row.connector.toPython()
        logicVarType = row.logicVarType
        firmwareVersion = row.firmwareVersion.toPython()
        current_maps = owl_bindings[binding][firmwareVersion]['maps']
        if map not in current_maps.keys():
            current_maps[map] = {}
        current_maps[map]['logicVar'] = logicVar
        current_maps[map]['updated'] = False
        current_maps[map]['connector'] = connector
        current_maps[map]['logicVarType'] = logicVarType
        current_maps[map]['connectorAttribute'] = connectorAttribute

    # Start a service for every Attribute
    for binding in owl_bindings.keys():
        firmwareVersion = None
        # Determine exact attribute or look for legicographically maximum
        if requestedFirmwareVersion in owl_bindings[binding].keys():
            firmwareVersion = requestedFirmwareVersion
        else:
            firmwareVersion = sorted(list(owl_bindings[binding].keys()))[0]

        attribute = owl_bindings[binding][firmwareVersion]['attribute']
        print(f'Start dataservice for attribute {attribute}')
        binding_dict = owl_bindings[binding][firmwareVersion]
        for map in binding_dict['maps'].keys():
            print(f"Requesting map {map} from {binding}")
            maps = binding_dict['maps']
            connector = maps[map]['connector']
            if connector == prefixes['base'].TestConnector.toPython():
                task = asyncio.create_task(testConnector.subscribe(maps[map], firmwareVersion))
                tasks.append(task)
            elif connector == prefixes['base'].OPCUAConnector.toPython():
                task = asyncio.create_task(opcuaConnector.subscribe(maps[map], firmwareVersion))
                tasks.append(task)
            else:
                print(f"Error: No connector found for {connector}")
                exit(1)
        # start collection job
        attribute_trust_level = 1.0
        if requestedFirmwareVersion != firmwareVersion:
            attribute_trust_level = 0.0
        task = asyncio.create_task(calculate_attribute(attribute, binding, firmwareVersion,
                                                       attribute_trust_level, 5, port, dryrun))
        tasks.append(task)
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass  # Tasks have been cancelled, likely during shutdown
    except Exception as e:
        print(f"An error occurred: {e}")


def gather_connectors(connector_attributes):
    connectors = set()
    for connector_attribute in connector_attributes:
        connectors.add(connector_attribute['connector'])
    return connectors


async def attribute_service(attribute, firmwareVersion, r):
    attribute_dict = attributes[attribute][firmwareVersion]
    connector = attribute_dict['connector']
    print(f"Requesting connector_attribute {attribute} from {connector}")
    if connector == prefixes['base'].TestConnector.toPython():
        print("Now fetching from testConnector")
        task = asyncio.create_task(testConnector.subscribe(attribute, attribute_dict, calculate_attribute))
        tasks.append(task)
    else:
        print(f"Warning: No connector found for {connector}")
        exit(1)


async def calculate_attribute(attribute, binding, firmwareVersion, attribute_trust_level, sleep, port, dryrun):
    # Bind retrieved values
    while True:
        querybindings = {}
        connector_attribute_trust_level = 1.0
        binding_dict = owl_bindings[binding][firmwareVersion]
        for map in binding_dict['maps']:
            logic_var = binding_dict['maps'][map]['logicVar']
            value = None
            try:
                value = binding_dict['maps'][map]['value']
                binding_dict['maps'][map]['updated'] = False
            except:
                pass
            querybindings[Variable(logic_var)] = value
            if value is None:
                connector_attribute_trust_level = 0.0

        results = {}
        overallTrust = min(attribute_trust_level,
                           connector_attribute_trust_level)
        # Remove all (forbidden) pre-defined contexts
        if binding_dict['logic'] is not None:
            query = 'SELECT ?type ?value ?object ?datasetId ?trustLevel ' + binding_dict['logic']
            query = re.sub(r'^PREFIX .*\n', '', query)
            qres = g.query(query, initBindings=querybindings, initNs=prefixes)
            if len(qres) == 0:
                print("Warning: Could not derive any value binding from connector data.")
                return

        else:  # if there is only one map, take this over directly
            if len(binding_dict['maps']) == 1:
                map = next(iter(binding_dict['maps'].values()))
                if 'value' in map:
                    qres = [{'value': map['value'], 'type': map['logicVarType']}]
                else:
                    qres = []
        for row in qres:
            datasetId = '@none'
            type = None
            if row.get('datasetId') is not None:
                datasetId = row.datasetId
            if datasetId in results.keys():
                overallTrust = 0.0
            else:
                results[datasetId] = {}
            if row.get('type') is not None:
                type = row.get('type')
                results[datasetId]['type'] = row.get('type')
            else:
                overallTrust = 0.0
            if row.get('value') is not None:
                results[datasetId]['value'] = row.get('value')
                if type is None:
                    results[datasetId]['type'] = prefixes['ngsi-ld'].Property
            else:
                if type == prefixes['ngsi-ld'].Property:
                    overallTrust = 0.0
            if row.get('object') is not None:
                results[datasetId]['object'] = row.get('object')
            else:
                if type == prefixes['ngsi-ld'].Relationship:
                    overallTrust = 0.0
            if row.get('trustLevel') is not None:
                results[datasetId]['trustLevel'] = row.get('trustLevel').toPython()
            else:
                results[datasetId]['trustLevel'] = 0.0
        # Revise trust level with overall trust
        for result in results:
            results[result]['trustLevel'] = min(overallTrust, results[result]
                                                ['trustLevel'])
        if len(results) > 0:
            send(results, attribute, binding_dict['entityId'], dryrun, port)
        update_found = False
        while not update_found:
            await asyncio.sleep(0)
            update_found = True
            for map in binding_dict['maps']:
                update_found = binding_dict['maps'][map]['updated'] and update_found


def send(results, attribute, entityId, dryrun, port):
    payload = []
    for datasetId in results.keys():
        result = results[datasetId]
        value = result['value']
        type = result['type']
        lang = None
        if 'lang' in result:
            lang = result['lang']
        datasetId = result
        prefix = "Property"
        if type == prefixes['ngsi-ld'].Relationship:
            prefix = "Relationship"
        elif isinstance(value, URIRef):
            prefix = "PropertyIri"
        # Send over mqtt/device-agent
        payload_build = f'{{ "n": "{attribute}",\
"v": "{value.toPython()}", "t": "{prefix}", "i": "{entityId}"'
        if lang is not None:
            payload_build += f', "l": "{lang}"'
        payload_build += '}'
        payload.append(payload_build)
    payloads = f'[{",".join(payload)}]'
    if not dryrun:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect(("127.0.0.1", port))
        client_socket.sendall(payloads.encode('ascii'))
        client_socket.close()
    print(f"sent {payloads}")


if __name__ == '__main__':
    args = parse_args()
    entityId = args.entityId
    entitiesfile = args.entities
    ontdir = args.ontdir
    binding = args.binding
    resources = args.resources
    firmwareVersion = args.firmwareVersion
    port = args.port
    dryrun = args.dryrun
    baseontoloy = args.baseOntology
    asyncio.run(main(entityId, ontdir, entitiesfile, binding, entityId, resources, baseontoloy,
                     firmwareVersion,
                     port,
                     dryrun))
