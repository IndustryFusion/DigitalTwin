/**
* Copyright (c) 2021, 2023 Intel Corporation
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*    http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/

'use strict';

const redis = require('redis');
const Logger = require('../logger');

class Cache {
  constructor (conf) {
    this.logger = new Logger(conf);
    this.redisClient = redis.createClient({ port: conf.cache.port, host: conf.cache.host });
    this.config = conf;
    this.redisClient.on('error', function (err) {
      this.logger.info('Error in Redis client: ' + err);
    });
  }

  async init () {
    await this.redisClient.connect();
  }

  async setValue (key, valueType, value) {
    // return new Promise((resolve, reject) => {
    await this.redisClient.hSet(key, valueType, value);
    // });
  }

  async getValue (key, valueType) {
    return await this.redisClient.hgetall(key);
  }

  async getValues (key) {
    return await this.redisClient.hgetall(key);
  }
}
module.exports = Cache;
