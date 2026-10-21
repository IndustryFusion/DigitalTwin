"""A disk cache for what the editor shows, valid exactly as long as its inputs.

Opening a window used to rebuild every view and every diagnostic from nothing:
load, validate, run the example suite, walk the knowledge. None of it depends
on anything but the package's files and the SDK's own code, so each result is
stored beside the package, stamped with a fingerprint of both, and served
again while the fingerprint still matches.

The fingerprint is every file under the package (path, size, modification
time) plus every source file of the SDK. Any edit, a checkout, a new example,
an SDK update -- each changes it, and the next request recomputes. Nothing is
ever served stale by design; when in doubt, `rescan` (or deleting the cache)
recomputes regardless.

Where: `<package>/.semforge/cache/views/`, one JSON file per view. It carries
its own `.gitignore`, so a package under version control never commits it.
"""

import hashlib
import json
import os
import shutil
import time

VIEWS = os.path.join('.semforge', 'cache', 'views')
SKIP_DIRS = {'.semforge', 'node_modules', '__pycache__', '.git', 'venv'}
_sdk_fingerprint = None


def views_dir(root):
    return os.path.join(root, VIEWS)


def _sdk():
    """The SDK's own code, so an update never serves a view an old one built."""
    global _sdk_fingerprint
    if _sdk_fingerprint is None:
        from .. import __version__

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        digest = hashlib.sha256(__version__.encode())
        for directory, dirs, names in sorted(os.walk(here)):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(names):
                if name.endswith(('.py', '.ttl')):
                    stat = os.stat(os.path.join(directory, name))
                    digest.update(f'{directory}/{name}:{stat.st_size}:'
                                  f'{stat.st_mtime_ns}'.encode())
        _sdk_fingerprint = digest.hexdigest()
    return _sdk_fingerprint


def fingerprint(root):
    """Every file the package is made of, as (path, size, mtime), hashed."""
    digest = hashlib.sha256(_sdk().encode())
    # Following links: a package may symlink a role or its examples in -- the
    # test corpus does both -- and an edit behind a link is still an edit.
    for directory, dirs, names in os.walk(root, followlinks=True):
        dirs[:] = sorted(d for d in dirs
                         if d not in SKIP_DIRS and not d.startswith('.'))
        for name in sorted(names):
            path = os.path.join(directory, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            digest.update(f'{os.path.relpath(path, root)}:{stat.st_size}:'
                          f'{stat.st_mtime_ns}\n'.encode())
    return digest.hexdigest()


def _entry(root, key):
    return os.path.join(views_dir(root), f'{key}.json')


def load(root, key, stamp=None):
    """The cached payload for `key` if its fingerprint still matches, else None."""
    path = _entry(root, key)
    try:
        with open(path, encoding='utf-8') as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        return None
    if stored.get('fingerprint') != (stamp or fingerprint(root)):
        return None
    return stored.get('payload')


def store(root, key, payload, stamp=None):
    """Write a payload, atomically -- a torn file must read as a miss."""
    directory = views_dir(root)
    try:
        os.makedirs(directory, exist_ok=True)
        ignore = os.path.join(directory, '.gitignore')
        if not os.path.exists(ignore):
            with open(ignore, 'w', encoding='utf-8') as handle:
                handle.write('# The SemForge editor cache: derived, never committed.\n*\n')
        temporary = _entry(root, key) + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as handle:
            json.dump({'fingerprint': stamp or fingerprint(root),
                       'created': time.time(), 'payload': payload}, handle)
        os.replace(temporary, _entry(root, key))
    except OSError:
        pass                    # a read-only package still works, uncached


def cached(root, key, compute, force=False):
    """`compute()` once per fingerprint. Returns (payload, hit)."""
    stamp = fingerprint(root)
    if not force:
        payload = load(root, key, stamp)
        if payload is not None:
            return payload, True
    payload = compute()
    store(root, key, payload, stamp)
    return payload, False


def status(root):
    """What the cache holds: entries, bytes, and how many are still current."""
    directory = views_dir(root)
    entries, size, current = [], 0, 0
    stamp = fingerprint(root)
    if os.path.isdir(directory):
        for name in sorted(os.listdir(directory)):
            if not name.endswith('.json'):
                continue
            path = os.path.join(directory, name)
            size += os.path.getsize(path)
            try:
                with open(path, encoding='utf-8') as handle:
                    fresh = json.load(handle).get('fingerprint') == stamp
            except (OSError, ValueError):
                fresh = False
            current += fresh
            entries.append({'view': name[:-5], 'current': fresh})
    return {'path': directory, 'entries': entries, 'bytes': size,
            'current': current}


def clear(root, contexts=False):
    """Delete the view cache -- and, asked to, the downloaded contexts too.

    Returns the bytes freed. The contexts are shared by every package on the
    machine, so they go only when asked: deleting them means the next scan
    downloads the NGSI-LD core context again.
    """
    from ..package.context import _fetched, user_context_cache

    freed = 0
    targets = [views_dir(root)] + ([user_context_cache()] if contexts else [])
    for directory in targets:
        if not os.path.isdir(directory):
            continue
        for current, _, names in os.walk(directory):
            freed += sum(os.path.getsize(os.path.join(current, n)) for n in names)
        shutil.rmtree(directory, ignore_errors=True)
    if contexts:
        _fetched.clear()
    return freed
