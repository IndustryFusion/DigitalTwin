#
# Copyright (c) 2026 Intel Corporation
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
# End-to-end tests for owl2virtualtypes.py (Part 14): for each NodeSet2.xml
# scenario below, run the full real pipeline --
#   NodeSet2.xml --[nodeset2owl.py]--> Semantic Bridge ttl --[owl2virtualtypes.py]--> OWL ontology of Virtual Types
# -- compare the result against a golden ttl (isomorphism-aware, ignoring the
# ontology header since owl:imports resolution touches the network), and for
# scenarios that construct a deliberate (or deliberately absent) contradiction,
# feed that OWL ontology of Virtual Types straight into check_consistency.py,
# which loads it directly (no regeneration -- see that module's own docstring
# for why reprocessing an already-built *.owl.ttl through OwlBuilder itself
# would be wrong) and runs the real HermiT reasoner over it.
#
# Requires ../../core.ttl AND ../../core.owl.ttl to already exist (both built
# by `make -f translate_default_nodesets.make` at the repo root, which `make
# test` already runs before invoking any tests/*/test.bash): the former is
# this suite's own -i dependency for nodeset2owl.py, the latter is what every
# generated *.owl.ttl here transitively owl:imports and check_consistency.py
# must be able to resolve.
#
set -e

MAKEFILE=../../translate_default_nodesets.make
# Read straight from the Makefile's own BASE_ONTOLOGY(_NS), so this can't
# silently drift out of sync with it again (it already has once: this file
# hardcoded .../v0/base.ttl while the Makefile had moved on to
# .../v0.3/base.ttl, which breaks nodeset2owl.py's reference-type/alias
# resolution against a core.ttl built with the newer base ontology).
#
# BASE_ONTOLOGY (-i/-burl) is the fetchable *document*; BASE_ONTOLOGY_NS
# (-b) is the *term namespace* those base:xxx IRIs are minted under -- the
# v0.3 document is a patched version of the base ontology (fixing
# inconsistencies like isAbstract boolean/string mismatches) but still
# declares its own terms under the original, unchanged v0 namespace. These
# must NOT be conflated into the same value: doing so once already made
# every base:xxx term in the generated output a malformed, separator-less
# run-on IRI (see translate_default_nodesets.make's own comment on this).
BASE_ONTOLOGY=$(grep -oP '^BASE_ONTOLOGY\s*:?=\s*\K\S+' "${MAKEFILE}")
BASE_ONTOLOGY_NS=$(grep -oP '^BASE_ONTOLOGY_NS\s*:?=\s*\K\S+' "${MAKEFILE}")
CORE_ONTOLOGY=../../core.ttl
NODESET2OWL=../../nodeset2owl.py
OWL2VIRTUALTYPES=../../owl2virtualtypes.py
COMPARE="python3 ./compare_vt_output.py"
CHECK_CONTRADICTION="python3 ../../check_consistency.py"

if [ ! -f "${CORE_ONTOLOGY}" ]; then
    echo "Missing ${CORE_ONTOLOGY}. Run 'make -f translate_default_nodesets.make' at the repo root first."
    exit 1
fi
if [ ! -f "../../core.owl.ttl" ]; then
    echo "Missing ../../core.owl.ttl. Run 'make -f translate_default_nodesets.make' at the repo root first."
    exit 1
fi

# name, expect-contradiction ("true"/"false")
SCENARIOS=(
    "test_vt_minimal.NodeSet2,false"
    "test_vt_inheritance.NodeSet2,false"
    "test_vt_override.NodeSet2,false"
    "test_vt_nested.NodeSet2,false"
    "test_vt_contradiction.NodeSet2,true"
    "test_vt_distinct_owners.NodeSet2,false"
    "test_vt_datatype_contradiction.NodeSet2,true"
    "test_vt_datatype_subtype_override.NodeSet2,false"
    "test_vt_modellingrule_narrowing.NodeSet2,false"
    "test_vt_deep_type_hierarchy.NodeSet2,false"
    "test_vt_array_modellingrule_placeholder.NodeSet2,false"
    "test_vt_type_valuerank_contradiction.NodeSet2,true"
    "test_vt_objecttype_contradiction.NodeSet2,true"
    "test_vt_objecttype_optional_no_contradiction.NodeSet2,false"
    "test_vt_variabletype_contradiction.NodeSet2,true"
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
        -b ${BASE_ONTOLOGY_NS} -burl ${BASE_ONTOLOGY} \
        -v http://example.com/v0.1/test/ -p test -o ${sb} || exit 1

    echo "--- owl2virtualtypes.py: ${sb} -> ${owl}"
    python3 ${OWL2VIRTUALTYPES} ${sb} -b ${BASE_ONTOLOGY_NS} -o ${owl} -q || exit 1

    echo "--- compare against ${expected}"
    ${COMPARE} ${expected} ${owl} || exit 1

    if [ "${expect_contradiction}" = "true" ]; then
        echo "--- checking with HermiT that the override IS unsatisfiable"
        ${CHECK_CONTRADICTION} --expect-contradiction ${owl} || exit 1
    else
        echo "--- checking with HermiT that no false-positive contradiction was introduced"
        ${CHECK_CONTRADICTION} --expect-none ${owl} || exit 1
    fi

    rm -f ${sb} ${owl}
    echo "=== ${name}: PASSED ==="
    echo
done

echo "All owl2virtualtypes.py e2e tests passed."
