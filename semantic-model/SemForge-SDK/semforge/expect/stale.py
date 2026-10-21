"""Asserts left behind by a rename, and the constraint they most likely meant.

An assert names a constraint by its shape: `ns:Shape/attribute/Component`.
Rename the shape in the .ttl by hand and the assert names a shape that is
gone -- the case fails for a reason that has nothing to do with its data.
SemForge's own Rename… carries asserts along; a rename typed into the file
cannot, so what is left is to recognise the leftovers and say which
constraint they meant.

The rule is deliberately narrow: an assert is retargeted only to a
constraint with the same attribute and component, and only when exactly one
shape declares it -- or, where the case's results are known, exactly one
that fires on the asserted resource. Anything less certain is left to the
author, with Remove as the other fix.
"""

from ..errors import PackageError


def _tail(constraint):
    """`attribute/Component` (or `Component`) -- the part a rename keeps."""
    return str(constraint).split('/', 1)[1] if '/' in str(constraint) else ''


def suggestion(constraint, known, firing=None):
    """The constraint a stale assert most likely meant, or ''.

    `known` are the constraints the shapes declare; `firing`, when given, the
    ones the case's report shows firing on the asserted resource.
    """
    tail = _tail(constraint)
    if not tail:
        return ''
    same = sorted(k for k in known if _tail(k) == tail and k != constraint)
    if len(same) == 1:
        return same[0]
    if firing is not None:
        fired = [k for k in same if k in set(firing)]
        if len(fired) == 1:
            return fired[0]
    return ''


def retarget_assert(source, case, index, constraint):
    """Point one assert of one case at `constraint`, in place."""
    from .store import _yaml

    with open(source, encoding='utf-8') as handle:
        raw = _yaml().load(handle) or {}
    entry = next((e for e in raw.get('examples') or [] if e.get('path') == case), None)
    asserts = (entry or {}).get('asserts') or []
    if entry is None or not 0 <= index < len(asserts):
        raise PackageError(f'{case} has no assert {index} any more; the file has changed '
                           'since it was checked')
    old = asserts[index].get('constraint')
    if any(a.get('constraint') == constraint and a.get('resource') == asserts[index].get('resource')
           for a in asserts):
        # The case already says it: the stale one is a duplicate, and goes.
        del asserts[index]
        note = f'{case} already asserted {constraint}; the stale {old} is removed'
    else:
        asserts[index]['constraint'] = constraint
        note = ''
    with open(source, 'w', encoding='utf-8') as handle:
        _yaml().dump(raw, handle)
    return note
