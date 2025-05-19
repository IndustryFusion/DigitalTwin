# Copyright (c) 2024, 2025 Intel Corporation
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
import argparse
import os
import signal
from asyncua import Server
from asyncua.ua.uaerrors._auto import BadParentNodeIdInvalid
from datetime import datetime


def log(message):
    """Helper function to log messages with timestamps."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


async def run_server(endpoint, namespace_uris, nodeset_files, strict):
    # 1. Create and initialize the server
    server = Server()
    await server.init()
    server.set_endpoint(endpoint)
    log(f"Server initialized at endpoint: {endpoint}")

    # 2. Register any provided namespaces
    for uri in namespace_uris:
        idx = await server.register_namespace(uri)
        log(f"Registered namespace '{uri}' at index {idx}")

    # 3. Validate and import Nodeset2 XML files
    for xml in nodeset_files:
        if not os.path.exists(xml):
            log(f"Error: Nodeset file '{xml}' does not exist. Skipping...")
            continue

        log(f"Importing Nodeset file: {xml} ({'strict' if strict else 'lenient'} mode)")
        try:
            await server.import_xml(xml)
            log(f"Successfully imported Nodeset file: {xml}")
        except BadParentNodeIdInvalid as e:
            if strict:
                raise
            else:
                log(f"Warning: Skipping BadParentNodeIdInvalid in {xml}: {e}")
        except Exception as e:
            if strict:
                raise
            else:
                log(f"Warning: Skipping import error in {xml}: {e}")

    # 4. Run the server
    async with server:
        log(f"Server running at {endpoint}")
        log(f"Registered namespaces: {namespace_uris}")
        log(f"Loaded Nodesets: {nodeset_files}")

        # Wait for termination signal
        stop_event = asyncio.Event()

        def stop_server(*_):
            log("Received termination signal. Shutting down server...")
            stop_event.set()

        signal.signal(signal.SIGINT, stop_server)
        signal.signal(signal.SIGTERM, stop_server)

        await stop_event.wait()


def parse_args():
    parser = argparse.ArgumentParser(
        description="AsyncUA OPC UA Server with Nodeset2 XML import"
    )
    parser.add_argument(
        "--endpoint", "-e",
        default="opc.tcp://0.0.0.0:4840/",
        help="OPC UA server endpoint URL (default: opc.tcp://0.0.0.0:4840/)"
    )
    parser.add_argument(
        "--namespace", "-n",
        action="append",
        default=[],
        metavar="URI",
        help="Namespace URI to register (can be repeated)"
    )
    parser.add_argument(
        "--nodeset", "-x",
        action="append",
        required=True,
        metavar="FILE",
        help="Path to Nodeset2 XML file to import (in order)"
    )
    parser.add_argument(
        "--lenient", "-l",
        action="store_true",
        help="Use lenient parsing mode (suppress certain import errors)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    # strict = not lenient => strict import or suppress errors
    try:
        asyncio.run(
            run_server(
                args.endpoint,
                args.namespace,
                args.nodeset,
                strict=not args.lenient
            )
        )
    except Exception as e:
        log(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
