#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi
DEBUG=${DEBUG:-false} # set this to true to disable starting and stopping of kubefwd
SKIP=
NAMESPACE=iff
USERSECRET=secret/credential-iff-realm-user-iff
USER=realm_user
CLIENT_ID=scorpio
KEYCLOAKURL=http://keycloak.local/auth/realms
CUTTER=/tmp/CUTTER
CUTTER_TIMESTAMPED=/tmp/CUTTER_TIMESTAMPED
CUTTER_SUBATTRIBUTES=/tmp/CUTTER_SUBATTRIBUTES
GEOCUTTER_ATTRIBUTES=/tmp/GEOCUTTER_ATTRIBUTES
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
KAFKACAT_ATTRIBUTES=/tmp/KAFKACAT_ATTRIBUTES
KAFKACAT_ATTRIBUTES_SORTED=/tmp/KAFKACAT_ATTRIBUTES_SORTED
KAFKACAT_ATTRIBUTES_TOPIC=iff.ngsild.attributes
KAFKACAT_ENTITY_PLASMACUTTER=/tmp/KAFKACAT_ENTITY_PLASMACUTTER
KAFKACAT_ENTITY_PLASMACUTTER_SORTED=/tmp/KAFKACAT_ENTITY_PLASMACUTTER_SORTED
KAFKACAT_ENTITY_PLASMACUTTER_NAME=plasmacutter_test
KAFKACAT_ENTITY_PLASMACUTTER_TOPIC=iff.ngsild.entities
PLASMACUTTER_ID=urn:plasmacutter-test:12345
GEOCUTTER_ID=urn:geocutter-test:12345
cat << EOF > ${CUTTER}
{
    "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld",
    "id": "${PLASMACUTTER_ID}",
    "type": "https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}",
    "https://industry-fusion.com/types/v0.9/state": [
        {
            "type": "Property",
            "value": "ON"
        },
        {
            "type": "Property",
            "value": "OFF"
        }
    ],
    "https://industry-fusion.com/types/v0.9/hasWorkpiece": [
        {
            "type": "Relationship",
            "object": "urn:workpiece-test:12345",
            "datasetId": "urn:workpiece-test:12345-ZZZ"
        },
        {
            "type": "Relationship",
            "object": "urn:workpiece-test:23456"
        }
    ],
    "https://industry-fusion.com/types/v0.9/hasFilter": {
      "type": "Relationship",
      "object": "urn:filter-test:12345"
    },
    "https://industry-fusion.com/types/v0.9/jsonValue": {
        "type": "JsonProperty",
        "json": {"my": "json"}
    },
    "https://industry-fusion.com/types/v0.9/jsonValueArray": [
        {
            "type": "JsonProperty",
            "json": {
                "my": "json1"
            },
            "datasetId": "urn:json-value-test:json1"
        },
        {
            "type": "JsonProperty",
            "json": {"my": "json2"}
        }
    ],
    "https://industry-fusion.com/types/v0.9/multiState": [
        {
            "type": "Property",
            "value": "OFF",
            "datasetId": "urn:multistate-test:off"
        },
        {
            "type": "Property",
            "value": {
                "@value": "ON",
                "type": "https://industry-fusion.com/types/v0.9/multiStateType"
            }
        }
    ],
    "https://industry-fusion.com/types/v0.9/list": {
        "type": "ListProperty",
        "valueList": [1, 2, 3]
    }
}
EOF

cat << EOF > ${CUTTER_TIMESTAMPED}
{
    "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
    "id": "${PLASMACUTTER_ID}",
    "type": "https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}",
    "https://industry-fusion.com/types/v0.9/state": [
        {
            "type": "Property",
            "value": "OFF",
            "observedAt": "2023-01-08T01:11:35.99Z"
        },
        {
            "type": "Property",
            "value": "ON",
            "datasetId": "urn:state-test:on",
            "observedAt": "2023-01-08T01:10:35.555Z"
        }
    ],
    "https://industry-fusion.com/types/v0.9/hasWorkpiece": [
        {
            "type": "Relationship",
            "object": "urn:workpiece-test:12345",
            "observedAt": "2023-05-19T01:19:35Z"
        }
    ],
    "https://industry-fusion.com/types/v0.9/hasFilter": {
      "type": "Relationship",
      "object": "urn:filter-test:12345",
      "observedAt": "2023-01-08T01:11:35.100Z"
    }
}
EOF


