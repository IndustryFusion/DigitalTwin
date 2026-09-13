"""Reading and editing `semforge.yaml`.

Four modules read this file and each opened it for itself -- the context, the
prefixes, the dependency list, the entity root. None of them could say what a
package's settings ARE, so nothing could show them and nothing could change
one. "I want to get/update the project settings somewhere" had no answer.

Editing is **line-based on purpose**. Round-tripping through a YAML parser
would drop every comment in the file, and the comments are most of it -- the
scaffold writes a paragraph above each key saying what it decides. So a write
finds the key's line and replaces the value on it, leaving the rest of the
file byte-for-byte.
"""

import os
from dataclasses import dataclass, field

from ruamel.yaml import YAML

CONFIG = 'semforge.yaml'


@dataclass(frozen=True)
class Setting:
    """One line of `semforge.yaml`, as the editor shows it."""
    key: str                  # dotted: 'context.published'
    label: str
    value: str
    doc: str                  # what it decides, one line
    line: int = 0             # 1-based, 0 when the file does not declare it
    editable: bool = True
    default: str = ''         # what applies when it is not declared


# Declared rather than discovered: a settings list that is whatever happens to
# be in the file cannot show what you have NOT set, which is most of what you
# need to know about a package you did not write.
SPEC = [
    ('name', 'name', 'The package\'s name. Two directories called `test` are '
     'not the same project.'),
    ('context.local', 'local context',
     'Resolved while you work, so a term is usable the moment it is agreed.'),
    ('context.published', 'published context',
     'Where the context will be served. `semforge export` points the model '
     'here and checks it declares everything the model uses.'),
    ('entityRoot', 'entity root',
     'The class every entity type descends from -- what separates an entity '
     '(the target of a Relationship) from a vocabulary term (the value of a '
     'Property).'),
]

DEFAULTS = {
    'context.local': 'context.jsonld',
}


def path_for(package_path):
    return os.path.join(package_path, CONFIG)


def read(package_path):
    """The mapping in `semforge.yaml`, or {} when there is none."""
    where = path_for(package_path)
    if not os.path.isfile(where):
        return {}
    with open(where, encoding='utf-8') as handle:
        return YAML(typ='safe').load(handle) or {}


def _dig(data, key):
    here = data
    for part in key.split('.'):
        if not isinstance(here, dict) or part not in here:
            return None
        here = here[part]
    return here


def _indent(line):
    return len(line) - len(line.lstrip(' '))


def locate(package_path, key):
    """The 1-based line declaring `key`, or 0.

    A dotted key is found by its parent: `context.published` is the `published:`
    line indented under `context:`, not the first `published:` in the file.
    """
    where = path_for(package_path)
    if not os.path.isfile(where):
        return 0
    with open(where, encoding='utf-8') as handle:
        lines = handle.read().splitlines()

    parts = key.split('.')
    start, depth = 0, 0
    for part in parts[:-1]:
        found = _find(lines, part, start, depth, nested=True)
        if found is None:
            return 0
        start, depth = found + 1, depth + 1
    found = _find(lines, parts[-1], start, depth)
    return 0 if found is None else found + 1


def _find(lines, name, start, depth, nested=False):
    """The index of `name:` at the expected nesting, searching from `start`."""
    for at in range(start, len(lines)):
        line = lines[at]
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = _indent(line)
        if depth and indent == 0 and not nested:
            return None            # left the block this key lives in
        if depth and indent == 0 and at > start:
            return None
        if stripped.split(':')[0].strip() == name and ':' in stripped:
            return at
    return None


def settings(package_path):
    """Every declared setting, and every one that is not."""
    data = read(package_path)
    out = []
    for key, label, doc in SPEC:
        value = _dig(data, key)
        if key == 'name' and value is None:
            # No `name:` in the file: the directory is the name, and saying so
            # is better than an empty row.
            value = os.path.basename(os.path.abspath(package_path))
            out.append(Setting(key=key, label=label, value=str(value), doc=doc,
                               line=0, default='the directory name'))
            continue
        out.append(Setting(
            key=key, label=label,
            value='' if value is None else str(value), doc=doc,
            line=locate(package_path, key),
            default=DEFAULTS.get(key, '')))
    return out


@dataclass
class Collection:
    """A setting that is a mapping or a list, shown but edited in the file."""
    key: str
    label: str
    doc: str
    entries: list = field(default_factory=list)   # (name, value, line)


def collections(package_path):
    data = read(package_path)
    namespaces = data.get('namespaces') or {}
    dependencies = data.get('dependencies') or []
    return [
        Collection(
            key='namespaces', label='namespaces',
            doc='The package\'s agreed name for each namespace. One name per '
                'namespace: a second name evicts the first.',
            entries=[(name, str(value), locate_entry(package_path, 'namespaces', name))
                     for name, value in namespaces.items()]),
        Collection(
            key='dependencies', label='dependencies',
            doc='Packages whose knowledge is assembled into this one, pinned '
                'by digest.',
            entries=[(str(entry.get('name', '?')),
                      f'{entry.get("version", "")} {entry.get("sha256", "")}'.strip(),
                      0)
                     for entry in dependencies if isinstance(entry, dict)]),
    ]


def locate_entry(package_path, block, name):
    """The line of `name:` inside `block:`."""
    return locate(package_path, f'{block}.{name}')


def set_value(package_path, key, value):
    """Write one scalar setting, keeping every comment in the file.

    Returns (path, line). Creates `semforge.yaml` when the package has none --
    a package without a manifest is the kms layout, and the first setting
    somebody edits is a reasonable moment for it to acquire one.
    """
    where = path_for(package_path)
    lines = []
    if os.path.isfile(where):
        with open(where, encoding='utf-8') as handle:
            lines = handle.read().splitlines()

    at = locate(package_path, key) - 1
    parts = key.split('.')
    rendered = _render(value)

    if at >= 0:
        indent = _indent(lines[at])
        lines[at] = f'{" " * indent}{parts[-1]}: {rendered}'
        written = at
    elif len(parts) == 1:
        lines = _append(lines, f'{parts[-1]}: {rendered}', key)
        written = len(lines) - 1
    else:
        parent = locate(package_path, '.'.join(parts[:-1]))
        if parent:
            lines.insert(parent, f'  {parts[-1]}: {rendered}')
            written = parent
        else:
            lines = _append(lines, f'{parts[0]}:', key)
            lines.append(f'  {parts[-1]}: {rendered}')
            written = len(lines) - 1

    with open(where, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines).rstrip('\n') + '\n')
    return where, written + 1


def _append(lines, text, key):
    """Add a key at the end, with the paragraph that says what it decides.

    The scaffold writes a comment above every key. A key added later that
    arrives bare reads as less official than the ones around it.
    """
    import textwrap

    doc = next((entry[2] for entry in SPEC if entry[0] == key), '')
    if lines and lines[-1].strip():
        lines.append('')
    for wrapped in textwrap.wrap(doc, 74):
        lines.append(f'# {wrapped}')
    lines.append(text)
    return lines


def _render(value):
    """YAML for a scalar, quoted only when it has to be.

    A published context is a url and a namespace is a url; neither should come
    back from an edit wrapped in quotes it did not have.
    """
    text = str(value)
    if text == '':
        return "''"
    try:
        plain = YAML(typ='safe').load(text) == text
    except Exception:                              # noqa: BLE001
        plain = False
    if plain and text == text.strip() and ': ' not in text \
            and not text.startswith(('#', '&', '*', '!', '|', '>', '%', '@', '`')):
        return text
    return "'" + text.replace("'", "''") + "'"
