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
- **ngsild-shared-kafka.yaml** - Kafka topic `iff.ngsild.entities`, shared with the bridges and kept when the validation is undeployed
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

## Undeploy SHACL rules to Flink

```bash
make flink-undeploy
```

Undeploying leaves the topic `iff.ngsild.entities`: the bridges write and read it, so its KafkaTopic is kept by helm (`helm.sh/resource-policy: keep`) and `make flink-deploy` takes it over again.

## Redeploy SHACL rules to Flink

```bash
make flink-redeploy            # KMS, SHACL, KNOWLEDGE and MODEL as for flink-deploy
```

The leaf checks write only violations, so after `make flink-undeploy` and `make flink-deploy` alerts of the previous job can stay open although the new job finds their constraint satisfied. `make flink-redeploy` (`flink_redeploy.sh`) runs four steps, in this order, each only after the previous one completed:

1. **Undeploy the validation** (`make flink-undeploy`) and wait until the statementset is gone and the topics of `constraint_table`, `constraint_combination_table` and `constraint_trigger_table` no longer exist in Kafka, so the new job replays no raise of the previous one.
2. **Close the SHACL alerts**: once Alerta has received no alert of service `SHACL Validator` for a settle time, close every alert of that service that is not closed, whatever its status. No alert of another service is changed.
3. **Restart Core Services** without state (a new `spec.restartNonce` of the FlinkSessionJob `core-services-job`) and wait until one new `Core Services` job runs with all its tasks, so its alerts filter forwards the new job's raises again.
4. **Deploy the validation** (`make flink-deploy`), check that the helm release was deployed, and wait until the job runs with all its tasks and each Debezium connector has completed a snapshot that started after the job.

Afterwards the open SHACL alerts are those of the constraints violated now. What an operator loses:

- Acknowledgements and the open time of alerts that are still violated: they are closed and opened again, their history shows the close by the redeploy. An alert shelved before it was closed comes back shelved.
- The validation while the redeploy runs: from step 1 until step 4 has completed, nothing is validated. A failed step stops the redeploy with `redeploy failed in step <n>/4 <name>: <reason>`; the platform then runs without validation until the redeploy is run again, with the command the message gives, after removing the cause. Every step can be repeated.
- Restarting Core Services also restarts its SQL part, which reads `iff.ngsild.attributes` from the earliest offset: the attribute window retained in that topic is sent to Scorpio again, as at every Core Services restart (the values and their `observedAt` are unchanged).

A validation deployed before the KafkaTopic of `iff.ngsild.entities` was kept would still delete it when undeployed; the redeploy then stops before step 1 and asks to run `make flink-deploy` once first.

The time limits are environment variables (`REDEPLOY_UNDEPLOY_TIMEOUT`, `REDEPLOY_SETTLE` (30 s), `REDEPLOY_SETTLE_TIMEOUT`, `REDEPLOY_ALERTA_TIMEOUT`, `REDEPLOY_CLOSE_TIMEOUT`, `REDEPLOY_RESTART_TIMEOUT`, `REDEPLOY_DEPLOY_TIMEOUT`, in seconds); exceeding one fails its step. The platform watchdog names this command as the repair of an inconsistent validation state.

# References

[RDF] RDF
[RDFS] RDFS
[TURTLE] TURTLE
[OWL] OWL
[SHACL] SHACL
[JSONLD] JSON-LD
[XSD] XSD
[SPARQL]
