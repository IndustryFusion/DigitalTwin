#!/usr/bin/env bats

DEBUG=${DEBUG:-false} # set this to true to disable starting and stopping of kubefwd
SKIP=
NAMESPACE=iff
USERSECRET=secret/credential-iff-realm-user-iff
USER=realm_user
CLIENT_ID=scorpio
KEYCLOAKURL=http://keycloak.local/auth/realms
SCHEMA=/tmp/schema.json
SCHEMA_IDS=( "https://industry-fusion.org/eclass%230173-1%2301-ACK991%23016"
             "https://industry-fusion.org/eclass%230173-1%2301-AKE795%23017"
             "https://industry-fusion.org/eclass%230173-1%2301-ADN228%23012"
            )
NGSILD_ENTITIES=/tmp/ngsild-objects.json
SUBCOMPONENTS=/tmp/subcomponents.txt
FILTERID=urn:iff:test:filter1
CARTRIDGEID=urn:iff:test:cartridge1
IDENTIFICATIONID=urn:iff:test:identification1
IDENTIFICATIONID2=urn:iff:test:identification2
JSONSCHEMA2OWL=../../../semantic-model/datamodel/tools/jsonschema2owl.js
JSONSCHEMA2SHACL=../../../semantic-model/datamodel/tools/jsonschema2shacl.js
GETSUBCOMPONENTS=../../../semantic-model/datamodel/tools/getSubcomponents.js
CONTEXT=https://industryfusion.github.io/contexts/tutorial/v0.1/context.jsonld
ENTITY_FILE=/tmp/entity.ttl
SHACL_FILE=/tmp/shacl.ttl
cat << 'EOF' > ${SCHEMA}
[
    {
        "$schema":  "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://industry-fusion.org/eclass%230173-1%2301-ACK991%23016",
        "title": "Filter",
        "description": "Schweissrauchabsauger",
        "type": "object",
        "properties": {
           "type": {
            "const": "eclass:0173-1#01-ACK991#016"
            },
            "id": {
              "type": "string",
              "pattern": "^urn:[a-zA-Z0-9][a-zA-Z0-9-]{1,31}:([a-zA-Z0-9()+,.:=@;$_!*'-]|%[0-9a-fA-F]{2})*$"
            }
        },
        "required": ["type", "id"],
        "allOf": [
            {
                "$ref": "https://industry-fusion.org/base-objects/v0.1/machine/properties"
            },
            {
                "$ref": "https://industry-fusion.org/base-objects/v0.1/filter/relationships"
            }
        ]
    },
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://industry-fusion.org/base-objects/v0.1/filter/relationships",
        "title": "IFF template for filter relationship",
        "description": "Filter template for IFF",
        "type": "object",
        "properties": {
            "hasCartridge": {
                "relationship": "eclass:0173-1#01-AKE795#017",
                "relationship_type": "subcomponent",
                "$ref": "https://industry-fusion.org/base-objects/v0.1/link"
            },
            "hasIdentification": {
                "relationship": "eclass:0173-1#01-ADN228#012",
                "relationship_type": "subcomponent",
                "$ref": "https://industry-fusion.org/base-objects/v0.1/link"
            }
        }
    },
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://industry-fusion.org/base-objects/v0.1/machine/properties",
        "title": "Cutter properties",
        "description": "Properties for class cutter",
        "type": "object",
        "properties": {
            "machine_state": {
                "type": "string",
                "title": "Machine Status",
                "description": "Current status of the machine (Online_Idle, Run, Online_Error, Online_Maintenance, Setup, Testing)",
                "enum": [
                    "Online_Idle",
                    "Run",
                    "Online_Error",
                    "Online_Maintenance",
                    "Setup",
                    "Testing"
                ]
            }
        },
        "required": [
            "machine_state"
        ]
    },
    {
        "$schema":  "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://industry-fusion.org/eclass%230173-1%2301-AKE795%23017",
        "title": "Filterpatrone",
        "description": "Filterpatrone",
        "type": "object",
        "properties": {
           "type": {
            "const": "eclass:0173-1#01-AKE795#017"
            },
            "id": {
              "type": "string",
              "pattern": "^urn:[a-zA-Z0-9][a-zA-Z0-9-]{1,31}:([a-zA-Z0-9()+,.:=@;$_!*'-]|%[0-9a-fA-F]{2})*$"
            }
        },
        "required": ["type", "id"],
        "allOf": [
            {
                "$ref": "https://industry-fusion.org/base-objects/v0.1/cartridge/attributes"
            }
        ]
    },
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://industry-fusion.org/base-objects/v0.1/cartridge/attributes",
        "title": "Cartridge attributes",
        "description": "Attributes for class cutter",
        "type": "object",
        "properties": {
            "waste_class": {
                "type": "string",
                "title": "Waste Class",
                "description": "Current wasteclass of the cartridge (WC0, WC1, WC2, WC3)",
                "enum": [
                    "WC0",
                    "WC1",
                    "WC2",
                    "WC3"
                ]
            },
            "hasIdentification": {
                "relationship": "eclass:0173-1#01-ADN228#012",
                "relationship_type": "subcomponent",
                "$ref": "https://industry-fusion.org/base-objects/v0.1/link"
            }
        },
        "required": [
            "waste_class"
        ]
    },
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://industry-fusion.org/base-objects/v0.1/link",
        "title": "IFF template for relationships",
        "description": "Relationship template for IFF",
        "type": "object",
        "properties": {
            "object": {
                "type": "string",
                "pattern": "^urn:[a-zA-Z0-9][a-zA-Z0-9-]{0,31}:[a-zA-Z0-9()+,\\-.:=@;$_!*']*[a-zA-Z0-9()+,\\-.:=@;$_!*']$"
            }
        },
        "required": ["object"]
    },
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://industry-fusion.org/base-objects/v0.1/json-property",
        "title": "IFF template for JSON-properties",
        "description": "JSON-property template for IFF",
        "type": "object",
        "properties": {
            "value": {
                "type": "object",
                "description": "Value field must be present if key ia not a native JSON type.",
                "properties": {
                    "@type": {
                        "type": "string",
                        "const": "@json",
                        "description": "Type of json-property in JSON-LD must be @json"
                    },
                    "@value": {
                        "type": "object",
                        "description": "@value of json-prpoerty must be plain JSON object"
                    }
                },
                "required": ["@type", "@value"]
            }
        }
    },
    {
        "$schema":  "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://industry-fusion.org/eclass%230173-1%2301-ADN228%23012",
        "title": "Filter",
        "description": "Identifikation",
        "type": "object",
        "properties": {
           "type": {
            "const": "eclass:0173-1#01-ADN228#012"
            },
            "id": {
              "type": "string",
              "pattern": "^urn:[a-zA-Z0-9][a-zA-Z0-9-]{1,31}:([a-zA-Z0-9()+,.:=@;$_!*'-]|%[0-9a-fA-F]{2})*$"
            },
            "eclass:0173-1#01-ADN199#011": {
                "$ref": "https://industry-fusion.org/base-objects/v0.1/json-property",
                "description": "eclass JSON object for Supplier",
                "title": "Lieferant"
            },
            "eclass:0173-1#01-ADN198#012": {
                "$ref": "https://industry-fusion.org/base-objects/v0.1/json-property",
                "description": "eclass JSON object for Manufacturer",
                "title": "Hersteller"
            }
        },
        "required": ["type", "id", "eclass:0173-1#01-ADN198#012"]
    }
]
EOF


