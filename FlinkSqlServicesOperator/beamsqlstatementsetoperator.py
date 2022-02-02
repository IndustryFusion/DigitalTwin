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

"""A kopf operator that manages SQL jobs on flink."""

import time
import datetime
import os
from enum import Enum

import requests
import kopf

import flink_util
import tables_and_views

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

timer_interval_seconds = int(os.getenv("TIMER_INTERVAL", default="10"))
timer_backoff_seconds = int(os.getenv("TIMER_BACKOFF_INTERVAL", default="10"))
timer_backoff_temp_failure_seconds = int(
    os.getenv("TIMER_BACKOFF_TEMPORARY_FAILURE_INTERVAL", default="30"))


class States(Enum):
    """SQL Job states as defined by Flink"""
    INITIALIZED = "INITIALIZED"
    DEPLOYING = "DEPLOYING"
    DEPLOYMENT_FAILURE = "DEPLOYMENT_FAILURE"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    CANCELING = "CANCELING"
    UPDATING = "UPDATING"
    SAVEPOINTING = "SAVEPOINTING"
    FINISHED = "FINISHED"
    UNKNOWN = "UNKNOWN"
    NOT_FOUND = "NOT_FOUND"


class SavepointStates(Enum):
    """Savepoint states as defined by Flink"""
    SUCCESSFUL = "SUCCESSFUL"
    IN_PROGRESS = "IN_PROGRESS"
    NOT_FOUND = "NOT_FOUND"
    FAILED = "FAILED"


class DeploymentFailedException(Exception):
    """Deployment failed exception."""


JOB_ID = "job_id"
STATE = "state"
SAVEPOINT_ID = "savepoint_id"
SAVEPOINT_LOCATION = "location"
SAVEPOINT_STATUS = "status"
MESSAGES = "messages"
UPDATE_STRATEGY = "updateStrategy"
UPDATE_STRATEGY_SAVEPOINT = "savepoint"
UPDATE_STRATEGY_NONE = "none"


@kopf.on.create("industry-fusion.com", "v1alpha2", "beamsqlstatementsets")
# pylint: disable=unused-argument
# Kopf decorated functions match their expectations
def create(body, spec, patch, logger, **kwargs):
    """Handle k8s create event."""
    name = body["metadata"].get("name")
    namespace = body["metadata"].get("namespace")
    kopf.info(body, reason="Creating",
              message=f"Creating beamsqlstatementsets {name}"
              f"in namespace {namespace}")
    logger.info(
        f"Created beamsqlstatementsets {name} in namespace {namespace}")
    patch.status[STATE] = States.INITIALIZED.name
    patch.status[JOB_ID] = None
    return {"createdOn": str(time.time())}


@kopf.on.delete("industry-fusion.com", "v1alpha2", "beamsqlstatementsets",
                retries=10)
# pylint: disable=unused-argument
# Kopf decorated functions match their expectations
def delete(body, spec, patch, logger, **kwargs):
    """
    Deleting beamsqlstatementsets

    If state is not CANCELING and not CANCELED and job_id defined,
    refresh status and trigger cancelation if needed
    If Canceling, refresh state, when canceled, allow deletion,otherwise wait
    """
    name = body["metadata"].get("name")
    namespace = body["metadata"].get("namespace")

    state = body['status'].get(STATE)
    job_id = body['status'].get(JOB_ID)
    if job_id and state not in [States.CANCELED.name, States.CANCELING.name]:
        try:
            refresh_state(body, patch, logger)
            if patch.status[STATE]:
                state = patch.status[STATE]
            if state not in [States.CANCELING.name, States.CANCELED.name]:
                flink_util.cancel_job(logger, job_id)
        except (KeyError, flink_util.CancelJobFailedException,
                kopf.TemporaryError) as err:
            raise kopf.TemporaryError(
                f"Error trying to cancel {namespace}/{name}"
                + f"with message {err}. Trying again later", 10)
        # cancelation went through, delete job_id and update state
        patch.status[JOB_ID] = None
        patch.status[STATE] = States.CANCELING.name
        raise kopf.TemporaryError(
            f"Waiting for confirmation of cancelation for {namespace}/{name}",
            5)

    if state == States.CANCELING.name:
        refresh_state(body, patch, logger)
        if not patch.status[STATE] == States.CANCELED.name:
            raise kopf.TemporaryError(
                "Canceling, waiting for final confirmation of cancelation"
                f"for {namespace}/{name}", 5)
    kopf.info(body, reason="deleting",
              message=f" {namespace}/{name} cancelled and ready for deletion")
    logger.info(f" {namespace}/{name} cancelled and ready for deletion")


@kopf.index('industry-fusion.com', "v1alpha2", "beamsqltables")
# pylint: disable=missing-function-docstring
def beamsqltables(name: str, namespace: str, body: kopf.Body, **_):
    return {(namespace, name): body}


