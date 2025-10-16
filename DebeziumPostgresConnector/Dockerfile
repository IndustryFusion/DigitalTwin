FROM quay.io/strimzi/kafka:0.45.0-kafka-3.9.0
USER root:root
RUN mkdir -p plugins && cd plugins && curl  https://repo1.maven.org/maven2/io/debezium/debezium-connector-postgres/1.8.1.Final/debezium-connector-postgres-1.8.1.Final-plugin.tar.gz | tar xvz
COPY * /opt/kafka/plugins/
USER 1001
