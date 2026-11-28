# syntax=docker/dockerfile:1.7
FROM maven:3.9.2-eclipse-temurin-17 AS build
WORKDIR /app
RUN <<'SCRIPT'
set -eu
PROXY_HOST=$(printf '%s' "${HTTPS_PROXY:-${HTTP_PROXY:-}}" | sed -E 's#^https?://##' | cut -d: -f1)
PROXY_PORT=$(printf '%s' "${HTTPS_PROXY:-${HTTP_PROXY:-}}" | sed -E 's#^https?://##' | cut -d: -f2)
if [ -n "$PROXY_HOST" ]; then
  mkdir -p /root/.m2
  cat > /root/.m2/settings.xml <<CONF
<settings>
  <proxies>
    <proxy>
      <id>build-proxy</id>
      <active>true</active>
      <protocol>http</protocol>
      <host>${PROXY_HOST}</host>
      <port>${PROXY_PORT}</port>
      <nonProxyHosts>localhost|127.0.0.1</nonProxyHosts>
    </proxy>
  </proxies>
</settings>
CONF
fi
SCRIPT
COPY CoreServices/pom.xml ./
# The local repository is a cache mount, kept from build to build and on CI
# by .github/actions/maven-cache (#1181): a build-time mount, not part of the
# image, so Maven Central is asked only for what is not in it yet.
RUN --mount=type=cache,id=maven-repo,target=/root/.m2/repository,sharing=locked \
    mvn dependency:go-offline test -B -Pcluster
COPY CoreServices/src ./src
COPY CoreServices/config ./config
RUN --mount=type=cache,id=maven-repo,target=/root/.m2/repository,sharing=locked \
    mvn package verify test -B -Pcluster
FROM apache/flink-kubernetes-operator:1.11.0
WORKDIR /app
COPY --from=build /app/target/CoreServices*.jar ./CoreServices.jar
