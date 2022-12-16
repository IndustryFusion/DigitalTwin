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
RUN cp /modules/oisp-js-policies/target/oisp-js-policies.jar /deployments/oisp-js-policies.jar

COPY --from=keycloak-themes-builder --chown=1000 /themes /themes
WORKDIR /themes
RUN jar cf fusion.jar theme META-INF && cp fusion.jar /deployments/fusion.jar

FROM nginx:1.23.2-alpine

COPY --from=keycloak-modules-builder --chown=1000 /deployments /usr/share/nginx/html/deployments
