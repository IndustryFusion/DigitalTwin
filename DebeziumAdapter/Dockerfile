FROM openjdk:11-jre
MAINTAINER DevelopmentTeam
WORKDIR /usr/src/adapter
COPY ./target/*.jar ./DebeziumAdapter-SNAPSHOT.jar
CMD ["java","-jar","/usr/src/adapter/DebeziumAdapter-SNAPSHOT.jar"]