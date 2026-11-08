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

"""A published version has changed: say so once, and offer the next ones.

openspec change gh-939-kms-package, "The editor warns when a published package
changes". The edit is never blocked -- a warning that stops work gets switched
off -- but it is said the moment it matters, once per version, with the three
versions that would make the change legitimate.

Every write the editor makes ends in `session.forget`, and a save typed into a
file ends in `validation.publish`; both call `check_after_write`. It costs a
stat for a package that was never published (no release record), and a hash
of the members, without parsing anything, for one that was.
"""

import os
import threading

NOTIFICATION = 'semforge/publishedChanged'

_warned = set()                  # (root, version) already told
_lock = threading.Lock()


def published_change(root):
    """{'name', 'version', 'next'} when the current, published version of the
    package at `root` no longer has its recorded digest; otherwise None."""
    from ..package.conformance import check
    from ..package.releases import next_versions, record_path, released

    if not os.path.isfile(record_path(root)):
        return None
    report = check(root, parse=False)
    if not report.version:
        return None
    entry = released(root, report.version)
    if entry is None or report.content_digest == entry.get('digest'):
        return None
    return {'name': report.name, 'version': report.version,
            'next': next_versions(report.version)}


def check_after_write(root, ls=None):
    """Notify the client the first time a published version is changed."""
    if not root:
        return None
    try:
        change = published_change(root)
    except Exception:                              # noqa: BLE001 -- never fail an edit
        return None
    if change is None:
        with _lock:
            # A raised version, or the change undone: tell again next time.
            for key in [k for k in _warned if k[0] == root]:
                _warned.discard(key)
        return None
    key = (root, change['version'])
    with _lock:
        if key in _warned:
            return None
        _warned.add(key)
    message = dict(change, root=root,
                   message=f'{change["name"]} {change["version"]} is published; '
                           f'this change needs a new version.')
    try:
        from .protocol import path_to_uri, server
        message['uri'] = path_to_uri(root)
        (ls or server).protocol.notify(NOTIFICATION, message)
    except Exception:                              # noqa: BLE001 -- no client: nothing to tell
        pass
    return message


def reset():
    """Forget what was told (tests)."""
    with _lock:
        _warned.clear()
