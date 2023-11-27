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

const assert = require('chai').assert;
const rewire = require('rewire');
const chai = require('chai');
global.should = chai.should();

const fileToTest = '../lib/cache/index.js';

describe(fileToTest, function () {
  const ToTest = rewire(fileToTest);
  class Logger {
    info () {}
    debug () {}
  };
  ToTest.__set__('Logger', Logger);

  it('Shall test constructing of Cache', function (done) {
    const config = {
      cache: {
        port: 1234,
        host: 'redishost'
      }
    };

    const redis = {
      createClient: function () {
        return {
          on: function (evType) {
            evType.should.equal('error');
          }
        };
      }
    };
    ToTest.__set__('redis', redis);
    const cache = new ToTest(config);
    cache.config.should.deep.equal(config);
    done();
  });
  it('Shall test setValue', function (done) {
    const config = {
      cache: {
        port: 1234,
        host: 'redishost'
      }
    };

    const redis = {
      createClient: function () {
        return {
          on: function (evType) {
            evType.should.equal('error');
          },
          hSet: function (key, valueKey, value) {
            key.should.equal('key');
            valueKey.should.equal('valueKey');
            value.should.equal('value')
          }
        };
      }
    };
    ToTest.__set__('redis', redis);
    const cache = new ToTest(config);
    cache.setValue('key', 'valueKey', 'value');
    done();
  });
  it('Shall test getValue', function (done) {
    const config = {
      cache: {
        port: 1234,
        host: 'redishost'
      }
    };

    const redis = {
      createClient: function () {
        return {
          on: function (evType) {
            evType.should.equal('error');
          },
          hGetAll: function (key) {
            key.should.equal('key');
            return 'true';
          }
        };
      }
    };
    ToTest.__set__('redis', redis);
    const cache = new ToTest(config);
    cache.getValue('key').then(result => result.should.equal('true'));
    done();
  });
});
