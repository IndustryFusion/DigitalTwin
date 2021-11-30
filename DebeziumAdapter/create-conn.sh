curl -X POST -H "Accept:application/json" -H "Content-Type:application/json" localhost:8083/connectors/ -d 
'{
 "name": "scorpio-connector",
 "config": {
 "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
 "tasks.max": "1",
 "plugin.name": "wal2json",
 "database.hostname": "postgres",
 "database.port": "5432",
 "database.user": "ngb",
 "database.password": "ngb",
 "database.dbname" : "ngb",
 "database.server.name": "dbserver1",
 "key.converter": "org.apache.kafka.connect.json.JsonConverter",
 "value.converter": "org.apache.kafka.connect.json.JsonConverter",
 "key.converter.schemas.enable": "false",
 "value.converter.schemas.enable": "false",
 "snapshot.mode": "always"
 }
}'
