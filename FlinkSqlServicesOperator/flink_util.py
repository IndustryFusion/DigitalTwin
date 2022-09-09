#
# Copyright (c) 2022 Intel Corporation
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
"""Helpers for communicating with Flink"""

import os
import requests

namespace = os.getenv("IFF_NAMESPACE", default="iff")
FLINK_URL = os.getenv("IFF_FLINK_REST",
                      default=f"http://flink-jobmanager-rest.{namespace}:8081")
DEFAULT_TIMEOUT = 60


class CancelJobFailedException(Exception):
    """Exception for a failed SQL Job cancellation"""


def get_job_status(logger, job_id):
    """Get job status as json dict as returned by Flink"""
    logger.debug(f"Requestion status for {job_id} from flink job-manager")
    job_response = requests.get(
        f"{FLINK_URL}/jobs/{job_id}", timeout=DEFAULT_TIMEOUT)
    if job_response.status_code == 404:
        return None
    job_response.raise_for_status()
    job_response = job_response.json()
    return job_response


def cancel_job(logger, job_id):
    """Cancel job with given id."""
    logger.debug(
        f"Requesting cancelation of job {job_id} from flink job-manager")
    response = requests.patch(
        f"{FLINK_URL}/jobs/{job_id}",
        timeout=DEFAULT_TIMEOUT)
    if response.status_code != 202:
        raise CancelJobFailedException("Could not cancel job {job_id}")


def stop_job(logger, job_id, savepoint_dir):
    """Stop a job and use savepoint
       Returns triggerid
    """
    logger.debug(f"Stop job {job_id} and request savepoint {savepoint_dir}")
    json = {}
    if savepoint_dir is not None:
        json = {"targetDirectory": f"{savepoint_dir}"}
    logger.info(f"sending object: {json}")
    job_response = requests.post(
        f"{FLINK_URL}/jobs/{job_id}/stop", json=json, timeout=DEFAULT_TIMEOUT)
    job_response.raise_for_status()
    if job_response.status_code != 202:
        raise CancelJobFailedException("Could not trigger stop of job "
                                       "{job_id}")
    job_response = job_response.json()
    logger.debug(f"Received job status: {job_response}")
    return job_response['request-id']


def get_savepoint_state(logger, job_id, savepoint_id):
    """Retrieves the state of the Savepoint trigger
       Returns a dictionary {"status": status, "location" location}
       Savepoint status:
       - IN_PROGRESS
       - SUCCESSFUL
       - NOT_FOUND
       - FAILED
    """
    logger.debug(f"Check state of savepoint trigger {savepoint_id}"
                 " for job  {job_id} ")
    response = requests.get(
        f"{FLINK_URL}/jobs/{job_id}/savepoints/{savepoint_id}",
        timeout=DEFAULT_TIMEOUT)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        if response.status_code == 404:
            logger.debug(f"Trigger {savepoint_id} not found")
            return {"status": "NOT_FOUND", "location": None}
    response.raise_for_status()
    if response.status_code != 200:
        raise CancelJobFailedException("Could not get status of savepoint"
                                       " trigger {savepoint_id} for job"
                                       " {job_id}")
    response = response.json()
    logger.info(f"Received job status: {response['status']}")
    status = response['status'].get('id')
    if status == "IN_PROGRESS":
        return {"status": status}
    try:
        if response['operation'] is None or \
                response['operation'].get('failure-cause') is not None:
            return {"status": "FAILED", "location": None}
    except KeyError:
        pass
    return {"status": response['status'].get('id'),
            "location": response['operation'].get('location')}
