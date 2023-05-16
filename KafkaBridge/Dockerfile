FROM node:16
COPY alerta/ /opt/alerta/
COPY debeziumBridge/ /opt/debeziumBridge/
COPY ngsildUpdates/ /opt/ngsildUpdates/
COPY mqttBridge /opt/mqttBridge
COPY timescaledb/ /opt/timescaledb/
ADD package.json /opt/package.json
ADD package-lock.json package-lock.json
COPY lib/ /opt/lib/
COPY config/ /opt/config/
ADD test/ /opt/test/
ADD .eslintrc.json /opt/.eslintrc.json
WORKDIR /opt
RUN npm install && npm run lint && npm run test
ENV NODE_ENV=production
USER 9999
