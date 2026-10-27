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

"""Incremental revalidation: after an edit, only what the edit can change.

editor/verdicts.py validates once per package version; this decides how much
of a new version needs validating, given the last one. It keeps the last run's
package, its verdicts and a digest of every file, and compares:

* **a shape** changed (or appeared, or went): that shape and every shape that
  refers to it -- through sh:node, a named property shape, sh:prefixes, any
  IRI in its tree -- are evaluated again, on the main model and every case;
  their old results are replaced, everyone else's kept. A shape with sh:rule
  in the change means everything: rules rewrite the data every shape reads;
* **a case or an include** changed: the cases built from it are validated
  again, whole;
* **the main model** changed: it is validated again, whole;
* **the knowledge** changed: nothing, if no predicate in the changed files is
  one a constraint can read (validate/readset.py) -- an OPC UA browse name --
  else everything;
* anything else -- the context, semforge.yaml, the NGSI-LD vocabulary, a
  file nobody can classify -- means everything. Text files (.md, .txt) mean
  nothing.

Never a guess on the cheap side: whatever cannot be shown to be unaffected is
evaluated again. SEMFORGE_VERIFY_INCREMENTAL=1 also validates everything and
reports any difference on stderr -- and uses the full result -- for whoever
wants to see it hold on their own package.
"""

import gc
import hashlib
import os
import sys
import time
from dataclasses import dataclass, field

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import SH

from .verdicts import Verdicts, compute

IGNORED_SUFFIXES = ('.md', '.txt', '.gitignore')


@dataclass
class Snapshot:
    """What one run saw: the package, its verdicts, every file's digest."""
    stamp: str
    package: object
    verdicts: Verdicts
    digests: dict = field(default_factory=dict)      # abs path -> sha256
    knowledge: dict = field(default_factory=dict)    # abs path -> bytes
    prints: dict = None                              # _prints(package.shapes), once known


@dataclass
class Plan:
    full: bool = False
    reason: str = ''
    shapes: set = field(default_factory=set)         # shape IRIs to evaluate again
    model: bool = False                              # the main model, whole
    cases: set = field(default_factory=set)          # case paths, whole
    new_prints: dict = None                          # the new shapes' _prints, if computed


# --- the package's files -------------------------------------------------------

def _files(root):
    from .cache import SKIP_DIRS

    found = []
    for directory, dirs, names in os.walk(root, followlinks=True):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.'))
        for name in sorted(names):
            found.append(os.path.abspath(os.path.join(directory, name)))
    return found


def _digests(root, knowledge_paths):
    digests, kept = {}, {}
    for path in _files(root):
        try:
            with open(path, 'rb') as handle:
                data = handle.read()
        except OSError:
            continue
        digests[path] = hashlib.sha256(data).hexdigest()
        if path in knowledge_paths:
            kept[path] = data
    return digests, kept


# --- shapes: what changed, and what refers to it --------------------------------

def _prints(graph):
    """{IRI: digest of what it says} for every named subject, blank node trees
    written out in place (sorted, so their labels do not matter)."""
    def text(node, path):
        if not isinstance(node, BNode):
            return node.n3()
        if node in path:
            return '<cycle>'
        return '[' + ' ; '.join(sorted(f'{p.n3()} {text(o, path | {node})}'
                                       for p, o in graph.predicate_objects(node))) + ']'

    out = {}
    for subject in set(graph.subjects()):
        if isinstance(subject, URIRef):
            body = '\n'.join(sorted(f'{p.n3()} {text(o, frozenset())}'
                                    for p, o in graph.predicate_objects(subject)))
            out[str(subject)] = hashlib.sha256(body.encode('utf-8')).hexdigest()
    return out


def _mentions(graph):
    """{IRI: the named subjects whose tree mentions it}."""
    referrers = {}
    for subject in set(graph.subjects()):
        if not isinstance(subject, URIRef):
            continue
        seen, todo = set(), [subject]
        while todo:
            node = todo.pop()
            for obj in graph.objects(node, None):
                if isinstance(obj, BNode) and obj not in seen:
                    seen.add(obj)
                    todo.append(obj)
                elif isinstance(obj, URIRef) and obj != subject:
                    referrers.setdefault(str(obj), set()).add(str(subject))
    return referrers


def changed_shapes(old, new, before=None, after=None):
    """The shape IRIs to evaluate again, or None when that is all of them.

    `before`/`after` are the graphs' _prints when already known."""
    before = before if before is not None else _prints(old)
    after = after if after is not None else _prints(new)
    changed = {iri for iri in set(before) | set(after) if before.get(iri) != after.get(iri)}
    if not changed:
        return set()
    referrers = {}
    for graph in (old, new):
        for iri, who in _mentions(graph).items():
            referrers.setdefault(iri, set()).update(who)
    affected, todo = set(changed), list(changed)
    while todo:
        for who in referrers.get(todo.pop(), ()):
            if who not in affected:
                affected.add(who)
                todo.append(who)
    for graph in (old, new):
        if any(str(s) in affected for s in graph.subjects(SH.rule, None)):
            return None
    return affected


