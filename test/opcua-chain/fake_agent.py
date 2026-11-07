#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Stands in for the device agent: records what the dataservice sends to its TCP port, one message per line."""
import json
import socketserver
import sys
import time

OUT = sys.argv[1]


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        data = self.rfile.read()
        with open(OUT, 'a') as f:
            for message in json.loads(data):
                message['_at'] = time.time()
                f.write(json.dumps(message) + '\n')


socketserver.ThreadingTCPServer.allow_reuse_address = True
socketserver.ThreadingTCPServer(('127.0.0.1', 7070), Handler).serve_forever()
