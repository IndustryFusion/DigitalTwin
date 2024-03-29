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

const net = require('net');

exports.init = function (conf, logger, onMessage) {
  const tcpServerPort = conf.tcp_port || 7070;
  const tcpServerHost = '127.0.0.1';

  function processMessage (data) {
    try {
      onMessage(data);
    } catch (ex) {
      logger.error('TCP Error on message: ' + ex.message);
      logger.error(ex.stack);
    }
  }

  const server = net.createServer();
  server.listen(tcpServerPort, tcpServerHost);

  server.on('connection', function (socket) {
    logger.debug(`TCP connection from ${socket.remoteAddress}:${socket.remotePort}%d`);
    if (socket.remoteAddress !== '127.0.0.1') {
      logger.debug('Ignoring remote connection from ' + socket.remoteAddress);
      return;
    }

    socket.on('data', function (msg) {
      try {
        const data = JSON.parse(msg);
        logger.debug('Data arrived: ' + JSON.stringify(data));
        processMessage(data);
      } catch (err) {
        logger.warn('Parsing of message failed: ' + JSON.stringify(msg) + 'Message will be ignored.');
      }
    });
  });

  logger.info('TCP listener started on port: ' + tcpServerPort);
  return server;
};
