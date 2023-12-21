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

. common.sh

usage="Usage: $(basename $0) <propertyname> <value> \n"

if [ $# -eq 2 ]; then
  propName="$1"
  value="$2"
else
  echo "Error: Expected propertyname and value."
  printf "${usage}"
  exit 1
fi

if [ -z "$CONFIG_FILE" ]; then
  echo "$CONFIG_FILE does not exists. Please prepare it.!"
  exit 1
fi
udpPort=$(jq '.listeners.udp_port' $CONFIG_FILE)

if [ -z $udpPort ]; then
  echo "No udp Port found. Please check $CONFIG_FILE"
fi

echo sending '{"n":"'${propName}'", "v":"'${value}'", "t":"Property"}' to udp port ${udpPort} 
echo -n '{"n":"'${propName}'", "v":"'${value}'", "t":"Property"}'  > /dev/udp/127.0.0.1/${udpPort}

