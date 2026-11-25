FROM quay.io/strimzi/kafka:0.45.0-kafka-3.9.0 AS plugin
ARG DEBEZIUM_VERSION=1.8.1.Final
# SHA-256 of debezium-connector-postgres-1.8.1.Final-plugin.tar.gz. Maven
# Central publishes only .sha1 (21a70ca1…) and .md5 (f400dadb…) for it; both
# match the archive this hash was taken from.
ARG DEBEZIUM_SHA256=bd790f50e24eefbf9312968e96f7a1201bebd443ef8258f52505322e970c0029
ARG DEBEZIUM_URL=https://repo1.maven.org/maven2/io/debezium/debezium-connector-postgres/${DEBEZIUM_VERSION}/debezium-connector-postgres-${DEBEZIUM_VERSION}-plugin.tar.gz
USER root:root
# The archive is optional in the build context (fetch-plugin.sh, the CI cache):
# its pattern may match nothing. fetch-verified.sh keeps it only with the
# pinned checksum.
COPY fetch-verified.sh debezium-connector-postgres.tar.g[z] /tmp/
RUN sh /tmp/fetch-verified.sh "${DEBEZIUM_URL}" "${DEBEZIUM_SHA256}" /tmp/debezium-connector-postgres.tar.gz && \
    mkdir -p /plugins && \
    tar -xzf /tmp/debezium-connector-postgres.tar.gz -C /plugins

# A stage of its own, so that the copied archive is in no layer of the image.
FROM quay.io/strimzi/kafka:0.45.0-kafka-3.9.0
COPY --from=plugin /plugins/ plugins/
USER 1001
