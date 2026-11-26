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

"""The example instances, as a tree, with what validation says about them.

The constraint tree shows the shapes. This shows the data they judge, which is
the other half of the loop the manifest describes: pick an entity, walk its
nested attributes, see which constraint fired on which one, change a value and
watch the verdict move.

A viewer alone would be a JSON outline VS Code already gives you. What makes it
worth its own tree is the verdicts hanging off the nodes -- an entity says how
many violations it carries, and the attribute that caused one says so on the
line you are looking at.

Editing goes through a JSON round-trip rather than a text-span index, unlike
the shapes. That is not laziness: `json.dumps(..., indent=2)` reproduces this
model byte for byte, so a value change really does produce a one-line diff.
JSON has no comments to lose either, which is what forced the span approach on
Turtle.
"""

import json
import math
import os
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from ..errors import PackageError

RESERVED = {'@context', 'id', '@id', 'type', '@type'}
DEFAULT_DATASET = '@none'
VALUE_KEYS = ('value', 'object', 'valueList', 'json')
META_KEYS = ('observedAt', 'unitCode', 'datasetId')


def _said(result):
    """A violation as the pages word it -- "hasWidth is above its maximum
    (WorkpieceShape)" -- not pyshacl's "Less than 1 values on [ <…> ]->…",
    which a tree row cannot show."""
    from .casepage import _explain

    explained = _explain(result)
    return f'{explained["text"]} ({explained["shape"]})'


@dataclass
class ExampleNode:
    # kind: example | entity | attribute | dataset | instance | meta
    kind: str
    label: str
    detail: str = ''
    entity: str = ''           # the entity IRI this sits under
    path: list = field(default_factory=list)   # attribute names, then index
    value: str = ''
    editable: bool = False
    severity: str = ''         # violation | warning | '' -- from the report
    messages: list = field(default_factory=list)
    children: list = field(default_factory=list)
    file: str = ''             # the JSON file this node was read from
    defined_at: str = ''       # file:line, so selecting the row moves the editor
    entity_type: str = ''      # the entity's NGSI-LD type, for the shape jump
    shared_by: list = field(default_factory=list)  # cases including this file
    dataset_id: str = ''       # the datasetId this row stands for
    observations: int = 0      # how many, when it is a series
    attribute_path: list = field(default_factory=list)  # where to append one
    datasets: list = field(default_factory=list)  # every datasetId of the attribute
    position: int = -1         # an entity's place in its file
    digest: str = ''           # of the file's content an entity was read from

    @property
    def is_series(self):
        return self.observations > 1


def _entities(path):
    with open(path, encoding='utf-8') as handle:
        return _documents(handle.read())


def _documents(text):
    document = json.loads(text, object_pairs_hook=OrderedDict)
    return document if isinstance(document, list) else [document]


def _render(value):
    if isinstance(value, dict) and '@id' in value:
        return str(value['@id'])
    if isinstance(value, dict) and '@value' in value:
        # A declared value -- a double, a timestamp (#961) -- reads as its value.
        return _render(value['@value'])
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)[:60]
    return json.dumps(value, ensure_ascii=False) if isinstance(value, str) \
        else str(value)


def _instance_node(instance, entity, path, findings):
    """One attribute instance: its value, its metadata, its sub-attributes."""
    node = ExampleNode(kind='instance', label='', entity=entity,
                       path=list(path))
    if not isinstance(instance, dict):
        node.label = _render(instance)
        node.value = _render(instance)
        return node

    kind = instance.get('type', '')
    for key in VALUE_KEYS:
        if key in instance:
            node.label = _render(instance[key])
            node.value = _render(instance[key])
            node.detail = kind
            # Every payload, not just the scalar ones. A JsonProperty's `json`
            # and a ListProperty's `valueList` are values as much as `value` is,
            # and the input box parses JSON, so `[1, 2, 3]` and `{"a": 1}` go in
            # as a list and an object. Excluding them left rows that showed a
            # value and refused to change it.
            node.editable = True
            node.path = list(path) + [key]
            break
    else:
        node.label = kind or '(no value)'
        node.detail = 'attribute with no value'

    for key in META_KEYS:
        if key in instance:
            node.children.append(ExampleNode(
                kind='meta', label=key, detail=_render(instance[key]),
                entity=entity, path=list(path) + [key],
                value=_render(instance[key]), editable=True))

    for key, value in instance.items():
        if key in RESERVED or key in VALUE_KEYS or key in META_KEYS:
            continue
        node.children.append(
            _attribute_node(key, value, entity, list(path) + [key], findings))
    return node


def _dataset_of(instance):
    if isinstance(instance, dict):
        return str(instance.get('datasetId', DEFAULT_DATASET))
    return DEFAULT_DATASET


def _group_by_dataset(instances):
    """{datasetId: [(index, instance)]}, in first-seen order.

    An NGSI-LD attribute is identified by (entity, name, datasetId). Several
    instances sharing a datasetId are ONE attribute observed repeatedly;
    different datasetIds are DIFFERENT attributes that happen to share a name.
    A flat list conflates the two, and they behave differently -- the dedup
    resolves within a datasetId and never across.
    """
    groups = OrderedDict()
    for index, instance in enumerate(instances):
        groups.setdefault(_dataset_of(instance), []).append((index, instance))
    return groups


def _current_index(members):
    """Which member validation reads: the latest -- an unstamped one counting
    as now, as on the platform -- and of those tied, the last in the file.

    Returns the index into the WHOLE attribute, not a position within the
    group -- an edit path has to address the JSON array, and the two coincide
    only when there is a single datasetId.
    """
    from ..ngsild.timestamps import key

    return max((key(instance), index) for index, instance in members)[1]


def _member_at(members, index):
    return next(instance for position, instance in members if position == index)


def _series_children(members, current, entity, path, findings):
    """One row per observation, newest marked current.

    Editing any other one changes the file and nothing else, which without the
    marker reads as the editor being broken.
    """
    out = []
    for index, instance in members:
        child = _instance_node(instance, entity, list(path) + [index], findings)
        stamp = instance.get('observedAt') if isinstance(instance, dict) else None
        marks = [child.detail] if child.detail else []
        if stamp:
            marks.append(str(stamp))
        marks.append('current' if index == current else 'superseded')
        child.detail = ' · '.join(marks)
        child.children = [c for c in child.children
                          if not (c.kind == 'meta' and c.label == 'observedAt')]
        out.append(child)
    return out


def dataset_label(dataset):
    """How a datasetId reads: the default instance has none, so it says so."""
    return 'default' if dataset == DEFAULT_DATASET else dataset


def _dataset_node(dataset, members, entity, path, findings, datasets=()):
    current = _current_index(members)
    head = _instance_node(_member_at(members, current), entity,
                          list(path) + [current], findings)
    node = ExampleNode(
        kind='dataset', label=head.label or dataset_label(dataset), entity=entity,
        dataset_id=dataset, observations=len(members), datasets=list(datasets),
        attribute_path=list(path), path=head.path, value=head.value,
        editable=head.editable,
        detail=' · '.join(p for p in (
            dataset_label(dataset), head.detail,
            f'{len(members)} observations' if len(members) > 1 else '') if p))
    node.children = (_series_children(members, current, entity, path, findings)
                     if len(members) > 1 else list(head.children))
    return node


def _attribute_node(name, value, entity, path, findings):
    instances = value if isinstance(value, list) else [value]
    short = name.rsplit('/', 1)[-1].rsplit('#', 1)[-1].split(':')[-1]

    node = ExampleNode(kind='attribute', label=short, entity=entity,
                       path=list(path), attribute_path=list(path))
    hit = findings.get((entity, short))
    if hit:
        node.severity = hit[0]
        node.messages = hit[1]
        node.detail = f'{len(hit[1])} violation(s)'

    groups = _group_by_dataset(instances)

    if len(groups) > 1:
        node.detail = ' · '.join(
            p for p in (node.detail, f'{len(groups)} instances') if p)
        node.datasets = list(groups)
        for dataset, members in groups.items():
            node.children.append(
                _dataset_node(dataset, members, entity, path, findings, groups))
        return node

    dataset, members = next(iter(groups.items()))
    current = _current_index(members)
    node.dataset_id = dataset
    node.datasets = [dataset]
    node.observations = len(members)
    if dataset != DEFAULT_DATASET:
        node.detail = ' · '.join(p for p in (node.detail, dataset) if p)

    head = _instance_node(_member_at(members, current), entity,
                          list(path) + [current], findings)

    if len(members) > 1:
        # One dataset observed repeatedly: the row shows the value validation
        # reads, and expanding gives the series.
        node.value, node.editable, node.path = head.value, head.editable, head.path
        node.detail = ' · '.join(p for p in (
            head.label, head.detail, f'{len(members)} observations',
            node.detail) if p)
        node.children = _series_children(members, current, entity, path,
                                         findings)
        return node

    if not head.children:
        node.value, node.editable, node.path = head.value, head.editable, head.path
        node.detail = ' · '.join(p for p in (head.label, head.detail,
                                             node.detail) if p)
    else:
        node.children = [head]
        node.detail = node.detail or head.label
    return node


