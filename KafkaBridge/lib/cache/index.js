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
    const logger = new Logger(conf);
    this.redisClient = redis.createClient({ socket: { port: conf.cache.port, host: conf.cache.host } });
    this.config = conf;
    this.logger = logger;
    this.redisClient.on('error', function (err) {
      logger.info('Error in Redis client: ' + err);
    });
  }

  async init () {
    await this.redisClient.connect();
  }

  async setValue (key, valueKey, value) {
    await this.redisClient.hSet(key, valueKey, value);
    return value;
  }

  async getValue (key, valueKey) {
    const obj = await this.redisClient.hGetAll(key);
    return obj[valueKey];
  }

  async deleteKeysWithValue (valueKey, clientid) {
    let cursor = 0;
    const keysToDelete = [];

    do {
      const reply = await this.redisClient.scan(cursor);
      cursor = parseInt(reply.cursor, 10);
      const keys = reply.keys;

      for (const key of keys) {
        const value = await this.redisClient.hGet(key, valueKey);
        if (value === clientid) {
          keysToDelete.push(key);
        }
      }
    } while (cursor !== 0);

    for (const key of keysToDelete) {
      await this.redisClient.del(key);
    }

    this.logger.info(`Deleted keys with ${valueKey}=${clientid}: ${keysToDelete.join(', ')}`);
  }
}
module.exports = Cache;
