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

load "../lib/utils"
load "../lib/detik"
load "../lib/config"
load "../lib/db"
load "../lib/mqtt"
# shellcheck disable=SC2034 # these variables are used by detik
DETIK_CLIENT_NAME="kubectl"
# shellcheck disable=SC2034
DETIK_CLIENT_NAMESPACE="iff"
# shellcheck disable=SC2034
DETIK_DEBUG="true"

DEBUG=${DEBUG:-false}
SKIP=

TEST_DIR="$(dirname "$BATS_TEST_FILENAME")"
CLIENT_ID=scorpio
GATEWAY_ID="testgateway"
DEVICE_ID="urn:iff:testdevice:1"
SUBDEVICE_ID1="urn:iff:testsubdevice:1"
SUBDEVICE_ID2="urn:iff:testsubdevice:2"
SUBDEVICE_IDS='[
  urn:iff:testsubdevice:1,
  urn:iff:testsubdevice:2
]'
VALID_DEVICE_IDS=("urn:iff:device:1" "https://example.org:8080/path?query=1#fragment" "ftp://ftp.example.com/resource.txt" "urn:ifric:ifx-eur-nld-ast-64972453-10a6-561d-a9ec-ef78fc2d5f0a")
INVALID_DEVICE_IDS=("device123" "urn" "http//example.com" "urn:ngsi-ld Device 123")
DEVICE_FILE="device.json"
ONBOARDING_TOKEN="onboard-token.json"
NGSILD_AGENT_DIR=${TEST_DIR}/../../../NgsildAgent
DEVICE_ID2="testdevice2"
SUBDEVICE_ID3="testsubdevice3"
SECRET_FILENAME=/tmp/SECRET
AGENT_CONFIG1=/tmp/AGENT_CONFIG1
AGENT_CONFIG2=/tmp/AGENT_CONFIG2
PROPERTY1="http://example.com/property1"
PROPERTY2="http://example.com/property2"
RELATIONSHIP1="http://example.com/relationship1"
IRI1="http://example.com/iri1"
JSON1="http://example.com/json1"
LIST1="http://example.com/list"
PGREST_URL="http://pgrest.local/attributes"
PGREST_RESULT=/tmp/PGREST_RESULT


cat << EOF > ${AGENT_CONFIG1}
{
        "data_directory": "./data",
        "listeners": {
                "udp_port": 41234,
                "tcp_port": 7070
        },
        "logger": {
                "level": "info",
                "path": "/tmp/",
                "max_size": 134217728
        },
        "dbManager": {
                "file": "metrics.db",
                "retentionInSeconds": 3600,
                "housekeepingIntervalInSeconds": 60,
                "enabled": false
        },
        "connector": {
                "mqtt": {
                        "host": "localhost",
                        "port": 1883,
                        "websockets": false,
                        "qos": 1,
                        "retain": false,
                        "secure": false,
                        "retries": 5,
                        "strictSSL": false,
                        "sparkplugB": true,
                        "version": "spBv1.0"          
                }
        }
}
EOF

cat << EOF > ${AGENT_CONFIG2}
{
        "data_directory": "./data",
        "listeners": {
                "udp_port": 41234,
                "tcp_port": 7070
        },
        "logger": {
                "level": "info",
                "path": "/tmp/",
                "max_size": 134217728
        },
        "dbManager": {
                "file": "metrics.db",
                "retentionInSeconds": 3600,
                "housekeepingIntervalInSeconds": 600,
                "enabled": true
        },
        "connector": {
                "mqtt": {
                        "host": "localhost",
                        "port": 1883,
                        "websockets": false,
                        "qos": 1,
                        "retain": false,
                        "secure": false,
                        "retries": 5,
                        "strictSSL": false,
                        "sparkplugB": true,
                        "version": "spBv1.0"          
                }
        }
}
EOF

check_device_file_contains() {
    deviceid=$(jq '.device_id' "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" | tr -d '"')
    gatewayid=$(jq '.gateway_id' "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" | tr -d '"')
    realmid=$(jq '.realm_id' "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" | tr -d '"')
    keycloakurl=$(jq '.keycloak_url' "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" | tr -d '"')
    [ "$deviceid" = "$1" ] && [ "$gatewayid" = "$2" ] && [ "$realmid" = "$3" ] && [ "$keycloakurl" = "$4" ]
}

