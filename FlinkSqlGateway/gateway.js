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
const express = require('express');
const { spawn } = require('child_process');
const uuid = require('uuid');
const fs = require('fs');
const path = require('path');
const app = express();
const bodyParser = require('body-parser');
const RateLimit = require('express-rate-limit');
const limiter = RateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100 // max 100 requests per windowMs
});

const logger = require('./lib/logger.js');
const port = process.env.SIMPLE_FLINK_SQL_GATEWAY_PORT || 9000;
const debug = process.env.DEBUG || 'false';
const flinksubmit = '/opt/flink/bin/flink run';
const runningAsMain = require.main === module;

const udfdir = '/tmp/udf';
const submitdir = 'submitjob';
const localudf = 'udf';
const localdata = 'data';
const sqlStructures = 'SQL-structures.json';
const submitjobscript = 'job.py';
const cwd = process.cwd();

function appget (_, response) {
  response.status(200).send('OK');
  logger.debug('Health Endpoint was requested.');
};

function submitJob (command, response) {
  const args = command.split(' ');
  let jobId = null;
  return new Promise((resolve, reject) => {
    const res = spawn(args[0], args.slice(1));
    res.stdout.on('data', (data) => {
      logger.info('Stdout messages from application: ' + data);
      // find Job ID ind stdout, e.g.
      // Job ID: e1ebb6b314c82b27cf81cbc812300d97
      const regexp = /JobID=\[([0-9a-f]*)\]/i;
      try {
        const found = data.toString().match(regexp);
        if (found !== null && found !== undefined) {
          jobId = found[1];
          logger.debug(`JobId matched: ${jobId}`);
        }
      } catch (e) {
        logger.debug('No JobId found');
      }
    });
    res.stderr.on('data', (data) => {
      logger.error('Stderr messages from application: ' + data);
    });
    res.on('close', (code) => {
      logger.info(`child process exited with code ${code}`);
      if (code === 0) {
        logger.info('jobId found: ' + jobId);
        response.status(200).send('{ "jobid": "' + jobId + '" }');
        resolve();
      } else {
        response.status(500);
        response.send('Not successfully submitted. No JOB ID found in server reply.');
        reject(new Error('Could not find JOB ID'));
      }
    });
  });
}

const createCommand = function (dirname) {
  const command = flinksubmit + ' --python ' + dirname + '/' + submitjobscript;
  logger.debug('Now executing ' + command);
  process.chdir(dirname);
  return command;
};

function apppost (request, response) {
  // for now ignore session_id
  const body = request.body;
  if (body === undefined || body === null || body.sqlstatementset === undefined) {
    response.status(500);
    response.send('Wrong format! No sqlstatementset field in body');
    return;
  }
  const id = uuid.v4();
  const dirname = '/tmp/gateway_' + id;
  const datatargetdir = dirname + '/' + localdata;
  const udftargetdir = dirname + '/' + localudf;
  const submitjobscripttargetdir = dirname + '/' + submitjobscript;
  try {
    process.chdir(cwd);
    fs.mkdirSync(dirname, '0744');
    fs.mkdirSync(datatargetdir, '0744');
    fs.cpSync(submitdir + '/' + localudf, udftargetdir, { recursive: true });
    fs.cpSync(submitdir + '/' + submitjobscript, submitjobscripttargetdir);
    fs.writeFileSync(datatargetdir + '/' + sqlStructures, JSON.stringify(body));
    const udfFiles = getLocalPythonUdfs();
    udfFiles.forEach(file => fs.copyFileSync(file, udftargetdir + '/' + path.basename(file)));

    const command = createCommand(dirname);
    submitJob(command, response).then(
      () => {
        if (debug === 'false') {
          logger.info('Removing ' + dirname + ': debug = ' + debug);
          fs.rmSync(dirname, { recursive: true, force: true });
        }
      }
    ).catch(
      (e) => {
        logger.error(e.stack || e);
        if (debug === 'false') {
          logger.info('Removing ' + dirname + ': debug = ' + debug);
          fs.rmSync(dirname, { recursive: true, force: true });
        }
      }
    );
  } catch (e) {
    logger.error('Could not submit job: ' + e.stack || e);
    if (debug === 'false') {
      logger.info('Removing ' + dirname + ': debug = ' + debug);
      fs.rmSync(dirname, { recursive: true, force: true });
    }
  }
}

function udfget (req, res) {
  const filename = req.params.filename;
  logger.debug('python_udf get was requested for: ' + filename);
  const fullname = `${udfdir}/${filename}.py`;
  try {
    fs.readFileSync(fullname);
  } catch (err) {
    res.status(404).send('File not Found');
    logger.info('File not found: ' + fullname);
    return;
  }
  res.status(200).send('OK');
};

function udfpost (req, res) {
  const filename = req.params.filename;
  const body = req.body;
  if (body === undefined || body === null) {
    res.status(500);
    res.send('No body received!');
    return;
  }
  logger.debug(`python_udf with name ${filename}`);
  const fullname = `${udfdir}/${filename}.py`;
  try {
    fs.writeFileSync(fullname, body);
  } catch (err) {
    res.status(500).send('Could not write file: ' + err);
    logger.error('WriteSync failed:' + err);
    return;
  }
  res.status(201).send('CREATED');
}

function getLocalPythonUdfs () {
  const verfiles = {};
  const files = fs.readdirSync(udfdir)
    .filter(fn => fn.endsWith('.py'))
    .sort()
    .map(x => x.substring(0, x.lastIndexOf('.')))
    .map(x => x.split('_v'));

  files.forEach(x => { verfiles[x[0]] = x[1]; });
  const result = Object.keys(verfiles).map(x => `${x}_v${verfiles[x]}.py`).map(x => `${udfdir}/${x}`);
  return result;
}

app.use(express.json({ limit: '10mb' }));

app.get('/health', appget);
app.get('/v1/python_udf/:filename', limiter, udfget);

app.post('/v1/sessions/:session_id/statements', limiter, apppost);
app.post('/v1/python_udf/:filename', limiter, bodyParser.text(), udfpost);

if (runningAsMain) {
  if (!fs.existsSync(udfdir)) {
    fs.mkdirSync(udfdir);
  }

  app.listen(port, function () {
    console.log('Listening on port ' + port);
  });
}
