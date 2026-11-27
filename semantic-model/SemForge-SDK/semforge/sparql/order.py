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

"""The join order of a basic graph pattern, chosen while it is evaluated.

rdflib orders a BGP's triple patterns ONCE: at parse time by how many terms
are constants (every `[ … ]` blank node and every variable counts as
unknown, and `$this` is not bound yet), and again on entry by what is bound
at that moment. After that the order is fixed. A NGSI-LD query is a chain of
`?a p [ ngsi-ld:hasObject ?b ]` patterns that all score the same, so the
fixed order soon reaches a pattern that shares nothing with what is bound,
and the nested loops build a cross product: a 12-pattern constraint over
6,435 triples and ONE focus node took 70 s from the bench and 353 s with
`$this` written in as a constant.

Here the next pattern is picked at every step from the bindings made so far:
the one with the most bound terms, subject and object counting more than the
predicate, ties kept in rdflib's order. The solutions are the same -- a BGP
is a conjunction, any order gives the same multiset -- only the work
changes; the query above takes 0.05 s.

It is installed through rdflib's CUSTOM_EVALS hook, so it serves every query
in the process: the workbench, Inspect, and pyshacl's SPARQL constraints and
rules in `semforge test`.
"""

from rdflib.plugins.sparql.sparql import AlreadyBound

NAME = 'semforge-bgp-order'


def _score(ctx, triple):
    s, p, o = (ctx[term] for term in triple)
    return 2 * (s is not None) + 2 * (o is not None) + (p is not None)


def evaluate(ctx, patterns):
    """The solutions of `patterns` (a list of triples) in `ctx`."""
    if not patterns:
        yield ctx.solution()
        return
    best = max(range(len(patterns)), key=lambda i: (_score(ctx, patterns[i]), -i))
    s, p, o = patterns[best]
    rest = patterns[:best] + patterns[best + 1:]
    _s, _p, _o = ctx[s], ctx[p], ctx[o]
    for ss, sp, so in ctx.graph.triples((_s, _p, _o)):
        c = ctx.push() if None in (_s, _p, _o) else ctx
        try:
            if _s is None:
                c[s] = ss
            if _p is None:
                c[p] = sp
            if _o is None:
                c[o] = so
        except AlreadyBound:            # a variable used twice, bound to another term
            continue
        yield from evaluate(c, rest)


def _custom(ctx, part):
    if part.name == 'BGP':
        return evaluate(ctx, list(part.triples))
    raise NotImplementedError


def install():
    """Evaluate every BGP in this process with the dynamic order. Idempotent."""
    from rdflib.plugins.sparql import CUSTOM_EVALS
    CUSTOM_EVALS[NAME] = _custom


def uninstall():
    from rdflib.plugins.sparql import CUSTOM_EVALS
    CUSTOM_EVALS.pop(NAME, None)
