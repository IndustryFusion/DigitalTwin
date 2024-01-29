#!/bin/bash
# Copyright (c) 2024 IB Systems GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

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