def build_suite(package, expectations=None, verdicts=None):
    """Every declared example as its own root, with what it is for and how it did.

    The package's own model-instance is included as a root too. It is not a
    declared example -- it is the model as shipped -- and leaving it out of the
    tree would hide the thing most of the toolchain actually compiles.

    Entities that arrive through `include` are shown read-only under the file
    that declares them. Editing a subobject in place would change every case
    that includes it, which is a decision to take deliberately in that file
    rather than a side effect of editing one example.

    `verdicts` as for build_type_page (cooked/typepage.py): with PENDING, or
    for a case they do not cover yet, the case says "evaluating…" instead of
    passing or failing; without it, every case is validated here.
    """
    from ..expect.store import compose, load_expectations
    from ..validate.orchestrator import validate_graphs
    from ..validate.results import Report
    from .typepage import PENDING

    expectations = expectations or load_expectations(package.path)
    notes = _identity_notes(package)
    shared = {}
    for example in expectations.examples:
        for included in example.include:
            shared.setdefault(included, []).append(example.path)
    by_suite = OrderedDict()
    loose = []

    for example in expectations.examples:
        try:
            graph = compose(package, example)
            if verdicts is PENDING:
                report = None
            elif verdicts is not None:
                report = verdicts.cases.get(example.path)
            else:
                report = validate_graphs(graph, package.shapes, package.knowledge,
                                         strict=False)
        except Exception as exc:                   # noqa: BLE001
            node = ExampleNode(kind='example', label=example.path,
                               detail=f'error: {exc}', severity='violation')
        else:
            node = _example_root(package, example, report or Report(), notes, shared)
            if report is None:
                node.severity = ''
                node.detail = 'evaluating…'

        target = by_suite.setdefault(example.suite, []) if example.suite \
            else loose
        target.append(node)

    roots = []
    for suite, nodes in by_suite.items():
        failing = [n for n in nodes if n.severity]
        node = ExampleNode(
            kind='suite', label=suite,
            detail=' · '.join(p for p in (
                f'{len(nodes)} case(s)',
                f'{len(failing)} failing' if failing else 'all ok') if p),
            severity='violation' if failing else '')
        node.children = nodes
        roots.append(node)

    roots.extend(loose)

    # Two sections of the Entities & Test Cases view, because they answer different
    # questions and are judged by different rules. A case declares what it is for and passes or fails; the
    # main model declares nothing and cannot fail -- it is where you try a
    # violation to see what a constraint does.
    cases = ExampleNode(
        kind='group', label='Tests',
        detail=_suite_summary(roots) if roots
        else 'no cases yet — add one under examples/')
    cases.children = roots
    cases.severity = 'violation' if any(n.severity for n in roots) else ''

    documents = _model_roots(package, notes, verdicts)
    main = ExampleNode(
        kind='group', label='Main',
        detail=' · '.join(p for p in (
            f'{len(documents)} document(s)' if len(documents) > 1 else '',
            'the scratchpad — violations here are information, not failures')
            if p))
    main.children = documents
    # Main first: it is the model you deploy; the cases are evidence about
    # the shapes.
    return _name_instances(package, [main, cases])


def _name_instances(package, roots):
    """Each instance of a multi-instance attribute reads attribute[prefix:name]
    -- hasHeight[sensors:left] -- and the default instance plain hasHeight;
    the value moves into the detail. A single instance under a datasetId says
    it the same way. Done once over the finished tree: the builders below do
    not know the package's prefixes, and should not need to."""
    names = dataset_names(package)

    def detail_without(node, dataset):
        parts = [p for p in node.detail.split(' · ') if p and p not in (dataset, 'default')]
        return parts

    def walk(nodes):
        for node in nodes:
            if node.kind == 'attribute':
                datasets = [c for c in node.children if c.kind == 'dataset']
                for child in datasets:
                    value = child.label
                    child.label = instance_label(node.label, child.dataset_id, names)
                    rest = detail_without(child, dataset_label(child.dataset_id))
                    if value and value != dataset_label(child.dataset_id):
                        rest = [value] + rest
                    if child.dataset_id == DEFAULT_DATASET:
                        rest.append('default')
                    child.detail = ' · '.join(rest)
                if not datasets and node.dataset_id and node.dataset_id != DEFAULT_DATASET:
                    plain = node.label
                    node.label = instance_label(plain, node.dataset_id, names)
                    node.detail = ' · '.join(detail_without(node, node.dataset_id))
            walk(node.children)
    walk(roots)
    return roots


def _suite_summary(roots):
    cases = [n for _, n in flatten(roots) if n.kind == 'example']
    failing = [n for n in cases if n.severity]
    return ' · '.join(p for p in (
        f'{len(cases)} case(s)',
        f'{len(failing)} failing' if failing else 'all ok') if p)


def _expected_shape(example, report):
    """Did it do what it says? -- the label the tree hangs on the example."""
    violations = len(report.violations)
    if example.expect == 'invalid':
        return ('ok' if violations else 'FAILED: expected a violation',
                '' if violations else 'violation')
    if example.conformance == 'full' and violations:
        return (f'FAILED: {violations} violation(s), conformance is full',
                'violation')
    return ('ok', '')


def _example_root(package, example, report, notes=None, shared=None):
    status, severity = _expected_shape(example, report)
    detail = ' · '.join(p for p in (
        example.group, example.expect, status,
        f'{len(example.include)} include(s)' if example.include else '') if p)
    node = ExampleNode(kind='example', label=os.path.basename(example.path),
                       detail=detail, severity=severity,
                       messages=[example.description] if example.description
                       else [])

    own = os.path.join(package.examples_dir, example.path)
    # The case's own file: what identifies the case to its page, and where
    # selecting the row lands.
    node.file = os.path.abspath(own)
    node.defined_at = f'{node.file}:1'
    node.children.extend(_entity_nodes(own, report, notes=notes))

    for included in example.include:
        path = os.path.join(package.examples_dir, included)
        cases = list(shared.get(included, [])) if shared else []
        detail = 'included'
        if len(cases) > 1:
            detail += f' — shared by {len(cases)} cases'
        folder = ExampleNode(kind='include', label=os.path.basename(included),
                             detail=detail, shared_by=cases)
        # Editable, because it is an ordinary JSON-LD file and there is nothing
        # about being included that makes it unwritable. What matters is that an
        # edit reaches every case that includes it, so the rows carry the list
        # and the edit asks first.
        folder.children.extend(_entity_nodes(path, report, notes=notes,
                                             shared_by=cases))
        node.children.append(folder)
    return node


def _model_roots(package, notes=None, verdicts=None):
    """The model instance, as one root per document.

    It is the scratchpad, not a test: violations here are how somebody finds out
    what a constraint does, so it carries no expectation and cannot fail a run.
    A directory of documents gets a root each, named by its path relative to the
    package, because that is what tells two of them apart.
    """
    from ..validate import validate_package
    from ..validate.results import Report
    from .typepage import PENDING

    if verdicts is PENDING:
        report = Report()
    elif verdicts is not None:
        report = verdicts.model
    else:
        report = validate_package(package, strict=False)
    roots = []
    documents = package.files('model')
    for document in documents:
        label = os.path.relpath(document, package.path) if len(documents) > 1 \
            else os.path.basename(document)
        node = ExampleNode(kind='example', label=label,
                           detail='the model as shipped')
        node.children.extend(_entity_nodes(document, report, notes=notes))
        roots.append(node)
    return roots


def _stamp_file(node, path):
    node.file = path
    for child in node.children:
        _stamp_file(child, path)


def _stamp_lines(node, path, index, prefix):
    """Give every node a file:line, so selecting it can move the editor.

    The shapes tree could always do this because Turtle is indexed by byte
    span. JSON had no equivalent, so selecting an entity or an attribute moved
    nothing at all.
    """
    # An attribute row means the attribute, even when it was folded onto its
    # current instance's value -- that is where you would edit the whole thing.
    address = node.attribute_path if node.kind == 'attribute' and \
        node.attribute_path else node.path
    full = tuple(prefix) + tuple(address)
    line = index.get(full)
    if line is None and node.kind == 'entity':
        line = index.get(tuple(prefix) + ('id',)) or index.get(tuple(prefix))
    if line is None:
        # Fall back to the nearest addressable ancestor rather than nothing: a
        # row that cannot be pointed at is worse than one pointing at its
        # parent.
        for depth in range(len(full) - 1, len(prefix) - 1, -1):
            line = index.get(full[:depth])
            if line is not None:
                break
    if line is not None:
        node.defined_at = f'{path}:{line}'
    for child in node.children:
        _stamp_lines(child, path, index, prefix)


def _identity_notes(package):
    """{entity id: (severity, [messages])} -- ids that name more than one thing.

    Only where the path cannot tell them apart: inside one document, or inside
    one composed case. The same id in two example files is not flagged, because
    the file is part of the address -- every row that names an entity shows it.
    """
    from ..expect.identity import duplicate_ids

    notes = {}
    try:
        found = duplicate_ids(package)
    except Exception:                              # noqa: BLE001
        return notes
    for duplicate in found:
        severity, messages = notes.setdefault(
            duplicate.entity, [duplicate.severity, []])
        messages.append(duplicate.message)
        if duplicate.severity == 'error':
            notes[duplicate.entity][0] = 'error'
    return notes


def _note_identity(node, notes):
    note = notes.get(node.entity)
    if not note:
        return
    severity, messages = note
    node.messages = list(node.messages) + list(messages)
    # A violation outranks it: that one says the entity is wrong, this one says
    # we cannot be sure which entity it is.
    if node.severity != 'violation':
        node.severity = 'violation' if severity == 'error' else 'warning'

    node.detail = ' · '.join(p for p in (node.detail, 'duplicate id') if p)


