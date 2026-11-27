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

"""A KMS package keeps its own history in git, so no change is without a way back.

An exported package carries no git, and an edit -- SemForge's or a hand's --
would otherwise overwrite the only copy. So whenever the editor opens a
package it makes sure the package is tracked:

  * not in a git repository -- `git init` in the package and commit every
    file as the starting point;
  * its own repository with uncommitted changes -- commit them, as changes
    made outside SemForge;
  * after every write SemForge makes -- commit it, naming what changed;
  * `semforge publish` -- tag the published version `v<version>`.

Every package gets its OWN repository, also inside another one (a source
checkout): `git init` in the package folder, and the enclosing repository
keeps tracking whatever it tracked there -- SemForge never commits into it.

Commits are made as "SemForge", unsigned and without hooks: they record the
package, not a person, and a signing setup or a commit hook must never make
an edit fail. Dot-files are never package members (package/conformance.py),
so `.git` and `.gitignore` change neither the digest nor an export.

A package that must not get a history of its own -- one a source checkout
keeps, like the kms example in DigitalTwin, where a nested repository and
SemForge's commits would only be in the way -- has a `.semforge-no-history`
file in its folder. A dot-file is no package member: it changes no digest and
is not exported, so a package extracted from there is tracked again.
SEMFORGE_HISTORY=off turns it all off, for every package.
"""

import os
import subprocess
import threading
import time

IDENTITY = ('-c', 'user.name=SemForge', '-c', 'user.email=semforge@localhost',
            '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', '-c', 'tag.forceSignAnnotated=false',
            '-c', 'core.hooksPath=', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf',
            '-c', 'core.quotePath=false')
IGNORE = """\
# Written by SemForge: what is derived, not authored.
.semforge/
*.kms.zip
*.kms.zip.part
"""
OUTSIDE = 'Changes made outside SemForge'
# Never package content (the fingerprint skips them too, editor/cache.py).
EXCLUDED = 'node_modules/\n__pycache__/\nvenv/\n'
NO_HISTORY = '.semforge-no-history'

_locks = {}
_guard = threading.Lock()


def enabled(root=None):
    """History is kept -- not turned off for every package, nor for this one."""
    if os.environ.get('SEMFORGE_HISTORY', '').lower() in ('off', '0', 'false', 'no'):
        return False
    return not (root and os.path.exists(os.path.join(root, NO_HISTORY)))


def _lock(root):
    with _guard:
        return _locks.setdefault(root, threading.Lock())


# Where git looks for a repository and an index, when the process that started
# the editor (a hook, a rebase's exec shell) set it: never inherited, or the
# commits would go into that other repository.
LOCATION = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
            'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_COMMON_DIR', 'GIT_NAMESPACE', 'GIT_PREFIX')
START = 'Start tracking '
STARTED = 'semforge-started'          # in the git folder: SemForge started this repository


def _env():
    env = {k: v for k, v in os.environ.items() if k not in LOCATION}
    env.update(LC_ALL='C', LANGUAGE='C')     # its messages are read: never translated
    return env


def _git(root, *arguments, check=False):
    """(exit code, stdout) of git in `root`; (None, '') when git cannot run.
    An index another git holds (VS Code's own, refreshing) is waited for."""
    return _git_err(root, *arguments, check=check)[:2]


def _git_err(root, *arguments, check=False):
    """(exit code, stdout, stderr) of git in `root`."""
    for attempt in range(6):
        try:
            done = subprocess.run(('git', '-C', root) + IDENTITY + arguments,
                                  capture_output=True, text=True, timeout=60,
                                  stdin=subprocess.DEVNULL, env=_env())
        except (OSError, subprocess.SubprocessError) as exc:
            if check:
                raise RuntimeError(f'git {" ".join(arguments)}: {exc}') from exc
            return None, '', ''
        if done.returncode == 0 or 'index.lock' not in done.stderr or attempt == 5:
            break
        time.sleep(0.1 * (attempt + 1))
    if check and done.returncode != 0:
        raise RuntimeError(f'git {" ".join(arguments)}: {done.stderr.strip()}')
    return done.returncode, done.stdout, done.stderr


