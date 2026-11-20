# Proposal

Issue: #1006

## Why

Every pull request and every push to `main` runs `K8s tests` on the single self-hosted runner: a full platform install and every bats suite, about 40 minutes a run, whatever the change touches. The runs queue behind each other, so results arrive hours late, and a change the cluster never runs still waits for one. `Build` runs every component one after the other in one job, about an hour.

## What Changes

- The K8s end-to-end test of a pull request runs on GitHub-hosted runners, split into shards (`device`, `broker`, `flink`) that run side by side. Each shard installs the full platform and runs its own suites, the same suites as today.
- The paths a pull request changes select the shards. Files every install depends on select all of them, and a change the cluster never runs selects none. The label `e2e-all` runs every shard.
- **BREAKING (CI behaviour):** `K8s tests`, every suite on one install on the self-hosted runner, no longer runs for every pull request and push to `main`. It runs in the nightly, by hand, and for a pull request with the label `e2e-full`.
- `Build` runs one job per component, side by side.
- The tests that need no cluster leave the K8s test: linting the bats suites, and the suites that run helm-templated scripts against a mocked `kubectl`. So does the shacl2flink lint and unit test, which `Build` already runs. The Debezium snapshot memory test, run by no workflow so far, joins `Build`.
- Specification-only pull requests still run neither `Build` nor any K8s end-to-end test.

## Capabilities

### New Capabilities
- `ci/pull-request-tests`: which tests a pull request, a push to `main` and the nightly run, where they run, and how a pull request's changed paths select the K8s end-to-end shards.

### Modified Capabilities
- `spec-driven-workflow`: *Specification-only contributions run only the validation* says that every other pull request runs `Build` and `K8s tests` as before. A pull request now runs `Build` and the K8s end-to-end shards its paths select, and `K8s tests` runs in the nightly.

## Out of Scope

- Installing only the components a shard needs (one full install per shard stays); a later change can slim the shards.
- Moving the nightly off the self-hosted runner, and pushing images from GitHub-hosted runners.
- Fixing flaky suites; they move with their shard.
- The OPC UA chain test and its workflow, which stay as they are.

## Impact

- CI workflows: `Build`, `K8s tests`, a new `K8s e2e` workflow; the nightly is unchanged.
- Test scripts: a setup script for GitHub-hosted runners, the shard selection, moving two bats suites out of the K8s test; `install_operators.sh` waits longer for cert-manager, which a runner without cached images needs.
- Contributor documentation: `CONTRIBUTING.md`, `AGENTS.md`, the pull request template and `test/README.md` name the checks a pull request runs.
- No component's code, image or deployment changes, and no contract between components changes.