@kopf.index('industry-fusion.com', "v1alpha1", "beamsqlviews")
# pylint: disable=missing-function-docstring
def beamsqlviews(name: str, namespace: str, body: kopf.Body, **_):
    return {(namespace, name): body}


@kopf.on.update("industry-fusion.com", "v1alpha2", "beamsqlstatementsets")
# pylint: disable=unused-argument
# Kopf decorated functions match their expectations
def update(body, spec, patch, logger, retries=20, **kwargs):
    """
    Updates a statementset
    - Checks whether updateStrategy is defined
        - If update strategy is defined transit to SAVEPOINTING
        - ELSE move direclty to UPDATING
    """
    logger.info("update triggered")
    state = body['status'].get(STATE)
    job_id = body['status'].get(JOB_ID)
    namespace = body['metadata'].get("namespace")
    metadata_name = body['metadata'].get("name")
    update_strategy = spec.get(UPDATE_STRATEGY)
    logger.debug(f"update strategy is {update_strategy}")
    if update_strategy is None or update_strategy == UPDATE_STRATEGY_NONE:
        # No update strategy. Cancel the current job and deploy it new
        try:
            cancel_job_and_get_state(logger, body, patch)
        except requests.exceptions.RequestException as exc:
            logger.error("Could not cancel job in update process."
                         "Try again later"
                         f"{namespace}/{metadata_name}."
                         f"{exc}")
            raise kopf.TemporaryError("Could not cancel job in update process."
                                      " Try again later"
                                      f"{namespace}/{metadata_name}."
                                      f"{exc}",
                                      timer_backoff_temp_failure_seconds)\
                from exc
        patch.status[STATE] = States.UPDATING.name
        patch.status[SAVEPOINT_ID] = None
        patch.status[SAVEPOINT_LOCATION] = None
    elif update_strategy == UPDATE_STRATEGY_SAVEPOINT:
        try:
            savepoint_id = body['status'].get(SAVEPOINT_ID)
        except KeyError:
            savepoint_id = None
        if state == States.RUNNING.name:
            try:
                savepoint_id = flink_util.stop_job(logger, job_id, None)
            except requests.exceptions.RequestException as exc:
                logger.error("Could not stop and savepoint job in "
                             f"{namespace}/{metadata_name}."
                             f"{exc}")
                raise kopf.TemporaryError("Could not stop and savepoint job in"
                                          f" {namespace}/{metadata_name}."
                                          f"{exc}",
                                          timer_backoff_temp_failure_seconds)\
                    from exc
            patch.status[STATE] = States.SAVEPOINTING.name
            patch.status[SAVEPOINT_ID] = savepoint_id
        # wait for savepoint to complete
        if savepoint_id is not None:
            job_id = body['status'].get(JOB_ID)
            savepoint_state = flink_util.get_savepoint_state(
                logger, job_id, savepoint_id)
            logger.debug(f"savepoint state {savepoint_state}")
            if savepoint_state.get(SAVEPOINT_STATUS) in [
              SavepointStates.FAILED.name, SavepointStates.NOT_FOUND.name]:
                # Savepointing not possible
                add_message(logger, body, patch,
                            "Savepointing failed! "
                            "Check Service configuration.",
                            "update failure")
                patch.status[STATE] = States.RUNNING.name
                patch.status[SAVEPOINT_ID] = None
                patch.status[SAVEPOINT_LOCATION] = None
            elif savepoint_state.get(SAVEPOINT_STATUS) in [
              SavepointStates.IN_PROGRESS.name]:
                logger.debug("Savepointing still in progress"
                             "try come back later")
                raise kopf.TemporaryError("Savepointing still in progress"
                                          " try come back later",
                                          timer_backoff_temp_failure_seconds)
            else:
                # savepoint is Completed successfully, now do the updating
                add_message(logger, body, patch,
                            "Savepointing completed! Now updating.",
                            "messsage")
                logger.debug("Savepoint Completed. Now go to updating state.")
                patch.status[SAVEPOINT_LOCATION] = \
                    savepoint_state.get(SAVEPOINT_LOCATION)
                patch.status[STATE] = States.UPDATING.name


@kopf.timer("industry-fusion.com", "v1alpha2", "beamsqlstatementsets",
            interval=timer_interval_seconds, backoff=timer_backoff_seconds)
