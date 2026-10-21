"""Merge into…: fold one shape into another with the same targets.

Two shapes on the same nodes are conjoined by SHACL, so folding one into the
other changes nothing a validator decides -- it only puts the constraints in
one place. That holds only when they select the same nodes; otherwise the
moved constraints would start judging nodes they never judged, and the merge
is refused. Refused too: a shape another reaches through sh:node (that
reference would dangle) and one with shape-level settings beyond its
targets, constraints and labels (severity, data view, ...).

Where both constrain the same attribute with plain parameters, the blocks are
combined the way SHACL combines them: the higher minimum and lower maximum
count, the tighter bound; two different datatypes or classes both stay (the
value must satisfy both, as before). Anything else -- sub-attributes, sh:or
-- is moved as it is written. SPARQL constraints and rules move verbatim.
Test-case asserts naming the merged shape are renamed to the shape it went
into, and the result is checked: every constraint either shape declared is
declared by the one that is left.
"""

import os
import re

from rdflib import URIRef
from rdflib.namespace import RDF, RDFS, SH

from ..errors import PackageError
from ..rdfio import TurtleIndex, property_blocks
from ..validate.normalise import curie
from .tree import EDITABLE, SLOTS

ALLOWED = {RDF.type, SH.targetClass, SH.targetNode, SH.targetSubjectsOf,
           SH.targetObjectsOf, SH.target, SH.property, SH.sparql, SH.rule,
           RDFS.comment, RDFS.label}
PLAIN = set(EDITABLE) | {'sh:nodeKind', 'sh:order', 'sh:name', 'sh:description'}
LOWER = ('sh:minInclusive', 'sh:minExclusive')
UPPER = ('sh:maxInclusive', 'sh:maxExclusive')
ONE_OF = ('sh:datatype', 'sh:class', 'sh:nodeKind', 'sh:pattern')


def _number(text):
    try:
        return float(str(text).split('^^')[0].strip('"'))
    except ValueError:
        return None


def candidates(package, shape):
    """The shapes `shape` may be merged into: same targets, not itself."""
    from ..validate.shapes import every_node_shape
    from .shapes import targets

    shape = URIRef(str(shape).strip('<>'))
    mine = {(t['kind'], t['value']) for t in targets(package, shape)}
    out = []
    for other in every_node_shape(package.shapes):
        if other == shape:
            continue
        theirs = {(t['kind'], t['value']) for t in targets(package, other)}
        if mine and theirs == mine:
            out.append({'iri': str(other), 'name': curie(package.shapes, other)})
    return out


def _statement(package, shape):
    index = package.index('shapes')
    path = index.file_for(URIRef(shape))
    if path is None:
        raise PackageError(f'{shape} is not a statement in any shapes file')
    with open(path, encoding='utf-8') as handle:
        return path, handle.read()


def _block(text, shape):
    block = TurtleIndex(text).block_for(str(shape))
    if block is None:
        raise PackageError(f'{shape} is not in the file any more')
    return block


def _plain(group):
    if set(group.parameters) - PLAIN:
        return False
    for child in group.children:
        if child.path not in SLOTS or child.children or set(child.parameters) - PLAIN:
            return False
    return True


def _verbatim_bodies(text, block, predicate):
    """The `[ … ]` objects of sh:sparql / sh:rule in a statement, as written."""
    from ..rdfio.blocks import _match_bracket

    out = []
    for match in re.finditer(rf'(?<![\w:]){re.escape(predicate)}\s*\[', text[block.start:block.end]):
        start = block.start + match.end() - 1
        end = _match_bracket(text, start, block.end)
        out.append(text[start:end])
    return out


def _stricter(name, mine, theirs):
    """Is `name mine` stricter than every bound in `theirs` ({name: value})?"""
    lower = name in LOWER or name == 'sh:minCount'
    value = _number(mine)
    for other_name, other in theirs.items():
        number = _number(other)
        if number is None or value is None:
            return False
        exclusive, other_exclusive = name.endswith('Exclusive'), other_name.endswith('Exclusive')
        if lower and (value < number or (value == number and not (exclusive and not other_exclusive))):
            return False
        if not lower and (value > number or (value == number and not (exclusive and not other_exclusive))):
            return False
    return True


