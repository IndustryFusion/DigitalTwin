#!/bin/bash
#
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

#for testdir in $(ls payload*.jsonld_?_c*); do
while IFS='_' read -ra ADDR; do
  payload=${ADDR[0]}
  switch=${ADDR[1]}
  context=${ADDR[2]}
  comparewith=${payload}_${switch}_${context}
  echo comparewith $comparewith
  command="node ../../jsonldConverter.js $payload -$switch -c file://$PWD/$context"
  echo Executing: $command
  $command | diff ${comparewith} -
  #$command
  #for i in "${ADDR[@]}"; do
    # process "$i"
  #  echo $i
  #done
done <<< $(ls payload*.jsonld_?_c*)
