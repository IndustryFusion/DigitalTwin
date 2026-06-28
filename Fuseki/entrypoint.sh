#!/bin/bash
set -e

# Build one --tdb2 --loc=<path> /<realm> argument group per realm.
# FUSEKI_REALMS is a space-separated list supplied via the K8s env var.
ARGS=()
for realm in ${FUSEKI_REALMS}; do
    mkdir -p "/fuseki/databases/${realm}"
    ARGS+=(--tdb2 --update --loc="/fuseki/databases/${realm}" "/${realm}")
done

exec java ${JVM_ARGS} -cp /opt/fuseki/fuseki-server.jar \
    org.apache.jena.fuseki.main.cmds.FusekiMainCmd "${ARGS[@]}"