def _linked(root):
    """A link among the package's files or folders: git stores the link, so
    changes behind it would never be committed."""
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ('.git', '.semforge')]
        for name in dirs + files:
            if os.path.islink(os.path.join(here, name)):
                return os.path.relpath(os.path.join(here, name), root)
    return None


def mode(root):
    """'own' (a history SemForge started: the package folder is the top of a
    repository whose first commit is SemForge's), 'foreign' (the folder is the
    top of a repository SemForge did not start: a clone, a checkout -- that
    repository's history, not the editor's), 'untracked' (no repository of
    its own: inside another one or none), 'linked' (the package links files
    from elsewhere) or 'none' (git is not available)."""
    code, top, error = _git_err(root, 'rev-parse', '--show-toplevel')
    if code is None:
        return 'none'
    if code != 0 and 'not a git repository' not in error.lower():
        return 'foreign'                  # a repository git refuses to read (ownership, damage)
    if code == 0 and os.path.realpath(top.strip()) == os.path.realpath(root):
        if not _started_here(root):
            return 'foreign'
        return 'linked' if _linked(root) else 'own'
    return 'linked' if _linked(root) else 'untracked'


def _started_here(root):
    """SemForge started this repository: the mark `_start` leaves in its git
    folder, or -- for one started before the mark existed -- a single root
    commit that is SemForge's "Start tracking …". Never a guess from the
    folder, and never a clone: the mark stays in the git folder it was made
    in, and the fallback holds only for a repository without a remote."""
    code, gitdir = _git(root, 'rev-parse', '--absolute-git-dir')
    if code != 0:
        return False
    if os.path.isfile(os.path.join(gitdir.strip(), STARTED)):
        return True
    code, remotes = _git(root, 'remote')
    if code != 0 or remotes.strip():
        return False
    code, roots = _git(root, 'rev-list', '--max-parents=0', 'HEAD')
    roots = roots.split()
    if code != 0 or len(roots) != 1:
        return False
    code, first = _git(root, 'log', '-1', '--format=%an%x1f%ae%x1f%s', roots[0])
    author, email, subject = (first.strip().split('\x1f') + ['', '', ''])[:3]
    return author == 'SemForge' and email == 'semforge@localhost' and subject.startswith(START)


def _changes(root):
    """[(status, path)] of what `git add -A` would stage, relative to the package."""
    code, out = _git(root, 'status', '--porcelain', '--untracked-files=all', '--', '.')
    if code != 0:
        return []
    found = []
    for line in out.splitlines():
        status, path = line[:2], line[3:]
        if ' -> ' in path:
            path = path.split(' -> ', 1)[1]
        found.append((status.strip() or '?', path.strip('"')))
    return found


def summary(changes):
    """'add a.jsonld; change b.yaml; delete c.jsonld' -- what a commit holds."""
    words = {'?': 'add', 'A': 'add', 'M': 'change', 'D': 'delete', 'R': 'rename'}
    groups = {}
    for status, path in changes:
        verb = next((words[c] for c in status if c in words), 'change')
        groups.setdefault(verb, []).append(path)
    parts = []
    for verb in ('add', 'change', 'rename', 'delete'):
        paths = groups.get(verb, [])
        if paths:
            shown = ', '.join(paths[:4]) + (f' and {len(paths) - 4} more' if len(paths) > 4 else '')
            parts.append(f'{verb} {shown}')
    return '; '.join(parts)


def _commit(root, title):
    """Commit everything in the package; the commit made, or None if clean."""
    changes = _changes(root)
    if not changes:
        return None
    _git(root, 'add', '-A', '--', '.', check=True)
    body = summary(changes)
    if title == 'SemForge edit':
        title = 'SemForge: ' + (body if len(body) <= 62 else body[:59] + '...')
    _git(root, 'commit', '-q', '--no-verify', '-m', title, '-m', body, check=True)
    _set_redo(root, [])                      # a new change: what was undone is not redone
    return {'title': title, 'files': [p for _, p in changes]}


