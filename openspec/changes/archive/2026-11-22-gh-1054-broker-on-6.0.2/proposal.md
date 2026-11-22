# Proposal

Issue: #1054

## Why

`contracts/context-broker` takes upstream Scorpio 6.0.2 as the baseline. The platform still builds its broker from the fork on upstream 5.0.5 (`e1cea4bc`), and the contract lists that build's deviations from the baseline as transitional: T1–T9.

The fork's patches are now carried onto 6.0.2. IndustryFusion/ScorpioBroker#14 is merged into `scorpio-v6.0.2`, commit `ced9624f`. That branch also fixes:
- A2 and A3, two accepted deviations of the baseline;
- T7, a defect in the fork's own access control;
- two deviations of 6.0.2 that the move to it would otherwise bring in:
  - A4: a notification to an MQTT endpoint without `receiverInfo` is lost;
  - A5: an attribute instance with a `datasetId` whose sub-attribute is an array of instances is refused with `400` (IndustryFusion/ScorpioBroker#15, fixed by IndustryFusion/ScorpioBroker#16, still open).

The platform deviations that depend on the old broker:
- P2 (#1048) is fixed by #1052, merged.
- P1 (#1047) and P3 (#1049) are being fixed by #1051 and #1056, both still open.

The change lands after #1051 and #1056 are merged. Until then the bridge on `main` relies on T3, and the updates bridge suite would fail on 6.0.2. The delta already states P1 and P3 as fixed, which holds once they are merged.

## What Changes

- **Order:** the implementation lands after #1051 and #1056 are merged.
- **The broker the platform builds** is IndustryFusion/ScorpioBroker `scorpio-v6.0.2` at the commit that merges IndustryFusion/ScorpioBroker#16 (`50569090`, as merges are fast-forward), built with JDK 21 and Maven 3.9 in a container, because 6.0.2 needs both. The same recipe is used by `test/build-local-platform.sh`, `test/opcua-chain/scorpio-image.sh` and the CI workflows.
- **`contracts/context-broker`:**
  - no transitional deviation stands any more;
  - the platform deviations P1–P3 are fixed;
  - A2, A3 and the new A4 and A5 are accepted deviations of the baseline, which the fork's patches remove;
  - a fully refused batch keeps an empty `success`;
  - the platform reports as refused an entity of a `207` that is listed neither under `success` nor under `errors`, also when the `207` has no list of errors;
  - *Deviations of the current image are transitional* is renamed *Deviations of an older build are transitional*;
  - the broker records no entity history unless configured to.
- **The contract test** checks T1–T9 as plain requirements of the standard, and A2, A3 and A5 as removed by their patches. It adds checks for an empty `success`, for history recording, and for MQTT notifications without `receiverInfo` on a freshly started broker.
- **Workarounds of transitional deviations are removed:** the updates bridge's reading of `id` and `ProblemDetails` (T2, from #1051 and #1056) and its handling of `Not Overwriting` (T8, from #1056); the contract test's texts of T2, T3 and T8 name no bridge workaround.
- **K8s tests that relied on the old broker's answers:**
  - the debezium fixture sends one default instance per attribute, as NGSI-LD requires; its *sends subattributes* test passes with A5's patch;
  - the updates bridge suite compares JSON regardless of key order.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `contracts/context-broker`: the deviation register after the move to the baseline. Transitional deviations no longer stand, P1–P3 are fixed, and A2–A5 are removed by fork patches. An empty `success`, the reading of a `207` without errors, and no history recording by default are added.

## Impact

- **Contract between components:** yes, `contracts/context-broker` changes. Its consumers: the updates and debezium bridges, Core Services, the OPC UA chain test, the K8s tests, XanaAI as a subscriber.
- **The platform's broker image:** `test/build-local-platform.sh`, `test/opcua-chain/scorpio-image.sh`, `test/prepare-platform-for-github-runner.sh`, and the workflows `context-broker.yaml`, `opcua-chain.yaml`, `k8s-e2e.yaml`.
- **Existing stores:** Flyway migrates a store written by `e1cea4bc` (or `v0.10`) to 6.0.2 out of order, adding six 6.0 migrations and `V20261121.1`. Measured on a copy and on the local platform: every entity and the stored row are unchanged.
- **Updates bridge:** `KafkaBridge/lib/ngsildUpdates.js` and its unit tests lose the T2 and T8 workarounds.
- **Tests:** `test/context-broker/contract.js`, `test/context-broker/run.sh` (an MQTT broker for the notification check), `test/opcua-chain/stage4b.js`, `test/bats/test-bridges/test-debezium-bridge.bats`, `test/bats/test-bridges/test-ngsild-updates-bridge.bats`.
- No change to the chart: the fork keeps the platform's variables.

## Out of Scope

- P4 (#1050): IRI values as VocabProperty, a change of the OPC UA path of its own.
- The follow-ups of the fork review (migration-order guard, `trust-all`, endpoint discovery in tests, the unused authorisation extension) and the fork's broken ETSI workflows.
- Publishing a release image; the next release ships the pinned build.
