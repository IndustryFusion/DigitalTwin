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
from rdflib.namespace import RDF
from rdflib import Variable, URIRef, Namespace
import services.testConnector as testConnector


get_maps_query = """
SELECT ?attribute ?connectorAttribute ?logicVar ?logicVarType ?connector ?firmwareVersion  WHERE  {
    ?attribute base:boundBy ?binding .
    ?binding base:bindsEntityType ?entityType .
    ?binding base:bindsMap ?map .
    ?binding base:bindsFirmware ?firmwareVersion .
    ?map base:bindsConnectorAttribute ?connectorAttribute .
    ?map base:bindsLogicVar ?logicVar .
    ?map base:bindsConnector ?connector .
    ?map base:bindsMapDataType ?logicVarType .
}

"""

get_attributes_query = """
SELECT ?attribute ?attributeType ?entityType ?apiVersion ?firmwareVersion ?logic WHERE  {
    ?attribute base:boundBy ?binding .
    ?binding base:bindsEntityType ?entityType .
    ?binding base:bindsMap ?map .
    ?binding base:bindsLogic ?logic .
    ?binding base:bindingVersion ?apiVersion .
    ?binding base:bindsFirmware ?firmwareVersion .
    ?attribute rdfs:range ?attributeType .
}
"""


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='Start a Dataservice based on ontology and binding information.')
    parser.add_argument('ontdir', help='Remote directory to pull down the ontology.')
    parser.add_argument('type', help='Type of entity to start service for, e.g. cutter, filter.')
    parser.add_argument('binding', help='Resources which describe the contexg binding to the type.')
    parser.add_argument('-u', '--usecases', help='List of Usecases from ontoloy in a comma separated list, \
e.g. -u "base,filter" or -u "base"', default='base')
    parser.add_argument('-r', '--resources', help='List of additional resources from the ontdir directory, \
e.g. -r "material.ttl"')
    parser.add_argument('-f', '--firmwareVersion', help='Firmware version of system to connect to. If no given, \
the most recent firmware is selected.')
    parser.add_argument('-p', '--port', help='TCP port to forward date to device agent', default=7070, type=int)
    parser.add_argument('-d', '--dryrun', help='Do not send data.', action='store_true')
    parsed_args = parser.parse_args(args)
    return parsed_args


attributes = {}
prefixes = {}
tasks = []
query_prefixes = ''
g = rdflib.Graph()
supported_versions = ["0.9"]


async def main(type, ontdir, binding, usecases, resources, requestedFirmwareVersion, port, dryrun):
    global attributes
    global prefixes
    global query_prefixes
    global g

    if 'base' not in usecases:
        usecases += ',base'
    if not ontdir.endswith('/'):
        ontdir += '/'

    for item in usecases.split(','):
        knowledge = rdflib.Graph()
        entities = rdflib.Graph()
        try:
            parsefile = ontdir + item + '_knowledge.ttl'
            print(f'Parsing knowledge: {parsefile}')
            knowledge.parse(parsefile)
        except:
            print('No valid Knowledge found.')
        parsefile = ontdir + item + '_entities.ttl'
        print(f'Parsing entities: {parsefile}')
        entities.parse(parsefile)

        g += knowledge
        g += entities
    if resources:
        for item in resources.split(','):
            parsefile = ontdir + item
            print(f'Parsing resource {parsefile}')
            resource = rdflib.Graph()
            resource.parse(parsefile)
            g += resource
    parsefile = ontdir + 'bindings/' + binding
    print(f'Parsing binding {parsefile}')
    binding = rdflib.Graph()
    binding.parse(parsefile)
    g += binding

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

    # Expand type and check if defined in ontology
    entity_type = context_graph.namespace_manager.expand_curie(type)
    type_found = False
    for s, p, o in g.triples((entity_type, RDF.type, None)):
        type_found = True
    if not type_found:
        print(f"Given Type {entity_type} is not found in the ontology. Please check spelling.")
        exit(1)

    # Add official Context to attribute query and try to find bindings
    bindings = {Variable("entityType"): entity_type}
    qres = g.query(get_attributes_query, initBindings=bindings, initNs=prefixes)
    for row in qres:
        print(f'Found attributes: {row.attribute}, {row.entityType}')
    if len(qres) == 0:
        print("Warning: No bindings found. Exiting.")
        exit(1)

    # Create Attribute strucuture
    tasks = []
    for row in qres:
        attribute = row.attribute.toPython()
        logic = row.logic.toPython()
        attributeType = row.attributeType.toPython()
        apiVersion = row.apiVersion.toPython()
        firmwareVersion = row.firmwareVersion.toPython()

        if attribute not in attributes.keys():
            attributes[attribute] = {}
        if firmwareVersion not in attributes[attribute]:
            attributes[attribute][firmwareVersion] = {}
        current_attribute = attributes[attribute][firmwareVersion]
        if 'connectorAttributes' not in current_attribute.keys():
            current_attribute['connectorAttributes'] = {}
        current_attribute['apiVersion'] = apiVersion
        current_attribute['attributeType'] = attributeType
        current_attribute['logic'] = logic

        # Basic checks
        if apiVersion not in supported_versions:
            print(f"Error: found binding version {apiVersion} not in list of supported versions {supported_versions}")
            exit(1)

    # Add official Context to mapping query and try to find bindings
    bindings = {Variable("entityType"): entity_type}
    qres = g.query(get_maps_query, initBindings=bindings, initNs=prefixes)
    for row in qres:
        print(f'Found mappings: {row.attribute}, {row.connectorAttribute}, {row.logicVar}, {row.connector}')
    if len(qres) == 0:
        print("Warning: No bindings found. Exiting.")
        exit(1)
