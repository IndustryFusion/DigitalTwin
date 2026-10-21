"""Deleting an attribute, and everything that would dangle without it.

An attribute is not one thing in one file. It is a declaration in the
knowledge, property shapes that constrain it (possibly nested inside other
attributes, possibly in several shapes), keys in every document that carries
it, asserts in the expectation files that name its constraints, and -- the hard
one -- the SPARQL bodies that read it.

Deleting only the declaration is the failure this module exists to prevent: the
shapes keep a `sh:path` the ontology no longer knows, the data keeps a key no
constraint judges, and nothing anywhere says so. So removal is planned first,
shown in full, and then done all at once or not at all.

What is removed, and what is not:

  * the declaration, each `sh:property` group whose path is the attribute
    (with whatever is nested inside it), the key in every model and example
    document, and every expectation assert naming one of those constraints --
    all mechanical, all verified before anything is written;
  * a SPARQL constraint or rule that mentions it, and any other ontology
    statement that does, are NOT. A query is not a list of parts: deleting it
    takes unrelated logic with it, and leaving it behind makes a rule that
    silently matches nothing. These BLOCK the removal until edited by hand.
"""

import json
import os
from dataclasses import dataclass, field

from rdflib import Graph, URIRef
from rdflib.namespace import SH

from ..errors import PackageError
from ..rdfio import TurtleIndex, property_blocks
from ..rdfio.turtle_index import _prefixes, _resolve
from ..validate.normalise import curie, local


@dataclass
class Dependent:
    kind: str           # declaration | constraint | data | expectation |
    #                     sparql | shapes | knowledge
    file: str
    line: int
    detail: str
    removable: bool = True


@dataclass
class RemovalPlan:
    iri: str
    label: str
    dependents: list = field(default_factory=list)

    @property
    def blocking(self):
        return [d for d in self.dependents if not d.removable]

    @property
    def in_use(self):
        """Anything beyond the declaration itself."""
        return any(d.kind != 'declaration' for d in self.dependents)

    def as_dict(self, root=''):
        def where(d):
            return os.path.relpath(d.file, root) if root else d.file
        return {'iri': self.iri, 'label': self.label, 'inUse': self.in_use,
                'dependents': [{'kind': d.kind, 'file': d.file,
                                'where': f'{where(d)}:{d.line}',
                                'line': d.line, 'detail': d.detail,
                                'removable': d.removable}
                               for d in self.dependents],
                'blocking': len(self.blocking)}


# --- which attribute ------------------------------------------------------------

def _resolve_attribute(package, attribute):
    """(IRI, label) for a term, IRI or local name; declared or merely used."""
    from .choices import attribute_terms
    from .constrain import _resolve as resolve_term

    wanted = str(attribute).strip()
    for entry in attribute_terms(package):
        if wanted in (entry.iri, entry.term, entry.label):
            return entry.iri, entry.label
    iri = resolve_term(package, wanted)
    if iri is None:
        raise PackageError(f'{attribute} is not a term this package can resolve')
    return str(iri), local(iri)


# --- the shapes -----------------------------------------------------------------

def _groups(text, statement):
    """Every sh:property group of a statement, with its parent (or None)."""
    def walk(groups, parent):
        for group in groups:
            yield group, parent
            yield from walk(group.children, group)
    yield from walk(property_blocks(text, statement), None)


def _shape_groups(package, iri):
    """{file: [(statement, group, parent)]} for groups whose path is `iri`.

    A group inside a group already being removed is not listed separately: it
    goes with its parent, and removing both would remove it twice.
    """
    found = {}
    for path in package.files('shapes'):
        if not os.path.isfile(path):
            continue
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
        prefixes, base = _prefixes(text)
        for statement in TurtleIndex(text).blocks:
            taken = []
            for group, parent in _groups(text, statement):
                if not group.path or _resolve(group.path, prefixes, base) != iri:
                    continue
                if any(t.start <= group.start < t.end for t in taken):
                    continue
                taken.append(group)
                found.setdefault(path, []).append((statement, group, parent))
    return found


