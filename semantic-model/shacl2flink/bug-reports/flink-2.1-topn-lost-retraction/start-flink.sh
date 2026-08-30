#!/bin/bash
# Runs INSIDE the Flink container: add the connector jar, give the cluster
# enough task slots (the rule job and each INSERT ... VALUES job need one
# each), start it, and stay alive.
set -e
cp /data/"$JARNAME" /opt/flink/lib/
cd /opt/flink
# config.yaml (Flink >= 1.19) already carries a `taskmanager:` block, so the
# slot count must be edited in place -- appending a second block is a YAML
# duplicate-key error.
sed -i 's/numberOfTaskSlots: .*/numberOfTaskSlots: 8/' conf/config.yaml 2>/dev/null || true
sed -i 's/taskmanager.numberOfTaskSlots: .*/taskmanager.numberOfTaskSlots: 8/' conf/flink-conf.yaml 2>/dev/null || true
grep -rn numberOfTaskSlots conf/ || true
./bin/start-cluster.sh
sleep 3600
