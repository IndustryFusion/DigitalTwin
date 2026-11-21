# Tasks

## 1. Contract test on the light stack

- [ ] 1.1 Make the broker startup of `test/opcua-chain/stage4a.sh` reusable with a name prefix and a port, without changing the chain test's behaviour; verify the `chain` job still passes
- [x] 1.2 Add a contract test (e.g. `test/context-broker/`) that starts the broker with the image from `.env`, signs tokens with client roles and realm roles, and runs one check per scenario of `contracts/context-broker` that needs no Debezium and no MQTT, each named after its requirement and scenario; verify it passes on `v0.10`
  - `test/context-broker/run.sh` and `contract.js` (Node, no dependencies): one check per scenario that needs no Debezium and no MQTT, plus the measurement of 1.6.
  - By default it runs the broker the platform pins (D7, 3.3). On that build, `e1cea4bc`: 27 ok, 9 deviations standing (A2, A3, T1 to T7), A1 reported as removed by the fork's patch, 0 failed.
  - On the published `v0.10` (`135b5ee`, the image the local cluster runs): 26 ok, all 10 deviations standing, 0 failed.
- [x] 1.3 Implement each deviation scenario as an assertion of today's answer, failing with a message that names the deviation, its issue and its workaround; verify by changing one expected answer that the message is printed
  - A deviation check passes while the broker gives today's answer, and fails with "the deviation is fixed (…): remove the workaround, …" once the broker meets the requirement.
  - Verified on 6.0.2, where the sub-attribute deviation is fixed: the check fails with that message, naming #969 and the liveness probe.
- [x] 1.4 Run the sub-attribute scenario last, on its own broker instance, and include a liveness check after about 60 s; verify that on `v0.10` the check reports the deviation and the other checks are unaffected
  - `run.sh` starts a second broker for it. On `v0.10`, the second merge isn't notified and liveness is `DOWN` within 90 s, which is reported as the deviation. The checks before it are unaffected.
- [x] 1.5 Run the contract test against the 6.0.2 image with upstream's variables, and authorisation checks skipped because upstream has none; verify the result per scenario matches the table in design.md, and record any difference in this change before it is archived
  - `IMAGE=scorpiobroker/all-in-one-runner:java-kafka-latest MODE=upstream` (6.0.2): 21 ok, A1 to A3 standing, 6 skipped (authorisation and T7), 6 failed, exactly T1 to T6, each as fixed. This is the expected result of the move to the baseline (D9), and it matches the table in design.md.
- [x] 1.6 Measure open question 1: a batch merge of two entities, one of them with a `null` value; verify the result is recorded in design.md and, if the whole batch is refused, named as a platform gap in the Pull Request
  - Only the entity with `null` is refused (`207`) and the other one is merged, on `v0.10` and on 6.0.2. Recorded in design.md (open question 1). The whole batch isn't refused, so there is no further platform gap.

## 2. K8s tests

- [x] 2.1 Add to `test/bats/test-scorpio/test-scorpio-mqtt-subscriptions.bats` a batch merge of two entities of the subscribed type; verify both entities arrive over MQTT
  - Local cluster (`v0.10`): both entities arrive over MQTT with the new value. The test waits for evidence instead of fixed sleeps: first both creations notified (the subscription is active), then both merged values.
  - The suite's older tests flake locally with their fixed sleeps, 2 to 3 per run; the unchanged suite from `origin/main` did the same (2 of 9).
- [x] 2.2 Add to `test/bats/test-bridges/test-debezium-bridge.bats` an entity with a JsonProperty and a ListProperty; verify the bridge publishes both with their values
  - Local cluster: passes; the bridge publishes the JsonProperty (`@json`), the ListProperty (`@list`) and the declared double (`valueType` `xsd:double`).
  - Two older tests of the suite fail locally only on line order: their expected files are sorted in `en_US.UTF-8`, which this machine lacks.
- [ ] 2.3 Verify the K8s shards that run these files pass in the Pull Request

## 3. Workflow

