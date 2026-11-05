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

import os
import base64
import dataclasses
import datetime
import enum
import json
import logging
import asyncio
import importlib
from rdflib import Literal
from rdflib.namespace import RDF
from asyncio import Lock


class OPCUAClientManager:
    _client_instance = None
    _lock = Lock()

    def __init__(self, url):
        if not asyncua_client:
            raise ImportError("The 'asyncua' library is required for this functionality. Please install it.")

        self.url = url
        self.client = None
        self.active_subscriptions = 0
        self._subscription_lock = Lock()
        self._connection_lock = Lock()
        self._value_lock = Lock()
        self._get_node_lock = Lock()
        self.namespace_dict = None

    async def connect(self):
        async with self._connection_lock:
            if self.client is None:
                logger.debug(f"Trying to connect to {self.url}")
                client = asyncua_client(url=self.url, timeout=connection_timeout)
                await client.connect()
                try:
                    namespace_array = await client.get_namespace_array()
                except Exception:
                    await self._disconnect_quietly(client)
                    raise
                logger.debug(f"Retrieved Namespacearray: {namespace_array}")
                self.namespace_dict = {name: idx for idx, name in enumerate(namespace_array)}
                self.client = client
                logger.info(f"Connection established to OPC UA server {self.url}")
            return self.client

    async def handle_read_failure(self):
        """A read failed. Drop the connection when the server is gone, so that the next read connects again."""
        async with self._connection_lock:
            client = self.client
            if client is None:
                return
            try:
                await client.get_node(ua.ObjectIds.Server_ServerStatus_State).read_value()
            except Exception as e:
                logger.warning(f"Connection to OPC UA server {self.url} is lost: {e}")
                self.client = None
                self.namespace_dict = None
                await self._disconnect_quietly(client)

    @staticmethod
    async def _disconnect_quietly(client):
        try:
            await client.disconnect()
        except Exception as e:
            logger.debug(f"Disconnecting failed: {e}")

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            self.client = None

    @classmethod
    async def get_instance(cls, url):
        async with cls._lock:
            if cls._client_instance is None:
                cls._client_instance = OPCUAClientManager(url)
            return cls._client_instance

    async def increment_subscriptions(self):
        async with self._subscription_lock:
            self.active_subscriptions += 1

    async def decrement_subscriptions(self):
        async with self._subscription_lock:
            self.active_subscriptions -= 1
            if self.active_subscriptions == 0:
                await self.disconnect()

    async def get_value(self, node):
        value = await node.get_value()
        return value

    async def get_var_node(self, client, nodeid, nsidx):
        full_nodeid = f'ns={nsidx};{nodeid}'
        logger.debug(f"Requesting {nodeid}")
        var_node = client.get_node(full_nodeid)
        return var_node

    async def get_namespace_idx(self, namespace):
        if self.namespace_dict is not None and namespace in self.namespace_dict:
            return self.namespace_dict[namespace]
        else:
            return None

    async def parse_attribute(self, map):
        nodeid = map['connectorAttribute']
        if 'nsu=' not in nodeid:
            return None
        try:
            ns_part, i_part = nodeid.split(';')
        except:
            ns_part = None
            i_part = nodeid
        if ns_part is not None:
            namespace = ns_part.split('=')[1]
        return i_part, namespace


asyncua_client = None

url = os.environ.get('OPCUA_TCP_CONNECT') or "opc.tcp://localhost:4840/"
connection_timeout = 10
try:
    connection_timeout = int(os.environ.get('OPCUA_TCP_CONNECTION_TIMEOUT'))
except:
    pass
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level, logging.INFO))
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logging.propagate = False
try:
    asyncua = importlib.import_module('asyncua')
    asyncua_client = asyncua.Client
    ua = asyncua.ua
except ImportError:
    print("The 'asyncua' library is not installed. Please install it separately to use this functionality.")


def is_structure(value):
    """NodeIds and the like are dataclasses in asyncua as well, but scalars for OPC UA."""
    return dataclasses.is_dataclass(value) and not isinstance(value, (ua.NodeId, ua.QualifiedName, ua.StatusCode))


def to_json(value):
    """Convert an OPC UA structure into plain JSON values, ByteStrings in the base64 form of OPC UA."""
    if is_structure(value):
        return {f'xsd:{field.name}': to_json(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [to_json(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode('ascii')
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def to_literal(value):
    """The RDF form of a value read from the server. A structure gets the form it has in the instances."""
    if is_structure(value):
        return Literal(json.dumps({'xsd:Body': {f'xsd:{type(value).__name__}': to_json(value)}}), datatype=RDF.JSON)
    return Literal(value)


def publish(map, value):
    if isinstance(value, ua.LocalizedText):
        map['value'] = Literal(value.Text)
        map['lang'] = value.Locale
    else:
        map['value'] = to_literal(value)
        map['lang'] = None
    map['updated'] = True


async def read_node(manager, nodeid, namespace):
    client = await manager.connect()
    nsidx = await manager.get_namespace_idx(namespace)
    if nsidx is None:
        raise ValueError(f'Server does not know namespace {namespace}')
    var = await manager.get_var_node(client, nodeid, nsidx)
    return await manager.get_value(var)


async def subscribe(map, firmware, sleeptime=5):
    """Read a node periodically and hand over its value.

    Neither a read which failed nor a node without a value (e.g. an optional, unset one) is a value: nothing is handed
    over, so the model keeps the last known value. Reading goes on, after a lost connection a new one is established.
    """
    manager = await OPCUAClientManager.get_instance(url)
    await manager.increment_subscriptions()
    nodeid, ns = await manager.parse_attribute(map)
    failing = False
    try:
        while True:
            logger.debug(f"Get value for {map['connectorAttribute']}")
            try:
                value = await read_node(manager, nodeid, ns)
            except Exception as e:
                # Reported once, not with every period
                if not failing:
                    logger.warning(f"Could not retrieve data for nodeid {map['connectorAttribute']}. Error: {e!r}")
                failing = True
                await manager.handle_read_failure()
            else:
                if failing:
                    logger.info(f"Retrieving data for nodeid {map['connectorAttribute']} again")
                failing = False
                logger.debug(f"Value {value} received")
                if value is not None:
                    publish(map, value)
            await asyncio.sleep(sleeptime)
    finally:
        await manager.decrement_subscriptions()
