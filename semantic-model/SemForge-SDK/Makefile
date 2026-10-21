PYTHON := venv/bin/python
PIP := venv/bin/pip
LINTER := venv/bin/flake8

setup: venv
	$(PIP) install -q -r requirements.txt -r requirements-dev.txt
	# Editable install so `semforge` imports regardless of the working
	# directory. The language server is launched with the folder the user
	# opened as its cwd, so an uninstalled package fails there while working
	# fine from a terminal inside this directory.
	$(PIP) install -q -e .

venv:
	python3 -m venv venv

test:
	$(PYTHON) -m pytest --cov semforge --cov-fail-under=80

# The extension in a real VS Code, on a throwaway copy of the kms corpus.
# Downloads VS Code once into vscode/.vscode-test; needs a display (a desktop,
# WSLg, or xvfb-run make test-e2e).
test-e2e:
	cd vscode && npm install --no-audit --no-fund && npm run test:e2e

lint:
	$(LINTER) semforge tests

clean:
	rm -rf venv .pytest_cache .coverage

.PHONY: setup test test-e2e lint clean
