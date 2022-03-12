# E2E tests

This folder contains the needed script for the github E2E tests.
`prepare-platform.sh`: Script to setup the Ubuntu 20.04 VM and install all needed packages and tools. This script is used to set every VM of a github hosted runner and has to be executed manually when a self-hosted github runner is used.
`prepare-platform-for-self-hosted-runner.sh`: In case of a self-hosted github runner this is used for the local setup. Self-hosted runners cannot use `prepare-platform.sh` above because it does not allow `sudo` operations.
`setup-local-ingress.sh`: For local testing the `/etc/hosts` file has to be changed to resolve `keycloak.local`, `alerta.local`, and `ngsild.local` to the respective K8s ingresses.

[`bats/`](bats/README.md): This directory contains the [bats-detik](https://github.com/bats-core/bats-detik) and [bats-core](https://github.com/bats-core/bats-core) based tests.

# Setup self-hosted runner for github

The main difference between a self-hosted and a github hosted runner is the fact that the github-hosted runner provides a clean VM for every test and the self-hosted provides always access to the same VM. Therefore the self-hosted VM needs to be prepare initially and then only tasks related to the concrete tests can be executed. For security reason nothing can be executed with `root` rights or `sudo`.

Self-Hosted-Runners can be added to github as describe [here](https://docs.github.com/en/actions/hosting-your-own-runners/about-self-hosted-runners). The VM which is added needs to fullfill the follwing:

1. The user under which the runner is installed must not be `root` and must not have password-less `sudo` rights.
2. A `root` user must install `prepare-platform.sh` with the env variable `SELF_HOSTED_RUNNER` set, i.e.

   ```
   # SELF_HOSTED_RUNNER=true bash ./prepare-platform.sh
   ```
3. The environment variable `SELF_HOSTED_RUNNER` must be set in the github actions workflow.
4. The tag `private` must be set for the self hosted runner, so that it is selected for the E2E test
5. The user which owns the runner must be part of following groups: `docker`, `runner`, e.g. by exeuting

   ```
   sudo usermod -a -G docker ${USER}
   sudo usermod -a -G runner ${USER}
   ```
