ARG KEYCLOAK_VERSION="20.0.2"

FROM node:12-alpine AS keycloak-themes-builder

ADD themes /themes

WORKDIR /themes/theme/fusion/login/resources
RUN npm install
RUN cp node_modules/patternfly/dist/css/patternfly.min.css css/patternfly.min.css
RUN cp node_modules/patternfly/dist/css/patternfly-additions.min.css css/patternfly-additions.min.css
RUN rm -rf node_modules

FROM maven:3.6.3-jdk-8-slim AS keycloak-modules-builder

RUN apt -y -qq update && apt -y -qq install build-essential

RUN mkdir /deployments

ADD oisp-event-listener /modules/oisp-event-listener
ADD oisp-js-policies /modules/oisp-js-policies

WORKDIR /modules/oisp-event-listener
RUN mvn checkstyle:check pmd:check clean package
RUN cp /modules/oisp-event-listener/target/oisp-event-listener.jar /deployments/oisp-event-listener.jar

WORKDIR /modules/oisp-js-policies
RUN mvn clean package
RUN cp ./target/oisp-js-policies.jar ./target/nashorn-core-15.3.jar ./target/asm-7.3.1.jar ./target/asm-util-7.3.1.jar ./target/asm-commons-7.3.1.jar /deployments

COPY --from=keycloak-themes-builder --chown=1000 /themes /themes
WORKDIR /themes
RUN jar cf fusion.jar theme META-INF && cp fusion.jar /deployments/fusion.jar

FROM quay.io/keycloak/keycloak:${KEYCLOAK_VERSION}

COPY --from=keycloak-modules-builder --chown=1000 /deployments/fusion.jar /opt/keycloak/providers/fusion.jar

COPY --from=keycloak-modules-builder --chown=1000 /deployments/oisp-event-listener.jar /opt/keycloak/providers/oisp-event-listener.jar

COPY --from=keycloak-modules-builder --chown=1000 /deployments/nashorn-core-15.3.jar /opt/keycloak/providers/nashorn-core-15.3.jar
COPY --from=keycloak-modules-builder --chown=1000 /deployments/asm-7.3.1.jar /opt/keycloak/providers/asm-7.3.1.jar
COPY --from=keycloak-modules-builder --chown=1000 /deployments/asm-util-7.3.1.jar /opt/keycloak/providers/asm-util-7.3.1.jar
COPY --from=keycloak-modules-builder --chown=1000 /deployments/asm-commons-7.3.1.jar /opt/keycloak/providers/asm-commons-7.3.1.jar
COPY --from=keycloak-modules-builder --chown=1000 /deployments/oisp-js-policies.jar /opt/keycloak/providers/oisp-js-policies.jar

RUN /opt/keycloak/bin/kc.sh build --db=postgres