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

# The contract test of openspec/specs/contracts/context-broker against a broker image, without Kubernetes.
#
#   test/context-broker/run.sh                       the broker the platform pins (test/build-local-platform.sh),
#                                                    built by test/opcua-chain/scorpio-image.sh if it isn't there
#   IMAGE=<image> test/context-broker/run.sh         any image built for the platform, e.g. a build of the fork
#   IMAGE=<image> MODE=upstream test/context-broker/run.sh
#                                                    an upstream Scorpio image: upstream's variables, no authorisation
#
# Needs Docker, Node 18 or newer, openssl and curl; building the pinned broker also needs git (JDK 21 and Maven 3.9
# come from a container).
# OUT is the directory for results (default .context-broker).
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1
if [ -z "${IMAGE:-}" ]; then
  IMAGE=$(bash test/opcua-chain/scorpio-image.sh) || { echo "FAIL cannot build the pinned broker"; exit 1; }
fi
MODE=${MODE:-platform}
: "broker.sh and contract.js read the mode each their own way, so anything else would skip checks silently"
case "$MODE" in
  platform|upstream) ;;
  *) echo "FAIL MODE must be platform or upstream, not '$MODE'"; exit 1;;
esac
export OUT=${OUT:-$PWD/.context-broker}
mkdir -p "$OUT"
NAMES=(ctx-broker ctx-broker-s)
cleanup () {
  for n in "${NAMES[@]}"; do
    docker rm -f "$n-sink" "$n-mqtt" > /dev/null 2>&1 || true
    bash test/opcua-chain/broker.sh down "$n"
  done
}
trap cleanup EXIT
cleanup

: "A broker built locally (test/opcua-chain/scorpio-image.sh) is used as it is; everything else is pulled"
for image in postgis/postgis:14-3.4 apache/kafka-native:3.9.0 python:3.12-alpine eclipse-mosquitto:2.0.20 "$IMAGE"; do
  docker image inspect "$image" > /dev/null 2>&1 || docker pull -q "$image" > /dev/null || { echo "FAIL cannot pull $image"; exit 1; }
done

# A broker named $1 on port $2, with a notification sink on port $2+1 (POST stores a notification, GET returns all,
# DELETE clears them) and an MQTT server $1-mqtt on its network, without authentication
start () {
  local name=$1 port=$2 code
  code=$(bash test/opcua-chain/broker.sh up "$name" "$port" "$IMAGE" "$OUT" "$MODE")
  if [ "$code" = 000 ]; then echo "FAIL the broker $IMAGE doesn't answer"; docker logs "$name-scorpio" 2>&1 | tail -n 25; return 1; fi
  docker run -d --name "$name-mqtt" --network "$name" eclipse-mosquitto:2.0.20 mosquitto -c /mosquitto-no-auth.conf > /dev/null ||
    { echo "FAIL cannot start the MQTT server $name-mqtt"; return 1; }
  docker run -d --name "$name-sink" --network "$name" -p "127.0.0.1:$((port + 1)):8080" python:3.12-alpine python -u -c '
import http.server, json
class Sink(http.server.BaseHTTPRequestHandler):
    received = []
    def log_message(self, *args):
        pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        Sink.received.append(json.loads(body or b"null"))
        self.send_response(200); self.end_headers()
    def do_GET(self):
        body = json.dumps(Sink.received).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)
    def do_DELETE(self):
        Sink.received.clear()
        self.send_response(200); self.end_headers()
http.server.ThreadingHTTPServer(("", 8080), Sink).serve_forever()' > /dev/null ||
    { echo "FAIL cannot start the notification sink $name-sink"; return 1; }
  for _ in $(seq 1 30); do curl -s -m 2 -o /dev/null "http://127.0.0.1:$((port + 1))/" && return 0; sleep 1; done
  echo "FAIL the notification sink doesn't answer"; return 1
}
run () {
  local name=$1 port=$2 part=$3
  BROKER="http://127.0.0.1:$port" SINK="http://127.0.0.1:$((port + 1))" SINK_IN="http://$name-sink:8080" MQTT="$name-mqtt" \
    KEY="$OUT/key.pem" MODE="$MODE" PART="$part" node test/context-broker/contract.js 2>&1 | tee "$OUT/$part.log"
  local rc=${PIPESTATUS[0]}
  docker logs "$name-scorpio" > "$OUT/$name-scorpio.log" 2>&1 || true
  return "$rc"
}

echo "=== contract test of $IMAGE ($MODE)"
status=0
start ctx-broker 19290 && run ctx-broker 19290 main || status=1
bash test/opcua-chain/broker.sh down ctx-broker; docker rm -f ctx-broker-sink ctx-broker-mqtt > /dev/null 2>&1
: "The sub-attribute merge stops all notifications on an image with the deviation, so it gets a broker of its own"
start ctx-broker-s 19292 && run ctx-broker-s 19292 subattribute || status=1
[ $status = 0 ] && echo "=== the contract test passed" || echo "=== the contract test FAILED"
exit $status
