# How to Reset TimescaleDB Database

## Stop consuming services

In k9s, go to deployments and scale down (typing `s`) the following deployments to 0:

- timescaledb-bridge

## Reset database

Open a shell in pod `acid-cluster-0`, e.g. by typing 's' in the pod-view of K9s. in the pod execute

    su postgres
    psql tsdb
    DROP SCHEMA public CASCADE; CREATE SCHEMA public;
    grant usage on schema public to public;
    grant create on schema public to public;


## Start consuming services

In k9s, go to deployments and scale down (typing `s`) the following deployments to 1:

- timescaledb-bridge