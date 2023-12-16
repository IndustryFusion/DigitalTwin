/**
* Copyright (c) 2021 Intel Corporation
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

const Cache = require('../cache');
const Logger = require('../logger');

class Acl {
  constructor (config) {
    this.config = config;
    this.logger = new Logger(config);
    this.cache = new Cache(this.config);
  }

  async init () {
    this.cache.init();
  }

  async acl (req, res) {
    const username = req.query.username;
    if (username === this.config.mqtt.adminUsername) {
      // superuser
      this.logger.info('Superuser ACL accepted!');
      res.status(200).json({ result: 'allow' });
      return;
    }
    const topic = req.query.topic;
    this.logger.debug('ACL request for username ' + username + ' and topic ' + topic);
    // allow all $SYS topics
    if (topic.startsWith('$SYS/')) {
      res.status(200).json({ result: 'allow' });
      return;
    }

    /* Check: Is accountId/username authorized to publish certain topic
         * ACL verification for SparkplugB message type
        */
    const splitTopic = topic.split('/');
    if (splitTopic[0] === 'spBv1.0') {
      const spBAccountId = splitTopic[1];
      const spBdevId = splitTopic[4];
      const spBAclKey = spBAccountId + '/' + spBdevId;
      const allowed = await this.cache.getValue(spBAclKey, 'acl');
      if (allowed === undefined || !(allowed === 'true') || spBdevId !== username) {
        this.logger.info('Connection rejected for realm ' + spBAccountId + ' device ' + spBdevId);
        res.sendStatus(400);
      } else {
        res.status(200).json({ result: 'allow' });
      }
    } else {
      this.logger.warn('Topic sructure not valid.');
      res.sendStatus(400);
    }
  }
}

module.exports = Acl;
