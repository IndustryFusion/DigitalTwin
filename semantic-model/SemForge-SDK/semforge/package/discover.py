"""Which package applies here.

Every other SDK answers this the same way: `cargo` walks up to Cargo.toml,
`npm` to package.json, `git` to .git. You can stand anywhere inside a project
and the tool knows which project you mean. SemForge did not -- `semforge
validate` read the current directory and nothing else, so running it one level
inside a package reported that package as missing all three of its roles, and
running it one level above reported the same thing. Both are the normal place
to be standing.

So: walk up, and take the first directory that is a package. Two things make a
directory one, in this order:

  * `semforge.yaml` -- the declared anchor. It wins even when a role is
    missing, because a package that says it is a package should be reported as
    broken rather than skipped in favour of some ancestor.
  * knowledge, shapes and model lying beside each other -- the kms layout,
    which predates the manifest and must keep working without one.

Nothing here looks DOWNWARD. An editor may (opening a folder above a package is
normal, and the extension searches a level down for exactly that reason), but a
command line must not: guessing which of several packages below you meant is
how a tool ends up validating something you were not looking at.
"""

import os

from .loader import DEFAULTS, FOLDERS, MODEL_FOLDER

MANIFEST = 'semforge.yaml'

# Why a directory counts, in the words the caller should see.
BY_MANIFEST = 'semforge.yaml'
BY_LAYOUT = 'knowledge, shapes and model beside each other'


def role_folders(role):
    """Directory names that may stand in for the role's file."""
    folders = list(FOLDERS.get(role, ([], ()))[0])
    if role == 'model' and MODEL_FOLDER not in folders:
        # `model/` is the grouping that holds the instance beside examples/.
        folders.append(MODEL_FOLDER)
    return folders


def has_role(directory, role):
    """Is this role present here, as a file or as a directory?"""
    for name in DEFAULTS.get(role, []):
        if os.path.isfile(os.path.join(directory, name)):
            return True
    return any(os.path.isdir(os.path.join(directory, folder))
               for folder in role_folders(role))


def missing_roles(directory):
    """The roles this directory does not have, in declaration order."""
    return [role for role in DEFAULTS if not has_role(directory, role)]


def is_package(directory):
    """Does this directory hold all three roles?"""
    return not missing_roles(directory)


def ancestors(start):
    """`start` and every directory above it, nearest first."""
    here = os.path.abspath(start)
    if os.path.isfile(here):
        here = os.path.dirname(here)
    while True:
        yield here
        parent = os.path.dirname(here)
        if parent == here:
            return
        here = parent


def find(start='.'):
    """(root, why) for the package that applies at `start`, else (None, '').

    `start` may be a file -- which is what an editor hands you -- or a
    directory, which is what a shell does.
    """
    for directory in ancestors(start):
        if os.path.isfile(os.path.join(directory, MANIFEST)):
            return directory, BY_MANIFEST
        if is_package(directory):
            return directory, BY_LAYOUT
    return None, ''


def root(start='.'):
    """The package directory that applies at `start`, or None."""
    return find(start)[0]


def explain(start='.'):
    """Why nothing was found -- with the search that was actually made.

    "not a package directory: ." told you what was not true about one
    directory. What you need is which directories were tried and what would
    have made any of them count.
    """
    looked = list(ancestors(start))
    if len(looked) > 5:
        looked = looked[:5] + [f'... and {len(looked) - 5} more, up to the root']
    wanted = ', '.join(
        f'{DEFAULTS[role][0]} (or {"/, ".join(role_folders(role))}/)'
        for role in DEFAULTS)
    return (
        f'no SemForge package at or above {os.path.abspath(start)}. '
        f'Looked in: {", ".join(looked)}. A package is a directory holding '
        f'{MANIFEST}, or holding {wanted}. '
        f'Run `semforge init` to make one here.'
    )


def describe(start='.'):
    """A report of what applies here: (root, why, roles) or (None, why, {}).

    `roles` maps each role to its directory-relative file or folder, which is
    the other half of the question -- knowing the root does not tell you
    whether the shapes are one file or eight.
    """
    found, why = find(start)
    if found is None:
        return None, explain(start), {}
    roles = {}
    for role in DEFAULTS:
        where = None
        for name in DEFAULTS[role]:
            if os.path.isfile(os.path.join(found, name)):
                where = name
                break
        if where is None:
            for folder in role_folders(role):
                if os.path.isdir(os.path.join(found, folder)):
                    where = folder + os.sep
                    break
        roles[role] = where
    return found, why, roles
