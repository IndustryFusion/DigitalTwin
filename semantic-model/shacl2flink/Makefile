# The KMS package to build from: kms/default links to the one used when none
# is named (openspec gh-939-kms-package). `make KMS=../kms/<name>` picks another.
KMS ?= ../kms/default
SHACL:= $(KMS)/shacl.ttl
KNOWLEDGE := $(KMS)/knowledge.ttl
MODEL := $(KMS)/model-instance.jsonld
PYTHON := python3
LINTER := flake8
PIP := pip
OUTPUTDIR := output
# A KMS package may hold its knowledge and shapes as one file or as a directory
# of files (contracts/kms-package); shacl2flink reads one file each, so a
# directory is merged first. Not into $(OUTPUTDIR): `make helm` ships that.
# One directory per package, so switching KMS never reuses another package's
# merge.
MERGEDDIR := merged-kms/$(subst /,_,$(abspath $(KMS)))
ifeq ($(wildcard $(KMS)/knowledge.ttl),)
ifneq ($(wildcard $(KMS)/knowledge/*.ttl),)
KNOWLEDGE := $(MERGEDDIR)/knowledge.ttl
endif
endif
ifeq ($(wildcard $(KMS)/shacl.ttl),)
ifneq ($(wildcard $(KMS)/shacl/*.ttl),)
SHACL := $(MERGEDDIR)/shacl.ttl
endif
endif
SQLITEDB := $(OUTPUTDIR)/database.db
SQLITE3 := sqlite3
HELM_DIR := ../../helm/charts/shacl
NAMESPACE := iff
ONTDIR := ../kms/ontology
CHECKPOINT ?= false
# How SPARQL constraints and rules are compiled: classic, one statement per query,
# or ladder (ALPHA), all queries as data for one fixed set of joins. See README.
SPARQL_ENGINE ?= classic
# The shapes of tests/e2e-kms that SPARQL_ENGINE=ladder refuses: its end-to-end
# run deploys the KMS without them (tests/e2e-kms/without_shapes.py).
LADDER_REFUSED_E2E := E2EQueryAnyAttributeShape
COMMON_CONFIG_FILE = ../../helm/common.yaml
ENVIRONMENT_CONFIG_FILE = ../../helm/environment/default.yaml
FUSEKI_HOSTNAME = $$(cat $(ENVIRONMENT_CONFIG_FILE) | yq '.fuseki.externalHostname')
FUSEKI_REALM = $$(cat $(ENVIRONMENT_CONFIG_FILE) | yq '.fuseki.realms[0]')
FLINK_DATABASE = $$(cat $(COMMON_CONFIG_FILE) | yq '.flink.db.name')
FLINK_DATABASE_SERVICE = $$(cat $(COMMON_CONFIG_FILE) | yq '.db.teamId')-$$(cat $(COMMON_CONFIG_FILE) | yq '.db.clusterSvcPostfix')
FLINK_DATABASE_PORT = $$(cat $(COMMON_CONFIG_FILE) | yq '.db.svcPort')
FLINK_DATABASE_USER_NAME = $$(cat $(COMMON_CONFIG_FILE) | yq '.flink.db.writeUser')
FLINK_DATABASE_USER = $$(echo $(FLINK_DATABASE_USER_NAME) | tr '_' '-')

# Conditionally set CHECKPOINTVAR based on CHECKPOINT
ifeq ($(CHECKPOINT), true)
    CHECKPOINTSWITCH = -p
else
    CHECKPOINTSWITCH =
endif

# Conditionally set NOROCKSDBVAR based on NOROCKSDB
ifeq ($(NOROCKSDB), true)
    NOROCKSDBSWITCH = -d
else
    NOROCKSDBSWITCH =
endif

sqlite_files = $(OUTPUTDIR)/core.sqlite $(OUTPUTDIR)/ngsild.sqlite $(OUTPUTDIR)/rdf.sqlite $(OUTPUTDIR)/ngsild-models.sqlite $(OUTPUTDIR)/shacl-validation.sqlite

$(MERGEDDIR)/knowledge.ttl: $(wildcard $(KMS)/knowledge/*.ttl)
	mkdir -p $(MERGEDDIR)
	rdfpipe -i ttl -o ttl $^ > $@.tmp
	mv $@.tmp $@

$(MERGEDDIR)/shacl.ttl: $(wildcard $(KMS)/shacl/*.ttl)
	mkdir -p $(MERGEDDIR)
	rdfpipe -i ttl -o ttl $^ > $@.tmp
	mv $@.tmp $@

build: $(SHACL) $(KNOWLEDGE) $(MODEL)
	@echo Build tables
	$(PYTHON) create_rdf_table.py $(KNOWLEDGE) $(KAFKA_TOPICS)
	$(PYTHON) create_core_tables.py
	${PYTHON} create_udfs.py
	$(PYTHON) create_ngsild_tables.py $(KAFKA_TOPICS)
	$(PYTHON) create_ngsild_models.py $(SHACL) $(KNOWLEDGE) $(MODEL)
	$(PYTHON) create_sql_checks_from_shacl.py $(CHECKPOINTSWITCH) $(NOROCKSDBSWITCH) --sparql-engine $(SPARQL_ENGINE) $(SHACL) $(KNOWLEDGE)

# Which SPARQL expressions of the package cannot be compiled, and why, without a build.
check-queries: $(SHACL)
	$(PYTHON) check_queries.py $(SHACL)

# Builds the chart. The tables are written by the deploy, and only when it
# replaces the validation (deploy_validation.sh, #1165): written under a
# running job, change data capture would hand it every row once more.
helm: export IFF_HELM=true
helm: build
	mkdir -p ${HELM_DIR}
	rm -rf ${HELM_DIR}/templates 
	cp -rf ${OUTPUTDIR} ${HELM_DIR}/templates
	rm -f ${HELM_DIR}/templates/*.sqlite ${HELM_DIR}/templates/*.postgres ${HELM_DIR}/templates/*.txt ${HELM_DIR}/templates/core.yaml ${HELM_DIR}/templates/knowledge.yaml ${HELM_DIR}/templates/rdf-maps.yaml
	rm -f ${HELM_DIR}/templates/shacl-constraints*.yaml
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

# update-rdf-cm: delete-rdf-cm
# 	kubectl -n $(NAMESPACE) create -f output/rdf-maps.yaml
# 	rm -f ${HELM_DIR}/templates/rdf-maps.yaml

#  delete-rdf-cm:
# 	kubectl -n $(NAMESPACE) delete configmap -l "shacl-data"="rdf-configmap"


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


# Compile every shape the OPC UA generator emits. The kms-constraints fixtures
# cover its patterns with real data; this covers its actual output, so a
# generator that starts emitting something untranslatable fails here rather
# than the next time somebody tries it by hand.
# Validate every kms fixture with pyshacl as well and compare. The fixtures say
# what we EXPECTED; only an independent implementation can say what SHACL
# REQUIRES. Needs the fixture outputs, so it runs them with DEBUG=true first --
# that is what keeps the per-model testout files instead of deleting them.
test-pyshacl-compare:
	@echo Compare kms fixture results against pyshacl
	cd tests/sql-tests && DEBUG=true bash tests.sh > /dev/null 2>&1 || true
	cd tests/sql-tests && $(PYTHON) ../pyshacl-compare/compare.py .


test-opcua-shapes:
	@echo Compile the shapes emitted by the opcua generator
	cd tests/opcua-shapes && bash test.sh


disable-strimzi:
	kubectl -n $(NAMESPACE) scale deployment -l "strimzi.io/name=my-cluster-entity-operator" --replicas=0


enable-strimzi:
	kubectl -n $(NAMESPACE) scale deployment -l "strimzi.io/name=my-cluster-entity-operator" --replicas=1


# Deploys the package, fresh or over a running validation (#1165,
# specification shacl2flink/validation-deployment): the same package over the
# running job writes nothing and keeps the job; anything else replaces the
# validation through `make shacl-resync REPLACE=package`, with deploy-install
# as its install. See deploy_validation.sh.
flink-deploy: clean
	@echo deploy helm package
	make helm
	NAMESPACE=$(NAMESPACE) ./deploy_validation.sh
	make test-flink-is-deployed

# The install of a new package, run by the resync while no validation job
# reads the tables: the tables, then the release. The KafkaTopic resources are
# deleted while Strimzi's entity operator is held back, so that the topics
# themselves stay; `sync` recreates the statementset the resync's stop
# deleted, also when the chart is unchanged.
deploy-install:
	make submit-postgres-tables
	make disable-strimzi || echo "Can fail"
	kubectl -n $(NAMESPACE) delete -f output/ngsild-kafka.yaml --ignore-not-found || { make enable-strimzi; exit 1; }
	kubectl -n $(NAMESPACE) delete -f output/rdf-kafka.yaml --ignore-not-found || { make enable-strimzi; exit 1; }
	cd ../../helm && ./helmfile -f helmfile-shacl.yaml sync || { make enable-strimzi; exit 1; }
	make enable-strimzi


# Publish all existing entities again (a Debezium re-snapshot) once the
# deployed validation reads them, so that it validates them. Fails, and leaves
# Kafka Connect alone, when the validation doesn't run in time
# (VALIDATION_START_TIMEOUT, seconds).
restart-connect:
	NAMESPACE=$(NAMESPACE) ./restart_connect.sh


# Bring the SHACL alerts in Alerta in line with what the deployed validation
# finds now (shacl_resync.sh): mark the validation degraded, with REPLACE=fresh
# stop its job and empty the topics it reads back, close the SHACL alerts,
# reset Core Services, start the job again, re-snapshot, wait until that is
# processed and end the degraded state. REPLACE=checkpoint RESTORE_FROM=<path>
# is refused until the statementset can start from a checkpoint (#1042). Needs
# no KMS: it works on the deployed statementset. REPLACE=package, the
# replacement by a new package, is run by `make flink-deploy`, which passes
# the install of the package (#1165).
REPLACE ?= none
RESTORE_FROM ?=
# The resync works on the deployed package. A KMS= on its command line would
# suggest it switches to that package, which it doesn't: it refuses (#1195).
shacl-resync:
	@if [ "$(origin KMS)" = "command line" ]; then \
		echo "shacl-resync works on the deployed package and takes no KMS. To deploy another package: make flink-deploy KMS=$(KMS)" >&2; \
		exit 2; \
	fi
	NAMESPACE=$(NAMESPACE) REPLACE=$(REPLACE) RESTORE_FROM=$(RESTORE_FROM) ./shacl_resync.sh


flink-undeploy:
	@echo undeploy helm package
	# A validation deployed before #1038 declares the platform's entity topic
	# without keep, and destroying it would delete the topic: refuse instead.
	cd ../../helm && bash ./check-release-keeps-topics.sh $(NAMESPACE) shacl iff.ngsild.entities
	cd ../../helm && ./helmfile -f helmfile-shacl.yaml destroy
	make test-flink-is-undeployed
	cd ../../helm && ./helmfile -f helmfile-shacl.yaml destroy # undeploy a scnd time to make sure that there are no kafkatopics left
	# No fingerprint is left for an undeployed validation (#1165).
	kubectl -n $(NAMESPACE) delete configmap shacl-validation-fingerprint --ignore-not-found
	make fuseki-undeploy-kms


test-flink-is-deployed:
	ln -fs ../../../../test/bats/lib tests/bats/lib || echo 'Bats framework not installed'
	cd tests/bats && bats test-shacl-flink-deployment
	rm tests/bats/lib


test-full-flink-deployment:
	@echo test deployment of helm package
	make helm
	make flink-deploy
	make flink-undeploy


# End-to-end test of the compiled pipeline against a live Flink.
#
# A standard platform install deploys NO shacl-validation, so this target owns
# the whole lifecycle: it compiles and deploys its own throwaway KMS, runs the
# bats suites against it, and undeploys again. The KMS in $(KMS) is never
# touched -- SHACL/KNOWLEDGE/MODEL are overridden for the sub-makes, which
# `make` forwards automatically because they are set on the command line.
#
# test-flink-deploy-e2e runs test-shacl-flink-deploy alone, on a platform
# with no validation deployed: an entity created before the first deployment
# must be validated after it, and so must the entities after a deployment over
# the running validation (#1114, #1165). It deploys seven times, about an hour,
# so it is a CI shard of its own (flink-deploy, #1202).
#
# test-flink-e2e deploys the KMS once and runs the other suites against it.
# test-shacl-flink-e2e drives Kafka directly, so a failure there is Flink's or
# the generated SQL's; test-shacl-flink-scorpio-e2e drives the NGSI-LD API and
# reads Alerta, so a failure there is somewhere in Postgres, the bridges or
# the alert path. Run together they say not just "the SQL is right" but
# "deleting an entity closes its alert", which is the property operators
# depend on.
#
# test-shacl-flink-resync runs last: it runs `make shacl-resync` without and
# with REPLACE=fresh against the same deployment and checks the alerts after
# each, and leaves the deployment for the teardown.
#
# The teardown of both must run even when the tests fail, otherwise a red
# build leaves a statementset behind and the next run inherits it.
#
# With SPARQL_ENGINE=ladder (alpha) test-flink-e2e deploys the same KMS
# without the shapes the ladder refuses; the suites skip what those raise, and
# test-shacl-flink-ladder checks that the job runs the ladder, joined as often
# as the build says.
E2E_KMS = $(if $(filter ladder,$(SPARQL_ENGINE)),$(CURDIR)/e2e-kms-ladder,$(CURDIR)/tests/e2e-kms)
E2E_KMS_VARS = SHACL=$(E2E_KMS)/shacl.ttl KNOWLEDGE=$(E2E_KMS)/knowledge.ttl MODEL=$(E2E_KMS)/model-instance.jsonld

test-flink-e2e: export SPARQL_ENGINE := $(SPARQL_ENGINE)
test-flink-e2e:
	@echo deploy throwaway e2e KMS, SPARQL_ENGINE=$(SPARQL_ENGINE)
ifeq ($(SPARQL_ENGINE),ladder)
	$(PYTHON) tests/e2e-kms/without_shapes.py tests/e2e-kms $(E2E_KMS) $(LADDER_REFUSED_E2E)
endif
	$(MAKE) flink-deploy $(E2E_KMS_VARS); rc=$$?; \
		if [ $$rc -eq 0 ]; then \
			ln -fs ../../../../test/bats/lib tests/bats/lib || echo 'Bats framework not installed'; \
			( cd tests/bats && bats test-shacl-flink-ladder test-shacl-flink-e2e test-shacl-flink-scorpio-e2e \
				test-shacl-flink-resync ) || rc=1; \
			echo "the platform watchdog with the validation deployed"; \
			VALIDATION_DEPLOYED=true bats $(CURDIR)/../../test/bats/test-jobs/platform-watchdog.bats || rc=1; \
			rm -f tests/bats/lib; \
		fi; \
		$(MAKE) flink-undeploy $(E2E_KMS_VARS); \
		exit $$rc

test-flink-deploy-e2e:
	( cd tests/bats && bats test-shacl-flink-deploy ); rc=$$?; \
		$(MAKE) flink-undeploy $(E2E_KMS_VARS); \
		exit $$rc


test-flink-is-undeployed:
	@echo test undeployment of helm package
	ln -fs ../../../../test/bats/lib tests/bats/lib || echo 'Bats framework not installed'
	cd tests/bats && bats test-shacl-flink-undeploy
	rm tests/bats/lib

prepare-kms:
ifdef KMS_DIR
	@echo copy kms values from $(KMS_DIR) into $(KMS)
	cd ../kms && cp $(KMS_DIR)/* $(abspath $(KMS))/
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
	/bin/bash -O extglob -c 'echo creating knowledge.ttl with $${ontpattern} $(ONTDIR)/!(*_shacl.ttl|*.html|*.jsonld|*.txt); rdfpipe -i ttl -o ttl $${ontpattern} $(ONTDIR)/!(*_shacl.ttl|*.html|*.jsonld|*.txt) > $(KMS)/knowledge.ttl'; \
	echo creating shacl.ttl with $${shaclpattern}; rdfpipe -i ttl -o ttl $${shaclpattern} > $(KMS)/shacl.ttl

# start-database-service:
# 	POD=$$(kubectl -n $(NAMESPACE) get ep $(FLINK_DATABASE_SERVICE)   -o jsonpath='{.subsets[0].addresses[0].targetRef.name}') && \
# 	kubectl -n $(NAMESPACE) port-forward pod/$${POD} $(FLINK_DATABASE_PORT):$(FLINK_DATABASE_PORT) &

# stop-database-service:
# 	killall -9 kubectl >/dev/null 2>&1 || echo "No database service found to stop"

submit-postgres-tables:
	@echo Create RDF table in database
	@FLINK_USER_SECRET=$$(kubectl -n $(NAMESPACE) get secrets | grep $(FLINK_DATABASE_USER) | cut -d " " -f 1) && \
	echo usersecret $${FLINK_USER_SECRET} from $(FLINK_DATABASE_USER) which is transformed from $(FLINK_DATABASE_USER_NAME) && \
	PGPASSWORD=$$(kubectl -n $(NAMESPACE) get secret $${FLINK_USER_SECRET} -o go-template='{{index .data "password" | base64decode}}') && \
	POD=$$(kubectl -n $(NAMESPACE) get ep $(FLINK_DATABASE_SERVICE) -o jsonpath='{.subsets[0].addresses[0].targetRef.name}') && \
	kubectl -n $(NAMESPACE) exec -i $${POD} -- bash -c "PGPASSWORD='$${PGPASSWORD}' PGSSLMODE=require psql -h localhost -U $(FLINK_DATABASE_USER_NAME) -d $(FLINK_DATABASE)" < $(OUTPUTDIR)/rdf.postgres && \
	kubectl -n $(NAMESPACE) exec -i $${POD} -- bash -c "PGPASSWORD='$${PGPASSWORD}' PGSSLMODE=require psql -h localhost -U $(FLINK_DATABASE_USER_NAME) -d $(FLINK_DATABASE)" < $(OUTPUTDIR)/ngsild.postgres && \
	kubectl -n $(NAMESPACE) exec -i $${POD} -- bash -c "PGPASSWORD='$${PGPASSWORD}' PGSSLMODE=require psql -h localhost -U $(FLINK_DATABASE_USER_NAME) -d $(FLINK_DATABASE)" < $(OUTPUTDIR)/shacl-constraints.postgres

# The KMS graphs go to Fuseki through the cluster (a port-forward to its
# service), as the SQL goes to Flink and the tables to Postgres: no ingress,
# no token. The graphs keep their names under the external hostname.
fuseki-deploy-kms: $(SHACL) $(KNOWLEDGE)
	@echo "Uploading shacl.ttl and knowledge.ttl to Fuseki"
	@REALM=$(FUSEKI_REALM) && \
	./fuseki_kms.sh deploy $(NAMESPACE) $${REALM} "http://$(FUSEKI_HOSTNAME)/$${REALM}" $(SHACL) $(KNOWLEDGE)


fuseki-undeploy-kms:
	@echo "Removing shacl.ttl and knowledge.ttl from Fuseki"
	@REALM=$(FUSEKI_REALM) && \
	./fuseki_kms.sh undeploy $(NAMESPACE) $${REALM} "http://$(FUSEKI_HOSTNAME)/$${REALM}" || \
	echo "WARNING: the KMS graphs could not be removed from Fuseki"


clean:
	@rm -rf $(OUTPUTDIR) merged-kms

.PHONY: clean restart-connect deploy-install shacl-resync fuseki-deploy-kms fuseki-undeploy-kms test-flink-e2e test-flink-deploy-e2e test-opcua-shapes test-pyshacl-compare
