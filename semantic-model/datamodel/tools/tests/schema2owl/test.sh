#!/bin/bash
#
# Copyright (c) 2024 Intel Corporation
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

while IFS='_' read -ra ADDR; do
  schemaname=${ADDR[0]}
  context=${ADDR[1]%.json}
  file=${schemaname}_${context}.json
  comparewith=${file}_result
  id=${file}_id
  command="node ../../jsonschema2owl.js -s $file -c file://$PWD/$context -i $(cat "$id")"
  echo Executing: "$command"
  $command | diff "${comparewith}" - || exit 1
done <<< "$(ls schema*_*.json)"
