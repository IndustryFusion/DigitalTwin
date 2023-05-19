SHACL:= ../kms/shacl.ttl
KNOWLEDGE := ../kms/knowledge.ttl
MODEL := ../kms/model-example.jsonld
PYTHON := python3
LINTER := $(HOME)/.local/bin/flake8
PIP := pip
OUTPUTDIR := output
SQLITEDB := $(OUTPUTDIR)/database.db
SQLITE3 := sqlite3
HELM_DIR := ../../helm/charts/shacl
NAMESPACE := iff


sqlite_files = $(OUTPUTDIR)/core.sqlite $(OUTPUTDIR)/ngsild.sqlite $(OUTPUTDIR)/rdf.sqlite $(OUTPUTDIR)/ngsild-models.sqlite $(OUTPUTDIR)/shacl-validation.sqlite

build: $(SHACL) $(KNOWLEDGE $(MODEL)
	@echo Build tables
	$(PYTHON) create_rdf_table.py $(KNOWLEDGE)
	$(PYTHON) create_core_tables.py
	$(PYTHON) create_ngsild_tables.py $(SHACL)
	$(PYTHON) create_ngsild_models.py $(SHACL) $(KNOWLEDGE) $(MODEL)
	$(PYTHON) create_sql_checks_from_shacl.py $(SHACL) $(KNOWLEDGE)

helm: export IFF_HELM=true
helm: build
	mkdir -p ${HELM_DIR}
	rm -rf ${HELM_DIR}/templates 
	mv ${OUTPUTDIR} ${HELM_DIR}/templates
	rm -f ${HELM_DIR}/templates/*.sqlite ${HELM_DIR}/templates/core.yaml
	cp Chart.yaml ${HELM_DIR}

test: requirements-dev.txt
	$(PYTHON) -m pytest --cov . --cov-fail-under=80

lint: requirements-dev.txt
	$(LINTER)

setup: requirements.txt setup-dev
	$(PIP) install -r requirements.txt
	echo ".headers on" > ~/.sqliterc
	echo ".mode column" >> ~/.sqliterc
	echo ".load /usr/lib/sqlite3/pcre.so" >> ~/.sqliterc



setup-dev: requirements-dev.txt
	$(PIP) install -r requirements-dev.txt

test-sqlite:
	@echo Test with sqlite
	cat $(sqlite_files) | $(SQLITE3) $(SQLITEDB)
	echo "Alerts"
	echo ------------------------------------------------
	echo 'select * from alerts_bulk;'| sqlite3 ${SQLITEDB}
	echo "Inserts"
	echo ------------------------------------------------
	echo "select * from attributes_insert_filter;"| sqlite3 ${SQLITEDB}

test-sqlite-update:
	@echo Update model
	$(PYTHON) create_ngsild_models.py $(SHACL) $(KNOWLEDGE) $(MODEL)
	cat $(OUTPUTDIR)/ngsild-models.sqlite | $(SQLITE3) $(SQLITEDB)
	sleep 1
	cat $(OUTPUTDIR)/shacl-validation.sqlite | $(SQLITE3) $(SQLITEDB)

test-kms:
	@echo Test different kms setups
	cd tests/sql-tests && bash tests.sh

flink-deploy: clean
	@echo deploy helm package
	make helm
	cd ../../helm && ./helmfile -f helmfile-shacl.yaml apply
	make test-flink-is-deployed
	sleep 2
	kubectl -n $(NAMESPACE) -l "app.kubernetes.io/instance"="kafka-connect" delete pod

flink-undeploy:
	@echo undeploy helm package
	cd ../../helm && ./helmfile -f helmfile-shacl.yaml destroy
	make test-flink-is-undeployed
	cd ../../helm && ./helmfile -f helmfile-shacl.yaml destroy # undeploy a scnd time to make sure that there are no kafkatopics left


test-flink-is-deployed:
	ln -fs ../../../../test/bats/lib tests/bats/lib || echo 'Bats framework not installed'
	cd tests/bats && bats test-shacl-flink-deployment
	rm tests/bats/lib

test-full-flink-deployment:
	@echo test deployment of helm package
	make helm
	make flink-deploy
	make flink-undeploy

test-flink-is-undeployed:
	@echo test undeployment of helm package
	ln -fs ../../../../test/bats/lib tests/bats/lib || echo 'Bats framework not installed'
	cd tests/bats && bats test-shacl-flink-undeploy
	rm tests/bats/lib

clean:
	@rm -rf $(OUTPUTDIR)

.PHONY: clean