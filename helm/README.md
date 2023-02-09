# Build and Deployment of Digital Twin Platform
This repo contains Helm charts for deploying the IFF Platform Services.

The Services consist of

* Zalando Postgres Operator
* Strimzi Kafka Operator
* Minio Operator
* Keycloak Operator
* Scorpio NGSI-LD Context broker with Keycloak integration
* Alerta with Keycloak integration
* Cert-Manager
* Apache Flink Streaming SQL
* SQL scripts for IFF example scenario 

There are two installation instructions below. The first [`section`](#installation-of-platform-with-dockerhub-access) describes how to deploy the platform with access to private dockerhub of IFF. The second [`section`](#building-and-installation-platform-locally) describes how to build everything from scratch with a local registry.

# Installation of Platform with DockerHub Access

---

> **_NOTE_**: Make sure you have access to IFF DockerHub repository. Otherwise follow the [local](#building-and-installation-of-whole-platform-locally) installation procedure below

---

1. Activate your Kubernetes cluster and install `kubectl` (`kubens` is also recommended) on your local machine.

   * Install an ingress controller, in case of K3s it is traefik, in other cases, install nginx ingress controller. [Instructions here.](https://kubernetes.github.io/ingress-nginx/deploy/#quick-start)
   * Edit you /etc/hosts file to make sure that `keycloak.local`, `alerta.local` and `ngsild.local` point to the ingress IP of your kubernetes cluster.
   * Make sure that the Pods within your Kubernetes cluster can resolve keycloak.local
2. Install operators using `bash install_operators.sh`
3. Install helm with diff plugin and helmfile 0.149.0:

   ```
   # helm v3.10.3
   wget https://get.helm.sh/helm-v3.10.3-linux-amd64.tar.gz
   tar -zxvf helm-v3.10.3-linux-amd64.tar.gz
   sudo mv linux-amd64/helm /usr/bin/helm

   # helm-diff plugin
   helm plugin install https://github.com/databus23/helm-diff

   # helmfile v0.149.0
   wget https://github.com/helmfile/helmfile/releases/download/v0.149.0/helmfile_0.149.0_linux_amd64.tar.gz
   tar -zxvf helmfile_0.149.0_linux_amd64.tar.gz
   chmod u+x helmfile
   ```
4. Deploy secrets for industry fusion registry

   ```
   kubectl -n iff create secret docker-registry regcred --docker-password=<password> --docker-username=<username> --docker-server=https://index.docker.io/v1/
   ```
5. Install the charts by using helmfile: `./helmfile apply`
6. Verify all pods are running using `kubectl -n iff get pods`
7. Login to keycloak with browser using `http://keycloak.local/auth`

   * The username is `admin`, the password can be found by `kubectl -n iff get secret/keycloak-initial-admin -o=jsonpath='{.data.password}' | base64 -d`
8. Verify that there are 2 realms `master`, `iff`
9. Verify that there is a user in realm `iff`, named: `realm_user`

   * The password for `realm_user` can be found by  `		kubectl -n iff get secret/credential-iff-realm-user-iff -o jsonpath='{.data.password}'| base64 -d`
10. Get token through http://keycloak.local/auth
11. Use ngsi-ld api via `ngsild.local`

## Configure Keycloak.local dns

First, find out which node in k3s is used as ingress ip by using `kubectl -n iff get ingress/keycloak-ingress -o jsonpath={".status.loadBalancer.ingress[0].ip"}`

Say the determined IP-addres is `172.27.0.2`. Then k8s internal, the keycloak.local has to be mapped to this IP. To do that, edit the coredns configmap of kubesystem:
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

# Building and Installation of Platform Locally

The following setup procedure is executed in the Kubernetes end to end [`test`](../.github/workflows/k8s-tests.yaml) as part of the Continous Integration procedure. It is tested and regularly executed on `Ubuntu 20.04`.

---

> **_NOTE_**: All following instructions have to be executed with an account with SUDO permission (i.e. Ubuntu admin user) 

---

The platform has to be prepared only once with the prepare script:
```
(cd test && bash ./prepare-platform.sh)
```

After that, the following steps have to be executed (note the round brackets):

```
(cd ./test/bats && bash ./prepare-test.sh)
(cd ./test && bash build-local-platform.sh)
(cd ./test && bash install-local-platform.sh)
```

---

> **_NOTE_**: This all can take some time when executed the first time because all the containers have to be downloaded to the local system. Be aware that DockerHub is restricting downloads of anonymous participants.

---

Finally, an otional (but recommended) end-to-end test can be excecuted to validate that all is up and running.
```
(cd ./test/bats && bats */*.bats)
```

# Troubleshooting

1. Keycloak instance not ready
2. Alerta not coming up
   * Error msg in the logs: `alerta.exceptions.ApiError: Could not get OpenID configuration from well known URL: HTTPConnectionPool(host='keycloak.local', port=80): Max retries exceeded with url: /auth/realms/iff/.well-known/openid-configuration`
     * `keycloak.local` url cannot be resolved from within kubernetes, make sure that it is known by the kubernetes dns. For K3s please see #configure-keycloak.local-dns
3. Alerta and/or Scorpio do not resolve keycloak.local

# Uninstallation Procedure

Test systems can uninstall all helm charts by:

```
./helmfile destroy
bash ./uninstall_operators.sh
```


