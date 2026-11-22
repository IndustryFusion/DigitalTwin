# Design

## Context

`contracts/context-broker` (archived change `2026-11-22-gh-1037-context-broker-contract`) registers each deviation from NGSI-LD as one of three kinds:
- **accepted** (A): deviations of upstream 6.0.2;
- **transitional** (T): deviations of the fork on 5.0.5, which the move to 6.0.2 removes;
- **platform** (P): deviations of the platform's own components.

Since then:
- **Fork:**
  - IndustryFusion/ScorpioBroker#14 carried the fork's patches onto 6.0.2. It is merged into `scorpio-v6.0.2` at `ced9624f`, and its `PATCHES.md` names each patch's requirement and unit test.
  - IndustryFusion/ScorpioBroker#16 (for #15) removes A5, open. The platform pins the commit of `scorpio-v6.0.2` that merges it: `50569090`, as merges are fast-forward.
- **Platform:**
  - #1052 fixed P2, merged: Core Services delivers nothing for a null value.
  - #1051 is fixing P1, open: the updates bridge reads refusals inside a `207`.
  - #1056 (for #1049) is fixing P3, open: a non-overwriting upsert through batch create and batch update with `options=noOverwrite`.

This change lands after #1051 and #1056 are merged (task 0.1). The delta states P1 and P3 as fixed, and *A non-overwriting update uses the standard's operation* describes the bridge of #1056; both hold only once they are merged. Without #1056 the bridge relies on T3, and the updates bridge suite fails on 6.0.2.

Measured with the contract test on `ced9624f` (and `f9d3766a`, the same tree before a reword):
- every check of the standard passes;
- every transitional deviation T1–T9 fails as fixed, as `contracts/context-broker` requires of a move to the baseline;
- A1, A2 and A3 report as removed by the fork's patches.

Measured on `ced9624f` with the K8s debezium suite: its *sends subattributes* test is refused with `400` "Duplicated datasetId or multiple entries with no datasetId found". That is A5. Upstream 6.0.2 refuses a create, upsert or merge where an attribute instance has a `datasetId` and a sub-attribute written as an array of instances; also a sub-attribute instance with its own `datasetId` under a named instance, and several named instances each with a sub-attribute. The cause: the expansion adds a sub-attribute's `datasetId`s to the instance that holds it. NGSI-LD makes a sub-attribute an attribute of its own (4.5.2, 4.5.3) with one default instance per attribute (4.5.5). The fork on 5.0.5 accepted these. IndustryFusion/ScorpioBroker#16 checks each attribute's and sub-attribute's instances against their own `datasetId`s; two default instances of one attribute or sub-attribute are still refused.

Measured on the local platform, with the store of a running installation:
- **Migration:** Flyway repaired the checksum of the fork's edited `V20190604.1` and applied the six 6.0 migrations out of order, plus `V20261121.1`. The 313 entities are byte-identical before and after (the `id`, `e_types` and `entity` dump).
- **K8s suites:**
  - **MQTT:** a subscription without `receiverInfo` lost its notifications. That is A4, fixed in the fork (`64f92801`).
  - **Debezium:** the bridge's fixture sends two default instances of an attribute, which 6.0.2 refuses (4.5.5).
  - **Updates bridge:** the suite compares JSON as text, and 6.0.2 orders keys differently.

## Decisions

### D1 — The register keeps its kinds; the move empties the transitional one

- **Chosen:** *Deviations of the current image are transitional* stays, renamed *Deviations of an older build are transitional*, stated as the rule for any future build on an older release, with the note that none stands now. The requirements drop their transitional and platform deviation sentences. A2, A3 and the new A4 and A5 stay accepted deviations of the baseline, each with the fork patch that removes it. A patch removes a deviation only for the platform's build; on a pure 6.0.2 image it would stand, which the contract test still recognises.
- *Alternative:* remove the requirement. Rejected: the next upstream update can bring the case back, and the rule says what to do then.
- *Alternative:* drop A2–A5 from the contract. Rejected: they are deviations of the baseline, and the patches that remove them must be carried on every later update (*The broker fork implements this specification*).

### D2 — Build 6.0.2 in a container

- **Chosen:** 6.0.2 needs JDK 21 and Maven 3.9. `test/build-local-platform.sh` and `test/opcua-chain/scorpio-image.sh` compile it in `maven:3.9-eclipse-temurin-21`, mounting the local Maven repository, and build the image with `docker build` from `Dockerfile.jvm`. The runners then need no JDK, and the workflows drop `actions/setup-java`.
- *Alternative:* install JDK 21 and Maven 3.9 on the runners. Rejected: one more toolchain to keep in step across GitHub-hosted and self-hosted runners.

### D3 — Tests that relied on the old broker are corrected, not adapted to it

- **Chosen:**
  - The debezium fixture gives one of its two default `state` instances a `datasetId`. NGSI-LD allows only one default instance per attribute (4.5.5), and the test is about the bridge, not about that case.
  - The updates bridge suite compares JSON with sorted keys, because key order carries no meaning in JSON.
- *Alternative:* keep the fixtures and teach the tests both brokers' answers. Rejected: the tests would encode a fork deviation, against *What the platform adds follows NGSI-LD*.

### D4 — History recording off

- **Chosen:** the fork defaults `scorpio.history.autorecording` to off (`SCORPIO_HISTORY_AUTORECORDING`). The contract states it under *The broker runs with the platform's configuration*, since the platform doesn't use the temporal API. On 5.0.5 the history managers were simply not built; on 6.0.2 they are, and recording would grow the store without bound.
- *Alternative:* leave upstream's default on. Rejected: unbounded growth and write load for an API nobody reads.
- **Fork follow-up:** the fork's `PATCHES.md` names *What the platform doesn't rely on* for the history default. It should name *The broker runs with the platform's configuration*, which holds the SHALL; the temporal API stays under *What the platform doesn't rely on*.

### D5 — Workarounds of transitional deviations are removed

- **Chosen:** after the move no build the platform pins sends the fork's forms, which the contract test shows (T1–T9 fixed). So the updates bridge drops what reads them:
  - the `id` and `ProblemDetails` members of a refusal (T2), read beside `entityId` and `error` since #1051 and #1056;
  - a batch update with `noOverwrite` refused with `Not Overwriting` taken as success (T8, from #1056);
  - the comment that the fork answers `409` or `400` when no entity is created (T1). Reading `errors` from any status stays: it is the standard's form, and a `400` without errors is still logged.

  Their unit tests go with them. The contract test's T2, T3 and T8 name no bridge workaround any more.
- *Alternative:* keep them for an older broker. Rejected: the bridge and the broker are released together, so the bridge never meets the 5.0.5 fork again; and a dead branch hides a broker that answers in a non-standard form again.

### D6 — AlreadyExists in P3's path is not a refusal

- **Chosen:** in the non-overwriting upsert, a batch create of an existing entity answers `207` with AlreadyExists. The bridge then updates that entity with `noOverwrite`; it doesn't log the AlreadyExists as refused. Every other refusal of the batch create is logged as P1 requires.

## Risks

- **Out-of-order migrations:** a later upstream migration below `20261120` that redefines `merge_has_value(_list)` would run after the fork's on upgraded stores. The fork review recorded this as a follow-up; the contract test catches the result (A1).
- **The fork's own CI** gives no signal yet: its ETSI and API workflows fail on pristine 6.0.2. The platform's contract test is the gate, as the contract requires.
- **Rollback:** a store migrated to 6.0.2 can't go back to 5.0.5 without restoring a backup. The release notes of the platform must say so.

## Open Questions

None.