def _start(root):
    """A repository in the package, its files committed as the starting point."""
    _git(root, 'init', '-q', check=True)
    _, gitdir = _git(root, 'rev-parse', '--absolute-git-dir', check=True)
    with open(os.path.join(gitdir.strip(), STARTED), 'w', encoding='utf-8') as handle:
        handle.write('This repository was started by SemForge: it keeps the package\'s history.\n')
    # What is derived stays out whatever a .gitignore of the package says:
    # the repository's own exclude file, which is no package file.
    exclude = os.path.join(gitdir.strip(), 'info', 'exclude')
    os.makedirs(os.path.dirname(exclude), exist_ok=True)
    with open(exclude, 'a', encoding='utf-8') as handle:
        handle.write(IGNORE + EXCLUDED)
    ignore = os.path.join(root, '.gitignore')
    if not os.path.exists(ignore):
        with open(ignore, 'w', encoding='utf-8') as handle:
            handle.write(IGNORE)
    return _commit(root, f'{START}{_name(root)}')


def _name(root):
    from . import config
    try:
        descriptor = config.read(root)
    except Exception:                               # noqa: BLE001
        descriptor = {}
    name = str(descriptor.get('name') or os.path.basename(os.path.normpath(root)))
    version = descriptor.get('version')
    return f'{name} {version}' if version else name


def ensure(root, title=OUTSIDE):
    """Make sure the package is tracked and committed. Returns what was done:
    {'mode', 'started', 'commit'} -- never raises; a failure is reported."""
    root = os.path.abspath(root)
    if not enabled(root):
        return {'mode': 'off', 'started': False, 'commit': None}
    with _lock(root):
        try:
            found = mode(root)
            if found in ('none', 'foreign', 'linked'):
                return {'mode': found, 'started': False, 'commit': None}
            if found == 'untracked':
                return {'mode': 'own', 'started': True, 'commit': _start(root)}
            return {'mode': 'own', 'started': False, 'commit': _commit(root, title)}
        except Exception as exc:                    # noqa: BLE001
            return {'mode': 'failed', 'started': False, 'commit': None, 'error': str(exc)}


# --- undo and redo -----------------------------------------------------------------
#
# Undo steps the package back one commit (`git reset --hard HEAD~1`) and keeps
# the commit it left on a redo stack; redo steps forward onto it again. Any new
# commit empties the stack, as in every editor. Outside changes are committed
# first, so undo never discards anything: the step back is itself undoable by
# redo, and every state stays in git (the reflog holds even a dropped redo).

class Refused(Exception):
    """Undo or redo cannot be done now; the message says why."""


def _redo_file(root):
    code, out = _git(root, 'rev-parse', '--absolute-git-dir')
    return os.path.join(out.strip(), 'semforge-redo') if code == 0 else None


def _redo(root):
    where = _redo_file(root)
    if not where or not os.path.exists(where):
        return []
    with open(where, encoding='utf-8') as handle:
        return [line.strip() for line in handle if line.strip()]


def _set_redo(root, stack):
    where = _redo_file(root)
    if where:
        with open(where, 'w', encoding='utf-8') as handle:
            handle.write(''.join(f'{sha}\n' for sha in stack))


def _head(root):
    code, out = _git(root, 'rev-parse', '-q', '--verify', 'HEAD')
    return out.strip() if code == 0 else None


def _title(root, sha):
    return _git(root, 'log', '-1', '--format=%s', sha)[1].strip()


def _ready(root):
    """The package committed and its own repository -- or Refused."""
    if not enabled(root):
        raise Refused(why_not(root, 'off'))
    done = ensure(root)
    if done['mode'] != 'own':
        raise Refused(done.get('error') or why_not(root, done['mode']) or 'there is no history')
    return done


def state(root, limit=30):
    """{'mode', 'undo', 'redo', 'log'}: the titles the next undo and redo
    would take back and bring back, and the last commits, newest first."""
    root = os.path.abspath(root)
    found = mode(root) if enabled(root) else 'off'
    if found != 'own':
        return {'mode': found, 'undo': None, 'redo': None, 'log': [], 'reason': why_not(root, found)}
    with _lock(root):
        code, out = _git(root, 'log', f'-{limit}', '--format=%H%x1f%s%x1f%cI%x1f%D')
        log = []
        for line in out.splitlines() if code == 0 else []:
            sha, title, date, refs = (line.split('\x1f') + ['', '', '', ''])[:4]
            tags = [r.split('tag: ', 1)[1] for r in refs.split(', ') if r.startswith('tag: ')]
            log.append({'sha': sha, 'title': title, 'date': date, 'tags': tags})
        stack, head = _redo(root), _head(root)
        redo = None
        if stack and head and _git(root, 'rev-parse', f'{stack[-1]}^')[1].strip() == head:
            redo = _title(root, stack[-1])
        return {'mode': 'own', 'undo': log[0]['title'] if len(log) > 1 else None,
                'redo': redo, 'log': log}


