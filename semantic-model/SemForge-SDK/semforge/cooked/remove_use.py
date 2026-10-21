"""Removing ONE use of a term -- what a quick fix on a single finding does.

`remove_attribute` takes every use at once, after showing them all. A quick fix
is the opposite gesture: the author is looking at one line the sanity check
marked, and wants that line dealt with and nothing else. So each function here
removes exactly the thing at the given place, verifies the file still parses,
and refuses rather than guess when the place does not hold what was expected.
"""

import json
import os

from rdflib import Graph

from ..errors import PackageError
from ..rdfio import TurtleIndex
from .remove_attribute import _groups, _remove_span


def remove_property_at(path, offset):
    """Remove the sh:property group whose sh:path term sits at `offset`.

    The innermost group containing the offset is the one: a nested attribute's
    marker is inside its parent's group too, and removing the parent would take
    far more than the line that was marked.
    """
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    statement = next((b for b in TurtleIndex(text).blocks
                      if b.start <= offset < b.end), None)
    if statement is None:
        raise PackageError('the marked line is no longer inside a statement; '
                           'revalidate and try again')
    best = None
    for group, parent in _groups(text, statement):
        if group.start <= offset < group.end and \
                (best is None or group.start >= best[0].start):
            best = (group, parent)
    if best is None:
        raise PackageError('no property shape at the marked place; the file '
                           'has changed since it was checked')
    group, parent = best
    start, end = (parent.start + 1, parent.end - 1) if parent else \
        (statement.start, statement.end)
    updated = _remove_span(text, group, start, end)
    Graph().parse(data=updated, format='turtle')
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(updated)
    return text.count('\n', 0, group.start) + 1


def remove_assert(source, case, index):
    """Remove one assert from one case in an expectations file."""
    from ..expect.store import _yaml

    with open(source, encoding='utf-8') as handle:
        raw = _yaml().load(handle) or {}
    entry = next((e for e in raw.get('examples') or []
                  if e.get('path') == case), None)
    asserts = (entry or {}).get('asserts') or []
    if entry is None or not 0 <= index < len(asserts):
        raise PackageError(f'{case} has no assert {index} any more; the file '
                           f'has changed since it was checked')
    del asserts[index]
    note = ''
    if not asserts:
        del entry['asserts']
        if entry.get('expect') == 'invalid':
            note = (f'{case} expects a violation but no longer asserts one -- '
                    f'give it a new assert, or remove the case')
    with open(source, 'w', encoding='utf-8') as handle:
        _yaml().dump(raw, handle)
    return note


def remove_key_at(package, path, line, iri):
    """Remove the attribute key on `line` of a document, if it means `iri`."""
    from ..editor.references import _Expander
    from .examples import _write
    from .jsonloc import locate

    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    document = json.loads(text)
    index = locate(text)
    expand = _Expander(package).for_file(path)
    if expand is None:
        raise PackageError(f'{os.path.basename(path)} has no @context, so its '
                           f'keys mean nothing that could be matched')
    target = next((address for address, at in index.items()
                   if at == line and address and isinstance(address[-1], str)
                   and expand(address[-1]) == iri), None)
    if target is None:
        raise PackageError(f'no key meaning {iri} on line {line} any more; the '
                           f'file has changed since it was checked')
    node = document
    for step in target[:-1]:
        node = node[step]
    del node[target[-1]]
    _write(path, document, text)
    return line
