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

export TSDB_TABLE=entityhistory
export TSDB_DATABASE=tsdb
export POSTGRES_SECRET=ngb.acid-cluster.credentials.postgresql.acid.zalan.do
export DBUSER=ngb
export NAMESPACE=iff
export USER_SECRET=secret/credential-iff-realm-user-iff
export USER=realm_user
export REALM_ID=iff
export KEYCLOAK_URL="http://keycloak.local/auth/realms"
export MQTT_URL=emqx-listeners:1883
export KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092