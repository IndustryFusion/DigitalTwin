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

const { assert } = require('chai');
const chai = require('chai');
global.should = chai.should();

const rewire = require('rewire');
const ToTest = rewire('../lib/alerta.js');

const logger = {
  debug: function () {},
  error: function () {}
};

describe('Test sendAlerts', function () {
  it('Should post body with correct path and token', async function () {
    const config = {
      alerta: {
        accessKeyVariable: 'ACCESS_KEY_VARIABLE',
        hostname: 'hostname',
        port: 1234,
        protocol: 'http:'
      }
    };
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };
    const process = {
      env: {
        ACCESS_KEY_VARIABLE: 'access_key'
      }
    };
    const body = {
      key: 'value',
      key2: 'value2'
    };
    const expectedOptions = {
      headers: {
        Authorization: 'Key access_key',
        'Content-type': 'application/json'
      },
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      path: '/api/alert',
      method: 'POST'

    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, body);
        obj.disableChunks.should.equal(true);
        return 'posted';
      }
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('process', process);
    ToTest.__set__('Rest', Rest);
    const alerta = new ToTest(config);
    const result = await alerta.sendAlert(body);
    result.should.equal('posted');
    revert();
  });
});
