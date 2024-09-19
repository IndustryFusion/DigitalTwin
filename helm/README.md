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
* TimescaleDB and PostRest for generic access


# Building and Installation of Platform Locally

The following setup procedure is executed in the Kubernetes end to end [`test`](../.github/workflows/k8s-tests.yaml) as part of the Continous Integration procedure. It is tested and regularly executed on `Ubuntu 22.04` and `Ubuntu 24.04`.

---

> **_NOTE_**: All following instructions have to be executed with an account with SUDO permission (i.e. Ubuntu admin user) 

---

The platform has to be prepared only once with the prepare script:
```
(cd ../test && bash ./prepare-platform.sh)
```

After that, the following steps have to be executed (note the round brackets):

```
(cd ../test/bats && bash ./prepare-test.sh)
(cd ../test && bash build-local-platform.sh)
(cd ../test && bash ./install-platform.sh -l -c all)
```

---

> **_NOTE_**: This all can take some time when executed the first time because all the containers have to be downloaded to the local system. Be aware that DockerHub is restricting downloads of anonymous participants.

---


# Accessing Keycloak and Scorpio

1. Login to keycloak with browser using `http://keycloak.local/auth`

   * The username is `admin`, the password can be found by
  
     ```
     kubectl -n iff get secret/keycloak-initial-admin -o=jsonpath='{.data.password}' | base64 -d | xargs echo
     ```
2. Verify that there are 2 realms `master`, `iff`
3. Verify that there is a user in realm `iff`, named: `realm_user`

   * The password for `realm_user` can be found by
     ```
     kubectl -n iff get secret/credential-iff-realm-user-iff -o jsonpath='{.data.password}'| base64 -d | xargs echo
     ```
4. Get token through http://keycloak.local/auth
5. Use ngsi-ld api via `ngsild.local`


# Other Installation Options