def _entity_nodes(path, report=None, editable=True, notes=None,
                  shared_by=()):
    from .jsonloc import locate
    from .removeentity import digest_of

    with open(path, encoding='utf-8') as handle:
        raw = handle.read()
    try:
        index = locate(raw)
    except Exception:                              # noqa: BLE001
        index = {}

    digest = digest_of(raw)
    findings = {}
    counts = {}
    for result in (report.violations if report is not None else []):
        findings.setdefault((result.resource, result.attribute),
                            ['violation', []])[1].append(
            _said(result))
        counts[result.resource] = counts.get(result.resource, 0) + 1

    out = []
    for position, entity in enumerate(_documents(raw)):
        if not isinstance(entity, dict):
            continue
        identifier = str(entity.get('id') or entity.get('@id') or '(no id)')
        node = ExampleNode(
            kind='entity', label=identifier, entity=identifier,
            detail=str(entity.get('type') or entity.get('@type') or ''),
            position=position, digest=digest)
        if counts.get(identifier):
            node.severity = 'violation'
            node.detail += f' · {counts[identifier]} violation(s)'
            node.messages = [m for (resource, _), (_, msgs) in findings.items()
                             if resource == identifier for m in msgs]
        kind_name = str(entity.get('type') or entity.get('@type') or '')
        if kind_name:
            node.children.append(_type_node(identifier, kind_name))
        for key, value in entity.items():
            if key in RESERVED:
                continue
            child = _attribute_node(key, value, identifier, [key], findings)
            if not editable:
                _read_only(child)
            node.children.append(child)
        if shared_by:
            _stamp_shared(node, list(shared_by))
        _stamp_type(node, str(entity.get('type') or entity.get('@type') or ''))
        _note_identity(node, notes or {})
        _stamp_file(node, path)
        _stamp_lines(node, path, index, [position])
        out.append(node)
    return out


def _type_node(entity, entity_type):
    """The entity's type, as a row of its own.

    It is already the entity row's description, but a description is greyed out
    and truncated in a narrow panel -- and the type is the most load-bearing
    field an NGSI-LD entity has: it decides which shapes judge it at all. So it
    gets a row, read-only, because changing a type is not an edit to one value
    (every shape that targeted the old type stops applying).
    """
    return ExampleNode(kind='type', label='type', detail=entity_type,
                       entity=entity, entity_type=entity_type,
                       path=['type'], value=entity_type)


def _stamp_type(node, entity_type):
    """Carry the entity type down to every row beneath it.

    An attribute row needs it to find the shape that judges it, and deriving it
    from the entity id later would mean re-reading the file the row came from.
    """
    node.entity_type = entity_type
    for child in node.children:
        _stamp_type(child, entity_type)


def _stamp_shared(node, cases):
    """Carry "this file is included by these cases" down to every row.

    The rows are editable -- it is an ordinary JSON-LD file -- but an edit lands
    in every case that includes it, and a row has to be able to say so before
    the edit rather than after.
    """
    node.shared_by = cases
    for child in node.children:
        _stamp_shared(child, cases)


def _read_only(node):
    node.editable = False
    for child in node.children:
        _read_only(child)


def build_examples(package, report=None):
    """Entities -> attributes -> instances, annotated with the verdicts."""
    findings = {}
    if report is not None:
        for result in report.violations:
            key = (result.resource, result.attribute)
            entry = findings.setdefault(key, ['violation', []])
            entry[1].append(_said(result))

    by_entity = {}
    for result in (report.violations if report is not None else []):
        by_entity.setdefault(result.resource, 0)
        by_entity[result.resource] += 1

    documents = package.files('model')
    entities = [e for document in documents for e in _entities(document)]
    root = ExampleNode(
        kind='example',
        label=package.sources['model'].rsplit('/', 1)[-1]
        + (f' + {len(documents) - 1} more' if len(documents) > 1 else ''),
        detail=f'{len(entities)} entities')

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        identifier = str(entity.get('id') or entity.get('@id') or '(no id)')
        node = ExampleNode(
            kind='entity', label=identifier, entity=identifier,
            detail=str(entity.get('type') or entity.get('@type') or ''))
        count = by_entity.get(identifier, 0)
        if count:
            node.severity = 'violation'
            node.detail += f' · {count} violation(s)'
            # A minCount violation is about an attribute that is NOT there, so
            # there is no node to hang it on. The entity carries the message or
            # it is lost.
            node.messages = [m for (resource, _), (_, msgs) in findings.items()
                             if resource == identifier for m in msgs]

        kind_name = str(entity.get('type') or entity.get('@type') or '')
        if kind_name:
            node.children.append(_type_node(identifier, kind_name))
        for key, value in entity.items():
            if key in RESERVED:
                continue
            node.children.append(
                _attribute_node(key, value, identifier, [key], findings))
        _stamp_type(node, kind_name)
        root.children.append(node)
    return _name_instances(package, [root])


# --- editing -----------------------------------------------------------------

def _locate(document, entity_id, path):
    for entity in document:
        if not isinstance(entity, dict):
            continue
        if str(entity.get('id') or entity.get('@id')) != entity_id:
            continue
        cursor = entity
        for step in path[:-1]:
            # An attribute with one instance may be written as a bare object or
            # as a one-element array, and both mean the same attribute. The tree
            # addresses instances by index either way, so index 0 against an
            # object stays where it is rather than failing with KeyError: 0.
            if isinstance(step, int) and isinstance(cursor, dict):
                if step:
                    raise PackageError(
                        f'{entity_id}: instance {step} of a single-instance '
                        f'attribute does not exist')
                continue
            try:
                cursor = cursor[step]
            except (KeyError, IndexError, TypeError):
                raise PackageError(
                    f'{entity_id}: no {step} to edit at this address')
        return cursor, path[-1]
    raise PackageError(f'no entity {entity_id} in this example')


def _target_file(package, file=None):
    """Which JSON an edit lands in.

    Defaults to the package model, but the suite view shows entities from
    example files too -- editing one of those has to write where it came from,
    not into model-instance.jsonld.
    """
    if not file:
        return package.sources['model']
    if os.path.isabs(file):
        return file
    for base in (package.path, package.examples_dir):
        candidate = os.path.join(base, file)
        if os.path.exists(candidate):
            return candidate
    raise PackageError(f'no such example file: {file}')


NGSILD_MEMBERS = {'type', 'value', 'object', 'valueList', 'json', 'vocab', 'observedAt',
                  'datasetId', 'unitCode', 'createdAt', 'modifiedAt', 'lang'}


