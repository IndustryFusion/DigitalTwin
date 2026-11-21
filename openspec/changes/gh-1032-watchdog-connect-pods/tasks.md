# Tasks

## 1. The checks

- [x] 1.1 Add the check `ConnectPods` (D1, D2); verify with tests of the watchdog script ("No running pod", "Restarted by the restarter", "Between delete and create", "Running again")
  - `test/bats-unit/platform-watchdog-alerts.bats`: *kafka-connect without a running pod is critical at the next run* (a crashing pod, and no pod at all); *a kafka-connect pod just replaced is starting, and a moment without a pod is looked at again*; *kafka-connect running again closes the alert* (the normal alert reaches Alerta); *kafka-connect pods that can't be listed post nothing*. The first two fail on `main`.
- [x] 1.2 Post `ResyncRecency` as normal on every run (D3); verify with a test of the watchdog script ("An open alert of the replaced check")
  - Same file: *an open ResyncRecency alert of the replaced check is closed* (fails on `main`).

## 2. Checks

- [x] 2.1 Run the watchdog tests and shellcheck as the Build workflow does; verify all pass
  - `bats test/bats-unit`: 81 tests pass (45 of the watchdog); shellcheck of the bats suites and of the watchdog script passes.
- [x] 2.2 On a deployed platform, run the watchdog once; verify `ConnectPods` is normal with a running Connect pod and `ResyncRecency` is posted as normal
  - On a local platform one run reported `[normal] kafka-connect/ConnectPods: running` and `[normal] kafka-connect/ResyncRecency: replaced`.
  - `test/bats/test-jobs/platform-watchdog.bats` asserts both on the installed platform, and that `ConnectPods` is normal in Alerta.
