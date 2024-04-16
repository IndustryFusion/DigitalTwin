import asyncio
import argparse
from asyncua import ua, Server
from rdflib import Graph, Namespace
from rdflib.namespace import RDF
import re
import sys
import random

opcua_ns = Namespace('http://opcfoundation.org/UA/')


async def setup_opcua_server(mapping_data):
    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://localhost:4840/freeopcua/server/")

    # Register base namespace
    base_uri = "http://example.com/opcua"
    base_idx = await server.register_namespace(base_uri)

    # Register additional namespaces from mapping data
    namespaces = {}
    for namespace_uri in set(data['namespace'] for data in mapping_data.values()):
        idx = await server.register_namespace(namespace_uri)
        namespaces[namespace_uri] = idx
        print(f"Registration: Namespace {namespace_uri} with id {idx}.")

    # Create an OPC UA object node
    objects = server.get_objects_node()
    device = await objects.add_object(base_idx, "Device")

    # Add variables based on the mapping data
    for nodeid, data in mapping_data.items():
        idx = namespaces.get(data['namespace'], base_idx)
        if nodeid.startswith('i='):
            numeric_id = int(nodeid[2:])  # Convert the "i=xxxx" part to an integer
        else:
            numeric_id = int(nodeid)  # Handle cases where nodeid is already numeric
        print(f"Provide nodeid {numeric_id} with datatype {data['datatype']} in namespace {data['namespace']} \
with namespace idx {idx}")
        node_id = ua.NodeId(numeric_id, idx)
        node = await device.add_variable(node_id, f"Node_{numeric_id}", data['datatype']())
        await node.set_writable()

        # Set initial random value based on data type
        if data['datatype'] == float:
            value = random.uniform(0, 100)
        elif data['datatype'] == bool:
            value = random.choice([True, False])
        elif data['datatype'] == int:
            value = random.randint(0, 100)
        else:
            value = "RandomString"

        await node.write_value(value)

    # Start the server
    async with server:
        print("OPC UA Server is running...")
        while True:
            await asyncio.sleep(1)


async def setup_opcua_server_backup(mapping_data):
    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://localhost:4840/freeopcua/server/")

    # Register base namespace
    base_uri = "http://example.com/opcua"
    base_idx = await server.register_namespace(base_uri)

    # Register additional namespaces from mapping data
    namespaces = {}
    for namespace_uri in set(data['namespace'] for data in mapping_data.values()):
        idx = await server.register_namespace(namespace_uri)
        namespaces[namespace_uri] = idx
        print(f"Registration: Namespace {namespace_uri} with id {idx}.")

    # Create an OPC UA object node
    objects = server.get_objects_node()
    device = await objects.add_object(base_idx, "Device")

    # Add variables based on the mapping data
    for nodeid, data in mapping_data.items():
        print(f"Provide nodeid {nodeid} with datatype {data['datatype']} in namespace {data['namespace']}")
        idx = namespaces.get(data['namespace'], base_idx)
        node = await device.add_variable(idx, f"Node_{nodeid}", data['datatype']())
        await node.set_writable()

    # Start the server
    async with server:
        print("OPC UA Server is running...")
        while True:
            await asyncio.sleep(1)


def parse_rdf_to_mapping(rdf_file, base_ns, binding_ns=None, uaentity_ns=None):
    g = Graph()
    g.parse(rdf_file, format="turtle")

    # Define the base namespace for the vocabulary
    BASE = Namespace(base_ns)

    # Check for binding and UA entity namespaces in RDF
    found_binding_ns = g.namespace_manager.store.namespace("binding")
    found_uaentity_ns = g.namespace_manager.store.namespace("uaentity")

    if not binding_ns and not found_binding_ns:
        print("Error: Binding namespace not found in RDF data, and no binding namespace provided.")
        sys.exit(1)
    if not uaentity_ns and not found_uaentity_ns:
        print("Error: UA entity namespace not found in RDF data, and no UA entity namespace provided.")
        sys.exit(1)

    # Use the found namespaces if not provided
    binding_ns = binding_ns or found_binding_ns
    uaentity_ns = uaentity_ns or found_uaentity_ns

    nsu_pattern = re.compile(r'nsu=(.*?);i=(\d+)')

    mapping_data = {}
    for s, p, o in g.triples((None, RDF.type, BASE.BoundMap)):
        connector_attribute = g.value(s, BASE.bindsConnectorAttribute)
        datatype_uri = g.value(s, BASE.bindsMapDatatype)

        if connector_attribute and datatype_uri:
            # Parse namespace and identifier from connector_attribute
            match = nsu_pattern.match(str(connector_attribute))
            if match:
                namespace_uri = match.group(1)
                node_id = f"i={match.group(2)}"
            else:
                namespace_uri = None
                node_id = str(connector_attribute)

            # Translate RDF Datatype to Python Type
            if datatype_uri == opcua_ns.Double:
                datatype = float
            elif datatype_uri == opcua_ns.Boolean:
                datatype = bool
            elif datatype_uri == opcua_ns.String:
                datatype = str
            elif datatype_uri == opcua_ns.LocalizedText:
                datatype = str
            else:
                print(f"Warning, could not determine python type for {datatype_uri}. Using default: str.")
                datatype = str  # Default to string if not recognized

            mapping_data[node_id] = {
                'namespace': namespace_uri,
                'datatype': datatype
            }

    return mapping_data


async def main(rdf_file, base_ns, binding_ns=None, uaentity_ns=None):
    # Parse the RDF to extract the mapping
    mapping_data = parse_rdf_to_mapping(rdf_file, base_ns, binding_ns, uaentity_ns)

    # Setup OPC UA server based on extracted mapping
    await setup_opcua_server(mapping_data)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start an OPC UA server based on an RDF binding description.")
    parser.add_argument("rdf_file", type=str, help="Path to the bindings.ttl RDF file")
    parser.add_argument("--base-ns", type=str, default="https://industryfusion.github.io/contexts/ontology/v0/base/",
                        help="Base namespace for the vocabulary (default: \
https://industryfusion.github.io/contexts/ontology/v0/base/)")
    parser.add_argument("--binding-ns", type=str, help="Optional: Binding namespace")
    parser.add_argument("--uaentity-ns", type=str, help="Optional: UA entity namespace")

    args = parser.parse_args()

    asyncio.run(main(args.rdf_file, args.base_ns, args.binding_ns, args.uaentity_ns))
