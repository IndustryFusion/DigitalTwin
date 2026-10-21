"""Residue: everything evaluated but not asserted, pinned by digest (H4).

An example declares which verdicts it ASSERTS, never which constraints EXECUTE.
The applicable set is always evaluated in full; what the example does not talk
about is its residue, and residue is recorded rather than discarded.

That is what makes a new constraint impossible to hide: adding one changes the
residue of every example in its target class, so it surfaces as a delta the
author has to review and accept.

The digest must change when and only when a verdict changes, so nothing
unstable may enter it. Blank node labels in particular are not stable across
runs -- which is why a result is identified by the entity and attribute it was
climbed out to (normalise.owner_and_edge), and a shape by its IRI rather than
by pyshacl's anonymous source node.
"""

import hashlib


def canonical_lines(results):
    """Sorted, stable text form of a set of results."""
    return sorted(
        '|'.join((r.resource, r.attribute, r.component, r.shape,
                  r.status.value, r.severity))
        for r in results)


def residue_digest(results):
    """sha256 over the canonical form. Empty residue digests to a stable value."""
    body = '\n'.join(canonical_lines(results)).encode('utf-8')
    return 'sha256:' + hashlib.sha256(body).hexdigest()
