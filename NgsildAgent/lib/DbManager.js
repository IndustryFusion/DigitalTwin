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
'use strict';

const sqlite3 = require('sqlite3').verbose();
const housekeepingIntervalDefault = 3600000;
const tableName = 'metrics';
const retentionDefault = 3600;


async function housekeeping (retention, db) {
    console.log(`dbManager housekeeping. Deleteing samples older than ${retention}s.`);
    const statement = `DELETE FROM ${tableName} where \`on\` < strftime('%s', 'now') * 1000-${retention} * 1000;` 
    return new Promise((resolve, reject) =>
        db.run(statement, error => { 
            if (error) {
                reject(error)
            } else {
                resolve()
            }
        })
    )
}


class DbManager{

    constructor(config){
        this.config = config;

    }

    async init () {
        return new Promise((resolve, reject) => {
            const me = this;
            const dataDir = this.config.data_directory;
            const file = dataDir + '/' + this.config.dbManager.file;
            this.db = new sqlite3.Database(file, sqlite3.OPEN_READWRITE | sqlite3.OPEN_CREATE | sqlite3.OPEN_FULLMUTEX, (error) => {
                if (error) {
                    reject(error);
                } else {
                    me.db.run(`CREATE TABLE IF NOT EXISTS ${tableName} (n TEXT, v TEXT, \`on\` TIMESTAMP, t TEXT, sent INTEGER, valid INTEGER)`, error => {
                        if (error) {
                            reject(error);
                        } else {
                            resolve()
                        }
                    });
                }
            });
            let retention = this.config.dbManager.retentionInSeconds || retentionDefault;
            let housekeepingInterval = this.config.dbManager.housekeepingIntervalInSeconds * 1000 || housekeepingIntervalDefault;
            console.log(`DBManager setup with housekeeping interval ${housekeepingInterval}ms and retention ${retention}s`)
            this.intervalId = setInterval(housekeeping, housekeepingInterval, retention, this.db)
        });
    }
    
    async preInsert(msg, valid) {
        return new Promise((resolve, reject) =>
            this.db.run(`INSERT INTO ${tableName} VALUES ('${msg.n}', '${msg.v}', '${msg.on}', '${msg.t}', 0, ${valid})`, error => { 
                if (error) {
                    reject(error)
                } else {
                    resolve()
                }
            })
        )
    }
    async acknowledge(msgs) {
        return new Promise((resolve, reject) => {
            let conditions = '';
            let first = true;
            for (const msg of msgs) {
                if (first) {
                    first = false;
                } else {
                    conditions += ' or '
                }
                conditions += `(\`on\` = ${msg.on} and n = '${msg.n}')`;
            }
            const statement = `UPDATE ${tableName} SET sent = 1 where ${conditions}`;
            this.db.run(statement, error => { 
                if (error) {
                    reject(error)
                } else {
                    resolve()
                }
            })
        })
    }
    async mostRecentPropertyUpdateStrategy() {
        return new Promise((resolve,reject) => {
            const statement = `select * from ${tableName} where (n, \`on\`, sent) in  (select  n, MAX(\`on\`), sent from metrics group by n) and sent = 0;`
            this.db.all(statement, (error, rows) => {
                if (error) {
                    reject(error);
                } else {
                    resolve({msgs: rows, finished: true})
                }
            })
        });
    }
}

module.exports = DbManager;