cat << EOF > ${CUTTER_SUBATTRIBUTES}
{
    "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
    "id": "${PLASMACUTTER_ID}",
    "type": "https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}",
    "https://industry-fusion.com/types/v0.9/state": [
        {
            "type": "Property",
            "value": "ON",
            "datasetId": "urn:state_on",
            "http://example.com/subattribute": {
                "type": "Property",
                "value": "OFF"
            }
        },
        {
            "type": "Property",
            "value": "OFF",
            "datasetId": "urn:state_off",
            "http://example.com/subattribute2": [{
                "type": "Relationship",
                "object": "urn:test:1"
            },

            {
                "type": "Relationship",
                "object": "urn:test:2",
                "datasetId": "urn:datasetId:1"
            }],
            "http://example.com/subattribute3": [{
                "type": "JsonProperty",
                "json": {"my": "test"}
            }],
            "http://example.com/subattribute4": [{
                "type": "ListProperty",
                "valueList": [1, 3, 2]
            }]
        },
        {
            "type": "Property",
            "value": "ONN",
            "datasetId": "2urn:state_on",
               "http://example.com/subattribute": [{
                "type": "Relationship",
                "object": "urn:test:1",
                "http://example.com/subattribute3": [{
                    "type": "Relationship",
                    "object": "urn:test:2"
                }]
            }]
        },
        {
            "type": "Property",
            "value": "MAYBE"
        },
        {
            "type": "Property",
            "value": "OFFOFF",
            "datasetId": "+=-urn:state_off"
        }
    ]
}
EOF

cat << EOF > ${GEOCUTTER_ATTRIBUTES}
{
    "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
    "id": "${GEOCUTTER_ID}",
    "type": "https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}",
    "https://uri.etsi.org/ngsi-ld/location": [
        {
            "type": "GeoProperty",
            "unitCode": "MTR",
            "value": {
                "type": "Point",
                "coordinates": [13.3698, 52.5163]
            },
            "datasetId": "urn:state_on"
        },
        {
            "type": "GeoProperty",
              "value": {
                "type": "Point",
                "coordinates": [-10.12, 5.5163]
            }
        }
    ],
    "relativeOperationalSpace": {
            "type": "GeoProperty",
            "unitCode": "MTR",
            "crs": "local",
            "value": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-10.0, -10.0],
                        [10.0, -10.0],
                        [10.0, 10.0],
                        [-10.0, 10.0],
                        [-10.0, -10.0]
                    ]
                ]
            }
    }
}
EOF

compare_create_attributes_timestamps() {
    cat << EOF | diff "$1" - >&3
1673140235555
1673140295100
1673140295990
1684459175000
EOF
}