1. Activate your Kubernetes cluster and install `kubectl` (`kubens` is also recommended) on your local machine.

   * Install an ingress controller, in case of K3s it is traefik, in other cases, install nginx ingress controller. [Instructions here.](https://kubernetes.github.io/ingress-nginx/deploy/#quick-start)
   * Edit you /etc/hosts file to make sure that `keycloak.local`, `alerta.local` and `ngsild.local` point to the ingress IP of your kubernetes cluster.
   * Make sure that the Pods within your Kubernetes cluster can resolve keycloak.local

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
4. (OPTIONAL) Deploy secrets for industry fusion registry if you are going to use a private docker registry

   ```
   kubectl -n iff create secret docker-registry regcred --docker-password=<password> --docker-username=<username> --docker-server=https://index.docker.io/v1/
   ```
## Installation Script
The installation script is located in the `../test` directory. It provides several installation options:
```
Usage: install-platform.sh [-t label] [-c command] [-olsv] <command>
-t:    Define label to apply
-o:    offline installation
-l:    local installation (for test & debug)
-c:    command: apply|sync|all|show|destroy|opinst|opuninst
-v:    verbose output

```
With the `-c` option it can either 
* install `all` by using `-c all`
* install dedicated sub parts by using `-c apply` and additional tag e.g.
   * `-t order=first` installs first part
   * `-t order=second` installs second part
   * `-t order=third` installs third part
   * `-t app=velero` installs velero
   * `-t app=keycloak` installs keyclaok
   * etc
* destroy dedicated sub parts by using `-c destroy` and tags, e.g
   * `-t order=first` installs first part
   * `-t app=velero` installs velero
   * etc
* install operators by using `-c opinst`
* destroy operators by using `-c opuninst`

Example 1:
```
bash ./install-platform.sh -c apply -t order=third
```
installs third subpart of platform from external repositories.

Example 2:
```
bash ./install-platform.sh -l -c apply -t order=first
```
installs first subpart where iff specific images are pulled locally and all other images are pulled from external repositories.

## Install with Dockerhub Access

The nighly builds and releases can be found at [Dockerhub](https://hub.docker.com/u/ibn40). To install a specific version, checkout the respective branch, update the tag description and apply the install script. For instance, to deploy version `v0.6.0-beta.1`, edit the file `.env` to containt the respective tag `DOCKER_TAG=v0.6.0-beta.1` and apply the procedure as follows:

      git checkout v0.6.0-beta.1
      (cd ../test && bash ./install-platform.sh -c all)

## Install with Airgap Mode

The Airgap mode works with a locally setup Kubernetes as described [here](#building-and-installation-of-platform-locally) 
Then download all the containers and github repositories locally:

```
(cd ./airgap-deployment && REGISTRY=k3d-iff.localhost:12345 bash ./prepare-airgap.bash)
```
After that, the offline and local deployment works as follows:

```
(cd ../test && bash ./install-platform.sh -lo -c all)
```



## Configure Keycloak.local dns

This is normally done by the platform installation scripts. However, dependent on K8s version, it needs to be done manually. For Keycloak to run properly, it needs to reach keycloak.local (or the defined external keycloak name) from inside of the K8s cluster.


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

# Troubleshooting

1. Keycloak instance not ready or there is no 'iff' realm. Check the keycloak realm import job, it can timeout if the postgres database does not come up on time. You can delete the job and the keycloak operator will automatically create a new one. Afterwards keycloak should come up.
2. Alerta not coming up
   * Error msg in the logs: `alerta.exceptions.ApiError: Could not get OpenID configuration from well known URL: HTTPConnectionPool(host='keycloak.local', port=80): Max retries exceeded with url: /auth/realms/iff/.well-known/openid-configuration`
     * `keycloak.local` url cannot be resolved from within kubernetes, make sure that it is known by the kubernetes dns. For K3s please see #configure-keycloak.local-dns
3. Alerta and/or Scorpio do not resolve keycloak.local

# S3 Backups and (Database) Recovery

By default, the database backups once per day to the internal Minio S3 storage. It can be configured to backup to another S3 by configuring the s3 object in the `environment/default.yaml` or `environment/production.yaml` profiles like so:

```
s3:
   protocol: 'https' # or 'http'
   endpoint: <S3 Endpoint>
   userAccessKey: <access key>
   userSecretKey: <secret key>
```

The selection of the environment files is depenend to the selected helmfile profile, if no profile is set, the `environment/default.yaml` file is used. In addition, when external S3 storage is used, Minio should be disabled in the profile, create the buckets in external S3 and then update the S3 bucket names in the following sections:

```
minio:
   enabled: false
```

```
velero:
  backupBucket: <External S3 bucket name for Velero>
```

```
flink:
  bucket: <External S3 bucket name for Flink>
```

```
db:
  backupBucket: <External S3 bucket name for Postgres>
```

Some Kubernetes Resources which are not easy recoverable are backed up once per day by `velero`.

In case of a database corruption, the database can be recoverd from S3 with the following steps:
1. Remove postgres chart: `helmfile -l app=postgres destroy`
2. Switch on database cloning mode in the profile:

   ```
   db:
   ...
      cloneEnabled: true
   ```

3. Clone the database: `helmfile -l app=postgres apply # --set "mainRepo=k3d-iff.localhost:12345" in case you pull images from local`
4. Wait until the postgres pods are up and running
5. Update all other charts: `helmfile apply # --set "mainRepo=k3d-iff.localhost:12345" --set "mainVersion=0.1" in case you pull images from local, adapt accordingly if you are pulling from dockerhub`
6. Recover missing secrets with `velero` by first [installing](https://velero.io/docs/v1.8/basic-install/) it.
7. Listing the `velero` backups and selecting the most recent one:
   
   ```
   velero backup get
   ```
8. Restore backup:
   ```
   velero restore create --from-backup <backup-name> --existing-resource-policy update
   ```
9. Update all charts again `helmfile apply # --set "mainRepo=k3d-iff.localhost:12345" --set "mainVersion=0.1" in case you pull images from local, adapt accordingly if you are pulling from dockerhub`

After that procedure, the database is running and all dependent pods should have been restarted and working with the new password credentials



