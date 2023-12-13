ARG KEYCLOAK_VERSION="22.0"

FROM node:12-alpine AS keycloak-themes-builder

ADD themes /themes

WORKDIR /themes/theme/fusion/login/resources
RUN npm install
RUN cp node_modules/patternfly/dist/css/patternfly.min.css css/patternfly.min.css
RUN cp node_modules/patternfly/dist/css/patternfly-additions.min.css css/patternfly-additions.min.css
RUN rm -rf node_modules

FROM alpine:3 AS keycloak-modules-builder

RUN apk add zip

RUN mkdir /deployments

ADD oisp-event-listener /modules/oisp-event-listener
ADD oisp-js-policies /modules/oisp-js-policies

#WORKDIR /modules/oisp-event-listener
#RUN mvn checkstyle:check pmd:check clean package
#RUN cp /modules/oisp-event-listener/target/oisp-event-listener.jar /deployments/oisp-event-listener.jar

WORKDIR /modules/oisp-js-policies
RUN zip -r oisp-js-policies.jar *
RUN cp ./oisp-js-policies.jar /deployments

COPY --from=keycloak-themes-builder --chown=1000 /themes /themes
WORKDIR /themes
RUN zip -r fusion.jar theme META-INF && cp fusion.jar /deployments/fusion.jar

FROM quay.io/keycloak/keycloak:${KEYCLOAK_VERSION}

COPY --from=keycloak-modules-builder --chown=1000 /deployments/fusion.jar /opt/keycloak/providers/fusion.jar

#COPY --from=keycloak-modules-builder --chown=1000 /deployments/oisp-event-listener.jar /opt/keycloak/providers/oisp-event-listener.jar

#COPY --from=keycloak-modules-builder --chown=1000 /deployments/nashorn-core-15.3.jar /opt/keycloak/providers/nashorn-core-15.3.jar
#COPY --from=keycloak-modules-builder --chown=1000 /deployments/asm-7.3.1.jar /opt/keycloak/providers/asm-7.3.1.jar
#COPY --from=keycloak-modules-builder --chown=1000 /deployments/asm-util-7.3.1.jar /opt/keycloak/providers/asm-util-7.3.1.jar
#COPY --from=keycloak-modules-builder --chown=1000 /deployments/asm-commons-7.3.1.jar /opt/keycloak/providers/asm-commons-7.3.1.jar
#COPY --from=keycloak-modules-builder --chown=1000 /deployments/httpclient-4.5.11.jar /opt/keycloak/providers/httpclient-4.5.11.jar
COPY --from=keycloak-modules-builder --chown=1000 /deployments/oisp-js-policies.jar /opt/keycloak/providers/oisp-js-policies.jar

RUN /opt/keycloak/bin/kc.sh build --db=postgres