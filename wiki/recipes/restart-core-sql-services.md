# Restart Core-SQL Services

In the following it is assumed that current working directory is the root directory of `DigitalTwin`. The platform must have been setup properly, e.g. all python dependnecies are installed. `K9s` is used as managemend interface for Kubernetes.


In order to restart the SQL Services, the follwoing steps must to be executed

1. Make sure that the file `.env` contains the desired tag from github.

2. Stop Flink SHACL services


        (cd semantic-model/shacl2flink/ && make flink-undeploy)

3. Stop Core Services
         (cd test && bash ./install-platform.sh -t app=sql-core -c destroy)

4. Stop Kafka-bridges

        (cd test && bash ./install-platform.sh -t app=kafka-bridges -c destroy)

5. Remove all Kafka topics starting with `iff.ngsild.*`, `iff.alerts.*` and `iff.rdf.*`

    1. In K9s select Kafktopics by typing `:kafkatopics`
    2. Mark first appearance of topic by space
    3. Mark last appearance of topic by ctrl+space.
    4. Press ctrl-d

6. start Core Services

        (cd test && bash ./install-platform.sh -t app=sql-core -c apply)

7. Start Kafka-bridges

        (cd test && bash ./install-platform.sh -t app=kafka-bridges -c apply)


8. start Flink SHACL services

        (cd semantic-model/shacl2flink/ && make flink-deploy)