# pylint: disable=too-many-arguments unused-argument redefined-outer-name
# pylint: disable=too-many-locals
# Kopf decorated functions match their expectations
def monitor(beamsqltables: kopf.Index, beamsqlviews: kopf.Index, patch, logger,
            body, spec, status, **kwargs):
    """
    Managaging the main lifecycle of the beamsqlstatementset crd
    Current state is stored under
    status:
        state: STATE
        job_id: string
    STATE can be
        - INITIALIZED - resource is ready to deploy job. job_id: None
        - DEPLOYING - resource has been deployed, job_id: flink_id
        - RUNNING - resource is running job_id: flink_id
        - FAILED - resource is in failed state
        - DEPLOYMENT_FAILURE - something went wrong while operator tried to
          deploy (e.g. server returned 500)
        - CANCELED - resource has been canceled
        - CANCELING - resource is in cancelling process
        - UNKNOWN - resource cannot be monitored
        - SAVEPOINTING - resource is currently trying to create a savepoint
        - UPDATING - resource is currently updating, i.e. removing old jobid
            and creating new one

    Transitions:
        - undefined/INITIALIZED => DEPLOYING
        - INITIALIZED => DEPLOYMENT_FAILURE
        - DEPLOYMENT_FAILURE => DEPLOYING
        - DEPLOYING/UNKNOWN =>FLINK_STATES(RUNNING/FAILED/CANCELLED/CANCELLING)
        - delete resource => CANCELLING
        - delete done => CANCELLED
    Currently, cancelled state is not recovered
    """
    namespace = body['metadata'].get("namespace")
    metadata_name = body['metadata'].get("name")
    try:
        state = body['status'].get(STATE)
    except (KeyError, TypeError):
        create(body, spec, patch, logger, **kwargs)
        return

    logger.debug(
        f"Triggered monitor for {namespace}/{metadata_name}"
        f" with state {state}")
    name = spec.get('name')
    if not name:
        message = f"No name specified in spec of {namespace}/{metadata_name}"
        logger.warning(message)
        name = metadata_name
    if state in [States.INITIALIZED.name, States.DEPLOYMENT_FAILURE.name]:
        # deploying
        logger.debug(f"Deploying {namespace}/{name}")

        # create the full statement in the folloing order:
        # (1) SET statements (sqlsettings)
        # (2) Tables
        # (3) Views

        ddls = create_sets(spec, body, namespace, name, logger)

        # get first all table ddls
        # get inputTable and outputTable

        ddls += create_tables(beamsqltables, spec, body, namespace, name,
                              logger)

        # Now get all views
        try:
            if spec.get("views") is not None:
                ddls += "\n".join(tables_and_views.create_view(
                    list(beamsqlviews[(namespace, view_name)])[0]
                    ) for view_name in spec.get("views")) + "\n"

        except (KeyError, TypeError) as exc:
            logger.error("Views could not be created for "
                         f"{namespace}/{name}."
                         "Check the views definitions and table references: "
                         f"{exc}")
            raise kopf.TemporaryError("Views could not be created for "
                                      f"{namespace}/{name}. Check the view"
                                      "definitions and table references: "
                                      f"{exc}",
                                      timer_backoff_temp_failure_seconds)\
                from exc

        # now create statement set
        statementset = ddls
        statementset += "BEGIN STATEMENT SET;\n"
        statementset += "\n".join(spec.get("sqlstatements")) + "\n"
        # TODO: check for "insert into" prefix and terminating ";"
        # in sqlstatement
        statementset += "END;"
        logger.debug(f"Now deploying statementset {statementset}")
        try:
            patch.status[JOB_ID] = deploy_statementset(statementset, logger)
            patch.status[STATE] = States.DEPLOYING.name
            return
        except DeploymentFailedException as err:
            # Temporary error as we do not know the reason
            patch.status[STATE] = States.DEPLOYMENT_FAILURE.name
            patch.status[JOB_ID] = None
            logger.error(f"Could not deploy statementset {err}")
            raise kopf.TemporaryError(
                f"Could not deploy statement: {err}",
                timer_backoff_temp_failure_seconds)

    # If state is UPDATING - monitor the job status
    # and if it is CANCELED => create new one
    if state == States.UPDATING.name:
        logger.debug("Processing updating state")
        job_state = get_job_state(logger, body)
        if job_state in [States.CANCELED.name, States.FINISHED.name]:
            add_message(logger, body, patch,
                        "Updating successful: Cancelled/Finished"
                        " old job and creating new one",
                        "message")
            create(body, spec, patch, logger, **kwargs)

    # If state is not INITIALIZED, DEPLOYMENT_FAILURE nor CANCELED,
    # the state is monitored
    if state not in [States.CANCELED.name,
       States.CANCELING.name, States.SAVEPOINTING.name, States.UPDATING.name]:
        refresh_state(body, patch, logger)
        if patch.status[STATE] == States.NOT_FOUND.name:
            logger.info("Job seems to be lost. Will re-initialize")
            patch.status[STATE] = States.INITIALIZED.name
            patch.status[JOB_ID] = None


