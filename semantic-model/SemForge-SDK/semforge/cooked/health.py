"""The package health page: is this package in good shape, and what needs
attention first.

Everything here is already computed somewhere -- `semforge test`, `validate`,
`check`, `--coverage`, the cache -- but each answers one question in one
place, and nothing put them side by side. This gathers them once into a few
figures and one list, ordered by how much each item matters:

  error    a test case that fails; a reference that points at nothing; an
           undeclared attribute used in a test case
  warning  a violation in the model; a constraint no example makes fire (a
           constraint that cannot fire looks exactly like one that holds);
           a query naming an undeclared term
  note     an undeclared key in the scratchpad; a declared attribute nothing
           uses

Every item carries what its action needs: a file and line, a case, or an
entity type, so the page can open the right thing in one click.
"""

import os

from rdflib import URIRef

RANK = {'error': 0, 'warning': 1, 'note': 2}
# Within a severity: what is broken before what is untested.
AREA = {'test': 0, 'reference': 1, 'vocabulary': 2, 'model': 3, 'coverage': 4}


def _short(term):
    return str(term).rsplit('/', 1)[-1].rsplit('#', 1)[-1].split(':')[-1]


def _shape_types(package):
    """{shape CURIE: entity type local name it targets}, for 'open the type'."""
    from ..validate.normalise import curie
    from ..validate.shapes import class_targets, node_shapes

    out = {}
    for shape in node_shapes(package.shapes):
        found = class_targets(package.shapes, shape)
        target = found[0] if found else None
        if isinstance(target, URIRef):
            out[curie(package.shapes, shape)] = str(target)
    return out


def _namer(shapes):
    """A shape's name for a reader: the local name, unless two shapes share
    it -- the kms has two CartridgeShapes -- in which case the CURIE."""
    counts = {}
    for shape in shapes:
        counts[_short(shape)] = counts.get(_short(shape), 0) + 1
    return lambda shape: shape if counts.get(_short(shape), 0) > 1 else _short(shape)


def build_health(package):
    """The payload the package health page renders. Reads only."""
    from ..editor.cache import status as cache_status
    from ..expect import coverage
    from ..expect.runner import constraint_ref, run_tests
    from ..expect.vocabulary import undeclared_attributes
    from ..sanity import known_constraints, sanity
    from ..validate import validate_package
    from .typepage import _cases

    items = []

    def item(severity, area, text, **action):
        items.append(dict({'severity': severity, 'area': area, 'text': text}, **action))

    # --- the test cases ----------------------------------------------------------
    cases = _cases(package)
    outcomes = run_tests([(example, report) for example, _, report in cases],
                         known_constraints(package))
    files = {example.path: os.path.abspath(os.path.join(package.examples_dir, example.path))
             for example, _, _ in cases}
    failing = [o for o in outcomes if not o.passed]
    for outcome in failing:
        item('error', 'test', f'{outcome.example} fails: ' + '; '.join(outcome.failures[:2])
             + (f' (and {len(outcome.failures) - 2} more)' if len(outcome.failures) > 2 else ''),
             case=files.get(outcome.example, ''))

    # --- the model ---------------------------------------------------------------------
    report = validate_package(package, strict=False)
    by_constraint = {}
    for result in report.violations:
        by_constraint.setdefault(constraint_ref(result), []).append(str(result.resource))
    shape_types = _shape_types(package)
    name = _namer(shape_types)
    for ref, resources in sorted(by_constraint.items(), key=lambda kv: -len(kv[1])):
        shape = ref.split('/')[0]
        parts = ref.split('/')
        what = ' · '.join(parts[1:]).replace('ConstraintComponent', '')
        item('warning', 'model',
             f'{len(resources)} model entit{"y" if len(resources) == 1 else "ies"} violate '
             f'{name(shape)} · {what}: {", ".join(sorted(resources)[:4])}'
             + (' …' if len(resources) > 4 else ''),
             type=_short(shape_types.get(shape, '')) if shape in shape_types else '')

    # --- coverage --------------------------------------------------------------------------
    entries = coverage([(example, case_report) for example, _, case_report in cases])
    never = {}
    for entry in entries:
        if not entry.has_firing:
            never.setdefault(entry.constraint.split('/')[0], []).append(entry.constraint)
    for shape, refs in sorted(never.items(), key=lambda kv: -len(kv[1])):
        attributes = sorted({r.split('/')[1] for r in refs if len(r.split('/')) == 3})
        item('warning', 'coverage',
             f'{name(shape)}: {len(refs)} constraint(s) no example makes fire'
             + (f' ({", ".join(attributes[:4])}{" …" if len(attributes) > 4 else ""})'
                if attributes else ' (its SPARQL rule)'),
             type=_short(shape_types.get(shape, '')) if shape in shape_types else '')

    # --- references ---------------------------------------------------------------------------
    found = sanity(package)
    for finding in found:
        severity = {'error': 'error', 'warning': 'warning'}.get(finding.severity, 'note')
        item(severity, 'reference', finding.message.split('. ')[0] + '.',
             at=f'{finding.file}:{finding.line}')
    undeclared = undeclared_attributes(package)
    for entry in undeclared:
        where, line = entry.places[0]
        item('error' if entry.severity == 'error' else 'note', 'vocabulary',
             f'{entry.term} is used in the data and declared nowhere'
             + (f' ({len(entry.places)} places)' if len(entry.places) > 1 else ''),
             at=f'{os.path.abspath(where)}:{line}')

    items.sort(key=lambda i: (RANK[i['severity']], AREA[i['area']]))
    cache = cache_status(package.path)
    errors = sum(1 for f in found if f.severity == 'error') + \
        sum(1 for e in undeclared if e.severity == 'error')
    return {
        'name': os.path.basename(os.path.abspath(package.path)),
        'path': package.path,
        'tiles': {
            'cases': len(outcomes), 'casesPassing': len(outcomes) - len(failing),
            'modelViolations': len(report.violations),
            'modelConstraints': len(by_constraint),
            'evaluated': len(report.evaluated),
            'neverFired': sum(len(refs) for refs in never.values()),
            'neverFiredShapes': len(never),
            'brokenReferences': errors,
            'cacheViews': len(cache['entries']), 'cacheCurrent': cache['current'],
        },
        'attention': items,
        'counts': {severity: sum(1 for i in items if i['severity'] == severity)
                   for severity in RANK},
    }
