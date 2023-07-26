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
const expect = chai.expect;

const rewire = require('rewire');
const toTest = rewire('../gateway.js');
const flinkVersion = '1.14.3';

const logger = {
  debug: function () {},
  error: function () {},
  info: function () {}
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
    const body = {
      sqlstatementset: statement
    };

    const request = {
      body: body
    };
    const exec = function (command, output) {
      command.should.equal(flinkSqlCommand + fsWriteFilename + ' --pyExecutable /usr/local/bin/python3 --pyFiles testfile');
    };
    const fs = {
      writeFileSync: function (filename, data) {
        fsWriteFilename = filename;
        data.should.equal(JSON.stringify(body));
      },
      mkdirSync: function (dirname, mode) {
        mode.should.equal('0744');
        dirname.startsWith('/tmp/gateway_').should.equal(true);
      },
      cpSync: function (src, tgt, mode) {
        tgt.startsWith('/tmp/gateway_').should.equal(true);
      },
      copyFileSync: function (file) {
        file.should.equal('testfile');
      },
      rmSync: function (file) {
        file.startsWith('/tmp/gateway_').should.equal(true);
      }
    };

    const getLocalPythonUdfs = function () {
      return ['testfile'];
    };

    const process = {
      cwd: function () { return 'cwd'; },
      chdir: function (dir) {}
    };

    const revert = toTest.__set__({
      logger: logger,
      exec: exec,
      fs: fs,
      getLocalPythonUdfs: getLocalPythonUdfs,
      process: process
    });

    const apppost = toTest.__get__('apppost');
    apppost(request, response);
    revert();
  });
});
describe('Test apppost', function () {
  it('Test empty body (should return 500)', function () {
    const response = {
      status: function (val) {
        val.should.equal(500);
      },
      send: function (val) {
        val.should.equal('Wrong format! No sqlstatementset field in body');
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
        val.should.equal('Wrong format! No sqlstatementset field in body');
      }
    };
    const uuid = {
      v4: () => 'uuid'
    };
    const fs = {
      unlinkSync: function (filename) {
        filename.should.equal('/tmp/script_uuid.sql');
      },
      writeFileSync: () => {},
      rmSync: function (file) {
        file.startsWith('/tmp/gateway_').should.equal(true);
      }
    };
    const request = {
      body: {
        statement: 'select *;'
      }
    };
    const exec = function (command, output) {
      output(error, null, null);
    };

    const getLocalPythonUdfs = function () {
      return ['testfile'];
    };

    const revert = toTest.__set__({
      logger: logger,
      exec: exec,
      uuid: uuid,
      fs: fs,
      getLocalPythonUdfs: getLocalPythonUdfs
    });

    const apppost = toTest.__get__('apppost');
    apppost(request, response);
    revert();
  });
  it('Test exec output with Job ID (should return 200)', function (done) {
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
      writeFileSync: () => {},
      rmSync: function (file) {
        file.startsWith('/tmp/gateway_').should.equal(true);
        done();
        revert();
      }
    };
    const request = {
      body: {
        sqlstatementset: 'select *;'
      }
    };
    const exec = function (command, output) {
      output(null, stdout, null);
    };

    const getLocalPythonUdfs = function () {
      return ['testfile'];
    };

    const revert = toTest.__set__({
      logger: logger,
      exec: exec,
      uuid: uuid,
      fs: fs,
      getLocalPythonUdfs: getLocalPythonUdfs
    });

    const apppost = toTest.__get__('apppost');
    apppost(request, response);
    // revert();
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
      writeFileSync: () => {},
      rmSync: function (file) {
        file.startsWith('/tmp/gateway_').should.equal(true);
      }
    };
    const request = {
      body: {
        sqlstatementset: 'select *;'
      }
    };
    const exec = function (command, output) {
      output(null, stdout, null);
    };

    const getLocalPythonUdfs = function () {
      return ['testfile'];
    };

    const revert = toTest.__set__({
      logger: logger,
      exec: exec,
      uuid: uuid,
      fs: fs,
      getLocalPythonUdfs: getLocalPythonUdfs
    });

    const apppost = toTest.__get__('apppost');
    apppost(request, response);
    revert();
  });
});
describe('Test udf functions', function () {
  it('Test getLocalPythonUdf', function () {
    const fs = {
      readdirSync: function (filename) {
        return ['file1_v1.py', 'file2_v2.py', 'file3_v1.py', 'file3_v22.py', 'file3_v23-alpha.py', 'file4_v1'];
      }
    };
    const revert = toTest.__set__({
      fs: fs
    });

    const getLocalPythonUdfs = toTest.__get__('getLocalPythonUdfs');
    const result = getLocalPythonUdfs();
    expect(result).to.deep.equal(['/tmp/udf/file1_v1.py',
      '/tmp/udf/file2_v2.py',
      '/tmp/udf/file3_v23-alpha.py']);
    revert();
  });
  it('Test udfpost without body', function () {
    const request = {
      params: {
        filename: 'filename'
      },
      body: undefined
    };
    const response = {
      status: function (val) {
        val.should.equal(500);
      },
      send: function (val) {
        val.should.equal('No body received!');
      }
    };
    const revert = toTest.__set__({
      logger: logger
    });
    const udfpost = toTest.__get__('udfpost');
    udfpost(request, response);
    revert();
  });
  it('Test udfpost with text body', function () {
    const request = {
      params: {
        filename: 'filename'
      },
      body: 'body'
    };
    const response = {
      status: function (val) {
        val.should.equal(201);
        return response;
      },
      send: function (val) {
        val.should.equal('CREATED');
      }
    };
    const fs = {
      writeFileSync: function (filename, data) {
        filename.should.equal('/tmp/udf/filename.py');
        data.should.equal('body');
      }
    };
    const revert = toTest.__set__({
      logger: logger,
      fs: fs
    });
    const udfpost = toTest.__get__('udfpost');
    udfpost(request, response);
    revert();
  });
  it('Test udfget', function () {
    const request = {
      params: {
        filename: 'filename'
      }
    };
    const response = {
      status: function (val) {
        val.should.equal(200);
        return response;
      },
      send: function (val) {
        val.should.equal('OK');
      }
    };
    const fs = {
      readFileSync: function (filename) {
        filename.should.equal('/tmp/udf/filename.py');
      }
    };
    const revert = toTest.__set__({
      logger: logger,
      fs: fs
    });
    const udfget = toTest.__get__('udfget');
    udfget(request, response);
    revert();
  });
});
describe('Test submitJob', function () {
  it('Submit without error', function (done) {
    const command = 'command';
    const exec = function (command, fn) {
      fn('error', null, null);
    };
    const response = {
      status: function (val) {
        val.should.equal(500);
        return response;
      },
      send: function (val) {
        val.should.equal('Error while submitting sql job: error');
        revert();
        done();
      }
    };
    const revert = toTest.__set__({
      logger: logger,
      exec: exec
    });
    const submitJob = toTest.__get__('submitJob');
    submitJob(command, response);
    revert();
  });
  it('Submit without jobId', function (done) {
    const command = 'command';
    const exec = function (command, fn) {
      fn(null, 'nojobid', null);
    };
    const response = {
      status: function (val) {
        val.should.equal(500);
        return response;
      },
      send: function (val) {
        val.should.equal('Not successfully submitted. No JOB ID found in server reply.');
        revert();
        done();
      }
    };
    const revert = toTest.__set__({
      logger: logger,
      exec: exec
    });
    const submitJob = toTest.__get__('submitJob');
    submitJob(command, response);
    revert();
  });
  it('Submit with jobId', function (done) {
    const command = 'command';
    const exec = function (command, fn) {
      fn(null, 'JobID=[1234]', null);
    };
    const response = {
      status: function (val) {
        val.should.equal(200);
        return response;
      },
      send: function (val) {
        val.should.equal('{ "jobid": "1234" }');
        revert();
        done();
      }
    };
    const revert = toTest.__set__({
      logger: logger,
      exec: exec
    });
    const submitJob = toTest.__get__('submitJob');
    submitJob(command, response);
    revert();
  });
});
