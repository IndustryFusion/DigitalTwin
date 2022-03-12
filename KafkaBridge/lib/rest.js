/**
* Copyright (c) 2022 Intel Corporation
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
const Logger = require('./logger.js');
const http = require('http');

module.exports = function Rest (config) {
  const logger = Logger(config);

  /**
   *
   * @param {object} options - http options
   * @param {object} body - body to post
   * @param {boolean} disableChunks - some rest servers cannot digest chunks, e.g. Alerta
   * @param {boolean} noStringify - body already stringified, no need to stringify it again
   * @returns
   */
  this.postBody = function ({ options, body, disableChunks, noStringify }) {
    if (noStringify === undefined || !noStringify) {
      body = JSON.stringify(body);
    }
    if (disableChunks === true) {
      options.headers['Content-Length'] = body.length;
    }
    return new Promise(function (resolve, reject) {
      const req = http.request(options, res => {
        const statusCode = res.statusCode;
        let resBody = '';
        res.on('data', d => {
          resBody += d;
        });
        res.on('end', () => {
          try {
            resBody = JSON.parse(resBody);
          } catch (e) {
            resBody = null;
          }
          const result = {
            statusCode: statusCode,
            body: resBody
          };
          resolve(result);
        });
      });
      req.on('error', error => {
        reject(error);
      });
      logger.debug('Now sending: ' + body);
      req.write(body);
      req.end();
    });
  };

  /**
   * GET rest body
   * @param {options for GET request} options
   */
  this.getBody = function (options) {
    return new Promise(function (resolve, reject) {
      const req = http.request(options, res => {
        const statusCode = res.statusCode;
        let body = '';
        res.on('data', d => {
          body += d;
        });
        res.on('end', () => {
          try {
            body = JSON.parse(body);
          } catch (e) {
            body = null;
          }
          const result = {
            statusCode: statusCode,
            body: body
          };
          resolve(result);
        });
      });
      req.on('error', error => {
        reject(error);
      });
      req.end();
    });
  };
};
