# Tasks

## 1. Shared topic

- [ ] 1.1 Write the KafkaTopic of `iff.ngsild.entities` with `helm.sh/resource-policy: keep` and take it out of the KafkaTopics `flink-deploy` deletes before deploying (D4); verify with a unit test of the generator that only that KafkaTopic carries the annotation, and on a platform that `make flink-undeploy` leaves the KafkaTopic and its topic ID ("Undeploy alone")
- [ ] 1.2 Check that a following `make flink-deploy` takes the kept resource over without error; verify on a platform that the release lists it again and its topic ID is unchanged

## 2. Redeploy command

- [x] 2.1 Add `make flink-redeploy` and its script with the four steps, the step reports, the failure message and the time limits (D2); verify with a bats-unit test, with kubectl, helmfile, make and curl stubbed, that the steps run in order and each starts after the previous ended ("The order", "Nothing deployed before")
- [x] 2.2 Stop on a failed or timed-out step (D2); verify with bats-unit tests that a failure in each of the four steps exits non-zero, names that step and runs no later step ("Alerta unreachable", "Topics not deleted in time"), and that a second run after the cause is removed completes ("Run again")
- [x] 2.3 Check the annotation of D4 before step 1 (Migration Plan); verify with a bats-unit test that a missing annotation stops the redeploy before anything is undeployed ("Deployed before this rule")
- [ ] 2.4 Step 1, undeploy and wait for the topics in Kafka (D3); verify with a bats-unit test that the step waits while a KafkaTopic or a broker topic is left, and on a platform that after the step no KafkaTopic and no broker topic of the three tables exists ("Topics deleted")
- [x] 2.5 Step 2, settle time and close by filter (D5); verify with bats-unit tests that the step waits while SHACL alerts arrive, repeats the bulk call until 404, treats 404 as nothing left and fails when the final count isn't 0 ("Many alerts", "A raise in flight"), and that the filter is `service=SHACL Validator&status!=closed`
- [ ] 2.6 Step 3, restart Core Services by `spec.restartNonce` and wait for one running job (D6); verify on a platform that afterwards Flink runs one `Core Services` job with a new job ID, all tasks running and no restored checkpoint ("A new job")
- [ ] 2.7 Step 4, deploy, check the apply's own status and wait for the snapshot of both connectors after the job's start (D7); verify with a bats-unit test that a failing apply fails the step, and on a platform that the step ends after both connectors logged a completed snapshot that started after the job ("Deployed and fed")
- [ ] 2.8 Lint the script and the tests as the Build workflow does (shellcheck, flake8 for any Python); verify that the Build workflow's shacl2flink and bats-unit jobs pass

## 3. Watchdog

- [x] 3.1 Change the repair text of `ValidationConsistency` to name `make flink-redeploy` and its four steps in their order, and the checkpoint note to "instead of the redeploy" (D8); verify with the updated test in `test/bats-unit/platform-watchdog-alerts.bats` ("The repair", "No checkpoint", "A checkpoint before the state went stale")

## 4. End-to-end test on the platform

- [ ] 4.1 Add a bats suite `test-shacl-flink-redeploy` in `semantic-model/shacl2flink/tests/bats`, run by `test-flink-e2e` after the two existing suites and before the teardown, which runs `make flink-redeploy` with the e2e KMS; verify that the `flink` shard of `k8s-e2e.yaml` and `k8s-tests.yaml` run it and it passes
- [ ] 4.2 Set up through Scorpio and Alerta before the redeploy, reusing the helpers of `test-shacl-flink-scorpio-e2e`: an entity satisfying its count constraint, one satisfying the range constraint of `E2ERangeMachineShape`, each with a raise of that constraint written into `constraint_trigger_table` and `iff.alerts.bulk` the way the previous job writes it, so its alert is open (the stale raise of #977); an entity still violating a count constraint with its alert open; a raise and an open alert for an entity that doesn't exist; an open alert of another service; a record written to `iff.ngsild.entities`; verify that the suite asserts each of these is in place before it runs the redeploy
- [ ] 4.3 Acceptance criterion 1: verify in the suite that both alerts of satisfied constraints are closed after the redeploy and stay closed, and that `constraint_trigger_table` holds no record for them ("A count constraint satisfied now", "Another constraint type satisfied now", "A raise of the previous job")
- [ ] 4.4 Acceptance criterion 2: verify in the suite that the alert of the still violated constraint is open within two minutes, with the same severity and text and a close by the redeploy in its history ("Still violated", "An unchanged raise is forwarded")
- [ ] 4.5 Acceptance criterion 3: verify in the suite that the alert of the entity that doesn't exist is closed and still closed two minutes later ("An entity that no longer exists")
- [ ] 4.6 Acceptance criterion 4: verify in the suite that the alert of the other service has its status, severity and history unchanged ("Other alerts")
- [ ] 4.7 Acceptance criterion 5: verify in the suite that the command's output reports the four steps in order and it exits 0 ("The order"), next to the bats-unit tests of 2.1 and 2.2 for the failures
- [ ] 4.8 Acceptance criterion 6: verify in the suite, polling during the redeploy, that the KafkaTopic of `iff.ngsild.entities` exists throughout, its topic ID is unchanged and the record written before can be read afterwards ("iff.ngsild.entities kept")
- [ ] 4.9 Acceptance criterion 7: verify that 4.3 to 4.6 run in CI on the platform, and that the suite fails when step 2 or step 3 is skipped (run once locally with each step disabled: a satisfied alert stays open without step 1 or 2, a still violated alert stays closed without step 3)

## 5. Documentation and verification

- [x] 5.1 Describe `make flink-redeploy`, its order, what it closes and what an operator loses, in `semantic-model/shacl2flink/README.md`; verify that the README names the command and the four steps
- [ ] 5.2 Report the result per scenario of both delta specs in the Pull Request; verify that every scenario has a test or a recorded manual check