# --- knowledge: does the change touch anything a constraint reads ---------------

def _lines(graph):
    """Every statement of a graph as a line: a named subject's predicate and
    object, a blank node object written out in place; a blank node nothing
    points at as one line of its own. With the predicates each line holds.

    (Counter of lines, {line: predicates}, every triple covered). A triple
    added or removed anywhere changes the line it lies in -- unless blank nodes
    only point at each other, which `covered` reports.
    """
    from collections import Counter

    covered = set()

    def render(node, path, predicates):
        parts = []
        for p, o in graph.predicate_objects(node):
            covered.add((node, p, o))
            predicates.add(p)
            parts.append(f'{p.n3()} {inner(o, path, predicates)}')
        return ' ; '.join(sorted(parts))

    def inner(o, path, predicates):
        if not isinstance(o, BNode):
            return o.n3()
        if o in path:
            return '<cycle>'
        return '[' + render(o, path | {o}, predicates) + ']'

    lines, holds = Counter(), {}
    pointed_at = {o for o in graph.objects() if isinstance(o, BNode)}
    for subject in set(graph.subjects()):
        if isinstance(subject, URIRef):
            for p, o in graph.predicate_objects(subject):
                covered.add((subject, p, o))
                predicates = {p}
                line = f'{subject.n3()} {p.n3()} {inner(o, frozenset(), predicates)}'
                lines[line] += 1
                holds[line] = predicates
        elif subject not in pointed_at:
            predicates = set()
            line = '[' + render(subject, frozenset([subject]), predicates) + ']'
            lines[line] += 1
            holds[line] = predicates
    return lines, holds, len(covered) == len(graph)


def changed_predicates(old, new):
    """The predicates of every triple added or removed between two graphs."""
    old_lines, old_holds, old_ok = _lines(old)
    new_lines, new_holds, new_ok = _lines(new)
    if not (old_ok and new_ok):
        return set(old.predicates()) | set(new.predicates())
    touched = set()
    for line in set(old_lines) | set(new_lines):
        if old_lines.get(line, 0) != new_lines.get(line, 0):
            touched |= old_holds.get(line, set()) | new_holds.get(line, set())
    return touched


def _statements(text):
    from collections import Counter

    from ..rdfio.turtle_index import _prefixes, _statement_spans

    return Counter(text[a:b] for a, b in _statement_spans(text)), _prefixes(text)


def knowledge_matters(old, new_package, changed_paths):
    """Can any triple added or removed in these knowledge files be read by a
    constraint (validate/readset.py)?

    Compared statement by statement, as text: only the statements that differ
    are parsed -- with the file's prefixes and base -- to see their predicates.
    Parsing both versions of an 8.6 MB ontology to change one browse name
    cost more than validating everything. Changed prefixes, or a changed
    statement that does not parse on its own, count as mattering.
    """
    from pathlib import Path

    from ..rdfio.turtle_index import DIRECTIVE
    from ..validate.readset import read_set

    reads = [read_set(old.package.shapes), read_set(new_package.shapes)]
    if any(r is None for r in reads):
        return True
    readable = reads[0] | reads[1]
    for path in changed_paths:
        before = old.knowledge.get(path, b'').decode('utf-8', errors='replace')
        after = ''
        if os.path.exists(path):
            with open(path, encoding='utf-8', errors='replace') as handle:
                after = handle.read()
        old_statements, old_names = _statements(before)
        new_statements, new_names = _statements(after)
        if old_names != new_names:
            return True
        prefixes, base = new_names
        header = ''.join(f'@prefix {p}: <{ns}> .\n' for p, ns in prefixes.items())
        if base:
            header += f'@base <{base}> .\n'
        gone, came = [], []
        for statement in set(old_statements) | set(new_statements):
            if DIRECTIVE.match(statement):
                continue
            surplus = old_statements.get(statement, 0) - new_statements.get(statement, 0)
            (gone if surplus > 0 else came if surplus < 0 else []).append(statement)
        if not gone and not came:
            continue
        # The statements that differ, old and new, as two small graphs: what a
        # line of them says is what changed (changed_predicates) -- a browse
        # name edited beside `a uardf:Variable` touches the name, not the type.
        try:
            graphs = [Graph().parse(data=header + '\n'.join(part), format='turtle',
                                    publicID=Path(path).as_uri()) for part in (gone, came)]
        except Exception:                          # noqa: BLE001
            return True
        if changed_predicates(*graphs) & readable:
            return True
    return False


