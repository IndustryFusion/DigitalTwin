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
./helmfile_linux_amd64 -l order=first apply --set "mainRepo=k3d-iff.localhost:12345" )
( cd ./bats && bats test-horizontal-platform/horizontal-platform-up-and-running-first.bats )
        
echo Install second part
( cd ../helm && ./helmfile_linux_amd64 -l order=second apply --set "mainRepo=k3d-iff.localhost:12345" )
( cd ./bats && bats test-horizontal-platform/horizontal-platform-up-and-running-second.bats )

echo Setup Ingress for localhost and install rest of platform
bash ./setup-local-ingress.sh

echo Install the rest
( cd ../helm && ./helmfile_linux_amd64 apply --set "mainRepo=k3d-iff.localhost:12345" )
( cd ./bats && bats test-horizontal-platform/horizontal-platform-up-and-running-rest.bats )

echo Test all together
( cd ./bats && bats ./*.bats )

echo Run all e2e tests
( cd ./bats && bats ./*/*.bats )