# Design

## Context

See proposal.md - Why. `K8s tests` takes about 50 minutes and needs a self-hosted runner, which is why this chain has no test of its own. A throwaway version of the test below ran on `ubuntu-24.04` runners, on [branch `spike/light-chain-test`](https://github.com/DrGarbitsch/DigitalTwin/tree/spike/light-chain-test) of a fork. The measurements are in #934. The implementation reuses it, without its bug-injection workflow.

Two findings shape the fixes. `rdflib==6.2.0`, pinned by the dataservice, reads an existing `../opcua/bindings.ttl` correctly, but names a missing one with a directory level dropped, because it then joins the path to the working directory as a URL. That misled the first validation of the tutorial, whose model hadn't been built. And `owl2instances.py` imports `pyshacl` through `lib/shacl.py`, while only `requirements-dev.txt` lists it.

## Goals / Non-Goals

**Goals:**
- Verify the rules in `contracts/opcua-live-data` on every relevant Pull Request, in under 10 minutes.
- Fail when a real past bug comes back, and stay reliable when none did.

**Non-Goals:**
- Replacing `K8s tests`, which remains the only test of the full platform.
- Changing a rule. The specification records today's behaviour, including its known gap.

## Decisions

**Staged test, real where practical.** Four stages, each feeding the next through files:

| Stage | Real | Replaced |
|---|---|---|
| 1. Model | `nodeset2owl`, `owl2instances`, pump nodesets | – |
| 2. Connector | OPC UA test server, dataservice, a plain client writing values | Agent, by a TCP listener recording the messages |
| 3. Bridge mapping | The bridge's mapper, the agent's schema, fed with the messages from stage 2 | MQTT |
| 4. Broker | Updates bridge code, Scorpio, Postgres, Kafka | Keycloak, Core Services |

Alternatives: a stripped platform in Docker Compose, rejected because MQTT authentication needs Keycloak, and Core Services needs Flink, which brings most of the platform's weight back; and adding to `K8s tests`, rejected in the issue.

**The real broker, not a fake.** Scorpio's refusals (`SB001`, `22023`) and its merging of a number into an IRI value are the behaviour the chain has to survive, and a fake would only repeat what we already believe. The real stack needs 10 to 12 seconds and about 600 MB. A fake is only used for the agent's TCP socket, which just records what it gets. Alternative: a fake NGSI-LD server, rejected because it would have passed all three of those bugs.

**Core Services stays out, and the gap is stated.** Stage 4 takes update records in Core Services' output format, written by hand. So the test can't see a change in Core Services' Flink SQL, the step which turns lowercase `true` into a boolean. This change adds no nightly run and no Flink container. A full run on the platform would need a nightly-only switch in `K8s tests`, which is shared with Pull Requests, and a single-container Flink is untried. Both are possible follow-ups with their own issue, if this class of bug comes back. Alternatives: each of those two, deferred; the issue asked the proposal to decide.

**Real MQTT authentication stays out.** The rule about `/` in device IDs gets a unit test on the access control, using the existing test suite in `KafkaBridge/test`. Alternative: running EMQX and Keycloak in the test, rejected for its weight.

**Python 3.10 and 3.12.** CI's `Build` uses 3.10, and the tutorial was validated on 3.12. Node.js 22 is what the agent's image uses, so the tutorial lists 22 as the version CI covers, next to the 24 it was validated with by hand. Alternative: 3.12 only, rejected because it wouldn't cover what `Build` uses. This is cheap, as both runs take about 5 minutes and share nothing.

**Scorpio image from `.env`.** The test uses `ibn40/scorpio-all-in-one-runner:${DOCKER_TAG}`, so it follows the release without its own version number. Between releases, the test uses the last published image, while `K8s tests` builds Scorpio from a pinned commit. Alternative: building Scorpio in the test, rejected because that build is much of the weight we want to avoid.

**Paths.** The workflow runs on changes to `semantic-model/opcua/**`, `semantic-model/dataservice/**`, `KafkaBridge/**`, `NgsildAgent/**`, `.env` and itself, so dependency updates there trigger it. Alternative: running on every Pull Request, rejected as unnecessary.

**Relative paths are resolved by our code.** The dataservice and the test servers make paths absolute before parsing. Alternative: raising the `rdflib` pin in the dataservice, rejected because that would be a dependency update with its own risk, for a problem we can fix in a few lines, and it leaves the behaviour dependent on a library. Raising the pin stays possible as a separate change.

**`pyshacl` moves to `requirements.txt` of the model tools.** It's a runtime dependency. Alternative: a lazy import in `lib/shacl.py`, rejected because it only hides the dependency.

**Tutorial commands drive the test.** The tutorial goes to `semantic-model/dataservice/opcua-pump-tutorial.md`. Marked command blocks of Steps 1, 2 and 3 are extracted and run by stage 1, and the blocks of the test server and the dataservice by stage 2. The platform steps need a deployed platform, so the test can't run them; they are validated by hand, and the tutorial says when. Alternative: a test with its own commands, rejected because the two would drift apart. The first validation of this tutorial is how the two clean-install bugs were found.

**Waits follow the connector's cycle.** The connector reads each node on its own 5-second cycle. After writing, the test waits for more than a full cycle before it stops or checks, because the first version without this was flaky. A logged bridge error fails the test, because the bridges log and carry on.

## Risks / Trade-offs

- [The update records in stage 4 drift from Core Services' real output] → They are in one place, marked as a copy of that format, and the specification states the gap. `K8s tests` still covers the real path.
- [The published Scorpio image differs from the commit `K8s tests` builds] → It's the image users deploy. A release updates it through `.env`.
- [Downloads from `industryfusion.github.io` or `raw.githubusercontent.com` fail] → The workflow retries. `Build` has the same dependency and retries as well.
- [A green test is taken to mean the full chain works] → The specification, the workflow's name and the guide say what it covers.
- [The test goes stale when a bug stops being reproducible] → The bug list is in the specification. Task 3.5 shows each one being caught, and the change that alters it has to update that list.

## Open Questions

- Whether to add the nightly run or single-container Flink later. Neither changes this design.
