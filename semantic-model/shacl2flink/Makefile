SHACL:= ../kms/shacl.ttl
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
COMMON_CONFIG_FILE = ../../helm/common.yaml
ENVIRONMENT_CONFIG_FILE = ../../helm/environment/default.yaml
FUSEKI_HOSTNAME = $$(cat $(ENVIRONMENT_CONFIG_FILE) | yq '.fuseki.externalHostname')
FUSEKI_REALM = $$(cat $(ENVIRONMENT_CONFIG_FILE) | yq '.fuseki.realms[0]')
FUSEKI_CLIENT_ID = fuseki
FUSEKI_CLIENT_SECRET = $$(kubectl -n $(NAMESPACE) get secret/keycloak-client-secret-fuseki -o jsonpath='{.data.CLIENT_SECRET}' | base64 -d)
KEYCLOAK_HOSTNAME = $$(cat $(ENVIRONMENT_CONFIG_FILE) | yq '.keycloak.externalAuthService.domainname')
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

build: $(SHACL) $(KNOWLEDGE $(MODEL)
	@echo Build tables
	$(PYTHON) create_rdf_table.py $(KNOWLEDGE) $(KAFKA_TOPICS)
	$(PYTHON) create_core_tables.py
	${PYTHON} create_udfs.py
	$(PYTHON) create_ngsild_tables.py $(KAFKA_TOPICS)
	$(PYTHON) create_ngsild_models.py $(SHACL) $(KNOWLEDGE) $(MODEL)
	$(PYTHON) create_sql_checks_from_shacl.py $(CHECKPOINTSWITCH) $(NOROCKSDBSWITCH) $(SHACL) $(KNOWLEDGE)

helm: export IFF_HELM=true
helm: build submit-postgres-tables
	mkdir -p ${HELM_DIR}
	rm -rf ${HELM_DIR}/templates 
	cp -rf ${OUTPUTDIR} ${HELM_DIR}/templates
	rm -f ${HELM_DIR}/templates/*.sqlite ${HELM_DIR}/templates/*.postgres ${HELM_DIR}/templates/core.yaml ${HELM_DIR}/templates/knowledge.yaml ${HELM_DIR}/templates/rdf-maps.yaml
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


flink-deploy: clean

	@echo deploy helm package
	make helm
	make disable-strimzi || echo "Can fail"
	# make build || make enable-strimzi
	kubectl -n $(NAMESPACE) delete -f output/ngsild-kafka.yaml --ignore-not-found || make enable-strimzi
	kubectl -n $(NAMESPACE) delete -f output/rdf-kafka.yaml --ignore-not-found || make enable-strimzi
	cd ../../helm && ./helmfile -f helmfile-shacl.yaml apply || make enable-strimzi
	make enable-strimzi
	make test-flink-is-deployed
	sleep 2
	kubectl -n $(NAMESPACE) -l "app.kubernetes.io/instance"="kafka-connect" delete pod
	make fuseki-deploy-kms


flink-undeploy:
	@echo undeploy helm package
	cd ../../helm && ./helmfile -f helmfile-shacl.yaml destroy
	make test-flink-is-undeployed
	cd ../../helm && ./helmfile -f helmfile-shacl.yaml destroy # undeploy a scnd time to make sure that there are no kafkatopics left
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
# bats suite against it, and undeploys again. The KMS in ../kms is never
# touched -- SHACL/KNOWLEDGE/MODEL are overridden for the sub-makes, which
# `make` forwards automatically because they are set on the command line.
#
# Both suites run against the one deployment. test-shacl-flink-e2e drives
# Kafka directly, so a failure there is Flink's or the generated SQL's;
# test-shacl-flink-scorpio-e2e drives the NGSI-LD API and reads Alerta, so a
# failure there is somewhere in Postgres, the bridges or the alert path. Run
# together they say not just "the SQL is right" but "deleting an entity closes
# its alert", which is the property operators depend on.
#
# The teardown must run even when the tests fail, otherwise a red build leaves
# a statementset behind and the next run inherits it.
test-flink-e2e: E2E_KMS := $(CURDIR)/tests/e2e-kms
test-flink-e2e:
	@echo deploy throwaway e2e KMS
	$(MAKE) flink-deploy SHACL=$(E2E_KMS)/shacl.ttl KNOWLEDGE=$(E2E_KMS)/knowledge.ttl \
		MODEL=$(E2E_KMS)/model-instance.jsonld
	ln -fs ../../../../test/bats/lib tests/bats/lib || echo 'Bats framework not installed'
	( cd tests/bats && bats test-shacl-flink-e2e test-shacl-flink-scorpio-e2e ); rc=$$?; \
		rm -f tests/bats/lib; \
		$(MAKE) flink-undeploy SHACL=$(E2E_KMS)/shacl.ttl KNOWLEDGE=$(E2E_KMS)/knowledge.ttl \
			MODEL=$(E2E_KMS)/model-instance.jsonld; \
		exit $$rc


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

fuseki-deploy-kms:
	@echo "Uploading shacl.ttl and knowledge.ttl to Fuseki"
	@REALM=$(FUSEKI_REALM) && \
	SECRET=$(FUSEKI_CLIENT_SECRET) && \
	TOKEN=$$(curl -sf \
	    -d "client_id=$(FUSEKI_CLIENT_ID)" \
	    -d "client_secret=$${SECRET}" \
	    -d "grant_type=client_credentials" \
	    "http://$(KEYCLOAK_HOSTNAME)/auth/realms/$${REALM}/protocol/openid-connect/token" \
	    | jq -r ".access_token") && \
	[ -n "$${TOKEN}" ] && [ "$${TOKEN}" != "null" ] || { echo "ERROR: failed to obtain Fuseki token"; exit 1; } && \
	GSP="http://$(FUSEKI_HOSTNAME)/$${REALM}/data" && \
	GRAPH_BASE="http://$(FUSEKI_HOSTNAME)/$${REALM}" && \
	CODE=$$(curl -s -o /dev/null -w "%{http_code}" \
	    -X PUT -H "Authorization: Bearer $${TOKEN}" -H "Content-Type: text/turtle" \
	    --data-binary @$(SHACL) "$${GSP}?graph=$${GRAPH_BASE}/shacl.ttl") && \
	echo "shacl.ttl → $${CODE}" && \
	{ [ "$${CODE}" = "200" ] || [ "$${CODE}" = "201" ]; } || { echo "ERROR: shacl.ttl upload failed ($${CODE})"; exit 1; } && \
	CODE=$$(curl -s -o /dev/null -w "%{http_code}" \
	    -X PUT -H "Authorization: Bearer $${TOKEN}" -H "Content-Type: text/turtle" \
	    --data-binary @$(KNOWLEDGE) "$${GSP}?graph=$${GRAPH_BASE}/knowledge.ttl") && \
	echo "knowledge.ttl → $${CODE}" && \
	{ [ "$${CODE}" = "200" ] || [ "$${CODE}" = "201" ]; } || { echo "ERROR: knowledge.ttl upload failed ($${CODE})"; exit 1; }


fuseki-undeploy-kms:
	@echo "Removing shacl.ttl and knowledge.ttl from Fuseki"
	@REALM=$(FUSEKI_REALM) && \
	SECRET=$(FUSEKI_CLIENT_SECRET) && \
	TOKEN=$$(curl -sf \
	    -d "client_id=$(FUSEKI_CLIENT_ID)" \
	    -d "client_secret=$${SECRET}" \
	    -d "grant_type=client_credentials" \
	    "http://$(KEYCLOAK_HOSTNAME)/auth/realms/$${REALM}/protocol/openid-connect/token" \
	    | jq -r ".access_token") && \
	[ -n "$${TOKEN}" ] && [ "$${TOKEN}" != "null" ] || { echo "WARNING: could not obtain Fuseki token, skipping KMS undeploy"; exit 0; } && \
	GSP="http://$(FUSEKI_HOSTNAME)/$${REALM}/data" && \
	GRAPH_BASE="http://$(FUSEKI_HOSTNAME)/$${REALM}" && \
	curl -s -o /dev/null -w "shacl.ttl delete: %{http_code}\n" \
	    -X DELETE -H "Authorization: Bearer $${TOKEN}" \
	    "$${GSP}?graph=$${GRAPH_BASE}/shacl.ttl" || true && \
	curl -s -o /dev/null -w "knowledge.ttl delete: %{http_code}\n" \
	    -X DELETE -H "Authorization: Bearer $${TOKEN}" \
	    "$${GSP}?graph=$${GRAPH_BASE}/knowledge.ttl" || true


clean:
	@rm -rf $(OUTPUTDIR)

.PHONY: clean fuseki-deploy-kms fuseki-undeploy-kms test-flink-e2e test-opcua-shapes test-pyshacl-compare
