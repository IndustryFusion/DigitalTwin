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
var logger = require('../lib/logger').init(),
    CloudProxy = require("../lib/CloudProxy"),
    DataSubmission = require('../lib/DataSubmission'),
    udpServer = require('../lib/server/udp'),
    tcpServer = require("../lib/server/tcp"),
    utils = require("../lib/utils").init(),
    conf = require('../config');

process.on("uncaughtException", function(err) {
    logger.error("UncaughtException:", err.message);
    logger.error(err.stack);
    // let the process exit so that k8s can restart is
    process.exit(1);
});

const id = utils.getDeviceId();
(async () => {
    var cloudProxy = new CloudProxy(logger, id);
    var udp = udpServer.singleton(conf.listeners.udp_port, logger);
    var dataSubmission = new DataSubmission(cloudProxy, logger);
    dataSubmission.init();
    logger.info("Starting listeners...");
    udp.listen(dataSubmission.submission);
    tcpServer.init(conf.listeners, logger, dataSubmission.submission);
    
    let res = await cloudProxy.init();
    if (res == 1) {
        setTimeout(async () => {
            let res = await cloudProxy.init();
            if (res) {
                console.error("Could not setup the Proxy. Please check logs and settings.")
                process.exit(1)
            }
        }
            , 1000);
    }
    if (res == 2) {
        console.error("Unrecoverable Error. Bye!")
        process.exit(1)
    }
})();
