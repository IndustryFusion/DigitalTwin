# This repo contains Helm charts for deploying Zalando Postgres Operator

Please ensure your `kubectl` is configured to use the credentials to your Kubernetes cluster by default. Generally this would mean adding your credentials to `~/.kube/config` file.

The database service name can be modified at the `clusterSvcName` key in the `values.yaml` file.
The total number of database pods (one master and remaining replicas) can be modified at the `podInstances` key in the `values.yaml` file.

## Installation

Ensure the namespace exists before executing this command. You can create a new namespace using `kubectl create ns <namespace>`
```
helm install zalando-operator . -n <namespace>
```
