# Tasks

## 1. Contract test on the light stack

- [ ] 1.1 Make the broker startup of `test/opcua-chain/stage4a.sh` reusable with a name prefix and a port, without changing the chain test's behaviour; verify the `chain` job still passes
- [ ] 1.2 Add a contract test (e.g. `test/context-broker/`) that starts the broker with the image from `.env`, signs tokens with client roles and realm roles, and runs one check per scenario of `contracts/context-broker` that needs no Debezium and no MQTT, each named after its requirement and scenario; verify it passes on `v0.10`
- [ ] 1.3 Implement each deviation scenario as an assertion of today's answer, failing with a message that names the deviation, its issue and its workaround; verify by changing one expected answer that the message is printed
- [ ] 1.4 Run the sub-attribute scenario last, on its own broker instance, and include a liveness check after about 60 s; verify that on `v0.10` the check reports the deviation and the other checks are unaffected
- [ ] 1.5 Run the contract test against the 6.0.2 image with upstream's variables, and authorisation checks skipped because upstream has none; verify the result per scenario matches the table in design.md, and record any difference in this change before it is archived
- [ ] 1.6 Measure open question 1: a batch merge of two entities, one of them with a `null` value; verify the result is recorded in design.md and, if the whole batch is refused, named as a platform gap in the Pull Request

## 2. K8s tests

- [ ] 2.1 Add to `test/bats/test-scorpio/test-scorpio-mqtt-subscriptions.bats` a batch merge of two entities of the subscribed type; verify both entities arrive over MQTT
- [ ] 2.2 Add to `test/bats/test-bridges/test-debezium-bridge.bats` an entity with a JsonProperty and a ListProperty; verify the bridge publishes both with their values
- [ ] 2.3 Verify the K8s shards that run these files pass in the Pull Request

## 3. Workflow

- [ ] 3.1 Run the contract test in a GitHub-hosted job when `.env`, `test/build-local-platform.sh`, `helm/charts/scorpio/**`, `KafkaBridge/lib/ngsild*.js` or the test itself changes, and in the nightly; verify by the job running on this Pull Request and not on a Pull Request that changes none of these
- [ ] 3.2 Verify the job finishes in under 5 minutes

## 4. References

- [ ] 4.1 Add a line to `AGENTS.md` under *Contracts between components*: a change to the broker, its image or its chart reads `contracts/context-broker`; verify `openspec validate --all --strict` passes
- [ ] 4.2 Link `contracts/context-broker` from the fork update (IndustryFusion/ScorpioBroker#9) with the patch table of design.md, and file the subscription read by id as a fork defect; verify both links are in this Pull Request

## 5. Verification

- [ ] 5.1 Report the result of every scenario of the three delta specs in the Pull Request: the test that covers it and its result on `v0.10`, and on 6.0.2 for the contract test
- [ ] 5.2 State in the Pull Request that the change adds test code only, so no product code coverage applies