# --- the plan ------------------------------------------------------------------

def plan(old, package, digests):
    from ..expect.store import examples_root, load_expectations

    changed = {p for p in set(old.digests) | set(digests)
               if old.digests.get(p) != digests.get(p)}
    result = Plan()
    if not changed:
        return result

    def role_files(pkg, role):
        return {os.path.abspath(p) for p in pkg.files(role)}

    shapes = role_files(old.package, 'shapes') | role_files(package, 'shapes')
    knowledge = role_files(old.package, 'knowledge') | role_files(package, 'knowledge')
    model = role_files(old.package, 'model') | role_files(package, 'model')
    examples = os.path.abspath(examples_root(package.path)) + os.sep

    touched_knowledge, touched_examples = set(), set()
    for path in changed:
        if path in shapes:
            continue
        if path in knowledge:
            touched_knowledge.add(path)
        elif path in model:
            result.model = True
        elif path.startswith(examples):
            touched_examples.add(path)
        elif path.endswith(IGNORED_SUFFIXES):
            continue
        else:
            return Plan(full=True, reason=f'{os.path.relpath(path, package.path)} changed')

    if changed & shapes:
        if old.prints is None:
            old.prints = _prints(old.package.shapes)
        result.new_prints = _prints(package.shapes)
        affected = changed_shapes(old.package.shapes, package.shapes,
                                  old.prints, result.new_prints)
        if affected is None:
            return Plan(full=True, reason='a rule changed')
        result.shapes = affected

    if touched_knowledge and knowledge_matters(old, package, touched_knowledge):
        return Plan(full=True, reason='knowledge a constraint reads changed')

    if touched_examples:
        root = examples_root(package.path)
        before = {e.path: e for e in load_expectations(old.package.path).examples} \
            if old.package.path == package.path else {}
        for example in load_expectations(package.path).examples:
            inputs = {os.path.abspath(os.path.join(root, r)) for r in
                      list(example.include) + [example.path]}
            inputs |= {os.path.abspath(os.path.join(package.path, r)) for r in example.include}
            previous = before.get(example.path)
            if inputs & touched_examples or previous is None or \
                    list(previous.include) != list(example.include):
                result.cases.add(example.path)
    return result


# --- merging a partial run into the last one ------------------------------------

def merge(old, new, shapes):
    """The old report with the given shapes' results replaced by the new run's."""
    from ..validate.results import Report

    results = [r for r in old.results if r.shape not in shapes] + list(new.results)
    diagnostics = []
    for diagnostic in [d for d in old.diagnostics if d.subject not in shapes] + \
            list(new.diagnostics):
        if diagnostic not in diagnostics:
            diagnostics.append(diagnostic)
    return Report(results=results, view_stats=new.view_stats or old.view_stats,
                  diagnostics=diagnostics,
                  complete=not any(d.code == 'SF-ENUM-001' for d in diagnostics),
                  rule_iterations=new.rule_iterations)


def apply(old, package, stamp, the_plan):
    """New verdicts from the last ones and a plan that is not `full`."""
    from ..expect.store import compose, load_expectations
    from ..errors import PackageError
    from ..validate.orchestrator import validate_graphs

    from ..validate.readset import run_knowledge

    started = time.time()
    shapes = the_plan.shapes
    knowledge = run_knowledge(package.shapes, package.knowledge)   # once per run

    def validate(graph, only=None):
        return validate_graphs(graph, package.shapes, knowledge, strict=False, cut=False,
                               only=only)

    def partial(previous, graph):
        if not shapes:
            return previous
        return merge(previous, validate(graph, shapes), shapes)

    model = validate(package.model) if the_plan.model \
        else partial(old.verdicts.model, package.model)
    cases = {}
    for example in load_expectations(package.path).examples:
        previous = old.verdicts.cases.get(example.path)
        if previous is not None and example.path not in the_plan.cases and not shapes:
            cases[example.path] = previous
            continue
        try:
            graph = compose(package, example)
        except PackageError:
            continue
        if previous is None or example.path in the_plan.cases:
            cases[example.path] = validate(graph)
        else:
            cases[example.path] = partial(previous, graph)
    return Verdicts(stamp=stamp, model=model, cases=cases,
                    seconds=round(time.time() - started, 2))


def _keys(verdicts):
    def of(report):
        return sorted((r.resource, r.attribute, r.component, r.shape, r.status.value)
                      for r in report.results)
    return of(verdicts.model), {p: of(r) for p, r in verdicts.cases.items()}


def findings(root, package, verdicts):
    """The editor's diagnostics for a validated version, as JSON-ready dicts."""
    from dataclasses import asdict

    from .analysis import analyse

    try:
        found, _ = analyse(root, package=package, verdicts=verdicts)
    except Exception:                              # noqa: BLE001 -- a broken package still validates
        return {}
    return {path: [asdict(f) for f in items] for path, items in found.items()}


