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

"""A kopf operator that manages JAR jobs on flink."""

import os
import os.path
import ftplib
import time
import uuid
import re
import kopf
import requests

import util

namespace = os.getenv("IFF_NAMESPACE") or "iff"
FLINK_URL = os.getenv(
    "IFF_FLINK_REST") or f"http://flink-jobmanager-rest.{namespace}:8081"
JOB_STATUS_UNKNOWN = "UNKNOWN"
JOB_STATUS_FAILED = "FAILED"
JOB_STATUS_CANCELED = "CANCELED"
JOB_STATUS_FIXING = "OPERATOR TRIES TO FIX"
DEFAULT_TIMEOUT = 60


@kopf.on.create("industry-fusion.com", "v1", "beamservices")
# pylint: disable=unused-argument
# Kopf decorated functions match their expectations
def create(body, spec, patch, **kwargs):
    """Handle job creation"""
    kopf.info(body, reason="Creating",
              message="Creating beamservices" + str(spec))
    return {"createdOn": str(time.time())}


@kopf.timer("industry-fusion.com", "v1", "beamservices", interval=10, idle=5)
# pylint: disable=unused-argument too-many-arguments
# Kopf decorated functions match their expectations
async def updates(stopped, patch, logger, body, spec, status, **kwargs):
    """Repeteadely check job status and take necessary actions,
    such as deployment once fetching is complete, or redeployment
    after failure."""
    update_status = status.get("updates")
    if update_status is None:
        kopf.info(body, reason="Status None", message="Status is none")
        return {"deployed": False, "jobCreated": False}

    if not update_status.get("deployed"):
        # try to delete old jars if existing
        delete_jar(body, status.get("jarfile"))
        patch.status["jarfile"] = None
        # Now try to deploy new one
        return {"deployed": True, "jarId": deploy(body, spec, patch)}

    if not update_status.get("jobCreated"):
        # before creating job, check whether jobmanager is ready
        # sometimes if it is not ready, deployments are failing and
        # this leads to LONG timeout until all is running again
        if check_readiness(body) == 0:
            return
        job_id = create_job(body, spec, update_status["jarId"])
        if job_id is not None:
            return {"jobCreated": True, "jobId": job_id}
        # something is wrong, so try everything again
        return {"deployed": False, "jobCreated": False}

    # check if job exists. If it exists, check whether the state is FAILED
    # all other states should be handled by jobmanager
    job_status = JOB_STATUS_UNKNOWN
    # Hmm, but what is the jobname prefix?
    # Assumption: lowercased entry class name
    try:
        jobs = requests.get(
            f"{FLINK_URL}/jobs",
            timeout=DEFAULT_TIMEOUT).json().get("jobs", [])
        # check whether job is in the list
        job_id = update_status.get("jobId")
        # if we have a job_id, check wether it is running
        need_job_restart = True
        for element in jobs:
            if element['id'] == job_id:
                if (element['status'] != JOB_STATUS_FAILED
                        and element['status'] != JOB_STATUS_CANCELED):
                    # job exists but failed
                    # for all other states, assume that jobmanager is taking
                    # care for restarting
                    need_job_restart = False
                    job_status = element['status']
                continue
            # Make sure that there are no old artefacts
            # i.e. jobs with the resource prefix
            # but not handled by us any longer
            # First get detail of the job
            job_name = requests.get(
                f"{FLINK_URL}/jobs/{element['id']}",
                timeout=DEFAULT_TIMEOUT).json().get("name")
            # cancel if it has the resource prefix
            name = get_jobname_prefix(body, spec)
            if name is not None and job_name.startswith(name):
                # AND if it is not already in cancelled or failed state
                if (element['status'] != JOB_STATUS_CANCELED
                        and element['status'] != JOB_STATUS_FAILED):
                    cancel_job(element['id'])
        if need_job_restart:
            return {"deployed": False, "jobCreated": False, "redeployed": True}
    except (ConnectionRefusedError, requests.ConnectionError):
        patch.status['state'] = job_status

    patch.status['state'] = job_status
    # return {"jobStatus": job_status.json().get("state")}


@kopf.on.delete("industry-fusion.com", "v1", "beamservices")
# pylint: disable=unused-argument too-many-arguments
# Kopf decorated functions match their expectations
def delete(body, **kwargs):
    """Delete given Beam Service."""
    try:
        update_status = body["status"].get("updates")
    except KeyError:
        return
    if not update_status:
        return
    job_id = update_status.get("jobId")
    if job_id:
        cancel_job(job_id)


def download_file_via_http(url):
    """Download the file and return the saved path."""
    response = requests.get(url, timeout=DEFAULT_TIMEOUT)
    path = "/tmp/" + str(uuid.uuid4()) + ".jar"
    with open(path, "wb") as download_file:
        download_file.write(response.content)
    return path


