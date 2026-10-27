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

"""A byte-span index over a Turtle file, keyed by subject (H3).

Invariant P2 says an edit through the cooked API changes only the triples
backing the edited element. rdflib cannot do that: it parses to a graph and
serialises the whole file fresh, which reorders statements, reassigns prefixes
and drops every comment. The kms shapes carry load-bearing comments -- the
explanation of why CartridgeShape needs a two-hop inverse path exists nowhere
else -- so a writer built on rdflib alone would delete the reasoning behind the
model on its first edit.

The plan timeboxed a spike (tree-sitter, or a purpose-built tokenizer) with
shape-block rewriting as the fallback. The tokenizer won: Turtle's statement
grammar is small, and what is needed is spans rather than semantics. It also
pays for itself twice, because the same index gives every shape a file:line
locator -- which is what provenance reports and what an editor will need.

What it understands, because each of these can hide a statement terminator:

  * comments      # to end of line, but NOT inside a string or an IRI
  * strings       "..." '...' \"\"\"...\"\"\" '''...''', with backslash escapes
  * nesting       [ ] blank node property lists, ( ) collections
  * directives    @prefix / @base / PREFIX / BASE, which are not subjects

It is not a Turtle parser and does not try to be. It locates statements; rdflib
remains the authority on what they mean.
"""

import bisect
from collections import OrderedDict
import re
from dataclasses import dataclass

# A directive, not a statement. The keyword must be either @-prefixed or
# followed by whitespace (SPARQL-style `PREFIX x: <…>` / `BASE <…>`): `\b`
# alone also matched `base:MachineState`, because ':' ends a word -- which threw
# away every statement whose subject used the `base:` prefix, and the kms uses
# it for the whole base_knowledge vocabulary. Silent: the statements parsed
# fine, they just had no locator, so jumps to them went nowhere.
DIRECTIVE = re.compile(r'^\s*(?:@(?:prefix|base)\b|(?:prefix|base)\s)',
                       re.IGNORECASE)
# The subject at the head of a statement: <iri>, prefix:name, or :name.
SUBJECT = re.compile(r'\s*(?:<(?P<iri>[^>]*)>|(?P<curie>[A-Za-z_][\w.-]*:[\w.-]*|:[\w.-]+))')


@dataclass(frozen=True)
class Block:
    """One Turtle statement: its subject, its text span and its line span."""
    subject: str          # IRI when resolvable, else the prefixed form as written
    raw_subject: str      # exactly as written in the file
    start: int            # byte offset of the first character
    end: int              # byte offset just past the terminating '.'
    start_line: int       # 1-based
    end_line: int

    def text(self, source):
        return source[self.start:self.end]


def _skip_string(text, i):
    """Return the index just past the string literal starting at i."""
    quote = text[i]
    triple = text[i:i + 3] in ('"""', "'''")
    delimiter = text[i:i + 3] if triple else quote
    i += len(delimiter)
    while i < len(text):
        if text[i] == '\\':
            i += 2
            continue
        if text.startswith(delimiter, i):
            return i + len(delimiter)
        i += 1
    return i  # unterminated; caller stops at EOF


def _statement_spans(text):
    """(start, end) for every top-level statement, terminator included."""
    spans = []
    i = 0
    start = None
    depth = 0
    while i < len(text):
        char = text[i]
        if char == '<':
            # An IRI. It must be skipped as one token, because a '#' inside it
            # is a fragment, not a comment -- reading <...shacl#> as a comment
            # swallowed the statement terminator and merged three statements
            # with the shape that followed them.
            closing = text.find('>', i)
            newline = text.find('\n', i)
            if closing != -1 and (newline == -1 or closing < newline):
                if start is None:
                    start = i
                i = closing + 1
                continue
        if char == '#':
            while i < len(text) and text[i] != '\n':
                i += 1
            continue
        if char in '"\'':
            if start is None:
                start = i
            i = _skip_string(text, i)
            continue
        if char in '[(':
            if start is None:
                start = i
            depth += 1
        elif char in '])':
            depth -= 1
        elif char == '.' and depth == 0 and start is not None:
            # A '.' inside a number or a prefixed name is not a terminator.
            following = text[i + 1:i + 2]
            if following == '' or following.isspace():
                spans.append((start, i + 1))
                start = None
                i += 1
                continue
        elif not char.isspace() and start is None:
            start = i
        i += 1
    return spans


def _resolve(raw, prefixes, base):
    if raw.startswith('<'):
        iri = raw[1:-1]
        return base + iri if base and not re.match(r'^[a-z][a-z0-9+.-]*:', iri, re.I) else iri
    prefix, _, name = raw.partition(':')
    namespace = prefixes.get(prefix)
    return namespace + name if namespace else raw


