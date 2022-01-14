# This repo contains Helm charts for deploying ScorpioBroker, Alerta, and Flink Operator


## Filling in the configuration details

A `conf.yaml` file contains passwords and service names that must be filled in prior to deploying using Helm.
```
alerta:
  alertaConfig:
    DATABASE_URL = "postgresql://<username>:<password>@<database service name>.<database namespace>.svc.cluster.local:5432/monitoring"

  alertaConfigSercrets:
    OAUTH2_CLIENT_SECRET: 95daabc0-7041-427c-95c1-40b0bc2c1e50

scorpioBroker:
  keycloakClientSecrets:
    historyManagerSecret: <client secret for history-manager>
    entityManagerSecret: <client secret for entity-manager>
    queryManagerSecret: <client secret for query-manager>
    subscriptionManagerSecret: <client secret for subscription-manager>
    registryManagerSecret: <client secret for registry-manager>

  keycloak_vars:
    KEYCLOAK_SERVER_URL: keycloak:8443
```
- `alerta.alertaConfig.DATABASE_URL` is the [Postgres connection string](https://www.postgresql.org/docs/9.6/libpq-connect.html) to your Postgres database. You need to provide the `username`, `password`, `database service name`, and `database namepsace` as shown. This will be determined by how your specifications while deploying [1-chart](../1-chart/README.md#filling-in-the-configuration-details)
- `scorpioBroker.keycloakClientSecrets` should be configured with the client secrets for each ScorpioBroker microservices. This can be retrieved from the Keycloak Console.
- `alertaConfigSecrets.OAUTH2_CLIENT_SECRET` and `scorpioBroker.keycloak_vars.KEYCLOAK_SERVER_URL` can be left unchanged.


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
