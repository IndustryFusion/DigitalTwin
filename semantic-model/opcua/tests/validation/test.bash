#!/bin/bash
#
# Copyright (c) 2025 Intel Corporation
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

VALIDATE=../../validate.py
PYTHON=python3
RESULTFILE=result.txt

# Each test is defined as:
# "TestName SHACLFILE TESTFILE [extra options]"
tests=(
  "RankValueTest ../../validation/ontology/rankValue.shacl.ttl ./rankValueTest.ttl -ni"
  "HasComponentTest ../../validation/ontology/hasComponent.shacl.ttl ./hasComponentTest.ttl"
)

for test in "${tests[@]}"; do
  # Extract parameters
  testName=$(echo "$test" | awk '{print $1}')
  shaclFile=$(echo "$test" | awk '{print $2}')
  testFile=$(echo "$test" | awk '{print $3}')
  extraOpts=$(echo "$test" | cut -d' ' -f4-)
  
  echo "-----------------------"
  echo "Executing ${testName}"
  echo "${PYTHON} ${VALIDATE} -s ${shaclFile} ${extraOpts} ${testFile}"
  
  ${PYTHON} ${VALIDATE} -s ${shaclFile} ${extraOpts} ${testFile} | \
    egrep "Message|Focus" | grep -v Literal | sed 's/^[[:space:]]*//' | LC_ALL=POSIX sort > ${RESULTFILE}
    
  diff ${RESULTFILE} ${testFile}.result
  echo "Test passed"
done


