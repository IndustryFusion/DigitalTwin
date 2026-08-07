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
  "RankValueTest ../../validation/ontology/rankValue.shacl.ttl ./rankValueTest.ttl -ni -m ontology"
  "HasComponentTest ../../validation/ontology/hasComponent.shacl.ttl ./hasComponentTest.ttl -m ontology -ni"
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

# -m vt validates a *.vt.owl.ttl Virtual-Types ontology's logical consistency via
# the HermiT DL reasoner (see check_consistency.py, which validate.py's vt mode
# wraps for a single file) -- a different mechanism than the SHACL-shape checks
# above, so it gets its own pair of positive/negative fixtures rather than fitting
# the "tests" table's SHACLFILE/TESTFILE/result-diff shape. Reuses two fixtures
# tests/owl2vt/test.bash already maintains and validates via check_consistency.py
# directly, so this only asserts validate.py's own CLI wiring, not the underlying
# HermiT logic (already covered there). Assumes core.vt.owl.ttl already exists at
# the repo root, as it does by this point in `make test` (translate_default_nodesets.make
# runs before this script).
VT_CONTRADICTION=../owl2vt/test_vt_contradiction.NodeSet2.vt.owl.ttl.expected
VT_NO_CONTRADICTION=../owl2vt/test_vt_objecttype_optional_no_contradiction.NodeSet2.vt.owl.ttl.expected

echo "-----------------------"
echo "Executing VirtualTypesContradictionTest"
echo "${PYTHON} ${VALIDATE} -m vt ${VT_CONTRADICTION}"
if ${PYTHON} ${VALIDATE} -m vt ${VT_CONTRADICTION} > ${RESULTFILE} 2>&1; then
  echo "Expected validate.py -m vt to report a contradiction, but it exited 0:" && cat ${RESULTFILE} && exit 1
fi
grep -q "Validation Conforms: False" ${RESULTFILE} || \
  { echo "Expected 'Validation Conforms: False':" && cat ${RESULTFILE} && exit 1; }
echo "Test passed"

echo "-----------------------"
echo "Executing VirtualTypesNoContradictionTest"
echo "${PYTHON} ${VALIDATE} -m vt ${VT_NO_CONTRADICTION}"
${PYTHON} ${VALIDATE} -m vt ${VT_NO_CONTRADICTION} > ${RESULTFILE} 2>&1
grep -q "Validation Conforms: True" ${RESULTFILE} || \
  { echo "Expected 'Validation Conforms: True':" && cat ${RESULTFILE} && exit 1; }
echo "Test passed"


