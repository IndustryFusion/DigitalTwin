"""Which context a model instance resolves against, and when.

A JSON-LD model names its `@context` by URL, and that one line decides three
different things depending on where the file is:

    working locally   the LOCAL context -- so a term can be used the moment it
                      is agreed, without waiting for a publication, and so a
                      build never depends on the network or on whatever the URL
                      happens to serve today
    exported          the PUBLISHED context -- because the broker, the compiler
                      and everyone else resolve it themselves, and a file
                      pointing at somebody's laptop is useless to them
    imported          rewritten back to local

So the package declares both, and the pointer is switched at the boundary
rather than committed to either side:

    context:
      local: context.jsonld
      published: https://…/v0.2/context.jsonld

The important part is what export does besides rewriting. It compares the terms
the model actually uses against the PUBLISHED context and refuses to pretend:
a term that exists locally and not upstream is exported as a value that will
not expand, and saying so at export time is the only moment anybody can act on
it.

Resolution happens in memory: the model on disk keeps naming the published URL,
and loading substitutes the local context's CONTENT for that URL before parsing.
Editing the file to point somewhere local would make the package useless to
everyone who resolves the URL themselves; fetching the URL would make every load
depend on the network and on whatever it serves today.

`semforge serve-context` exists for tools that genuinely need an HTTP URL rather
than a file.
"""

import json
import os
from dataclasses import dataclass, field

from ..errors import Diagnostic, PackageError

DEFAULT_LOCAL = 'context.jsonld'


@dataclass
class ContextConfig:
    local: str = DEFAULT_LOCAL
    published: str = ''

    @property
    def declared(self):
        return bool(self.published)


def context_config(package_path):
    """`context:` from semforge.yaml, defaulting to context.jsonld."""
    config_path = os.path.join(package_path, 'semforge.yaml')
    if not os.path.exists(config_path):
        return ContextConfig()
    from ruamel.yaml import YAML

    with open(config_path) as handle:
        data = YAML().load(handle) or {}
    section = data.get('context') or {}
    return ContextConfig(local=section.get('local', DEFAULT_LOCAL),
                         published=section.get('published', ''))


def local_context_path(package_path, config=None):
    config = config or context_config(package_path)
    path = os.path.join(package_path, config.local)
    return path if os.path.exists(path) else None


def local_context_value(package_path, config=None):
    """The `@context` value of the local context file, ready to inline."""
    config = config or context_config(package_path)
    path = local_context_path(package_path, config)
    if path is None:
        return None
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    return document.get('@context', document)


def resolve_model_document(package_path, model_path, config=None):
    """The model as JSON, with the published URL swapped for local content.

    Only the package's OWN published URL is replaced. A model that also
    references an external standard -- the NGSI-LD core context does exactly
    that, from inside the local context -- still resolves that normally, because
    substituting somebody else's vocabulary is not this function's business.
    """
    config = config or context_config(package_path)
    with open(model_path, encoding='utf-8') as handle:
        document = json.load(handle)
    inline = local_context_value(package_path, config)
    if inline is None or not config.declared:
        return document, False

    entities = document if isinstance(document, list) else [document]
    swapped = False
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        value = entity.get('@context')
        if value == config.published:
            entity['@context'] = inline
            swapped = True
        elif isinstance(value, list) and config.published in value:
            entity['@context'] = [inline if item == config.published else item
                                  for item in value]
            swapped = True
    return document, swapped


def model_context(path):
    """The `@context` value of a model instance, as written."""
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    entities = document if isinstance(document, list) else [document]
    for entity in entities:
        if isinstance(entity, dict) and '@context' in entity:
            return entity['@context']
    return None


