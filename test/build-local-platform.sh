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
    ( cd ../../ScorpioBroker && git checkout a49ce4e ) # Checking out specific commit for CI purposes
    ( cd ../../ScorpioBroker && source /etc/profile.d/maven.sh && mvn clean package -DskipTests -Ddocker -Ddocker-tag=$DOCKER_TAG -Dkafka -Pkafka -Dquarkus.profile=kafka)
else
    ( cd ../.. && git clone https://github.com/IndustryFusion/ScorpioBroker.git )
    ( cd ../../ScorpioBroker && mvn clean package -DskipTests -Pdocker )
fi

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