def _prefixes(text):
    found = {}
    base = ''
    for match in re.finditer(
            r'^\s*@?(prefix|base)\s+(?:([\w.-]*):)?\s*<([^>]*)>\s*\.?',
            text, re.IGNORECASE | re.MULTILINE):
        kind, prefix, iri = match.group(1).lower(), match.group(2), match.group(3)
        if kind == 'base':
            base = iri
        else:
            found[prefix or ''] = iri
    return found, base


_PARSED = OrderedDict()        # source text -> its blocks, most recent last
_PARSED_LIMIT = 32


def _blocks(source):
    """(blocks, {subject: block}) of a text, parsed once per distinct text.

    One `semforge check` indexed the same ontologies sixteen times: every
    caller builds its own index from the text it just read. Blocks are frozen
    and no caller changes the list, so equal texts share one.
    """
    found = _PARSED.get(source)
    if found is None:
        blocks = _parse(source)
        found = (blocks, {block.subject: block for block in blocks})
        _PARSED[source] = found
        if len(_PARSED) > _PARSED_LIMIT:
            _PARSED.popitem(last=False)
    else:
        _PARSED.move_to_end(source)
    return found


def _parse(source):
    prefixes, base = _prefixes(source)
    blocks = []
    # Line numbers counted forward from the previous statement: counting from
    # the start of the file for each one was quadratic -- 34 s for one 8.6 MB
    # ontology.
    line, counted = 1, 0
    for start, end in _statement_spans(source):
        line += source.count('\n', counted, start)
        counted = start
        chunk = source[start:end]
        if DIRECTIVE.match(chunk):
            continue
        match = SUBJECT.match(chunk)
        if not match:
            continue
        raw = match.group(0).strip()
        blocks.append(Block(
            subject=_resolve(raw, prefixes, base),
            raw_subject=raw,
            start=start, end=end,
            start_line=line,
            end_line=line + chunk.count('\n')))
    return blocks


class TurtleIndex:
    """Statement spans of one Turtle file, addressable by subject IRI."""

    def __init__(self, source, path=''):
        self.source = source
        self.path = path
        self.blocks, self._by_subject = _blocks(source)

    def block_for(self, subject):
        return self._by_subject.get(str(subject))

    def locator(self, subject):
        """'file:line' for a subject, or '' when it is not in this file."""
        block = self.block_for(subject)
        if block is None:
            return ''
        return f'{self.path}:{block.start_line}' if self.path else str(block.start_line)

    def __len__(self):
        return len(self.blocks)


INDEX_FORMAT = 1


def _seed(source, blocks):
    """Put known blocks where TurtleIndex(source) will find them."""
    _PARSED[source] = (blocks, {block.subject: block for block in blocks})
    if len(_PARSED) > _PARSED_LIMIT:
        _PARSED.popitem(last=False)


def index_file(path, cache_root=None):
    """The index of a Turtle file. With `cache_root` (the package), built once
    per content and kept in `.semforge/cache/index/` (rdfio/derived.py).

    The first page of the OPC UA pump package spent 1.8 s indexing 12.8 MB of
    ontology text to say where each attribute is declared; read back, the
    statements of every file take milliseconds.
    """
    with open(path, encoding='utf-8') as handle:
        source = handle.read()
    if cache_root is not None and source not in _PARSED:
        from .derived import cache_dir, entry_name, read_entry, write_entry

        directory = cache_dir(cache_root, 'index')
        slug, name = entry_name(path, source.encode('utf-8'))
        stored = read_entry(directory, name)
        blocks = None
        if isinstance(stored, dict) and stored.get('format') == INDEX_FORMAT:
            try:
                blocks = [Block(*row) for row in stored['blocks']]
            except (KeyError, TypeError):
                blocks = None
        if blocks is None:
            blocks = _parse(source)
            write_entry(directory, slug, name,
                        {'format': INDEX_FORMAT,
                         'blocks': [[b.subject, b.raw_subject, b.start, b.end,
                                     b.start_line, b.end_line] for b in blocks]},
                        'Turtle statement index')
        _seed(source, blocks)
    return TurtleIndex(source, path=path)


