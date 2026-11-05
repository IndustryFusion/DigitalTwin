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
"""Compose the static export of a nodeset (nodeset2owl.py without --serverUri) and its dynamic exports of one or
more servers (nodeset2owl.py --serverUri --dynamic-only) into one ontology, e.g. to browse or query an example of
the complete model."""

import base64
import binascii
import os
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS
import lib.utils as utils


def composed_ontology_iri(ontology_iri):
    """IRI of the composed ontology: the (normalized) ontology IRI plus 'all'. It cannot collide with a node IRI,
    which is the base64url encoding of an ExpandedNodeId (i=..., nsu=..., svu=...)."""
    return URIRef(f'{utils.normalize_namespaceuri(ontology_iri)}all')


def ontology_header(graph):
    """The single owl:Ontology node of an export."""
    ontologies = list(graph.subjects(RDF.type, OWL.Ontology))
    if len(ontologies) != 1:
        raise ValueError(f'Expected exactly one owl:Ontology, found {len(ontologies)}')
    return ontologies[0]


def server_of_dynamic_header(static_header, dynamic_header):
    """Server URI of a dynamic export of static_header: its IRI is <ontology> + base64url('svu=<server>')."""
    prefix = str(utils.normalize_namespaceuri(static_header))
    suffix = str(dynamic_header)[len(prefix):] if str(dynamic_header).startswith(prefix) else ''
    try:
        decoded = base64.urlsafe_b64decode(suffix + '=' * (-len(suffix) % 4)).decode('utf-8')
    except (binascii.Error, UnicodeDecodeError):
        decoded = ''
    if not suffix or not decoded.startswith('svu=') or ';' in decoded:
        raise ValueError(f'{dynamic_header} is not a dynamic export of {static_header}')
    return decoded[len('svu='):]


def compose(static, dynamics, import_map=None):
    """Return the static export and the dynamic exports (of any number of servers) as one graph with own header.

    The header gets the IRI <ontology>all (versionIRI likewise) and the owl:imports of the static export, where
    import_map ({basename of an imported file: replacement}) replaces imported static files, e.g. the static
    exports of the dependencies by their composed files. The owl:imports of the dynamic headers (their static
    sibling and the dynamic exports of the dependencies) are not taken over, since their content is part of
    this or of the imported composed files.
    """
    import_map = import_map or {}
    static_header = ontology_header(static)
    composed = Graph()
    servers = []
    parts = [(static, static_header)]
    for dynamic in dynamics:
        dynamic_header = ontology_header(dynamic)
        servers.append(server_of_dynamic_header(static_header, dynamic_header))
        parts.append((dynamic, dynamic_header))
    for graph, header in parts:
        for prefix, namespace in graph.namespaces():
            composed.bind(prefix, namespace, override=False)
        for triple in graph.triples((None, None, None)):
            if triple[0] != header:
                composed.add(triple)
    header = composed_ontology_iri(static_header)
    composed.add((header, RDF.type, OWL.Ontology))
    for version_iri in static.objects(static_header, OWL.versionIRI):
        composed.add((header, OWL.versionIRI, composed_ontology_iri(version_iri)))
    for version_info in static.objects(static_header, OWL.versionInfo):
        composed.add((header, OWL.versionInfo, version_info))
    composed.add((header, RDFS.comment, Literal(f'Static part of {static_header} and its server specific (dynamic) '
                                                f'part of the servers: {", ".join(sorted(servers)) or "none"}')))
    for imported in static.objects(static_header, OWL.imports):
        replacement = import_map.get(os.path.basename(str(imported)))
        composed.add((header, OWL.imports, utils.file_path_to_uri(replacement) if replacement else imported))
    return composed