def _as_written(package, entity, attribute_path, value):
    """`value` as the attribute's values are written (#961, contracts/typed-literals):
    a plain number for an xsd:double (float, decimal) attribute is declared with
    the full XSD IRI, since JSON-LD makes a plain whole number an integer. The
    attribute's shape decides, not the number's notation. A value object the
    modeller typed, and anything that is not a plain number, is kept as it is."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    from ..expect.attributecase import declared_type, declared_value

    row = next(_rows(package, entity, attribute_path), None)
    iri = declared_type(row) if row is not None else None
    return declared_value(value, iri) if iri else value


def _rows(package, entity, attribute_path):
    """The attribute's row in each of the entity's types that has it."""
    from ..expect.attributecase import _row

    chain = [step for step in attribute_path
             if isinstance(step, str) and step not in NGSILD_MEMBERS]
    types = entity.get('type')
    for entity_type in (types if isinstance(types, list) else [types]):
        try:
            yield _row(package, entity_type, chain)[1]
        except PackageError:
            continue


def _entity(document, entity_id):
    return next((e for e in document if isinstance(e, dict)
                 and str(e.get('id') or e.get('@id')) == entity_id), None)


def _replace(package, entity_id, path, file, change):
    """Replace one value in an example by `change(old, entity, key)`. Returns
    (path, old, new). Nothing is written when `change` raises."""
    source = _target_file(package, file)
    with open(source, encoding='utf-8') as handle:
        text = handle.read()
    document = json.loads(text, object_pairs_hook=OrderedDict)
    if not isinstance(document, list):
        document = [document]

    container, key = _locate(document, entity_id, list(path))
    try:
        old = container[key]
    except (KeyError, IndexError, TypeError):
        raise PackageError(f'{entity_id}: no value at {"/".join(map(str, path))}')
    made = change(old, _entity(document, entity_id), key)
    container[key] = made

    rendered = json.dumps(document, indent=2, ensure_ascii=False)
    if text.endswith('\n'):
        rendered += '\n'
    json.loads(rendered)                       # never write what will not parse
    with open(source, 'w', encoding='utf-8') as handle:
        handle.write(rendered)
    return source, _render(old), _render(made)


def set_value(package, entity_id, path, value, file=None):
    """Change one value in an example. Returns (path, old, new).

    The new value is parsed as JSON when it can be, so `42` becomes a number
    and `{"@id": "..."}` becomes a node reference -- typing an IRI into a
    Property that expects one should not quietly produce the string form,
    which is the difference between a constraint passing and failing.
    """
    def change(old, entity, key):
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except (TypeError, ValueError):
            parsed = value
        return _as_written(package, entity, path, parsed) if key == 'value' else parsed

    return _replace(package, entity_id, path, file, change)


XSD = 'http://www.w3.org/2001/XMLSchema#'
VALUE_TYPES = ('shape', 'double', 'integer', 'decimal', 'text', 'boolean', 'term')
_NUMBER = re.compile(r'[-+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][-+]?[0-9]+)?')
RDF_LANG_STRING = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#langString'
_DIGITS = 1000      # what a number may be written out with
# The XSD datatypes of whole numbers: a value is an integer of that datatype.
INTEGERS = ('integer', 'int', 'long', 'short', 'byte', 'nonNegativeInteger', 'positiveInteger',
            'negativeInteger', 'nonPositiveInteger', 'unsignedLong', 'unsignedInt',
            'unsignedShort', 'unsignedByte')
_TERM = re.compile(r'[A-Za-z][\w+.-]*:[^\s"<>{}|^`\\]+|<[^\s"<>{}|^`\\]+:[^\s"<>{}|^`\\]+>')


def value_type(value):
    """What an attribute's value is, as JSON-LD reads it: text, integer,
    double, … -- two values may look the same and not be. '' for what has no
    type of its own: a list, an object, null."""
    if isinstance(value, dict):
        if '@id' in value:
            return 'term'
        if '@value' in value:
            if '@type' in value:
                said = re.split(r'[#/:]', str(value['@type']))[-1]
                return {'string': 'text'}.get(said, said)
            return value_type(value['@value'])
        return ''
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, (int, float)):
        from ..rdfio.numbers import LIMIT, as_jsonld_numbers

        read = as_jsonld_numbers(value)
        # JSON-LD 1.1: a plain number of 10^21 and more is a double, however written.
        return 'integer' if isinstance(read, int) and abs(read) < LIMIT else 'double'
    return 'text' if isinstance(value, str) else ''


def _value_says(value):
    """What a value says, as text."""
    if isinstance(value, dict):
        value = value.get('@value', value.get('@id'))
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float, str)):
        return str(value)
    raise PackageError('a list, an object or null has no type to choose')


def _as_type(wanted, text):
    """`text` as a value of the type `wanted`, in the forms of
    contracts/typed-literals; refused when it cannot be one."""
    if wanted == 'text':
        return text
    text = text.strip()
    if wanted == 'boolean':
        if text not in ('true', 'false'):
            raise PackageError(f'{text} is neither true nor false')
        return text == 'true'
    if wanted == 'term':
        if not _TERM.fullmatch(text):
            raise PackageError(f'{text} is no term: one has a prefix, or is a whole IRI')
        return {'@id': text.strip('<>')}
    if not _NUMBER.fullmatch(text):
        raise PackageError(f'{text} is not a number')
    try:
        exact = Decimal(text)
    except InvalidOperation:           # an exponent beyond what Decimal holds
        raise PackageError(f'{text} is not a number that can be written out') from None
    if exact == 0 and abs(exact.as_tuple().exponent) > _DIGITS:
        exact = Decimal(0).copy_sign(exact)    # 0e-2000 is a zero, not 2000 places of one
    if wanted == 'double':
        held = float(text)
        if not math.isfinite(held) or (held == 0 and exact != 0):
            raise PackageError(f'{text} is not a number a double can hold')
        return {'@value': held, '@type': XSD + 'double'}
    integral = exact == exact.to_integral_value()
    if wanted != 'decimal' and not integral:
        raise PackageError(f'{text} is not a whole number: change the value first')
    # The digits it is written out with: before the point, and after it.
    after = 0 if integral and wanted != 'decimal' else max(-exact.as_tuple().exponent, 0)
    digits = max(exact.adjusted() + 1, 1) + after
    if digits > _DIGITS:
        raise PackageError(f'{text} has more than {_DIGITS} digits to write out')
    if wanted == 'decimal':
        # As text: a JSON number would come back as a double's spelling.
        return {'@value': format(exact, 'f'), '@type': XSD + 'decimal'}
    whole = int(exact)
    from ..rdfio.numbers import LIMIT

    # From 10^21 on a JSON number is a double to JSON-LD: its digits, as text.
    said = whole if abs(whole) < LIMIT else str(whole)
    if wanted == 'integer' and said is whole:
        return whole
    return {'@value': said, '@type': XSD + wanted}     # xsd:int, xsd:long, … declared


def _datatype_iri(package, datatype):
    """The IRI a datatype the shapes name means, read with the shapes' prefixes."""
    from ..expect.attributecase import _meant, _prefixes

    said = str(datatype).strip()
    if said.startswith('<') and said.endswith('>'):
        return said[1:-1]
    return _meant(_prefixes(package)[1], said) or \
        (XSD + said[4:] if said.startswith('xsd:') else said)


def _as_shape_says(package, entity, path, old, text):
    """What `text` is in the one datatype the attribute's shape names, else as
    an edit of the value would write it. The shape is the one an edit follows."""
    from ..expect.attributecase import value_datatype

    row = next(_rows(package, entity, path), None)
    datatype = value_datatype(row) if row is not None else None
    if datatype:
        iri = _datatype_iri(package, datatype)
        local = iri[len(XSD):] if iri.startswith(XSD) else None
        if local in ('double', 'decimal', 'boolean') or local in INTEGERS:
            return _as_type(local, text)
        if local == 'float':
            return dict(_as_type('double', text), **{'@type': XSD + 'float'})
        if local == 'string':
            return text
        if iri == RDF_LANG_STRING:
            # A text with a language keeps it; one without has none to give.
            if isinstance(old, dict) and '@language' in old:
                return dict(old, **{'@value': text})
            raise PackageError(f'{text} has no language, which its shape asks for')
        return {'@value': text, '@type': iri}
    if isinstance(old, dict) and '@id' in old:
        return old
    try:
        made = json.loads(text)
    except ValueError:
        return text
    if isinstance(made, (int, float)) and not isinstance(made, bool) and math.isfinite(made):
        return _as_written(package, entity, path, made)
    return made if isinstance(made, bool) else text


def set_value_type(package, entity_id, path, wanted, file=None):
    """Make one value of an example another type, what it says unchanged: 50.0
    as a double, an integer, a text. 'shape': as the attribute's shape asks.
    Returns (path, old, new)."""
    if wanted not in VALUE_TYPES:
        raise PackageError(f'{wanted} is no type of value: {", ".join(VALUE_TYPES)}')
    if not path or path[-1] != 'value':
        raise PackageError('only the value of a Property has a type to choose')

    def change(old, entity, key):
        text = _value_says(old)
        return _as_shape_says(package, entity, path, old, text) if wanted == 'shape' \
            else _as_type(wanted, text)

    return _replace(package, entity_id, path, file, change)


def add_observation(package, entity_id, attribute_path, dataset_id=None,
                    value=None, observed_at=None, file=None):
    """Append an observation to one attribute of one entity.

    An attribute is identified by (entity, name, datasetId), so a new
    observation joins the series for ITS datasetId and starts a new one for a
    datasetId not seen before. The type is copied from what is already there --
    a Property whose new instance arrives as a Relationship is not a new
    observation of the same attribute, it is a different attribute.
    """
    source = _target_file(package, file)
    with open(source, encoding='utf-8') as handle:
        text = handle.read()
    document = json.loads(text, object_pairs_hook=OrderedDict)
    if not isinstance(document, list):
        document = [document]

    entity = next((e for e in document if isinstance(e, dict)
                   and str(e.get('id') or e.get('@id')) == entity_id), None)
    if entity is None:
        raise PackageError(f'no entity {entity_id} in this example')

    cursor = entity
    for step in list(attribute_path)[:-1]:
        cursor = cursor[step]
    key = list(attribute_path)[-1]
    if key not in cursor:
        raise PackageError(f'{entity_id} has no attribute {key}')

    existing = cursor[key]
    instances = existing if isinstance(existing, list) else [existing]
    template = next((i for i in instances if isinstance(i, dict)), {})

    fresh = OrderedDict()
    if template.get('type'):
        fresh['type'] = template['type']
    try:
        fresh['value'] = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        fresh['value'] = value
    fresh['value'] = _as_written(package, entity, attribute_path, fresh['value'])
    if observed_at:
        same = _group_by_dataset(instances).get(dataset_id or DEFAULT_DATASET, [])
        fresh['observedAt'] = checked_stamp(observed_at, same, f'{entity_id}: {key}')
    if dataset_id and dataset_id != DEFAULT_DATASET:
        fresh['datasetId'] = dataset_id

    cursor[key] = instances + [fresh]

    rendered = json.dumps(document, indent=2, ensure_ascii=False)
    if text.endswith('\n'):
        rendered += '\n'
    json.loads(rendered)
    with open(source, 'w', encoding='utf-8') as handle:
        handle.write(rendered)
    return source, len(cursor[key])


def checked_stamp(stamp, members=(), what=''):
    """`stamp` as an observedAt is written -- 2024-02-28T13:52:35.000Z -- after
    checking it is one, and that no other instance of the same datasetId says
    it: two of them would be one update written twice."""
    from ..ngsild.timestamps import normalised, parse

    written = normalised(stamp)
    if written is None:
        raise PackageError(f'"{stamp}" is not a timestamp: ISO 8601 with its zone, '
                           f'e.g. 2024-02-28T13:52:35.000Z')
    moment = parse(written)
    for _, member in members:
        if isinstance(member, dict) and parse(member.get('observedAt')) == moment:
            raise PackageError(f'{what} already has an observation at {written} for this '
                               f'datasetId; another one there would be the same update '
                               f'written twice')
    return written


