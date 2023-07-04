#
# Copyright (c) 2023 Intel Corporation
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
# pylint: disable=duplicate-code

"""A kopf operator that manages Flink python udfs."""

import time
import os
from enum import Enum

import requests
import kopf

iff_namespace = os.getenv("IFF_NAMESPACE", default="iff")
FLINK_URL = os.getenv("IFF_FLINK_REST",
                      default="http://flink-jobmanager-rest"
                      f".{iff_namespace}:8081")

default_gateway_url = f"http://flink-sql-gateway.{iff_namespace}:9000"
FLINK_SQL_GATEWAY = os.getenv("IFF_FLINK_SQL_GATEWAY",
                              default=default_gateway_url)
DEFAULT_SAVEPOINT_DIR = "/flink-savepoints"
FLINK_SAVEPOINT_DIR = os.getenv("IFF_FLINK_SAVEPOINT_DIR",
                                default=DEFAULT_SAVEPOINT_DIR)
DEFAULT_TIMEOUT = 30

timer_interval_seconds = int(os.getenv("TIMER_INTERVAL", default="10"))
timer_backoff_seconds = int(os.getenv("TIMER_BACKOFF_INTERVAL", default="10"))
timer_backoff_temp_failure_seconds = int(
    os.getenv("TIMER_BACKOFF_TEMPORARY_FAILURE_INTERVAL", default="30"))


class DeploymentFailedException(Exception):
    """Deployment failed exception."""


class States(Enum):
    """Sync states"""
    SYNCED = "Uploading"
    FAILED = "Uploaded"


STATE = "state"
CLASS = 'class'
VERSION = 'version'


@kopf.on.create("industry-fusion.com", "v1alpha1", "flinkpythonudf")
# pylint: disable=unused-argument
# Kopf decorated functions match their expectations
def create(body, spec, patch, logger, **kwargs):
    """Handle k8s create event."""
    name = body["metadata"].get("name")
    namespace = body["metadata"].get("namespace")
    kopf.info(body, reason="Creating",
              message=f"Creating flinkpythonudf {name}"
              f"in namespace {namespace}")
    logger.info(
        f"Created flinkpythonudf {name} in namespace {namespace}")
    patch.status[STATE] = States.SYNCED.name
    try:
        post_file(spec, logger)
    except DeploymentFailedException as err:
        logger.warning(f"Could not upload udf: {err}")
        patch.status[STATE] = States.FAILED.name
    return {"createdOn": str(time.time())}


@kopf.on.update("industry-fusion.com", "v1alpha1", "flinkpythonudf")
# pylint: disable=unused-argument
# Kopf decorated functions match their expectations
def update(body, spec, patch, logger, retries=20, **kwargs):
    """
    Updates means set state to syncing
    - Checks whether updateStrategy is defined
        - If update strategy is defined transit to SAVEPOINTING
        - ELSE move direclty to UPDATING
    """
    logger.info("update triggered")
    patch.status[STATE] = States.SYNCED.name
    try:
        post_file(spec, logger)
    except DeploymentFailedException as err:
        logger.warning(f"Could not upload udf: {err}")
        patch.status[STATE] = States.FAILED.name
    return {"updatedOn": str(time.time())}


@kopf.timer("industry-fusion.com", "v1alpha1", "flinkpythonudf",
            interval=timer_interval_seconds, backoff=timer_backoff_seconds)
# pylint: disable=too-many-arguments unused-argument redefined-outer-name
# pylint: disable=too-many-locals too-many-statements
# Kopf decorated functions match their expectations
def monitor(patch, logger, body, spec, **kwargs):
    """
    Managaging the main lifecycle of the flinkpythonudf CRD
    Current state is stored under
    STATE can be
        - SYNCED - uploaded to flink jobmanager
        - FAILED - uploading failed
    """
    filename = spec.get('filename')
    version = spec.get('version')
    fullname = f'{filename}_{version}'
    try:
        result = check_file_state(fullname)
    except requests.RequestException:
        patch.status[STATE] = States.FAILED.name
        logger.error("Could not check file state.")
        return {"monitoredOn": str(time.time())}
    patch.status[STATE] = States.SYNCED.name
    if result == 404:
        try:
            post_file(spec, logger)
        except DeploymentFailedException as err:
            logger.error(f"Could not upload udf: {err}")
            patch.status[STATE] = States.FAILED.name
    logger.info("monitoring triggered")
    return {"monitoredOn": str(time.time())}


def check_file_state(filename):
    """Get udf file state from sql-gateway
    """
    url = f"{FLINK_SQL_GATEWAY}/v1/python_udf/{filename}"
    response = requests.get(url,
                            timeout=DEFAULT_TIMEOUT)
    return response.status_code


def post_file(spec, logger):
    """Post spec data to gateway
    """
    filename = spec.get('filename')
    version = spec.get('version')
    fullname = f'{filename}_{version}'
    udf = spec.get(CLASS)

    url = f"{FLINK_SQL_GATEWAY}/v1/python_udf/{fullname}"
    logger.debug(f"Deployment udf to SQL Gateway {url}")
    try:
        response = requests.post(url,
                                 timeout=DEFAULT_TIMEOUT,
                                 data=udf.encode('utf-8'),
                                 headers={'Content-Type': 'text/plain'})
    except Exception as err:
        raise DeploymentFailedException(
            f"Could not deploy job to {url}, server unreachable ({err})")\
            from err
    if response.status_code != 201:
        raise DeploymentFailedException(
            f"Could not deploy job to {url}, server returned:"
            f"{response.status_code}")
