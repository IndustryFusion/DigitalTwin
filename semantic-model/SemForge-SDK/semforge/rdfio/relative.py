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

"""One base for the ids NGSI-LD data should not have: relative ones.

An entity id must be an absolute URI. A document that says `"id": "sn1234…"`
gets it resolved by JSON-LD against the document's base -- which rdflib takes
from the process's current directory when none is given. The language server
and its validation worker then read the same entity as two different IRIs,
and neither is the id the data says: the violations of such an entity were
counted and then attached to nothing.

So every JSON-LD document is read against one base that is no place, and a
result names the id as it was written (`as_written`). sanity.py still says
the id is not an IRI (id-not-iri): the platform resolves it its own way.
"""

BASE = 'https://relative.semforge.invalid/'


def absolute_contexts(document, path):
    """`document` with each relative "@context" made absolute against its
    file, `path`: read against BASE, "context.jsonld" would be looked up at
    no place instead of beside the document."""
    import os
    import re

    scheme = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:')
    folder = os.path.dirname(os.path.abspath(path))

    def fixed(context):
        if isinstance(context, str) and not scheme.match(context):
            return 'file://' + os.path.normpath(os.path.join(folder, context))
        if isinstance(context, list):
            return [fixed(item) for item in context]
        return context

    def walk(node):
        if isinstance(node, list):
            return [walk(item) for item in node]
        if isinstance(node, dict) and '@context' in node:
            return dict(node, **{'@context': fixed(node['@context'])})
        return node

    return walk(document)


def as_written(iri):
    """The id as the data wrote it: a relative one without the base."""
    text = str(iri)
    return text[len(BASE):] if text.startswith(BASE) else text
