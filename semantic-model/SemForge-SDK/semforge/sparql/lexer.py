"""A SPARQL tokenizer that keeps every character's position.

Not a parser: rdflib parses, and says whether a query is valid. This splits
the text into the pieces an editor works with -- a prefixed name, a
variable, an IRI, a keyword -- each with its offsets, comments and
whitespace included, so that joining the tokens gives the text back exactly.
"""

import re
from dataclasses import dataclass

KEYWORDS = {
    'BASE', 'PREFIX', 'SELECT', 'CONSTRUCT', 'DESCRIBE', 'ASK', 'DISTINCT', 'REDUCED',
    'FROM', 'NAMED', 'WHERE', 'ORDER', 'BY', 'ASC', 'DESC', 'LIMIT', 'OFFSET', 'GROUP',
    'HAVING', 'VALUES', 'OPTIONAL', 'UNION', 'MINUS', 'GRAPH', 'SERVICE', 'SILENT',
    'FILTER', 'BIND', 'AS', 'NOT', 'EXISTS', 'IN', 'UNDEF',
}

# Built-in functions and aggregates: written in capitals by convention.
FUNCTIONS = {
    'STR', 'LANG', 'LANGMATCHES', 'DATATYPE', 'BOUND', 'IRI', 'URI', 'BNODE', 'RAND', 'ABS',
    'CEIL', 'FLOOR', 'ROUND', 'CONCAT', 'STRLEN', 'UCASE', 'LCASE', 'ENCODE_FOR_URI',
    'CONTAINS', 'STRSTARTS', 'STRENDS', 'STRBEFORE', 'STRAFTER', 'YEAR', 'MONTH', 'DAY',
    'HOURS', 'MINUTES', 'SECONDS', 'TIMEZONE', 'TZ', 'NOW', 'UUID', 'STRUUID', 'MD5', 'SHA1',
    'SHA256', 'SHA384', 'SHA512', 'COALESCE', 'IF', 'STRLANG', 'STRDT', 'SAMETERM', 'ISIRI',
    'ISURI', 'ISBLANK', 'ISLITERAL', 'ISNUMERIC', 'REGEX', 'SUBSTR', 'REPLACE',
    'COUNT', 'SUM', 'MIN', 'MAX', 'AVG', 'SAMPLE', 'GROUP_CONCAT', 'SEPARATOR',
}

_PATTERNS = [
    ('space', r'[ \t\r\n]+'),
    ('comment', r'#[^\n]*'),
    ('string', r'"""(?:[^"\\]|\\.|"(?!""))*"""|\'\'\'(?:[^\'\\]|\\.|\'(?!\'\'))*\'\'\''
               r'|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\''),
    ('iri', r'<[^<>"{}|^`\\\s]*>'),
    ('var', r'[?$][A-Za-z0-9_·-￿]+'),
    # A prefixed name; its local part may not end with '.', which ends a triple.
    ('pname', r'(?:[A-Za-z][\w.-]*)?:(?:[\w%:-]|\.(?=[\w%:-]))*'),
    ('number', r'[0-9]+\.[0-9]*(?:[eE][+-]?[0-9]+)?|\.[0-9]+(?:[eE][+-]?[0-9]+)?'
               r'|[0-9]+[eE][+-]?[0-9]+|[0-9]+'),
    ('lang', r'@[A-Za-z]+(?:-[A-Za-z0-9]+)*'),
    ('name', r'[A-Za-z_][A-Za-z0-9_]*'),
    ('op', r'&&|\|\||!=|<=|>=|\^\^|[{}()\[\].,;=<>!+\-*/|^]'),
    ('error', r'.'),
]
_RE = re.compile('|'.join(f'(?P<{name}>{pattern})' for name, pattern in _PATTERNS), re.S)


@dataclass(frozen=True)
class Token:
    kind: str          # space comment string iri var pname number lang name op error
    text: str
    start: int
    end: int

    @property
    def upper(self):
        return self.text.upper()

    @property
    def is_keyword(self):
        return self.kind == 'name' and self.upper in KEYWORDS

    @property
    def is_function(self):
        return self.kind == 'name' and self.upper in FUNCTIONS

    @property
    def code(self):
        """Neither whitespace nor a comment: what the query is made of."""
        return self.kind not in ('space', 'comment')


def tokens(text):
    """Every token, in order; joined, they are the text."""
    return [Token(m.lastgroup, m.group(), m.start(), m.end()) for m in _RE.finditer(text)]


def code_tokens(text):
    return [t for t in tokens(text) if t.code]


def at(text, offset):
    """The token covering `offset`, or the one just before it (a cursor sits
    after what it typed)."""
    found = None
    for token in tokens(text):
        if token.start <= offset <= token.end and token.code:
            found = token
            if offset < token.end:
                break
        elif token.start > offset:
            break
    return found


def position(text, offset):
    """(line, character) of an offset, both from 0, as LSP counts them."""
    line = text.count('\n', 0, offset)
    return line, offset - (text.rfind('\n', 0, offset) + 1)


def offset_of(text, line, character):
    """The offset of an LSP (line, character)."""
    start = 0
    for _ in range(line):
        newline = text.find('\n', start)
        if newline < 0:
            return len(text)
        start = newline + 1
    return min(start + character, len(text))


def declared_prefixes(text):
    """{prefix: namespace} the query's own PREFIX lines declare, with where."""
    found = {}
    code = code_tokens(text)
    for i, token in enumerate(code):
        if token.is_keyword and token.upper == 'PREFIX' and i + 2 < len(code) \
                and code[i + 1].kind == 'pname' and code[i + 2].kind == 'iri':
            found[code[i + 1].text[:-1] if code[i + 1].text.endswith(':')
                  else code[i + 1].text.split(':')[0]] = code[i + 2].text[1:-1]
    return found


def prologue_end(text):
    """Where a new PREFIX line goes: after the last PREFIX/BASE declaration,
    else at the start (after leading comments)."""
    code = code_tokens(text)
    end = 0
    for i, token in enumerate(code):
        if token.is_keyword and token.upper in ('PREFIX', 'BASE'):
            last = code[i + 2] if token.upper == 'PREFIX' and i + 2 < len(code) else \
                code[i + 1] if i + 1 < len(code) else token
            end = last.end
    if end:
        newline = text.find('\n', end)
        return len(text) if newline < 0 else newline + 1
    # After leading comment lines and blank lines.
    for token in tokens(text):
        if token.code:
            return text.rfind('\n', 0, token.start) + 1
    return len(text)
