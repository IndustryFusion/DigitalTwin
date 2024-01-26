FROM node:21

ADD . /app

RUN groupadd -g 1001 agent && useradd -u 1001 -g agent -ms /bin/bash agent

RUN apt-get update && apt-get install -y jq bash && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN mkdir /volume && chown -R agent /volume && chown -R agent /app && chmod u+x /app/util/*

RUN cp -rf /app/config /volume && rm -f /app/config/config.json && ln -s /volume/config/config.json /app/config/config.json

WORKDIR /app

USER agent

RUN npm --force cache clean

RUN npm install

EXPOSE 1884
EXPOSE 8000
EXPOSE 41234
EXPOSE 7070

ENTRYPOINT /app/util/entrypoint.sh