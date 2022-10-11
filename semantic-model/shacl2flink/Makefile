SHACL:= ../kms/shacl.ttl
KNOWLEDGE := ../kms/knowledge.ttl
MODEL := ../kms/example-model.ttl
PYTHON := python3
LINTER := flake8
PIP := pip
OUTPUTDIR := output
SQLITEDB := $(OUTPUTDIR)/database.db
SQLITE3 := sqlite3

sqlite_scripts = $(wildcard $(OUTPUTDIR)/*.sqlite)

build: $(SHACL) $(KNOWLEDGE $(MODEL)
	@echo Build tables
	$(PYTHON) create_rdf_table.py $(KNOWLEDGE)

test: requirements-dev.txt
	$(PYTHON) -m pytest --cov . --cov-fail-under=80

lint: requirements-dev.txt
	$(LINTER)

setup: requirements.txt setup-dev
	$(PIP) install -r requirements.txt

setup-dev: requirements-dev.txt
	$(PIP) install -r requirements-dev.txt

test-sqlite:
	@echo Test with sqlite
	$(SQLITE3) $(SQLITEDB) < $(sqlite_scripts) 