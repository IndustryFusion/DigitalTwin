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
    config = require ('../config'),
    Metric = require('@open-iot-service-platform/oisp-sdk-js')(config).lib.data.metric.init();

/**
 *
 * @type {{n: string, v: number}}
 */
var sampleMetric = {"n": "temp-sensor",
                    "v": 26.7 };



var Data = function (connector, logT) {
    var me = this;
    me.logger = logT || {};
    me.connector = connector;
    me.validator = schemaValidation.validateSchema(schemaValidation.schemas.data.SUBMIT);

    /**
     * It will process a component registration if
     * it is not a component registration will return false
     * @param msg
     * @returns {boolean}
     */
    me.submission = function (msg, callback) {
        if (me.validator(msg)) {
            me.logger.info ("Submitting: ", msg);
            if (config.connector.mqtt.sparkplugB) {
                me.connector.dataSubmit(msg, function(dat) {
                    me.logger.info("Response received: " + JSON.stringify(dat));
                    return callback(dat);
                });
            } else {
                // Metric to hold data for submission
                var metric = new Metric();

                // Handle multiple observations
                if (Array.isArray(msg)) {
                    for (var i = msg.length - 1; i >= 0; i -= 1) {
                        // Check component id
                        /*var cidArr = me.store.byName(msg[i].n);
                        if (cidArr) {
                            msg[i].cid = cidArr.cid; // Add component id to observation
                        } else {
                            me.logger.error('Data submission - could not find time series with the name: %s.', msg[i].n);
                            msg.splice(i, 1);
                        }*/
                    }
                    // Check if we have any data left to submit
                    if (msg.length === 0) {
                        me.logger.error('Data submission - no data to submit.');
                        return callback(false);
                    }
                } else {
                    /*var cid = me.store.byName(msg.n);
                    if (cid) {
                        msg.cid = cid.cid; // Add component id to message
                    } else {
                        me.logger.error('Data submission - could not find time series with the name: %s.', msg.n);
                        return callback(true);
                    }*/
                }

                metric.set(msg);

                me.connector.dataSubmit(metric, function(dat) {
                    me.logger.info("Response received:", dat);
                    return callback(dat);
                });
            }
        } else {
            me.logger.debug('Data submission - No detected Expected %j got %j', sampleMetric, msg, {});
            return callback(false);
        }
    };

};
var init = function(connector, logger) {
    return new Data(connector, logger);
};
module.exports.init = init;
