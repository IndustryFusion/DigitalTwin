PYTHON := python3
LINTER := $(HOME)/.local/bin/flake8
PIP := pip
HELM_DIR := ../../helm/charts/shacl
NAMESPACE := iff


lint: requirements-dev.txt
	$(LINTER)

setup: requirements.txt setup-dev
	$(PIP) install -r requirements.txt

setup-dev: requirements-dev.txt
	$(PIP) install -r requirements-dev.txt