DATASET_IRI = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:[^\s<>"{}|\\^`]+$')


def dataset_id_problem(dataset_id, package=None):
    """What is wrong with `dataset_id` as a datasetId, or None.

    NGSI-LD makes it a URI, and the context reads it as an @id: a plain word
    is resolved against the document's base and silently becomes another id.
    `@none` is the platform's own name for the default instance -- written in
    the data it is NOT that: the default instance is the one without one.
    """
    text = str(dataset_id or '').strip()
    if text == DEFAULT_DATASET:
        return ('@none is the platform\'s name for the default instance; in the data '
                'the default instance is the one WITHOUT a datasetId')
    if not DATASET_IRI.match(text):
        return f'"{text}" is not an IRI; a datasetId is one, e.g. urn:sensor:left'
    if package is not None and dataset_name(dataset_names(package), text) is None:
        return (f'{text} is in no namespace this package registers. A datasetId reads '
                f'attribute[prefix:name], so its namespace needs a prefix: register it '
                f'(New namespace…) first')
    return None


LOCAL_NAME = re.compile(r'^[A-Za-z0-9_][\w.-]*$')


def dataset_names(package):
    """{namespace: prefix} a datasetId may be written in: the package's own
    registered namespaces, not the standard vocabularies."""
    from ..package.prefixes import STANDARD, names_by_namespace

    standard = set(STANDARD.values())
    return {space: prefix for space, prefix in names_by_namespace(package.path).items()
            if prefix and space not in standard}


def dataset_name(names, dataset_id):
    """`prefix:name` for a datasetId in a registered namespace (the longest
    that fits), else None. The default instance has none."""
    text = str(dataset_id or '')
    best = None
    for space, prefix in names.items():
        if text.startswith(space) and LOCAL_NAME.match(text[len(space):]) and \
                (best is None or len(space) > len(best[0])):
            best = (space, prefix)
    return f'{best[1]}:{text[len(best[0]):]}' if best else None


def instance_label(attribute, dataset_id, names):
    """How one instance of an attribute reads: `hasHeight[sensors:left]`, the
    default instance plain `hasHeight`, an unregistered datasetId in full."""
    if not dataset_id or dataset_id == DEFAULT_DATASET:
        return attribute
    return f'{attribute}[{dataset_name(names, dataset_id) or dataset_id}]'


def _read_document(source):
    with open(source, encoding='utf-8') as handle:
        text = handle.read()
    document = json.loads(text, object_pairs_hook=OrderedDict)
    return text, document, (document if isinstance(document, list) else [document])


def _instances_at(entities, entity_id, attribute_path):
    holder, key = _locate(entities, entity_id, list(attribute_path))
    if not isinstance(holder, dict) or key not in holder:
        raise PackageError(f'{entity_id} has no attribute {key}')
    existing = holder[key]
    return holder, key, list(existing) if isinstance(existing, list) else [existing]


def add_instance(package, entity_id, attribute_path, dataset_id, file=None):
    """Another instance of an attribute: the same attribute under a new
    datasetId -- what sh:minCount and sh:maxCount count.

    It starts as a copy of the attribute's current instance (its type, value
    and sub-attributes), so the case stays valid in everything but the count.
    A datasetId the attribute already has is refused: a second instance there
    is an observation of that one, not another instance.
    """
    import copy

    problem = dataset_id_problem(dataset_id, package)
    if problem:
        raise PackageError(problem)
    dataset_id = str(dataset_id).strip()
    source = _target_file(package, file)
    text, document, entities = _read_document(source)
    holder, key, instances = _instances_at(entities, entity_id, attribute_path)
    groups = _group_by_dataset(instances)
    if dataset_id in groups:
        raise PackageError(f'{entity_id}: {key} already has an instance with datasetId '
                           f'{dataset_id}; another one there is an observation of it')
    members = next(iter(groups.values()))
    fresh = copy.deepcopy(_member_at(members, _current_index(members)))
    if not isinstance(fresh, dict):
        raise PackageError(f'{entity_id}: {key} is not an NGSI-LD attribute')
    fresh['datasetId'] = dataset_id
    holder[key] = instances + [fresh]
    _write(source, document, text)
    return {'file': source, 'datasetId': dataset_id, 'instances': len(groups) + 1}


def set_dataset_id(package, entity_id, attribute_path, old, new, file=None, index=None):
    """Give the instances of datasetId `old` the datasetId `new` -- every
    observation of it, since they are one instance. `@none` or '' as `old`
    is the default instance; as `new` it makes that instance the default
    (its datasetId is removed), when the attribute has none yet.

    `index` (a position in the attribute's array) moves that ONE instance
    instead: the fix for two instances that share a datasetId by mistake.
    `@none` to `@none` drops a "datasetId": "@none" written out, which is
    not the default instance it means to be."""
    old = str(old or '').strip() or DEFAULT_DATASET
    new = str(new or '').strip() or DEFAULT_DATASET
    if new != DEFAULT_DATASET:
        problem = dataset_id_problem(new, package)
        if problem:
            raise PackageError(problem)
    source = _target_file(package, file)
    text, document, entities = _read_document(source)
    holder, key, instances = _instances_at(entities, entity_id, attribute_path)
    groups = _group_by_dataset(instances)
    if old not in groups:
        raise PackageError(f'{entity_id}: {key} has no instance with datasetId {old}')
    if new == old == DEFAULT_DATASET:
        written = [i for _, i in groups[old] if i.get('datasetId') == DEFAULT_DATASET]
        for instance in written:
            del instance['datasetId']
        _write(source, document, text)
        return {'file': source, 'datasetId': new, 'changed': len(written)}
    if new == old:
        return {'file': source, 'datasetId': new, 'changed': 0}
    if new in groups:
        raise PackageError(f'{entity_id}: {key} already has '
                           + ('a default instance' if new == DEFAULT_DATASET
                              else f'an instance with datasetId {new}'))
    moving = groups[old]
    if index is not None:
        moving = [(position, i) for position, i in moving if position == int(index)]
        if not moving:
            raise PackageError(f'{entity_id}: {key} has no instance {index} with '
                               f'datasetId {old}')
    for _, instance in moving:
        if new == DEFAULT_DATASET:
            instance.pop('datasetId', None)
        else:
            instance['datasetId'] = new
    holder[key] = instances if isinstance(holder[key], list) else instances[0]
    _write(source, document, text)
    return {'file': source, 'datasetId': new, 'changed': len(moving)}


def set_observed_at(package, entity_id, attribute_path, index, stamp, file=None):
    """Give one instance -- `index` in the attribute's array -- its observedAt,
    or with no stamp take it away (it then counts as now, as on the platform).
    A stamp another instance of its datasetId already says is refused."""
    source = _target_file(package, file)
    text, document, entities = _read_document(source)
    holder, key, instances = _instances_at(entities, entity_id, attribute_path)
    index = int(index or 0)
    if not 0 <= index < len(instances) or not isinstance(instances[index], dict):
        raise PackageError(f'{entity_id}: {key} has no instance {index}')
    instance = instances[index]
    if stamp:
        same = [(i, m) for i, m in _group_by_dataset(instances).get(
            _dataset_of(instance), []) if i != index]
        instance['observedAt'] = checked_stamp(stamp, same, f'{entity_id}: {key}')
    else:
        instance.pop('observedAt', None)
    _write(source, document, text)
    return {'file': source, 'observedAt': instance.get('observedAt', '')}


def sort_observations(package, entity_id, attribute_path, dataset_id=None, file=None):
    """Put the observations of one datasetId in time order, the latest last --
    where Scorpio and the bridge look for the current one -- leaving every
    other instance where it is."""
    from ..ngsild.timestamps import key as moment

    source = _target_file(package, file)
    text, document, entities = _read_document(source)
    holder, key, instances = _instances_at(entities, entity_id, attribute_path)
    members = _group_by_dataset(instances).get(str(dataset_id or '') or DEFAULT_DATASET)
    if not members:
        raise PackageError(f'{entity_id}: {key} has no instance with datasetId {dataset_id}')
    ordered = sorted((instance for _, instance in members), key=moment)
    for (position, _), instance in zip(members, ordered):
        instances[position] = instance
    if isinstance(holder[key], list):
        holder[key] = instances
    _write(source, document, text)
    return {'file': source, 'sorted': len(members)}


def remove_value(package, entity_id, path, file=None, dataset=None):
    """Remove what a row of a case stands for, from the file it was read from.

    `path` is the row's address. An attribute's own path (`[hasState]`, or
    `[hasFilter, 0, hasTrust]` for a sub-attribute) removes the whole
    attribute; with `dataset`, only its instances with that datasetId; a
    path ending in the value key (`[hasState, 2, value]`) removes that one
    observation; one ending in a metadata key (`observedAt`, `unitCode`, ...)
    removes that key. An attribute left with no instance goes entirely.

    Returns {'file', 'removed'}: where, and what in words.
    """
    source = _target_file(package, file)
    with open(source, encoding='utf-8') as handle:
        text = handle.read()
    document = json.loads(text, object_pairs_hook=OrderedDict)
    if not isinstance(document, list):
        document = [document]
    path = list(path)
    if not path:
        raise PackageError('nothing to remove: the row has no address')

    def short(key):
        return str(key).rsplit('/', 1)[-1].rsplit('#', 1)[-1].split(':')[-1]

    if path[-1] in VALUE_KEYS and len(path) >= 3 and isinstance(path[-2], int):
        # One observation of a series: its instance goes from the array.
        holder, key = _locate(document, entity_id, path[:-2])
        instances = holder.get(key) if isinstance(holder, dict) else None
        if instances is None:
            raise PackageError(f'{entity_id} has no {short(key)} any more')
        index = path[-2]
        if isinstance(instances, list):
            if not 0 <= index < len(instances):
                raise PackageError(f'{entity_id}: {short(key)} has no observation {index}')
            del instances[index]
            if len(instances) == 0:
                del holder[key]
        else:
            del holder[key]
        removed = f'an observation of {short(key)}'
    elif dataset is not None:
        holder, key = _locate(document, entity_id, path)
        if key not in holder:
            raise PackageError(f'{entity_id} has no {short(key)} any more')
        value = holder[key]
        instances = value if isinstance(value, list) else [value]
        keep = [i for i in instances if _dataset_of(i) != str(dataset)]
        if len(keep) == len(instances):
            raise PackageError(f'{entity_id}: {short(key)} has no instance with datasetId {dataset}')
        if keep:
            holder[key] = keep if len(keep) > 1 or isinstance(value, list) else keep[0]
        else:
            del holder[key]
        removed = f'{short(key)} ({dataset})'
    else:
        holder, key = _locate(document, entity_id, path)
        if not isinstance(holder, dict) or key not in holder:
            raise PackageError(f'{entity_id} has no {short(key)} any more')
        if key in RESERVED and key not in META_KEYS:
            raise PackageError(f'{key} is what makes it an entity or an attribute; it is '
                               'not removed on its own')
        del holder[key]
        removed = short(key)
    _write(source, document, text)
    return {'file': source, 'removed': removed}


def _write(source, document, text):
    rendered = json.dumps(document, indent=2, ensure_ascii=False)
    if text.endswith('\n'):
        rendered += '\n'
    json.loads(rendered)
    with open(source, 'w', encoding='utf-8') as handle:
        handle.write(rendered)
    return rendered


def _attribute_node_at(entity, under, entity_id, dataset=None):
    """The attribute instance `under` addresses inside an entity.

    `under` is the attribute path a Model-view row carries: keys, and the
    instance index of each enclosing attribute. The last attribute is picked
    the way the tree shows it -- by datasetId, then the current observation --
    because a row stands for one dataset, and an index inside that dataset is
    not an index into the list the document holds.
    """
    from ..ngsild.build import KINDS

    node = entity
    for position, step in enumerate(under):
        if isinstance(step, int):
            if isinstance(node, list):
                node = node[step]
            continue
        if isinstance(node, list):
            node = node[0] if len(node) == 1 else None
        if not isinstance(node, dict) or step not in node:
            raise PackageError(f'{entity_id} has no {step} at that place')
        node = node[step]
    if isinstance(node, list):
        groups = _group_by_dataset(node)
        wanted = dataset or (next(iter(groups)) if len(groups) == 1 else None)
        if wanted not in groups:
            raise PackageError(
                f'that attribute has {len(groups)} datasets on {entity_id}; '
                f'add the sub-attribute on one dataset\'s row')
        members = groups[wanted]
        node = _member_at(members, _current_index(members))
    if not isinstance(node, dict) or node.get('type') not in KINDS:
        raise PackageError('that is not an attribute; a sub-attribute hangs off '
                           'an attribute node (a Property or a Relationship)')
    return node


def add_attribute(package, entity_id, name, kind=None, value=None,
                  file=None, under=None, dataset=None, **metadata):
    """Add a legal NGSI-LD attribute to an entity.

    The kind decides which key carries the payload, and the shapes are asked
    first: a value shape on ngsild:hasObject means Relationship, one on
    hasValue means Property. Reading it from the model beats asking the author,
    who is the person the model exists to help -- and getting the pairing wrong
    produces something that parses, looks plausible and means nothing.
    """
    from ..ngsild.build import attribute, kind_for_shape
    from .choices import attribute_terms

    # Declared before used, for the same reason a type is: the NAME is what a
    # shape's sh:path matches, so one the knowledge has never heard of is not
    # a broken document but an invisible one -- no constraint selects it, and
    # the entity reads as validated.
    declared = attribute_terms(package)
    if declared and name not in ({entry.term for entry in declared}
                                 | {entry.iri for entry in declared}):
        raise PackageError(
            f'{name} is not an attribute this package declares. Declare it in '
            f'the knowledge first -- it needs a domain (which entity type '
            f'carries it) and a range (Property or Relationship).')

    source = _target_file(package, file)
    with open(source, encoding='utf-8') as handle:
        text = handle.read()
    document = json.loads(text, object_pairs_hook=OrderedDict)
    if not isinstance(document, list):
        document = [document]

    entity = next((e for e in document if isinstance(e, dict)
                   and str(e.get('id') or e.get('@id')) == entity_id), None)
    if entity is None:
        raise PackageError(f'no entity {entity_id} in {source}')

    # `under`: a sub-attribute, hung off the attribute instance it addresses
    # rather than off the entity -- and only one the knowledge allows there.
    carrier = entity
    if under:
        from .choices import sub_attributes_for

        carrier = _attribute_node_at(entity, under, entity_id, dataset)
        parent = next(step for step in reversed(under) if isinstance(step, str))
        allowed = sub_attributes_for(package, parent)
        if not any(name in (e.term, e.iri) for e in allowed):
            raise PackageError(
                f'{name} is not something {parent} may carry: the knowledge '
                f'allows {", ".join(e.term for e in allowed) or "nothing"} '
                f'inside it')
        if not kind:
            kind = next((e.kind for e in declared
                         if name in (e.term, e.iri)), '') or 'Property'

    # An attribute is (entity, name, datasetId): one the entity already has is
    # added again as another INSTANCE, under a datasetId it does not have yet
    # -- empty meaning the default instance. Only that exact pair is refused.
    dataset_id = str(metadata.get('datasetId') or '').strip()
    if dataset_id:
        problem = dataset_id_problem(dataset_id, package)
        if problem:
            raise PackageError(problem)
        metadata['datasetId'] = dataset_id
    else:
        metadata.pop('datasetId', None)
    existing = None
    if name in carrier:
        existing = carrier[name] if isinstance(carrier[name], list) else [carrier[name]]
        groups = _group_by_dataset(existing)
        same = groups.get(dataset_id or DEFAULT_DATASET)
        if same and not metadata.get('observedAt'):
            which = f'datasetId {dataset_id}' if dataset_id else 'a default instance'
            raise PackageError(
                f'{entity_id} already has {name} with {which}. Another one there is '
                f'an observation of it: give it a timestamp none of its instances has, '
                f'or another datasetId')
        if same:
            # The same datasetId at another time: an observation of it.
            metadata['observedAt'] = checked_stamp(metadata['observedAt'], same,
                                                   f'{entity_id}: {name}')
        # The same attribute: its kind is what is already written.
        kind = next((i.get('type') for i in existing
                     if isinstance(i, dict) and i.get('type')), None) or kind

    if not kind:
        kind = kind_for_shape(package, str(entity.get('type', '')), name) \
            or 'Property'
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        parsed = value

    if kind == 'Property':
        parsed = _as_written(package, entity, list(under or []) + [name], parsed)
    if metadata.get('observedAt') and existing is None:
        metadata['observedAt'] = checked_stamp(metadata['observedAt'])
    fresh = attribute(kind, parsed, **metadata)
    carrier[name] = fresh if existing is None else existing + [fresh]
    _write(source, document, text)
    return source, kind


def add_entity(package, identifier, entity_type, file=None, context=None):
    """Append a legal NGSI-LD entity to an example file.

    The type must be one the KNOWLEDGE declares. A type invented here is the
    quietest way to break a model: no shape targets it, so every constraint
    stays silent and the entity reads as validated. A genuinely missing type is
    declared first -- `knowledge.add_entity_type` -- and used afterwards.
    """
    from ..ngsild.build import entity as build_entity
    from ..package.context import context_config
    from .choices import entity_types

    known, root = entity_types(package)
    if root is not None:
        allowed = {t.term for t in known} | {t.iri for t in known}
        if entity_type not in allowed:
            raise PackageError(
                f'{entity_type} is not an entity type in this package. '
                f'Declare it in the knowledge first. '
                f'Known: {", ".join(sorted(t.term for t in known))}')

    source = _target_file(package, file)
    with open(source, encoding='utf-8') as handle:
        text = handle.read()
    document = json.loads(text, object_pairs_hook=OrderedDict)
    if not isinstance(document, list):
        document = [document]

    if any(isinstance(e, dict) and str(e.get('id') or e.get('@id')) == identifier
           for e in document):
        raise PackageError(f'{source} already declares {identifier}')

    if context is None:
        existing = next((e.get('@context') for e in document
                         if isinstance(e, dict) and e.get('@context')), None)
        context = existing or context_config(package.path).published

    document.append(build_entity(identifier, entity_type, context=context))
    _write(source, document, text)
    return source, len(document)


def _case_file(package, case):
    """(a declared case's file as the package names it, its declaration). Two
    cases may be one file, by a link: the one that is named, before the other."""
    from ..expect.store import examples_root, load_expectations

    root = examples_root(package.path)
    wanted = os.path.abspath(case if os.path.isabs(case) else os.path.join(root, case))
    declared = [(os.path.abspath(os.path.join(root, e.path)), e) for e in load_expectations(package.path).examples]
    for same in (lambda path: path == wanted, lambda path: os.path.realpath(path) == os.path.realpath(wanted)):
        for path, example in declared:
            if same(path):
                return path, example
    raise PackageError(f'{case} is not a declared test case')


def _read(path):
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    try:
        document = json.loads(text, object_pairs_hook=OrderedDict)
    except ValueError as exc:
        raise PackageError(f'{os.path.basename(path)} is not JSON: {exc}')
    documents = document if isinstance(document, list) else [document]
    if any(isinstance(d, dict) and '@graph' in d for d in documents):
        # Not seen, they would be missing from a copy, or pasted a second time.
        raise PackageError(f'{os.path.basename(path)} has its entities inside "@graph", which copy and paste do not '
                           'read; write them as a list')
    for document in documents:
        inside = _inlined(document)
        if inside:
            raise PackageError(f'{os.path.basename(path)}: {_document_id(document)} has {inside} written in a '
                               "relationship's object, which copy and paste do not read; write it as an entity of "
                               'its own and point at its id')
    return documents, text


OBJECTS = ('object', 'objectList', 'ngsi-ld:hasObject', 'ngsi-ld:hasObjectList',
           'https://uri.etsi.org/ngsi-ld/hasObject', 'https://uri.etsi.org/ngsi-ld/hasObjectList')
# What an attribute has besides its sub-attributes: no entity is written there.
NOT_ATTRIBUTES = set(VALUE_KEYS) | set(META_KEYS) | {
    'vocab', 'languageMap', 'lang', 'objectType', 'createdAt', 'modifiedAt', 'deletedAt', 'instanceId'}


def _relationship(node):
    kind = str(node.get('type') or node.get('@type') or '')
    return kind.rpartition(':')[2].rpartition('/')[2] in ('Relationship', 'ListRelationship') or \
        not set(node).isdisjoint(OBJECTS)


def _inlined(document):
    """The id (or type) of the first entity written in a relationship's object
    -- its own or a sub-attribute's -- else ''. A reference ({"@id": …}) is
    none, and neither is anything in a Property's value."""
    if not isinstance(document, dict):
        return ''
    pending = [v for k, v in document.items() if k not in RESERVED]
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(node)
        elif isinstance(node, dict):
            relationship = _relationship(node)
            for key, value in node.items():
                if relationship and key in OBJECTS:
                    objects = [value]
                    while objects:
                        one = objects.pop()
                        if isinstance(one, list):
                            objects.extend(one)
                        elif isinstance(one, dict) and set(one) <= set(OBJECTS) | {'@list'}:
                            objects.extend(one.values())     # {"@list": …}, objectList's {"object": …}
                        elif isinstance(one, dict) and set(one) - {'id', '@id'}:
                            return _document_id(one) or str(one.get('type') or one.get('@type') or 'an entity')
                elif key not in RESERVED and key not in NOT_ATTRIBUTES:
                    pending.append(value)              # a sub-attribute
    return ''


def _write_whole(source, document, text):
    """`_write`, but the file is either what it was or all of the new one. A
    link stays a link: what it leads to is written."""
    import shutil
    import tempfile

    target = os.path.realpath(source)
    handle, partial = tempfile.mkstemp(dir=os.path.dirname(target), suffix='.partial')
    os.close(handle)
    try:
        _write(partial, document, text)
        shutil.copymode(target, partial)
        os.replace(partial, target)
    finally:
        if os.path.exists(partial):
            os.remove(partial)


def _document_id(document):
    return str(document.get('id') or document.get('@id') or '') if isinstance(document, dict) else ''


def _included_files(package, example):
    """The files a case includes, found as `compose` finds them."""
    from ..expect.store import examples_root

    found = []
    for relative in example.include:
        for base in (examples_root(package.path), package.path):
            path = os.path.abspath(os.path.join(base, relative))
            if os.path.exists(path):
                found.append(path)
                break
    return found


def _same_document(one, other):
    """Do two documents of one entity say the same? The order of keys and the
    spelling of the id say nothing, but 1, 1.0 and true are three values, though
    Python calls them equal."""
    def said(document):
        return json.dumps({k: v for k, v in document.items() if k not in ('id', '@id')}, sort_keys=True)
    return said(one) == said(other)


class _Ids:
    """The IRI an entity's id names, however it is written: whole, with a
    prefix of its context, relative ("./a" and "a" are one), or with a prefix
    its context leaves open, which the package's names expand (D6)."""

    def __init__(self, package):
        from ..package.context import context_config, local_context_value

        config = context_config(package.path)
        self._inline = local_context_value(package.path, config) if config.declared else None
        self._published, self._contexts, self._path, self._canonical = config.published, {}, package.path, {}

    def _own_context(self, value):
        """As resolve_model_document does: the package's own, not the web's."""
        if self._inline is not None and value == self._published:
            return self._inline
        if self._inline is not None and isinstance(value, list):
            return [self._inline if item == self._published else item for item in value]
        return value

    def resolved(self, document):
        if not isinstance(document, dict) or '@context' not in document:
            return document
        return dict(document, **{'@context': self._own_context(document['@context'])})

    def _context(self, value, folder):
        from rdflib.plugins.shared.jsonld.context import Context

        from ..rdfio.relative import BASE, absolute_contexts

        key = (folder, json.dumps(value, sort_keys=True))
        if key not in self._contexts:
            value = absolute_contexts({'@context': self._own_context(value)}, os.path.join(folder, 'x'))['@context']
            try:
                self._contexts[key] = Context(value, base=BASE)
            except Exception:                      # noqa: BLE001 -- not to be had: no prefixes then
                self._contexts[key] = Context(base=BASE)
        return self._contexts[key]

    def term(self, document, folder):
        """The id as the graph has it; '' for a document without an id."""
        name = _document_id(document)
        if not name or name.startswith('_:'):
            return name
        return self._context(document.get('@context'), folder).resolve(name) or name

    def canonical(self, term):
        """A term of the graph as the package names it: a prefix the context
        left open, by the package's names -- as the trees read it."""
        from .choices import expand

        if term not in self._canonical:
            self._canonical[term] = expand(self._path, term) if term and not term.startswith('_:') else term
        return self._canonical[term]

    def iri(self, document, folder):
        """'' for a document without an id."""
        return self.canonical(self.term(document, folder))


def _once(paths):
    """Each file once, however it is named."""
    found = OrderedDict()
    for path in paths:
        found.setdefault(os.path.realpath(path), path)
    return list(found.values())


class _Scene:
    """Where a copy takes entities from: the file of the entity, then -- for a
    test case -- what it includes, then the main model. `file`: none for the
    main model's. An entity is named by its IRI here."""

    def __init__(self, package, file):
        from ..expect.store import examples_root, load_expectations

        self.package, self.example = package, None
        models = _once(os.path.abspath(p) for p in package.files('model') if p.endswith(('.jsonld', '.json')))
        own = []
        if file:
            named = os.path.abspath(_target_file(package, file))
            wanted = os.path.realpath(named)
            if any(os.path.realpath(p) == wanted for p in models):
                # The row's own file first: another may define the id as well.
                models.sort(key=lambda p: os.path.realpath(p) != wanted)
            else:
                own = _once(self._own_files(named, load_expectations(package.path), examples_root(package.path)))
        self.own, self.ids = own, _Ids(package)
        self.written, self.repeated = OrderedDict(), set()
        # Of each group, the definition that counts, the others, and what has no id.
        self._counts, self._unnamed, self._all = {'own': OrderedDict(), 'model': OrderedDict()}, {}, []
        outside = [p for p in _included_files(package, self.example) if not self._inside(p)] if self.example else []
        for group, paths in (('own', own + _once(outside)), ('model', models)):
            counts, self._unnamed[group] = self._counts[group], []
            for path in paths:
                for document in _read(path)[0]:
                    iri = self.ids.iri(document, os.path.dirname(path))
                    if not iri:
                        self._unnamed[group].append((document, path, group))
                        continue
                    if iri in counts:
                        self.repeated.add(iri)       # one entity of two definitions: the first is taken
                    definition = counts.setdefault(iri, (document, path, group))
                    if path not in outside:
                        self._all.append((iri, (document, path, group)))
                        self.written.setdefault(iri, definition)
        self._graphs, self._pointers, self._documents = {}, {}, {}

    def _own_files(self, named, expectations, root):
        """`named` as the package names it -- a file outside it, or one that
        is not its data, is nothing to copy from -- and what it includes. A
        case by the path it was named by, before one that is the same file by
        a link: a relative context is read from that path's folder."""
        cases = [(os.path.abspath(os.path.join(root, e.path)), e) for e in expectations.examples]
        included = [p for _, e in cases for p in _included_files(self.package, e)]
        for same in (lambda path: path == named, lambda path: os.path.realpath(path) == os.path.realpath(named)):
            for path, example in cases:
                if same(path):
                    self.example = example
                    return [path] + [p for p in _included_files(self.package, example) if self._inside(p)]
            for path in included:
                if same(path) and self._inside(path):
                    return [path]
        raise PackageError(f'{os.path.basename(named)} is no model file, test case or included file of this package')

    def _inside(self, path):
        root = os.path.abspath(self.package.path)
        return os.path.commonpath([root, os.path.abspath(path)]) == root

    def asked(self, entity_id, file):
        """The IRI of the entity of a row, which has its id as written, in its
        file; that definition is then the one that is copied."""
        wanted = os.path.realpath(_target_file(self.package, file)) if file else None
        for iri, definition in self._all:
            if _document_id(definition[0]) == entity_id and wanted in (None, os.path.realpath(definition[1])):
                self.written[iri] = self._counts[definition[2]][iri] = definition
                return iri
        raise PackageError(f'no entity {entity_id} to copy any more')

    def said_by(self, iri):
        """The graph to read an entity's relationships from: what is copied, so
        of one defined more than once only that definition's."""
        if iri not in self.repeated:
            return self.graph(self.written[iri][2])
        if iri not in self._documents:
            document, path, _ = self.written[iri]
            self._documents[iri] = self._parsed([(document, path)])
        return self._documents[iri]

    def graph(self, group):
        """The triples an entity is in: those of the case it is in -- which
        are one graph with what it includes -- or of the main model. Of an id
        defined more than once, those of the definition that counts."""
        if group not in self._graphs:
            if self.repeated.isdisjoint(self._counts[group]):
                self._graphs[group] = self.package.model if group == 'model' else self._own_graph()
            else:
                self._graphs[group] = self._counted(group)
        return self._graphs[group]

    def _counted(self, group):
        return self._parsed([(document, path) for document, path, _ in
                             list(self._counts[group].values()) + self._unnamed[group]])

    def _parsed(self, documents):
        from rdflib import Graph

        from ..package.loader import hoist_context
        from ..rdfio.relative import BASE, for_rdflib

        graph, by_path = Graph(), OrderedDict()
        for document, path in documents:
            by_path.setdefault(path, []).append(self.ids.resolved(document))
        for path, of_path in by_path.items():
            graph.parse(data=json.dumps(hoist_context(for_rdflib(of_path, path))), format='json-ld', base=BASE)
        return graph

    def term(self, iri):
        """The id of the definition copied, as its graph has it."""
        document, path, _ = self.written[iri]
        return self.ids.term(document, os.path.dirname(path))

    def pointing_at(self, iri, groups):
        """The entities that point at `iri`; all by the package's names."""
        from .hierarchy import pointers

        found, canonical = set(), self.ids.canonical
        for group in groups:
            if group not in self._pointers:
                by = {}
                for target, sources in pointers(self.graph(group)).items():
                    by.setdefault(canonical(str(target)), set()).update(canonical(str(s)) for s in sources)
                self._pointers[group] = by
            found |= self._pointers[group].get(iri, set())
        return found

    def _own_graph(self):
        from rdflib import Graph

        from ..expect.store import compose
        from ..package.context import resolve_model_document
        from ..package.loader import hoist_context
        from ..rdfio.relative import BASE, for_rdflib

        if self.example is not None:
            return compose(self.package, self.example)
        document, _ = resolve_model_document(self.package.path, self.own[0])
        return Graph().parse(data=json.dumps(hoist_context(for_rdflib(document, self.own[0]))),
                             format='json-ld', base=BASE)

    def name(self, iri, spelled=None):
        """An entity's id as its document has it, else as the data points at it."""
        from ..rdfio.relative import as_written

        return _document_id(self.written[iri][0]) if iri in self.written else as_written((spelled or {}).get(iri, iri))


def copy_entities(package, entity_id, file=None, subtree=False):
    """What a copy of an entity holds, to be pasted into a test case. `file`:
    the one it is read from (the main model's, when not given). `subtree`: with
    its children, theirs, and so on: what a relationship made from a HasChild
    reference leads to (hierarchy.py), as far as the data of that file --
    itself, what a case includes, the main model -- has it. Each is taken once,
    so a circle ends.

    Returns {'content', 'copied', 'missing', 'left', 'assumed', 'repeated'}:
    `content` is {'package', 'entities': [{'document', 'from'}]}, each document
    with the folder it is read from (a relative @context is from there), and is
    what `paste_entities` takes. The others are ids as written: what is copied;
    children that are written nowhere; what the copied ones point at otherwise;
    those copied as children by the data only (no shape declares the
    relationship); and those defined more than once, of which the first is
    copied.
    """
    from rdflib import URIRef

    from .hierarchy import Hierarchy

    scene = _Scene(package, file)
    top = scene.asked(entity_id, file)
    hierarchy = Hierarchy(package)
    order, at, copied, missing, left, assumed, spelled = [top], 0, {top}, OrderedDict(), set(), set(), {}
    while subtree and at < len(order):
        iri, at = order[at], at + 1
        node, group = URIRef(scene.term(iri)), scene.written[iri][2]
        for target, child in sorted(hierarchy.relationships(scene.said_by(iri), node).items()):
            end, guessed = scene.ids.canonical(str(target)), False
            spelled.setdefault(end, str(target))
            if child is None and hierarchy.has_reference_types and end in scene.written:
                # What it points at itself is no other's.
                guessed = scene.pointing_at(end, {group, scene.written[end][2]}) - {end} == {iri}
            if not (child or guessed):
                left.add(end)
            elif end not in scene.written:
                missing[end] = True
            elif end not in copied:
                copied.add(end)
                order.append(end)
                assumed |= {end} if guessed else set()
    root = os.path.abspath(package.path)
    return {'content': {'package': os.path.realpath(package.path),
                        'entities': [{'document': scene.written[iri][0],
                                      'from': os.path.relpath(os.path.dirname(scene.written[iri][1]), root)}
                                     for iri in order]},
            'copied': [scene.name(i) for i in order], 'missing': [scene.name(i, spelled) for i in missing],
            'left': sorted(scene.name(i, spelled) for i in left - copied - set(missing)),
            'assumed': [scene.name(i) for i in order if i in assumed],
            'repeated': [scene.name(i) for i in order if i in scene.repeated]}


def _checked_content(package, content):
    """[(document, the folder it was read from)] of what `copy_entities` gave.
    It went through the editor, so what it is is checked here."""
    if not isinstance(content, dict) or not isinstance(content.get('entities'), list):
        raise PackageError('what is pasted is not a copy of entities')
    if not content['entities']:
        raise PackageError('nothing to paste')
    copied_in = str(content.get('package') or '')
    if copied_in != os.path.realpath(package.path):
        raise PackageError(f'it was copied in another package ({copied_in}): what it points at, and its names, '
                           'are of that package')
    root, found = os.path.abspath(package.path), []
    for item in content['entities']:
        if not isinstance(item, dict) or not isinstance(item.get('document'), dict) \
                or not isinstance(item.get('from'), str):
            raise PackageError('what is pasted is not a copy of entities')
        name = _document_id(item['document'])
        if not name:
            raise PackageError('an entity without an id cannot be pasted')
        # As the package names its folders: one may be a link to elsewhere.
        source = os.path.normpath(os.path.join(root, item['from']))
        if os.path.isabs(item['from']) or os.path.commonpath([root, source]) != root:
            raise PackageError(f'{name} was not copied from a folder of this package')
        found.append((item['document'], source))
    return found


def paste_entities(package, content, case, replace=False, check=False, plan=None):
    """Write copied entities (`copy_entities`) into a test case's own file.

    An entity the case has -- by its IRI, however the two spell the id -- is
    replaced with `replace`, by the copied document with the id as that spells
    it, else left as it is. One in a file the case includes is always left:
    written twice, its values would add up, and changing it there would change
    other cases. `check` only asks; its `plan`, handed back, makes the write
    refuse when what was asked about is not what is there any more.

    Returns {'file', 'real', 'case', 'plan', 'pasted', 'present', 'included',
    'same', 'shared', 'spelled'}: the ids, as copied, that are (or would be)
    written, and those the case has otherwise, has in an included file, or has
    just like that; `shared` are the other cases that include this case's file,
    and get what is written as well; `spelled` is {id: how the case spells it}
    of those present; `real` is the file behind links.
    """
    import hashlib

    from ..expect.addcase import _moved_context
    from ..expect.store import examples_root, load_expectations

    target, example = _case_file(package, case)
    folder, real, ids = os.path.dirname(target), os.path.realpath(target), _Ids(package)
    if real in {os.path.realpath(p) for p in package.files('model')}:
        raise PackageError(f'{example.path} is a file of the main model, which a paste does not change')
    incoming = OrderedDict()
    for document, source in _checked_content(package, content):
        iri = ids.iri(document, source)
        if iri in incoming:
            raise PackageError(f'{_document_id(document)} is in the copy twice')
        incoming[iri] = _moved_context(document, source, folder)
    documents, text = _read(target)
    single = isinstance(json.loads(text), dict)
    own = {}
    for document in documents:
        own.setdefault(ids.iri(document, folder), []).append(document)
    # A case that is the same file, by a link, has what this one's file has.
    declared = [(e, os.path.realpath(os.path.join(examples_root(package.path), e.path)))
                for e in load_expectations(package.path).examples if e.path != example.path]
    twins = [e for e, path in declared if path == real]
    beside = [(d, os.path.dirname(path)) for path in _once(p for e in [example] + twins
                                                           for p in _included_files(package, e))
              if os.path.realpath(path) != real for d in _read(path)[0]]
    elsewhere = {ids.iri(d, source) for d, source in beside}
    same = [i for i in incoming if len(own.get(i, [])) == 1 and
            _same_document(_moved_context(own[i][0], folder, folder), incoming[i])]
    unchanged = set(same)
    present = [i for i in incoming if i in own and i not in unchanged]
    replaced = present if replace else []
    gone = set(replaced)
    included = [i for i in incoming if i not in own and i in elsewhere]
    fresh = [i for i in incoming if i not in own and i not in elsewhere]
    shared = [e.path for e, path in declared if path == real or
              real in {os.path.realpath(p) for p in _included_files(package, e)}]
    seen = hashlib.sha256(json.dumps([text, [d for d, _ in beside], shared, content]).encode('utf-8')).hexdigest()
    if plan is not None and plan != seen:
        raise PackageError(f'{example.path} was changed meanwhile, or a file it includes; paste again')
    if (fresh or replaced) and not check:
        done, kept = set(), []
        for document in documents:
            iri = ids.iri(document, folder)
            if iri not in gone:
                kept.append(document)
            elif iri not in done:                    # in its place, and once
                done.add(iri)
                kept.append(incoming[iri])
        kept += [incoming[i] for i in fresh]
        _write_whole(target, kept[0] if single and len(kept) == 1 else kept, text)

    def names(iris):
        return [_document_id(incoming[i]) for i in iris]
    return {'file': target, 'real': real, 'case': example.path, 'plan': seen, 'pasted': names(fresh + replaced),
            'present': names(present), 'included': names(included), 'same': names(same), 'shared': shared,
            'spelled': {_document_id(incoming[i]): _document_id(own[i][0]) for i in present
                        if _document_id(incoming[i]) != _document_id(own[i][0])}}


def flatten(nodes, depth=0):
    for node in nodes:
        yield depth, node
        yield from flatten(node.children, depth + 1)
