# This repo contains Helm charts for deploying ScorpioBroker and Platform Services

Two Helm charts are provided. `1-chart` deploys Postgres Operator, Keycloak Operator, and Strimzi (Kafka) Operator and must be installed first. `2-chart` deploys ScorpioBroker, Alerta, and Flink Operator. Additional information is provided in the respective directories.

## Installation Procedure Overview

1. Activate your Kubernetes cluster and install `kubectl` (`kubens` is also recommended) on your local machine.
2. Install **1-chart** using `helm`. [Learn more.](1-chart/README.md#installation)
3. Configure your `hosts` file to access Keycloak GUI. [Learn more.](1-chart/README.md#accessing-keycloak-console-via-gui)
4. ~~Login to Keycloak Admin Console with your credentials. From the Realm dropdown, select `Add realm` and import the files present in the `res` directory.~~
5. Verify all pods are up and running using `kubectl`.
6. Install **2-chart** using `helm`. [Learn more.](2-chart/README.md#installation)
7. Configure your `hosts` file to access Alerta GUI. [Learn more.](2-chart/README.md#accessing-alerta-console-via-gui)
8. Verify all pods are up and running using `kubectl`.


## Uninstallation Procedure

Removal instructions are provided in the *Uninstallation* sections in the `README` files for [1-chart](1-chart/README.md#uninstallation) and [2-chart](2-chart/README.md#uninstallation).
