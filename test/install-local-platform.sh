#!/bin/bash
# Copyright (c) 2022 Intel Corporation
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
set -e

echo Install operators
( cd ../helm && bash ./install_operators.sh )

echo Test whether operators are coming up
( cd ./bats && bats test-operators/*.bats )

echo Install first two parts of horizontal platform
( cd ../helm && echo Install first part &&
./helmfile -l order=first apply --set "mainRepo=k3d-iff.localhost:12345" )
( cd ./bats && bats test-jobs/keycloak-realm-import-job-is-up.bats )
# Increase backoff limit for realm import job, unfortunately, right now,
# keycloak operator does not reset the job if backoff limit is exceeded,
# this behavior will probably be fixed in the future
kubectl -n iff patch job iff-keycloak-realm-import -p '{"spec":{"backoffLimit":60}}'
( cd ./bats && bats test-horizontal-platform/horizontal-platform-up-and-running-first.bats )
        
echo Install second part
( cd ../helm && ./helmfile -l order=second apply --set "mainRepo=k3d-iff.localhost:12345" )
( cd ./bats && bats test-horizontal-platform/horizontal-platform-up-and-running-second.bats )

echo Setup Ingress for localhost
bash ./setup-local-ingress.sh

echo Install third part
( cd ../helm && ./helmfile -l order=third apply --set "mainRepo=k3d-iff.localhost:12345" )
( cd ./bats && bats test-horizontal-platform/horizontal-platform-up-and-running-third.bats )

echo Install the rest
( cd ../helm && ./helmfile apply --set "mainRepo=k3d-iff.localhost:12345" )
( cd ./bats && bats test-horizontal-platform/horizontal-platform-up-and-running-velero.bats )

echo Test all together
( cd ./bats && bats ./*.bats )

echo Run all e2e tests
( cd ./bats && bats ./*/*.bats )