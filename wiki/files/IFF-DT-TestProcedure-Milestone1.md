# Industry Fusion-Digital Twin | Milestone 1 | Feature Test Procedure

This document covers the test procedure for the features developed in Milestone 1.

- RBAC support in Context broker
- Relay context updates to Kafka

**Context Broker:**

The context broker application adapted is Scorpio. It is Fiware GE and NGSI-LD compliant. Scorpio broker is microservice compliant and is implemented in Spring Boot. Scorpio broker has all the NGSI-LD APIs implemented in its microservices - Entity Manager, Subscription Manager, Context Registry Manager, History Manager. The services exchange data over Apache Kafka. Persistence support is provided by Postgres. Scorpio is compliant with microservices patterns using the Spring Cloud framework: Eureka for Service Discovery, Zuul for API Gateway, etc.

Scorpio is licensed under BSD-3 Clause.

**Prerequisites to test the features:**

- Docker images for Scorpio and Debezium service pushed to the private container registry (ibn40/digitaltwin), version of images is 2.0.0.
- Scorpio components deployed via K8s/Docker-compose.
- Scorpio's Platform services: Apache Kafka with Kafka Connect, Kafka Connector, PostgreSQL, Keycloak.
- REST client tools to test the APIs: curl/Postman, etc.

**RBAC support in Context broker**

The objective of this feature is to test RBAC support on Scorpio. RBAC support on Scorpio has been provided by integrating Scorpio with Keycloak, an identity management tool. The creation of the necessary objects on Keycloak: Clients, Roles, Users, etc. is done manually since tenant/user management isn't under the current scope of work.

**Configuration:**

Keycloak Configuration Steps:

1. Realm: Realm is tenant profile within Keycloak. _Create a Realm._
2. Role: A role includes the permissions to be given to the resources/APIs. _Create the roles: Factory-Admin, Factory-Editor, Factory-Writer, Reader, Subscriber._
3. Client: A client is the entity that connects with Keycloak to serve its APIs to end users. Clients establish their trust with Keycloak using Client ID and Client Secret. _Create clients for each of the Scorpio microservices: Entity Manager, Query Manager, Subscription Manager, History Manager and Registry Manager._
4. User: End user who requests the context broker resources. _Create users as needed._
5. Map the clients and roles to associate the relevant roles to the services within the context broker and associate the users with their roles.

**Test Procedure:**

Each client has roles corresponding to their NGSI-LD protected APIs and have something called client secret, which we need to get the access token.

1. Getting access token from Keycloak:

	HTTP Verb: `POST`
	URL: `http://<Keycloak IP Address>:<Port>/auth/realms/<realm-name>/protocol/openid-connect/token`

	In the body, specify the below `x-www-form-urlencoded` data as key values:

	- grant_type: `password`
	- client_id: `<client id of the scorpio microservice>`
	- client_secret: `<client secret of the scorpio microservice>`
	- username: `<username>`
	- password: `<password>`

	Response: JWT access token is obtained upon the authentication of the user details.

2. Testing APIs – Provide the JWT token obtained in above step in the Authorization header of the API request as below.

	Header: `Authorization`
	Header value: `Bearer <JWT token>`

	Response: As defined in the NGSI-LD specs. Identified roles for the APIs should be able to access the APIs as desired and respond with 2XX status code. Unauthorized roles for the APIs should return 403 Access Forbidden response.

	The RBAC is supported for all NGSI-LD APIs implemented in Scorpio's microservices.

**Relay context updates to Kafka**

The objective of this feature is to relay context change updates in the context broker to Apache Kafka. Any change on the NGSI-LD Entities – CREATE, UPDATE, DELETE is to be processed and relayed to Kafka topics in Debezium format. The Kafka topics for this are created on the run based on the entity name.

**Configuration:**

Installation of Strimzi operator for Kafka along with Kafka Connect &amp; Kafka Connector to the Scorpio database is required to test this feature. The above setup has been done using K8s manifest files.

**Test Procedure:**

1. Perform any operation on an Entity that changes the state of the entity – Create, Update, Partial Update, Delete.

	E.g.: Create an Entity.

	`curl -vvv http://\<Gateway IP>:\<Gateway Port>/ngsi-ld/v1/entities -s -S -H 'Content-Type: application/ld+json' -H 'Authorization: Bearer \<token>' -d @- <<EOF`
	```
	{
		"id": "house2:smartrooms:room1",
		"type": "Room",
		"temperature": {
			"value": 23,
			"unitCode": "CEL",
			"type": "Property",
			"providedBy": {
				"type": "Relationship",
				"object": "smartbuilding:house2:sensor0815"
			}
		},

		"isPartOf": {
			"type": "Relationship",
			"object": "smartcity:houses:house2"
		},

		"@context": [{"Room": "urn:mytypes:room", "temperature": "myuniqueuri:temperature", "isPartOf": "myuniqueuri:isPartOf"},"https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"]
	}
	EOF
	```

2. Test the context updates on the entity using the default Kafka consumer provided within Kafka service. The following commands are to test this feature on Kubernetes.

	- Log into the Kafka pod
	`kubectl -n <namespace of pod> exec -it <Kafka pod name or pod id> /bin/bash`

	- Run the consumer script from within the pod
	`bin/kafka-console-consumer.sh –bootstrap-server localhost:9092 –topic <name of topic> --from-beginning`

	Expected Result: JSON message in Debezium format associated with the CRUD operations on Entity object is received.
	```
	{
		"op": "c",
		"before": null,
		"after": {
			"temperature": 23,
			"id": "house2:smartrooms:room3",
			"type": "room",
			"isPartOf": "smartcity:houses:house2"
		},

		"source": {
			"version": "1.7.1.Final",
			"connector": "postgresql",
			"name": "pgserver",
			"ts_ms": 1639036587474,
			"snapshot": "false",
			"db": "ngb",
			"sequence": "[null,\"32872704\"]",
			"schema": "public",
			"table": "entity",
			"txId": 566,
			"lsn": 32872704,
			"xmin": null
		},

		"ts_ms": 1639036588534,
		"transaction": null
	}
	```