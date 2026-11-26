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

"""How a query reads NGSI-LD attributes -- checked against the shape of the data.

An attribute is two steps in RDF: the entity points at an attribute
INSTANCE (a blank node), and the instance holds the payload:

    $this iffBaseEntities:hasPressure [ ngsild:hasValue ?pressure ] .

or with the instance named (`?a ngsild:hasValue ?pressure`), or as a path. A
query that takes one step where the data has two matches nothing, silently.
Each finding says where, and offers the rewrite. Whether a query can be
compiled to Flink SQL is said by the compiler itself (target/deploy.py):

  * skipped-layer      `$this ex:hasPressure ?p . FILTER(?p > 5)` -- ?p is the
                       instance, not the value: [ ngsild:hasValue ?p ]
  * constant-object    `$this ex:hasState base:state_ON` never matches: the
                       object is always an instance
  * variable-node      `$this ex:hasPressure ?a` used for nothing else -- ?a is
                       the instance: [ ngsild:hasValue ?a ], or [ ] for presence
  * plain-bracket      a plain property (no NGSI-LD kind) read through
                       [ ngsild:hasValue … ]: its value is the object itself
"""

from dataclasses import dataclass, field

from rdflib import BNode, Literal, URIRef, Variable
from rdflib.paths import Path

from ..ngsild.kinds import NGSILD, PAYLOAD_NAME, PAYLOAD_PATHS
from .lexer import code_tokens

STRUCTURAL = {'Builtin_isBLANK', 'Builtin_BOUND', 'Builtin_sameTerm', 'Aggregate_Count',
              'Builtin_isIRI', 'Builtin_isURI', 'Builtin_isLITERAL'}
NGSILD_PREDICATES = set(PAYLOAD_PATHS) | {NGSILD + m for m in
                                          ('observedAt', 'datasetId', 'unitCode')}


@dataclass
class Structure:
    """A finding before it becomes a check.Finding: spans and fixes in text."""
    start: int
    end: int
    severity: str
    message: str
    code: str
    data: dict = field(default_factory=dict)


# --- the query's triples ----------------------------------------------------------------------

