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
var schemaValidation = require('./schema-validator'),
    config = require ('../config');
    //Metric = require('./proxy')(config).lib.data.metric.init();
const DbManager = require('./dbManager')

/**
 *
 * @type {{n: string, v: number}}
 */
var sampleMetric = {"n": "temp-sensor",
                    "v": 26.7 };



var Data = function (connector, logT, dbManager) {
    var me = this;
    me.logger = logT || {};
    me.connector = connector;
    me.validator = schemaValidation.validateSchema(schemaValidation.schemas.data.SUBMIT);
    me.dbManager = dbManager;
    /**
     * It will process a component registration if
     * it is not a component registration will return false
     * @param msg
     * @returns {boolean}
     */
    me.submission = async function (msg, callback) {
        if (msg.t === undefined || msg.t === null) {
            msg.t = "Property"
        }
        if (msg.on === undefined || msg.on === null) {
            msg.on = new Date().getTime();
        }
        if (me.validator(msg)) {
            try {
                await dbManager.preInsert(msg, 1)
            } catch (e) {
                this.logger.warn("Error in local database: " + e.message)
            }
            const msgKey = {n: msg.n, on: msg.on};
            msg.n = msg.t + '/' + msg.n;
            delete msg.t;
            me.logger.info ("Submitting: ", msg);
            if (config.connector.mqtt.sparkplugB) {
                me.connector.dataSubmit(msg, async function(dat) {
                    if (dat !== 'fail') {
                        try {
                            await me.dbManager.acknowledge(msgKey)
                        } catch (e) {
                            me.logger.warn("Error in local database: " + e.message)
                        }
                    }       
                    me.logger.info("Response received: " + JSON.stringify(dat));
                    return callback(dat);
                });
            } /*else {
                // Metric to hold data for submission
                var metric = new Metric();

                // Handle multiple observations
                if (Array.isArray(msg)) {
                    for (var i = msg.length - 1; i >= 0; i -= 1) {
                    }
                    // Check if we have any data left to submit
                    if (msg.length === 0) {
                        me.logger.error('Data submission - no data to submit.');
                        return callback(false);
                    }
                }

                metric.set(msg);

                me.connector.dataSubmit(metric, function(dat) {
                    me.logger.info("Response received:", dat);
                    return callback(dat);
                });
            }*/
        } else {
            me.logger.debug(`Data submission - No detected Expected ${sampleMetric} got ${msg}`);
            try {
                await dbManager.preInsert(msg, 0)
            } catch (e) {
                this.logger.warn("Error in local database: " + e.message)
            }
            return callback(false);
        }
    };

};
var init = async function(connector, logger) {
    var dbManager = new DbManager(config)
    await dbManager.init()
    return new Data(connector, logger, dbManager);
};
module.exports.init = init;
