FROM openjdk:11-jre
MAINTAINER DevelopmentTeam
# Run as non-root user
RUN useradd deb-user
USER deb-user
WORKDIR /usr/src/adapter
COPY ./target/*.jar ./DebeziumAdapter-SNAPSHOT.jar
CMD ["java","-jar","/usr/src/adapter/DebeziumAdapter-SNAPSHOT.jar"]