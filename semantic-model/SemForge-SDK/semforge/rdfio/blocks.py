"""Locating property shapes inside a Turtle statement, by byte span.

The block index finds statements. Editing a constraint needs one level finer:
the `sh:property [ ... ]` group for a given attribute, and the span of one
parameter's value inside it, so that changing `sh:minCount 1` to `sh:minCount 0`
rewrites four bytes and leaves the rest of the file -- comments included --
untouched.

This is what invariant P2 costs. rdflib can find the triple in a heartbeat and
cannot tell you where it is in the file; the write-back would reserialise
everything and delete the reasoning the kms shapes carry in their comments.

Scope: it locates and it edits values. It does not parse Turtle -- rdflib
remains the authority on meaning, and every edit here is re-parsed before it is
trusted.
"""

import re
from dataclasses import dataclass, field

from .turtle_index import _skip_string

PARAMETER = re.compile(r'(sh:[A-Za-z]\w*|<[^>]*>)\s*')


@dataclass
class PropertyBlock:
    """One `sh:property [ ... ]` group."""
    start: int                 # offset of '['
    end: int                   # offset just past ']'
    path: str = ''             # the sh:path token, exactly as written
    parameters: dict = field(default_factory=dict)   # name -> (start, end, text)
    children: list = field(default_factory=list)
    depth: int = 0

    @property
    def inner(self):
        return self.start + 1, self.end - 1

    def parameter(self, name):
        return self.parameters.get(name)


def _skip_noise(text, i, limit):
    """Advance past whitespace, comments, strings and IRIs. Returns the index."""
    while i < limit:
        char = text[i]
        if char.isspace():
            i += 1
        elif char == '#':
            while i < limit and text[i] != '\n':
                i += 1
        elif char in '"\'':
            i = _skip_string(text, i)
        elif char == '<':
            closing = text.find('>', i)
            newline = text.find('\n', i)
            if closing != -1 and (newline == -1 or closing < newline):
                i = closing + 1
            else:
                return i
        else:
            return i
    return i


def _match_bracket(text, start, limit, pair='[]'):
    """Index just past the bracket closing the one at start.

    Counts BOTH kinds on the way, because a Turtle collection and a blank node
    interleave: `sh:or ( [ … sh:path ( [ … ] rdf:first ) ] … )`. Closing a `(`
    at the first `)` ended the token in the middle of that, and the scanner
    then read the rest of the collection as if it were the group's own
    parameters -- so the group's `sh:path` was whatever came last. Every
    attribute constrained with `sh:or` pointed at the wrong shape, or at none.
    """
    opening, closing_char = pair
    depth = 0
    i = start
    while i < limit:
        char = text[i]
        if char == '#':
            while i < limit and text[i] != '\n':
                i += 1
            continue
        if char in '"\'':
            i = _skip_string(text, i)
            continue
        if char == '<':
            closing = text.find('>', i)
            newline = text.find('\n', i)
            if closing != -1 and (newline == -1 or closing < newline):
                i = closing + 1
                continue
        if char == opening:
            depth += 1
        elif char == closing_char:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return limit


def _read_token(text, i, limit):
    """The next Turtle term after i, as (text, start, end)."""
    i = _skip_noise(text, i, limit)
    if i >= limit:
        return '', i, i
    start = i
    if text[i] == '<':
        closing = text.find('>', i)
        return text[i:closing + 1], start, closing + 1
    if text[i] in '"\'':
        end = _skip_string(text, i)
        return text[i:end], start, end
    if text[i] in '([':
        end = _match_bracket(text, i, limit,
                             '[]' if text[i] == '[' else '()')
        return text[i:end], start, end
    while i < limit and not text[i].isspace() and text[i] not in ';,]':
        i += 1
    return text[start:i], start, i


def _scan_group(text, start, end, depth):
    """Parse one bracketed group into a PropertyBlock."""
    block = PropertyBlock(start=start, end=end, depth=depth)
    i, limit = start + 1, end - 1
    while i < limit:
        i = _skip_noise(text, i, limit)
        if i >= limit:
            break
        if text[i] in ';,':
            i += 1
            continue
        match = PARAMETER.match(text, i)
        if not match:
            i += 1
            continue
        name = match.group(1)
        value, value_start, value_end = _read_token(text, match.end(), limit)
        if name == 'sh:property':
            # One predicate may carry several groups: [ … ], [ … ] ;
            position = value_start
            while position < limit and text[position] == '[':
                child_end = _match_bracket(text, position, limit)
                block.children.append(
                    _scan_group(text, position, child_end, depth + 1))
                position = _skip_noise(text, child_end, limit)
                if position < limit and text[position] == ',':
                    position = _skip_noise(text, position + 1, limit)
                else:
                    break
            i = position
            continue
        if name == 'sh:path':
            block.path = value
        else:
            block.parameters[name] = (value_start, value_end, value)
        i = value_end
    return block


def property_blocks(text, block):
    """Every `sh:property` group of a statement, nested as written."""
    groups = []
    i, limit = block.start, block.end
    while i < limit:
        i = _skip_noise(text, i, limit)
        if i >= limit:
            break
        match = PARAMETER.match(text, i)
        if match and match.group(1) == 'sh:property':
            position = _skip_noise(text, match.end(), limit)
            while position < limit and text[position] == '[':
                group_end = _match_bracket(text, position, limit)
                groups.append(_scan_group(text, position, group_end, 0))
                position = _skip_noise(text, group_end, limit)
                if position < limit and text[position] == ',':
                    position = _skip_noise(text, position + 1, limit)
                else:
                    break
            i = position
            continue
        i += 1
    return groups


def find_block(groups, path_chain):
    """The block reached by following a chain of sh:path tokens."""
    remaining = list(path_chain)
    candidates = groups
    found = None
    while remaining:
        wanted = remaining.pop(0)
        found = next((g for g in candidates if g.path == wanted), None)
        if found is None:
            return None
        candidates = found.children
    return found


def set_parameter(text, target, name, value):
    """Replace one parameter's value. Returns the new text."""
    located = target.parameter(name)
    if located is None:
        raise KeyError(name)
    start, end, _ = located
    return text[:start] + str(value) + text[end:]


def add_parameter(text, target, name, value):
    """Insert a parameter into a block, just before its closing bracket."""
    at = target.end - 1
    while at > target.start and text[at - 1].isspace():
        at -= 1
    separator = '' if text[at - 1] in '[;' else ' ;'
    return text[:at] + f'{separator} {name} {value}' + text[at:]


def remove_parameter(text, target, name):
    """Delete a parameter and the separator that follows it."""
    located = target.parameter(name)
    if located is None:
        raise KeyError(name)
    _, end, _ = located
    start = text.rfind(name, target.start, end)
    after = end
    while after < target.end and text[after] in ' \t':
        after += 1
    if after < target.end and text[after] == ';':
        after += 1
    return text[:start] + text[after:]
