#!/usr/bin/env node
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
"use strict";
var utils = require("../lib/utils").init(),
    logger = require('../lib/logger').init(),
    Cloud = require("../lib/cloud.proxy"),
    Control = require ("../lib/control.proxy"),
    Message = require('../lib/agent-message'),
    udpServer = require('../lib/server/udp'),
    Listener = require("../listeners/"),
    admin= require('commander'),
    pkgJson = require('../package.json'),
    conf = require('../config');

process.on("uncaughtException", function(err) {
    logger.error("UncaughtException:", err.message);
    logger.error(err.stack);
    // let the process exit so that forever can restart it
    process.exit(1);
});

admin.version(pkgJson.version);

admin.parse(process.argv);

utils.getDeviceId(function (id) {
    var cloud = Cloud.init(logger, id);
    cloud.activate(function (status) {
        if (status === 0) {
            var udp = udpServer.singleton(conf.listeners.udp_port, logger);

            var agentMessage = Message.init(cloud, logger);
            logger.info("Starting listeners...");
            udp.listen(agentMessage.handler);

            if (conf.connector.mqtt != undefined) {
                var ctrl = Control.init(conf, logger, id);
                ctrl.bind(udp);
            }
            Listener.TCP.init(conf.listeners, logger, agentMessage.handler);

            // Update catalog
            cloud.catalog(function (catalog) {
                if (catalog) {
                    logger.info("Updating catalog...");
                    utils.updateCatalog(catalog);
                }
            });

        } else {
            logger.error("Error in activation... err # : ", status);
            process.exit(status);
        }
    });
});
