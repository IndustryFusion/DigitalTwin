#!/bin/bash
# Copyright (c) 2024 IB Systems GmbH
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

CONTAINER_NAME = iff-iot-agent

build:
	@$(call msg,"Building iff-iot-agent ...")
	@docker build . -t ${IMAGE_NAME}

start:
	@$(call msg,"Starting iff-iot-agent container...")

	docker run  \
				-d -t -i --network=host --rm \
				--env DEVICE_ID=${DEVICE_ID} \
				--env GATEWAY_ID=${GATEWAY_ID} \
				--env KEYCLOAK_URL=${KEYCLOAK_URL} \
				--env REALM_ID=${REALM_ID} \
				--env REALM_USER_PASSWORD=${REALM_USER_PASSWORD} \
				--env DEBUG=${DEBUG} \
				--name ${CONTAINER_NAME} ${IMAGE_NAME}