FROM python:3.8 as plint
ADD submitjob/ submitjob
RUN pip3 install flake8 && flake8 submitjob/job.py

FROM node:22 as nodelint
ADD gateway.js gateway.js
ADD package.json package.json
ADD lib/ lib
ADD test test
ADD .eslintrc.json .eslintrc.json
WORKDIR /
RUN npm install && npm run lint && npm run test

FROM flink:1.20.4 as flink

# The functions of shacl2flink's SPARQL_ENGINE=ladder. No Maven: they need the
# jars of Flink only.
FROM eclipse-temurin:11-jdk as sparqludf
COPY --from=flink /opt/flink/lib /flink-lib
ADD sparql-udf/ /sparql-udf
WORKDIR /sparql-udf
RUN ./build.sh /flink-lib sparql-udf.jar

FROM flink
COPY --from=sparqludf /sparql-udf/sparql-udf.jar /opt/flink/lib/

RUN curl -fsSL --retry 5 --retry-delay 10 --retry-all-errors -o /tmp/nvm-install.sh https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh && \
    bash /tmp/nvm-install.sh && rm -f /tmp/nvm-install.sh
ENV NVM_DIR="$HOME/.nvm"
RUN NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
RUN . $HOME/.nvm/nvm.sh && nvm install 22 && node --version
RUN mkdir -p /opt/gateway
ENV SIMPLE_FLINK_SQL_GATEWAY_ROOT=/opt/flink
ENV NODE_ENV=production
ENV NODEJSPATH=/.nvm/versions/node/v*/bin
ENV NODE_PATH=/.nvm/versions/node/v*/lib/node_modules
WORKDIR /opt/gateway
#ADD gateway.js gateway.js
COPY --from=nodelint gateway.js gateway.js
ADD package.json package.json
ADD lib/ lib
COPY --from=plint submitjob submitjob
# The jars from Maven Central go through the cache mount maven-repo (#1181),
# fetched by maven-jar.sh, which is bind-mounted and not part of the image.
RUN --mount=type=cache,id=maven-repo,target=/root/.m2/repository,sharing=locked \
    --mount=type=bind,source=maven-jar.sh,target=/usr/local/bin/maven-jar.sh \
    sh /usr/local/bin/maven-jar.sh org/apache/flink flink-sql-connector-kafka 3.3.0-1.20 jars
#RUN mkdir -p jars && cd jars && wget https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/1.16.1/flink-sql-connector-kafka-1.16.1.jar
RUN . $HOME/.nvm/nvm.sh && npm install --production
ADD sql-client-defaults.yaml /opt/flink/conf/


RUN apt-get update -y && \
apt-get install -y build-essential libssl-dev zlib1g-dev libbz2-dev libffi-dev liblzma-dev zip && \
wget --tries=5 --waitretry=10 --retry-connrefused --retry-on-http-error=429,500,502,503,504 https://www.python.org/ftp/python/3.8.20/Python-3.8.20.tgz && \
tar -xvf Python-3.8.20.tgz && \
cd Python-3.8.20 && \
./configure --without-tests --enable-shared && \
make -j6 && \
make install && \
ldconfig /usr/local/lib && \
cd .. && rm -f Python-3.8.20.tgz && rm -rf Python-3.8.20 && \
ln -s /usr/local/bin/python3 /usr/local/bin/python && \
apt-get clean && \
rm -rf /var/lib/apt/lists/*

# install PyFlink
RUN pip3 install --no-cache-dir apache-flink==1.20.4
RUN mkdir -p /opt/flink/plugins/s3 && cp /opt/flink/opt/flink-s3-fs-hadoop-*.jar /opt/flink/plugins/s3
RUN --mount=type=cache,id=maven-repo,target=/root/.m2/repository,sharing=locked \
    --mount=type=bind,source=maven-jar.sh,target=/usr/local/bin/maven-jar.sh \
    sh /usr/local/bin/maven-jar.sh org/apache/flink flink-sql-connector-postgres-cdc 3.4.0 /opt/flink/lib

USER 9999
ENTRYPOINT [ "node ./gateway.js" ]
