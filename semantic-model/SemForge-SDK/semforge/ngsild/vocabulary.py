"""The NGSI-LD vocabulary itself, as a graph.

Every package written against this SDK uses these terms -- `ngsild:Property`,
`ngsild:hasValue`, `ngsild:observedAt` -- and until now nothing declared them.
The SDK knew them as Python constants and the packages used them as bare IRIs,
so the rule this project applies to everything else, *declared before used*,
was the one rule its own encoding did not follow. `rdfs:domain
ngsild:Relationship` pointed at a class no file defined.

It is not an ordinary dependency. A domain vocabulary is the package's business
and is declared in semforge.yaml; the encoding is what MAKES it an NGSI-LD
package, every one of them needs it, and a package that forgot to declare it
would silently lose the terms every shape's `sh:path` names. So the SDK ships
it and always loads it, and a package that wants a different copy says so:

    ngsild: ./vendor/ngsild.ttl          # or an http(s) url

Upstream is UPSTREAM below. What ships here is that file extended -- it
declares two classes, and the shipped kms alone uses ten NGSI-LD terms. The
additions are marked in the Turtle so they can go back upstream.
"""

import os

from rdflib import Graph

UPSTREAM = ('https://industryfusion.github.io/contexts/staging/ontology/v0/'
            'ngsild.ttl')
SHIPPED = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'vocabulary.ttl')

_cache = {}


def graph(source=None):
    """The vocabulary, parsed once per source."""
    where = source or SHIPPED
    if where not in _cache:
        parsed = Graph()
        parsed.parse(where, format='turtle')
        _cache[where] = parsed
    return _cache[where]


def declared_source(package_path):
    """`ngsild:` from semforge.yaml, resolved against the package."""
    from ..package.config import read

    declared = read(package_path).get('ngsild')
    if not declared:
        return None
    declared = str(declared)
    if declared.startswith(('http://', 'https://')):
        return declared
    return os.path.join(package_path, declared)


def for_package(package_path):
    """The vocabulary this package uses: its own copy, or the shipped one.

    A remote copy is fetched through the dependency machinery, so it is cached
    and verifiable like any other declared source rather than reaching the
    network on every load.
    """
    source = declared_source(package_path)
    if source is None:
        return graph()
    if source.startswith(('http://', 'https://')):
        from .. package.registry import Dependency, resolve

        resolution = resolve([Dependency(name='ngsild', source=source)],
                             package_path)
        source = resolution.paths['ngsild']
    return graph(source)


def terms(package_path=None):
    """{local name: IRI} for everything the vocabulary declares."""
    from rdflib import URIRef

    NGSILD = 'https://uri.etsi.org/ngsi-ld/'
    found = {}
    for subject in set(graph_for(package_path).subjects(None, None)):
        text = str(subject)
        if isinstance(subject, URIRef) and text.startswith(NGSILD) \
                and len(text) > len(NGSILD):
            found[text[len(NGSILD):]] = text
    return found


def graph_for(package_path):
    return graph() if package_path is None else for_package(package_path)
