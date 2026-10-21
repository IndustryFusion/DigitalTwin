"""Deleting a test case, or a whole suite -- and saying what goes with it.

A case is a file and an entry in the expectations.yaml that declares it;
deleting only the file leaves an entry `semforge test` fails on, deleting
only the entry leaves a file nothing runs. So both go together. What a
deletion really costs is evidence: an assert is the proof that a constraint
can fire, and the last case asserting it takes that proof along. The plan
names those constraints before anything is written.

A file another case includes is shared data, not this case's: its entry
goes, the file stays. A suite is deleted whole -- refused while a case
outside it includes one of its files, which would then point at nothing.
"""

import os
import shutil

from ..errors import PackageError
from .store import EXPECTATIONS, _yaml, examples_root, expectation_files, load_expectations


def _relative(package, path):
    root = examples_root(package.path)
    path = str(path or '')
    if os.path.isabs(path):
        path = os.path.relpath(path, root)
    return path.replace('\\', '/').strip('/')


def _plan(package, doomed, suite=''):
    root = examples_root(package.path)
    examples = load_expectations(package.path).examples
    by_path = {e.path: e for e in examples}
    missing = [c for c in doomed if c not in by_path]
    if missing:
        raise PackageError(f'{missing[0]} is not a declared test case')
    remaining = [e for e in examples if e.path not in doomed]
    included = {}
    for example in remaining:
        for item in example.include:
            included.setdefault(str(item).replace('\\', '/'), []).append(example.path)

    if suite:
        reaching = sorted({who for item, cases in included.items()
                           if item.startswith(suite + '/') for who in cases})
        if reaching:
            raise PackageError(f'{", ".join(reaching)} include(s) a file in {suite}; deleted, '
                               'they would point at nothing. Change them first.')

    asserted_elsewhere = {str(a.get('constraint', '')) for e in remaining for a in e.asserts}
    lost = sorted({str(a.get('constraint', '')) for c in doomed for a in by_path[c].asserts}
                  - asserted_elsewhere)
    cases = [{'case': c, 'file': os.path.join(root, c), 'expect': by_path[c].expect,
              'asserts': len(by_path[c].asserts),
              'keptFile': bool(included.get(c)), 'includedBy': included.get(c, [])}
             for c in sorted(doomed)]
    return {'cases': cases, 'lost': lost, 'suite': suite,
            'folder': os.path.join(root, suite) if suite else ''}


def delete_plan(package, case='', suite=''):
    """What deleting the case (or the whole suite) removes, and what it costs."""
    if suite:
        suite = _relative(package, suite)
        root = examples_root(package.path)
        folder = os.path.normpath(os.path.join(root, suite))
        if not suite or not folder.startswith(os.path.normpath(root) + os.sep) or \
                not os.path.isdir(folder):
            raise PackageError(f'{suite} is not a suite folder under {root}')
        doomed = [e.path for e in load_expectations(package.path).examples
                  if e.path.startswith(suite + '/')]
        return _plan(package, doomed, suite)
    return _plan(package, [_relative(package, case)])


def delete_cases(package, case='', suite=''):
    """Delete the case (or the suite); the plan, as done."""
    plan = delete_plan(package, case, suite)
    root = examples_root(package.path)
    doomed = {c['case'] for c in plan['cases']}

    # The entries first, wherever they are declared.
    touched = set()
    for source in expectation_files(package.path):
        directory = os.path.dirname(source)
        with open(source, encoding='utf-8') as handle:
            raw = _yaml().load(handle) or {}
        entries = raw.get('examples') or []
        keep = [e for e in entries
                if _relative(package, os.path.join(directory, e.get('path', ''))) not in doomed]
        if len(keep) == len(entries):
            continue
        touched.add(directory)
        if keep:
            raw['examples'] = keep
            with open(source, 'w', encoding='utf-8') as handle:
                _yaml().dump(raw, handle)
        else:
            os.remove(source)                      # declares nothing any more

    removed = []
    if plan['suite']:
        shutil.rmtree(plan['folder'])
        removed = [c['file'] for c in plan['cases']]
    else:
        for item in plan['cases']:
            if not item['keptFile'] and os.path.exists(item['file']):
                os.remove(item['file'])
                removed.append(item['file'])
        # A good/ or bad/ left with nothing, and a suite left with neither, go.
        for directory in sorted(touched, key=len, reverse=True):
            for folder in (directory, os.path.dirname(directory)):
                if folder != root and os.path.isdir(folder) and not os.listdir(folder) and \
                        os.path.normpath(folder).startswith(os.path.normpath(root) + os.sep):
                    os.rmdir(folder)
    return dict(plan, removed=sorted(removed),
                kept=[c['file'] for c in plan['cases'] if c['keptFile'] and not plan['suite']],
                declaration=EXPECTATIONS)
