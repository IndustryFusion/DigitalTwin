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
const sinon = require('sinon');
const rewire = require('rewire');
const ToTest = rewire('../lib/rest.js');

const logger = {
  debug: function () {},
  error: function () {}
};

describe('Test postBody', function () {
  it('Should write body', async function () {
    const config = {
      ngsildServer: {
        host: 'hostname',
        protocol: 'http'
      }
    };
    const Logger = function () {
      return logger;
    };
    const options = {
      option: 'option'
    };
    const expOptions = {
      option: 'option'
    };

    const body = 'body';
    const evmap = {};
    const req = {
      on: function (ev, cb) {
        ev.should.oneOf(['error', 'timeout']);
      },
      write: function (bo) {
        bo.should.equal(JSON.stringify(body));
      },
      end: function () {

      }
    };
    const http = {
      request: function (options, callback) {
        assert.deepEqual(options, expOptions);
        const res = {
          on: function (ev, cb) {
            evmap[ev] = cb;
          },
          statusCode: 200
        };
        callback(res);
        return req;
      }
    };
    const resBody = {
      body: 'body'
    };
    const expResult = {
      statusCode: 200,
      body: resBody
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('http', http);
    const reqSpy = sinon.spy(req, 'end');
    const rest = new ToTest(config);
    setTimeout(function () {
      evmap.data(JSON.stringify(resBody));
      evmap.end();
    }, 1000);
    const result = await rest.postBody({ options, body, noStringify: false, disableChunks: false });
    assert.deepEqual(result, expResult);
    assert(reqSpy.calledOnce, 'req.end not called once!');
    revert();
  });
  it('Should write body, no stringify', async function () {
    const config = {
      ngsildServer: {
        host: 'hostname',
        protocol: 'http'
      }
    };
    const Logger = function () {
      return logger;
    };
    const options = {
      option: 'option'
    };
    const expOptions = {
      option: 'option'
    };
    const body = 'body';
    const evmap = {};
    const req = {
      on: function (ev, cb) {
        ev.should.oneOf(['error', 'timeout']);
      },
      write: function (bo) {
        bo.should.equal(body);
      },
      end: function () {

      }
    };
    const http = {
      request: function (options, callback) {
        assert.deepEqual(options, expOptions);
        const res = {
          on: function (ev, cb) {
            evmap[ev] = cb;
          },
          statusCode: 200
        };
        callback(res);
        return req;
      }
    };
    const resBody = {
      body: 'body'
    };
    const expResult = {
      statusCode: 200,
      body: resBody
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('http', http);
    const reqSpy = sinon.spy(req, 'end');
    const rest = new ToTest(config);
    setTimeout(function () {
      evmap.data(JSON.stringify(resBody));
      evmap.end();
    }, 1000);
    const result = await rest.postBody({ options, body, noStringify: true, disableChunks: false });
    assert.deepEqual(result, expResult);
    assert(reqSpy.calledOnce, 'req.end not called once!');
    revert();
  });
  it('Should write body, with explicit length header', async function () {
    const config = {
      ngsildServer: {
        host: 'hostname',
        protocol: 'http'
      }
    };
    const Logger = function () {
      return logger;
    };
    const expOptions = {
      option: 'option',
      headers: {
        'Content-Length': 6
      }
    };
    const options = {
      option: 'option',
      headers: {}
    };
    const body = 'body';
    const evmap = {};
    const req = {
      on: function (ev, cb) {
        ev.should.oneOf(['error', 'timeout']);
      },
      write: function (bo) {
        bo.should.equal(JSON.stringify(body));
      },
      end: function () {

      }
    };
    const http = {
      request: function (options, callback) {
        assert.deepEqual(options, expOptions);
        const res = {
          on: function (ev, cb) {
            evmap[ev] = cb;
          },
          statusCode: 200
        };
        callback(res);
        return req;
      }
    };
    const resBody = {
      body: 'body'
    };
    const expResult = {
      statusCode: 200,
      body: resBody
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('http', http);
    const reqSpy = sinon.spy(req, 'end');
    const rest = new ToTest(config);
    setTimeout(function () {
      evmap.data(JSON.stringify(resBody));
      evmap.end();
    }, 1000);
    const result = await rest.postBody({ options, body, noStringify: false, disableChunks: true });
    assert.deepEqual(result, expResult);
    assert(reqSpy.calledOnce, 'req.end not called once!');
    revert();
  });
});
describe('Test getBody', function () {
  it('Should get body', async function () {
    const config = {
      ngsildServer: {
        host: 'hostname',
        protocol: 'http'
      }
    };
    const Logger = function () {
      return logger;
    };
    const options = {
      option: 'option'
    };
    const expOptions = {
      option: 'option'
    };

    const body = 'body';
    const evmap = {};
    const req = {
      on: function (ev, cb) {
        ev.should.equal('error');
      },
      write: function (bo) {
        bo.should.equal(JSON.stringify(body));
      },
      end: function () {

      }
    };
    const http = {
      request: function (options, callback) {
        assert.deepEqual(options, expOptions);
        const res = {
          on: function (ev, cb) {
            evmap[ev] = cb;
          },
          statusCode: 200
        };
        callback(res);
        return req;
      }
    };
    const resBody = {
      body: 'body'
    };
    const expResult = {
      statusCode: 200,
      body: resBody
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('http', http);
    const reqSpy = sinon.spy(req, 'end');
    const rest = new ToTest(config);
    setTimeout(function () {
      evmap.data(JSON.stringify(resBody));
      evmap.end();
    }, 1000);
    const result = await rest.getBody(options);
    assert.deepEqual(result, expResult);
    assert(reqSpy.calledOnce, 'req.end not called once!');
    revert();
  });
});
