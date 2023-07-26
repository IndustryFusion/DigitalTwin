FROM python:3.8 as plint
ADD submitjob/ submitjob
RUN pip3 install flake8 && flake8 submitjob/job.py

FROM node:16 as nodelint
ADD gateway.js gateway.js
ADD package.json package.json
ADD lib/ lib
ADD test test
ADD .eslintrc.json .eslintrc.json
WORKDIR /
RUN npm install && npm run lint && npm run test

FROM flink:1.16.2

RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash
ENV NVM_DIR="$HOME/.nvm"
RUN NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
RUN . $HOME/.nvm/nvm.sh && nvm install 16 && node --version
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
RUN mkdir jars && cd jars && wget https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/1.16.2/flink-sql-connector-kafka-1.16.2.jar
RUN mkdir -p jars && cd jars && wget https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/1.16.1/flink-sql-connector-kafka-1.16.1.jar
RUN . $HOME/.nvm/nvm.sh && npm install --production
ADD sql-client-defaults.yaml /opt/flink/conf/


RUN apt-get update -y && \
apt-get install -y build-essential libssl-dev zlib1g-dev libbz2-dev libffi-dev liblzma-dev zip && \
wget https://www.python.org/ftp/python/3.7.9/Python-3.7.9.tgz && \
tar -xvf Python-3.7.9.tgz && \
cd Python-3.7.9 && \
./configure --without-tests --enable-shared && \
make -j6 && \
make install && \
ldconfig /usr/local/lib && \
cd .. && rm -f Python-3.7.9.tgz && rm -rf Python-3.7.9 && \
ln -s /usr/local/bin/python3 /usr/local/bin/python && \
apt-get clean && \
rm -rf /var/lib/apt/lists/*

# install PyFlink
RUN pip3 install apache-flink==1.16.2


USER 9999
ENTRYPOINT [ "node ./gateway.js" ]
