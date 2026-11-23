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

"""Running a package's tests without the network.

openspec change gh-943-offline-package-tests, capabilities
`contracts/kms-package` and `semforge-sdk/package-tools`.

A package's tests (`semforge verify --tests`, `semforge publish`) run offline;
`--allow-network` only lets them fetch remote JSON-LD contexts and NGSI-LD
vocabularies. Each check decides on what is really parsed or opened, never on
a reading of its own that rdflib may not share:

    SPARQL SERVICE    every SPARQL text of the shapes is parsed with rdflib's
                      own grammar before anything runs, and a federated query
                      in the parse tree -- or a text that does not parse --
                      fails the tests, naming its owner (`refuse_services`).
                      While the tests run, rdflib's evaluation of SERVICE is
                      replaced by a refusal as well.
    JSON-LD contexts  `resolve_context` RETURNS the document or refuses; rdflib
                      opens nothing. The document is the package's own local
                      context (for its published URL), one the SDK pins
                      (`PINNED`), a file it found inside the package, or one
                      `_fetch` brought over http(s).
    everything else   an audit hook (`sys.addaudithook`, the mechanism rdflib's
                      security notes recommend) refuses every socket
                      connection, name lookup and urllib request of the thread
                      inside an `offline` scope, but `_fetch`'s own.

Code on the way may swallow an exception and go on with half an answer, so
every refusal is also kept on the scope, and `run_tests` fails on it. Audit
hooks cannot be removed; it and the SERVICE guard are installed once and do
nothing outside a scope.
"""

import contextlib
import copy
import hashlib
import json
import os
import stat
import sys
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse
from urllib.request import url2pathname

from ..errors import PackageError

ALLOW = '--allow-network'

# Contexts the SDK answers itself: url -> (file in contexts/, its sha256).
# The digest is checked on every read, so a pinned context cannot drift from
# what was reviewed. The NGSI-LD core context v1.8 is the file its URL serves,
# byte for byte; the same JSON (with LF line endings) is
# coreContext/ngsi-ld-core-context-v1.8.jsonld in
# https://forge.etsi.org/rep/data/ngsi-ld-openapi at tag v1.8.1 (commit
# db4324df). Copyright 2024 ETSI, BSD-3-Clause: contexts/LICENSE-ETSI-BSD-3-Clause,
# and Notice.md at the repository root.
PINNED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'contexts')
PINNED = {
    'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld': (
        'ngsi-ld-core-context-v1.8.jsonld',
        'sha256:4ac48e7d00cb0378546570ab0dbc46b3717da78ca4cb0fac98b0e32665046cca'),
}

# NGSI-LD vocabularies the SDK answers itself, the same way: url -> (file in
# vocabularies/, its sha256). The official one `semforge init` pins by
# default, byte for byte as its URL serves it: IndustryFusion's
# staging/ontology/v0.1/ngsild.ttl in github.com/IndustryFusion/contexts at
# commit 79edb472, under Apache-2.0 (IndustryFusion/contexts#74); the URL's v0
# is a link to it.
VOCABULARY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vocabularies')
PINNED_VOCABULARIES = {
    'https://industryfusion.github.io/contexts/staging/ontology/v0/ngsild.ttl': (
        'ngsild-staging-v0.ttl',
        'sha256:b4b2e04e2c7aba4fe97b7bff0af9c68636954d0ce575d1bbe0f0a80164bcb41e'),
}

# What an allowed fetch may cost: seconds, bytes, redirects.
FETCH_TIMEOUT = 30
FETCH_LIMIT = 16 * 1024 * 1024
FETCH_REDIRECTS = 5

_NETWORK_EVENTS = frozenset({
    'socket.connect', 'socket.sendto', 'socket.sendmsg', 'socket.getaddrinfo',
    'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.getnameinfo',
    'urllib.Request',
})


class NetworkRefused(PackageError):
    """Something in an offline scope tried to read what it may not."""


class TestsDoNotRun(PackageError):
    """Something other than a refusal kept the tests from running."""

    __test__ = False                               # not a pytest class


class ServiceRefused(PackageError):
    """The package's SPARQL uses SERVICE where it cannot run.

    `problems` holds one (subject, message) per constraint, rule or target
    concerned, so a report can name each one.
    """

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__('; '.join(f'{s}: {m}' if s else m for s, m in self.problems))


