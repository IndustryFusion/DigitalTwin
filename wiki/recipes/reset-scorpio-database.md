# How to Reset Scorpio Database

## Stop consuming services

In k9s, go to deployments and scale down (typing `s`) the following deployments to 0:

- scorpio-all-in-one-runner
- ngsild-update-bridge

## Reset database

Open a shell in pod `acid-cluster-0`, e.g. by typing 's' in the pod-view of K9s. in the pod execute

    su postgres
    psql ngb;
    DROP SCHEMA public CASCADE; CREATE SCHEMA public;
    create extension postgis;
    grant usage on schema public to public;
    grant create on schema public to public;


## Start consuming services

In k9s, go to deployments and scale down (typing `s`) the following deployments to 1:

- scorpio-all-in-one-runner
- ngsild-update-bridge