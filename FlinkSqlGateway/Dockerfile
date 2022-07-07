FROM node:16
ADD gateway.js gateway.js
ADD package.json package.json
ADD lib/ lib
ADD test test
ADD .eslintrc.json .eslintrc.json
WORKDIR /
RUN npm install && npm run lint && npm run test

FROM flink:1.15.0

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
ADD gateway.js gateway.js
ADD package.json package.json
ADD lib/ lib
RUN mkdir jars && cd jars && wget https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/1.15.0/flink-sql-connector-kafka-1.15.0.jar
RUN . $HOME/.nvm/nvm.sh && npm install --production
ADD sql-client-defaults.yaml /opt/flink/conf/
USER 9999
ENTRYPOINT [ "node ./gateway.js" ]