def download_file_via_ftp(url, username, password):
    """Download the file vie ftp and return the saved path."""
    local_path = "/tmp/" + str(uuid.uuid4()) + ".jar"
    url_without_protocol = url[6:]
    addr = url_without_protocol.split("/")[0]
    remote_path = "/".join(url_without_protocol.split("/")[1:])
    with open(local_path, "wb") as download_file:
        with ftplib.FTP(addr, username, password) as ftp:
            ftp.retrbinary(f"RETR {remote_path}", download_file.write)
    return local_path


def deploy(body, spec, patch):
    """Deploy the specified file to flink cluster."""
    # TODO Create schema for spec in CRD
    package = spec["package"]
    url = package["url"]
    kopf.info(body, reason="Jar download",
              message=f"Downloading from {url}")
    if url.startswith("http"):
        jarfile_path = download_file_via_http(url)
    elif url.startswith("ftp"):
        jarfile_path = download_file_via_ftp(
            url, package["username"], package["password"])
    else:
        raise kopf.PermanentError(
            "Jar download failed. Invalid url (must start with http or ftp)")
    patch.status["jarfile"] = jarfile_path
    try:
        with open(jarfile_path, "rb") as jarfile:
            response = requests.post(
                f"{FLINK_URL}/jars/upload",
                files={"jarfile": jarfile},
                timeout=DEFAULT_TIMEOUT)
            if response.status_code != 200:
                delete_jar(body, jarfile_path)
                raise kopf.TemporaryError(
                    "Jar submission failed."
                    f"Status code: {response.status_code}",
                    delay=10)
    except requests.exceptions.RequestException as exc:
        delete_jar(body, jarfile_path)
        raise kopf.TemporaryError(
            f"Jar submission failed. Error: {exc}", delay=10)
    jar_id = response.json()["filename"].split("/")[-1]
    kopf.info(body, reason="BeamDeploymentSuccess",
              message=f"Submitted jar with id: {jar_id}")
    return jar_id


def build_args(args_dict, tokens):
    """Given a dictionary of arguments, build the corresponding encoded
    argument string."""
    args_str = ""
    for key, val in args_dict.items():
        if isinstance(val, str):
            args_str += f"--{key}={val} "
            continue
        assert isinstance(val, dict), "Values should be str or dict."
        assert "format" in val, "'format' is mandatory"
        val = util.format_template(
            val["format"], tokens=tokens, encode=val.get("encode"))
        args_str += f"--{key}={val} "
    return args_str


def create_job(body, spec, jar_id):
    """Create job after the required jar was submitted."""
    entry_class = spec["entryClass"]
    tokens = util.get_tokens(spec.get("tokens", []))
    kopf.info(body, reason="Got tokens", message=str(tokens))
    args = build_args(spec["args"], tokens)
    kopf.info(body, reason="Args Parsed",
              message=args)
    response = requests.post(f"{FLINK_URL}/jars/{jar_id}/run",
                             json={"entryClass": entry_class,
                                   "programArgs": args},
                             timeout=DEFAULT_TIMEOUT)
    if response.status_code != 200:
        kopf.info(body, reason="BeamExecutionFailed",
                  message="Could not run job, server returned:"
                  + response.status_code)
        return None
    job_id = response.json().get("jobid")
    kopf.info(body, reason="Job created", message=f"Job id: {job_id}")
    return job_id


def delete_jar(body, jar_path):
    """Delete jar at given filepath."""
    if jar_path is not None:
        if os.path.isfile(jar_path):
            try:
                os.remove(jar_path)
            except OSError as exc:
                kopf.info(body, reason="Jar deleting",
                          message=f"Could not delte jar file: {exc}")
            kopf.info(body, reason="Jar deleted",
                      message=f"Jar file: {jar_path}")


def check_readiness(body):
    """Return number of free slots."""
    try:
        response = requests.get(
            f"{FLINK_URL}/overview",
            timeout=DEFAULT_TIMEOUT)
        if response.status_code == 200:
            free_slots = response.json()["slots-total"]
            return free_slots
    except (requests.exceptions.RequestException, KeyError) as exc:
        kopf.info(body, reason="jobmanager overview",
                  message="Exception while trying to check cluster state."
                  f"Reason: {exc}")
    return 0


def cancel_job(job_id):
    """Cancel job with the given job_id."""
    try:
        response = requests.patch(
            f"{FLINK_URL}/jobs/{job_id}",
            timeout=DEFAULT_TIMEOUT)
        if response.status_code != 202:
            raise kopf.TemporaryError(
                "Could not cancel job from cluster", delay=5)
    except requests.exceptions.RequestException as exc:
        raise kopf.TemporaryError(
            "Could not cancel job from cluster: {e}", delay=5) from exc


def get_jobname_prefix(body, spec):
    """Get name prefix from spec."""
    prefix_match = re.compile(r"\w*$")
    classname = spec["entryClass"]
    jobname = prefix_match.search(classname)[0]

    if jobname is not None:
        jobname = jobname.lower()
        kopf.info(body, reason="debugging",
                  message=f"found jobname {jobname} in {classname}")
    return jobname
