#!/bin/bash
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
set -e

cd /app/util

# Debugging output
echo "ARG1: $DEVICE_ID"
echo "ARG2: $GATEWAY_ID"
echo "ARG3: $KEYCLOAK_URL"
echo "ARG4: $REALM_ID"
echo "ARG5: $REALM_USER_PASSWORD"

# Execute the first script with passed arguments
./init-device.sh -k "$KEYCLOAK_URL" -r "$REALM_ID" "$DEVICE_ID" "$GATEWAY_ID"
# Execute the second script with passed arguments
./get-onboarding-token.sh -p "$REALM_USER_PASSWORD" "realm_user"
# Execute the third script with passed arguments
./activate.sh -f

cd /app/

./iff-agent.js