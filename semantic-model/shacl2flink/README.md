# Digital Twin Shacl to Flink Transformation

This directory contains the translation mechanism from SHACL basee constraints and rules to SQL/Flink.
There are always three ingredients to such a translation, called KMS (Knowledge, Model-instance, SHACL)

- **K**nowledge contains OWL/RDF data, preferable serialized in Turtle
- **M**odel-instance describes the actual instances/objects of the setup. These are described in JSON-LD/NGSI-LD.
- **S**HACL is the W3C standard describing the constraints and rules for the model with respect to the Knowledge.

A first [overview](../datamodel/README.md) and [tutorial](../datamodel/Tutorial.md) can be found in the [datamodel](../datamodel/) directory.

# Table of Contents

1. [Quick Setup](#quick-setup)
2. [KMS Examples & Tutorial](./docs/examples.md)
3. [Supported SHACL Features](./docs/supported-features.md)
4. User Defined Functions
3. [Build and test KMS](#build-and-test-kms)
4. [Deploy Flink-Jobs](#deploy-flink-jobs)
5. [References](#references)

# Quick Setup

## Requirements

- You need to have Python > 3.8
- Virtualenv needs to be installed
- `sqlite3` and `sqlite3-pcre` need to be installed

  ```bash
  sudo  apt install sqlite3 libsqlite3-dev libpcre2-dev
  ```

## Installation

If miniconda installed with python3.10 environment (using prepare-platform.sh), move to step 2 else use below script to install and create python env
### Step 1 :
```bash
bash pyenv_setup.sh
source ./miniconda3/bin/activate
conda create -n py310 python=3.10 -y
```
### Step 2 :
Everytime you are starting a new shell you need to enable the miniconda Virtual Environment which runs python 3.10 sourcing miniconda installation path:

```bash
source ./miniconda3/bin/activate
conda activate py310
make setup
```

## VS Code

Normally VS Code should recognize the virtual environment and ask you if you want to use the virtual environment as you Python interpreter.
If not you can do it manually.
Press `Ctrl + Shift + p` and type `Python: Select Interpreter` and select the virtual environment in the _venv/_ folder.

## Development

Install the development dependencies:

```bash
source ./miniconda3/bin/activate
conda activate py310
pip install -r requirements-dev.txt
```

### Unittests

Run with

```bash
make test
```
## Linting

Run with

```bash
make lint
```


# Build and Test KMS
## Build KMS directory

The build reads a KMS package (see `../kms/README.md`): `KMS ?= ../kms/default`,
the package `kms/default` links to, and `make KMS=../kms/<name>` picks another.
`make prepare-kms KMS_DIR=<dir>` copies `<dir>` (relative to `../kms`) into
that package, which is `kms/example` unless `KMS` says otherwise. Three of its
files are used:

- shacl.ttl
- knowledge.ttl
- model-instance.jsonld

A package may hold its knowledge or its shapes as a directory of files instead
(`knowledge/`, `shacl/`), as the packages generated from OPC UA models do
(`../opcua/README.md`, `owl2kms.py`). The build then merges the directory into
one file under `merged-kms/` first, so `make build KMS=../kms/opcua-pumps`
works like any other package. A `model-instance/` directory is not read yet.

The default package carries two model instances, and which one to use depends on whether
the model is being compiled or deployed.

`model-instance.jsonld` gives `urn:filter:1` four `hasStrength` values observed
a second apart, all with the same `datasetId`. That is deliberate and is what
you want when compiling: it is a stream of observations of one attribute, so it
exercises the dedup and the aggregations built on it -- resolving many
observations of one `(id, datasetId)` down to the current value. That is what
`attributes_view` does and what the SQLite oracle checks, and it resolves to
`0.6` at `13:52:35`.

`model-instance.scorpio.jsonld` is the same model with that attribute reduced
to exactly that one value, for loading into a live broker. Two clauses of
NGSI-LD ([ETSI GS CIM 009][cim009]) explain why it has to be a separate file:

- **4.5.5.1** -- "If no datasetId is provided, or `"datasetId": "@none"` is
  supplied, it is considered as the default Attribute instance. […] There can
  only be one default Attribute instance for an Attribute with a given
  Attribute name **in any request or response**." The same clause adds that
  there is no multi-attribute support for `observedAt`, so differing timestamps
  do not make the four into distinct instances. As an NGSI-LD *request*, then,
  the four-instance form is not conformant -- which costs nothing offline,
  where nothing is being sent to a broker, and matters only on deployment.
- **4.5.5.3** -- where a `datasetId` is duplicated, "the one with the most
  recent observedAt DateTime […] **shall be provided**". So a broker receiving
  the four is required to resolve them to `0.6`, exactly as the dedup does.

Scorpio does neither: it accepts the payload and returns all four, so the
entity reads back with four values where one was sent. It is not consistent
about it either -- appending those four over an existing `hasStrength` discards
the existing value, so instances sharing a `datasetId` do replace each other
between writes, just not within a single payload.

So: compile from `model-instance.jsonld`, deploy `model-instance.scorpio.jsonld`.

[cim009]: https://www.etsi.org/deliver/etsi_gs/CIM/001_099/009/01.09.01_60/gs_CIM009v010901p.pdf

To build:

```bash
make build
```

As a result, there must be a new directory `output` with the following files included:

- **core.yaml** - SQL-Tables for Flink (Core tables are used independent of concrete SHACL rules)
- **core.sqlite** - SQL-Tables for SQLite (Core tables are used independent of concrete SHACL rules)
- **shacl-validation.yaml** - From SHACL compiled SQL scripts for Flink
- **shacl-validation.sqlite** - From SHACL compiled SQL scripts for SQLite
- **shacl-validation-maps.yaml** - Additional SQL scripts when result is too large to store in  **shacl-validation.sqlite** directly
- **rdf.sqlite** - Knowledge translated to RDF triples for SQLite
- **rdf.yaml** - Knowledge translated to RDF triples for Flink
- **ngsild-kafka.yaml** - Kafka topics used by Flink
- **ngsild-models.sqlite** - translated model-instance.ttl for SQLite (only for SQLite needed)
- **ngsild.sqlite** - SQL tables for the concrete SHACL rules generated for SQLite
- **ngsild.yaml** - SQL tables for the concrete SHACL rules generated for Flink
- **rdf-kafka.yaml** - Kafka topic for rdf data
- **rdf-maps.yaml** - RDF data add-on when data is too much to fit into **rdf.yaml**
- **udf.yaml** - User Defined Functions (UDF) for Flink SQL


## Test locally with SQLite

```bash
make test-sqlite
```

# Deploy Flink Jobs

## Deploy SHACL rules to Flink

```bash
make flink-deploy
```

A deploy over a running validation starts a new job without state, and that job
replays the raises of the previous one from `constraint_trigger_table`: alerts
whose constraint is satisfied now stay open. Follow it with
`make shacl-resync REPLACE=fresh` (below).

## Resync the SHACL alerts

```bash
make shacl-resync                  # keep the running validation job
make shacl-resync REPLACE=fresh    # replace it with a fresh job
```

The leaf checks write only violations, so nothing closes an alert that was
raised and not retracted although its constraint is satisfied now: after a
redeploy, a restore, or alerts that drifted. `make shacl-resync` brings the
alerts of service `SHACL Validator` in Alerta in line with what the deployed
validation finds now, for every constraint type. It needs no KMS and works on
the deployed statementset `shacl-validation`; without one it stops at once and
says to deploy the validation first. It runs these steps in this order, each
only after the previous one completed, and reports the start and end of each:

1. mark the validation degraded: the platform watchdog's `ValidationConsistency`
   alert becomes a warning that a resync is in progress and the SHACL alerts are
   incomplete, naming the current step;
2. with `REPLACE=fresh` only: stop the validation job (the statementset is deleted
   and kept in `~/.local/state/shacl-resync` until the job runs again) and delete
   every record of `constraint_table`, `constraint_combination_table` and
   `constraint_trigger_table`, so the new job replays nothing. No topic, and no
   record of another topic, is deleted;
3. close every SHACL alert that is not closed, whatever its status, and no other
   alert; after a stop only once no SHACL alert arrived for a settle time;
4. reset Core Services by its restart nonce, so its alerts filter forwards raises
   with an unchanged severity and text again;
5. with `REPLACE=fresh` only: create the statementset again and wait for its job;
6. trigger a complete Debezium re-snapshot by deleting the Connect pods, and wait
   until every connector completed a snapshot that started after the resync began.
   The `kafka-connect-restart` CronJob keeps running;
7. wait until the re-snapshot is processed: the debezium-bridge, the validation
   job and Core Services have read every topic they consume to its end for a
   quiet period, and then a marker the command writes to `iff.alerts` (an alert
   of resource `shacl-validation`, event `ResyncMarker`, service `System`,
   severity `normal`, so it arrives closed) has reached Alerta through the
   alerta-bridge. The resync refuses to start when `iff.alerts` has more than one
   partition, since one marker covers one partition only;
8. end the degraded state and start one run of the platform watchdog, whose own
   judgement then sets `ValidationConsistency` again.

A resync without a replacement doesn't end an inconsistency the watchdog
reports, since the job keeps its state; `REPLACE=fresh` does. `REPLACE=checkpoint
RESTORE_FROM=<path>`, a restore of the job from a checkpoint or savepoint, is
refused before the first step until the statementset can be started from one
(#1042): the statementset has no field for it, the validation takes no retained
checkpoints, and the operator's savepoint path is passed in a form the submit job
doesn't read.

A failed or timed-out step stops the resync with the step's name and leaves
`ValidationConsistency` critical, naming the step, until a later resync
completes; if the job was stopped and not started again, the message says that
the validation doesn't run. Every step is safe to run again: run the command
again once the cause is removed. The time limits, the settle time
(`RESYNC_SETTLE`, 30 s) and the quiet period (`RESYNC_QUIET`, 30 s) are set by
environment variables, listed at the top of `shacl_resync.sh`. It needs curl 7.55
or later, which reads Alerta's key from a file of mode 0600 instead of the command
line. Ctrl-C or a TERM ends the running step at once and counts as a failure of it. The command needs
an operator's rights: it patches the watchdog's ConfigMap and the Core Services
FlinkSessionJob, with `REPLACE=fresh` deletes and creates the statementset,
deletes the Connect pods, runs the Kafka tools in the broker pod and starts a
Job from the watchdog's CronJob.

What an operator loses: every SHACL alert is closed, and an alert that is still
violated is opened again within a minute, its history showing the resync. Its
acknowledgement and the time it was first opened are lost, and an alert that was
shelved before comes back shelved. The restart of Core Services sends the
attributes still in `iff.ngsild.attributes` to Scorpio again, as every Core
Services restart does. With `REPLACE=fresh` the validation doesn't run between
the stop and the start.

## Undeploy SHACL rules to Flink

```bash
make flink-undeploy
```

# References

[RDF] RDF
[RDFS] RDFS
[TURTLE] TURTLE
[OWL] OWL
[SHACL] SHACL
[JSONLD] JSON-LD
[XSD] XSD
[SPARQL]