compare_create_attributes() {
    cat << EOF | diff "$1" - >&3
{"attributeValue":"urn:filter-test:12345","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\715fe7eb6833a04d08b433d3","name":"https://industry-fusion.com/types/v0.9/hasFilter","nodeType":"@id","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Relationship"}
{"attributeValue":"urn:workpiece-test:23456","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\6114697c79dec3f570cd2d19","name":"https://industry-fusion.com/types/v0.9/hasWorkpiece","nodeType":"@id","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Relationship"}
{"attributeValue":"urn:workpiece-test:12345","datasetId":"urn:workpiece-test:12345-ZZZ","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\882d5719144799b508cc9140","name":"https://industry-fusion.com/types/v0.9/hasWorkpiece","nodeType":"@id","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Relationship"}
{"attributeValue":"{\"my\":\"json2\"}","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\1f19b4954c2fa90c9c5aab69","name":"https://industry-fusion.com/types/v0.9/jsonValueArray","nodeType":"@json","synced":true,"type":"https://uri.etsi.org/ngsi-ld/JsonProperty"}
{"attributeValue":"{\"my\":\"json1\"}","datasetId":"urn:json-value-test:json1","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\2d82376db95502ccb2d95c08","name":"https://industry-fusion.com/types/v0.9/jsonValueArray","nodeType":"@json","synced":true,"type":"https://uri.etsi.org/ngsi-ld/JsonProperty"}
{"attributeValue":"{\"my\":\"json\"}","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\22feacb2a08bb41caebdb141","name":"https://industry-fusion.com/types/v0.9/jsonValue","nodeType":"@json","synced":true,"type":"https://uri.etsi.org/ngsi-ld/JsonProperty"}
{"attributeValue":"[1,2,3]","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\4a4625cc698675e31907afa3","name":"https://industry-fusion.com/types/v0.9/list","nodeType":"@list","synced":true,"type":"https://uri.etsi.org/ngsi-ld/JsonProperty"}
{"attributeValue":"ON","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\4bf8a2c53e468ed60ad7ac44","name":"https://industry-fusion.com/types/v0.9/multiState","nodeType":"@value","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Property","valueType":"https://industry-fusion.com/types/v0.9/multiStateType"}
{"attributeValue":"OFF","datasetId":"urn:multistate-test:off","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\670a3d03d2f519573f495af1","name":"https://industry-fusion.com/types/v0.9/multiState","nodeType":"@value","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Property"}
{"attributeValue":"OFF","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\6e27e969d7144bb8bcc17e7a","name":"https://industry-fusion.com/types/v0.9/state","nodeType":"@value","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Property"}
EOF
}

compare_delete_attributes() {
    cat << EOF | diff "$1" - >&3
{"id":"urn:plasmacutter-test:12345\\\\1f19b4954c2fa90c9c5aab69","name":"https://industry-fusion.com/types/v0.9/jsonValueArray","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/JsonProperty","datasetId":"@none","nodeType":"@json","deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\22feacb2a08bb41caebdb141","name":"https://industry-fusion.com/types/v0.9/jsonValue","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/JsonProperty","datasetId":"@none","nodeType":"@json","deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\2d82376db95502ccb2d95c08","name":"https://industry-fusion.com/types/v0.9/jsonValueArray","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/JsonProperty","datasetId":"urn:json-value-test:json1","nodeType":"@json","deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\4a4625cc698675e31907afa3","name":"https://industry-fusion.com/types/v0.9/list","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/JsonProperty","datasetId":"@none","nodeType":"@list","deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\4bf8a2c53e468ed60ad7ac44","name":"https://industry-fusion.com/types/v0.9/multiState","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Property","datasetId":"@none","nodeType":"@value","deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\6114697c79dec3f570cd2d19","name":"https://industry-fusion.com/types/v0.9/hasWorkpiece","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Relationship","datasetId":"@none","nodeType":"@id","deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\670a3d03d2f519573f495af1","name":"https://industry-fusion.com/types/v0.9/multiState","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Property","datasetId":"urn:multistate-test:off","nodeType":"@value","deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\6e27e969d7144bb8bcc17e7a","name":"https://industry-fusion.com/types/v0.9/state","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Property","datasetId":"@none","nodeType":"@value","deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\715fe7eb6833a04d08b433d3","name":"https://industry-fusion.com/types/v0.9/hasFilter","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Relationship","datasetId":"@none","nodeType":"@id","deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\882d5719144799b508cc9140","name":"https://industry-fusion.com/types/v0.9/hasWorkpiece","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Relationship","datasetId":"urn:workpiece-test:12345-ZZZ","nodeType":"@id","deleted":true,"synced":true}
EOF
}

compare_create_plasmacutter() {
    cat << EOF | jq -S | diff "$1" - >&3
{"id":"${PLASMACUTTER_ID}","type":"https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}"}
EOF
}

compare_delete_plasmacutter() {
    cat << EOF | jq -S | diff "$1" - >&3
{"id":"${PLASMACUTTER_ID}","type": "https://industry-fusion.com/types/v0.9/plasmacutter_test","deleted":true}
EOF
}