@dataclass
class _Scope:
    root: str
    contexts: dict = field(default_factory=dict)    # url -> document
    named: set = field(default_factory=set)         # urls the model names itself
    fetch_contexts: bool = False                    # --allow-network
    refusals: list = field(default_factory=list)    # every one, swallowed or not


_state = threading.local()
_hook_installed = False


def active():
    """The offline scope of this thread, or None."""
    return getattr(_state, 'scope', None)


def _refused(error):
    """Keep `error` on the scope, so a caller that swallows it changes nothing."""
    active().refusals.append(error)
    return error


def _hook(event, args):
    if event not in _NETWORK_EVENTS:
        return
    if getattr(_state, 'scope', None) is None:
        return
    target = str(args[0]) if args else ''
    if getattr(_state, 'fetching', False):
        # _fetch's own connection, and http(s) at every hop of it.
        if event != 'urllib.Request' or _scheme(target) in ('http', 'https'):
            return
    elif event == 'socket.connect' and len(args) > 1:
        target = args[1]
    raise _refused(NetworkRefused(
        f'network access refused while running the tests offline ({event} {target}); '
        f'only a JSON-LD context or an NGSI-LD vocabulary may be fetched, with {ALLOW}'))


def _install_service_guard():
    """Replace rdflib's evaluation of SERVICE, inside a scope, by a refusal.

    The scan before the run names the owner; this is for a query no scan sees,
    such as one put together while it runs.
    """
    from rdflib.plugins.sparql import evaluate

    original = evaluate.evalServiceQuery
    if getattr(original, '_semforge_guard', False):
        return

    def guarded(ctx, part):
        if active() is None:
            return original(ctx, part)
        raise _refused(ServiceRefused([('', _SERVICE.format(
            _service_target(part), _REMOTE))]))

    guarded._semforge_guard = True
    evaluate.evalServiceQuery = guarded


def _install_hook():
    global _hook_installed
    if not _hook_installed:
        sys.addaudithook(_hook)
        _hook_installed = True


@contextlib.contextmanager
def offline(root, contexts=None, named=(), fetch_contexts=False):
    """No network for this thread inside: see the module docstring.

    `root` is the package root: context files are read only from inside it.
    `contexts` maps a remote context URL to the document that answers it,
    beside the SDK's `PINNED` ones. `named` are the context URLs the
    package's model names as its own, for a refusal that says how to
    declare one in kms.yaml. `fetch_contexts` (--allow-network) lets any
    other remote context be fetched; nothing else reaches the network.
    """
    _install_hook()
    _install_service_guard()
    previous = active()
    _state.scope = scope = _Scope(os.path.realpath(root), dict(contexts or {}),
                                  set(named), fetch_contexts)
    try:
        yield scope
    finally:
        _state.scope = previous


def model_context_urls(root):
    """The remote context URLs the package's model names as its own.

    Those of each entity whose `@context` does not name the published context
    kms.yaml declares: the model then has no declared context of its own, and
    one of these is it.
    """
    from .conformance import check
    from .context import context_config

    published = context_config(root).published
    found = set()
    for relative in check(root).roles.get('model-instance', []):
        try:
            with open(os.path.join(root, relative), encoding='utf-8') as handle:
                document = json.load(handle)
        except (OSError, ValueError):
            continue
        for entity in document if isinstance(document, list) else [document]:
            value = entity.get('@context') if isinstance(entity, dict) else None
            items = value if isinstance(value, list) else [value]
            if published and published in items:
                continue
            for item in items:
                if isinstance(item, str) and item.startswith(('http://', 'https://')):
                    found.add(item)
    return found


def package_contexts(root):
    """{published url: local context document} for the package at `root`."""
    from .context import context_config, local_context_path

    config = context_config(root)
    path = local_context_path(root, config)
    if not config.declared or path is None:
        return {}
    with open(path, encoding='utf-8') as handle:
        return {config.published: json.load(handle)}


def _normal(url):
    """`url` with its scheme and host in lower case, as they compare."""
    parts = urlparse(url)
    return parts._replace(scheme=parts.scheme.lower(), netloc=parts.netloc.lower()).geturl()