def why_not(root, found):
    """The message Undo, Redo and History… give for a package without a history."""
    if found == 'off':
        if not enabled():
            return 'the package history is turned off (SEMFORGE_HISTORY)'
        return (f'this package keeps no history of its own ({NO_HISTORY}); a source checkout '
                'around it has one')
    if found == 'foreign':
        return ('this package folder is a repository SemForge did not start (a clone, a checkout): '
                'its history is that repository\'s, and the editor leaves it alone')
    if found == 'linked':
        return (f'this package links {_linked(root)} from elsewhere: git would not see its changes, '
                'so the package keeps no history')
    if found == 'none':
        return 'git is not available, so there is no history'
    return None


def undo(root):
    """Step back one commit. Returns {'undone': title, 'now': title}."""
    root = os.path.abspath(root)
    _ready(root)
    with _lock(root):
        head = _head(root)
        code, parent = _git(root, 'rev-parse', '-q', '--verify', 'HEAD^')
        if not head or code != 0:
            raise Refused('nothing to undo: this is where the history starts')
        undone = _title(root, head)
        _git(root, 'reset', '-q', '--hard', parent.strip(), check=True)
        _set_redo(root, _redo(root) + [head])
        return {'undone': undone, 'now': _title(root, 'HEAD')}


def redo(root):
    """Step forward onto what the last undo left. Returns {'redone': title}."""
    root = os.path.abspath(root)
    _ready(root)
    with _lock(root):
        stack, head = _redo(root), _head(root)
        if not stack:
            raise Refused('nothing to redo')
        target = stack[-1]
        if _git(root, 'rev-parse', f'{target}^')[1].strip() != head:
            _set_redo(root, [])
            raise Refused('nothing to redo: the package changed since the undo')
        _git(root, 'reset', '-q', '--hard', target, check=True)
        _set_redo(root, stack[:-1])
        return {'redone': _title(root, target)}


def back_to(root, sha):
    """Go back to the package as it was right after commit `sha` -- every
    later step undone, each redoable. Returns {'undone': [titles], 'now'}."""
    root = os.path.abspath(root)
    _ready(root)
    with _lock(root):
        code, _ = _git(root, 'merge-base', '--is-ancestor', sha, 'HEAD')
        if code != 0:
            raise Refused(f'{sha[:8]} is not an earlier state of this package')
        code, out = _git(root, 'rev-list', f'{sha}..HEAD')
        later = out.split() if code == 0 else []          # newest first
        if not later:
            raise Refused('the package is at that state already')
        titles = [_title(root, s) for s in later]
        _git(root, 'reset', '-q', '--hard', sha, check=True)
        _set_redo(root, _redo(root) + later)                # the oldest on top: redone first
        return {'undone': titles, 'now': _title(root, 'HEAD')}


def tag(root, version):
    """Tag the package's current commit `v<version>` (after a publish).
    An existing tag is never moved. Returns the tag or None.

    Only in a history the package already has: publishing never STARTS one.
    `semforge publish` runs in CI too, on a package a repository checkout
    holds, and a repository started there would hide its files from that
    checkout. The editor starts the history (session.package_for)."""
    root = os.path.abspath(root)
    if not enabled(root) or mode(root) != 'own':
        return None
    done = ensure(root, f'Publish {version}')
    if done['mode'] != 'own':
        return None
    name = f'v{version}'
    with _lock(root):
        code, _ = _git(root, 'rev-parse', '-q', '--verify', f'refs/tags/{name}')
        if code == 0:
            return None
        code, _ = _git(root, 'tag', '-a', name, '-m', f'Published {version}')
        return name if code == 0 else None