def retarget_model(path, context_value, out_path=None):
    """Rewrite every `@context` in a model instance. Returns how many changed."""
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    entities = document if isinstance(document, list) else [document]

    changed = 0
    for entity in entities:
        if isinstance(entity, dict) and entity.get('@context') != context_value:
            entity['@context'] = context_value
            changed += 1

    target = out_path or path
    with open(target, 'w', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write('\n')
    return changed


CONTEXT_CACHE = os.path.join('.semforge', 'cache', 'contexts')
_fetched = {}           # url -> parsed document, for the life of the process


def context_cache_dir(package_path):
    return os.path.join(package_path, CONTEXT_CACHE)


def user_context_cache():
    """Where remote contexts are kept for every package on this machine.

    Per user rather than per package: the NGSI-LD core context is the same
    document whichever package names it, and fetching it once per package
    would be the cost this exists to remove, multiplied.
    """
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(
        os.path.expanduser('~'), '.cache')
    return os.path.join(base, 'semforge', 'contexts')


def install_context_cache():
    """Make rdflib fetch every remote @context through fetch_context.

    rdflib keeps fetched contexts only per Context object, and every parse
    makes a new one, so a document naming the NGSI-LD core context downloaded
    it on every parse: 44 downloads, 9 seconds, in one Knowledge-view build.
    Wrapping its one fetch function keeps every other behaviour -- the URL
    stays a URL, resolution and errors are rdflib's -- and removes the network
    after the first time. Idempotent.
    """
    from rdflib.plugins.shared.jsonld import context as jsonld_context

    original = jsonld_context.source_to_json
    if getattr(original, '_semforge_cached', False):
        return

    def cached(source, *args, **kwargs):
        if isinstance(source, str) and source.startswith(('http://', 'https://')):
            # rdflib does the download on a miss -- its request is the one the
            # servers already accept -- and what it gets is kept.
            document = fetch_context(
                source, user_context_cache(),
                download=lambda url: original(url, *args, **kwargs)[0])
            if document is not None:
                return document, None
        return original(source, *args, **kwargs)

    cached._semforge_cached = True
    jsonld_context.source_to_json = cached


def _download(url):
    """The raw bytes of a remote context. Named, with an Accept header: the
    ETSI server answers a bare urllib request with 403 Forbidden."""
    from urllib.request import Request, urlopen

    request = Request(url, headers={
        'Accept': 'application/ld+json, application/json;q=0.9, */*;q=0.1',
        'User-Agent': 'semforge (+https://github.com/IndustryFusion/DigitalTwin)'})
    with urlopen(request, timeout=30) as response:                # noqa: S310
        return response.read()


def fetch_context(url, cache_dir=None, download=None):
    """A remote JSON-LD context document: memory, then disk, then network.

    Fetched once and kept. rdflib fetches a remote @context on EVERY parse and
    keeps nothing, and the NGSI-LD core context is named by every document in
    a package -- one Knowledge-view build parsed the examples four times and
    downloaded it 44 times, which was 9 of its 11 seconds. Returns the parsed
    document, or None when it is neither cached nor reachable.
    """
    import hashlib
    from urllib.error import URLError

    if url in _fetched:
        return _fetched[url]
    cached = None
    if cache_dir:
        cached = os.path.join(cache_dir, hashlib.sha256(url.encode()).hexdigest()
                              + '.jsonld')
        if os.path.exists(cached):
            try:
                with open(cached, encoding='utf-8') as handle:
                    _fetched[url] = json.load(handle)
                return _fetched[url]
            except (OSError, ValueError):
                pass                       # a torn write; fetch it again
    try:
        if download is not None:
            document = download(url)
            raw = json.dumps(document).encode()
        else:
            raw = _download(url)
            document = json.loads(raw)
    except (URLError, OSError, ValueError):
        return None
    if not isinstance(document, (dict, list)):
        return None
    if cached:
        os.makedirs(cache_dir, exist_ok=True)
        ignore = os.path.join(cache_dir, '.gitignore')
        if not os.path.exists(ignore):
            with open(ignore, 'w', encoding='utf-8') as handle:
                handle.write('# Fetched @context documents: derived, never committed.\n*\n')
        with open(cached, 'wb') as handle:
            handle.write(raw)
    _fetched[url] = document
    return document


def published_terms(config, cache_dir=None):
    """{term: iri} the PUBLISHED context declares, fetched and cached."""
    if not config.published:
        return {}, 'no published context declared'
    document = fetch_context(config.published, cache_dir)
    if document is None:
        return {}, 'could not fetch the published context'
    return _terms(document), ''


def _terms(document):
    entries = document.get('@context', document)
    if not isinstance(entries, list):
        entries = [entries]
    found = {}
    for entry in entries:
        if isinstance(entry, dict):
            for name, value in entry.items():
                if isinstance(value, dict) and '@id' in value:
                    found[name] = value['@id']
                elif isinstance(value, str):
                    found[name] = value
    return found


def check_export_readiness(package, config=None, cache_dir=None):
    """Diagnostics for terms the model uses that the published context lacks.

    This is the moment the local/published split has to be paid for. Locally a
    term works as soon as the local context declares it; exported, it works only
    if the URL the file names declares it too.
    """
    from .prefixes import model_prefixes

    config = config or context_config(package.path)
    if not config.declared:
        return [Diagnostic(
            code='SF-CTX-000', category='package', severity='warning',
            message=('no published context declared in semforge.yaml; the '
                     'exported model will keep whatever @context it has'))]

    upstream, error = published_terms(config, cache_dir)
    if error:
        return [Diagnostic(code='SF-CTX-001', category='package',
                           severity='warning', message=error)]

    findings = []
    used = {}
    for document in package.files('model'):
        for name, count in model_prefixes(document).items():
            used[name] = used.get(name, 0) + count
    for name, count in sorted(used.items()):
        if name not in upstream:
            findings.append(Diagnostic(
                code='SF-CTX-002', category='package', severity='error',
                subject=name,
                message=(f'the model uses "{name}:" {count} time(s), and the '
                         f'PUBLISHED context does not declare it. Exported as '
                         f'is, those values will not expand to IRIs. Publish '
                         f'the term at {config.published} first.')))
    return findings


@dataclass
class ContextServer:
    """A local HTTP server for tools that need a URL rather than a file."""
    path: str
    port: int = 0
    _httpd: object = field(default=None, repr=False)

    @property
    def url(self):
        return f'http://127.0.0.1:{self.port}/{os.path.basename(self.path)}'

    def start(self):
        import threading
        from functools import partial
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

        directory = os.path.dirname(os.path.abspath(self.path)) or '.'
        handler = partial(SimpleHTTPRequestHandler, directory=directory)
        self._httpd = ThreadingHTTPServer(('127.0.0.1', self.port), handler)
        self.port = self._httpd.server_address[1]
        thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        thread.start()
        return self

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


def serve_local_context(package_path, port=0):
    path = local_context_path(package_path)
    if path is None:
        raise PackageError(f'{package_path} has no local context to serve')
    return ContextServer(path=path, port=port).start()
