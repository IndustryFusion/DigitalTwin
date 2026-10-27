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

"""Derived files kept beside a package: one entry per source file and content.

What loading derives from a file -- its parsed triples (package/graphcache.py),
its statement index (rdfio/turtle_index.py) -- is kept in
`.semforge/cache/<kind>/`, named by the source file and the sha256 of its
content: an edit misses, and writing the new entry removes the old one, so
there is one version per file. JSON only, never pickle: the directory is in
the package, and a cloned package must not be able to run code through it.
"""

import hashlib
import json
import os
import re


def cache_dir(package_path, kind):
    return os.path.join(package_path, '.semforge', 'cache', kind)


def entry_name(path, data):
    """(slug, file name) for a source file with this content (bytes)."""
    slug = re.sub(r'[^A-Za-z0-9_.-]+', '_', os.path.abspath(path))[-80:]
    return slug, f'{slug}.{hashlib.sha256(data).hexdigest()[:32]}.json'


def read_entry(directory, name):
    """The stored payload, or None when there is none or it does not read."""
    try:
        with open(os.path.join(directory, name), encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def write_entry(directory, slug, name, payload, what):
    """Store a payload atomically, replacing older versions of the same file.

    Never raises for a package that cannot be written to: it still loads,
    only uncached. The temporary name carries the process id, since the
    editor's server and its validation worker may write the same entry.
    """
    try:
        os.makedirs(directory, exist_ok=True)
        ignore = os.path.join(directory, '.gitignore')
        if not os.path.exists(ignore):
            with open(ignore, 'w', encoding='utf-8') as handle:
                handle.write(f'# {what}: derived, never committed.\n*\n')
        for old in os.listdir(directory):
            if old.startswith(slug + '.') and old != name and old.endswith('.json'):
                try:
                    os.remove(os.path.join(directory, old))
                except OSError:
                    pass
        temporary = os.path.join(directory, f'{name}.{os.getpid()}.tmp')
        with open(temporary, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, separators=(',', ':'))
        os.replace(temporary, os.path.join(directory, name))
    except OSError:
        pass