check_device_file_contains_with_subcomponents() {
    deviceid=$(jq '.device_id' "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" | tr -d '"')
    gatewayid=$(jq '.gateway_id' "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" | tr -d '"')
    realmid=$(jq '.realm_id' "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" | tr -d '"')
    keycloakurl=$(jq '.keycloak_url' "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" | tr -d '"')
    subdevice_ids=$(jq '.subdevice_ids' "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" | tr -d '"')
    echo "# subdevice_ids $subdevice_ids"
    echo [ "$subdevice_ids" = "$5" ]
    [ "$deviceid" = "$1" ] && [ "$gatewayid" = "$2" ] && [ "$realmid" = "$3" ] && [ "$keycloakurl" = "$4" ] && [ "$subdevice_ids" = "$5" ]
}


init_agent_and_device_file() {
    (rm -f "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}")
    ( { cd "${NGSILD_AGENT_DIR}" && [ -d node_modules ]  && echo "iff-agent already installed"; } || { npm install && echo "iff-agent successfully installed."; } )
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./init-device.sh "${DEVICE_ID}" "${GATEWAY_ID}")
}


init_agent_and_device_file_with_subcomponents() {
    (rm -f "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}")
    ( { cd "${NGSILD_AGENT_DIR}" && [ -d node_modules ]  && echo "iff-agent already installed"; } || { npm install && echo "iff-agent successfully installed."; } )
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./init-device.sh -d "$SUBDEVICE_ID1" -d "$SUBDEVICE_ID2" "${DEVICE_ID}" "${GATEWAY_ID}")
}

delete_tmp() {
  rm -f "${PGREST_RESULT}"
}

get_password() {
    kubectl -n "${NAMESPACE}" get "${USER_SECRET}" -o jsonpath='{.data.password}' | base64 -d
}


check_onboarding_token() {
    access_token=$(jq '.access_token' "${NGSILD_AGENT_DIR}"/data/"${ONBOARDING_TOKEN}" | tr -d '"')
    access_exp=$(echo "$access_token" | tr -d '"' | jq -R 'split(".") | .[1] | @base64d | fromjson| .exp' )
    cur_time=$(date +%s)
    [ "$access_exp" -gt "$cur_time" ]
}

check_device_file_token() {
    device_token=$(jq '.device_token' "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" | tr -d '"')
    device_exp=$(echo "$device_token" | tr -d '"' | jq -R 'split(".") | .[1] | @base64d | fromjson| .exp' )
    cur_time=$(date +%s)
    [ "$device_exp" -gt "$cur_time" ]
}

get_token() {
        curl -XPOST  -d "client_id=${CLIENT_ID}" \
         -d "username=${USER}" \
         -d "password=$1" \
         -d 'grant_type=password' \
         "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" | jq ".access_token"| tr -d '"'
}

get_tsdb_samples() {
    entityId=$1
    limit=$2
    token=$3
    curl -H "Authorization: Bearer $token" "${PGREST_URL}?limit=${limit}&order=observedAt.desc,attributeId.asc&entityId=eq.${entityId}" 2>/dev/null | jq -S 'map(del(.modifiedAt, .observedAt))'
}

# compare entity with reference
# $1: file to compare with
compare_pgrest_result1() {
    number=$1
    cat << EOF | jq | diff "$2" - >&3
[
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "${number}",
    "valueType": null
  }
]
EOF
}

# compare entity with reference
# $1: file to compare with
compare_pgrest_subdevice_result1() {
    number=$1
    cat << EOF | jq | diff "$2" - >&3
[
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testsubdevice:2",
    "id": "urn:iff:testsubdevice:2\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "${number}",
    "valueType": null
  }
]
EOF
}


# compare entity with reference
# $1: file to compare with
compare_pgrest_result2() {
    cat << EOF | jq | diff "$1" - >&3
[
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "1",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/property2",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\7e35d302996f334d94a85448",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "2",
    "valueType": null
  }
]
EOF
}

compare_pgrest_result3() {
    cat << EOF | jq | diff "$1" - >&3
[
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "5",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "3",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/property2",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\7e35d302996f334d94a85448",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "4",
    "valueType": null
  }
]
EOF
}


