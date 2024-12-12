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
import logging
import asyncio
import importlib
from rdflib import Literal
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
                self.client = asyncua_client(url=self.url, timeout=connection_timeout)
                try:
                    await self.client.connect()
                    await self.get_namespace_dict()
                except asyncio.TimeoutError:
                    logger.error("Timeout Error whily trying  to connect to OPCUA Server")
                    raise
                if self.namespace_dict is None:
                    self.client = None
                logger.info(f"Connection established to OPC UA server {url}")

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

    async def get_var_node(self, nodeid, nsidx):
        full_nodeid = f'ns={nsidx};{nodeid}'
        logger.debug(f"Requesting {nodeid}")
        var_node = self.client.get_node(full_nodeid)
        return var_node

    async def get_namespace_idx(self, namespace):
        if self.namespace_dict is not None and namespace in self.namespace_dict:
            return self.namespace_dict[namespace]
        else:
            return None

    async def get_namespace_dict(self):
        namespace_array = await self.client.get_namespace_array()
        logger.debug(f"Retrieved Namespacearray: {namespace_array}")
        self.namespace_dict = {name: idx for idx, name in enumerate(namespace_array)}

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


async def subscribe(map, firmware, sleeptime=5):
    manager = await OPCUAClientManager.get_instance(url)
    await manager.connect()
    await manager.increment_subscriptions()
    nodeid, ns = await manager.parse_attribute(map)
    nsidx = await manager.get_namespace_idx(ns)
    var = await manager.get_var_node(nodeid, nsidx)
    try:
        while True:
            logger.debug(f"Get value for {map['connectorAttribute']}")
            try:
                value = await manager.get_value(var)
            except Exception as e:
                logger.warning(f"Warning: Could not retrieve data for nodeid {map['connectorAttribute']}. Error: {e}")
                value = None
            logger.debug(f"Value {value} received")
            if isinstance(value, ua.LocalizedText):
                map['value'] = Literal(value.Text)
                map['lang'] = value.Locale
            else:
                map['value'] = Literal(value)
                map['lang'] = None
            map['updated'] = True
            await asyncio.sleep(sleeptime)
    except Exception as sub_error:
        logger.error(f"Error in subscription loop: {sub_error}")
    finally:
        await manager.decrement_subscriptions()
