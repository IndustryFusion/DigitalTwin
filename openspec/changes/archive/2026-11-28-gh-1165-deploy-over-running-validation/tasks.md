# Tasks

## 1. Fingerprint

- [x] 1.1 Compute the fingerprint: SHA-256, in a fixed order, over `helmfile -f helmfile-shacl.yaml template` of the shacl release with the deploy's environment and values, plus the three `.postgres` files. Verified by unit tests:
  - the same package and values rendered twice give the same value, with the `lookup` placeholders as well;
  - a change to one constraint, one knowledge triple, one statement or one rendered value gives another.

  (Scenarios "The same package rendered twice" and "A changed package or value".)
- [x] 1.2 Keep the fingerprint and the job ID in the ConfigMap `shacl-validation-fingerprint`, outside the release. The replace path deletes it before its resync and writes it with `kubectl apply` as the deploy's last step, only on success; `flink-undeploy` deletes it too. Verified by bats unit tests with stubbed kubectl:
  - written after a completed deploy;
  - not written when a step failed;
  - deleted before a replacement.

  The e2e test 4.4 checks that writing it leaves the job ID unchanged. (Scenarios "After a completed deploy" and "After an interrupted deploy".)

## 2. Resync replacement by a new package

- [x] 2.1 `shacl_resync.sh REPLACE=package` with an install command: stop (skipped without a statement set), close, reset, install, start, re-snapshot, processed, end.
  - The install writes the tables and runs `helmfile -f helmfile-shacl.yaml sync`.
  - The start waits for the new statement set and its job, and recreates no saved one; a kept one from an earlier failed resync is discarded.
  - A failure while no job runs names `make flink-deploy`.
  - The deadline includes the install's limit.

  Verified by `test/bats-unit/shacl-resync.bats` with stubbed kubectl, helmfile and curl:
  - the order of the steps, and the tables written only after the stop;
  - `sync`, not `apply`, also for an unchanged chart;
  - a failed install named, and the watchdog's failed mark set;
  - the stop skipped without a statement set;
  - a kept statement set discarded, not refusing;
  - the message naming the deploy;
  - refused before the first step while another resync runs.

  (Requirements "One command for the resync", "A fresh job replays nothing", "A failed resync stops", "Replace the validation by a new package" and "The new package's job is started, not the stopped one", all scenarios.)
- [x] 2.2 Mention `REPLACE=package` in the resync's header and in the Makefile's `shacl-resync` comment. Verified by review.

## 3. Deploy decision

- [x] 3.1 `make helm` stops writing the tables; `submit-postgres-tables` stays a target of its own. Verified by a unit test of the Makefile's target dependencies.
- [x] 3.2 `make flink-deploy` compares the kept fingerprint and job ID with the new fingerprint and the running job. Unchanged: no table write, Fuseki, `restart_connect.sh`, with the waited-for job ID in the output. Otherwise: delete the fingerprint ConfigMap, `shacl_resync.sh REPLACE=package` with the install (tables plus `helmfile sync`), then Fuseki, then the ConfigMap with the new job ID. Verified by bats unit tests with stubbed kubectl for each case (equal and the same job running, different, no ConfigMap, a ConfigMap of another job, no statement set, job not running): which path, and no psql call in the unchanged path. (Scenario "A fingerprint of another job".)

## 4. End-to-end on Flink (test-shacl-flink-deploy)

- [x] 4.1 Busy operator, redefined: hold the operator back from the moment the old statement set is gone until `HOLD` seconds after the new one exists, instead of before the deploy. Update the suite's comment. Verified by the suite itself: "Restart after a replacement" (newest Connect pod after the new job's start, no later restart, entities read).
- [x] 4.2 The second deploy (a changed statement set) replaces through the resync. Assert:
  - another job ID;
  - each constraint table source's `numRecordsOut` equals the table's row count;
  - every KafkaTopic keeps its topic ID;
  - the alerts of the suite's entities are those of a fresh deployment: the existing entity's count alert is open again; tests 4.3, 4.6 and 4.7 check the others. A comparison of every open alert with a separate fresh deployment is not made.

  (Scenarios "A changed package over a running validation" and "Alerts after a changed package".)
- [x] 4.3 Relationship counts: two entities raise a relationship-count alert under the first package. The changed package lets one of them satisfy its count, while the other still violates it. Assert after the deploy: the first alert closed, the second open with the real number. (Scenario "Relationship counts after a changed package".)
- [x] 4.4 A third and a fourth deploy of the same package over the running job. Assert:
  - the same job ID;
  - sources equal row counts;
  - the count verdicts unchanged;
  - the job ID named in the output;
  - the job ID still the same a minute after the fingerprint was written (no restart by the operator).

  (Scenarios "Deploying the same package again", "… three times", "Restart over an unchanged validation".)
- [x] 4.5 Delete the ConfigMap `shacl-validation-fingerprint` and deploy the same package: it replaces. (Scenario "A validation without a fingerprint".)
- [x] 4.6 Interrupted deploy: break a replacing deploy off after the new statement set exists, before the resync's end. The test gives the resync's wait for the re-snapshot one second, so it fails there, deterministically; a signal timed against the running deploy did not land reliably on CI. A failed and an interrupted resync leave the deploy the same way (no fingerprint kept); the resync's handling of a signal is covered by `test/bats-unit/shacl-resync.bats`. Deploy the same package again: it replaces, and the suite's count alerts are those of a fresh deployment. (Scenario "After an interrupted deploy".)
- [x] 4.7 No validation running, with an open alert of a previous validation: undeploy, keep the alert, deploy. Assert it is closed afterwards. (Scenario "No validation running".)

## 5. Open points settled on the cluster

- [x] 5.1 `iff.rdf`: deploy a changed package that removes a knowledge triple, and check that the new job no longer sees it. Settled on k3d (2026-11-27): it did see it. `iff.rdf` kept every key of every earlier package, without a single tombstone (design D6). The install step now ends with `drop_removed_knowledge`, which writes a tombstone for every live key of `iff.rdf` that the new rdf table lacks. Verified by:
  - unit tests in `test/bats-unit/shacl-resync.bats`: the right keys only, after the install; a key already tombstoned gets no second one; the same knowledge writes none; an empty or unreadable table, or a short read of the topic, fails the step;
  - the deploy suite: the changed package of 4.3 also drops the ontology's `owl:versionInfo` triple, which is live in `iff.rdf` before and a tombstone after. Passed on k3d: "214 live keys in iff.rdf, 1 of them removed by a tombstone". The first replacement there removed 6,154 stale keys.
  - a lint test in `test/bats-unit/shacl-resync-tty.bats`: no command of the scripts pipes into a reader that stops early (`grep -m`, `grep -q`, `head`). Under pipefail that failed the read of the rdf table's secret once on k3d, by SIGPIPE.

  (Scenarios "A knowledge triple removed by a new package" and "The same knowledge again".)
- [x] 5.2 Change data capture after the rewrite: 4.2's `numRecordsOut` assertion. If it fails, drop the two replication slots in the install step before writing the tables. Settled: it passes in CI and on k3d (2026-11-27), so the slots stay.

## 6. Documentation

- [x] 6.1 shacl2flink README:
  - what `make flink-deploy` does over a running validation, and the fingerprint;
  - that a deploy needs Alerta, Core Services and the platform watchdog;
  - that `make flink-undeploy` plus `make shacl-resync` are no longer needed after a package change.

  Verified by review.