compare_pgrest_result4() {
    cat << EOF | jq | diff "$1" - >&3
[
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "8",
    "valueType": null
  },

  { 
    "attributeId": "http://example.com/property2",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\7e35d302996f334d94a85448",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "9",
    "valueType": null
  },
  { 
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "6",
    "valueType": null
  },
  { 
    "attributeId": "http://example.com/property2",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\7e35d302996f334d94a85448",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "7",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "4",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/property2",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\7e35d302996f334d94a85448",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "5",
    "valueType": null
  }
]
EOF
}


compare_pgrest_result5() {
    cat << EOF | jq | diff "$1" - >&3
[
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "12",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "10",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/property2",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\7e35d302996f334d94a85448",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "11",
    "valueType": null
  }
]
EOF
}

compare_pgrest_result6() {
    cat << EOF | jq | diff "$1" - >&3
[
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "19",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/property2",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\7e35d302996f334d94a85448",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "16",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "13",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/property2",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\7e35d302996f334d94a85448",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "14",
    "valueType": null
  }
]

EOF
}


compare_pgrest_result7() {
    cat << EOF | jq | diff "$1" - >&3
[ 
  { 
    "attributeId": "http://example.com/relationship1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Relationship",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\76f31d9e7b2f5a2a6b16ca7c",
    "lang": null,
    "nodeType": "@id",
    "parentId": null,
    "unitCode": null,
    "value": "urn:iff:testdevice11",
    "valueType": null
  },
  { 
    "attributeId": "http://example.com/relationship1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Relationship",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\76f31d9e7b2f5a2a6b16ca7c",
    "lang": null,
    "nodeType": "@id",
    "parentId": null,
    "unitCode": null,
    "value": "urn:iff:testdevice10",
    "valueType": null
  },
  { 
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "22",
    "valueType": null
  },
  { 
    "attributeId": "http://example.com/property2",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\7e35d302996f334d94a85448",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "23",
    "valueType": null
  },
  { 
    "attributeId": "http://example.com/relationship1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Relationship",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\76f31d9e7b2f5a2a6b16ca7c",
    "lang": null,
    "nodeType": "@id",
    "parentId": null,
    "unitCode": null,
    "value": "urn:iff:testdevice:8",
    "valueType": null
  },
  { 
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "20",
    "valueType": null
  },
  { 
    "attributeId": "http://example.com/property2",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\7e35d302996f334d94a85448",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "21",
    "valueType": null
  },
  { 
    "attributeId": "http://example.com/relationship1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Relationship",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\76f31d9e7b2f5a2a6b16ca7c",
    "lang": null,
    "nodeType": "@id",
    "parentId": null,
    "unitCode": null,
    "value": "urn:iff:testdevice:9",
    "valueType": null
  }
]
EOF
}


compare_pgrest_result8() {
    cat << EOF | diff "$1" - >&3
[
  {
    "attributeId": "http://example.com/list",
    "attributeType": "https://uri.etsi.org/ngsi-ld/ListProperty",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\ecf0d98b3a1b39a029523c99",
    "lang": null,
    "nodeType": "@list",
    "parentId": null,
    "unitCode": null,
    "value": "[1, 3]",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/json1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/JsonProperty",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\3f25b4d758282cccd5076771",
    "lang": null,
    "nodeType": "@json",
    "parentId": null,
    "unitCode": null,
    "value": "{}",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/iri1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0104891eb4dc7dd71f442037",
    "lang": null,
    "nodeType": "@id",
    "parentId": null,
    "unitCode": null,
    "value": "iri1",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/property1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\0c8a0d568adb7bbf749c6301",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitCode": null,
    "value": "1000",
    "valueType": null
  }
]
EOF
}


compare_pgrest_result9() {
    cat << EOF | jq | diff "$1" - >&3
[
  {
    "attributeId": "http://example.com/list",
    "attributeType": "https://uri.etsi.org/ngsi-ld/ListProperty",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\ecf0d98b3a1b39a029523c99",
    "lang": null,
    "nodeType": "@list",
    "parentId": null,
    "unitCode": null,
    "value": "[1, 3]",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/relationship1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Relationship",
    "datasetId": "urn:iff:index:3",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\af7e1856addfc29682cb4f75",
    "lang": null,
    "nodeType": "@id",
    "parentId": null,
    "unitCode": null,
    "value": "urn:iff:test:1",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/json1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/JsonProperty",
    "datasetId": "urn:iff:index:2",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\8d6ea8004a0ae7f6772458f6",
    "lang": null,
    "nodeType": "@json",
    "parentId": null,
    "unitCode": null,
    "value": "[]",
    "valueType": null
  },
  {
    "attributeId": "http://example.com/iri1",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "urn:iff:index:1",
    "deleted": false,
    "entityId": "urn:iff:testdevice:1",
    "id": "urn:iff:testdevice:1\\\\40ffec13da3c7c85e04edaca",
    "lang": null,
    "nodeType": "@id",
    "parentId": null,
    "unitCode": null,
    "value": "iri2",
    "valueType": null
  }
]
EOF
}