class Session:
    """run(root, stamp): verdicts for a package version, incremental when it can.

    Keeps one Snapshot per package: the validation worker holds it between
    runs, so an edit is compared with the version validated last.
    """

    def __init__(self, load):
        self._load = load
        self._last = {}

    def run(self, root, stamp):
        old = self._last.get(root)
        digests, _ = _digests(root, set())
        reuse = self._reusable(old, digests)
        fresh = set(reuse or ()) != {'knowledge', 'shapes'}
        if fresh:
            gc.unfreeze()        # what was kept may be replaced now: collectable again
        package = self._load(root, reuse=reuse)
        knowledge_paths = {os.path.abspath(p) for p in package.files('knowledge')}
        kept = {}
        for path in knowledge_paths:
            try:
                with open(path, 'rb') as handle:
                    kept[path] = handle.read()
            except OSError:
                pass
        verdicts = None
        if old is not None:
            the_plan = plan(old, package, digests)
            prints = the_plan.new_prints if the_plan.new_prints is not None \
                else (old.prints if package.shapes is old.package.shapes else None)
            if not the_plan.full:
                verdicts = apply(old, package, stamp, the_plan)
                if os.environ.get('SEMFORGE_VERIFY_INCREMENTAL'):
                    full = compute(package, stamp)
                    if _keys(full) != _keys(verdicts):
                        print(f'semforge: incremental verdicts differ from a full run on '
                              f'{root}; using the full run', file=sys.stderr)
                        verdicts = full
        else:
            prints = None
        if verdicts is None:
            verdicts = compute(package, stamp)
        verdicts.findings = findings(root, package, verdicts)
        self._last[root] = Snapshot(stamp=stamp, package=package, verdicts=verdicts,
                                    digests=digests, knowledge=kept, prints=prints)
        if fresh:
            # The knowledge and shapes graphs stay for every edit that follows:
            # two million objects on the OPC UA pumps, which each full pass of
            # Python's cycle collector walked again -- a second, at random,
            # inside an edit that otherwise validates in a quarter of one.
            # Frozen, the collector leaves them alone (paid here, once).
            old = None
            gc.collect()
            gc.freeze()
        return verdicts

    def prime(self, root, verdicts):
        """Take verdicts that came from the disk cache as the last run.

        A restart on an unchanged package validates nothing: the verdicts are
        read from disk. The worker then held no run, so the first edit loaded
        the package and validated it whole -- 5-6 s on the OPC UA pumps, where
        every later edit took a fraction of that. Loaded here, while nobody
        waits, the first edit is compared with this version like any other.
        """
        old = self._last.get(root)
        if old is not None and old.stamp == verdicts.stamp:
            return False
        digests, _ = _digests(root, set())
        # Edited since the verdicts were read (the prime waits in the worker's
        # queue): these files are not what they judged, and kept as their
        # version the next run would find nothing changed and show them as
        # current. Read after the digests, so any edit before is seen here.
        from .cache import fingerprint
        if fingerprint(root) != verdicts.stamp:
            return False
        package = self._load(root, reuse=None)
        kept = {}
        for path in {os.path.abspath(p) for p in package.files('knowledge')}:
            try:
                with open(path, 'rb') as handle:
                    kept[path] = handle.read()
            except OSError:
                pass
        self._last[root] = Snapshot(stamp=verdicts.stamp, package=package, verdicts=verdicts,
                                    digests=digests, knowledge=kept)
        # The main model and the editor's findings once, results dropped: what
        # each builds on its first run (the shapes compiled, the knowledge cut,
        # the Turtle files' index -- 8 s of the 13 on the pumps) is then built,
        # and the first edit costs what every later one does.
        from ..validate.orchestrator import validate_graphs
        from ..validate.readset import run_knowledge
        validate_graphs(package.model, package.shapes,
                        run_knowledge(package.shapes, package.knowledge), strict=False, cut=False)
        findings(root, package, verdicts)
        gc.unfreeze()
        gc.collect()
        gc.freeze()
        return True

    @staticmethod
    def _reusable(old, digests):
        """{role: (documents, graph)} the last run read that are unchanged.

        Only when no Turtle file came or went anywhere: a new file in a role
        directory would join the role, and that is for the loader to see.
        """
        if old is None:
            return None
        changed = {p for p in set(old.digests) | set(digests)
                   if old.digests.get(p) != digests.get(p)}
        if any((p not in old.digests or p not in digests) and p.endswith('.ttl')
               for p in changed):
            return None
        reuse = {}
        for role in ('knowledge', 'shapes'):
            documents = old.package.files(role)
            if not changed & {os.path.abspath(d) for d in documents}:
                reuse[role] = (documents, getattr(old.package, role))
        return reuse
