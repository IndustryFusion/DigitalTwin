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
#
# End-to-end tests for semanticbridge2owl.py (Part 14): for each NodeSet2.xml
# scenario below, run the full real pipeline --
#   NodeSet2.xml --[nodeset2owl.py]--> Semantic Bridge ttl --[semanticbridge2owl.py]--> pure OWL ttl
# -- and compare the result against a golden ttl (isomorphism-aware, ignoring
# the ontology header since owl:imports resolution touches the network).
#
# Requires ../../core.ttl to already exist (built by
# `make -f translate_default_nodesets.make` at the repo root, which `make test`
# already runs before invoking any tests/*/test.bash).
#
set -e

BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0/base.ttl
CORE_ONTOLOGY=../../core.ttl
NODESET2OWL=../../nodeset2owl.py
SEMANTICBRIDGE2OWL=../../semanticbridge2owl.py
COMPARE="python3 ./compare_vt_output.py"
CHECK_CONTRADICTION="python3 ./check_unsatisfiable_precondition.py"

if [ ! -f "${CORE_ONTOLOGY}" ]; then
    echo "Missing ${CORE_ONTOLOGY}. Run 'make -f translate_default_nodesets.make' at the repo root first."
    exit 1
fi

# name, expect-contradiction ("true"/"false")
SCENARIOS=(
    "test_vt_minimal.NodeSet2,false"
    "test_vt_inheritance.NodeSet2,false"
    "test_vt_override.NodeSet2,false"
    "test_vt_nested.NodeSet2,false"
    "test_vt_contradiction.NodeSet2,true"
)

for tuple in "${SCENARIOS[@]}"; do IFS=","
    set -- $tuple
    name=$1
    expect_contradiction=$2
    unset IFS

    sb="${name}.ttl"
    owl="${name}.owl.ttl"
    expected="${name}.owl.ttl.expected"

    echo "=================================================================="
    echo "=== ${name} ==="
    echo "=================================================================="

    echo "--- nodeset2owl.py: ${name}.xml -> ${sb}"
    python3 ${NODESET2OWL} ${name}.xml -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} \
        -v http://example.com/v0.1/test/ -p test -o ${sb} || exit 1

    echo "--- semanticbridge2owl.py: ${sb} -> ${owl}"
    python3 ${SEMANTICBRIDGE2OWL} ${sb} -o ${owl} -q || exit 1

    echo "--- compare against ${expected}"
    ${COMPARE} ${expected} ${owl} || exit 1

    if [ "${expect_contradiction}" = "true" ]; then
        echo "--- checking the override IS structurally unsatisfiable"
        ${CHECK_CONTRADICTION} --expect-contradiction ${owl} || exit 1
    else
        echo "--- checking no false-positive contradiction was introduced"
        ${CHECK_CONTRADICTION} --expect-none ${owl} || exit 1
    fi

    rm -f ${sb} ${owl}
    echo "=== ${name}: PASSED ==="
    echo
done

echo "All semanticbridge2owl.py e2e tests passed."
