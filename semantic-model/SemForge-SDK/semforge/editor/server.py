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

"""The SemForge language server: `python -m semforge.editor.server`.

A thin translation of the cooked layer into protocol objects -- nothing here
decides anything semantic (architecture.md section 8.4). The server object and
the request helpers are in protocol.py; the handlers register themselves by
what they do: documents.py (the LSP features), views.py (requests that read),
edits.py (requests that write), over session.py (the loaded package versions)
and validation.py (diagnostics and verdicts).
"""

from . import documents, edits, views  # noqa: F401 -- their handlers register on import
from .protocol import server


def main():
    server.start_io()


if __name__ == '__main__':
    main()
