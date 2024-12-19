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

const { Sequelize } = require('sequelize');
const config = require('../../config/config.json');

let sequelize;
const postgPassword = process.env.POSTGRES_PASSWORD || config.timescaledb.password;
const postgHostname = process.env.POSTGRES_SERVICE || config.timescaledb.hostname;
const postgPort = process.env.POSTGRES_PORT || config.timescaledb.port;

if (config.timescaledb.PGSSLMODE === "require") {
    sequelize = new Sequelize(config.timescaledb.dbname, config.timescaledb.username, postgPassword, {
        host: postgHostname,
        port: postgPort,
        dialect: 'postgres',
        dialectOptions: {
        ssl: {
            rejectUnauthorized: false
            }
        },
     });
} else {
    sequelize = new Sequelize(config.timescaledb.dbname, config.timescaledb.username, postgPassword, {
        host: postgHostname,
        port: postgPort,
        dialect: 'postgres'
    });
}

module.exports = sequelize;