setup() {
    # shellcheck disable=SC2086
    if [ "$DEBUG" != "true" ]; then
        echo "This test works only in debug mode. Set DEBUG=true."
        exit 1
    fi
}


@test "test init_device.sh" {
    $SKIP
    init_agent_and_device_file
    run check_device_file_contains "${DEVICE_ID}" "${GATEWAY_ID}" "${REALM_ID}" "${KEYCLOAK_URL}"
    [ "${status}" -eq "0" ]    
}

@test "test init_device.sh with subcomponents" {
    $SKIP
    init_agent_and_device_file_with_subcomponents
    run check_device_file_contains_with_subcomponents "${DEVICE_ID}" "${GATEWAY_ID}" "${REALM_ID}" "${KEYCLOAK_URL}" "${SUBDEVICE_IDS}"
    [ "${status}" -eq "0" ]    
}

@test "test init_device.sh with deviceid no URN" {
    $SKIP
    (rm -f "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./init-device.sh "${DEVICE_ID2}" "${GATEWAY_ID}" || echo "failed as expected")
    run [ ! -f "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" ]
    [ "${status}" -eq "0" ]    
}

@test "test init_device.sh with subdeviceid no URN" {
    $SKIP
    (rm -f "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./init-device.sh -d "${SUBDEVICE_ID3}" "${DEVICE_ID}" "${GATEWAY_ID}" || echo "failed as expected")
    run [ ! -f "${NGSILD_AGENT_DIR}"/data/"${DEVICE_FILE}" ]
    [ "${status}" -eq "0" ]    
}

@test "test init-device.sh with invalid IRIs for Device ID (not URN/URI)" {
    $SKIP
    for INVALID_DEVICE_ID in "${INVALID_DEVICE_IDS[@]}"; do
      echo "Testing valid ID: $INVALID_DEVICE_ID"
      rm -f "${NGSILD_AGENT_DIR}/data/${DEVICE_FILE}"
      cd "${NGSILD_AGENT_DIR}/util" && run bash ./init-device.sh "$INVALID_DEVICE_ID" "$GATEWAY_ID"
      run [ ! -f "${NGSILD_AGENT_DIR}/data/${DEVICE_FILE}" ]
      [ "$status" -eq 0 ]
    done
}

@test "test init-device.sh with valid IRIs for Device ID (URN & URI)" {
    $SKIP
    for VALID_DEVICE_ID in "${VALID_DEVICE_IDS[@]}"; do
      echo "Testing valid ID: $VALID_DEVICE_ID"
      rm -f "${NGSILD_AGENT_DIR}/data/${DEVICE_FILE}"
      cd "${NGSILD_AGENT_DIR}/util" && run bash ./init-device.sh "$VALID_DEVICE_ID" "$GATEWAY_ID"
      [ "$status" -eq 0 ]
      [ -f "${NGSILD_AGENT_DIR}/data/${DEVICE_FILE}" ]
    done
}

@test "test get-onboarding-token.sh" {
    $SKIP
    init_agent_and_device_file
    password=$(get_password)
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    run check_onboarding_token
    [ "${status}" -eq "0" ]
}

@test "test basic activation" {
    $SKIP
    init_agent_and_device_file
    password=$(get_password)
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    run check_device_file_token
    [ "${status}" -eq "0" ]
}

@test "test activation though k8s" {
    $SKIP
    init_agent_and_device_file
    kubectl -n "${NAMESPACE}" apply -f "${NGSILD_AGENT_DIR}"/util/prepare_device_namespace.yaml
    password=$(get_password)
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" -s "${SECRET_FILENAME}" "${USER}")
    kubectl apply -f "${SECRET_FILENAME}"
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -s)
    run check_device_file_token
    [ "${status}" -eq "0" ]
}

@test "test agent starting up and sending data" {
    $SKIP
    init_agent_and_device_file
    delete_tmp
    mqtt_setup_service
    password=$(get_password)
    token=$(get_token "$password")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    cp "${AGENT_CONFIG1}" "${NGSILD_AGENT_DIR}"/config/config.json
    (cd "${NGSILD_AGENT_DIR}" && exec stdbuf -oL node ./iff-agent.js) &
    sleep 2
    randomnr=$RANDOM
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh "${PROPERTY1}" ${randomnr} )
    sleep 2
    pkill -f iff-agent
    mqtt_delete_service
    get_tsdb_samples "${DEVICE_ID}" 1 "${token}" > ${PGREST_RESULT}
    run compare_pgrest_result1 ${randomnr} ${PGREST_RESULT}
    [ "${status}" -eq "0" ]
}

