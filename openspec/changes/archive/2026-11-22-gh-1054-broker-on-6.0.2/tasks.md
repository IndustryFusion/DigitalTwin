# Tasks

## 0. Preconditions

- [x] 0.1 #1051 and #1056 are merged before the implementation lands; verify on `main` that the updates bridge reads refusals inside a `207` (P1) and upserts without overwriting through a batch create and a batch update with `options=noOverwrite` (P3)
- [x] 0.2 IndustryFusion/ScorpioBroker#16 is merged into `scorpio-v6.0.2`; verify the commit that merges it (`50569090` when fast-forwarded) is on the branch

## 1. The broker build

- [x] 1.1 Pin `SCORPIO_COMMIT` in `test/build-local-platform.sh` to the commit of IndustryFusion/ScorpioBroker `scorpio-v6.0.2` that merges IndustryFusion/ScorpioBroker#16 (`50569090`), and build it in `maven:3.9-eclipse-temurin-21` followed by `docker build` (D2); verify the image `ibn40/scorpio-all-in-one-runner:$DOCKER_TAG` is built and pushed to the local registry
- [x] 1.2 Use the same recipe and pin in `test/opcua-chain/scorpio-image.sh`; verify it builds the pinned commit tagged with its first 8 characters
- [x] 1.3 Drop `actions/setup-java` from `context-broker.yaml`, `opcua-chain.yaml` and `k8s-e2e.yaml`, and the Maven installation from `test/prepare-platform-for-github-runner.sh`; verify the Build, chain, contract and K8s e2e workflows build the broker

## 2. Contract test

- [x] 2.1 Check T1–T9 as plain requirements of the standard, including an empty `success` when every entity of a batch is refused (scenario *The only entity refused*), and A2 and A3 as removed by the fork's patches; verify the contract test passes with 0 failed on the pinned build, and fails exactly on those checks on `e1cea4bc`
- [x] 2.2 Add a check for A5 with its `patch` field, like A2 and A3: an upsert of an entity whose attribute instance has a `datasetId` and a sub-attribute written as an array of instances (scenario *Sub-attribute array on an instance with a datasetId*); verify it reports A5 as removed by the fork's patch on the pinned build, and as the deviation on `ced9624f`
- [x] 2.3 Add a check that the broker records no entity history by default (scenario *No history by default*); verify it passes on the pinned build
- [x] 2.4 Add an MQTT broker to the stack of `test/context-broker/run.sh` and a check that a subscription to its `mqtt://` endpoint without `receiverInfo`, created as the first subscription of the freshly started broker, delivers its notification (scenario *MQTT endpoint without receiverInfo*); verify it passes on the pinned build and reports A4 on an upstream 6.0.2 image (`MODE=upstream`)
- [x] 2.5 Make stage 4b's type-change probe accept the standard's `207` with `entityId` and `error`; verify the `chain` job passes
- [x] 2.6 Make the texts of T2, T3 and T8 in `test/context-broker/contract.js` name no bridge workaround (D5); verify the contract test still passes

## 3. Updates bridge

- [x] 3.1 Remove from `KafkaBridge/lib/ngsildUpdates.js` the reading of `id` and `ProblemDetails` (T2), the handling of `Not Overwriting` as success (T8) and the comment on the fork's `409` or `400` (T1), with their unit tests (D5); verify the unit tests pass with coverage above 80 % of the changed code, and the contract test shows T1, T2 and T8 fixed on the pinned build
- [x] 3.2 Keep AlreadyExists of the batch create out of the refusals the bridge logs (D6); verify the unit test of a non-overwriting upsert of an existing entity logs nothing

## 4. K8s tests

- [x] 4.1 Give one of the two default `state` instances of the debezium fixture a `datasetId` (D3); verify the debezium suite passes on the pinned build, *sends subattributes* included (A5)
- [x] 4.2 Compare JSON with sorted keys in the updates bridge suite (D3); verify it passes on the pinned build
- [x] 4.3 Verify the MQTT suite passes on the pinned build
- [x] 4.4 Verify the K8s shards of the Pull Request pass

## 5. Existing store

- [x] 5.1 Migrate the store of a running installation from `e1cea4bc` to the pinned build; verify Flyway applies the migrations without error and the stored entities are identical before and after

## 6. Verification

- [x] 6.1 Report each scenario of the delta with the test that covers it and its result on the pinned build
- [x] 6.2 State the changed-code coverage and the licences (no dependency change in DigitalTwin)
- [x] 6.3 Fork follow-up: ask for the history row of the fork's `PATCHES.md` to name *The broker runs with the platform's configuration* (D4)
