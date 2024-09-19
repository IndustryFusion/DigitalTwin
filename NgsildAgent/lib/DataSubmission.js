/*
Copyright (c) 2014, 2023 Intel Corporation

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
const schemaValidation = require('./schema-validator');
const dataSchema = require('./schemas/data');
const config = require('../config');
const DbManager = require('./DbManager');
const validate = require('validate-iri');

/**
 *
 * @type {{n: string, v: number}}
 */
// const sampleMetric = {
//   n: '<uri>',
//   v: 'value'
// };

class DataSubmission {
  constructor (connector, logger) {
    this.logger = logger;
    this.connector = connector;
    this.validator = schemaValidation.validateSchema(dataSchema);
    this.sessionIsOnline = 1;
  }

  /**
     * It will process a component registration if
     * it is not a component registration will return false
     * @param msg
     * @returns {boolean}
     */
  getSubmissionCallback () {
    const me = this;
    return async function (msgs) {
      if (!Array.isArray(msgs)) {
        msgs = [msgs];
      }
      let msgKeys = [];
      const toTransmitMsgs = await Promise.all(msgs.map(async msg => {
        if (validate.validateIri(msg.n)) {
          me.logger.warn(`Metric name ${msg.n} not an IRI. Ignoring message.`);
          return;
        }
        if (msg.t === 'PropertyJson') {
          try {
            JSON.parse(msg.v);
          } catch {
            me.logger.warn(`Metric name ${msg.n} with ${msg.v} not a parsable JSON object. Ignoring message.`);
            return;
          }
        }
        if (msg.t === undefined || msg.t === null) {
          msg.t = 'Property';
        }
        if (msg.d !== undefined && msg.d !== null) {
          const datasetId = msg.d;
          delete msg.d;
          if (validate.validateIri(datasetId)) {
            me.logger.warn(`DatasetId ${datasetId} not an IRI. Will ignore datasetId value`);
          } else {
            msg.properties = {};
            msg.properties.values = [datasetId];
            msg.properties.keys = ['datasetId'];
          }
        }
        if (msg.on === undefined || msg.on === null) {
          msg.on = new Date().getTime();
        }
        const validationResult = me.validator(msg);
        if (validationResult === null) {
          try {
            await me.dbManager.preInsert(msg, 1);
          } catch (e) {
            me.logger.warn('Error in local database: ' + e.message);
          }
          msgKeys.push({ n: msg.n, on: msg.on });
          msg.n = msg.t + '/' + msg.n;
          delete msg.t;
        } else {
          me.logger.warn(`Data submission - Validation failed. ${JSON.stringify(validationResult)}`);
          try {
            await me.dbManager.preInsert(msg, 0);
          } catch (e) {
            me.logger.warn('Error in local database: ' + e.message);
          }
          return;
        }
        return msg;
      }));
      msgs = toTransmitMsgs.filter(msg => (msg !== undefined));
      if (msgs === undefined || msgs === null) {
        return;
      }
      me.logger.info('Submitting: ', msgs);
      // Check online state
      const isOnline = await me.connector.checkOnlineState();
      if (isOnline) {
        if (me.sessionIsOnline === 0) { // if session was offline, go into catch-up mode
          if (me.dbManager.isEnabled()) {
            me.sessionIsOnline = 2; // 2 means online but catch up
          } else {
            me.sessionIsOnline = 1;
          }
        }
      } else {
        me.sessionIsOnline = 0;
      }
      if (me.sessionIsOnline === 2 && me.dbManager.isEnabled()) {
        // We are in the catch-up mode
        // All relevant should be in database,
        // so fetch it and ignore original messages.
        try {
          const result = await me.dbManager.mostRecentPropertyUpdateStrategy();
          msgs = [];
          msgKeys = [];
          for (const msg of result.msgs) {
            msgKeys.push({ n: msg.n, on: msg.on });
            msgs.push({ n: msg.t + '/' + msg.n, on: msg.on, v: msg.v });
          }
          if (result.finished) {
            me.sessionIsOnline = 1;
          }
        } catch (e) {
          me.logger.warn('Error in local database: ' + e);
        }
      }
      if (config.connector.mqtt.sparkplugB && me.sessionIsOnline > 0) {
        try {
          await me.connector.dataSubmit(msgs);
          try {
            await me.dbManager.acknowledge(msgKeys);
          } catch (e) {
            me.logger.warn('Error in local database: ' + e);
          }
        } catch (err) {
          me.sessionIsOnline = 0;
          me.logger.warn('Could not submit sample: ' + err);
        }
      }
    };
  }

  async init () {
    this.dbManager = new DbManager(config);
    await this.dbManager.init();
    // return new Data(connector, logger, dbManager);
  };
};
module.exports = DataSubmission;
