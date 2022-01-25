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

const chai = require('chai');
global.should = chai.should();

const rewire = require('rewire');
const toTest = rewire('../gateway.js');
const flinkVersion = '1.14.3';

const logger = {
  debug: function () {},
  error: function () {}
};

describe('Test health path', function () {
  it('Should return 200 and OK', function () {
    const response = {
      status: function (val) {
        val.should.equal(200);
        return {
          send: function (state) {
            state.should.equal('OK');
          }
        };
      }
    };
    const revert = toTest.__set__({
      logger: logger
    });

    const appget = toTest.__get__('appget');
    appget(null, response);
    revert();
  });
});
describe('Test statement path', function () {
  it('Test exec command for sqlclient', function () {
    let fsWriteFilename;
    const statement = 'select *;';
    const flinkSqlCommand = `./flink-${flinkVersion}/bin/sql-client.sh -l ./jars -f `;

    const response = {
      status: function (val) {

      }
    };
    const request = {
      body: {
        statement: statement
      }
    };
    const exec = function (command, output) {
      command.should.equal(flinkSqlCommand + fsWriteFilename);
    };
    const fs = {
      writeFileSync: function (filename, data) {
        fsWriteFilename = filename;
        data.should.equal(statement);
      }
    };
    const revert = toTest.__set__({
      logger: logger,
      exec: exec,
      fs: fs
    });

    const apppost = toTest.__get__('apppost');
    apppost(request, response);
    revert();
  });
  it('Test empty body (should return 500)', function () {
    const response = {
      status: function (val) {
        val.should.equal(500);
      },
      send: function (val) {
        val.should.equal('Wrong format! No statement field in body');
      }
    };
    const request = {
    };
    const request2 = {
      body: undefined
    };
    const request3 = {
      body: null
    };
    const request4 = {
      body: {
        statement: undefined
      }
    };

    const revert = toTest.__set__({
      logger: logger
    });

    const apppost = toTest.__get__('apppost');
    apppost(request, response);
    apppost(request2, response);
    apppost(request3, response);
    apppost(request4, response);
    revert();
  });
  it('Test exec output with exec error (should return 500)', function () {
    const error = 'error';

    const response = {
      status: function (val) {
        val.should.equal(500);
      },
      send: function (val) {
        val.should.equal('Error while executing sql-client: ' + error);
      }
    };
    const uuid = {
      v4: () => 'uuid'
    };
    const fs = {
      unlinkSync: function (filename) {
        filename.should.equal('/tmp/script_uuid.sql');
      },
      writeFileSync: () => {}
    };
    const request = {
      body: {
        statement: 'select *;'
      }
    };
    const exec = function (command, output) {
      output(error, null, null);
    };
    const revert = toTest.__set__({
      logger: logger,
      exec: exec,
      uuid: uuid,
      fs: fs
    });

    const apppost = toTest.__get__('apppost');
    apppost(request, response);
    revert();
  });
  it('Test exec output with Job ID (should return 200)', function () {
    const stdout = 'Job ID: abcdef123456789';
    const response = {
      status: function (val) {
        val.should.equal(200);
        return {
          send: function (state) {
            state.should.equal('{ "jobid": "abcdef123456789" }');
          }
        };
      },
      send: function (val) {
        val.should.equal('Error while executing sql-client: ');
      }
    };
    const uuid = {
      v4: () => 'uuid'
    };
    const fs = {
      unlinkSync: function (filename) {
        filename.should.equal('/tmp/script_uuid.sql');
      },
      writeFileSync: () => {}
    };
    const request = {
      body: {
        statement: 'select *;'
      }
    };
    const exec = function (command, output) {
      output(null, stdout, null);
    };
    const revert = toTest.__set__({
      logger: logger,
      exec: exec,
      uuid: uuid,
      fs: fs
    });

    const apppost = toTest.__get__('apppost');
    apppost(request, response);
    revert();
  });
  it('Test exec output with no Job ID (should return 500)', function () {
    const stdout = 'Job : error';
    const response = {
      status: function (val) {
        val.should.equal(500);
      },
      send: function (state) {
        state.should.equal('Not successfully submitted. No JOB ID found in server reply.');
      }

    };
    const uuid = {
      v4: () => 'uuid'
    };
    const fs = {
      unlinkSync: function (filename) {
        filename.should.equal('/tmp/script_uuid.sql');
      },
      writeFileSync: () => {}
    };
    const request = {
      body: {
        statement: 'select *;'
      }
    };
    const exec = function (command, output) {
      output(null, stdout, null);
    };
    const revert = toTest.__set__({
      logger: logger,
      exec: exec,
      uuid: uuid,
      fs: fs
    });

    const apppost = toTest.__get__('apppost');
    apppost(request, response);
    revert();
  });
});
