/*
Copyright (c) 2023, Intel Corporation

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
    common = require('../lib/common'),
    utils = require("../lib/utils").init();

var configFileKey = {
    dataDirectory: 'data_directory',
    loggerLevel: 'logger.LEVEL',
    connectorRestProxyHost: 'connector.rest.proxy.host',
    connectorRestProxyPort: 'connector.rest.proxy.port',
    gatewayId : 'gateway_id',
    deviceId: 'device_id',
    deviceName: 'device_name',
    keycloakUrl: 'keycloak_url',
    deviceToken: 'device_token',
    refreshToken: 'refresh_token',
    deviceTokenExpire: 'device_token_expire',
    attributeList: 'attribute_list'
};

var setGatewayId = function(id, cb) {
    common.saveToDeviceConfig(configFileKey.gatewayId, id);
    cb(id);
};

var setDeviceId = function(id) {
    common.saveToDeviceConfig(configFileKey.deviceId, id);
};

var getGatewayId = function(cb) {
    utils.getGatewayId(configFileKey.gatewayId, cb);
};

var getDataDirectory = function(cb) {
    utils.getDataDirectory(configFileKey.dataDirectory, cb);
};


module.exports = {
    addCommand : function (program) {

        program
            .command('device-id')
            .description('Displays the device id.')
            .action(function() {
                utils.getDeviceId(function (id) {
                    logger.info("Device ID: %s", id);
                });
            });

        program
            .command('set-device-id <id>')
            .description('Overrides the device id.')
            .action(function(id) {
                common.saveToDeviceConfig(configFileKey.deviceId, id);
                logger.info("Device ID set to: %s", id);
            });

        program
            .command('clear-device-id')
            .description('Reverts to using the default device id.')
            .action(function() {
                common.saveToDeviceConfig(configFileKey.deviceId, false);
                logger.info("Device ID cleared.");
            });

        program
            .command('gateway-id')
            .description('Displays the geteway id.')
            .action(function() {
                getGatewayId(function (id) {
                    logger.info("Gateway ID: %s", id);
                });
            });

        program
            .command('set-gateway-id <id>')
            .description('Overrides the geteway id.')
            .action(function(id) {
                setGatewayId(id, function(id) {
                    logger.info("Gateway Id set to: %s", id);
                });
            });
       
        program
            .command('data-directory')
            .description('Displays current data directory.')
            .action(function() {
                getDataDirectory(function (id) {
                    logger.info("Current data directory: %s", id);
                });
            });

        program
            .command('reset-data-directory')
            .description('Resets to default the path of directory that contains sensor data.')
            .action(function() {
                common.saveToConfig(configFileKey.dataDirectory, "./data/");
                logger.info("Data directory changed to default.");
            });

        program
            .command('force-device-token-refresh')
            .description('Marks the device token as expired and forces its refreshment at the start of the next command.')
            .action(function() {
                common.saveToDeviceConfig(configFileKey.deviceTokenExpire, new Date().getTime());
                logger.info("Current device token is marked as expired and will be refreshed.");
            });
    },
    getGatewayId: getGatewayId,
    setGatewayId: setGatewayId,
    setDeviceId: setDeviceId,
};
