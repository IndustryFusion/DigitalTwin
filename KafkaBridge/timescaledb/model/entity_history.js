/**
* Copyright (c) 2023 Intel Corporation
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*    http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/

'use strict';
// Include Sequelize module.
const { Sequelize } = require('sequelize');
// Sequelize tsdb connect instance
const sequelize = require('../utils/tsdb-connect');
const config = require('../../config/config.json');

// CREATE table/model in tsdb to enter SpB NGSI_LD data
// Define method takes two arguments
// 1st - name of table, 2nd - columns inside the table
const entityHistoryTable = sequelize.define(config.timescaledb.entityTablename, {

  id: { type: Sequelize.TEXT, allowNull: false, primaryKey: true },
  observedAt: { type: Sequelize.DATE, allowNull: false, primaryKey: true },
  modifiedAt: { type: Sequelize.DATE, allowNull: false },
  type: { type: Sequelize.TEXT, allowNull: false },
  deleted: { type: Sequelize.BOOLEAN, allowNull: true }

}, {
  // disabled for a model auto timestamping with createAt and ModifiedAt as we take value from Kafka
  timestamps: false,
  freezeTableName: true
});

module.exports = entityHistoryTable;
