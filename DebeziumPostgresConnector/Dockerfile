FROM quay.io/strimzi/kafka:0.45.0-kafka-3.9.0
ARG DEBEZIUM_VERSION=1.8.1.Final
# SHA-256 of debezium-connector-postgres-1.8.1.Final-plugin.tar.gz. Maven
# Central publishes only .sha1 (21a70ca1…) and .md5 (f400dadb…) for it; both
# match the archive this hash was taken from.
ARG DEBEZIUM_SHA256=bd790f50e24eefbf9312968e96f7a1201bebd443ef8258f52505322e970c0029
USER root:root
COPY fetch-verified.sh /tmp/fetch-verified.sh
RUN sh /tmp/fetch-verified.sh \
      "https://repo1.maven.org/maven2/io/debezium/debezium-connector-postgres/${DEBEZIUM_VERSION}/debezium-connector-postgres-${DEBEZIUM_VERSION}-plugin.tar.gz" \
      "${DEBEZIUM_SHA256}" /tmp/debezium-connector-postgres.tar.gz && \
    mkdir -p plugins && \
    tar -xzf /tmp/debezium-connector-postgres.tar.gz -C plugins && \
    rm -f /tmp/debezium-connector-postgres.tar.gz /tmp/fetch-verified.sh
USER 1001
