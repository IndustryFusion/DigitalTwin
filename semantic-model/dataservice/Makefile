PYTHON := uv run python
LINTER := uv run flake8
PIP := uv pip
HELM_DIR := ../../helm/charts/shacl
NAMESPACE := iff


lint: pyproject.toml
	$(LINTER)

setup: pyproject.toml
	uv sync

setup-dev: pyproject.toml
	uv sync --dev

test: pyproject.toml
	uv run pytest tests