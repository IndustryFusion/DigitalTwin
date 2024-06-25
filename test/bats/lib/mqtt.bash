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


MQTT_SERVICE=mqtt-service
MQTT_SERVICE_PORT=1883

mqtt_setup_service() {
  pod=$(kubectl -n ${NAMESPACE} get pods -l ${EMQX_LABEL} -o jsonpath='{.items[0].metadata.name}')
  exec stdbuf -oL kubectl -n ${NAMESPACE} port-forward $pod 1883:1883 &
}

mqtt_delete_service() {
    killall kubectl
}