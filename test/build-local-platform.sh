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
. ../.env
. ../helm/env.sh


echo Build DT containers and push to local registry
(cd .. && DOCKER_PREFIX=${LOCAL_REGISTRY}/ibn40 docker-compose build)
(cd .. && DOCKER_PREFIX=${LOCAL_REGISTRY}/ibn40 docker-compose push)

echo Build Scorpio containers
( cd ../.. && rm -rf ScorpioBroker)

# Scorpio is built from one pinned commit of the IndustryFusion fork (branch scorpio-v6.0.2): the fork's patches
# on upstream 6.0.2.
SCORPIO_COMMIT=505690906dfc080cee831c3819ad44f82b4d5f33
( cd ../.. && git clone https://github.com/IndustryFusion/ScorpioBroker.git )
( cd ../../ScorpioBroker && git checkout -q "$SCORPIO_COMMIT" ) || exit 1
# 6.0.2 needs JDK 21 and Maven 3.9: they come from a container, so the build needs Docker only.
# The Maven repository is the host's (~/.m2), with its settings.xml (a proxy) when there is one.
mkdir -p "$HOME/.m2"
MVN_SETTINGS=()
[ -f "$HOME/.m2/settings.xml" ] && MVN_SETTINGS=(-s /m2/settings.xml)
( cd ../../ScorpioBroker && docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e MAVEN_CONFIG=/tmp/.m2 -v "$PWD:/src" -v "$HOME/.m2:/m2" -w /src \
    maven:3.9-eclipse-temurin-21 mvn -B -Duser.name=scorpio -Dmaven.repo.local=/m2/repository "${MVN_SETTINGS[@]}" clean package -DskipTests \
    -Dkafka -Pkafka -Dquarkus.profile=kafka -pl AllInOneRunner -am ) || exit 1
( cd ../../ScorpioBroker && docker build -f AllInOneRunner/src/main/docker/Dockerfile.jvm \
    -t "ibn40/scorpio-all-in-one-runner:$DOCKER_TAG" AllInOneRunner ) || exit 1

# Fetch Docker images, filter them, and process accordingly
docker images --format "{{.Repository}}:{{.Tag}}" | \
    grep scorpio | \
    grep ibn40 | \
    grep "${DOCKER_TAG}" | \
    grep -v "${LOCAL_REGISTRY}" | \
    while read -r image; do
        # Debug: Display the current image being processed
        echo "Processing image: $image"

        # Extract the image path starting from 'ibn40/'
        # This handles both 'ibn40/...' and 'scorpiobroker/ibn40/...'
        image_path=$(echo "$image" | sed -n 's|.*\(ibn40/.*\)|\1|p')

        # Check if the image_path was successfully extracted
        if [ -z "$image_path" ]; then
            echo "Skipping image '$image' as it does not match expected patterns."
            continue
        fi

        # Construct the new image name by prefixing with LOCAL_REGISTRY
        new_image="${LOCAL_REGISTRY}/${image_path}"

        # Display the tagging and pushing action
        echo "Tagging and pushing: $image -> $new_image"

        # Tag the image
        docker tag "$image" "$new_image"
        if [ $? -ne 0 ]; then
            echo "Error: Failed to tag image '$image'. Skipping..."
            continue
        fi

        # Push the new image to the local registry
        docker push "$new_image"
        if [ $? -ne 0 ]; then
            echo "Error: Failed to push image '$new_image'. Skipping..."
            continue
        fi

        echo "Successfully tagged and pushed: $new_image"
    done