def _plan_group(source_group, target_group, source_text):
    """[(layer, slot, op, name, value)] that fold source into target's block,
    and the words for each."""
    ops, said = [], []
    layers = [('attribute', None, source_group, target_group)]
    for child in source_group.children:
        mate = next((c for c in target_group.children if c.path == child.path), None)
        if mate is None:
            ops.append(('attribute', None, 'add', 'sh:property', None,
                        source_text[child.start:child.end]))
            said.append(f'its {child.path} layer moves over')
            continue
        layers.append(('value', child.path, child, mate))
    for layer, slot, mine, theirs in layers:
        have = {k: v[2] for k, v in theirs.parameters.items()}
        for name, (_, _, value) in mine.parameters.items():
            if name in ('sh:order', 'sh:name', 'sh:description'):
                continue
            where = 'on the value' if layer == 'value' else 'on the attribute'
            if name in ('sh:minCount', 'sh:maxCount') or name in LOWER or name in UPPER:
                family = (('sh:minCount',) if name == 'sh:minCount' else
                          ('sh:maxCount',) if name == 'sh:maxCount' else
                          LOWER if name in LOWER else UPPER)
                current = {n: have[n] for n in family if n in have}
                if not current:
                    ops.append((layer, slot, 'add', name, value, None))
                    said.append(f'{name} {value} {where} added')
                elif _stricter(name, value, current):
                    # The same parameter changes in place; a different one
                    # (an exclusive bound for an inclusive) replaces it.
                    for old in current:
                        if old != name:
                            ops.append((layer, slot, 'remove', old, None, None))
                    ops.append((layer, slot, 'set' if name in current else 'add',
                                name, value, None))
                    said.append(f'{name} {value} {where} replaces the weaker '
                                + ', '.join(f'{n} {v}' for n, v in current.items()))
                elif _number(current.get(name, '')) == _number(value):
                    said.append(f'{name} {value} {where}: already there')
                else:
                    said.append(f'{name} {value} {where}: no effect, dropped')
            elif name in ONE_OF:
                if have.get(name) == value:
                    continue
                ops.append((layer, slot, 'add', name, value, None))
                said.append(f'{name} {value} {where} added' +
                            (f' beside {have[name]}: both must hold' if name in have else ''))
            else:
                if have.get(name) != value:
                    ops.append((layer, slot, 'add', name, value, None))
                    said.append(f'{name} {value} {where} added')
    return ops, said


def plan(package, source, into):
    """What merging `source` into `into` would do -- or why it cannot."""
    from ..validate.shapes import every_node_shape
    from .shapes import targets

    graph = package.shapes
    source, into = URIRef(str(source).strip('<>')), URIRef(str(into).strip('<>'))
    shapes = set(every_node_shape(graph))
    for shape in (source, into):
        if shape not in shapes:
            raise PackageError(f'{shape} is not a shape in this package')
    if source == into:
        raise PackageError('a shape cannot be merged into itself')
    name, into_name = curie(graph, source), curie(graph, into)
    mine = {(t['kind'], t['value']) for t in targets(package, source)}
    theirs = {(t['kind'], t['value']) for t in targets(package, into)}
    if mine != theirs:
        raise PackageError(f'{name} and {into_name} select different nodes; merged, '
                           f'its constraints would judge nodes they never judged')
    if any(True for _ in graph.subjects(SH.node, source)):
        raise PackageError(f'another shape reaches {name} through sh:node; that '
                           f'reference would point at nothing')
    extra = sorted({curie(graph, p) for p in graph.predicates(source, None)} -
                   {curie(graph, p) for p in ALLOWED})
    if extra:
        raise PackageError(f'{name} sets {", ".join(extra)} on the shape itself; merge '
                           f'it by hand, deciding what {into_name} should say')

    source_path, source_text = _statement(package, source)
    target_path, target_text = _statement(package, into)
    source_block = _block(source_text, source)
    target_block = _block(target_text, into)
    target_groups = {g.path: g for g in property_blocks(target_text, target_block)}
    steps, words = [], []
    for group in property_blocks(source_text, source_block):
        mate = target_groups.get(group.path)
        if mate is not None and _plain(group) and _plain(mate):
            ops, said = _plan_group(group, mate, source_text)
            steps.append(('combine', group.path, ops))
            words += [f'{group.path}: {s}' for s in said] or \
                [f'{group.path}: nothing new, {into_name} already says it all']
        else:
            steps.append(('move', group.path, source_text[group.start:group.end]))
            words.append(f'{group.path}: moved as written' +
                         (' (beside its own block: both apply)' if mate is not None else ''))
    for predicate in ('sh:sparql', 'sh:rule'):
        for body in _verbatim_bodies(source_text, source_block, predicate):
            steps.append(('append', predicate, body))
            words.append(f'a {predicate[3:]} block moves over')
    asserts = _asserts_naming(package, name)
    return {'source': str(source), 'into': str(into), 'name': name, 'intoName': into_name,
            'steps': steps, 'said': words, 'asserts': len(asserts),
            'files': sorted({source_path, target_path})}


