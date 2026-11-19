# Tasks

## 1. Build per component

- [ ] 1.1 Split `Build` into one job per component (docker images, shacl2flink, dataservice, SemForge SDK, datamodel tools, OPC UA tools, iff-agent, OPC UA KMS packages) with no job depending on another; install sqlite3 with the PCRE extension through one shared script in the shacl2flink and SemForge SDK jobs. Verified by a pull request run with every job green and side by side, and by the SemForge SDK job running its SQLite cross-check tests.
- [ ] 1.2 Add the `test-scripts` job: lint and shell-check the bats suites, run `test/bats-unit`. Move the two suites that run helm-templated scripts against a mocked `kubectl` (connect restarter, platform watchdog) from `test/bats/test-jobs` to `test/bats-unit`, and remove the duplicate `compare_attributes4` that shellcheck 0.9 reports as unreachable. Verified by `bats test/bats-unit` and the job green in CI.
- [ ] 1.3 Add the `debezium-snapshot-memory` job running `test/debezium-snapshot-memory/test.sh` with the Connect image built from `docker-compose.yml`. Verified by the job green in CI (the defaults run out of memory, the chart's bounds complete).

## 2. K8s end-to-end shards

- [ ] 2.1 Add `.github/scripts/e2e-shards.sh` (`select`, `suites`, `list`) with the shards and path rules of the design. Verified by `test/bats-unit/e2e-shards.bats`: every suite directory in exactly one shard, every named suite exists, every rule branch selects its shards (agent, shacl2flink, bridges, Debezium connector, EMQX, Scorpio, Fuseki, a suite directory, shared platform files, top-level test scripts only), unrelated paths select none, `--all`, empty input, unknown shard.
- [ ] 2.2 Add `test/prepare-platform-for-github-runner.sh` (`images` and `cluster` phases, two k3d agents) and `test/platform-images.sh` (`save`, `load`). Verified by shellcheck and by the shards of the pull request run.
- [ ] 2.3 Wait up to 5 minutes for cert-manager in `helm/install_operators.sh`. Verified by the shards' installs on runners without cached images.
- [ ] 2.4 Add the `K8s e2e` workflow: the `changes` job selects the shards from the merge commit's diff (`e2e-all` or a manual start: every shard), the `images` job builds once, one job per selected shard installs, loads the images and runs its suites (`flink` also shacl2flink's `test-flink-e2e`); a new push cancels the older head's run; a label other than `e2e-all` neither starts nor cancels a run (also not through the concurrency group); specification-only pull requests don't trigger it. Verified by this pull request's run: every shard selected (it changes shared platform files) and green, and the shards kept running when `spec-approved` or another label was added.
- [ ] 2.5 Run `K8s tests` only from the nightly, by hand and for a pull request labelled `e2e-full`; no run on pushes to `main`; a label other than `e2e-full` neither starts nor cancels it; keep its `openspec/` exclusion; drop the shacl2flink lint, unit and KMS tests and the bats linting from it. Verified by this pull request: `K8s tests` skipped without the label, one run green on the self-hosted runner after adding `e2e-full`, and that run kept running when another label was added.

## 3. Documentation

- [ ] 3.1 Name the checks a pull request runs and the labels `e2e-full` and `e2e-all` in `CONTRIBUTING.md`, `AGENTS.md`, the pull request template and `test/README.md` (including the new scripts). Verified by review against the delta specs.

## 4. Verification

- [ ] 4.1 Verify every scenario of the delta specs against the pull request's runs and tests and list the result per scenario in the pull request. The specification-only scenario is verified by the archive pull request, which runs neither `Build` nor any K8s end-to-end test.
- [ ] 4.2 State the coverage of the shard selection: every branch of its path rules is exercised by a bats test. Verified by the per-branch list in the pull request.
