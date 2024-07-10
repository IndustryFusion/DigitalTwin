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
. ../.env
. ../helm/env.sh


echo Build DT containers and push to local registry
(cd .. && DOCKER_PREFIX=${LOCAL_REGISTRY}/ibn40 docker-compose build)
(cd .. && DOCKER_PREFIX=${LOCAL_REGISTRY}/ibn40 docker-compose push)

echo Build Scorpio containers
( cd ../.. && rm -rf ScorpioBroker)

if [[ $TEST -eq "true" ]]; then
    ( cd ../.. && git clone https://github.com/IndustryFusion/ScorpioBroker.git)
    ( cd ../../ScorpioBroker && git checkout 68f36d8 ) # Checking out specific commit for CI purposes
    ( cd ../../ScorpioBroker && source /etc/profile.d/maven.sh && mvn clean package -DskipTests -Ddocker -Ddocker-tag=$DOCKER_TAG -Dkafka -Pkafka -Dquarkus.profile=kafka -Dos=java)
else
    ( cd ../.. && git clone https://github.com/IndustryFusion/ScorpioBroker.git )
    ( cd ../../ScorpioBroker && mvn clean package -DskipTests -Pdocker )
fi

docker images | tail -n +2 | awk '{print $1":"$2}'| grep ibn40 | grep -v ${LOCAL_REGISTRY} | grep scorpio | grep ${DOCKER_TAG} |
{
    while read -r i; do
    j=${i//ibn40/${LOCAL_REGISTRY}\/ibn40};
    echo $i --- $j
    docker tag "$i" "$j";
    docker push "$j";
    done
}
