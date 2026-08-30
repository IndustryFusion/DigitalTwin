#!/bin/bash
# Bring up a single-node Kafka (KRaft) on a docker network for the reproducer.
# run-minimal.sh creates and fills the topics itself, so nothing is produced
# here.
set -e
NET=reprnet
KAFKA=${KAFKA_IMAGE:-k3d-iff.localhost:12345/strimzi/kafka:0.45.0-kafka-3.9.0}
D="$(cd "$(dirname "$0")" && pwd)"

docker network create $NET 2>/dev/null || true
docker rm -f kafka 2>/dev/null || true

docker run -d --name kafka --network $NET --user root \
  -e LOG_DIR=/tmp/kafka-logs-out -e KAFKA_HEAP_OPTS="-Xmx512M -Xms256M" \
  -v "$D/server.properties":/tmp/server.properties \
  --entrypoint /bin/bash $KAFKA -c '
    /opt/kafka/bin/kafka-storage.sh format -t 5L6g3nShT-eMCtK--X86sw \
      -c /tmp/server.properties --ignore-formatted
    exec /opt/kafka/bin/kafka-server-start.sh /tmp/server.properties'

echo "waiting for kafka ..."
for i in $(seq 1 40); do
  if docker exec kafka /opt/kafka/bin/kafka-topics.sh \
       --bootstrap-server kafka:9092 --list >/dev/null 2>&1; then
    echo "kafka up"; exit 0
  fi
  sleep 3
done
echo "kafka did not come up" >&2
exit 1
