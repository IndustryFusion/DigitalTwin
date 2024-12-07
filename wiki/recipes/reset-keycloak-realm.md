# How to reset Keycloak REALM

This document describes how to bring the keycloak realm into the default state. The default state is stored in a K8s Custom Resource and is applied by the Keycloak-Operator when there is no valid Keycloak DB. Therefore, cleaning the keycloakdb table and reinstalling Keycloak will fix the problem. NOTE that this procedure will delete all individual changes which have been applied to Keycloak. 
The preferred way to recover the keycloak settings is therefore to recover the database. But if the Keycloak state needs to be reset to the original state, the following can be applied. Note that hereby admin password is changed and all related access and refresh tokens will become invalid. DEvices need to be reonboarded in this case.

##  Remove Keycloak

In directory `DigitalTwin/test` apply:

    ./install-platform.sh -t app=keycloak -c destroy
## Clean Keycloak DB

Open a shell in pod `acid-cluster-0`, e.g. by typing 's' in the pod-view of K9s. in the pod execute

    su postgres
    psql
    drop DATABASE keycloakdb;
    create database keycloakdb;

Then the shell can be exited.

## Redeploy Keycloak

In directory `DigitalTwin/test` apply:

    ./install-platform.sh -t app=keycloak -c apply