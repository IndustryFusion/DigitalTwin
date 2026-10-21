"""What is wrong in a SPARQL query, and exactly where -- for squiggles.

Each finding has a span in the query text, a severity, a message saying
what to do, and data a quick fix can use:

  * the query does not parse (rdflib's own error, at its position);
  * a constraint that is not a SELECT, a rule that is not a CONSTRUCT;
  * a prefix the query uses but does not declare (the fix adds its PREFIX
    line, when the package knows the namespace);
  * a name in one of the package's own namespaces that the knowledge does
    not declare -- a typo, usually: "did you mean hasState?";
  * an attribute read through the wrong NGSI-LD layer: a Relationship's
    target is under ngsild:hasObject, a Property's value under ngsild:hasValue;
  * what SHACL refuses in a SPARQL constraint (MINUS, VALUES, SERVICE,
    `AS ?this`), and what validation reads differently than it looks.
"""

import difflib
import re
from dataclasses import dataclass, field

from ..ngsild.kinds import PAYLOAD_NAME as LAYER
from ..ngsild.kinds import PAYLOAD_NAMES, is_relationship
from .lexer import code_tokens, declared_prefixes
from .terms import NGSILD

AGGREGATES = {'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'SAMPLE', 'GROUP_CONCAT'}


@dataclass
class Finding:
    start: int
    end: int
    severity: str          # error | warning | info
    message: str
    code: str
    data: dict = field(default_factory=dict)


def _parse_error(text, prefix_lines):
    from rdflib.plugins.sparql import prepareQuery

    head = ''.join(line + '\n' for line in prefix_lines)
    try:
        prepared = prepareQuery(head + text)
        return None, prepared
    except Exception as exc:                         # noqa: BLE001
        message = str(exc)
        if message.startswith('Unknown namespace prefix'):
            return None, None                      # reported by the prefix check, with its fix
        loc = getattr(exc, 'loc', None)
        if isinstance(loc, int):
            loc = max(loc - len(head), 0)
        else:
            loc = 0
        clean = re.sub(r'\s*\(at char \d+\), \(line:\d+, col:\d+\)', '', message)
        found = re.match(r"Expected (\w+), found '(.*)'", clean)
        if found:
            # The parser names the rule it was trying, not the mistake; what
            # helps is where it could read no further.
            clean = (f"the query cannot be read from \"{found.group(2)}\" on — "
                     f"check this clause (the parser expected a {found.group(1)})")
        return (loc, clean), None


PAIRS = {'(': ')', '[': ']', '{': '}'}


def _unbalanced(code):
    """The first bracket without its partner -- said where it is, which is
    more use than the parser's "expected SelectQuery"."""
    stack = []
    for token in code:
        if token.kind != 'op':
            continue
        if token.text in PAIRS:
            stack.append(token)
        elif token.text in PAIRS.values():
            if not stack or PAIRS[stack[-1].text] != token.text:
                return Finding(token.start, token.end, 'error',
                               f'"{token.text}" closes nothing' if not stack else
                               f'"{token.text}" does not close "{stack[-1].text}" '
                               f'(opened on line {stack[-1].line})', 'syntax')
            stack.pop()
    if stack:
        opened = stack[-1]
        return Finding(opened.start, opened.end, 'error',
                       f'"{opened.text}" is never closed', 'syntax')
    return None


def check(text, terms=None, kind='constraint', view='current', prefix_lines=()):
    """[Finding] for one query, in text order."""
    found = []
    code = code_tokens(text)

    unbalanced = _unbalanced([_Lined(t, text) for t in code])
    error, prepared = _parse_error(text, list(prefix_lines))
    if unbalanced is not None:
        found.append(unbalanced)
        error = ('unbalanced', '')
    elif error is not None:
        loc, message = error
        token = next((t for t in code if t.start <= loc < t.end), None) or \
            next((t for t in code if t.start >= loc), None)
        start, end = (token.start, token.end) if token else (max(len(text) - 1, 0), len(text))
        found.append(Finding(start, end, 'error', f'Syntax: {message}', 'syntax'))
    elif prepared is not None:
        form = prepared.algebra.name
        wanted = 'SelectQuery' if kind == 'constraint' else 'ConstructQuery'
        if form != wanted:
            head = next((t for t in code if t.kind == 'name' and t.upper in
                         ('SELECT', 'CONSTRUCT', 'ASK', 'DESCRIBE')), None)
            span = (head.start, head.end) if head else (0, 1)
            found.append(Finding(*span, 'error',
                                 f'a SPARQL {kind} must be a '
                                 f'{"SELECT" if kind == "constraint" else "CONSTRUCT"} query',
                                 'query-form'))

    declared = dict(declared_prefixes(text))
    for line in prefix_lines:
        match = re.match(r'PREFIX\s+([\w-]*):\s*<([^>]*)>', line)
        if match:
            declared[match.group(1)] = match.group(2)

    previous = None
    for index, token in enumerate(code):
        declaring = (previous is not None and previous.kind == 'name' and
                     previous.upper in ('PREFIX', 'BASE')) or \
            (index >= 2 and code[index - 2].kind == 'name' and code[index - 2].upper == 'PREFIX')
        if token.kind == 'pname' and not declaring:
            prefix, _, local = token.text.partition(':')
            if prefix not in declared:
                namespace = terms.namespaces.get(prefix) if terms else None
                found.append(Finding(
                    token.start, token.start + len(prefix) + 1, 'error',
                    f'the prefix {prefix}: is not declared' +
                    (f' — add PREFIX {prefix}: <{namespace}>' if namespace
                     else ', and the package knows no namespace by that name'),
                    'undeclared-prefix', {'prefix': prefix, 'namespace': namespace or ''}))
            elif terms is not None and local:
                found.extend(_unknown(terms, declared[prefix] + local, token,
                                      f'{prefix}:{local}', prefix))
        elif token.kind == 'iri' and terms is not None and not declaring:
            found.extend(_unknown(terms, token.text[1:-1], token, token.text, None))
        if token.kind == 'pname' and terms is not None and not declaring:
            found.extend(_layer(terms, declared, code, index))
        if token.kind == 'name' and token.upper in ('MINUS', 'VALUES', 'SERVICE'):
            found.append(Finding(token.start, token.end, 'error',
                                 f'SHACL does not allow {token.upper} in a SPARQL '
                                 f'{kind}: validation refuses the whole query',
                                 'not-allowed'))
        if token.kind == 'name' and token.upper == 'AS' and index + 1 < len(code) \
                and code[index + 1].text in ('?this', '$this'):
            found.append(Finding(token.start, code[index + 1].end, 'error',
                                 '$this cannot be bound with AS: the engine binds it',
                                 'not-allowed'))
        if token.kind == 'var' and token.text[1:] in ('shapesGraph', 'currentShape'):
            found.append(Finding(token.start, token.end, 'warning',
                                 f'{token.text} is not supported by the validator here',
                                 'unsupported'))
        if view == 'current' and token.kind == 'name' and token.upper in AGGREGATES \
                and index + 1 < len(code) and code[index + 1].text == '(':
            found.append(Finding(token.start, token.end, 'warning',
                                 f'{token.upper} in the current view sees only the latest '
                                 'observation of each attribute; declare semforge:dataView '
                                 'history to aggregate over time', 'aggregate-current'))
        previous = token

    if prepared is not None and terms is not None:
        # How the query reads NGSI-LD attributes: what the data's two steps
        # need, and what Flink can compile (semforge.sparql.ngsild).
        from .ngsild import check as structure

        try:
            for item in structure(text, terms, prepared, declared):
                found.append(Finding(item.start, item.end, item.severity, item.message,
                                     item.code, item.data))
        except Exception:                            # noqa: BLE001 -- never cost the squiggles
            pass

    if kind == 'constraint' and error is None and \
            not any(t.kind == 'var' and t.text[1:] == 'this' for t in code):
        head = next((t for t in code if t.kind == 'name' and t.upper == 'SELECT'), None)
        if head:
            found.append(Finding(head.start, head.end, 'warning',
                                 'the query never mentions $this: it runs once, not per '
                                 'focus node, and every row is a violation of every node',
                                 'no-this'))
    return sorted(found, key=lambda f: (f.start, f.end))


class _Lined:
    """A token that knows its line, for messages."""

    def __init__(self, token, text):
        self.kind, self.text, self.start, self.end = token.kind, token.text, token.start, token.end
        self.line = text.count('\n', 0, token.start) + 1


def _unknown(terms, iri, token, written, prefix):
    if not terms.own(iri) or iri in terms.terms:
        return []
    namespace = next((ns for ns in terms.owned if iri.startswith(ns)), '')
    local = iri[len(namespace):]
    known = [t.local for t in terms.in_namespace(namespace)]
    close = difflib.get_close_matches(local, known, n=1, cutoff=0.6)
    data = {}
    message = f'{written} is not declared in the knowledge'
    if close:
        better = f'{prefix}:{close[0]}' if prefix is not None else f'<{namespace}{close[0]}>'
        message += f' — did you mean {better}?'
        data = {'replace': better}
    return [Finding(token.start, token.end, 'warning', message, 'undeclared-term', data)]


def _layer(terms, declared, code, index):
    """`attr [ ngsild:hasValue … ]` where attr is a Relationship, or the reverse."""
    token = code[index]
    if index + 2 >= len(code) or code[index + 1].text != '[':
        return []
    inner = code[index + 2]
    if inner.kind != 'pname':
        return []
    prefix, _, local = token.text.partition(':')
    inner_prefix, _, inner_local = inner.text.partition(':')
    if prefix not in declared or declared.get(inner_prefix) != NGSILD:
        return []
    term = terms.terms.get(declared[prefix] + local)
    if term is None or term.kind != 'attribute' or term.attribute_kind not in LAYER:
        return []
    wanted = LAYER[term.attribute_kind]
    if inner_local not in PAYLOAD_NAMES or inner_local == wanted:
        return []
    return [Finding(inner.start, inner.end, 'warning',
                    f'{local} is a {term.attribute_kind}: its '
                    f'{"target" if is_relationship(term.attribute_kind) else "value"} is under '
                    f'ngsild:{wanted}, so ngsild:{inner_local} matches nothing',
                    'wrong-layer', {'replace': f'{inner_prefix}:{wanted}'})]
