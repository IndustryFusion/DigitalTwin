# Tasks

## 1. The checks

- [ ] 1.1 Add the check `ConnectPods` (D1, D2); verify with tests of the watchdog script ("No running pod", "Restarted by the restarter", "Between delete and create", "Running again")
- [ ] 1.2 Post `ResyncRecency` as normal on every run (D3); verify with a test of the watchdog script ("An open alert of the replaced check")

## 2. Checks

- [ ] 2.1 Run the watchdog tests and shellcheck as the Build workflow does; verify all pass
- [ ] 2.2 On a deployed platform, run the watchdog once; verify `ConnectPods` is normal with a running Connect pod and `ResyncRecency` is posted as normal
