import asyncio
import argparse
import sys
import traceback
import importlib

Client = None
Server = None
XmlExporter = None
ua = None
temp_object_browse_name = "DELETEMELATER_"

try:
    asyncua = importlib.import_module('asyncua')
    Client = asyncua.Client
    Server = asyncua.Server
    XmlExporter = asyncua.common.xmlexporter.XmlExporter
    ua = asyncua.ua
except ImportError:
    print("The 'asyncua' library is not installed. Please install it separately to use this tool.")
    exit(1)

sys.setrecursionlimit(1500)  # Increase the recursion limit to avoid maximum recursion depth error

debug = False
not_exported_nodes = []


def remove_uaobjects_with_browsename(etree, browse_name_prefix_to_remove):
    """
    Remove all UAObject nodes with a specific BrowseName from the XML tree.

    :param exporter: Instance of XMLExporter etree
    :param browse_name_to_remove: The BrowseName to match for removal
    """
    # Find all UAObject nodes
    for parent in etree.findall(".//UAObject/.."):  # Find the parent nodes of UAObject
        uaobjects = parent.findall("UAObject")
        for uaobject in uaobjects:
            # Get the BrowseName attribute
            browse_name = uaobject.attrib.get("BrowseName")
            if browse_name is None:
                continue

            # Check if BrowseName starts with the target prefix (with or without namespace index)
            if browse_name.startswith(browse_name_prefix_to_remove) or \
               ":" in browse_name and browse_name.split(":", 1)[1].startswith(browse_name_prefix_to_remove):
                parent.remove(uaobject)  # Remove the UAObject node
                if debug:
                    print(f"Removed UAObject with BrowseName: {browse_name}")


async def create_dummy_object(server, idx, start_node):
    placeholder_name = f"{temp_object_browse_name}{idx}"
    temp_objects = server.nodes.objects
    local_node = await temp_objects.add_object(idx, placeholder_name)
    return local_node


async def browse_node(client, node, exported_nodes, visited_nodes, excluded, export_namespace_indexes,
                      first_time_namespace, parent_node_id=None, follow_backward_references=False):
    """
    Browse the given node and add its information to the XML in a flat structure.
    """
    try:
        # Avoid re-visiting nodes to prevent infinite recursion
        if node.nodeid in visited_nodes:
            return
        visited_nodes.add(node.nodeid)
        if debug:
            print(f"visited: {node.nodeid.NamespaceIndex}:{node.nodeid.Identifier}")

        # If the node belongs to a relevant namespace, add it to the XML
        if node.nodeid.NamespaceIndex in export_namespace_indexes and node.nodeid not in excluded:
            exported_nodes.append(node)

        # Browse children nodes and add them to the XML root
        references = await node.get_references()
        for ref in references:
            # Always browse the child nodes, filter them later
            # Except there is a backward reference
            if ref.IsForward is False and follow_backward_references is not True:
                continue
            child_node = client.get_node(ref.NodeId)
            await browse_node(client, child_node, exported_nodes, visited_nodes, excluded, export_namespace_indexes,
                              first_time_namespace, parent_node_id=node.nodeid,
                              follow_backward_references=follow_backward_references)

    except Exception as e:
        print(f"Error browsing node: {e}")
        traceback.print_exc()


async def main():
    global debug
    # Setup argument parser
    parser = argparse.ArgumentParser(description='Dump OPC UA server nodeset to XML-File.')
    parser.add_argument('--server-url', type=str, default='opc.tcp://localhost:4840/freeopcua/server/',
                        help='OPC UA server URL (default is opc.tcp://localhost:4840/freeopcua/server/)')
    parser.add_argument('--start-node', type=str, default='i=84',
                        help='Node ID to start browsing from (default is the Root node, i=84)')
    parser.add_argument('--output-file', type=str, default='nodeset2.xml',
                        help='Output XML file name (default is nodeset2.xml)')
    parser.add_argument('--namespaces', type=str, nargs='*', help='List of Namespaces to collect nodes from.')
    parser.add_argument('--excluded', type=str, nargs='*', help='List of Nodes to exclude from export.')
    parser.add_argument('-d', '--debug', action="store_true", default=False, help="Set debug flag.")
    parser.add_argument('-v', '--values', action="store_true", default=False, help="Export values.")
    parser.add_argument('-s', '--single', action="store_true", default=False, help="Export single node.")
    parser.add_argument('-b', '--backward', action="store_true", default=False,
                        help="Consider forward and backward references.")
    args = parser.parse_args()

    debug = args.debug
    # Connect to the OPC UA server
    async with Client(url=args.server_url) as client:
        # Create XML root for the NodeSet
        exporter = XmlExporter(client, export_values=args.values)

        # Get the namespace URIs from the server
        namespace_uris = await client.get_namespace_array()

        # Create NamespaceUris element
        export_namespace_indexes = []
        not_exported_namespaces = []

        if args.namespaces is None:
            print(f"Please provide a namespace, e.g. one of {namespace_uris}.")
            exit(1)
        for index, uri in enumerate(namespace_uris):
            # Only resolve requested namespaces and add "dummy" nodes for the other NSs
            nsidx = await client.get_namespace_index(uri)
            if uri in args.namespaces:
                export_namespace_indexes.append(nsidx)
            elif nsidx != 0:
                not_exported_namespaces.append(nsidx)

        # Get the starting node
        exported_nodes = []

        start_node = client.get_node(args.start_node)
        excluded = []
        first_time_namespace = []
        for nodeid in args.excluded or []:
            excluded.append(ua.NodeId.from_string(nodeid))

        single_node = args.single
        # Start browsing from the specified start node
        visited_nodes = set()  # Track visited nodes to avoid infinite recursion
        if not single_node:
            await browse_node(client, start_node, exported_nodes, visited_nodes, excluded,
                              export_namespace_indexes, first_time_namespace,
                              follow_backward_references=args.backward)
        temp_server = Server()
        await temp_server.init()
        for node in exported_nodes:
            try:
                node_class = await node.read_node_class()
                # Check if the node is a Variable type
                if args.values and node_class == ua.NodeClass.Variable:
                    await node.read_value()
            except:
                exported_nodes.remove(node)
                print(f"Removing node {node.nodeid} since it cannot export values.")
                # remove the node since this will create exceptions later
        # Generate the XML tree
        if not single_node:
            # Add for every not exported namespace a "dummy" object
            # This is needed because the namespace mapping of the exporter
            # does not work correctly
            for nidx in not_exported_namespaces:
                exported_nodes.append(await create_dummy_object(temp_server, nidx, start_node))
            await exporter.build_etree(exported_nodes)
            remove_uaobjects_with_browsename(exporter.etree, temp_object_browse_name)
        else:
            exporter.aliases = {}
            await exporter.node_to_etree(start_node)
        # Write to the nodeset2.xml file with pretty formatting
        await exporter.write_xml(args.output_file)

if __name__ == "__main__":
    asyncio.run(main())
