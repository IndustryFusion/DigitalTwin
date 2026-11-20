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

PYTHON := python3
LINTER := python3 -m flake8
PIP := pip
HELM_DIR := ../../helm/charts/shacl
NAMESPACE := iff
TOLINT := nodeset2owl.py owl2instances.py owl2kms.py lib/kms_package.py lib/instance_coverage.py nodeset-dump.py validate.py start_fuseki.py extractIffBindings.py owl2vt.py virtual_type_stats.py check_consistency.py lib/nodesetparser.py lib/utils.py lib/shacl.py lib/entity.py lib/jsonld.py lib/bindings.py lib/owlbuilder.py
PYTEST := python3 -m pytest


lint: requirements-dev.txt
	$(LINTER) ${TOLINT}

setup: requirements.txt setup-dev
	$(PIP) install -r requirements.txt

setup-dev: requirements-dev.txt
	$(PIP) install -r requirements-dev.txt

# The example KMS packages (openspec gh-944-opcua-kms-package): generated, never
# committed. Every example writes shacl.ttl, entities.ttl, ... into this
# directory, so each starts from its own clean slate. `kms-packages` downloads
# NodeSets and ontologies; `kms-packages-check` only verifies what it wrote.
KMS_EXAMPLES := pumpExample:opcua-pumps laserExample:opcua-laser simpleExample:opcua-simple
KMS_OUT ?= ../kms
SEMFORGE ?= ../SemForge-SDK/venv/bin/semforge

kms-packages:
	for entry in $(KMS_EXAMPLES); do \
		example=$${entry%%:*}; \
		$(MAKE) -f translate_$$example.make clean && \
		$(MAKE) -f translate_$$example.make package KMS_OUT="$(KMS_OUT)" || exit 1; \
	done

# validate reads a package's model through the package's own context.jsonld, so a name the instances use but
# that context does not define fails here. opcua-laser is not validated: its example nodeset lacks mandatory
# members (Activity, UtilityName of the prognoses), which the shapes rightly report.
KMS_VALIDATED := opcua-pumps opcua-simple

kms-packages-check:
	for entry in $(KMS_EXAMPLES); do \
		$(SEMFORGE) verify "$(KMS_OUT)/$${entry##*:}" || exit 1; \
	done
	for package in $(KMS_VALIDATED); do \
		$(SEMFORGE) validate "$(KMS_OUT)/$$package" || exit 1; \
	done

test:
	${PYTEST} tests --cov=lib . --cov-fail-under=80
	make -f translate_default_nodesets.make
	(cd tests/nodeset2owl; bash ./test.bash)
	(cd tests/owl2instances; bash ./test.bash)
	(cd tests/owl2instances; bash ./e2e_shacl2flink.bash)
	(cd tests/nodeset-dump; bash ./test.bash)
	(cd tests/validation; bash ./test.bash)
	(cd tests/extractIffBindings; bash ./test.bash)
	(cd tests/owl2vt; bash ./test.bash)
	$(PYTHON) check_consistency.py