class PackageIndex:
    """One locator over every Turtle file of a role.

    A role may be one file or a directory of them, and the difference has to
    stop at this boundary: a caller asks where a subject IS, not which file to
    guess. Everything that edits a shape needs the same answer -- writing a
    constraint into `shacl.ttl` because that is the role's first file would put
    it in the wrong document as soon as there are two.

    A subject declared in two files is reported once, at its first occurrence in
    load order, and `files_for` gives all of them: splitting a subject across
    files is legal Turtle and the writer has to know it is not the whole story.
    """

    def __init__(self, paths, cache_root=None):
        self.paths = list(paths)
        self.indexes = {}
        for path in self.paths:
            self.indexes[path] = index_file(path, cache_root)

    def block_for(self, subject):
        """(path, block) for a subject, or (None, None)."""
        for path in self.paths:
            block = self.indexes[path].block_for(subject)
            if block is not None:
                return path, block
        return None, None

    def files_for(self, subject):
        """Every file with a statement about this subject."""
        return [path for path in self.paths
                if self.indexes[path].block_for(subject) is not None]

    def file_for(self, subject):
        """The file an edit to this subject belongs in, or None."""
        return self.block_for(subject)[0]

    def locator(self, subject):
        path, block = self.block_for(subject)
        return f'{path}:{block.start_line}' if block is not None else ''

    def text_for(self, subject):
        """(path, source) of the file holding this subject, or (None, '')."""
        path = self.file_for(subject)
        if path is None:
            return None, ''
        return path, self.indexes[path].source

    def source_of(self, path):
        return self.indexes[path].source

    def __len__(self):
        return sum(len(index) for index in self.indexes.values())


# --- terms ----------------------------------------------------------------------

# A term as written: <iri>, or a prefixed name. The lookbehind keeps a match
# from starting mid-word, which is what makes `https://…` inside a string read
# as nothing rather than as the prefix `https`. A local name may contain '.' but
# not end with one: in `ex:a .` the '.' terminates the statement.
TERM = re.compile(
    r'<(?P<iri>[^<>"{}|^`\\\s]*)>'
    r'|(?<![\w.:-])(?P<curie>(?:[A-Za-z][\w.-]*)?:[\w-](?:[\w.-]*[\w-])?)')


@dataclass(frozen=True)
class Term:
    """One term as it occurs in the text, and what it resolves to."""
    raw: str              # as written
    iri: str              # resolved, or the raw form when the prefix is unknown
    start: int            # byte offset of the first character
    end: int
    line: int             # 1-based
    column: int           # 0-based, of the first character
    quoted: bool          # inside a string literal -- a SPARQL body, say


def _resolve_term(match, prefixes, base):
    if match.group('iri') is not None:
        return _resolve(match.group(0), prefixes, base)
    return _resolve(match.group('curie'), prefixes, base)


_TERMS = OrderedDict()          # source text -> its terms, most recent last


def terms(source):
    """Every term in a Turtle file, in order, comments excluded -- a tuple.

    Kept per distinct text: the diagnostics scan every knowledge file for the
    terms it uses, and on the OPC UA pump package (12.8 MB) that was 3.4 s of
    every edit, for files the edit had not touched.
    """
    found = _TERMS.get(source)
    if found is None:
        found = tuple(_scan_terms(source))
        _TERMS[source] = found
        if len(_TERMS) > _PARSED_LIMIT:
            _TERMS.popitem(last=False)
    else:
        _TERMS.move_to_end(source)
    return found


def _scan_terms(source):
    """Every term in a Turtle file, in order, comments excluded.

    Strings are scanned too, because that is where a SPARQL constraint names the
    attributes it reads: a rename that finds `sh:path` and misses the `SELECT`
    has found half the uses. A query's own PREFIX declarations win over the
    file's inside that string. Prose in a string that happens to spell a term
    is reported as one -- it resolves to the same IRI, and a false positive in
    a list is cheaper than a use nobody was told about.
    """
    prefixes, base = _prefixes(source)
    newlines = [i for i, char in enumerate(source) if char == '\n']

    def position(offset):
        line = bisect.bisect_left(newlines, offset)
        return line + 1, offset - (newlines[line - 1] + 1 if line else 0)

    def found(match, local_prefixes, quoted):
        line, column = position(match.start())
        return Term(raw=match.group(0),
                    iri=_resolve_term(match, local_prefixes, base),
                    start=match.start(), end=match.end(),
                    line=line, column=column, quoted=quoted)

    out = []
    i = 0
    while i < len(source):
        char = source[i]
        if char == '#':
            while i < len(source) and source[i] != '\n':
                i += 1
            continue
        if char in '"\'':
            end = _skip_string(source, i)
            inner = dict(prefixes)
            for declared in re.finditer(
                    r'PREFIX\s+([\w.-]*):\s*<([^>]*)>',
                    source[i:end], re.IGNORECASE):
                inner[declared.group(1)] = declared.group(2)
            out.extend(found(match, inner, True)
                       for match in TERM.finditer(source, i, end))
            i = end
            continue
        match = TERM.match(source, i)
        if match:
            out.append(found(match, prefixes, False))
            i = match.end()
            continue
        i += 1
    return out
