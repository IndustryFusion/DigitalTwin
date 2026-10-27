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

"""The loaded packages: one version each, read again when its files change.

A version is reused as far as its files allow (package/loader.py,
package/patches.py), warmed before the first click, and its graphs kept out
of the cycle collector's way. What is derived from one lives with its graphs
(rdfio/frozen.py) or in the disk cache under its fingerprint (cache.py).
Also kept here: what the shapes were, to see a rename typed into the file.
"""

import gc
import os
import threading

from .analysis import package_root
from .protocol import field, uri_to_path


_packages = {}
_stamps = {}               # root -> fingerprint the loaded package was read at


def view(root, key, compute, params=None):
    """A view's payload, from the disk cache while the package is unchanged.

    With `detail: summary` in the request the tree comes back slimmed
    (editor/slim.py). The full payload is what is cached; the summary is a
    cheap pass over it, so one entry serves both modes.
    """
    from .cache import cached
    from .slim import SLIM

    warm(root)
    payload, hit = cached(root, key, compute)
    payload = dict(payload, cached=hit)
    if params is not None and field(params, 'detail') == 'summary' \
            and key in SLIM and payload.get('roots'):
        payload['roots'] = SLIM[key](payload['roots'], payload)
        payload['detail'] = 'summary'
    return payload


_load_lock = threading.Lock()


def package_for(root):
    """The loaded package, reloaded whenever its files changed.

    Keyed on the same fingerprint the disk cache uses: a checkout or an edit
    in another editor changes it just as the server's own writes do, and a
    view must never be computed from a package that is no longer on disk.
    Locked: the verdict worker loads from its own thread, and two loads of one
    package at once would only double the wait.
    """
    from ..package import load
    from .cache import fingerprint

    with _load_lock:
        stamp = fingerprint(root)
        if _stamps.get(root) != stamp or root not in _packages:
            _packages[root] = load(root, reuse=_reusable(root))
            _stamps[root] = stamp
            _previous[root] = (_packages[root], _role_stamps(_packages[root]))
            _watch_renames(root, _packages[root])
            # The package's graphs stay for every request that follows: two
            # million objects on the OPC UA pumps, which each full pass of the
            # cycle collector walked again -- a second, at random, inside a
            # click. Frozen, the collector leaves them alone (as the
            # validation worker does, editor/incremental.py).
            gc.freeze()
            _tidy_later()
        return _packages[root]


# Frozen objects are never collected: the graphs an edit replaced would stay
# for the whole session. So once the edits have been quiet for a while, the
# collector is given one pass over everything -- a second, while nobody is
# clicking -- and what is left frozen again.
TIDY_AFTER = 20.0
_tidy_timer = None


def _tidy_later():
    global _tidy_timer
    if _tidy_timer is not None:
        _tidy_timer.cancel()
    _tidy_timer = threading.Timer(TIDY_AFTER, _tidy)
    _tidy_timer.daemon = True
    _tidy_timer.start()


def _tidy():
    with _load_lock:
        gc.unfreeze()
        gc.collect()
        gc.freeze()


# The last package loaded, with its knowledge and shapes files as (path, mtime,
# size): kept even when an edit drops the loaded package, so the reload after
# a one-line change to a case reuses the 217,582 knowledge triples of the OPC UA
# pumps instead of reading them again (2.9 s on every edit).
_previous = {}


def _role_stamps(package):
    stamps = {}
    for role in ('knowledge', 'shapes'):
        try:
            stamps[role] = [(path, os.stat(path).st_mtime_ns, os.stat(path).st_size)
                            for path in package.files(role)]
        except OSError:
            stamps[role] = None
    return stamps


def _reusable(root):
    """{role: (documents, graph)} of the last load whose files are untouched."""
    held = _previous.get(root)
    if held is None:
        return None
    package, stamps = held
    reuse = {}
    for role, before in stamps.items():
        if before is None:
            continue
        try:
            now = [(path, os.stat(path).st_mtime_ns, os.stat(path).st_size)
                   for path, _, _ in before]
        except OSError:
            continue
        if now == before:
            reuse[role] = ([path for path, _, _ in before], getattr(package, role))
        elif role == 'shapes' and len(before) == 1:
            # One shapes file a cooked edit just wrote: its graph patched
            # rather than parsed again (package/patches.py), when certain.
            from ..package import patches
            graph = patches.patched(before[0][0], package.shapes)
            if graph is not None:
                reuse[role] = ([before[0][0]], graph)
    return reuse


_warmed = {}             # root -> the fingerprint it was warmed at
_warm_lock = threading.Lock()


def warm(root):
    """Load the package, index its files and start its validation -- in the
    background, once per package version, as soon as anything asks about it.

    The views come from the disk cache without loading the package, so the
    first click used to pay the load (2.6 s on the OPC UA pumps) and the text
    index (1.8 s) itself. Started by the first request instead, both are
    usually done before anyone clicks; a click that comes earlier waits for
    them rather than doing them twice (both are locked).
    """
    from .cache import fingerprint

    stamp = fingerprint(root)
    with _warm_lock:
        if _warmed.get(root) == stamp:
            return
        _warmed[root] = stamp
    threading.Thread(target=_warm_up, args=(root,), daemon=True,
                     name=f'semforge-warm:{os.path.basename(root)}').start()


def _warm_up(root):
    try:
        package = package_for(root)
        for role in ('knowledge', 'shapes'):
            package.index(role)
        from .validation import service
        service().get(root)
    except Exception:                              # noqa: BLE001 -- a head start, never a failure
        pass


# A shape renamed by typing in the .ttl leaves its asserts behind. Between two
# reads of a package, a shape vanishing as one saying exactly the same appears
# is that rename; it is kept until the next save offers to carry them along.
_shape_prints = {}
_pending_renames = {}


def rename_baseline(uri):
    """The shapes as they are on disk now, before the editor's change is saved.

    Views are served from the disk cache, so the package may never be loaded
    before the first save -- and a rename needs a "before" to be seen. Opening
    or first changing a file of the package is the last moment the disk still
    holds it.
    """
    root = package_root(uri_to_path(uri))
    if root is None or root in _shape_prints:
        return
    try:
        from ..cooked.rename import shape_prints
        package = package_for(root)
        _shape_prints.setdefault(root, shape_prints(package))
    except Exception:                              # noqa: BLE001 -- a hint, never a failure
        pass


def _watch_renames(root, package):
    from ..cooked.rename import renamed_pairs, shape_prints

    try:
        now = shape_prints(package)
    except Exception:                              # noqa: BLE001 -- a hint, never a failure
        return
    before = _shape_prints.get(root)
    _shape_prints[root] = now
    if before is not None:
        for pair in renamed_pairs(before, now):
            if pair not in _pending_renames.setdefault(root, []):
                _pending_renames[root].append(pair)


def forget(root, renames=False):
    """The package's files changed: read it again on the next request. With
    `renames`, also what its shapes were -- a write that moves shapes is not
    a rename typed into the file."""
    _packages.pop(root, None)
    if renames:
        _shape_prints.pop(root, None)
        _pending_renames.pop(root, None)


def take_renames(root):
    """The renames typed into the package's shapes since they were last offered."""
    return _pending_renames.pop(root, [])
