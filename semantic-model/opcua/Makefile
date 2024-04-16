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
TOLINT := nodeset2owl.py extractType.py lib/nodesetparser.py lib/utils.py lib/shacl.py lib/entity.py lib/jsonld.py lib/bindings.py
PYTEST := python3 -m pytest


lint: requirements-dev.txt
	$(LINTER) ${TOLINT}

setup: requirements.txt setup-dev
	$(PIP) install -r requirements.txt

setup-dev: requirements-dev.txt
	$(PIP) install -r requirements-dev.txt

test:
	${PYTEST} tests --cov . --cov-fail-under=80
	(cd tests/nodeset2owl; bash ./test.bash)
	(cd tests/extractType; bash ./test.bash)