compare_subattributes() {
    cat << EOF | diff "$1" - >&3
{"attributeValue":"urn:test:1","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\86969620a799025bec62d30e","name":"http://example.com/subattribute2","nodeType":"@id","parentId":"urn:plasmacutter-test:12345\\\\436a09c26ec3fb1a252c6384","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Relationship"}
{"attributeValue":"urn:test:2","datasetId":"urn:datasetId:1","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\0b73df883eb95ade589bdeee","name":"http://example.com/subattribute2","nodeType":"@id","parentId":"urn:plasmacutter-test:12345\\\\436a09c26ec3fb1a252c6384","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Relationship"}
{"attributeValue":"urn:test:2","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\c8ef580afbbaa9bd5e47bdf5","name":"http://example.com/subattribute3","nodeType":"@id","parentId":"urn:plasmacutter-test:12345\\\\19c5c3a1ca609f3fa8dd16b0","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Relationship"}
{"attributeValue":"{\"my\":\"test\"}","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\164d54900d7c3c5c1612d46e","name":"http://example.com/subattribute3","nodeType":"@json","parentId":"urn:plasmacutter-test:12345\\\\436a09c26ec3fb1a252c6384","synced":true,"type":"https://uri.etsi.org/ngsi-ld/JsonProperty"}
{"attributeValue":"[1,3,2]","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\ba7f1e39e6e86d5e3295d1d0","name":"http://example.com/subattribute4","nodeType":"@list","parentId":"urn:plasmacutter-test:12345\\\\436a09c26ec3fb1a252c6384","synced":true,"type":"https://uri.etsi.org/ngsi-ld/JsonProperty"}
{"attributeValue":"OFF","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\54a9f45fb3f6a5bb00820d12","name":"http://example.com/subattribute","nodeType":"@value","parentId":"urn:plasmacutter-test:12345\\\\0688fd1bed196dfd63ebce11","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Property"}
{"attributeValue":"urn:test:1","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\19c5c3a1ca609f3fa8dd16b0","name":"http://example.com/subattribute","nodeType":"@id","parentId":"urn:plasmacutter-test:12345\\\\6d9c2cd02173db637f0e3885","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Relationship"}
{"attributeValue":"ONN","datasetId":"2urn:state_on","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\6d9c2cd02173db637f0e3885","name":"https://industry-fusion.com/types/v0.9/state","nodeType":"@value","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Property"}
{"attributeValue":"MAYBE","datasetId":"@none","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\6e27e969d7144bb8bcc17e7a","name":"https://industry-fusion.com/types/v0.9/state","nodeType":"@value","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Property"}
{"attributeValue":"OFF","datasetId":"urn:state_off","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\436a09c26ec3fb1a252c6384","name":"https://industry-fusion.com/types/v0.9/state","nodeType":"@value","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Property"}
{"attributeValue":"OFFOFF","datasetId":"+=-urn:state_off","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\822584b81b5e26be88a16ebd","name":"https://industry-fusion.com/types/v0.9/state","nodeType":"@value","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Property"}
{"attributeValue":"ON","datasetId":"urn:state_on","entityId":"urn:plasmacutter-test:12345","id":"urn:plasmacutter-test:12345\\\\0688fd1bed196dfd63ebce11","name":"https://industry-fusion.com/types/v0.9/state","nodeType":"@value","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Property"}
EOF
}

