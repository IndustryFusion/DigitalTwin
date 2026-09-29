FROM node:24
COPY alerta/ /opt/alerta/
COPY debeziumBridge/ /opt/debeziumBridge/
COPY ngsildUpdates/ /opt/ngsildUpdates/
COPY mqttBridge /opt/mqttBridge
COPY timescaledb/ /opt/timescaledb/
ADD package.json /opt/package.json
ADD package-lock.json /opt/package-lock.json
COPY lib/ /opt/lib/
COPY config/ /opt/config/
ADD test/ /opt/test/
ADD .eslintrc.json /opt/.eslintrc.json
WORKDIR /opt
# npm ci installs exactly what package-lock.json pins. The lockfile used to be
# copied to / instead of /opt, so `npm install` ignored it and every build took
# the newest release of every dependency -- mqtt.js 5.16.0 arrived that way and
# broke the bridge's reconnect without a single line of our code changing.
RUN npm ci && npm run lint && npm run test
ENV NODE_ENV=production
USER 9999
