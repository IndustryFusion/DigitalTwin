#!/bin/bash
#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# A context broker with Postgres and Kafka on one Docker network, without Kubernetes and without Keycloak.
#
#   broker.sh up <name> <port> <image> <keydir> [platform|upstream]
#   broker.sh down <name>
#
# Containers are <name>-pg, <name>-kafka and <name>-scorpio on the network <name>; the broker listens on
# 127.0.0.1:<port>. "platform" (the default) starts the platform's image with the variables of its chart: Keycloak
# is replaced by a key pair in <keydir> (key.pem, pub.b64), generated if missing, and the broker accepts tokens
# signed with it. "upstream" starts an upstream Scorpio image with upstream's variable names; it has no
# authorisation. Prints the broker's answer to a request without a token, once it answers.
set -euo pipefail
cmd=${1:?usage: broker.sh up|down <name> ...}
N=${2:?name}
P=$N-pg; K=$N-kafka; C=$N-scorpio
if [ "$cmd" = down ]; then
  docker rm -f "$C" "$K" "$P" > /dev/null 2>&1 || true
  docker network rm "$N" > /dev/null 2>&1 || true
  exit 0
fi
PORT=${3:?port}; IMAGE=${4:?image}; KEYDIR=${5:?keydir}; MODE=${6:-platform}
mkdir -p "$KEYDIR"
if [ ! -f "$KEYDIR/key.pem" ]; then
  openssl genrsa -out "$KEYDIR/key.pem" 2048 2> /dev/null
  openssl rsa -in "$KEYDIR/key.pem" -pubout -outform DER 2> /dev/null | base64 -w0 > "$KEYDIR/pub.b64"
fi
docker network create "$N" > /dev/null
docker run -d --name "$K" --network "$N" \
  -e KAFKA_NODE_ID=1 -e KAFKA_PROCESS_ROLES=broker,controller \
  -e KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093 -e KAFKA_ADVERTISED_LISTENERS="PLAINTEXT://$K:9092" \
  -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT \
  -e KAFKA_CONTROLLER_QUORUM_VOTERS="1@$K:9093" -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 \
  apache/kafka-native:3.9.0 > /dev/null
: "Scorpio connects with SSL, so Postgres serves the image's snakeoil certificate"
docker run -d --name "$P" --network "$N" -e POSTGRES_USER=ngb -e POSTGRES_PASSWORD=ngb -e POSTGRES_DB=ngb postgis/postgis:14-3.4 \
  -c ssl=on -c ssl_cert_file=/etc/ssl/certs/ssl-cert-snakeoil.pem -c ssl_key_file=/etc/ssl/private/ssl-cert-snakeoil.key > /dev/null
for _ in $(seq 1 60); do docker exec "$P" pg_isready -U ngb -d ngb -q && break; sleep 1; done
: "pg_isready is true during the image's init restart, so give it a moment"
sleep 4
if [ "$MODE" = upstream ]; then
  docker run -d --name "$C" --network "$N" -p "127.0.0.1:$PORT:9090" \
    -e dbhost="$P" -e dbport=5432 -e dbname=ngb -e dbuser=ngb -e dbpass=ngb -e bushost="$K" -e busport=9092 \
    "$IMAGE" > /dev/null
else
  docker run -d --name "$C" --network "$N" -p "127.0.0.1:$PORT:9090" \
    -e POSTGRES_SERVICE="$P" -e POSTGRES_PORT=5432 -e POSTGRES_DBNAME=ngb -e POSTGRES_USERNAME=ngb -e POSTGRES_USER=ngb -e POSTGRES_PASSWORD=ngb \
    -e KAFKA_BOOTSTRAP="$K" -e KAFKA_BROKERS="$K" -e KAFKA_PORT=9092 \
    -e REALM=iff -e CLIENT_ID=scorpio -e SSL_REQUIRED=none \
    -e QUARKUS_OIDC_PUBLIC_KEY="$(cat "$KEYDIR/pub.b64")" -e QUARKUS_OIDC_TOKEN_ISSUER=any \
    "$IMAGE" > /dev/null
fi
code=000
for _ in $(seq 1 90); do
  code=$(curl -s -o /dev/null -m 3 -w '%{http_code}' "http://127.0.0.1:$PORT/ngsi-ld/v1/types" || true)
  [ "$code" != 000 ] && break
  sleep 2
done
echo "$code"
