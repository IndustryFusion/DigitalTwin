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


// CREATE table/model in tsdb to enter SpB NGSI_LD data
// Define method takes two arguments
// 1st - name of table, 2nd - columns inside the table
const entityHistoryTable = sequelize.define( "entityhistories", {
     
    // Column-1, observedAt is an object with kafka timestamp to date Data_Type UTC timestamp
    observedAt:{ type:Sequelize.DATE, allowNull:false, primaryKey:true },

    // Same as observedAt for now-> Later we modify
    modifiedAt: { type:Sequelize.DATE, allowNull:false }, 
  
    // Column-2, entityId 
    entityId: { type: Sequelize.TEXT, allowNull:false },
  
    // Column-3, attributeId-> full name as URI
    attributeId: { type: Sequelize.TEXT, allowNull:false },

    // Column-4, attributeType-> Relaionship or properties
    attributeType: { type: Sequelize.TEXT, allowNull:false },
  
    // Column-5, datasetId-> entityid+name(Must be URI)
    datasetId: { type: Sequelize.TEXT, allowNull:false, primaryKey:true },

    nodeType: { type: Sequelize.TEXT, allowNull:false },

    value: { type: Sequelize.TEXT, allowNull:false },
    
    // In future can be used for literals value types
    valueType: { type: Sequelize.TEXT, allowNull:true },

    // Useful when we have array
    index: { type: Sequelize.INTEGER, allowNull:false },
    
    }, {
    // disabled for a model auto timestamping with createAt and ModifiedAt as we take value from Kafka
    timestamps: false
      
})

module.exports = entityHistoryTable ;