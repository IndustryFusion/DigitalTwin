"""Format a SPARQL query: one layout, so queries read alike.

Only whitespace and the case of keywords and built-in functions change.
That is checked, not hoped: the code tokens of the result must equal those
of the input (keywords compared without case), and every comment must still
be there -- otherwise nothing is formatted and the reason is raised.

The layout:
  * one PREFIX per line, a blank line after them;
  * SELECT / CONSTRUCT / ASK, WHERE, GROUP BY, ORDER BY, HAVING, LIMIT, OFFSET
    each start a line;
  * a group's content indented four spaces per level, `}` on its own line;
  * one triple per line ending ` .`; after `;` the next predicate on its own
    line, indented once more; `,` stays on the line;
  * `[ … ]` and `( … )` stay on one line;
  * FILTER, BIND, OPTIONAL, MINUS, VALUES, GRAPH, SERVICE start a line; `}
    UNION {` stays together;
  * keywords and built-in functions in capitals, `a`, `true` and `false` not;
  * a comment stays where it was: at the end of its line, or on a line of its
    own; one blank line between statements is kept.
"""

from .lexer import tokens

INDENT = '    '
CLAUSES = {'SELECT', 'CONSTRUCT', 'ASK', 'DESCRIBE', 'WHERE', 'ORDER', 'GROUP', 'HAVING',
           'LIMIT', 'OFFSET'}
STATEMENTS = {'FILTER', 'BIND', 'OPTIONAL', 'MINUS', 'VALUES', 'GRAPH', 'SERVICE'}
NO_SPACE_BEFORE = {')', ',', ']', '.', ';'}
SPACE_BEFORE = {']': True, ';': True, '.': True}


class FormatError(Exception):
    pass


def _case(token):
    if token.kind == 'name' and (token.is_keyword or token.is_function):
        return token.upper
    return token.text


def format_query(text):
    """The query laid out; its meaning untouched. Raises FormatError when the
    layout would change a token (it never should) -- then nothing changes."""
    out = _layout(text)
    _check(text, out)
    return out


def _check(before, after):
    def key(t):
        return (t.kind, t.upper if t.kind == 'name' and (t.is_keyword or t.is_function)
                else t.text)
    a = [key(t) for t in tokens(before) if t.code]
    b = [key(t) for t in tokens(after) if t.code]
    if a != b:
        at = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        raise FormatError(f'formatting would change the query near token {at}: '
                          f'{a[at:at + 3]} became {b[at:at + 3]}; nothing was changed')
    comments = lambda t: [x.text.rstrip() for x in tokens(t) if x.kind == 'comment']  # noqa: E731
    if comments(before) != comments(after):
        raise FormatError('formatting would lose a comment; nothing was changed')


class _Printer:
    def __init__(self):
        self.lines = []
        self.line = ''
        self.depth = 0          # { } nesting
        self.continued = False  # after ';' inside a triple
        self.blank_wanted = False
        self.pending = False    # a line end owed, paid at the next token

    def end_line(self):
        self.pending = True

    def settle(self):
        if self.pending:
            self.pending = False
            self.newline()

    def newline(self):
        if self.line.strip() or not self.lines or self.lines[-1] != '':
            self.lines.append(self.line.rstrip())
        self.line = ''

    def at_start(self):
        return not self.line.strip()

    def indent(self, extra=0):
        if self.blank_wanted and self.lines and self.lines[-1] != '':
            self.lines.append('')
        self.blank_wanted = False
        self.line = INDENT * (self.depth + extra)

    def put(self, text, space):
        if self.at_start():
            if not self.line:
                self.indent(1 if self.continued else 0)
            self.line += text
        else:
            self.line += (' ' if space else '') + text

    def text(self):
        self.pending = False
        if self.line.strip():
            self.lines.append(self.line.rstrip())
        while self.lines and self.lines[-1] == '':
            self.lines.pop()
        return '\n'.join(self.lines) + '\n'


def _more_prologue(code, comment):
    """Is the next code token after this comment another PREFIX or BASE?"""
    following = next((t for t in code if t.start > comment.start), None)
    return following is not None and following.kind == 'name' and \
        following.upper in ('PREFIX', 'BASE')