- [ ] 3.1 Run the contract test in a GitHub-hosted job when `.env`, `test/build-local-platform.sh`, `helm/charts/scorpio/**`, `KafkaBridge/lib/ngsild*.js` or the test itself changes, and in the nightly; verify by the job running on this Pull Request and not on a Pull Request that changes none of these
- [ ] 3.2 Verify the job finishes in under 5 minutes when the pinned build is cached, and record how long a run takes that builds it
- [ ] 3.3 Build the broker from the commit `test/build-local-platform.sh` pins, with the profiles of that script, once per commit, and keep the image in the Actions cache keyed by the commit (D7); verify that a second run on the same commit restores the image instead of building it
- [ ] 3.4 Make the OPC UA chain test use the same pinned build instead of the published release image; verify the `chain` job passes with it

## 4. References

- [x] 4.1 Add a line to `AGENTS.md` under *Contracts between components*: a change to the broker, its image or its chart reads `contracts/context-broker`; verify `openspec validate --all --strict` passes
  - `openspec validate --all --strict`: 18 passed.
- [x] 4.2 Link `contracts/context-broker` from the fork update (IndustryFusion/ScorpioBroker#9) with the patch table of design.md, asking for a patch list that names each patch's requirement and its unit test (D8), and file the subscription read by id as a fork defect; verify both links are in this Pull Request
  - Comment on IndustryFusion/ScorpioBroker#9: https://github.com/IndustryFusion/ScorpioBroker/issues/9#issuecomment-7069870110 (patch list per requirement, unit tests, the contract test before the move).
  - The subscription read by id: IndustryFusion/ScorpioBroker#13.
- [x] 4.3 Make the contract test runnable against any image given by name, so the fork can run it on its own build before a release; verify by running it with the 6.0.2 image name (task 1.5)
  - `IMAGE=<image>` and `MODE=upstream`, also as inputs of the workflow's manual run. Verified with the 6.0.2 image (1.5).

## 5. Verification

- [ ] 5.1 Report the result of every scenario of the three delta specs in the Pull Request: the test that covers it and its result on `v0.10`, and on 6.0.2 for the contract test
- [ ] 5.2 State in the Pull Request that the change adds test code only, so no product code coverage applies

## 6. Convergence

- [x] 6.1 Let the contract test print each deviation's kind and id (accepted A…, transitional T…, platform P…, design D9) and check every scenario against the standard's answer: batch results as `207` with `entityId` and `error`, upsert `options=update` overwriting, two default instances refused, an id that isn't a URI refused with `400`; verify on `v0.10` that every transitional deviation is reported as standing, and on 6.0.2 that each fails as fixed while the accepted ones stand
  - Every deviation line names its id, kind, clause, and the workaround or what removes it. A deviation that a patch the platform carries removes (A1) passes as removed.
  - `v0.10` and the pinned build: every transitional deviation stands (1.2). 6.0.2: T1 to T6 fail as fixed, A1 to A3 stand, T7 is skipped with authorisation (1.5).
- [x] 6.2 File an issue for each platform deviation P1 to P4 with its requirement, P1 and P3 marked as needed before the move to 6.0.x; verify the issues are linked in this Pull Request
  - P1 #1047, P2 #1048, P3 #1049 (P1 and P3 marked as needed before the move to 6.0.x), P4 #1050.
- [x] 6.3 Report the accepted deviations A1 to A3 on IndustryFusion/ScorpioBroker, with their reproduction from the contract test, for a patch or an upstream report; verify the issues are linked in this Pull Request
  - A2 IndustryFusion/ScorpioBroker#11, A3 IndustryFusion/ScorpioBroker#12, each with its reproduction; A1 already has IndustryFusion/ScorpioBroker#8 (fixed by the fork patch since #1040).
- [ ] 6.4 Mark the expectation of `test-ngsild-updates-bridge.bats` *upserting and non-overwriting* as asserting T3, with a comment naming P3; verify the K8s shard still passes on `v0.10`
