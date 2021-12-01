# This repo contains Helm charts for deploying ScorpioBroker

A `creds.yaml` file contains the following information which is injected into Helm during the build process:
- Credentials for pulling images from the **ibn40/digitaltwin** Docker Hub repository
- Client secrets for the five Scorpio Broker modules registered as Clients in Keycloak

Please ensure your `kubectl` is configured to use the credentials to your Kubernetes cluster by default. Generally this would mean adding your credentials to `~/.kube/config` file.

## Installation

```
cd helm
helm install scorpio-release scorpioBroker -f creds.yaml
```
