/*
Copyright (c) 2014, Intel Corporation

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

'use strict';
const fs = require('fs');
const path = require('path');
const config = require('../config');
let logger = require('./logger').init();
/**
 * @description it will write to JSON file overwriting the current content
 * @param filename <string> the name with path where the file will be wrote.
 * @param data <object> the will be wrote to filename
 */
module.exports.writeToJson = function (filename, data) {
  const err = fs.writeFileSync(filename, JSON.stringify(data, null, 4));
  if (err) {
    logger.error('The file could not be written ', err);
    return true;
  } else {
    logger.info('Object data saved to ' + filename);
    return false;
  }
};

/**
 * @description it will read from filename and return the content if not exists will return empty object
 * @param filename <string> fullpath name
 * @return <object> if the file not exist will return an empty object
 */
module.exports.readFileToJson = function (filename) {
  let objectFile = null;
  if (fs.existsSync(filename)) {
    try {
      objectFile = fs.readFileSync(filename);
      objectFile = JSON.parse(objectFile);
    } catch (err) {
      logger.error('Improper JSON format:', err.message);
      logger.error(err.stack);
    }
  }
  logger.debug('Filename: ' + filename + ' Contents:', objectFile);
  return objectFile;
};

module.exports.initializeDataDirectory = function () {
  const defaultDirectory = path.resolve('./data/');
  let currentDirectory = config.data_directory;

  if (!currentDirectory) {
    currentDirectory = defaultDirectory;
    this.saveToConfig('data_directory', defaultDirectory);
  }

  if (!fs.existsSync(currentDirectory)) {
    fs.mkdirSync(currentDirectory);
  }
};

module.exports.initializeFile = function (filepath, data) {
  if (!fs.existsSync(filepath)) {
    this.writeToJson(filepath, data);
  }
};

module.exports.init = function (logT) {
  logger = logT;
};

module.exports.isAbsolutePath = function (location) {
  return path.resolve(location) === path.normalize(location);
};

module.exports.getFileFromDataDirectory = function (filename) {
  let fullFileName = '';
  if (config) {
    const dataDirectory = config.data_directory;
    if (module.exports.isAbsolutePath(dataDirectory)) {
      fullFileName = path.resolve(dataDirectory, filename);
    } else {
      fullFileName = path.resolve(__dirname, '..', dataDirectory, filename);
    }
  }
  return fullFileName;
};

module.exports.getDeviceConfigName = function () {
  const fullFileName = module.exports.getFileFromDataDirectory('device.json');

  if (!fs.existsSync(fullFileName)) {
    this.initializeDeviceConfig();
  }

  if (fs.existsSync(fullFileName)) {
    return fullFileName;
  } else {
    logger.error('Failed to find device config file!');
    process.exit(0);
  }
};

module.exports.getDeviceConfig = function () {
  const deviceConfig = this.readFileToJson(this.getDeviceConfigName());
  return deviceConfig;
};

module.exports.initializeDeviceConfig = function () {
  if (config) {
    const dataDirectory = config.data_directory;
    const deviceConfig = path.resolve(dataDirectory, 'device.json');
    if (!fs.existsSync(deviceConfig)) {
      const dataFile = {
        activation_retries: 10,
        activation_code: null,
        device_id: false,
        device_name: false,
        device_loc: [
          88.34,
          64.22047,
          0
        ],
        gateway_id: false,
        device_token: '',
        refresh_token: '',
        device_token_expire: new Date().getTime(),
        account_id: '',
        sensor_list: [],
        last_actuations_pull_time: false
      };

      this.writeToJson(deviceConfig, dataFile);
    }
  }
};

module.exports.readConfig = function (fileName) {
  return this.readFileToJson(fileName);
};

module.exports.writeConfig = function (fileName, data) {
  this.writeToJson(fileName, data);
};

module.exports.saveToConfig = function (key, value) {
  const fileName = config.getConfigName();
  this.saveConfig(fileName, key, value);
};

module.exports.saveToDeviceConfig = function (key, value) {
  const fileName = this.getDeviceConfigName();
  this.saveConfig(fileName, key, value);
};

module.exports.saveConfig = function () {
  if (arguments.length < 2) {
    logger.error('Not enough arguments : ', arguments);
    process.exit(1);
  }

  const fileName = arguments[0];
  const key = arguments[1];
  let value = arguments[2];
  let data = this.readConfig(fileName);
  const keys = key.split('.');
  const configSaver = function (data, keys) {
    while (keys.length > 1) {
      const subtree = {};
      subtree[keys.pop()] = value;
      value = subtree;
    }
    data[keys.pop()] = value;
    return data;
  };
  data = configSaver(data, keys);
  if (data) {
    this.writeConfig(fileName, data);
  }
  return true;
};

module.exports.initializeCatalog = function () {
  if (config) {
    const dataDirectory = config.data_directory;
    const catalogFile = path.resolve(dataDirectory, 'catalog.json');
    if (!fs.existsSync(catalogFile)) {
      const data = [];
      this.writeToJson(catalogFile, data);
    }
  }
};

module.exports.getCatalogName = function () {
  const fullFileName = this.getFileFromDataDirectory('catalog.json');

  if (!fs.existsSync(fullFileName)) {
    this.initializeCatalog();
  }

  if (fs.existsSync(fullFileName)) {
    return fullFileName;
  } else {
    logger.error('Failed to find catalog file!');
    process.exit(0);
  }
};

module.exports.getCatalog = function () {
  const catalog = this.readFileToJson(this.getCatalogName());
  return catalog;
};

module.exports.writeCatalog = function (data) {
  const fileName = this.getCatalogName();
  this.writeToJson(fileName, data);
};

/**
 * @description Build a path replacing patter {} by the data arguments
 * if more the one {} pattern is present it shall be use Array
 * @param path string the represent a URL path
 * @param data Array or string,
 * @returns {*}
 */
module.exports.buildPath = function (path, data) {
  const re = /{\w+}/;
  let pathReplace = path;
  if (Array.isArray(data)) {
    data.forEach(function (value) {
      pathReplace = pathReplace.replace(re, value);
    });
  } else {
    pathReplace = pathReplace.replace(re, data);
  }
  return pathReplace;
};

module.exports.isAbsolutePath = function (location) {
  return path.resolve(location) === path.normalize(location);
};

module.exports.isBinary = function (object) {
  if (Buffer.isBuffer(object)) {
    return true;
  }
  const keys = Object.keys(object);
  for (const index in keys) {
    const key = keys[index];
    if (typeof object[key] === 'object') {
      if (this.isBinary(object[key])) {
        return true;
      }
    }
  }
  return false;
};
