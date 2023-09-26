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

var logger = require('../lib/logger').init(),
    Cloud = require("../lib/cloud.proxy"),
    utils = require("../lib/utils").init(),
    common = require("../lib/common"),
    configurator = require('../admin/configurator'),
    config = require('../config'),
    mqttConnector = require('@open-iot-service-platform/oisp-sdk-js')(config).api.mqtt.connector,
    exec = require('child_process').exec,
    exitMessageCode = {
        "OK": 0,
        "ERROR": 1
    };

var activate = function (code) {
    logger.debug("Activation started ...");
    utils.getDeviceId(function (id) {
        var cloud = Cloud.init(logger, id);
        cloud.activate(code, function (err) {
            var exitCode = exitMessageCode.OK;
            cloud.disconnect();
            if (err) {
                logger.error("Error in the activation process ...", err);
                exitCode = exitMessageCode.ERROR;
            } else{
                configurator.setDeviceId(id);
            }
            process.exit(exitCode);
        });
    });
};

function testConnection () {
    var host = config.connector['rest'].host;
    utils.getDeviceId(function (id) {
        var cloud = Cloud.init(logger, id);
        cloud.test(function (res) {
            var exitCode = exitMessageCode.OK;
            if (res) {
                logger.info("Connected to %s", host);
                logger.info("Environment: %s", res.currentSetting);
                logger.info("Build: %s", res.build);
                logger.debug("Full response: ", res );
            } else {
                logger.error("Connection failed to %s", host);
                exitCode = exitMessageCode.ERROR;
            }

            if (config.connector.mqtt != undefined) {
                var deviceInfo = common.getDeviceConfig();
                if (deviceInfo == null) {
                    logger.error('Cannot test connection to MQTT before device activation...');
                    process.exit(exitCode);
                }
                var mqtt = mqttConnector.singleton(config);
                mqtt.updateDeviceInfo(deviceInfo);
                logger.info("Trying to connect to MQTT...");
                mqtt.connect(function(err) {
                    if (err) {
                        logger.error('Failed to connect to MQTT: ' + err);
                        exitCode = exitMessageCode.ERROR;
                        process.exit(exitCode);
                    }

                    logger.info('Connection to MQTT successful');
                    mqtt.disconnect();
                });
            }

        });
    });
}

function setActualTime () {
    utils.getDeviceId(function (id) {
        var cloud = Cloud.init(logger, id);
        cloud.getActualTime(function (time) {
            var exitCode = exitMessageCode.OK;
            if (time) {
                var command = 'date -u "' + time + '"';
                exec(command, function (error, stdout, stderr) {
                    if (error) {
                        logger.error("Error changing data: ", stderr);
                        logger.debug("Date error: ", error);
                        exitCode = exitMessageCode.ERROR;
                    } else {
                        logger.info("UTC time changed for: ", stdout);
                    }
                    process.exit(exitCode);
                });
            } else {
                logger.error("Failed to receive actual time");
                exitCode = exitMessageCode.ERROR;
                process.exit(exitCode);
            }
        });
    });
}

module.exports = {
    addCommand : function (program) {
        program
            .command('test')
            .description('Tries to reach the server (using the current protocol).')
            .action(function() {
                testConnection();
            });

        program
            .command('activate <activation_code>')
            .description('Activates the device.')
            .action(activate);

        program
            .command('set-time')
            .description('Sets actual UTC time on your device.')
            .action(function() {
                setActualTime();
            });
    }
};
