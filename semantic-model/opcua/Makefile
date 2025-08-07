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

PYTHON := uv run python
LINTER := uv run python -m flake8
PIP := uv pip
HELM_DIR := ../../helm/charts/shacl
NAMESPACE := iff
TOLINT := nodeset2owl.py extractType.py nodeset-dump.py validate.py start_fuseki.py extractIffBindings.py lib/nodesetparser.py lib/utils.py lib/shacl.py lib/entity.py lib/jsonld.py lib/bindings.py
PYTEST := uv run python -m pytest


lint: pyproject.toml
	$(LINTER) ${TOLINT}

setup: pyproject.toml
	uv sync

setup-dev: pyproject.toml
	uv sync --dev

test: pyproject.toml
	${PYTEST} tests --cov=lib . --cov-fail-under=80
	(cd tests/nodeset2owl; bash ./test.bash)
	(cd tests/extractType; bash ./test.bash)
	(cd tests/nodeset-dump; bash ./test.bash)
	(cd tests/validation; bash ./test.bash)
	(cd tests/extractIffBindings; bash ./test.bash)