@test "test agent starting up and sending subcomponent data" {
    $SKIP
    init_agent_and_device_file_with_subcomponents
    delete_tmp
    mqtt_setup_service
    password=$(get_password)
    token=$(get_token "$password")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    cp "${AGENT_CONFIG1}" "${NGSILD_AGENT_DIR}"/config/config.json
    (cd "${NGSILD_AGENT_DIR}" && exec stdbuf -oL node ./iff-agent.js) &
    sleep 2
    randomnr=$RANDOM
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -i ${SUBDEVICE_ID2} "${PROPERTY1}" ${randomnr} )
    sleep 2
    pkill -f iff-agent
    mqtt_delete_service
    rm -f ${PGREST_RESULT}
    get_tsdb_samples "${SUBDEVICE_ID2}" 1 "${token}" > ${PGREST_RESULT}
    run compare_pgrest_subdevice_result1 "${randomnr}" "${PGREST_RESULT}"
    [ "${status}" -eq "0" ]
}

@test "test agent starting up and sending data array" {
    $SKIP
    init_agent_and_device_file
    delete_tmp
    mqtt_setup_service
    password=$(get_password)
    token=$(get_token "$password")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    cp "${AGENT_CONFIG1}" "${NGSILD_AGENT_DIR}"/config/config.json
    (cd "${NGSILD_AGENT_DIR}" && exec stdbuf -oL node ./iff-agent.js) &
    sleep 2
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -a "${PROPERTY1}" 1 "${PROPERTY2}" 2)
    sleep 2
    pkill -f iff-agent
    mqtt_delete_service
    get_tsdb_samples "${DEVICE_ID}" 2 "${token}" > ${PGREST_RESULT}
    run compare_pgrest_result2 ${PGREST_RESULT}
    [ "${status}" -eq "0" ]
}

@test "sending data over tcp" {
    $SKIP
    init_agent_and_device_file
    delete_tmp
    mqtt_setup_service
    password=$(get_password)
    token=$(get_token "$password")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    cp "${AGENT_CONFIG1}" "${NGSILD_AGENT_DIR}"/config/config.json
    (cd "${NGSILD_AGENT_DIR}" && exec stdbuf -oL node ./iff-agent.js) &
    sleep 2
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -at "${PROPERTY1}" 3 "${PROPERTY2}" 4 )
    sleep 1
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t "${PROPERTY1}" 5 )
    sleep 1
    pkill -f iff-agent
    mqtt_delete_service
    get_tsdb_samples "${DEVICE_ID}" 3 "${token}" > ${PGREST_RESULT}
    run compare_pgrest_result3 ${PGREST_RESULT}
    [ "${status}" -eq "0" ]
}

@test "sending data without utils directly to TCP/UDP API" {
    $SKIP
    init_agent_and_device_file
    delete_tmp
    mqtt_setup_service
    password=$(get_password)
    token=$(get_token "$password")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    cp "${AGENT_CONFIG1}" "${NGSILD_AGENT_DIR}"/config/config.json
    (cd "${NGSILD_AGENT_DIR}" && exec stdbuf -oL node ./iff-agent.js) &
    sleep 2
    echo -n '[{"n": "'$PROPERTY1'", "v": "4"},{"n": "'$PROPERTY2'", "v": "5"}]' >/dev/tcp/127.0.0.1/7070
    sleep 1
    echo -n '[{"n": "'$PROPERTY1'", "v": "6"},{"n": "'$PROPERTY2'", "v": "7"}]' >/dev/udp/127.0.0.1/41234
    sleep 1
    echo -n '{"n": "'$PROPERTY1'", "v": "8"}' >/dev/tcp/127.0.0.1/7070
    echo '{"n": "'$PROPERTY2'", "v": "9"}' >/dev/udp/127.0.0.1/41234
    sleep 1
    mqtt_delete_service
    pkill -f iff-agent
    get_tsdb_samples "${DEVICE_ID}" 6 "${token}" > ${PGREST_RESULT}
    run compare_pgrest_result4 ${PGREST_RESULT}
    [ "${status}" -eq "0" ]
}