def _shapes_losing(package, groups):
    """The CURIEs of the shapes a removal takes constraints from -- the form
    an expectation assert names them in."""
    return {curie(package.shapes, URIRef(statement.subject))
            for items in groups.values() for statement, _, _ in items}


def _remove_span(text, group, limit_start, limit_end):
    """Text with one `[ … ]` object of an sh:property removed, separators kept
    consistent. Refuses a layout it does not recognise rather than guess."""
    def back(i):
        while i > limit_start and text[i - 1].isspace():
            i -= 1
        return i

    def forward(i):
        while i < limit_end and text[i].isspace():
            i += 1
        return i

    before = back(group.start)
    after = forward(group.end)
    if text[before - 1] == ',':
        # A later object in `sh:property [A], [B]`: drop ", [B]".
        return text[:back(before - 1)] + text[group.end:]
    predicate = text.rfind('sh:property', limit_start, before)
    if predicate == -1 or text[predicate:before].strip() != 'sh:property':
        raise PackageError('a sh:property group is written in a way this '
                           'editor does not recognise; remove it by hand')
    if after < limit_end and text[after] == ',':
        # The first of several objects: drop "[A], " and keep the predicate.
        return text[:group.start] + text[forward(after + 1):]
    if after < limit_end and text[after] == ';':
        # A middle predicate: drop "sh:property [A] ;" and the space after it.
        return text[:predicate] + text[forward(after + 1):]
    # The last predicate before '.' or ']': drop the ';' that led to it.
    lead = back(predicate)
    if text[lead - 1] == ';':
        return text[:lead - 1] + text[group.end:]
    return text[:predicate] + text[group.end:]


def _shapes_without(path, groups, iri):
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    # Last first, so earlier spans stay valid.
    for statement, group, parent in sorted(groups, key=lambda g: -g[1].start):
        start, end = (parent.start + 1, parent.end - 1) if parent else \
            (statement.start, statement.end)
        text = _remove_span(text, group, start, end)
    graph = Graph().parse(data=text, format='turtle')
    if (None, SH.path, URIRef(iri)) in graph:
        raise PackageError(f'{os.path.basename(path)} still constrains '
                           f'{local(iri)} after the edit; nothing was written')
    return text


# --- the knowledge --------------------------------------------------------------

def _knowledge_without(path, iri):
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    statement = TurtleIndex(text).block_for(iri)
    if statement is None:
        return None
    start, end = statement.start, statement.end
    # Take the statement's lines with it, and one of the blank lines around it,
    # so no hole is left -- declaring and then deleting is byte-identical.
    line_start = text.rfind('\n', 0, start) + 1
    if text[line_start:start].strip() == '':
        start = line_start
    while end < len(text) and text[end] in ' \t':
        end += 1
    if text[end:end + 1] == '\n':
        end += 1
    if text[start - 2:start] == '\n\n' and (end >= len(text) or text[end] == '\n'):
        start -= 1
    updated = text[:start] + text[end:]
    graph = Graph().parse(data=updated, format='turtle')
    if (URIRef(iri), None, None) in graph:
        raise PackageError(f'{local(iri)} is still declared in '
                           f'{os.path.basename(path)} after the edit')
    return updated


# --- the data -------------------------------------------------------------------

def _strip_keys(node, expand, iri, removed, entity=''):
    if isinstance(node, list):
        for item in node:
            _strip_keys(item, expand, iri, removed, entity)
        return
    if not isinstance(node, dict):
        return
    entity = str(node.get('id') or node.get('@id') or entity)
    for key in list(node):
        if key == '@context':
            continue
        if expand(key) == iri:
            del node[key]
            removed.append(entity)
            continue
        _strip_keys(node[key], expand, iri, removed, entity)


# --- the plan -------------------------------------------------------------------

