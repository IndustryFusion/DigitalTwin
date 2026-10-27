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

"""Loaded graphs are frozen, and what is derived from one is kept with it.

A package reloaded after an edit reuses the graphs of every file that did not
change (package/loader.py, editor/session.py), and a shapes file the editor
wrote becomes a NEW graph (package/patches.py). A graph is therefore one
version of its files: what was derived from it holds for as long as it lives,
and goes with it. That is the whole validity rule -- identity -- and it holds
only because nothing writes into a loaded graph. `freeze` makes that a fact
rather than a promise: a frozen graph refuses add, remove, set and addN.

`derived(graph, name, compute, depends, key)` is the one way to keep a value
derived from loaded graphs: `graph` holds it, `depends` are the other frozen
graphs it read (compared by identity, held weakly), `key` anything else it
depends on. A graph that is not frozen keeps nothing -- whoever may still
change it gets a fresh value every time, never a stale one.

The other caches are of other things and keep their own rule:
  * text -> what is parsed from it (rdfio/turtle_index.py, the lru_caches of
    cooked/valueforms.py, payloads.py, knowledge.py): the text is the key;
  * file -> entry on disk (rdfio/derived.py): the content's sha256;
  * per package version (package/loader.Package.index, editor/cache.py,
    editor/verdicts.py): the package's fingerprint.
"""

import weakref

from rdflib import Graph

_STORE = '_semforge_derived'


class FrozenGraphError(RuntimeError):
    """Something tried to change a loaded graph."""


def _refuse(*args, **kwargs):
    raise FrozenGraphError(
        'a loaded graph is frozen (rdfio/frozen.py): what is derived from it '
        'is kept with it -- write the file and load it again, or copy the graph')


_WRITERS = ('add', 'addN', 'remove', 'set', 'parse')


def freeze(graph):
    """Make `graph` read-only and give it a store for what is derived from it.
    Idempotent; returns the graph."""
    if not is_frozen(graph):
        for writer in _WRITERS:
            graph.__dict__[writer] = _refuse
        graph.__dict__[_STORE] = {}
    return graph


def is_frozen(graph):
    return isinstance(graph, Graph) and _STORE in graph.__dict__


def _part(value):
    return weakref.ref(value) if isinstance(value, Graph) else value


def derived(graph, name, compute, depends=(), key=(), keep=1):
    """compute(), kept with `graph` under `name` for these `depends` and
    `key`; at most `keep` values per name, the most recent last."""
    if not is_frozen(graph) or not all(is_frozen(other) for other in depends):
        return compute()
    full = tuple(_part(other) for other in depends) + tuple(_part(part) for part in key)
    kept = graph.__dict__[_STORE].setdefault(name, [])
    for at, (held, value) in enumerate(kept):
        if held == full:
            if at != len(kept) - 1:
                kept.append(kept.pop(at))
            return value
    value = compute()
    kept.append((full, value))
    del kept[:-keep]
    return value
