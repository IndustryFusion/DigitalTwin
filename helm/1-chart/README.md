# This repo contains Helm charts for deploying Postgres Operator, Strimzi Operator, and Keycloak Operator

A `conf.yaml` file contains passwords and service names that must be filled in prior to deploying using Helm.


## ibn40 Docker Hub images

ScoprioBroker components are pulled from `ibn40/digitaltwin` repository in Docker Hub. Kafka Connect, a part of Strimzi, is pulled using the tag `connect_tgz`.


## Installation

Please ensure your `kubectl` is configured to use the credentials to your Kubernetes cluster by default. Generally this would mean adding your credentials to `~/.kube/config` file.

Please ensure the namespace exists before executing this command. You can create a new namespace using `kubectl create ns <namespace>`. It is recommended to use `kubens` to prevent specifying the namespace manually on every command.
```
helm install <release-name> . -f conf.yaml -n <namespace>
```


## Accessing Keycloak console via GUI

To enable GUI access to Keycloak, a self-signed TLS certificate is provided in the Helm chart at the following location:
`charts/keycloakOperator/values.yaml`
```
131: tlsCrt
132: tlsKey
``` 
In addition to this, you will need to add the following to your `hosts` file to access the Keycloak GUI using your browser:
```
85.215.213.132 keycloak.local
```
The IP and the hostname can be retrieved from the output of `kubectl get ingress -n <namespace>`.


## Uninstallation

Services deployed using this chart can be removed using Helm `uninstall`
```
helm uninstall <release-name> -n <namespace>
```

**Note:** Postgres Operator does not remove all created resources by design. Resources of type `Statefulset` and its associated `pods`, `Service`, `PersistentVolumeClaim` for each pod, and `Secret` will persist after running `helm uninstall`.

**Known issue:** Keycloak Operator fails to remove `CustomResourceDefinition` named `keycloakrealms.keycloak.org` after running `helm uninstall`. If this is not removed manually, subsequent Keycloak installations will fail. Delete the CRD using `kubectl delete crd keycloakrealms.keycloak.org` and hit `Ctrl+C` after you see the deletion success message in the terminal. Then execute `kubectl edit crd keycloakrealms.keycloak.org`, delete the entry under the `finalizers` section, and save. Verify that the CRD has been removed.