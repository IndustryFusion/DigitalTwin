#!/usr/bin/env bats
# Copyright (c) 2023 Intel Corporation
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


DB_SERVICE=my-db-service
DB_SERVICE_PORT=5432
DB_SPILO_SELECTOR="application: spilo"
export DB_SERVICE_URL=${DB_SERVICE}:${DB_SERVICE_PORT}


# $1 query
# $2 namespace
# $3 postgres_secret
# $4 database name
# $5 username for access to database
db_query() {
    query=$1
    namespace=$2
    postgres_secret=$3
    database=$4
    username=$5
    password=$(kubectl -n "${namespace}" get secret/"${postgres_secret}" -o jsonpath='{.data.password}'| base64 -d)
    echo  "$query" | \
        PGPASSWORD="${password}" psql -t -h "${DB_SERVICE}" -U "${username}" -d "${database}" -A
}

db_setup_service() {
    # shellcheck disable=SC2153
    cat << EOF  | kubectl -n "${NAMESPACE}" apply -f -
apiVersion: v1
kind: Service
metadata:
  name: ${DB_SERVICE}
spec:
  selector:
    ${DB_SPILO_SELECTOR}
  ports:
    - protocol: TCP
      port: ${DB_SERVICE_PORT}
      targetPort: ${DB_SERVICE_PORT}
EOF
run try "at most 30 times every 5s to find 1 service named '${DB_SERVICE}'"
}

db_delete_service() {
    kubectl -n "${NAMESPACE}" delete svc "${DB_SERVICE}"
}
