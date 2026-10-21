"""What deleting a project would take with it.

Nothing here deletes anything. It answers the question a delete button has to
ask first -- what is in there, what of it is not the package, and whether any
of it can be got back -- because "are you sure?" is not a warning. A person can
only be sure about something they have been told.

Three things are worth knowing before the click, and a package cannot tell you
any of them by looking at its own artifacts:

  * **what is not the package.** A project directory collects things: a README
    somebody wrote, a scratch file, a vendored copy, a whole second package.
    Those are what a deletion actually costs, and they are what the plan lists
    first.
  * **whether git has it.** Tracked files come back with one command; untracked
    ones do not come back at all. That is the difference between an annoyance
    and a loss, and it is knowable.
  * **that it is the folder you have open.** Deleting it out from under the
    window is legal and confusing.

The deleting itself belongs to the editor, which can move a directory to the
trash rather than unlinking it. This module deliberately has no rmtree.
"""

import os
import subprocess
from dataclasses import dataclass, field

# What the layout puts there. Everything else in a project directory was put
# there by a person, and is what a deletion actually costs.
KNOWN = {
    'semforge.yaml', 'context.jsonld', 'knowledge.ttl', 'shacl.ttl',
    'main.jsonld', 'model-instance.jsonld', 'model.jsonld', 'README.md',
}
KNOWN_DIRS = {
    'knowledge', 'shacl', 'shapes', 'model', 'main', 'model-instance',
    'examples', '.semforge',
}


@dataclass
class DeletionPlan:
    path: str
    name: str = ''
    is_package: bool = False
    files: int = 0
    bytes: int = 0
    strangers: list = field(default_factory=list)   # not part of the layout
    nested: list = field(default_factory=list)      # packages inside this one
    tracked: int = 0                                # files git knows
    untracked: int = 0                              # files git does not
    in_git: bool = False
    warnings: list = field(default_factory=list)
    error: str = ''


def _walk(path):
    for here, directories, names in os.walk(path):
        directories[:] = [d for d in directories if d != '.git']
        for name in names:
            yield os.path.join(here, name)


def _git(path, *arguments):
    try:
        done = subprocess.run(('git', '-C', path) + arguments,
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return [line for line in done.stdout.splitlines() if line.strip()]


def plan_deletion(path):
    """Everything a delete button should say, and nothing it should do."""
    from .discover import find, is_package

    root = os.path.abspath(path)
    plan = DeletionPlan(path=root, name=os.path.basename(root))
    if not os.path.isdir(root):
        plan.error = f'{root} is not a directory'
        return plan

    found = find(root)[0]
    plan.is_package = found == root
    if not plan.is_package:
        plan.error = (
            f'{root} is not a SemForge package' +
            (f' -- the package here is {found}' if found else '') +
            '. Only a package is deletable from here; anything else is a '
            'directory this tool knows nothing about.')
        return plan

    from .config import read

    plan.name = str(read(root).get('name') or plan.name)

    for entry in sorted(os.listdir(root)):
        if entry in KNOWN or entry in KNOWN_DIRS or entry.startswith('.'):
            continue
        full = os.path.join(root, entry)
        if os.path.isdir(full) and is_package(full):
            plan.nested.append(entry + os.sep)
        else:
            plan.strangers.append(entry + (os.sep if os.path.isdir(full) else ''))

    for file in _walk(root):
        plan.files += 1
        try:
            plan.bytes += os.path.getsize(file)
        except OSError:
            pass

    tracked = _git(root, 'ls-files', '--', '.')
    if tracked is not None:
        plan.in_git = True
        plan.tracked = len(tracked)
        others = _git(root, 'ls-files', '--others', '--exclude-standard', '--', '.')
        plan.untracked = len(others or [])

    plan.warnings = _warnings(plan)
    return plan


def _warnings(plan):
    """What to put in front of somebody about to do this."""
    out = []
    if plan.nested:
        out.append(
            f'It contains {len(plan.nested)} package(s) of its own: '
            f'{", ".join(plan.nested)} — those go too.')
    if plan.strangers:
        shown = ', '.join(plan.strangers[:6])
        more = f', and {len(plan.strangers) - 6} more' if len(plan.strangers) > 6 \
            else ''
        out.append(
            f'{len(plan.strangers)} item(s) here are not part of the package: '
            f'{shown}{more}. Nothing else knows what they are.')
    if not plan.in_git or not plan.tracked:
        out.append(
            'Nothing here is tracked by git, so nothing can bring it back.'
            if plan.in_git else
            'This directory is not in a git repository, so nothing can bring '
            'it back.')
    elif plan.untracked:
        out.append(
            f'{plan.tracked} file(s) are tracked by git and can be restored; '
            f'{plan.untracked} are not, and cannot.')
    else:
        out.append(
            f'All {plan.tracked} file(s) are tracked by git, so this is '
            f'recoverable with `git checkout`.')
    return out
