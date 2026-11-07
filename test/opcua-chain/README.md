# OPC UA Chain Test

Verifies the path from an OPC UA server to the context broker against the rules in
[contracts/opcua-live-data](../../openspec/changes/gh-934-opcua-live-data/specs/contracts/opcua-live-data/spec.md),
on GitHub-hosted runners and without a Kubernetes cluster. The workflow is
[opcua-chain.yaml](../../.github/workflows/opcua-chain.yaml). It runs on Pull Requests which change the
components of the chain or their dependencies, with Python 3.10 and 3.12 and Node.js 22.

Each stage uses the real components and feeds the next one through files in `$OUT`:

| Stage | Real | Replaced |
|---|---|---|
| 1. Model | Steps 1 to 3 of the [tutorial](../../semantic-model/dataservice/opcua-pump-tutorial.md), as written there: `nodeset2owl`, `owl2instances`, the pump nodesets | – |
| 2. Connector | The tutorial's test server and dataservice, a plain OPC UA client writing values, an outage and the recovery | The device agent, by a TCP listener which records the messages |
| 3. Bridge mapping | The agent's schema, the MQTT bridge's mapper and ingestion, fed with the messages of stage 2 | MQTT |
| 4. Broker | The updates bridge code, Scorpio of the current release from `.env`, Postgres, Kafka | Keycloak, by a self-signed token; Core Services, see below |

Stages 1 and 2 extract the command blocks of the tutorial marked with `<!-- chain-test: NAME -->`, so a
change which breaks one of those commands fails the test.

## What it doesn't cover

- **Core Services.** Its Flink SQL turns the bridge's attributes into update records.
  [core_services_format.js](core_services_format.js) writes those records by hand instead, so a change to
  Core Services, for instance to how it turns lowercase `true` into a boolean, isn't seen here.
- **MQTT authentication and Keycloak.** The rule that device IDs contain no `/` is covered by a unit test
  of the access control in `KafkaBridge/test`.
- **The tutorial's platform steps**, loading the entities, onboarding the device and reading over REST,
  which need a deployed platform. `K8s tests` remains the test of the full platform.

## Running it locally

From the repository root, with Python, Node.js, Docker, `curl`, `jq` and `openssl`, and ports 4840, 7070
and 19090 free:

```bash
bash test/opcua-chain/run.sh
```

It writes the tutorial's generated files and virtual environments into the checkout, as the tutorial does,
its logs into `.opcua-chain/`, and removes its containers at the end.