compare_geoattributes() {
    cat << EOF | diff "$1" - >&3
{"attributeValue":"local","datasetId":"@none","entityId":"urn:geocutter-test:12345","id":"urn:geocutter-test:12345\\\\0f4aacc220af630349e4f439","name":"https://uri.etsi.org/ngsi-ld/default-context/crs","nodeType":"@value","parentId":"urn:geocutter-test:12345\\\\7b1e3d672b471e5711346193","synced":true,"type":"https://uri.etsi.org/ngsi-ld/Property"}
{"attributeValue":"{\"@type\":[\"https://purl.org/geojson/vocab#Polygon\"],\"https://purl.org/geojson/vocab#coordinates\":[{\"@list\":[{\"@list\":[{\"@list\":[{\"@value\":-10},{\"@value\":-10}]},{\"@list\":[{\"@value\":10},{\"@value\":-10}]},{\"@list\":[{\"@value\":10},{\"@value\":10}]},{\"@list\":[{\"@value\":-10},{\"@value\":10}]},{\"@list\":[{\"@value\":-10},{\"@value\":-10}]}]}]}]}","datasetId":"@none","entityId":"urn:geocutter-test:12345","id":"urn:geocutter-test:12345\\\\7b1e3d672b471e5711346193","name":"https://uri.etsi.org/ngsi-ld/default-context/relativeOperationalSpace","nodeType":"@json","synced":true,"type":"https://uri.etsi.org/ngsi-ld/GeoProperty","unitCode":"MTR","valueType":"https://purl.org/geojson/vocab#Polygon"}
{"attributeValue":"{\"@type\":[\"https://purl.org/geojson/vocab#Point\"],\"https://purl.org/geojson/vocab#coordinates\":[{\"@list\":[{\"@value\":-10.12},{\"@value\":5.5163}]}]}","datasetId":"@none","entityId":"urn:geocutter-test:12345","id":"urn:geocutter-test:12345\\\\af65fbaf9b16ce7e4077e96b","name":"https://uri.etsi.org/ngsi-ld/location","nodeType":"@json","synced":true,"type":"https://uri.etsi.org/ngsi-ld/GeoProperty","valueType":"https://purl.org/geojson/vocab#Point"}
{"attributeValue":"{\"@type\":[\"https://purl.org/geojson/vocab#Point\"],\"https://purl.org/geojson/vocab#coordinates\":[{\"@list\":[{\"@value\":13.3698},{\"@value\":52.5163}]}]}","datasetId":"urn:state_on","entityId":"urn:geocutter-test:12345","id":"urn:geocutter-test:12345\\\\630176de6aa43b22b8e89219","name":"https://uri.etsi.org/ngsi-ld/location","nodeType":"@json","synced":true,"type":"https://uri.etsi.org/ngsi-ld/GeoProperty","unitCode":"MTR","valueType":"https://purl.org/geojson/vocab#Point"}
EOF
}

get_password() {
    kubectl -n ${NAMESPACE} get ${USERSECRET} -o jsonpath='{.data.password}'| base64 -d
}
get_token() {
    curl -d "client_id=${CLIENT_ID}" -d "username=${USER}" -d "password=$password" -d 'grant_type=password' "${KEYCLOAKURL}/${NAMESPACE}/protocol/openid-connect/token"| jq ".access_token"| tr -d '"'
}

# create ngsild entity
# $1: auth token
# $2: filename which contains entity to create
create_ngsild() {
    curl -vv -X POST -H "Authorization: Bearer $1" -d @"$2" http://ngsild.local/ngsi-ld/v1/entities/ -H "Content-Type: application/ld+json"
}


# deletes ngsild entity
# $1: auth token
# $2: id of entity to delete
delete_ngsild() {
    curl -vv -X DELETE -H "Authorization: Bearer $1" http://ngsild.local/ngsi-ld/v1/entities/"$2" -H "Content-Type: application/ld+json"
}

setup() {
    # shellcheck disable=SC2086
    [ $DEBUG = "true" ] || (exec ${SUDO} kubefwd -n iff -l app.kubernetes.io/name=kafka svc) &
    echo "# launched kubefwd for kafka, wait some seconds to give kubefwd to launch the services"
    sleep 3
    echo "# create needed kafka topics to make sure that consumers will not fail first time"
    echo "--------------------------New Test------------------" | kafkacat -P -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP}
    echo "--------------------------New Test------------------" | kafkacat -P -t ${KAFKACAT_ENTITY_PLASMACUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP}
}
teardown(){
    echo "# now killing kubefwd"
    # shellcheck disable=SC2086
    [ $DEBUG = "true" ] || ${SUDO} killall kubefwd
}


