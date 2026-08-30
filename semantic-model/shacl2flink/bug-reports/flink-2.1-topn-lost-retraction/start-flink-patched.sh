#!/bin/bash
# Runs INSIDE the Flink container. Same as start_flink.sh, but swaps the
# stock planner for the patched one: the distribution loads the planner
# through lib/flink-table-planner-loader-*.jar, so to use a custom build the
# loader is removed and the planner jar itself is placed in lib/.
set -e
cp /data/"$JARNAME" /opt/flink/lib/
cd /opt/flink
rm -f lib/flink-table-planner-loader-*.jar
cp /data/patched-planner.jar lib/flink-table-planner_2.12-2.3.0.jar
echo "planner in lib:"; ls -l lib/ | grep -i planner
sed -i 's/numberOfTaskSlots: .*/numberOfTaskSlots: 8/' conf/config.yaml 2>/dev/null || true
./bin/start-cluster.sh
sleep 3600