def plan_attribute_removal(package, attribute):
    """Everything deleting this attribute would touch. Writes nothing."""
    from ..editor.references import references_to
    from ..expect.store import load_expectations

    iri, label = _resolve_attribute(package, attribute)
    plan = RemovalPlan(iri=iri, label=label)

    knowledge_files = {os.path.abspath(p) for p in package.files('knowledge')}
    shapes_files = {os.path.abspath(p) for p in package.files('shapes')}
    groups = _shape_groups(package, iri)
    # {file: [(start, end)]} of the groups going, so a use inside one is
    # recognised as leaving with it rather than reported on its own.
    spans = {os.path.abspath(path): [(g.start, g.end) for _, g, _ in items]
             for path, items in groups.items()}

    for path, items in groups.items():
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
        for statement, group, parent in items:
            shape = curie(package.shapes, URIRef(statement.subject))
            nested = len(group.children)
            where = f'inside {parent.path}' if parent else 'on the entity'
            plan.dependents.append(Dependent(
                kind='constraint', file=os.path.abspath(path),
                line=text.count('\n', 0, group.start) + 1,
                detail=f'{shape}: the property shape {where}'
                       + (f', with {nested} nested constraint(s)' if nested else '')))

    removed_shapes = _shapes_losing(package, groups)

    references = references_to(package, {iri})
    # Where each data key sits, per file in document order -- the same order
    # _strip_keys meets them in, so the two can be paired below.
    key_lines = {}
    for reference in references:
        if reference.path.endswith(('.jsonld', '.json')):
            key_lines.setdefault(os.path.abspath(reference.path), []).append(
                reference.line)

    for reference in references:
        path = os.path.abspath(reference.path)
        if path in knowledge_files:
            if reference.declaration:
                plan.dependents.append(Dependent(
                    kind='declaration', file=path, line=reference.line,
                    detail=f'the declaration of {label}'))
            else:
                plan.dependents.append(Dependent(
                    kind='knowledge', file=path, line=reference.line,
                    detail='another ontology statement names it -- edit it by hand',
                    removable=False))
        elif path in shapes_files:
            with open(path, encoding='utf-8') as handle:
                text = handle.read()
            offset = sum(len(line) + 1 for line in
                         text.split('\n')[:reference.line - 1]) + reference.column
            if any(start <= offset < end for start, end in spans.get(path, [])):
                continue                      # leaves with its group, above
            owner = next((b for b in TurtleIndex(text).blocks
                          if b.start <= offset < b.end), None)
            shape = curie(package.shapes, URIRef(owner.subject)) if owner else ''
            if reference.quoted:
                detail = (f'{shape}: a SPARQL body reads it -- a query cannot '
                          f'be cut apart safely; edit or remove it by hand')
            else:
                detail = (f'{shape}: names it outside a property shape -- '
                          f'edit it by hand')
            plan.dependents.append(Dependent(
                kind='sparql' if reference.quoted else 'shapes', file=path,
                line=reference.line, detail=detail, removable=False))

    from ..editor.references import _Expander
    from .knowledge import example_files
    expander = _Expander(package)
    for path in example_files(package):
        expand = expander.for_file(path)
        if expand is None:
            continue
        try:
            with open(path, encoding='utf-8') as handle:
                document = json.load(handle)
        except Exception:                          # noqa: BLE001
            continue
        removed = []
        _strip_keys(document, expand, iri, removed)
        lines = key_lines.get(os.path.abspath(path), [])
        if len(lines) != len(removed):
            lines = [1] * len(removed)        # a key spelled as an IRI value too
        for entity, line in zip(removed, lines):
            plan.dependents.append(Dependent(
                kind='data', file=os.path.abspath(path), line=line,
                detail=f'{entity} carries it'))

    try:
        expectations = load_expectations(package.path)
    except Exception:                              # noqa: BLE001
        expectations = None
    for example in (expectations.examples if expectations else []):
        for item in example.asserts:
            shape, _, rest = str(item.get('constraint', '')).partition('/')
            attribute_name = rest.split('/')[0]
            if attribute_name == label and shape in removed_shapes:
                plan.dependents.append(Dependent(
                    kind='expectation', file=example.source, line=1,
                    detail=f'{example.path} asserts {item.get("constraint")}'))
    return plan


# --- the removal ----------------------------------------------------------------

