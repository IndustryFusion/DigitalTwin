# This repo contains Helm charts for deploying ScorpioBroker, Alerta, and Flink Operator

A `conf.yaml` file contains passwords and service names that must be filled in prior to deploying using Helm.


## ibn40 Docker Hub images

ScoprioBroker components are pulled from `ibn40/digitaltwin` repository in Docker Hub. Image tags contain the suffix `3.0.0-SNAPSHOT`. Debezium adapter image is tagged `debeziumbridge`.


## Installation

Please ensure your `kubectl` is configured to use the credentials to your Kubernetes cluster by default. Generally this would mean adding your credentials to `~/.kube/config` file.

Please ensure the namespace exists before executing this command. You can create a new namespace using `kubectl create ns <namespace>`. It is recommended to use `kubens` to prevent specifying the namespace manually on every command.
```
helm install <release-name> . -f conf.yaml -n <namespace>
```


## Accessing Alerta console via GUI

To enable GUI access to Keycloak, a self-signed TLS certificate is provided in the Helm chart at the following location:
`charts/alerta/values.yaml`
```
153: tlsCrt
154: tlsKey
``` 
In addition to this, you will need to add the following to your `hosts` file to access the Alerta GUI using your browser:
```
85.215.213.132 alerta.local
```
The IP and the hostname can be retrieved from the output of `kubectl get ingress -n <namespace>`.


## Uninstallation

Services deployed using this chart can be removed using Helm `uninstall`
```
helm uninstall <release-name> -n <namespace>
```
