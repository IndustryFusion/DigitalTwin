SHACL:= ../kms/shacl.ttl
SHACL_NORMALIZED := ../kms/shacl_normalized.ttl
KNOWLEDGE := ../kms/knowledge.ttl
MODEL := ../kms/model-instance.jsonld
PYTHON := python3
LINTER := flake8
PIP := pip
OUTPUTDIR := output
SQLITEDB := $(OUTPUTDIR)/database.db
SQLITE3 := sqlite3
HELM_DIR := ../../helm/charts/shacl
NAMESPACE := iff
ONTDIR := ../kms/ontology
CHECKPOINT ?= false

# Conditionally set CHECKPOINTVAR based on CHECKPOINT
ifeq ($(CHECKPOINT), true)
    CHECKPOINTSWITCH = -p
else
    CHECKPOINTSWITCH =
endif

sqlite_files = $(OUTPUTDIR)/core.sqlite $(OUTPUTDIR)/ngsild.sqlite $(OUTPUTDIR)/rdf.sqlite $(OUTPUTDIR)/ngsild-models.sqlite $(OUTPUTDIR)/shacl-validation.sqlite

build: $(SHACL) $(KNOWLEDGE $(MODEL)
	@echo Build tables
	$(PYTHON) create_rdf_table.py $(KNOWLEDGE) $(KAFKA_TOPICS)
	$(PYTHON) create_core_tables.py
	${PYTHON} create_udfs.py
	$(PYTHON) create_ngsild_tables.py $(KAFKA_TOPICS)
	$(PYTHON) create_ngsild_models.py $(SHACL) $(KNOWLEDGE) $(MODEL)
	$(PYTHON) shacl_normalization.py $(SHACL) $(SHACL_NORMALIZED)
	$(PYTHON) create_sql_checks_from_shacl.py $(CHECKPOINTSWITCH) $(SHACL_NORMALIZED) $(KNOWLEDGE)

helm: export IFF_HELM=true
helm: build
	mkdir -p ${HELM_DIR}
	rm -rf ${HELM_DIR}/templates 
	cp -rf ${OUTPUTDIR} ${HELM_DIR}/templates
	rm -f ${HELM_DIR}/templates/*.sqlite ${HELM_DIR}/templates/core.yaml ${HELM_DIR}/templates/knowledge.yaml ${HELM_DIR}/templates/rdf-maps.yaml
	cp Chart.yaml ${HELM_DIR}

test: requirements-dev.txt
	$(PYTHON) -m pytest --cov . --cov-fail-under=80

lint: requirements-dev.txt
	$(LINTER)

setup: requirements.txt setup-dev
	$(PIP) install -r requirements.txt
	echo ".headers on" > ~/.sqliterc
	echo ".mode column" >> ~/.sqliterc
	echo ".load /usr/lib/sqlite3/pcre2.so" >> ~/.sqliterc

update-rdf-cm: delete-rdf-cm
	kubectl -n $(NAMESPACE) create -f output/rdf-maps.yaml
	rm -f ${HELM_DIR}/templates/rdf-maps.yaml

 delete-rdf-cm:
	kubectl -n $(NAMESPACE) delete configmap -l "shacl-data"="rdf-configmap"


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


test-sqlite-udf:
	@echo Test with sqlite
	for file in $(sqlite_files); do \
		${PYTHON} udf/sqlite3_insert.py $(SQLITEDB) $${file};\
	done
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


disable-strimzi:
	kubectl -n $(NAMESPACE) scale deployment -l "strimzi.io/name=my-cluster-entity-operator" --replicas=0


enable-strimzi:
	kubectl -n $(NAMESPACE) scale deployment -l "strimzi.io/name=my-cluster-entity-operator" --replicas=1


flink-deploy: clean
	@echo deploy helm package
	make helm
	make update-rdf-cm
	make disable-strimzi || echo "Can fail"
	# make build || make enable-strimzi
	kubectl -n $(NAMESPACE) delete -f output/ngsild-kafka.yaml --ignore-not-found || make enable-strimzi
	kubectl -n $(NAMESPACE) delete -f output/rdf-kafka.yaml --ignore-not-found || make enable-strimzi
	cd ../../helm && ./helmfile -f helmfile-shacl.yaml apply || make enable-strimzi
	make enable-strimzi
	make test-flink-is-deployed
	sleep 2
	kubectl -n $(NAMESPACE) -l "app.kubernetes.io/instance"="kafka-connect" delete pod


flink-undeploy: delete-rdf-cm
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

prepare-kms:
ifdef KMS_DIR
	@echo copy kms values from $(KMS_DIR)
	cd ../kms && cp $(KMS_DIR)/* .
else
	@echo No KMS_DIR defined, doing nothing
endif


ontology2kms:
	BASEURI=$$(cat ../../helm/common.yaml | yq '.ontology.baseUri') && \
		if [ -z "$(ONTDEBUG)" ]; then rm -rf $(ONTDIR); wget -r --no-parent  --directory-prefix=$(ONTDIR) -nd -A ttl,jsonld $${BASEURI}; else \
		echo Not updating local ontolgoy directory; fi
	@for ontology in $(ONTOLOGIES) base; do \
		echo "Processing $${ontology}"; \
		entitiesfile=$(ONTDIR)/$${ontology}_entities.ttl; \
		knowledgefile=$(ONTDIR)/$${ontology}_knowledge.ttl; \
		shaclfile=$(ONTDIR)/$${ontology}_shacl.ttl; \
		if [ -f "$${entitiesfile}" ]; then ontpattern=$${ontpattern}" $${entitiesfile}"; fi; \
		if [ -f "$${knowledgefile}" ]; then ontpattern=$${ontpattern}" $${knowledgefile}"; fi; \
		if [ -f "$${shaclfile}" ]; then shaclpattern=$${shaclpattern}" $${shaclfile}"; fi; \
	done; \
	/bin/bash -O extglob -c 'echo creating knowledge.ttl with $${ontpattern} $(ONTDIR)/!(*_shacl.ttl|*.html|*.jsonld|*.txt); rdfpipe -i ttl -o ttl $${ontpattern} $(ONTDIR)/!(*_shacl.ttl|*.html|*.jsonld|*.txt) > ../kms/knowledge.ttl'; \
	echo creating shacl.ttl with $${shaclpattern}; rdfpipe -i ttl -o ttl $${shaclpattern} > ../kms/shacl.ttl

clean:
	@rm -rf $(OUTPUTDIR)

.PHONY: clean
