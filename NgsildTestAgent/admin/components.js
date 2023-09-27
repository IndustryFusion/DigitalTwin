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

var Cloud = require("../lib/cloud.proxy"),
    Message = require('../lib/agent-message'),
    utils = require("../lib/utils").init(),
    logger = require('../lib/logger').init(),
    Component = require('../lib/data/Components'),
    common = require('../lib/common')

var configFileKey = {
    realmId : 'realm_id',
    gatewayId : 'gateway_id',
    deviceId: 'device_id',
    deviceName: 'device_name',
    keycloakUrl: 'keycloak_url',
    onboardingToken:'onboarding_token',
    deviceToken: 'device_token',
    attributeList: 'attribute_list'
};

var resetComponents = function () {
    var data = [];
    common.saveToDeviceConfig(configFileKey.metricList, data);
};

var resetToken = function () {
    common.saveToDeviceConfig(configFileKey.realmId, false);
    common.saveToDeviceConfig(configFileKey.deviceToken, false);
};

function registerObservation (comp, value) {
    utils.getDeviceId(function (id) {
        var cloud = Cloud.init(logger, id);
        if (cloud.isActivated()) {
            cloud.setDeviceCredentials();
            var r = 0;
            var agentMessage = Message.init(cloud, logger);
            var msg = {
                "n": comp,
                "v": value
            };
            agentMessage.handler(msg, function (stus) {
                logger.info("Response:", stus);
                process.exit(r);
            });
        } else {
            logger.error("Error in the Observation Device is not activated ...");
            process.exit(1);
        }
    });
}

function getComponentsList () {
    var storeFile = common.getDeviceConfig();
    if(storeFile) {
        var com = storeFile[configFileKey.sensorList];
        var table = new Component.Register(com);
        console.log(table.toString());
    }
}

module.exports = {
    addCommand : function (program) {
        program
            .command('reset-components')
            .description('Clears the component list.')
            .action(resetComponents);
        program
            .command('observation <comp_name> <value>')
            .description('Sends an observation for the device, for the specific component.')
            .action(registerObservation);
        program
            .command('components')
            .description('Displays components registered for this device.')
            .action(getComponentsList);
        program
            .command('initialize')
            .description("Resets both the token and the component's list.")
            .action(function() {
                resetComponents();
                resetToken();
                logger.info("Initialized");
            });
    }
};
