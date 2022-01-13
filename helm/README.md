# This repo contains Helm charts for deploying ScorpioBroker and Platform Services

An installation script `install_operators.sh` is provided to deploy operators for Keycloak, Kafka (Strimzi), and Postgres. Two Helm charts are provided: `1-chart` initialises the Opeartors and starts the services. `2-chart` deploys ScorpioBroker and  Alerta. Additional information is provided in the respective directories.

## Installation Procedure Overview

1. Activate your Kubernetes cluster and install `kubectl` (`kubens` is also recommended) on your local machine.
2. Install operators using `install_operators.sh`
3. Install nginx Ingress Controller. [Instructions here.](https://kubernetes.github.io/ingress-nginx/deploy/#quick-start)
4. Install **1-chart** using `helm`. [Learn more.](1-chart/README.md#installation)
5. Configure your `hosts` file to access Keycloak GUI. [Learn more.](1-chart/README.md#accessing-keycloak-console-via-gui)
6. Verify all pods are running and that the realms have been imported into Keycloak.
7. Install **2-chart** using `helm`. [Learn more.](2-chart/README.md#installation)
8. Configure your `hosts` file to access Alerta GUI. [Learn more.](2-chart/README.md#accessing-alerta-console-via-gui)
9. Verify all pods are up and running using `kubectl get pods`.


## Uninstallation Procedure

Removal instructions for helm charts are provided in the *Uninstallation* sections in the `README` files for [1-chart](1-chart/README.md#uninstallation) and [2-chart](2-chart/README.md#uninstallation). Once charts have been removed, the Operators can be uninstalled using `uninstall_operators.sh`.
