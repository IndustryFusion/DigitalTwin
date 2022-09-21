# Installation of Digital Twin Platform using Crossplane

## Getting started

* Deploy `DigitalTwinPlatform` composite resource definition.

```shell
kubectl apply -f crossplane/platform/definition.yaml
```

* Deploy `local` and `ionos` compositions. 
```shell
kubectl apply -f crossplane/platform/local/composition.yaml
kubectl apply -f crossplane/platform/ionos/composition.yaml
```

### Local deployment

#### Prerequisites
* [Helm provider](https://github.com/crossplane-contrib/provider-helm).
* Provider config named `digitaltwin`.

# TODO: MOVE ALL RESOURCES TO DIGITALTWIN PLATFORM


### IONOS cloud deployment

----

#### Prerequisites
* [IONOS provider](https://github.com/ionos-cloud/crossplane-provider-ionoscloud)
* Provider config named `digitaltwin`.

##### Deploy a DigitalTwinPlatform

e.g.
```shell
kubectl apply -f crossplane/platform/ionos/example.yaml
```

#### Extract K8s secret
```shell
kubectl get secret digitaltwinplatform-ionos-example-kubeconfig -o jsonpath='{.data.kubeconfig}' | base64 --decode > ionos-example-kubeconfig.conf
```

#### Use it
```shell
export KUBECONFIG=$(pwd)/ionos-example-kubeconfig.conf
```
