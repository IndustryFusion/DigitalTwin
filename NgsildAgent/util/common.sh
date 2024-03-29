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
#
set -e

export CONFIG_DIR=../config
export CONFIG_FILE=${CONFIG_DIR}/config.json
export DATA_DIR=../data
export DEVICE_FILE=${DATA_DIR}/device.json
export DEVICES_NAMESPACE=devices
export ONBOARDING_TOKEN_FILE=${DATA_DIR}/onboard-token.json