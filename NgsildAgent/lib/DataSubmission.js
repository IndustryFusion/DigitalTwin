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
const DbManager = require('./DbManager')

/**
 *
 * @type {{n: string, v: number}}
 */
var sampleMetric = {"n": "<uri>",
                    "v": "value" };



class DataSubmission {

    constructor(connector, logger) {
        this.logger = logger;
        this.connector = connector;
        this.validator = schemaValidation.validateSchema(schemaValidation.schemas.data.SUBMIT);
        this.sessionIsOnline = 1;
    }
    /**
     * It will process a component registration if
     * it is not a component registration will return false
     * @param msg
     * @returns {boolean}
     */
    async submission (msgs) {
        if (! Array.isArray(msgs)) {
            msgs = [msgs]
        }
        let msgKeys=[];
        for (const msg of msgs) {
            if (msg.t === undefined || msg.t === null) {
                msg.t = "Property"
            }
            if (msg.on === undefined || msg.on === null) {
                msg.on = new Date().getTime();
            }
            if (this.validator(msg)) {
                try {
                    await dbManager.preInsert(msg, 1)
                } catch (e) {
                    this.logger.warn("Error in local database: " + e.message)
                }
                msgKeys.push({n: msg.n, on: msg.on});
                msg.n = msg.t + '/' + msg.n;
                delete msg.t;
            } else {
                this.logger.debug(`Data submission - Validation failed. Expected something like ${sampleMetric} got ${msg}`);
                try {
                    await dbManager.preInsert(msg, 0)
                } catch (e) {
                    this.logger.warn("Error in local database: " + e.message)
                }
                return callback(false);
            }
        }
        this.logger.info ("Submitting: ", msgs);
        // Check online state
        const isOnline = await this.connector.checkOnlineState();
        if (isOnline) {
            if (this.sessionIsOnline === 0) { // if session was offline, go into catch-up mode
                this.sessionIsOnline = 2; // 2 means online but catch up
            }
        } else {
            this.sessionIsOnline = 0;
        }
        if (config.connector.mqtt.sparkplugB && this.sessionIsOnline > 0) {
            try {
                await this.connector.dataSubmit(msgs);
                try {
                    await this.dbManager.acknowledge(msgKeys)
                } catch (e) {
                    this.logger.warn("Error in local database: " + e)
                }
                
            } catch(err) {
                this.sessionIsOnline = 0;
                this.logger.warn("Could not submit sample: " + err);
            }
        }
    };

    async init () {
        this.dbManager = new DbManager(config)
        await this.dbManager.init()
        //return new Data(connector, logger, dbManager);
    };
};
module.exports = DataSubmission;
