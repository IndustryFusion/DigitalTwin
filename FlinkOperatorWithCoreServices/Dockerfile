FROM maven:3.9.2-eclipse-temurin-17 AS build
WORKDIR /app
COPY CoreServices/pom.xml ./
RUN mvn dependency:go-offline test -B -Pcluster
COPY CoreServices/src ./src
COPY CoreServices/config ./config
RUN mvn package verify test -B -Pcluster
FROM apache/flink-kubernetes-operator:1.11.0
WORKDIR /app
COPY --from=build /app/target/CoreServices*.jar ./CoreServices.jar
