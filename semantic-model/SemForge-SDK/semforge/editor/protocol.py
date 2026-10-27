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

"""The server object and what every handler reads its requests with.

Architecture section 8.3: LSP is used where the operation IS an LSP
operation. A constraint tree and an edit-by-address are not, and forcing them
through workspace/executeCommand would make them opaque to any other client:
they are named `semforge/...` methods instead. The handlers live by what
they do -- documents.py (the LSP features), views.py (requests
that read), edits.py (requests that write) -- over session.py (the loaded
package versions) and validation.py (diagnostics and verdicts).
"""

import os

from pygls.lsp.server import LanguageServer

from .. import __version__


server = LanguageServer('semforge', __version__)


def uri_to_path(uri):
    from urllib.parse import unquote, urlparse
    return unquote(urlparse(uri).path)


def path_to_uri(path):
    from urllib.request import pathname2url
    return 'file://' + pathname2url(os.path.abspath(path))


def local(iri):
    return str(iri).rstrip('/#').rsplit('/', 1)[-1].rsplit('#', 1)[-1]


def field(params, name, default=None):
    """Read a parameter whichever way pygls handed it over.

    Custom methods have no registered type, so pygls deserialises their params
    into a namedtuple-like object rather than a dict -- and a handler written
    for one shape fails on the other with a TypeError the client never sees.
    """
    if isinstance(params, dict):
        return params.get(name, default)
    value = getattr(params, name, default)
    # That object is a tuple underneath: a parameter the client did not send
    # and that shares a name with a tuple method -- `index`, `count` -- would
    # come back as the bound method, not as missing.
    return default if callable(value) else value


def serialise(node):
    return {
        'kind': node.kind, 'label': node.label, 'detail': node.detail,
        'shape': node.shape, 'path': list(node.path_chain),
        'parameter': node.parameter, 'value': node.value,
        'editable': node.editable,
        'inheritedFrom': node.inherited_from,
        'inheritedClass': node.inherited_class,
        'definedAt': node.defined_at,
        'targetClass': node.target_class,
        'children': [serialise(child) for child in node.children],
    }


def holder_index(package, shape, params):
    """Which of a shape's queries: by its text when the page knows it (pages
    list them in graph order, not file order), else by `holder`."""
    from ..cooked.sparqlbench import holders, pick
    from ..errors import PackageError

    found = holders(package, shape)
    if not found:
        raise PackageError('this shape has no SPARQL query')
    return pick(found, field(params, 'holder'), field(params, 'query'),
                field(params, 'kind'))['index']
