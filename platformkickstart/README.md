# Platform kickstarter

`platformkickstart` helps deploying a DigitalTwinPlatforn on:
- Local cluster
- Private cloud
- Ionos cloud

### Prerequisites
- docker

### Building
```shell
make build
```

### Local scenario

Creates kind cluster and deploys DigitalTwinPlatform there.

##### Flags:

- `save-kubeconfig`: Kubeconfig save path.

#### Example usage

```shell
platformkickstart -file pkg/crossplane/deploy/local-example-claim.yaml
```

### Private cloud scenario

Deploys a DigitalTwinPlatform on the desired private cloud.

##### Flags:

- `kubeconfig`: Kubeconfig of private cloud.

#### Example usage

```shell
platformkickstart -file pkg/crossplane/deploy/private-example-claim.yaml --kubeconfig=private-kubeconfig
```

### Ionos cloud scenario

Deploys a DigitalTwinPlatform on the Ionos infrastructure.

##### Flags:

- `ionos-username`: IONOS account username.
- `ionos-password`: IONOS account password.
- `save-kubeconfig`: Kubeconfig save path.

#### Example usage

```shell
platformkickstart -file pkg/crossplane/deploy/private-example-claim.yaml --ionos-username=username --ionos-password=password --save-kubeconfig=ionos-kubeconfig`
```

----
## Crossplane deployment without kickstarter
Deploy all crossplane resources:
```shell
make crossplane-resoures
```

----
### Local cloud scenario

#### Prerequisites
* [Helm provider](https://github.com/crossplane-contrib/provider-helm) with "cluster-admin" role.
  
  e.g. for `provider-helm`
  ```shell
  SA=$(kubectl -n crossplane-system get sa -o name | grep provider-helm | sed -e 's|serviceaccount\/|crossplane-system:|g')
  kubectl create clusterrolebinding provider-helm-admin-binding --clusterrole cluster-admin --serviceaccount="${SA}"
  ```
* [Kubernetes provider](https://github.com/crossplane-contrib/provider-kubernetes) with "cluster-admin" role.
  
  e.g. for `provider-kubernetes`
  ```shell
  SA=$(kubectl -n crossplane-system get sa -o name | grep provider-kubernetes | sed -e 's|serviceaccount\/|crossplane-system:|g')
  kubectl create clusterrolebinding provider-kubernetes-admin-binding --clusterrole cluster-admin --serviceaccount="${SA}" 
  ```

#### Example usage
```shell
kubectl apply -f pkg/crossplane/deploy/local-claim-example.yaml
```

----
### Private cloud scenario

#### Prerequisites
* [Helm provider](https://github.com/crossplane-contrib/provider-helm)
* [Kubernetes provider](https://github.com/crossplane-contrib/provider-kubernetes)
* Secret named `<claim-name>-kubeconfig` with the kubeconfig key value.
  
  e.g. create it from env for `private-example` claim
  ```shell
  kubectl -n crossplane-system create secret generic private-example-kubeconfig --from-literal=kubeconfig="${KUBECONFIG}" 
  ```

#### Example usage
```shell
kubectl apply -f pkg/crossplane/deploy/private-claim-example.yaml
```

----

### Ionos cloud scenario

#### Prerequisites
* [Helm provider](https://github.com/crossplane-contrib/provider-helm)
* [Kubernetes provider](https://github.com/crossplane-contrib/provider-kubernetes)
* [Ionos provider](https://github.com/ionos-cloud/crossplane-provider-ionoscloud)
  * Provider config named `digitaltwin`.

#### Example usage
```shell
kubectl apply -f pkg/crossplane/deploy/ionos-claim-example.yaml
```

Extract kubeconfig from k8s secret
```shell
kubectl get secret digitaltwinplatform-ionos-example-kubeconfig -o jsonpath='{.data.kubeconfig}' | base64 --decode > ionos-example-kubeconfig.conf
```

Use it
```shell
export KUBECONFIG=$(pwd)/ionos-example-kubeconfig.conf
```
