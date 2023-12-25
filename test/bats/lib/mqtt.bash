#!/usr/bin/env bats
# Copyright (c) 2023 Intel Corporation
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


MQTT_SERVICE=mqtt-test-service
MQTT_EMQX_SELECTOR="apps.emqx.io/instance: emqx"
MQTT_SERVICE_PORT=1883

mqtt_setup_service() {
    # shellcheck disable=SC2153
    cat << EOF  | kubectl -n "${NAMESPACE}" apply -f -
apiVersion: v1
kind: Service
metadata:
  name: ${MQTT_SERVICE}
spec:
  selector:
    ${MQTT_EMQX_SELECTOR}
  ports:
    - protocol: TCP
      port: ${MQTT_SERVICE_PORT}
      targetPort: ${MQTT_SERVICE_PORT}
EOF
run try "at most 30 times every 5s to find 1 service named '${MQTT_SERVICE}'"
}

mqtt_delete_service() {
    kubectl -n "${NAMESPACE}" delete svc "${MQTT_SERVICE}"
}