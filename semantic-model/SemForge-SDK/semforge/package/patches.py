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

"""A shapes graph after an edit, patched instead of parsed again.

A cooked edit changes one statement of a shapes file -- one node shape -- and
knows which (cooked/tree._write_verified). Reloading the package then parsed
the whole file again: 21,000 lines of OPC UA shapes, 1.5 s after every click
in the value editor. So the edit records what it changed, and the reload
builds the new graph from the last one: the old statements' triples out, the
new statements' in.

Only when that is certainly the same graph: the file holds exactly what was
written; the old statements account for exactly the triples taken out -- the
same number, the same named ones -- so a subject also said elsewhere in the
file is never cut short. Otherwise None, and the file is parsed as before.
The result is a new Graph, frozen when it is loaded: nothing kept with the
old one (rdfio/frozen.py) is reused for it.
"""

import hashlib
import os

from rdflib import BNode, Graph, URIRef

_RECORDED = {}            # path -> (sha256 of the text written, old statements, new ones)


def record(path, text, old_statements, new_statements):
    """What one write changed: each a Turtle document of its own."""
    _RECORDED[os.path.abspath(path)] = (hashlib.sha256(text.encode('utf-8')).hexdigest(),
                                        old_statements, new_statements)


def forget(path):
    _RECORDED.pop(os.path.abspath(path), None)


def _named(graph):
    return {t for t in graph if not any(isinstance(term, BNode) for term in t)}


def patched(path, graph):
    """`graph` -- the file's graph before the write -- patched to what the file
    now holds, or None when that cannot be said for certain."""
    path = os.path.abspath(path)
    entry = _RECORDED.get(path)
    if entry is None:
        return None
    digest, old_text, new_text = entry
    try:
        with open(path, 'rb') as handle:
            if hashlib.sha256(handle.read()).hexdigest() != digest:
                return None
        old = Graph().parse(data=old_text, format='turtle')
        new = Graph().parse(data=new_text, format='turtle')
    except Exception:                              # noqa: BLE001
        return None
    removed = set()
    for subject in {s for s in old.subjects() if isinstance(s, URIRef)}:
        removed.update(graph.cbd(subject))
    if len(removed) != len(old) or _named(removed) != _named(old):
        return None
    out = Graph()
    for prefix, namespace in graph.namespaces():
        out.bind(prefix, namespace, override=False)
    # By subject, and addN. What was taken out is every triple of the old
    # statements' subjects and their blank nodes, so a subject test says the
    # same as a triple test -- without hashing each literal (0.8 s), and one
    # addN instead of an add per triple.
    gone = {s for s, _, _ in removed}
    out.addN((s, p, o, out) for s, p, o in graph if s not in gone)
    out.addN((s, p, o, out) for s, p, o in new)
    return out