def _layout(text):
    every = tokens(text)
    code = [t for t in every if t.code]
    printer = _Printer()
    paren = 0                # ( ) nesting: an expression stays on one line
    bracket = 0              # [ ] nesting: a blank node stays on one line
    previous = None
    prologue = True
    pending_space_newlines = 0

    for index, token in enumerate(every):
        if token.kind == 'space':
            pending_space_newlines = token.text.count('\n')
            continue
        newlines_before, pending_space_newlines = pending_space_newlines, 0

        if token.kind == 'comment':
            if previous is None or newlines_before:
                printer.settle()
                if newlines_before > 1 and previous is not None:
                    printer.blank_wanted = True
                if prologue and previous is not None and not _more_prologue(code, token):
                    # The comment introduces the query: the blank line after
                    # the PREFIX block goes before it, not between it and SELECT.
                    prologue = False
                    printer.blank_wanted = True
                if not printer.at_start():
                    printer.newline()
                printer.put(token.text.rstrip(), False)
            else:
                printer.pending = False
                printer.line += '  ' + token.text.rstrip()
            printer.newline()
            continue
        printer.settle()

        word = token.upper if token.kind == 'name' else token.text
        current = _case(token)
        position = code.index(token)
        following = code[position + 1] if position + 1 < len(code) else None

        # --- where a line starts -------------------------------------------------
        if prologue and token.kind == 'name' and word in ('PREFIX', 'BASE'):
            if not printer.at_start():
                printer.newline()
        elif token.kind == 'name' and word in CLAUSES and paren == 0 and bracket == 0 \
                and not (word == 'BY'):
            if prologue:
                prologue = False
                if printer.lines or printer.line.strip():
                    if not printer.at_start():
                        printer.newline()
                    printer.blank_wanted = True
            if not printer.at_start():
                printer.newline()
            printer.continued = False
        elif token.kind == 'name' and word in STATEMENTS and paren == 0 and bracket == 0 \
                and printer.depth > 0 and not (previous and previous.upper == 'NOT'):
            if not printer.at_start():
                printer.newline()
            printer.continued = False
            if newlines_before > 1:
                printer.blank_wanted = True
        elif printer.depth > 0 and paren == 0 and bracket == 0 and printer.at_start() \
                and newlines_before > 1 and token.text != '}':
            printer.blank_wanted = True

        # --- the token itself ----------------------------------------------------
        if token.text == '{' and paren == 0:
            printer.put('{', previous is not None)
            printer.end_line()
            printer.depth += 1
            printer.continued = False
        elif token.text == '}' and paren == 0:
            if not printer.at_start():
                printer.newline()
            printer.depth = max(printer.depth - 1, 0)
            printer.continued = False
            printer.blank_wanted = False
            printer.put('}', False)
            nxt = following.upper if following and following.kind == 'name' else \
                (following.text if following else '')
            if nxt not in ('UNION', '.', ')', ','):
                printer.end_line()
        elif token.text == '.' and paren == 0 and bracket == 0 and printer.depth > 0:
            printer.put('.', True)
            printer.end_line()
            printer.continued = False
        elif token.text == ';' and paren == 0 and bracket == 0 and printer.depth > 0:
            printer.put(';', True)
            printer.end_line()
            printer.continued = True
        elif token.text == '(':
            space = previous is not None and not (
                previous.kind == 'name' and (previous.is_function or previous.upper in
                                             ('FILTER', 'BIND', 'IN', 'EXISTS')
                                             and previous.upper not in ('IN',))) \
                and previous.text not in ('(', '!', '^')
            if previous is not None and previous.kind == 'name' and previous.upper == 'IN':
                space = True
            if previous is not None and previous.kind in ('pname', 'iri') and paren > 0:
                space = False                   # a function named by IRI: ex:f(?x)
            printer.put('(', space)
            paren += 1
        elif token.text == ')':
            printer.put(')', False)
            paren = max(paren - 1, 0)
        elif token.text == '[':
            printer.put('[', previous is not None and previous.text != '(')
            bracket += 1
        elif token.text == ']':
            printer.put(']', previous is not None and previous.text != '[')
            bracket = max(bracket - 1, 0)
        elif token.text in (',',):
            printer.put(',', False)
        elif token.text == ';':
            printer.put(';', True)              # inside [ ] or ( ): stays inline
        elif token.text == '.':
            printer.put('.', paren == 0)
        elif token.text in ('^^',) or token.kind == 'lang':
            printer.put(current, False)
        elif previous is not None and previous.text in ('^^',):
            printer.put(current, False)
        elif previous is not None and previous.text == '!' and paren > 0:
            printer.put(current, False)
        elif previous is not None and previous.text == '(':
            printer.put(current, False)
        elif token.text == '!' and previous is not None and previous.text in ('(', '&&', '||', ','):
            printer.put('!', previous.text != '(')
        else:
            printer.put(current, previous is not None)

        previous = token

    return printer.text()
