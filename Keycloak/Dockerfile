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

ADD iff-js-providers /modules/iff-js-providers

WORKDIR /modules/iff-js-providers
RUN zip -r iff-js-providers.jar *
RUN cp ./iff-js-providers.jar /deployments

COPY --from=keycloak-themes-builder --chown=1000 /themes /themes
WORKDIR /themes
RUN zip -r fusion.jar theme META-INF && cp fusion.jar /deployments/fusion.jar

FROM quay.io/keycloak/keycloak:${KEYCLOAK_VERSION}

COPY --from=keycloak-modules-builder --chown=1000 /deployments/fusion.jar /opt/keycloak/providers/fusion.jar

COPY --from=keycloak-modules-builder --chown=1000 /deployments/iff-js-providers.jar /opt/keycloak/providers/iff-js-providers.jar

RUN /opt/keycloak/bin/kc.sh build --db=postgres