def _walk(node, out):
    if isinstance(node, dict) or hasattr(node, 'name'):
        if getattr(node, 'name', '') == 'BGP':
            out['triples'].extend(node['triples'])
        if getattr(node, 'name', '') in ('Filter', 'Extend', 'LeftJoin') and 'expr' in node:
            out['exprs'].append(node['expr'])
        for key, value in list(node.items()):
            if key in ('_vars', 'PV'):
                continue
            _walk(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _walk(item, out)


def _value_uses(expr, found, structural=False):
    """Variables an expression uses AS VALUES (not just tests for)."""
    if isinstance(expr, Variable):
        if not structural:
            found.add(expr)
        return
    name = getattr(expr, 'name', '')
    if name in ('Builtin_EXISTS', 'Builtin_NOTEXISTS'):
        return                                   # their patterns are triples, walked apart
    inner = structural or name in STRUCTURAL
    if isinstance(expr, dict) or hasattr(expr, 'items'):
        for key, value in expr.items():
            if key != '_vars':
                _value_uses(value, found, inner)
    elif isinstance(expr, (list, tuple)):
        for item in expr:
            _value_uses(item, found, inner)


# --- text positions ----------------------------------------------------------------------------

class _Text:
    """Code tokens with what each names, to find a triple's words."""

    def __init__(self, text, declared):
        self.text, self.declared = text, declared
        self.code = code_tokens(text)

    def resolve(self, token):
        if token.kind == 'pname':
            prefix, _, local = token.text.partition(':')
            namespace = self.declared.get(prefix)
            return URIRef(namespace + local) if namespace else None
        if token.kind == 'iri':
            return URIRef(token.text[1:-1])
        if token.kind == 'name' and token.text == 'a':
            return URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#type')
        return None

    def predicate_spots(self, iri):
        return [i for i, t in enumerate(self.code) if self.resolve(t) == iri]

    def object_after(self, index):
        return self.code[index + 1] if index + 1 < len(self.code) else None

    def bracket_end(self, index):
        """The index of the `]` closing the `[` at `index`."""
        depth = 0
        for j in range(index, len(self.code)):
            if self.code[j].text == '[':
                depth += 1
            elif self.code[j].text == ']':
                depth -= 1
                if depth == 0:
                    return j
        return None


# --- the checks -----------------------------------------------------------------------------------

def check(text, terms, prepared, declared):
    """[Structure] for a query that parses (`prepared` from rdflib)."""
    found = []
    words = _Text(text, declared)
    out = {'triples': [], 'exprs': []}
    _walk(prepared.algebra, out)
    # A rule's CONSTRUCT template writes attributes too. (`get` on rdflib's
    # CompValue returns the key itself when it is missing -- so ask with `in`.)
    if 'template' in prepared.algebra and prepared.algebra['template']:
        out['triples'].extend(prepared.algebra['template'])
    triples = out['triples']

    used_as_value = set()
    for expr in out['exprs']:
        _value_uses(expr, used_as_value)

    def attribute(p):
        term = terms.terms.get(str(p)) if isinstance(p, URIRef) else None
        return term if term is not None and term.kind == 'attribute' and \
            term.attribute_kind in PAYLOAD_NAME else None

    def plain(p):
        term = terms.terms.get(str(p)) if isinstance(p, URIRef) else None
        return term is not None and ((term.kind == 'attribute' and not term.attribute_kind)
                                     or term.kind == 'property')

    def short(iri):
        prefix = next((p for p, n in declared.items() if str(iri).startswith(n)), None)
        return f'{prefix}:{str(iri)[len(declared[prefix]):]}' if prefix else f'<{iri}>'

    for s, p, o in triples:
        if isinstance(p, Path):
            continue
        term = attribute(p)
        if term is not None:
            payload = PAYLOAD_NAME[term.attribute_kind]
            if isinstance(o, (Literal, URIRef)):
                found.extend(_constant(words, p, o, term, payload, short))
            elif isinstance(o, Variable):
                inside = [(q, x) for (a, q, x) in triples if a == o and str(q) in NGSILD_PREDICATES]
                elsewhere = [t for t in triples if (t[0] == o and str(t[1]) not in NGSILD_PREDICATES)
                             or (t[2] == o and (t[0], t[1]) != (s, p))]
                if inside:
                    continue                         # a named instance: read as `[ … ]` is
                if o in used_as_value or elsewhere:
                    found.extend(_skipped(words, p, o, term, payload, short))
                else:
                    found.extend(_variable(words, p, o, term, short, text))
        elif plain(p) and isinstance(o, BNode):
            inner = [(q, x) for (a, q, x) in triples if a == o]
            if inner and all(str(q) in PAYLOAD_PATHS for q, _ in inner):
                found.extend(_plain_bracket(words, p, inner, short))
    return found


def _spots(words, p, test):
    """(predicate token index, object token index) where `test(object token)`."""
    out = []
    for i in words.predicate_spots(p):
        nxt = words.object_after(i)
        if nxt is not None and test(nxt):
            out.append((i, i + 1))
    return out


def _constant(words, p, o, term, payload, short):
    def same(token):
        if token.kind in ('pname', 'iri', 'name'):
            return words.resolve(token) == o
        return isinstance(o, Literal) and token.kind in ('string', 'number', 'name') and \
            (token.text.strip('"\'') == str(o) or token.text == str(o))
    out = []
    for i, j in _spots(words, p, same):
        obj = words.code[j]
        out.append(Structure(
            obj.start, obj.end, 'warning',
            f'{short(p)} is a {term.attribute_kind}: its object is an attribute instance '
            f'(a blank node), never {obj.text} — the {"target" if "Relationship" in term.attribute_kind else "value"} '
            f'is under ngsild:{payload}', 'constant-object',
            {'replace': f'[ ngsild:{payload} {obj.text} ]'}))
    return out


def _skipped(words, p, o, term, payload, short):
    out = []
    for i, j in _spots(words, p, lambda t: t.kind == 'var' and t.text[1:] == str(o)):
        obj = words.code[j]
        out.append(Structure(
            obj.start, obj.end, 'warning',
            f'{obj.text} is the attribute instance of {short(p)}, not its '
            f'{"target" if "Relationship" in term.attribute_kind else "value"} — read it as '
            f'{short(p)} [ ngsild:{payload} {obj.text} ]', 'skipped-layer',
            {'replace': f'[ ngsild:{payload} {obj.text} ]'}))
    return out


def _variable(words, p, o, term, short, text):
    """`$this ex:hasFilter ?filter .` -- almost always meant as reading the
    target, so that is the fix offered first; `[ ]` (only "it is there") is
    the alternative when the variable is used nowhere else."""
    out = []
    payload = PAYLOAD_NAME[term.attribute_kind]
    said = 'target' if term.attribute_kind in ('Relationship', 'ListRelationship') else 'value'
    for i, j in _spots(words, p, lambda t: t.kind == 'var' and t.text[1:] == str(o)):
        obj = words.code[j]
        once = sum(1 for t in words.code if t.kind == 'var' and t.text[1:] == str(o)) == 1
        data = {'replace': f'[ ngsild:{payload} {obj.text} ]'}
        if once:
            data['alternative'] = '[ ]'
        out.append(Structure(
            obj.start, obj.end, 'warning',
            f'{obj.text} names the attribute instance of {short(p)}, not its {said} — '
            f'to read its {said}: {short(p)} [ ngsild:{payload} {obj.text} ]',
            'variable-node', data))
    return out


def _plain_bracket(words, p, inner, short):
    out = []
    for i in words.predicate_spots(p):
        nxt = words.object_after(i)
        if nxt is None or nxt.text != '[':
            continue
        end = words.bracket_end(i + 1)
        if end is None:
            continue
        data = {}
        if len(inner) == 1 and end == i + 4:
            data = {'replace': words.code[i + 3].text}
        out.append(Structure(
            nxt.start, words.code[end].end, 'warning',
            f'{short(p)} is a plain property, not an NGSI-LD attribute: its value is the '
            'object itself, with no instance in between — so this matches nothing',
            'plain-bracket', data))
    return out