@test "verify debezium bridge sends updates to attributes and entities topics when entity is created" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    echo "# token: $token"
    delete_ngsild "$token" "$PLASMACUTTER_ID" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ENTITY_PLASMACUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ENTITY_PLASMACUTTER}) &
    echo "# launched kafkacat for debezium updates, wait some time to let it connect"
    sleep 2
    create_ngsild "$token" "$CUTTER"
    echo "# Sent ngsild updates, sleep 5s to let debezium bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    jq -S < ${KAFKACAT_ENTITY_PLASMACUTTER} > ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    jq -c 'to_entries | sort_by(.key) | from_entries' ${KAFKACAT_ATTRIBUTES} > ${KAFKACAT_ATTRIBUTES_SORTED}
    echo "# Compare ATTRIBUTES"
    run compare_create_attributes ${KAFKACAT_ATTRIBUTES_SORTED}
    [ "$status" -eq 0 ]

    echo "# Compare PLASMACUTTER Entity"
    run compare_create_plasmacutter ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    [ "$status" -eq 0 ]
}

@test "verify debezium bridge sends updates to attributes and entity topics when entity is deleted" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    create_ngsild "$token" "$CUTTER" || echo "Could not creatattributee $PLASMACUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ENTITY_PLASMACUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ENTITY_PLASMACUTTER}) &
    echo "# launched kafkacat for debezium updates, wait some time to let it connect"
    sleep 2
    delete_ngsild "$token" "$PLASMACUTTER_ID"
    echo "# Sent ngsild updates, sleep 5s to let debezium bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    sleep 2
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    jq -S < ${KAFKACAT_ENTITY_PLASMACUTTER} > ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    run compare_delete_attributes ${KAFKACAT_ATTRIBUTES}
    [ "$status" -eq 0 ]

    run compare_delete_plasmacutter ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    [ "$status" -eq 0 ]
}

@test "verify debezium bridge sends updates to attributes with correct Kafka timestamps" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    echo "# token: $token"
    delete_ngsild "$token" "$PLASMACUTTER_ID" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -f '%T\n' -o end >${KAFKACAT_ATTRIBUTES}) &
    echo "# launched kafkacat for debezium updates, wait some time to let it connect"
    sleep 2
    create_ngsild "$token" "$CUTTER_TIMESTAMPED"
    echo "# Sent ngsild updates, sleep 5s to let debezium bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    jq -S < ${KAFKACAT_ENTITY_PLASMACUTTER} > ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    echo "# Compare ATTRIBUTES"
    run compare_create_attributes_timestamps ${KAFKACAT_ATTRIBUTES}
    [ "$status" -eq 0 ]

}

@test "verify debezium bridge sends subattributes" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    delete_ngsild "$token" "$PLASMACUTTER_ID" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    echo "# launched kafkacat for debezium updates, wait some time to let it connect"
    sleep 2
    create_ngsild "$token" "$CUTTER_SUBATTRIBUTES"
    echo "# Sent ngsild updates, sleep 5s to let debezium bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    jq -c 'to_entries | sort_by(.key) | from_entries' ${KAFKACAT_ATTRIBUTES} > ${KAFKACAT_ATTRIBUTES_SORTED}
    echo "# Compare ATTRIBUTES"
    run compare_subattributes ${KAFKACAT_ATTRIBUTES_SORTED}
    [ "$status" -eq 0 ]
}

@test "verify debezium bridge sends geoattributes" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    delete_ngsild "$token" "$GEOCUTTER_ID" || echo "Could not delete $GEOCUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    echo "# launched kafkacat for debezium updates, wait some time to let it connect"
    sleep 2
    create_ngsild "$token" "$GEOCUTTER_ATTRIBUTES"
    echo "# Sent ngsild updates, sleep 5s to let debezium bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    jq -c 'to_entries | sort_by(.key) | from_entries' ${KAFKACAT_ATTRIBUTES} > ${KAFKACAT_ATTRIBUTES_SORTED}
    echo "# Compare ATTRIBUTES"
    run compare_geoattributes ${KAFKACAT_ATTRIBUTES_SORTED}
    [ "$status" -eq 0 ]
}