def remove_declaration(package, attribute, force=False):
    """Delete only the declaration; every use stays where it is.

    The author's call, and a legitimate one -- the term may be moving to
    another ontology, or the uses are about to be rewritten by hand. What it
    leaves is visible, not silent: the editor reports each remaining use as
    naming an undeclared term. `force` is the yes to doing it while in use.
    Returns (plan, notes), the notes naming what now points at nothing.
    """
    plan = plan_attribute_removal(package, attribute)
    declared = [d for d in plan.dependents if d.kind == 'declaration']
    if not declared:
        raise PackageError(f'{plan.label} is not declared in any knowledge '
                           f'file, so there is no declaration to remove')
    left = [d for d in plan.dependents if d.kind != 'declaration']
    if left and not force:
        raise PackageError(f'{plan.label} is in use ({len(left)} use(s) would '
                           f'name an undeclared term); confirm to remove the '
                           f'declaration anyway')
    writes = {}
    for path in package.files('knowledge'):
        updated = _knowledge_without(path, plan.iri)
        if updated is not None:
            writes[path] = updated
    for path, text in writes.items():
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
    notes = []
    if left:
        notes.append(f'{len(left)} use(s) of {plan.label} remain and now name '
                     f'an undeclared term; the Problems panel lists them until '
                     f'it is declared again or they are removed')
    return plan, notes


def remove_attribute(package, attribute, force=False):
    """Delete the attribute and every removable dependent, all or nothing.

    Refuses while anything blocks (SPARQL, other ontology statements). Refuses
    an attribute in use unless `force` -- the caller has shown the plan and the
    author said yes. Returns the plan that was carried out, plus a `notes` list
    of things to look at afterwards. `remove_declaration` is the other choice:
    the declaration alone, every use left in place.
    """
    from ..editor.references import _Expander
    from ..expect.store import _yaml, load_expectations
    from .examples import _write
    from .knowledge import example_files

    plan = plan_attribute_removal(package, attribute)
    if plan.blocking:
        raise PackageError(
            f'{plan.label} cannot be removed yet: '
            + '; '.join(f'{os.path.basename(d.file)}:{d.line} {d.detail}'
                        for d in plan.blocking))
    if plan.in_use and not force:
        raise PackageError(f'{plan.label} is in use '
                           f'({len(plan.dependents) - 1} dependent(s)); '
                           f'confirm to remove them too')
    iri = plan.iri

    writes = {}                                   # path -> new text
    for path, groups in _shape_groups(package, iri).items():
        writes[path] = _shapes_without(path, groups, iri)
    for path in package.files('knowledge'):
        updated = _knowledge_without(path, iri)
        if updated is not None:
            writes[path] = updated

    documents = {}
    expander = _Expander(package)
    for path in example_files(package):
        expand = expander.for_file(path)
        if expand is None:
            continue
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
        document = json.loads(text)
        removed = []
        _strip_keys(document, expand, iri, removed)
        if removed:
            documents[path] = (document, text)

    notes = []
    yaml_writes = {}
    # The same set the plan used, computed the same way: recovering it from
    # the plan's prose split `iffBaseShacl:WorkpieceShape` at its own colon.
    removed_shapes = _shapes_losing(package, _shape_groups(package, iri))
    expectations = load_expectations(package.path)
    for source, raw in (expectations.raw or {}).items():
        changed = False
        for entry in raw.get('examples') or []:
            asserts = entry.get('asserts') or []
            keep = []
            for item in asserts:
                shape, _, rest = str(item.get('constraint', '')).partition('/')
                if rest.split('/')[0] == plan.label and shape in removed_shapes:
                    changed = True
                    continue
                keep.append(item)
            if len(keep) != len(asserts):
                if keep:
                    entry['asserts'] = keep
                else:
                    del entry['asserts']
                    if entry.get('expect') == 'invalid':
                        notes.append(f'{entry.get("path")} expects a violation '
                                     f'but no longer asserts one -- give it a '
                                     f'new assert, or remove the case')
                if entry.get('residue'):
                    notes.append(f'{entry.get("path")}: its residue changed; '
                                 f're-run `semforge test` and accept it')
        if changed:
            yaml_writes[source] = raw

    # Everything is computed and verified; only now does anything change.
    for path, text in writes.items():
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
    for path, (document, text) in documents.items():
        _write(path, document, text)
    for source, raw in yaml_writes.items():
        with open(source, 'w') as handle:
            _yaml().dump(raw, handle)

    return plan, notes
