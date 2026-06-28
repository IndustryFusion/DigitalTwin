ARG FUSEKI_VERSION=6.1.0
ARG JAVA_IMAGE=eclipse-temurin:21-jre-alpine

FROM ${JAVA_IMAGE}

ARG FUSEKI_VERSION
ARG FUSEKI_DOWNLOAD=https://downloads.apache.org/jena/binaries/apache-jena-fuseki-${FUSEKI_VERSION}.tar.gz

RUN apk add --no-cache bash curl && \
    curl -fsSL "${FUSEKI_DOWNLOAD}" -o /tmp/fuseki.tar.gz && \
    tar -xzf /tmp/fuseki.tar.gz -C /opt && \
    mv /opt/apache-jena-fuseki-${FUSEKI_VERSION} /opt/fuseki && \
    rm /tmp/fuseki.tar.gz && \
    apk del curl

RUN addgroup -S fuseki && adduser -S -G fuseki fuseki && \
    mkdir -p /fuseki/databases && \
    chown -R fuseki:fuseki /fuseki /opt/fuseki

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV JVM_ARGS="-Xmx2048m -Xms512m"
ENV FUSEKI_REALMS="iff"

WORKDIR /opt/fuseki

USER fuseki

EXPOSE 3030

ENTRYPOINT ["/entrypoint.sh"]