cat << EOF > ${NGSILD_ENTITIES}
[
    {
        "@context": "${CONTEXT}",
        "id": "${CARTRIDGEID}",
        "type": "eclass:0173-1#01-AKE795#017",
        "hasFilter": {
            "object": "${FILTERID}"
        },
        "waste_class": "WC0",
        "hasIdentification": {
            "object": "${IDENTIFICATIONID}"
        }
    },
    {
        "@context": "${CONTEXT}",
        "id": "${FILTERID}",
        "type": "eclass:0173-1#01-ACK991#016",
        "machine_state": "Testing",
        "hasCartridge": {
            "object": "${CARTRIDGEID}"
        },
        "hasIdentification": {
            "object": "${IDENTIFICATIONID2}"
        }
    },
    {
        "@context": "${CONTEXT}",
        "id": "${IDENTIFICATIONID}",
        "type": "eclass:0173-1#01-ACK991#016",
        "eclass:0173-1#01-ADN199#011": {
            "type": "Property",
            "value": {
                "@value": {"test": "123"},
                "@type": "@json"
            }
        },
        "eclass:0173-1#01-ADN198#012": {
            "type": "Property",
            "value": {
                "@value": {"test2": "1234"},
                "@type": "@json"
            }
        }
    },
    {
        "@context": "${CONTEXT}",
        "id": "${IDENTIFICATIONID2}",
        "type": "eclass:0173-1#01-ACK991#016",
        "eclass:0173-1#01-ADN199#011": {
            "type": "Property",
            "value": {
                "@value": {"test3": "x123"},
                "@type": "@json"
            }
        },
        "eclass:0173-1#01-ADN198#012": {
            "type": "Property",
            "value": {
                "@value": {"test3": "y1234"},
                "@type": "@json"
            }
        }
    }
]
EOF

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
    curl -vv -X POST -H "Authorization: Bearer $1" -d @"$2" http://ngsild.local/ngsi-ld/v1/entityOperations/create -H "Content-Type: application/ld+json"
}


