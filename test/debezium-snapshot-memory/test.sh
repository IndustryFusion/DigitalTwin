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
# Does a Debezium snapshot of a large knowledge table fit the Kafka Connect
# heap the chart deploys? Runs the platform's Connect image against a
# 219,500-row rdf table (the size of the OPC UA pumps knowledge) twice:
#
#   1. Debezium/producer defaults      -> expected to run out of memory
#                                         (proves the test can fail)
#   2. the bounds from the chart       -> must complete, every row in Kafka,
#                                         live heap below LIMIT_MB
#
# The heap and the bounds are read from helm/values.yaml.gotmpl, so the test
# checks what is deployed, not a copy of it.
#
# usage: test.sh                 (CONNECT_IMAGE overrides the image)
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
cd "$HERE" || exit 1

value() { sed -n "/^  connect:/,/^  [a-z]/s/^    $1: *\"\?\([^\"]*\)\"\?\$/\1/p" "$ROOT/helm/values.yaml.gotmpl" | head -1; }
HEAP=$(value heap)
BUFFER=$(value producerBufferMemory)
QUEUE=$(value maxQueueSize)
BATCH=$(value maxBatchSize)
ROWS=219500
LIMIT_MB=${LIMIT_MB:-80}
. "$ROOT/.env"
export CONNECT_IMAGE=${CONNECT_IMAGE:-${DOCKER_PREFIX:-ibn40}/debezium-postgresql-connector:${DOCKER_TAG}}
export CONNECT_HEAP=$HEAP
echo "image $CONNECT_IMAGE, heap $HEAP, chart bounds: buffer.memory=$BUFFER max.queue.size=$QUEUE max.batch.size=$BATCH"
if [ -z "$HEAP" ] || [ -z "$BUFFER" ] || [ -z "$QUEUE" ] || [ -z "$BATCH" ]; then
  echo "FAIL: could not read kafka.connect values"; exit 1
fi

dc() { docker compose "$@"; }
cleanup() { dc down -v >/dev/null 2>&1; }
trap cleanup EXIT

dc up -d kafka postgres >/dev/null 2>&1 || { echo "FAIL: compose up"; exit 1; }
until [ "$(dc exec -T postgres psql -U postgres -d flink -Atc 'select count(*) from rdf' 2>/dev/null)" = "$ROWS" ]; do sleep 2; done
until dc exec -T postgres pg_isready -q 2>/dev/null; do sleep 1; done
sleep 3

live_heap_mb() {
  dc exec -T connect bash -c 'P=$(for p in /proc/[0-9]*; do grep -q ConnectDistributed $p/cmdline 2>/dev/null && basename $p; done | head -1); jcmd $P GC.class_histogram 2>/dev/null | tail -1' | awk '{print int($3/1048576)}'
}

# run <label> <extra connector config as JSON members>
# prints: <result> <peak_live_heap_MB> <records_in_topic>
run() {
  dc rm -sf connect >/dev/null 2>&1
  dc exec -T postgres psql -U postgres -d flink -Atc "select pg_drop_replication_slot(slot_name) from pg_replication_slots" >/dev/null
  for t in iff.rdf connect-configs connect-offsets connect-status; do
    dc exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --delete --topic $t >/dev/null 2>&1
  done
  sleep 3
  dc up -d connect >/dev/null 2>&1
  until dc exec -T connect curl -sf localhost:8083/connector-plugins >/dev/null 2>&1; do sleep 2; done
  # the rdf connector as helm/charts/kafka/templates/kafkaConnector.yml renders it
  local cfg='{"name":"rdf-table-connector","config":{
   "connector.class":"io.debezium.connector.postgresql.PostgresConnector","tasks.max":"1",
   "snapshot.mode":"always","database.hostname":"postgres","database.port":"5432",
   "database.user":"postgres","database.password":"pw","database.dbname":"flink",
   "database.server.name":"iff","table.include.list":"public.rdf","slot.name":"rdf_slot",
   "key.converter":"org.apache.kafka.connect.json.JsonConverter","value.converter":"org.apache.kafka.connect.json.JsonConverter",
   "key.converter.schemas.enable":"false","value.converter.schemas.enable":"false",
   "transforms":"Reroute, unwrap","transforms.Reroute.type":"io.debezium.transforms.ByLogicalTableRouter",
   "transforms.Reroute.topic.regex":"(.*)\\.public\\.(.*)","transforms.Reroute.topic.replacement":"$1.$2",
   "transforms.unwrap.type":"io.debezium.transforms.ExtractNewRecordState","transforms.Reroute.key.enforce.uniqueness":"false"
   '"$2"' }}'
  echo "$cfg" | dc exec -T connect curl -sf -o /dev/null -X POST -H 'Content-Type: application/json' --data @- localhost:8083/connectors || { echo "register-failed 0 0"; return; }
  local peak=0 res=timeout h log
  for _ in $(seq 1 300); do
    h=$(live_heap_mb); [ -n "$h" ] && [ "$h" -gt "$peak" ] && peak=$h
    log=$(dc logs connect 2>&1)
    echo "$log" | grep -q OutOfMemoryError && { res=OOM; break; }
    echo "$log" | grep -q "Snapshot ended with SnapshotResult \[status=COMPLETED" && { res=COMPLETED; break; }
    echo "$log" | grep -q "Task threw an uncaught and unrecoverable exception" && { res=TASK-FAILED; break; }
    sleep 1
  done
  sleep 8
  local n
  n=$(dc exec -T kafka /opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server kafka:9092 --topic iff.rdf 2>/dev/null | awk -F: '{s+=$3} END{print s+0}')
  echo "$res $peak $n"
}

FAIL=0
read -r R P N <<< "$(run defaults '')"
echo "defaults:     result=$R peak_live_heap_MB=$P records=$N/$ROWS"
[ "$R" = OOM ] || { echo "FAIL: the defaults did not run out of memory -- the test no longer reproduces the problem"; FAIL=1; }

read -r R P N <<< "$(run chart ",\"producer.override.buffer.memory\":\"$BUFFER\",\"max.queue.size\":\"$QUEUE\",\"max.batch.size\":\"$BATCH\"")"
echo "chart bounds: result=$R peak_live_heap_MB=$P records=$N/$ROWS"
[ "$R" = COMPLETED ] || { echo "FAIL: snapshot did not complete with the chart's bounds"; FAIL=1; }
[ "$N" = "$ROWS" ] || { echo "FAIL: $N of $ROWS records reached Kafka"; FAIL=1; }
[ "$P" -le "$LIMIT_MB" ] || { echo "FAIL: live heap $P MB above $LIMIT_MB MB"; FAIL=1; }

[ $FAIL = 0 ] && echo "PASS" || echo "FAILED"
exit $FAIL