def _shipped(table, folder, url, what):
    """(path, bytes) of the SDK's copy for `url`, hashed on every read, or None."""
    entry = table.get(_normal(url))
    if entry is None:
        return None
    name, digest = entry
    path = os.path.join(folder, name)
    with open(path, 'rb') as handle:
        raw = handle.read()
    actual = 'sha256:' + hashlib.sha256(raw).hexdigest()
    if actual != digest:
        raise PackageError(f'the {what} the SDK ships, {name}, has {actual}, '
                           f'not {digest}')
    return path, raw


def pinned(url):
    """The pinned context document for `url`, digest-checked, or None."""
    found = _shipped(PINNED, PINNED_DIR, url, 'context')
    return None if found is None else json.loads(found[1])


def shipped_vocabulary(url):
    """(path, bytes) of the pinned NGSI-LD vocabulary for `url`, or None."""
    return _shipped(PINNED_VOCABULARIES, VOCABULARY_DIR, url, 'NGSI-LD vocabulary')


def _scheme(source):
    return urlparse(source).scheme.lower()


def _open_http(url, accept):
    """The response for `url`: http(s) at every hop, nothing else followed."""
    from urllib import request
    from urllib.error import HTTPError

    class Redirect(request.HTTPRedirectHandler):
        max_redirections = FETCH_REDIRECTS

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if _scheme(newurl) not in ('http', 'https'):
                raise HTTPError(req.full_url, code, f'redirect to {newurl}, which is '
                                f'not an http(s) URL', headers, fp)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    # Built by hand: build_opener would add file, ftp and data handlers.
    opener = request.OpenerDirector()
    for handler in (request.ProxyHandler(), request.UnknownHandler(),
                    request.HTTPHandler(), request.HTTPSHandler(),
                    request.HTTPDefaultErrorHandler(), Redirect(),
                    request.HTTPErrorProcessor()):
        opener.add_handler(handler)
    # A named agent: the ETSI server answers urllib's own with 403 Forbidden.
    return opener.open(request.Request(url, headers={
        'Accept': accept,
        'User-Agent': 'semforge (+https://github.com/IndustryFusion/DigitalTwin)'}),
        timeout=FETCH_TIMEOUT)


def _fetch(url, accept):
    """The bytes at an http(s) `url`, the one fetch --allow-network allows."""
    if _scheme(url) not in ('http', 'https'):
        raise _refused(NetworkRefused(f'{url} is not an http(s) URL'))
    _state.fetching = True
    try:
        deadline = time.monotonic() + FETCH_TIMEOUT
        with _open_http(url, accept) as response:
            raw = b''
            while True:
                part = response.read1(65536)
                if not part:
                    if response.length:
                        raise ValueError('the answer is incomplete')
                    return raw
                raw += part
                if len(raw) > FETCH_LIMIT:
                    raise ValueError(f'the answer is larger than {FETCH_LIMIT} bytes')
                if time.monotonic() > deadline:
                    raise ValueError(f'the answer took longer than {FETCH_TIMEOUT} s')
    except PackageError:
        raise
    except Exception as exc:                       # noqa: BLE001 -- whatever the server did
        raise PackageError(f'{url} could not be fetched: {_reason(exc)}') from exc
    finally:
        _state.fetching = False


def _reason(exc):
    text = (str(exc).strip().splitlines() or [''])[0]
    return f'{type(exc).__name__}: {text}' if text else type(exc).__name__


def dependency_bytes(url):
    """(where, bytes) of a remote dependency of a test run: the SDK's pinned
    copy, or fetched when --allow-network allows; refused, named, otherwise."""
    found = shipped_vocabulary(url)
    if found is not None:
        return found
    if active().fetch_contexts:
        return url, _fetch(url, 'text/turtle, */*;q=0.1')
    raise _refused(NetworkRefused(
        f'{url} is not shipped with the SDK, and the tests run offline; run with '
        f'{ALLOW} to fetch it'))