@test "Test agent reconnects after service interruption" {
    $SKIP
    init_agent_and_device_file
    delete_tmp
    mqtt_setup_service
    password=$(get_password)
    token=$(get_token "$password")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    cp "${AGENT_CONFIG1}" "${NGSILD_AGENT_DIR}"/config/config.json
    (cd "${NGSILD_AGENT_DIR}" && exec stdbuf -oL node ./iff-agent.js) &
    sleep 2
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -at "${PROPERTY1}" 10 "${PROPERTY2}" 11 )
    sleep 1
    mqtt_delete_service 
    sleep 5
    mqtt_setup_service
    sleep 3
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t "${PROPERTY1}" 12 )
    sleep 1
    mqtt_delete_service
    pkill -f iff-agent
    get_tsdb_samples "${DEVICE_ID}" 3 "${token}" > ${PGREST_RESULT}
    run compare_pgrest_result5 ${PGREST_RESULT}
    [ "${status}" -eq "0" ]
}

@test "Test agent reconnects with synchronizing offline storage" {
    $SKIP
    init_agent_and_device_file
    delete_tmp
    mqtt_setup_service
    password=$(get_password)
    token=$(get_token "$password")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    cp "${AGENT_CONFIG2}" "${NGSILD_AGENT_DIR}"/config/config.json
    (cd "${NGSILD_AGENT_DIR}" && exec stdbuf -oL node ./iff-agent.js) &
    sleep 2
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -at "${PROPERTY1}" 13 "${PROPERTY2}" 14 )
    sleep 1
    mqtt_delete_service
    sleep 2
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -at "${PROPERTY1}" 15 "${PROPERTY2}" 16)
    sleep 1
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t "${PROPERTY1}" 17 )
    sleep 1
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t "${PROPERTY1}" 18 )
    mqtt_setup_service
    sleep 2
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t "${PROPERTY1}" 19 )
    sleep 1
    pkill -f iff-agent
    mqtt_delete_service
    get_tsdb_samples "${DEVICE_ID}" 4 "${token}" > ${PGREST_RESULT}
    run compare_pgrest_result6 ${PGREST_RESULT}
    [ "${status}" -eq "0" ]
}

@test "sending relationships and property mixed" {
    $SKIP
    init_agent_and_device_file
    delete_tmp
    mqtt_setup_service
    password=$(get_password)
    token=$(get_token "$password")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    cp "${AGENT_CONFIG1}" "${NGSILD_AGENT_DIR}"/config/config.json
    (cd "${NGSILD_AGENT_DIR}" && exec stdbuf -oL node ./iff-agent.js) &
    sleep 2
    echo -n '[{"n": "'$PROPERTY1'", "v": "20"},{"n": "'$RELATIONSHIP1'", "v": "urn:iff:testdevice:9", "t": "Relationship"}, {"n": "'$PROPERTY2'", "v": "21", "t": "Property"}]' >/dev/tcp/127.0.0.1/7070
    sleep 1
    echo -n '[{"n": "'$PROPERTY1'", "v": "22"},{"n": "'$RELATIONSHIP1'", "v": "urn:iff:testdevice:8", "t": "Relationship"}, {"n": "'$PROPERTY2'", "v": "23", "t": "Property"}]' >/dev/udp/127.0.0.1/41234
    sleep 1
    echo -n '{"n": "'$RELATIONSHIP1'", "v": "urn:iff:testdevice10", "t": "Relationship"}' >/dev/tcp/127.0.0.1/7070
    sleep 1
    echo -n '{"n": "'$RELATIONSHIP1'", "v": "urn:iff:testdevice11", "t": "Relationship"}' >/dev/udp/127.0.0.1/41234
    sleep 1
    pkill -f iff-agent
    mqtt_delete_service
    get_tsdb_samples "${DEVICE_ID}" 8 "${token}" > ${PGREST_RESULT}
    run compare_pgrest_result7 ${PGREST_RESULT}
    [ "${status}" -eq "0" ]
}


