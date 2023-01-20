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
TEST="true"

echo Build DT containers and push to local registry
(cd .. && DOCKER_PREFIX=k3d-iff.localhost:12345 docker-compose build)
(cd .. && DOCKER_PREFIX=k3d-iff.localhost:12345 docker-compose push)

echo Build Scorpio containers
( cd ../.. && rm -rf ScorpioBroker)

if [[ $TEST -eq "true" ]]; then
    ( cd ../.. && git clone https://github.com/IndustryFusion/ScorpioBroker.git)
    ( cd ../../ScorpioBroker && git checkout ScorpioDigitalTwin )
    ( cd ../../ScorpioBroker && source /etc/profile.d/maven.sh && mvn clean package -DskipTests -Ddocker -Din-memory -Pin-memory -Dquarkus.profile=in-memory -Dos=java)
else
    ( cd ../.. && git clone https://github.com/IndustryFusion/ScorpioBroker.git )
    ( cd ../../ScorpioBroker && mvn clean package -DskipTests -Pdocker )
fi
docker images | tail -n +2 | awk '{print $1":"$2}'| grep ibn40 |
{
    while read -r i; do
    j=${i//ibn40/k3d-iff.localhost:12345};
    docker tag "$i" "$j";
    docker push "$j";
    done
}