# Create maps strucuture
    tasks = []
    for row in qres:
        attribute = row.attribute.toPython()
        connectorAttribute = row.connectorAttribute.toPython()
        logicVar = row.logicVar.toPython()
        connector = row.connector.toPython()
        logicVarType = row.logicVarType
        firmwareVersion = row.firmwareVersion.toPython()
        current_connector_attributes = attributes[attribute][firmwareVersion]['connectorAttributes']
        if connectorAttribute not in current_connector_attributes:
            current_connector_attributes[connectorAttribute] = {}
        current_connector_attributes[connectorAttribute]['logicVar'] = logicVar
        current_connector_attributes[connectorAttribute]['connector'] = connector
        current_connector_attributes[connectorAttribute]['logicVarType'] = logicVarType

    # Start a service for every Attribute
    for attribute in attributes.keys():
        firmwareVersion = None
        print(f'Start dataservice for attribute {attribute}')
        # Determine exact attribute or look for legicographically maximum
        if requestedFirmwareVersion in attributes[attribute].keys():
            firmwareVersion = requestedFirmwareVersion
        else:
            firmwareVersion = sorted(list(attributes[attribute].keys()))[0]

        attribute_dict = attributes[attribute][firmwareVersion]['connectorAttributes']
        for connector_attribute in attribute_dict:
            print(f"Requesting connector_attribute {connector_attribute} from {connector}")
            firmware_data = attributes[attribute][firmwareVersion]
            connector_attrs = firmware_data['connectorAttributes']
            connector_attribute_dict = connector_attrs[connector_attribute]
            connector = connector_attribute_dict['connector']
            if connector == prefixes['base'].TestConnector.toPython():
                task = asyncio.create_task(testConnector.subscribe(connector_attribute_dict, firmwareVersion))
                tasks.append(task)
            else:
                print(f"Error: No connector found for {connector}")
                exit(1)
        # start collection job
        attribute_trust_level = 1.0
        if requestedFirmwareVersion != firmwareVersion:
            attribute_trust_level = 0.0
        task = asyncio.create_task(calculate_attribute(attribute, firmwareVersion,
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


async def calculate_attribute(attribute, firmwareVersion, attribute_trust_level, sleep, port, dryrun):
    # Bind retrieved values
    while True:
        bindings = {}
        connector_attribute_trust_level = 1.0
        attribute_dict = attributes[attribute][firmwareVersion]
        for conntectorAttribute in attribute_dict['connectorAttributes']:
            logic_var = attribute_dict['connectorAttributes'][conntectorAttribute]['logicVar']
            value = None
            try:
                value = attribute_dict['connectorAttributes'][conntectorAttribute]['value']
            except:
                pass
            bindings[Variable(logic_var)] = value
            if value is None:
                connector_attribute_trust_level = 0.0

        # Remove all (forbidded) pre-defined contexts
        query = 'SELECT ?type ?value ?object ?datasetId ?trustLevel ' + attribute_dict['logic']
        query = re.sub(r'^PREFIX .*\n', '', query)
        qres = g.query(query, initBindings=bindings, initNs=prefixes)
        if len(qres) == 0:
            print("Warning: Could not derive any value binding from connector data.")
            return
        results = {}
        overallTrust = min(attribute_trust_level,
                           connector_attribute_trust_level)
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
                type = row.type
                results[datasetId]['type'] = row.type
            else:
                overallTrust = 0.0
            if row.get('value') is not None:
                results[datasetId]['value'] = row.value
            else:
                if type == prefixes['ngsi-ld'].Property:
                    overallTrust = 0.0
            if row.get('object') is not None:
                results[datasetId]['object'] = row.object
            else:
                if type == prefixes['ngsi-ld'].Relationship:
                    overallTrust = 0.0
            if row.get('trustLevel') is not None:
                results[datasetId]['trustLevel'] = row.trustLevel.toPython()
            else:
                results[datasetId]['trustLevel'] = 0.0
        # Revise trust level with overall trust
        for result in results:
            results[result]['trustLevel'] = min(overallTrust, results[result]
                                                ['trustLevel'])
        send(results, attribute, dryrun, port)
        await asyncio.sleep(sleep)


def send(results, attribute, dryrun, port):
    payload = []
    for datasetId in results.keys():
        result = results[datasetId]
        value = result['value']
        type = result['type']
        datasetId = result
        prefix = "Property"
        if type == prefixes['ngsi-ld'].Relationship:
            prefix = "Relationship"
        elif isinstance(value, URIRef):
            prefix = "PropertyIri"
        # Send over mqtt/device-agent

        payload.append(f'{{ "n": "{attribute}",\
"v": "{value.toPython()}", "t": "{prefix}"}}')
    payloads = f'[{",".join(payload)}]'
    if not dryrun:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect(("127.0.0.1", port))
        client_socket.sendall(payloads.encode('ascii'))
        client_socket.close()
    print(f"sent {payloads}")


if __name__ == '__main__':
    args = parse_args()
    type = args.type
    ontdir = args.ontdir
    binding = args.binding
    usecases = args.usecases
    resources = args.resources
    firmwareVersion = args.firmwareVersion
    port = args.port
    dryrun = args.dryrun
    asyncio.run(main(type, ontdir, binding, usecases, resources,
                     firmwareVersion,
                     port,
                     dryrun))