@test "sending large array" {
    $SKIP
    init_agent_and_device_file
    delete_tmp
    db_setup_service
    mqtt_setup_service
    password=$(get_password)
    token=$(get_token "$password")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    cp "${AGENT_CONFIG1}" "${NGSILD_AGENT_DIR}"/config/config.json
    (cd "${NGSILD_AGENT_DIR}" && exec stdbuf -oL node ./iff-agent.js) &
    send_array="["
    first=true
    for i in {24..123}; do
      if [ "$first" = "true" ]; then
        first=false
      else
        send_array="${send_array},"
      fi
      send_array="${send_array} {\"n\": \"${PROPERTY1}$i\", \"v\":\"$i\"}"
    done
    send_array="${send_array}]"
    sleep 2 
    echo -n "${send_array}" >/dev/tcp/127.0.0.1/7070
    sleep 1
    pkill -f iff-agent
    mqtt_delete_service
    run try "at most 30 times every 5s to find 1 service named '${DB_SERVICE}'"
    query="SELECT SUM(CAST(value as INTEGER)) AS total FROM (SELECT value FROM ${TSDB_TABLE} where \"entityId\"='${DEVICE_ID}' ORDER BY \"observedAt\" DESC LIMIT 100) AS subquery;"
    result=$(db_query "$query" "$NAMESPACE" "$POSTGRES_SECRET" "$TSDB_DATABASE" "$DBUSER")
    echo db_query "$query" "$NAMESPACE" "$POSTGRES_SECRET" "$TSDB_DATABASE" "$DBUSER"
    [ "$result" = "7350" ] || { echo "wrong aggregator result: $result"; false ; }
    db_delete_service
}
@test "test agent starting up and sending IRIs, JSONs, Lists, and Literals" {
    $SKIP
    init_agent_and_device_file
    delete_tmp
    mqtt_setup_service
    password=$(get_password)
    token=$(get_token "$password")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    cp "${AGENT_CONFIG1}" "${NGSILD_AGENT_DIR}"/config/config.json
    (cd "${NGSILD_AGENT_DIR}" && exec stdbuf -oL node ./iff-agent.js) &
    sleep 2
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t -y Literal "${PROPERTY1}" 1000)
    sleep 1
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t -y Iri "${IRI1}" "iri1")
    sleep 1
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t -y Json "${JSON1}" "{}")
    sleep 1
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t -y List "${LIST1}" "[1, 3]")
    sleep 2
    mqtt_delete_service
    get_tsdb_samples "${DEVICE_ID}" 4 "${token}" > ${PGREST_RESULT}
    pkill -f iff-agent
    run compare_pgrest_result8 ${PGREST_RESULT}
    [ "${status}" -eq "0" ]
}
@test "test agent starting up and sending IRIs, JSONs, Literals, Lists and Relationships with datasetIds" {
    $SKIP
    init_agent_and_device_file
    delete_tmp
    mqtt_setup_service
    password=$(get_password)
    token=$(get_token "$password")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./get-onboarding-token.sh -p "$password" "${USER}")
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./activate.sh -f)
    cp "${AGENT_CONFIG1}" "${NGSILD_AGENT_DIR}"/config/config.json
    (cd "${NGSILD_AGENT_DIR}" && exec stdbuf -oL node ./iff-agent.js) &
    sleep 2
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t -y Literal -d urn:iff:index:0 "${PROPERTY1}" 1001)
    sleep 1
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t -y Iri -d urn:iff:index:1 "${IRI1}" "iri2")
    sleep 1
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t -y Json -d urn:iff:index:2 "${JSON1}" "[]")
    sleep 1
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t -y Relationship -d urn:iff:index:3 "${RELATIONSHIP1}" "urn:iff:test:1")
    sleep 1
    (cd "${NGSILD_AGENT_DIR}"/util && bash ./send_data.sh -t -y List "${LIST1}" "[1, 3]")
    sleep 2
    mqtt_delete_service
    get_tsdb_samples "${DEVICE_ID}" 4 "${token}" > ${PGREST_RESULT}
    pkill -f iff-agent
    run compare_pgrest_result9 ${PGREST_RESULT}
    [ "${status}" -eq "0" ]
}