```
This repo contains Helm charts for deploying the IFF Platform Services
```

The Services consist of

* Zalando Postgres Operator
* Strimzi Kafka Operator
* Keycloak Operator
* Scorpio NGSI-LD Context broker with Keycloak integration
* Alerta with Keycloak integration
* Cert-Manager

An installation script `install_operators.sh` is provided to deploy the operators. The concrete instances are defined in a joint Helm chart, consisting of sub charts for the respective components. The installation is done with the helmfile tool.

## Installation Procedure Overview

1. Activate your Kubernetes cluster and install `kubectl` (`kubens` is also recommended) on your local machine.

   * Install an ingress controller, in case of K3s it is traefik, in other cases, install nginx ingress controller. [Instructions here.](https://kubernetes.github.io/ingress-nginx/deploy/#quick-start)
   * Edit you /etc/hosts file to make sure that `keycloak.local`, `alerta.local` and `ngsild.local` point to the ingress IP of your kubernetes cluster.
   * Make sure that the Pods within your Kubernetes cluster can resolve keycloak.local
2. Install operators using `bash install_operators.sh`
3. Install helm with diff plugin and helmfile 0.143.0:

   ```
   # helm v3.7.2
   wget https://get.helm.sh/helm-v3.7.2-linux-amd64.tar.gz
   tar -zxvf helm-v3.7.2-linux-amd64.tar.gz
   sudo mv linux-amd64/helm /usr/bin/helm

   # helm-diff plugin
   helm plugin install https://github.com/databus23/helm-diff

   # helmfile v0.143.0
   wget https://github.com/roboll/helmfile/releases/download/v0.143.0/helmfile_linux_amd64
   chmod u+x helmfile_linux_amd64
   ```
4. Deploy secrets for industry fusion registry
    ```
    kubectl -n iff create secret docker-registry regcred --docker-password=<password> --docker-username=<username> --docker-server=https://index.docker.io/v1/
    ```
4. Install the charts by using helmfile: `./helmfile_linux_amd64 apply`
5. Verify all pods are running using `kubectl -n iff get pods`
6. Login to keycloak with browser using `http://keycloak.local/auth`

   * The username is `admin`, the password can be found by `kubectl -n iff get secret/credential-keycloak -o=jsonpath='{.data.ADMIN_PASSWORD}' | base64 -d`
7. Verify that there are 3 realms `master`, `org`, `alerta`.
8. Select `alerta`, define user and get the secret of `alerta-ui` client.
9. Fill the secret into `default.yaml` in keycloak.alertaClientSecret
10. Select `org`, define users and assign `Factory Admin` Role on Realm level and for all Scorpio clients: `entity-mananger`, `query-manager`, ...
11. Get token through http://keycloak.local/auth
12. Use ngsi-ld api via `ngsild.local`

## Troubleshooting

1. Keycloak instance not ready
2. Alerta not coming up
2. Alerta and/or Scorpio do not resolve keycloak.local

## Uninstallation Procedure

Test systems can uninstall all helm charts by:

```
./helmfile_linux_amd64 destroy
bash ./uninstall_operators.sh
```

Removal instructions for helm charts are provided in the *Uninstallation* sections in the `README` files for [1-chart](1-chart/README.md#uninstallation) and [2-chart](2-chart/README.md#uninstallation). Once charts have been removed, the Operators can be uninstalled using `uninstall_operators.sh`.
