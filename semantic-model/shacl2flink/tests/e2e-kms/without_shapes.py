#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
Copies the e2e KMS without the shapes a SPARQL method refuses.

    without_shapes.py <kms dir> <target dir> <shape name> ...

SPARQL_ENGINE=ladder (alpha) refuses some queries the e2e KMS holds, and a
refused query stops the build. Its end-to-end run deploys this copy; the
suites skip what the dropped shapes would raise (see LADDER_REFUSED there).
A shape is named by the last part of its IRI; one that is not there is an
error, so the list cannot go stale unnoticed.

The copy is the original text without the shapes' blocks, not a new
serialization: the deploy suite edits the package as text (changed_package),
and every line it looks for stays where it was. rdflib checks that the copy
holds exactly the original graph without the shapes.
"""
import shutil
import sys
from pathlib import Path

import rdflib
import rdflib.compare


def name_of(node):
    return str(node).rsplit('/', 1)[-1].rsplit('#', 1)[-1]


def without_text(text, names):
    """The Turtle text without the blocks of the named shapes. A block starts at
    the line `:<name> ` and ends before the next line at the left margin outside
    a \"\"\" string (a query in it may end its lines with " .")."""
    out, dropping, in_string = [], False, False
    for line in text.splitlines(keepends=True):
        top = not in_string and line[:1] not in ('', ' ', '\t', '\n')
        if top:
            dropping = any(line.startswith(f':{name} ') for name in names)
        if not dropping:
            out.append(line)
        if line.count('"""') % 2:
            in_string = not in_string
    return ''.join(out)


def without(graph, names):
    shapes = {s for s in graph.subjects() if isinstance(s, rdflib.URIRef) and name_of(s) in names}
    missing = set(names) - {name_of(s) for s in shapes}
    if missing:
        raise SystemExit(f'not in the KMS: {", ".join(sorted(missing))}')
    # the shape and every blank node it holds, nothing it only points at
    pending = list(shapes)
    while pending:
        node = pending.pop()
        for _, _, o in list(graph.triples((node, None, None))):
            if isinstance(o, rdflib.BNode):
                pending.append(o)
        graph.remove((node, None, None))
    return graph


def main(source, target, names):
    source, target = Path(source), Path(target)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, symlinks=False,
                    ignore=shutil.ignore_patterns('*.py', '__pycache__'))
    text = (source / 'shacl.ttl').read_text()
    expected = without(rdflib.Graph().parse(data=text, format='turtle'), names)
    copy = without_text(text, names)
    if not rdflib.compare.isomorphic(rdflib.Graph().parse(data=copy, format='turtle'), expected):
        raise SystemExit(f'the text of {", ".join(names)} is not one block of its own in {source}/shacl.ttl')
    (target / 'shacl.ttl').write_text(copy)


if __name__ == '__main__':
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
