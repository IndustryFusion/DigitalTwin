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

"""Whether a SPARQL expression can be deployed, asked of the compiler itself.

Validation evaluates any SPARQL; the platform runs what shacl2flink compiles
to Flink SQL, which is less. A list of its own of what that is would drift, so
each query goes through shacl2flink's translation (lib/query_check.py there),
in this process and without a build. Where no shacl2flink is found nothing is
said -- never that a query can be deployed.
"""

import importlib
import os
import sys

_loaded = {}


def _is_checkout(where):
    return os.path.isfile(os.path.join(where, 'lib', 'query_check.py'))


def shacl2flink_dir(package_path=''):
    """The checkout: named by SEMFORGE_SHACL2FLINK, else beside the package or
    beside SemForge itself. '' when there is none -- a named directory
    without the check is none either, never a reason to import another `lib`."""
    named = os.environ.get('SEMFORGE_SHACL2FLINK')
    if named is not None:
        return named if _is_checkout(named) else ''
    for start in (package_path, os.path.dirname(os.path.abspath(__file__))):
        here = os.path.abspath(start) if start else ''
        while here and here != os.path.dirname(here):
            candidate = os.path.join(here, 'shacl2flink')
            if _is_checkout(candidate):
                return candidate
            here = os.path.dirname(here)
    return ''


def compiler(package_path=''):
    """shacl2flink's query_check module, or None."""
    where = shacl2flink_dir(package_path)
    if not where:
        return None
    if where not in _loaded:
        # Its modules are called `lib`: kept out of everybody else's way.
        before = {name: module for name, module in sys.modules.items()
                  if name == 'lib' or name.startswith('lib.')}
        for name in before:
            del sys.modules[name]
        sys.path.insert(0, where)
        try:
            _loaded[where] = importlib.import_module('lib.query_check')
        except Exception:                              # noqa: BLE001 -- a dependency of it is missing
            _loaded[where] = None
        finally:
            sys.path.remove(where)
            for name in [n for n in sys.modules if n == 'lib' or n.startswith('lib.')]:
                del sys.modules[name]
            sys.modules.update(before)
    return _loaded[where]


def problems(package):
    """[Problem] of the package's SPARQL constraints and rules that cannot be
    deployed (shape, kind, reason, pattern, query, file, line), one per
    expression and reason even when several target classes refuse it alike.
    A check that fails says nothing, as a checkout that cannot be loaded."""
    check = compiler(package.path)
    if check is None:
        return []
    try:
        found = check.check(package.shapes, package.files('shapes'))
    except Exception:                                  # noqa: BLE001 -- a check that fails is no check
        return []
    seen, out = set(), []
    for problem in found:
        key = (problem.shape, problem.kind, problem.query, problem.reason)
        if key not in seen:
            seen.add(key)
            out.append(problem)
    return out


def describe(problem):
    """`the SPARQL constraint 'its message'`, or `the SPARQL rule` when it has none."""
    what = 'rule' if problem.kind == 'sh:construct' else 'constraint'
    return f'the SPARQL {what} {problem.message!r}' if problem.message else f'the SPARQL {what}'


def query_problem(package, shape, kind, query):
    """Why this query of the shape cannot be deployed, or None. A build
    compiles it once per target class of the shape, so each is asked."""
    from rdflib import URIRef
    from rdflib.namespace import SH

    check = compiler(package.path)
    if check is None:
        return None
    for target in sorted(package.shapes.objects(URIRef(shape), SH.targetClass), key=str):
        found = check.check(package.shapes, draft={
            'shape': shape, 'target': target, 'query': query,
            'kind': 'sh:construct' if kind == 'rule' else 'sh:select'})
        if found:
            return found[0]
    return None
