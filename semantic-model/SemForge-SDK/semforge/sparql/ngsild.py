"""How a query reads NGSI-LD attributes -- checked against the shape of the data.

An attribute is two steps in RDF: the entity points at an attribute
INSTANCE (a blank node), and the instance holds the payload:

    $this iffBaseEntities:hasPressure [ ngsild:hasValue ?pressure ] .

shacl2flink, which compiles every SPARQL constraint to Flink SQL, reads an
attribute only in exactly that form -- the object written as `[ … ]`, the
attribute known from a shape that nests its payload. Validation (pyshacl)
reads any form. So nothing here refuses a query; each finding says what is
wrong or what Flink cannot compile, and offers the rewrite:

  * skipped-layer      `$this ex:hasPressure ?p . FILTER(?p > 5)` -- ?p is the
                       instance, not the value: [ ngsild:hasValue ?p ]
  * constant-object    `$this ex:hasState base:state_ON` never matches: the
                       object is always an instance
  * explicit-node      `$this ex:hasPressure ?a . ?a ngsild:hasValue ?p` --
                       valid, but Flink compiles only the [ … ] form
  * variable-node      `$this ex:hasPressure ?a` used for nothing else -- Flink
                       reads it as a plain triple: [ ] tests presence
  * path               `ex:hasPressure/ngsild:hasValue ?p` -- Flink has no paths
  * plain-bracket      a plain property (no NGSI-LD kind) read through
                       [ ngsild:hasValue … ]: its value is the object itself
  * not-compiled       an attribute no shape nests a payload for: Flink would
                       read it as a plain triple
"""

from dataclasses import dataclass, field

from rdflib import BNode, Literal, URIRef, Variable
from rdflib.paths import Path, SequencePath

from ..ngsild.kinds import NGSILD, PAYLOAD_NAME, PAYLOAD_PATHS
from .lexer import code_tokens

STRUCTURAL = {'Builtin_isBLANK', 'Builtin_BOUND', 'Builtin_sameTerm', 'Aggregate_Count',
              'Builtin_isIRI', 'Builtin_isURI', 'Builtin_isLITERAL'}
NGSILD_PREDICATES = set(PAYLOAD_PATHS) | {NGSILD + m for m in
                                          ('observedAt', 'datasetId', 'unitCode')}
FLINK = 'shacl2flink compiles an attribute only as `{p} [ … ]`'


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

    reported = set()
    for s, p, o in triples:
        if isinstance(p, SequencePath) and p.args and attribute(p.args[0]):
            found.extend(_path(words, p, o, attribute(p.args[0]), short))
            continue
        if isinstance(p, Path):
            continue
        term = attribute(p)
        if term is not None:
            payload = PAYLOAD_NAME[term.attribute_kind]
            if str(p) not in terms.compiled and str(p) not in reported:
                reported.add(str(p))
                found.extend(_not_compiled(words, p, term, payload, short))
            if isinstance(o, (Literal, URIRef)):
                found.extend(_constant(words, p, o, term, payload, short))
            elif isinstance(o, Variable):
                inside = [(q, x) for (a, q, x) in triples if a == o and str(q) in NGSILD_PREDICATES]
                elsewhere = [t for t in triples if (t[0] == o and str(t[1]) not in NGSILD_PREDICATES)
                             or (t[2] == o and (t[0], t[1]) != (s, p))]
                if inside:
                    found.extend(_explicit(words, p, o, term, payload, short, inside, triples))
                elif o in used_as_value or elsewhere:
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
            f'{obj.text} names the attribute instance of {short(p)}, which shacl2flink reads '
            f'as a plain triple — to read its {said}: {short(p)} [ ngsild:{payload} {obj.text} ]',
            'variable-node', data))
    return out


def _explicit(words, p, o, term, payload, short, inside, triples):
    """`X p ?a . ?a ngsild:hasValue ?v .` -- offered as `X p [ ngsild:hasValue ?v ]`
    when ?a is used nowhere else and each `?a …` triple is a statement of its own."""
    out = []
    var = f'?{o}'
    for i, j in _spots(words, p, lambda t: t.kind == 'var' and t.text[1:] == str(o)):
        obj = words.code[j]
        data = {}
        statements = _statements_of(words, str(o))
        uses = [t for t in words.code if t.kind == 'var' and t.text[1:] == str(o)]
        if statements is not None and len(uses) == 1 + len(statements):
            parts = []
            for start, end in statements:
                body = words.text[words.code[start + 1].start:words.code[end - 1].end] \
                    if end - 1 > start else ''
                parts.append(body.strip())
            data = {'replace': f'[ {" ; ".join(parts)} ]',
                    'remove': [[words.code[start].start, words.code[end].end]
                               for start, end in statements]}
        out.append(Structure(
            obj.start, obj.end, 'warning',
            f'{FLINK.format(p=short(p))}, not through a named instance '
            f'{var}; validation reads it either way', 'explicit-node', data))
    return out


def _statements_of(words, name):
    """[(first token, closing `.` token)] of each `?name pred obj .` statement,
    or None when one is not that simple (more than one predicate, or not
    ending in `.`)."""
    found = []
    code = words.code
    for i, token in enumerate(code):
        if token.kind != 'var' or token.text[1:] != name:
            continue
        before = code[i - 1].text if i else ''
        if before not in ('.', '{', '}'):
            continue                             # an object, not a subject
        depth, j = 0, i + 1
        while j < len(code):
            t = code[j].text
            if t in ('[', '('):
                depth += 1
            elif t in (']', ')'):
                depth -= 1
            elif depth == 0 and t in ('.', '}', ';'):
                break
            j += 1
        if j >= len(code) or code[j].text != '.':
            return None
        found.append((i, j))
    return found or None


def _path(words, path, o, term, short):
    out = []
    first = path.args[0]
    for i in words.predicate_spots(first):
        slash = words.object_after(i)
        if slash is None or slash.text != '/':
            continue
        second = words.code[i + 2] if i + 2 < len(words.code) else None
        obj = words.code[i + 3] if i + 3 < len(words.code) else None
        data = {}
        if second is not None and obj is not None and obj.kind in ('var', 'pname', 'iri',
                                                                   'string', 'number'):
            data = {'replace': f'{words.code[i].text} [ {second.text} {obj.text} ]',
                    'span': [words.code[i].start, obj.end]}
        out.append(Structure(
            words.code[i].start, (obj or second or slash).end, 'warning',
            f'{FLINK.format(p=short(first))}: shacl2flink has no property paths',
            'path', data))
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


def _not_compiled(words, p, term, payload, short):
    spots = words.predicate_spots(p)
    if not spots:
        return []
    token = words.code[spots[0]]
    return [Structure(
        token.start, token.end, 'warning',
        f'shacl2flink knows {short(p)} as an NGSI-LD attribute only from a shape that nests '
        f'ngsild:{payload} on it, and none does: Flink would compile it as a plain triple',
        'not-compiled', {'attribute': str(p), 'kind': term.attribute_kind,
                         'domain': term.domain_iri})]