# pylint: disable=too-many-arguments unused-argument redefined-outer-name
# kopf is ingesting too many parameters, this is inherite by subroutine
def create_tables(beamsqltables, spec, body, namespace, name, logger):
    """
    create tables from beamsqltables index
    """
    ddls = ""
    try:
        ddls += "\n".join(tables_and_views.create_ddl_from_beamsqltables(
            list(beamsqltables[(namespace, table_name)])[0],
            logger) for table_name in spec.get("tables")) + "\n"

    except (KeyError, TypeError) as exc:
        logger.error("Table DDLs could not be created for "
                     f"{namespace}/{name}."
                     "Check the table definitions and references.")
        raise kopf.TemporaryError("Table DDLs could not be created for "
                                  f"{exc}"
                                  f"{namespace}/{name}. Check the table"
                                  "definitions and references: "f"{exc}",
                                  timer_backoff_temp_failure_seconds)\
            from exc
    return ddls


def create_sets(spec, body, namespace, name, logger):
    """
    create the list of SET statements which configures the
    statementsets
    """
    sets = ""
    sqlsettings = spec.get('sqlsettings')
    if not sqlsettings:
        message = "pipeline name not determined in"\
                  f" {namespace}/{name}, using default"
        logger.debug(message)
        sets = f"SET pipeline.name = '{namespace}/{name}';\n"
    elif all(x for x in sqlsettings if x.get('pipeline.name') is None):
        sets = f"SET pipeline.name = '{namespace}/{name}';\n"
        for setting in sqlsettings:
            key = list(setting.keys())[0]
            value = setting.get(key)
            sets += f"SET '{key}' = '{value}';\n"
    # add savepoint if location is set
    try:
        savepoint_location = body['status'].get(SAVEPOINT_LOCATION)
        if savepoint_location is not None:
            sets += f"SET execution.savepoint.path = '{savepoint_location}';\n"
        logger.debug(f"Savepoint location {savepoint_location} used for sets.")
    except KeyError:
        pass

    return sets


def refresh_state(body, patch, logger):
    """Refrest patch.status.state"""
    job_id = body['status'].get(JOB_ID)
    job_info = None
    try:
        job_info = flink_util.get_job_status(logger, job_id)
    except requests.HTTPError as exc:
        if exc.response.status_code == 404:
            patch.status[STATE] = States.NOT_FOUND.name
            return
    except requests.exceptions.RequestException as exc:
        patch.status[STATE] = States.UNKNOWN.name
        raise kopf.TemporaryError(
            f"Could not monitor task {job_id}: {exc}",
            timer_backoff_temp_failure_seconds) from exc
    if job_info is not None:
        patch.status[STATE] = job_info.get("state")
    else:
        # API etc works but no job found. Can happen for instance
        # after restart of job manager
        # In this case, we need to signal that stage
        patch.status[STATE] = States.UNKNOWN.name


def deploy_statementset(statementset, logger):
    """
    deploy statementset to flink SQL gateway

    A statementset is deployed to the flink sql gateway.
    It is expected that all statements in a set are inserting
    the result into a table.
    The table schemas are defined at the beginning

    Parameter
    ---------
    statementset: string
        The fully defined statementset including table ddl
    logger: obj
        logger obj
    returns: jobid: string or exception if deployment was not successful
        id of the deployed job

    """
    request = f"{FLINK_SQL_GATEWAY}/v1/sessions/session/statements"
    logger.debug(f"Deployment request to SQL Gateway {request}")
    try:
        response = requests.post(request,
                                 json={"statement": statementset})
    except requests.RequestException as err:
        raise DeploymentFailedException(
            f"Could not deploy job to {request}, server unreachable ({err})")\
            from err
    if response.status_code != 200:
        raise DeploymentFailedException(
            f"Could not deploy job to {request}, server returned:"
            f"{response.status_code}")
    logger.debug(f"Response: {response.json()}")
    job_id = response.json().get("jobid")
    return job_id


def cancel_job_and_get_state(logger, body, patch):
    """
    Cancel job if it is running
    and return the Job state
    """
    job_id = body['status'].get(JOB_ID)
    job_info = flink_util.get_job_status(logger, job_id)
    job_state = job_info.get("state")
    if job_state == States.RUNNING.name:
        flink_util.cancel_job(logger, job_id)
    return job_state


def get_job_state(logger, body):
    """
    Get job state
    """
    job_id = body['status'].get(JOB_ID)
    job_info = flink_util.get_job_status(logger, job_id)
    job_state = job_info.get("state")
    logger.debug(f"job state is {job_state}")
    return job_state


def add_message(logger, body, patch, reason, mtype):
    """
    add message to status oject of CR
    """
    messages = body.status.get(MESSAGES)
    if messages is None:
        messages = []
    messages.append({"timestamp": f"{datetime.datetime.now()}",
                    "type": mtype, "message": reason})
    patch.status[MESSAGES] = messages
