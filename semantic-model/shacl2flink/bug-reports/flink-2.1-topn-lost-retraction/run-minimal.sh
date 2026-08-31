#!/bin/bash
# Reproduce the Flink 2.1+ Top-N retraction bug against one Flink version.
#
# A top-1 ROW_NUMBER view holds exactly one row per key, so COUNT(*) over it
# with a single key can only be 1. On 2.1+ it returns 2, because the planner
# declares the Rank insert-only and its retraction is dropped.
#
#   ./kafka_setup.sh                      # once, starts `kafka` on `reprnet`
#   ./run-minimal.sh <flink-image> <label> <kafka-connector-jar-url>
#
# e.g.
#   ./run-minimal.sh flink:1.20.4 1.20 \
#     https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.3.0-1.20/flink-sql-connector-kafka-3.3.0-1.20.jar
#   ./run-minimal.sh flink:2.3.0 2.3 \
#     https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/5.0.0-2.2/flink-sql-connector-kafka-5.0.0-2.2.jar
#
# 1.20.4 prints cnt=1 twice. 2.3.0 prints cnt=1 then cnt=2.
#
# The one-word control: DDL=minimal-ddl-descending.sql
# STEPS=minimal-inserts-descending.sql is the same query with ASC changed to
# DESC, and is correct on both versions.
set -u
IMG="$1"; LABEL="$2"; JAR="$3"
D="$(cd "$(dirname "$0")" && pwd)"
JARNAME=$(basename "$JAR"); B=kafka:9092; CN=sqlrep-$LABEL
DDL=${DDL:-minimal-ddl.sql}; RULE=${RULE:-minimal-query.sql}
STEPS=${STEPS:-minimal-inserts.sql}
say() { echo "[$LABEL] $*"; }
[ -f "$D/$JARNAME" ] || curl -sSL -o "$D/$JARNAME" "$JAR"

for t in t rowcount; do
  docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server $B \
    --delete --topic $t >/dev/null 2>&1
done
sleep 4
for t in t rowcount; do
  docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server $B \
    --create --topic $t --partitions 1 --replication-factor 1 >/dev/null 2>&1
done

rm -f "$D"/_step*.sql   # stale steps from a previous run must not leak in
# every sql-client invocation is its own session, so each script repeats the DDL
cat "$D/$DDL" "$D/$RULE" > "$D/_query.sql"
python3 - "$D" "$STEPS" "$DDL" <<'EOF'
import sys
d = sys.argv[1]
ddl = open(d + '/' + sys.argv[3]).read()
steps = open(d + '/' + sys.argv[2]).read().split('-- ===== STEP')
for i, s in enumerate(steps[1:], start=1):
    open(f'{d}/_step{i}.sql', 'w').write(ddl + '\n-- ===== STEP' + s)
EOF

docker rm -f $CN >/dev/null 2>&1
docker run -d --name $CN --network reprnet -v "$D":/data -e JARNAME="$JARNAME" \
  --entrypoint /bin/bash "$IMG" /data/start-flink.sh >/dev/null
sleep 15

# never pipe this through `tail -2`: a step that failed to submit then looks
# like a Flink result rather than a broken script.
run() { docker exec $CN bash -c "cd /opt/flink && ./bin/sql-client.sh -f /data/$1 2>&1 \
        | grep -E 'ERROR|Exception|Caused|successfully submitted' | tail -4" | sed "s/^/[$LABEL] /"; }

say "submit the query"; run _query.sql; sleep 30
i=1
while [ -f "$D/_step$i.sql" ]; do
  say "insert $i"; run _step$i.sql; sleep 55
  i=$((i+1))
done

say "rowcount topic (must be 1 every time):"
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server $B \
  --topic rowcount --from-beginning --timeout-ms 15000 2>/dev/null \
  | sed "s/^/[$LABEL]    /"
docker rm -f $CN >/dev/null 2>&1
