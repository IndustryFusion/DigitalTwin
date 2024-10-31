import asyncio
import importlib

from asyncua import ua, Server
from asyncua.common.structures104 import new_struct, new_struct_field

ua = None
Server = None
new_struct = None
new_struct_field = None

try:
    asyncua = importlib.import_module('asyncua')
    Server = asyncua.Server
    ua = asyncua.ua
    new_struct = asyncua.common.structures104.new_struct
    new_struct_field = asyncua.common.structures104.new_struct_field
except ImportError:
    print("The 'asyncua' library is not installed. Please install it separately to use this tool.")
    exit(1)

async def main():
    # setup our server
    server = Server()
    await server.init()
    server.set_endpoint('opc.tcp://0.0.0.0:4840/freeopcua/server/')

    uri = 'http://examples.com/url1'
    idx = await server.register_namespace(uri)

    uri2 = 'http://examples.com/url2'
    idx2 = await server.register_namespace(uri2)
    
    uri3 = 'http://examples.com/url3'
    idx3 = await server.register_namespace(uri3)
    
    struct1, _ = await new_struct(server, idx2, "Struct1", [
        new_struct_field("MyUInt32", ua.VariantType.UInt32)
    ])
    struct2, _ = await new_struct(server, idx3, "Struct2", [
        new_struct_field("Bool", ua.VariantType.Boolean),
    ])

    custom_objs = await server.load_data_type_definitions()

    await server.nodes.objects.add_variable(idx, "Struct1", ua.Variant(ua.Struct1(), ua.VariantType.ExtensionObject))
    await server.nodes.objects.add_variable(idx, "Struct2", ua.Variant(ua.Struct2(), ua.VariantType.ExtensionObject))

    async with server:
        while True:
            await asyncio.sleep(1)


if __name__ == '__main__':
    asyncio.run(main())
