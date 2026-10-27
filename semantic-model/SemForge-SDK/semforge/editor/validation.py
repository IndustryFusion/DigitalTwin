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

"""Diagnostics and verdicts: what the editor says is wrong, and when.

Findings are published per document; the package's validation runs in the
background (verdicts.py), and pages that show verdicts are answered at once
with what is known, the worker's notification bringing the client back.
"""

import asyncio

from lsprotocol import types

from . import session
from .analysis import package_root
from .protocol import path_to_uri, server, uri_to_path


SEVERITY = {
    'error': types.DiagnosticSeverity.Error,
    'warning': types.DiagnosticSeverity.Warning,
    'information': types.DiagnosticSeverity.Information,
    'hint': types.DiagnosticSeverity.Hint,
}


_offered = set()            # roots whose cached verdicts went to the Problems panel
_published = {}            # root -> uris that were last sent findings


def findings_of(root):
    """{file: [EditorFinding]}: what the validation worker found, never computed here.

    The diagnostics are worked out with the verdicts (editor/incremental.py),
    in the background. Here they are only read: the last ones the worker
    finished, while it works on the next -- they arrive with
    `_notify_verdicts`, which publishes again. Computed on this thread they
    held every edit request, and the whole editor, for 5 s on the OPC UA pumps.
    """
    from .analysis import EditorFinding

    session.warm(root)
    verdicts, _ = verdicts_for(root)
    stored = (verdicts.findings if verdicts is not None else None) or {}
    return {path: [EditorFinding(**f) for f in items]
            for path, items in stored.items()}


def publish(ls, uri):
    """Analyse the package this file belongs to and publish its diagnostics."""
    path = uri_to_path(uri)
    root = package_root(path)
    if root is None:
        ls.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=uri, diagnostics=[]))
        return
    try:
        findings = findings_of(root)
    except Exception as exc:                       # noqa: BLE001
        # A broken package must not silence the server: report the failure as a
        # diagnostic rather than leaving the editor showing a clean file.
        ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
            uri=uri, diagnostics=[types.Diagnostic(
                range=types.Range(types.Position(0, 0), types.Position(0, 1)),
                message=f'semforge could not analyse this package: {exc}',
                severity=types.DiagnosticSeverity.Error, source='semforge')]))
        return

    for file_path, items in findings.items():
        diagnostics = []
        for finding in items:
            line = max(finding.line - 1, 0)
            diagnostics.append(types.Diagnostic(
                range=types.Range(types.Position(line, 0),
                                  types.Position(line, 200)),
                message=finding.message,
                severity=SEVERITY.get(finding.severity,
                                      types.DiagnosticSeverity.Information),
                source=f'semforge ({finding.kind})',
                code=finding.code or None,
                # Round-trips through the client untouched: the quick fix
                # reads it back from the diagnostic it was offered on.
                data=finding.data))
        ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
            uri=path_to_uri(file_path), diagnostics=diagnostics))

    # A file that HAD findings and has none now must be told so: an LSP client
    # keeps the last list it was sent per document, so fixing the last problem
    # in a .jsonld would leave its squiggle standing forever.
    now = {path_to_uri(path) for path, items in findings.items() if items}
    for stale in _published.get(root, set()) - now:
        ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
            uri=stale, diagnostics=[]))
    _published[root] = now
    republish_queries(ls)


def republish_queries(ls):
    """Open SPARQL query documents are checked against the package's terms
    and shapes: when the package changed, so may their squiggles -- a quick
    fix that adds a shape must take the warning it fixed away."""
    from .sparqldocs import is_query

    try:
        open_uris = list(ls.workspace.text_documents)
    except Exception:                              # noqa: BLE001
        return
    for uri in open_uris:
        if is_query(uri):
            publish_query(ls, uri)


def _query_context(uri):
    from .sparqldocs import context
    return context(uri, session.package_for, package_root, uri_to_path)


def publish_query(ls, uri):
    """Squiggles for a query document, from its text as it is now."""
    from .sparqldocs import diagnostics

    try:
        ctx = _query_context(uri)
        found = diagnostics(ls.workspace.get_text_document(uri).source, ctx) if ctx else []
    except Exception as exc:                       # noqa: BLE001
        found = [types.Diagnostic(
            range=types.Range(types.Position(0, 0), types.Position(0, 1)),
            message=f'semforge could not check this query: {exc}',
            severity=types.DiagnosticSeverity.Warning, source='semforge-sparql')]
    ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
        uri=uri, diagnostics=found))


_verdict_service = None
_loop = None             # the server's event loop, for the worker's notifications


def service():
    global _verdict_service
    if _verdict_service is None:
        from .cache import fingerprint
        from .verdicts import ProcessRunner, VerdictService
        _verdict_service = VerdictService(fingerprint, ProcessRunner(), _notify_verdicts)
    return _verdict_service


def verdicts_for(root):
    """(Verdicts or None, State) for a package -- never waits for a validation.

    Called from request handlers, which run on the event loop: that is where
    the loop is taken from, so the worker thread can hand its notification
    back to it rather than write to the client from a second thread.
    """
    global _loop
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        pass
    found = service().get(root)
    # Verdicts from the disk cache bring no notification: the first time a
    # page asks for them, the Problems panel gets them too.
    if found[1].state == 'ready' and root not in _offered and _loop is not None:
        _offered.add(root)
        _loop.call_soon(_republish, root)
    return found


def verdict_page(root, key, build):
    """A page that shows verdicts, answered without waiting for them.

    `build(verdicts)` makes the payload. With current verdicts the page is
    cached like any view; otherwise it is built from the last known ones
    (stale) or none (PENDING) and not cached -- the `semforge/verdicts`
    notification brings the client back for the real one.
    """
    from ..cooked.typepage import PENDING

    session.warm(root)
    verdicts, state = verdicts_for(root)
    if state.state == 'ready':
        page = session.view(root, key, lambda: {'page': build(verdicts)})
        payload, cached = page['page'], page['cached']
    else:
        payload = build(verdicts if verdicts is not None else PENDING)
        cached = False
    return dict(payload, ok=True, root=root, cached=cached, verdicts=state.as_dict())


def _notify_verdicts(root, state):
    """The worker finished (or must start over): tell the client, on the loop."""
    from .verdicts import NOTIFICATION

    if _loop is None or _loop.is_closed():
        return
    _loop.call_soon_threadsafe(server.protocol.notify, NOTIFICATION,
                               dict(state.as_dict(), root=root))
    if state.state == 'ready':
        _loop.call_soon_threadsafe(_republish, root)


def _republish(root):
    """The verdicts are in: the package's diagnostics again, now with them --
    whether or not one of its files is open. The pages and views are where a
    package is worked on; waiting for an open .ttl left the Problems panel
    empty while the Main page counted violations."""
    try:
        for uri in list(server.workspace.text_documents):
            path = uri_to_path(uri)
            if path and package_root(path) == root:
                publish(server, uri)
                return
        shapes = session.package_for(root).files('shapes')
        if shapes:
            publish(server, path_to_uri(shapes[0]))
    except Exception:                              # noqa: BLE001 -- no client, no panel
        pass
