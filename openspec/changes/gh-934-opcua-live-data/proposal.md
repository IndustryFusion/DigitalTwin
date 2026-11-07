# Proposal

Issue: #934

## Why

Live values from an OPC UA server pass through many components on their way to the context broker. Each component has its own tests, but nothing tests the chain, and the rules between the components aren't written down, so a change in one can break the chain unnoticed. On `main` today, the documented recipe also fails on a clean install.

## What Changes

- A tutorial takes a newcomer from nodesets to live values over REST, using the pump example, with its system requirements, troubleshooting and notes for other machines.
- The rules between the components become a specification, naming for each who produces it and who relies on it.
- A lightweight test verifies the chain on GitHub-hosted runners in minutes, without a Kubernetes cluster, against the real broker.
- Fix: `owl2instances.py` works with the documented runtime requirements of the model tools.
- Fix: the dataservice and the test servers accept relative paths such as `../opcua/bindings.ttl`.
- `AGENTS.md` and `CONTRIBUTING.md` point to the specification, so that a change to a listed component finds what relies on it.

## Capabilities

### New Capabilities
- `contracts/opcua-live-data`: The rules between the components on the path from an OPC UA server to the context broker, how they are verified, and what the verification doesn't cover.
- `dataservice/opcua-getting-started`: What a newcomer needs to get a machine's live data into the context broker: the tutorial, its system requirements, and a clean install of the tools.

### Modified Capabilities

None.

## Impact

- **Contract between components:** yes. This writes down existing rules. It changes none of them, and no component's behaviour changes except for the two fixes.
- **Affected components:**
  - `semantic-model/opcua`: the requirements files
  - `semantic-model/dataservice`: path handling, the tutorial
  - `KafkaBridge`: a unit test for the access control only
  - Read by the test, not changed: `NgsildAgent`, `KafkaBridge`, the published Scorpio image
- **CI:** a new workflow, limited to the paths the chain depends on. `K8s tests` and `Build` are unchanged.
- **Dependencies:** `pyshacl` moves to the runtime requirements of the model tools. `asyncua` stays optional for the components and is only installed by the test and the tutorial, because of its license.
- **Other changes:** none. The test takes the Scorpio image from `DOCKER_TAG` in `.env`, which names a published release.

## Out of Scope

- Extracting nodesets from a server.
- Specifying the internals of `nodeset2owl`, which #930 covers.
- New connector features: array values, OPC UA subscriptions instead of polling, custom structure decoding.
- Subscriptions of the context broker.
- Changing the agent or the MQTT bridge, including `PropertyIri` being accepted by one and dropped by the other. The specification records this as a known gap.
- Other operating systems than Linux.
- Specifying other components or chains.
- Adding to the runtime of `K8s tests`.
- Running Core Services' Flink SQL, real MQTT authentication or Keycloak in the new test, see `design.md`.