def _asserts_naming(package, name):
    from ..expect.store import load_expectations

    found = []
    for example in load_expectations(package.path).examples:
        for item in example.asserts:
            if str(item.get('constraint', '')).startswith(name + '/'):
                found.append((example, item))
    return found


def _find(text, shape, path, slot):
    groups = property_blocks(text, _block(text, shape))
    group = next(g for g in groups if g.path == path)
    return group if slot is None else next(c for c in group.children if c.path == slot)


def _apply(text, into, steps):
    from ..rdfio import set_parameter
    from .constrain import _add_line, _remove_line

    for kind, path, payload in steps:
        if kind == 'combine':
            for layer, slot, op, name, value, child in payload:
                target = _find(text, into, path, slot)
                if op == 'remove':
                    text = _remove_line(text, target, name)
                elif op == 'set':
                    text = set_parameter(text, target, name, value)
                elif child is not None:
                    text = _add_line(text, target, 'sh:property', child)
                else:
                    text = _add_line(text, target, name, value)
        else:
            block = _block(text, into)
            statement = block.text(text).rstrip()
            predicate = 'sh:property' if kind == 'move' else path
            statement = statement[:-1].rstrip() + f' ;\n    {predicate} {payload} .'
            text = text[:block.start] + statement + text[block.end:]
    return text


def merge_shape(package, source, into):
    """Fold `source` into `into`, delete `source`, rename asserts.

    Returns {'into', 'said', 'asserts', 'notes'}."""
    from rdflib import Graph

    from ..validate.applicable import constraints_of_shape

    steps = plan(package, source, into)
    source, into = URIRef(steps['source']), URIRef(steps['into'])
    source_path, source_text = _statement(package, source)
    target_path, target_text = _statement(package, into)

    before = set(constraints_of_shape(source, package.shapes)) | \
        set(constraints_of_shape(into, package.shapes))
    merged = _apply(target_text, into, steps['steps'])
    writes = {target_path: merged}
    remaining = merged if source_path == target_path else source_text
    without = _knowledge_without_text(remaining, source)
    writes[source_path] = without

    graph = Graph()
    for path in package.files('shapes'):
        text = writes.get(path, None)
        if text is None:
            with open(path, encoding='utf-8') as handle:
                text = handle.read()
        graph.parse(data=text, format='turtle')
    if (source, None, None) in graph:
        raise PackageError(f'{steps["name"]} is still there after the merge; nothing written')
    after = set(constraints_of_shape(into, graph))
    lost = before - after
    if lost:
        raise PackageError('the merge would lose ' + ', '.join(f'{a}/{c}' for a, c in sorted(lost))
                           + '; nothing written')
    for path, text in writes.items():
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)

    renamed, notes = _rename_asserts(package, steps['name'], steps['intoName'])
    return {'into': str(into), 'intoName': steps['intoName'], 'said': steps['said'],
            'asserts': renamed, 'notes': notes}


def _knowledge_without_text(text, shape):
    """`text` without the shape's statement and one of the blank lines around it."""
    block = _block(text, shape)
    start, end = block.start, block.end
    line_start = text.rfind('\n', 0, start) + 1
    if text[line_start:start].strip() == '':
        start = line_start
    while end < len(text) and text[end] in ' \t':
        end += 1
    if text[end:end + 1] == '\n':
        end += 1
    if text[start - 2:start] == '\n\n' and (end >= len(text) or text[end] == '\n'):
        start -= 1
    return text[:start] + text[end:]


def _rename_asserts(package, name, into_name):
    from ..expect.store import _yaml, expectation_files

    renamed, notes = 0, []
    for path in expectation_files(package.path):
        with open(path, encoding='utf-8') as handle:
            raw = _yaml().load(handle) or {}
        changed = False
        for entry in raw.get('examples') or []:
            for item in entry.get('asserts') or []:
                constraint = str(item.get('constraint', ''))
                if constraint.startswith(name + '/'):
                    item['constraint'] = into_name + constraint[len(name):]
                    renamed += 1
                    changed = True
                    if entry.get('residue'):
                        notes.append(f'{os.path.basename(path)}: {entry.get("path")} pins a '
                                     f'residue; run `semforge accept` to pin it again')
        if changed:
            with open(path, 'w', encoding='utf-8') as handle:
                _yaml().dump(raw, handle)
    return renamed, sorted(set(notes))