def _context_file(scope, source):
    """The bytes of the context file `source` names, inside the package.

    The name is everything after `file://`, unquoted, `#` and `?` included --
    what rdflib would open -- resolved through every link, and read here.
    """
    try:
        where = os.path.realpath(url2pathname(source[len('file://'):]))
        inside = os.path.commonpath([where, scope.root]) == scope.root
    except (ValueError, OSError) as exc:
        raise _refused(NetworkRefused(
            f'the JSON-LD context {source} is not a file name: {_reason(exc)}')) from exc
    if not inside:
        raise _refused(NetworkRefused(f'the JSON-LD context {source} is outside the '
                                      f'package {scope.root}'))
    try:
        # O_NOFOLLOW: what was checked is what is opened; O_NONBLOCK: a pipe
        # does not hold the run up before it is refused.
        handle = os.open(where, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(handle, 'rb') as opened:
            if not stat.S_ISREG(os.fstat(opened.fileno()).st_mode):
                raise OSError('not a regular file')
            return opened.read()
    except OSError as exc:
        raise PackageError(f'the JSON-LD context {source} cannot be read: '
                           f'{_reason(exc)}') from exc


def _document(source, raw):
    try:
        return json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise PackageError(f'the JSON-LD context {source} is not JSON: '
                           f'{_reason(exc)}') from exc


def resolve_context(source):
    """The document of a JSON-LD context named inside an offline scope.

    Always the document, or an error naming `source`: nothing is left for
    rdflib to open. A copy each time, since rdflib merges into an imported one.
    """
    scope = active()
    try:
        scheme = _scheme(source)
        known = _normal(source) if scheme in ('http', 'https') else ''
    except (AttributeError, TypeError, ValueError) as exc:
        raise _refused(NetworkRefused(
            f'the JSON-LD context {source} is not a URL: {_reason(exc)}')) from exc
    if scheme in ('http', 'https'):
        for url in (source, known):
            if url in scope.contexts:
                return copy.deepcopy(scope.contexts[url])
        document = pinned(source)
        if document is not None:
            return document
        if scope.fetch_contexts:
            return _document(source, _fetch(
                source, 'application/ld+json, application/json;q=0.9, */*;q=0.1'))
        if source in scope.named:
            raise _refused(NetworkRefused(
                f'the model names {source} as its context, and kms.yaml does '
                f'not declare it as the package\'s own: add `published: {source}` '
                f'under `context:` in kms.yaml, with `local:` naming the file '
                f'that holds it (default context.jsonld); or run with {ALLOW} '
                f'to fetch it'))
        raise _refused(NetworkRefused(
            f'the JSON-LD context {source} is neither the package\'s own nor pinned '
            f'by the SDK, and the tests run offline; run with {ALLOW} to fetch it'))
    # file:///<path> and nothing else: no host, no path without a root.
    if source[:8].lower() == 'file:///':
        return _document(source, _context_file(scope, source))
    raise _refused(NetworkRefused(
        f'the JSON-LD context {source} is neither a file inside the package nor an '
        f'http(s) URL, which is all a test run reads'))


# -- SERVICE -----------------------------------------------------------------

_SERVICE = 'uses SPARQL SERVICE {}, which a package cannot use: {}'
_REMOTE = 'a package\'s results must not depend on a remote endpoint'
_PREBOUND = 'SHACL does not allow SERVICE in a SPARQL constraint'
_PATH = '<urn:semforge:path>'


def _service_target(part):
    """What a ServiceGraphPattern of rdflib's parse tree names."""
    term = part.get('term')
    if getattr(term, 'name', '') == 'pname':
        # dict.get: CompValue.get answers a missing key with its name.
        return f'{dict.get(term, "prefix", "")}:{dict.get(term, "localname", "")}'
    return term.n3() if hasattr(term, 'n3') else str(term)


def _service_patterns(node):
    """Every ServiceGraphPattern below `node` of a parse tree, in order.

    Every mapping and sequence is entered, whatever the grammar calls it, and
    without recursion: a deep query must not end the search.
    """
    from pyparsing import ParseResults

    found, todo = [], [node]
    while todo:
        node = todo.pop()
        if getattr(node, 'name', None) == 'ServiceGraphPattern':
            found.append(node)
        if isinstance(node, dict):
            todo.extend(reversed(list(node.values())))
        elif isinstance(node, (list, tuple, set, ParseResults)):
            todo.extend(reversed(list(node)))
    return found


def services(text, update=False):
    """The targets of every SERVICE in a SPARQL text, as rdflib parses it.

    Raises what rdflib raises for a text it cannot parse. Escapes, comments
    and spellings are the grammar's business, not this function's.
    """
    from rdflib.plugins.sparql.parser import parseQuery, parseUpdate

    tree = (parseUpdate if update else parseQuery)(text)
    return [_service_target(part) for part in _service_patterns(tree)]


def _as_run(graph, node, text):
    """The texts the SHACL engine may make of `text`: the declared prefixes in
    front, as pyshacl writes them, and `$PATH` in a constraint put in as a path."""
    from pyshacl.helper.sparql_query_helper import SPARQLQueryHelper
    from rdflib.namespace import OWL, RDF, SH

    prologue = []
    if (node, SH.prefixes, None) in graph:
        holders = set(graph.objects(node, SH.prefixes)) | \
            set(graph.subjects(RDF.type, OWL.Ontology))
        declared = {(str(graph.value(d, SH.prefix)), str(graph.value(d, SH.namespace)))
                    for holder in holders for d in graph.objects(holder, SH.declare)}
        prologue = [f'PREFIX {p}: <{n}>\n' for p, n in sorted(declared)]
    text = ''.join(prologue) + text
    with_path = SPARQLQueryHelper.bind_path_regex.sub(rf'\g<1>{_PATH}', text)
    return [text] if with_path == text else [text, with_path]


def _services_as_run(graph, node, text, update):
    """The services of a text in any form it runs in; raises when none parses."""
    found, error = None, None
    for written in _as_run(graph, node, text):
        try:
            found = (found or []) + services(written, update)
        except Exception as exc:                   # noqa: BLE001 -- the parser's, any
            error = exc
    if found is None:
        raise error
    return found


def network_uses(package):
    """[(subject, target, constraint)]: each SERVICE in the shapes' SPARQL.

    The subject names what owns the query the way a report names it: a SPARQL
    constraint as `<shape>/SPARQLConstraintComponent`, like coverage does, a
    rule or a target by its shape, a constraint component's validator by its
    IRI. `constraint` is True for the queries SHACL pre-binds -- SPARQL
    constraints and validators -- in which SHACL does not allow SERVICE. A
    text that does not parse has the parser's error as its target.
    """
    from rdflib.namespace import SH

    from ..validate.normalise import curie

    graph = package.shapes
    owners = ((SH.sparql, '{}/SPARQLConstraintComponent', True),
              (SH.validator, '{}', True), (SH.nodeValidator, '{}', True),
              (SH.propertyValidator, '{}', True),
              (SH.rule, '{} (rule)', False), (SH.target, '{} (target)', False))
    found = set()
    for predicate in (SH.select, SH.ask, SH.construct, SH.update):
        for node, text in graph.subject_objects(predicate):
            try:
                targets = _services_as_run(graph, node, str(text), predicate == SH.update)
            except Exception as exc:               # noqa: BLE001 -- the parser's, any
                targets = [exc]
            if not targets:
                continue
            subject, constraint = '', False
            for link, form, prebound in owners:
                owner = next(iter(graph.subjects(link, node)), None)
                if owner is not None:
                    subject, constraint = form.format(curie(graph, owner)), prebound
                    break
            subject = subject or curie(graph, node) or 'a SPARQL query'
            found.update((subject, t, constraint) for t in targets)
    return sorted(found, key=lambda use: (use[0], str(use[1])))


def refuse_services(package):
    """Raise ServiceRefused for every SERVICE in the package's SPARQL.

    Refused everywhere, with the network allowed too: SHACL does not allow
    SERVICE in a SPARQL constraint (pyshacl refuses it), the platform's
    validation cannot run it, and a package's results must not depend on a
    remote endpoint. SPARQL that does not parse is refused as well: what it
    would do is not known. Nothing has run when this raises.
    """
    problems = []
    for subject, target, constraint in network_uses(package):
        if isinstance(target, Exception):
            problems.append((subject, f'SPARQL that does not parse, so the tests do '
                                      f'not run: {_reason(target)}'))
        else:
            problems.append((subject, _SERVICE.format(
                target, _PREBOUND if constraint else _REMOTE)))
    if problems:
        raise ServiceRefused(problems)