# deletes ngsild entity
# $1: auth token
# $2: id of entity to delete
delete_ngsild() {
    curl -vv -X DELETE -H "Authorization: Bearer $1" http://ngsild.local/ngsi-ld/v1/entities/"$2" -H "Content-Type: application/ld+json"
}

compare_subcomponents() {
    cat << EOF | diff "$1" - >&3
 -d urn:iff:test:cartridge1 -d urn:iff:test:identification1 -d urn:iff:test:identification2
EOF
}


@test "Get subcomponents of hierarchical ngsild-object" {
    $SKIP
    test_file_path="${BATS_TEST_FILENAME}"
    test_directory=$(dirname "$test_file_path")
    cd "$test_directory"
    password=$(get_password)
    token=$(get_token)
    echo "# token: $token"
    delete_ngsild "$token" "$FILTERID" || echo "Could not delete $FILTERID. But that is okay."
    delete_ngsild "$token" "$CARTRIDGEID" || echo "Could not delete $CARTRIDGEID. But that is okay."
    delete_ngsild "$token" "$IDENTIFICATIONID" || echo "Could not delete $IDENTIFICATIONID. But that is okay."
    delete_ngsild "$token" "$IDENTIFICATIONID2" || echo "Could not delete $IDENTIFICATIONID2. But that is okay."
    sleep 2
    create_ngsild "$token" "$NGSILD_ENTITIES"
    for id in "${SCHEMA_IDS[@]}"; do
        node $JSONSCHEMA2OWL -s "${SCHEMA}" -i "$id" -c "$CONTEXT"
    done | sed 's/"/\\"/g' | xargs echo | rdfpipe - > ${ENTITY_FILE}
    for id in "${SCHEMA_IDS[@]}"; do
        node $JSONSCHEMA2SHACL -s "${SCHEMA}" -i "$id" -c "$CONTEXT"
    done | sed 's/"/\\"/g' | xargs echo | rdfpipe - > ${SHACL_FILE}
    node $GETSUBCOMPONENTS -e "$ENTITY_FILE" -s "${SHACL_FILE}" -t "$token" "$FILTERID" > $SUBCOMPONENTS
    run compare_subcomponents "$SUBCOMPONENTS"
    [ "$status" -eq 0 ]
    delete_ngsild "$token" "$FILTERID"
    delete_ngsild "$token" "$CARTRIDGEID"
    delete_ngsild "$token" "$IDENTIFICATIONID"
    delete_ngsild "$token" "$IDENTIFICATIONID2"
}
