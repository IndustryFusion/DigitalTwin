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
5. Install the charts by using helmfile: `./helmfile_linux_amd64 apply`
6. Verify all pods are running using `kubectl -n iff get pods`
7. Login to keycloak with browser using `http://keycloak.local/auth`

   * The username is `admin`, the password can be found by `kubectl -n iff get secret/credential-keycloak -o=jsonpath='{.data.ADMIN_PASSWORD}' | base64 -d`
8. Verify that there are 2 realms `master`, `iff`
9. Verify that there is a user in realm `iff`, named: `realm_user`

   * The password for `realm_user` can be found by  `		kubectl -n iff get secret/credential-iff-realm-user-iff -o jsonpath='{.data.password}'| base64 -d`
10. Get token through http://keycloak.local/auth
11. Use ngsi-ld api via `ngsild.local`

## Troubleshooting

1. Keycloak instance not ready
2. Alerta not coming up
   * Error msg in the logs: `alerta.exceptions.ApiError: Could not get OpenID configuration from well known URL: HTTPConnectionPool(host='keycloak.local', port=80): Max retries exceeded with url: /auth/realms/iff/.well-known/openid-configuration`
     * `keycloak.local` url cannot be resolved from within kubernetes, make sure that it is known by the kubernetes dns. For K3s please see #configure-keycloak.local-dns
3. Alerta and/or Scorpio do not resolve keycloak.local

## Uninstallation Procedure

Test systems can uninstall all helm charts by:

```
./helmfile_linux_amd64 destroy
bash ./uninstall_operators.sh
```

Removal instructions for helm charts are provided in the *Uninstallation* sections in the `README` files for [1-chart](1-chart/README.md#uninstallation) and [2-chart](2-chart/README.md#uninstallation). Once charts have been removed, the Operators can be uninstalled using `uninstall_operators.sh`.

# Configure Keycloak.local dns

Edit the coredns configmap of kubesystem:
`kubectl -n kube-system edit cm/coredns`

```
 NodeHosts: |
    172.27.0.1 host.k3d.internal
    172.27.0.2 <your cluster name>
    172.27.0.2 keycloak.local # <= add here the keycloak.local entry
```

restart the `coredns` pod in `kube-system` namespace. Then start a test busybox and make sure you can ping

```
 kubectl -n iff run -i --tty --rm debug --image=busybox --restart=Never -- sh
 If you don't see a command prompt, try pressing enter.
/ # ping keycloak.local
PING keycloak.local (172.27.0.2): 56 data bytes
64 bytes from 172.27.0.2: seq=0 ttl=64 time=0.035 ms
64 bytes from 172.27.0.2: seq=1 ttl=64 time=0.032 ms
64 bytes from 172.27.0.2: seq=2 ttl=64 time=0.032 ms

```
