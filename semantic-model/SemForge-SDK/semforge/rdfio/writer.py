"""Editing a Turtle artifact in place, touching only what changed (P2).

The edit is a text insertion located by the block index, not a reserialisation.
Everything outside the edited statement is byte-identical afterwards, and so is
everything inside it that the edit did not add -- including comments, which
rdflib would have dropped and which in the kms shapes are the only record of why
several constraints are written the way they are.
"""

import re

from ..errors import PackageError
from .turtle_index import TurtleIndex

INDENT = '    '


def _insertion_point(source, block):
    """Offset just before the statement's terminating '.', and its indent.

    Inserting there appends a new predicate-object to the subject rather than
    starting a new statement, which is what keeps the diff to the shape.
    """
    i = block.end - 1                      # the '.' itself
    while i > block.start and source[i - 1].isspace():
        i -= 1
    line_start = source.rfind('\n', block.start, i) + 1
    indent = re.match(r'[ \t]*', source[line_start:]).group(0) or INDENT
    return i, indent


def property_constraint_text(path, parameters, indent=INDENT):
    """A sh:property block for one attribute.

    Values are emitted as written by the caller: they are Turtle terms, and
    quoting them here would turn every IRI into a string. A value that is
    itself a list of (name, value) pairs is a nested blank node -- which is how
    the NGSI-LD encoding's inner layer is written -- and must carry its own
    `sh:path` as the first pair.
    """
    lines = _block_lines(indent, [('sh:path', path)] + list(parameters))
    lines[0] = f'{indent}sh:property [ ' + lines[0].lstrip()
    # The leading ' ;' joins this to the predicate-object list already there;
    # no trailing one, because the statement's own '.' follows.
    return ' ;\n' + '\n'.join(lines)


def _block_lines(indent, pairs):
    """The inside of a `[ ... ]`, one predicate per line, closed with ' ]'."""
    lines = []
    for name, value in pairs:
        if isinstance(value, (list, tuple)):
            inner = _block_lines(indent + INDENT, value)
            inner[0] = f'{indent}{INDENT}{name} [ ' + inner[0].lstrip()
            inner[-1] += ' ;'
            lines.extend(inner)
        else:
            lines.append(f'{indent}{INDENT}{name} {value} ;')
    lines[-1] = lines[-1].removesuffix(' ;') + ' ]'
    return lines


def add_property_constraint(path_or_source, shape, attribute_path, parameters,
                            source=None):
    """Add a sh:property constraint to an existing shape.

    Returns the new file content. Raises PackageError when the shape is not in
    this file -- silently appending a second statement for the same subject
    would be valid Turtle and a confusing diff.
    """
    if source is None:
        with open(path_or_source, encoding='utf-8') as handle:
            source = handle.read()
        path = path_or_source
    else:
        path = ''

    index = TurtleIndex(source, path=path)
    block = index.block_for(shape)
    if block is None:
        raise PackageError(
            f'{shape} is not a statement in {path or "this file"}; '
            f'nothing to add a constraint to')

    at, indent = _insertion_point(source, block)
    text = property_constraint_text(attribute_path, parameters, indent)
    # The statement's '.' stays on the block's last line, as it is written
    # everywhere else; a newline here left it alone, unindented, below. The
    # insertion point is before whatever space preceded the '.', so that space
    # is kept as it was.
    return source[:at] + text + source[at:]
