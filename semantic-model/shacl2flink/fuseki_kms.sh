#!/bin/bash
#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Writes or removes the KMS graphs (shacl.ttl, knowledge.ttl) in Fuseki
# through the cluster, like the rest of flink-deploy: a port-forward to the
# Fuseki service, not the ingress. Fuseki serves each realm with --update
# and no authentication of its own (Fuseki/entrypoint.sh); the fuseki-auth
# proxy guards only the outside way in.
#
# Usage:
#   fuseki_kms.sh deploy   <namespace> <realm> <graph-base> <shacl.ttl> <knowledge.ttl>
#   fuseki_kms.sh undeploy <namespace> <realm> <graph-base>
#
# <graph-base> names the graphs (<graph-base>/shacl.ttl, <graph-base>/knowledge.ttl);
# it is not contacted.

set -euo pipefail

ACTION=${1:?deploy or undeploy}
NAMESPACE=${2:?namespace}
REALM=${3:?realm}
GRAPH_BASE=${4:?graph base}
SERVICE=${FUSEKI_SERVICE:-svc/fuseki}
REMOTE_PORT=${FUSEKI_PORT:-3030}

# A free local port, so parallel deploys don't collide.
LOCAL_PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')

kubectl -n "$NAMESPACE" port-forward "$SERVICE" "$LOCAL_PORT:$REMOTE_PORT" >/dev/null 2>&1 &
FORWARD=$!
trap 'kill $FORWARD 2>/dev/null || true' EXIT

BASE="http://127.0.0.1:$LOCAL_PORT"
for _ in $(seq 1 30); do
    if curl -s -o /dev/null "$BASE/\$/ping"; then
        break
    fi
    if ! kill -0 "$FORWARD" 2>/dev/null; then
        echo "ERROR: port-forward to $SERVICE in $NAMESPACE failed" >&2
        exit 1
    fi
    sleep 1
done
curl -s -o /dev/null "$BASE/\$/ping" || { echo "ERROR: Fuseki did not answer through the port-forward" >&2; exit 1; }

GSP="$BASE/$REALM/data"

put() {  # <file> <graph name>
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT -H "Content-Type: text/turtle" \
        --data-binary "@$1" "$GSP?graph=$GRAPH_BASE/$2")
    echo "$2 → $code"
    [ "$code" = "200" ] || [ "$code" = "201" ] || [ "$code" = "204" ] || { echo "ERROR: $2 upload failed ($code)" >&2; exit 1; }
}

count() {  # <graph name>: triples in the graph
    curl -s -H "Accept: application/sparql-results+json" \
        --data-urlencode "query=SELECT (COUNT(*) AS ?n) WHERE { GRAPH <$GRAPH_BASE/$1> { ?s ?p ?o } }" \
        "$BASE/$REALM/query" | python3 -c 'import json, sys; print(json.load(sys.stdin)["results"]["bindings"][0]["n"]["value"])'
}

case "$ACTION" in
    deploy)
        SHACL=${5:?shacl.ttl}
        KNOWLEDGE=${6:?knowledge.ttl}
        put "$SHACL" shacl.ttl
        put "$KNOWLEDGE" knowledge.ttl
        # An empty graph after an accepted upload means the data went somewhere else.
        for graph in shacl.ttl knowledge.ttl; do
            n=$(count "$graph")
            echo "$graph: $n triples"
            [ "$n" -gt 0 ] || { echo "ERROR: $graph is empty in Fuseki after the upload" >&2; exit 1; }
        done
        ;;
    undeploy)
        for graph in shacl.ttl knowledge.ttl; do
            code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$GSP?graph=$GRAPH_BASE/$graph")
            echo "$graph delete → $code"  # 404: it was not there
        done
        ;;
    *)
        echo "usage: $0 deploy|undeploy <namespace> <realm> <graph-base> [<shacl.ttl> <knowledge.ttl>]" >&2
        exit 2
        ;;
esac
