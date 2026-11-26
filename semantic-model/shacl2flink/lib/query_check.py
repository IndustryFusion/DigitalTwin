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

"""Which SPARQL expressions of a shapes graph can be compiled, and why not.

The answer is the compiler's own: every sh:select and sh:construct goes through
the translation that a build uses, so what passes here compiles, and what does
not says which expression it is, of which shape, and which of its patterns.
"""

from dataclasses import asdict, dataclass

from rdflib import RDF, SH, URIRef

import lib.utils as utils
from lib.sparql_to_sql import translate_sparql


@dataclass
class Problem:
    shape: str
    target: str
    kind: str              # sh:select or sh:construct
    message: str           # the constraint's sh:message
    reason: str
    pattern: str           # the pattern that could not be translated, if known
    query: str
    file: str = ''
    line: int = 0

    def as_dict(self):
        return asdict(self)

    def __str__(self):
        where = f' ({self.file}:{self.line})' if self.line else ''
        lines = [f'{self.kind} of <{self.shape}>{where}']
        if self.message:
            lines.append(f'  message : {self.message}')
        lines.append(f'  target  : <{self.target}>')
        lines.append(f'  problem : {self.reason}')
        if self.pattern:
            lines.append(f'  pattern : {self.pattern}')
        lines.append('  query   :')
        text = [line for line in self.query.strip('\n').split('\n')
                if not line.strip().upper().startswith('PREFIX ')]
        while text and not text[0].strip():
            text.pop(0)
        lines += [f'    | {line.rstrip()}' for line in text]
        return '\n'.join(lines)


def line_of(query, files):
    """(file, line) where the query stands, or ('', 0)."""
    wanted = query.strip()
    for path in files:
        try:
            with open(path, encoding='utf-8') as handle:
                text = handle.read()
        except OSError:
            continue
        at = text.find(wanted)
        if at >= 0:
            return path, text.count('\n', 0, at) + 1
    return '', 0


def problem_of(error, shape, target, kind, message, query, files=()):
    """What is said about an expression that did not translate. Any exception
    counts: one the translator did not foresee is as much a reason not to
    deploy, and naming the expression is the point."""
    if isinstance(error, (utils.SparqlValidationFailed, utils.WrongSparqlStructure)):
        reason = str(error)
    else:
        reason = f'The compiler failed on it ({type(error).__name__}: {error}). This is a defect of shacl2flink.'
    path, line = line_of(query, files)
    return Problem(str(shape), str(target), kind, str(message or ''), reason,
                   getattr(error, 'pattern', ''), query, path, line)


def expressions(graph):
    """(shape, target, kind, message, query) of every SPARQL expression that is compiled."""
    found = []
    for shape in graph.subjects(RDF.type, SH.NodeShape):
        for target in graph.objects(shape, SH.targetClass):
            for holder, what, kind in ((SH.sparql, SH.select, 'sh:select'), (SH.rule, SH.construct, 'sh:construct')):
                for node in graph.objects(shape, holder):
                    for query in graph.objects(node, what):
                        found.append((shape, target, kind, graph.value(node, SH.message), str(query)))
    return sorted(found, key=lambda e: tuple(str(x) for x in e))


def check(graph, files=(), draft=None):
    """[Problem] of a shapes graph. `draft`, a dict with target, kind and query
    (and shape, message), is checked instead of what the graph holds."""
    if draft is not None:
        found = [(draft.get('shape', ''), URIRef(draft['target']), draft.get('kind', 'sh:select'),
                  draft.get('message', ''), draft['query'])]
    else:
        found = expressions(graph)
    problems = []
    for shape, target, kind, message, query in found:
        try:
            utils.process_sql_dialect(translate_sparql(None, None, query, target, graph)[0], False)
        except Exception as error:              # noqa: BLE001
            problems.append(problem_of(error, shape, target, kind, message, query, files))
    return problems
