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
const os = require('os');
const config = require('../config');
const common = require('./common');

function IoTKitUtils (cfg) {
  const me = this;
  common.initializeDataDirectory();
  me.deviceConf = common.getDeviceConfig();
  me.config = cfg;
  me.did = me.deviceConf.device_id;
}

IoTKitUtils.prototype.getAgentAttr = function () {
  return {
    hardware_vendor: os.cpus()[0].model,
    hardware_model: os.platform(),
    'Model Name': os.arch(),
    'Firmware Version': os.release()
  };
};

IoTKitUtils.prototype.getDeviceId = function () {
  return this.did;

  /* mac.getMac(function(err, macAddress) {
        var result = null;
        if (err) {
        //Unable to get MAC address
            result = os.hostname().toLowerCase();
        } else {
            result = macAddress.replace(/:/g, '-');
        }
        me.did = result;
        cb(result);
    }); */
};
/* IoTKitUtils.prototype.getIPs = function () {
  const addresses = [];
  const interfaces = os.networkInterfaces();
  for (const k in interfaces) {
    if (interfaces.hasOwnProperty(k)) {
      for (const k2 in interfaces[k]) {
        if (interfaces[k].hasOwnProperty(k2)) {
          const address = interfaces[k][k2];
          if (address.family === 'IPv4' && !address.internal) {
            addresses.push(address.address);
          }
        }
      }
    }
  }

  return addresses;
}; */

IoTKitUtils.prototype.getGatewayId = function (key, cb) {
  const me = this;
  if (!cb) {
    throw new Error('Callback required');
  }

  if (me.config[key]) {
    cb(me.config[key]);
  } else {
    (me.getDeviceId(cb));
  }
};

IoTKitUtils.prototype.getDataDirectory = function (key, cb) {
  const me = this;
  if (!cb) {
    throw new Error('Callback required');
  }

  if (me.config[key]) {
    cb(me.config[key]);
  } else {
    throw new Error('Config for data directory not found');
  }
};

IoTKitUtils.prototype.getValueFromDeviceConfig = function (key, cb) {
  const me = this;
  if (!cb) {
    throw new Error('Callback required');
  }

  if (me.deviceConf[key]) {
    cb(me.deviceConf[key]);
  } else {
    throw new Error('Value not found in device config');
  }
};

IoTKitUtils.prototype.getMinutesAndSecondsFromMiliseconds = function (miliseconds) {
  const minutes = Math.floor(miliseconds / 60000);
  const seconds = ((miliseconds % 60000) / 1000).toFixed(0);
  return { m: minutes, s: seconds };
};

exports.init = function () {
  const utils = new IoTKitUtils(config);
  return utils;
};
