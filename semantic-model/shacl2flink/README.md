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

There are three files expected in the `../kms` directory:

- shacl.ttl
- knowledge.ttl
- model-instance.ttl

`../kms` carries two model instances, and which one to use depends on whether
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
