"""Adding an attribute to a shape: the constraint, both layers, at once.

The one way an attribute reached a shape before was a side effect -- "go to
the rule" on an attribute with none wrote a bare `sh:path` stub, which the
capability check then reports as compiling to nothing. That is right for a
jump, which must not decide anything, and wrong for an author who has said
"this type has this attribute": they have decided, and the shape should say so.

What gets written is the NGSI-LD two-layer encoding the scaffold teaches:

    sh:property [ sh:path ex:hasState ;            the attribute is there,
        sh:minCount 1 ; sh:maxCount 1 ;            once,
        sh:nodeKind sh:BlankNode ;                 as an attribute node,
        sh:property [ sh:path ngsild:hasValue ;    and its value is there,
            sh:minCount 1 ; sh:maxCount 1 ;        once,
            sh:nodeKind sh:IRI ;                   and is what was asked for
            sh:class ex:MachineState ] ]

The kind decides the inner path -- a Relationship's payload is `hasObject`, a
Property's `hasValue` -- and is read from the knowledge, never asked: that is
what the knowledge's `rdfs:range` is for. What the value must BE is asked,
because the knowledge deliberately does not say: `sh:class` is the shapes'
business (see choices.nesting).

The refusals are the point as much as the write:

  * an undeclared attribute -- declare it in the knowledge first, or nothing
    else (pickers, references, the Knowledge view) will ever know of it;
  * one the knowledge gives to another type -- the shape would demand it of
    entities that never carry it, and every one of them would fail;
  * a sub-attribute -- it hangs off an attribute node, not off the entity;
  * one already constrained here -- edit it instead;
  * one constrained by a supertype's shape -- SHACL conjoins, so a second
    declaration is an override, and that has its own command, which says
    whether the change tightens or can never take effect.
"""

import os

from rdflib import URIRef
from rdflib.namespace import SH, XSD

from ..errors import PackageError
from ..rdfio import property_blocks
from ..validate.normalise import curie, local
from .choices import _ancestor_chain, attribute_terms, classify_classes

# The kind decides where the payload hangs, exactly as ngsild.build's
# PAYLOAD_KEY decides the JSON key.
from ..ngsild.kinds import PAYLOAD_PATH  # noqa: E402


def _attribute(package, attribute):
    wanted = str(attribute)
    for entry in attribute_terms(package):
        if wanted in (entry.iri, entry.term, entry.label):
            return entry
    raise PackageError(
        f'{attribute} is not declared in the knowledge. Declare it there '
        f'first: an attribute only the shapes know of is one no picker '
        f'offers and no example is checked against.')


def _shape_targets(package, shape):
    from ..validate.shapes import class_targets

    return class_targets(package.shapes, shape)


def _family(package, classes):
    found = set()
    for cls in classes:
        found.update(str(c) for c in _ancestor_chain(package.knowledge, cls))
    return found


def _constrained_paths(package, shape):
    """The attribute IRIs a shape's own top-level sh:property groups name."""
    return {str(path)
            for group in package.shapes.objects(URIRef(shape), SH.property)
            for path in package.shapes.objects(group, SH.path)
            if isinstance(path, URIRef)}


def _inherited_constraints(package, shape):
    """{attribute IRI: the supertype shape that constrains it}."""
    from ..validate.shapes import node_shapes

    own = set(_shape_targets(package, shape))
    above = _family(package, own) - {str(t) for t in own}
    found = {}
    for other in node_shapes(package.shapes):
        if str(other) == str(shape):
            continue
        targets = {str(t) for t in _shape_targets(package, other)}
        if targets & above:
            for path in _constrained_paths(package, other):
                found.setdefault(path, str(other))
    return found


def own_shape(package, entity_type):
    """The node shape that targets this type itself, or None.

    Its OWN shape, not the nearest one: a new attribute of Filter belongs in
    FilterShape, and writing it into MachineShape because Filter inherits from
    Machine would demand it of every Cutter too. When a type has several shapes
    of its own -- a structural one and SPARQL rule shapes, say -- the one that
    already carries sh:property groups is the one attributes go in.
    """
    from ..validate.shapes import node_shapes
    from .choices import entity_types

    wanted = str(entity_type or '').strip('<>')
    if not wanted:
        return None
    # The type as the knowledge declares it -- term, IRI or local name -- so
    # the comparison is on IRIs and two namespaces' `Filter` stay two.
    iri = next((entry.iri for entry in entity_types(package)[0]
                if wanted in (entry.iri, entry.term, entry.label)), wanted)
    candidates = [shape for shape in node_shapes(package.shapes)
                  if iri in {str(t) for t in _shape_targets(package, shape)}]
    if not candidates:
        return None
    candidates.sort(key=lambda s: (-len(list(package.shapes.objects(s, SH.property))),
                                   str(s)))
    return str(candidates[0])


def attribute_options(package, shape):
    """What the add-attribute picker offers for this shape, and in what state.

    Every attribute the knowledge gives to the shape's target type or one of
    its supertypes, then the ones it gives to nobody (a package may simply not
    have said). Each says whether it can be added:

      * free       -- not constrained here or above
      * elsewhere  -- the knowledge gives it to other types only; adding it
                      here gives it to this type too (its domain becomes the
                      union), so the picker asks first
      * here       -- this shape already constrains it; edit it instead
      * inherited  -- a supertype's shape does; override it instead
    """
    targets = _shape_targets(package, shape)
    # A shape without a class target (sh:targetNode, a SPARQL target, one
    # used through sh:node) belongs to no type: every attribute may go on it,
    # and nothing above it can already constrain one.
    family = _family(package, targets) if targets else None
    here = _constrained_paths(package, shape)
    above = _inherited_constraints(package, shape) if targets else {}

    out = []
    for entry in attribute_terms(package):
        if not entry.ngsild or entry.parents or entry.carrier_kind:
            continue
        status, by = 'free', ''
        if family is not None and entry.domain_iris and \
                not set(entry.domain_iris) & family:
            status, by = 'elsewhere', ', '.join(local(d) for d in entry.domain_iris)
        if entry.iri in here:
            status = 'here'
        elif entry.iri in above:
            status, by = 'inherited', curie(package.shapes, above[entry.iri])
        out.append({'iri': entry.iri, 'term': entry.term,
                    'label': entry.label, 'kind': entry.kind or 'Property',
                    'comment': entry.comment, 'domain': entry.domain,
                    'scoped': bool(entry.domain_iris), 'status': status,
                    'by': by})
    order = {'free': 0, 'elsewhere': 1}
    out.sort(key=lambda o: (order.get(o['status'], 2), not o['scoped'],
                            o['label'].lower()))
    return out


def _resolve(package, term):
    """A term from a picker (CURIE or IRI) as an IRI, or None."""
    if not term:
        return None
    text = str(term).strip().strip('<>')
    if '://' in text or text.startswith('urn:'):
        return URIRef(text)
    prefix, _, name = text.partition(':')
    for bound, namespace in package.shapes.namespaces():
        if bound == prefix:
            return URIRef(str(namespace) + name)
    from ..package.prefixes import canonical_map
    namespace = canonical_map(package.path).get(prefix)
    return URIRef(namespace + name) if namespace else None


def _value_layer(package, kind, datatype, value_class, name):
    """The inner layer's parameters, minus its sh:path, as (name, IRI) pairs."""
    pairs = [(SH.minCount, 1), (SH.maxCount, 1)]
    entities, vocabularies, _ = classify_classes(package)
    if kind == 'Relationship':
        if datatype:
            raise PackageError(f'{name} is a Relationship: its value is an '
                               f'entity, which has no datatype')
        pairs.append((SH.nodeKind, SH.IRI))
        if value_class:
            cls = _resolve(package, value_class)
            if cls not in entities:
                raise PackageError(
                    f'{value_class} is not an entity type, so no entity can '
                    f'be one -- a Relationship to it could never be satisfied')
            pairs.append((SH['class'], cls))
        return pairs

    if value_class and datatype:
        raise PackageError('a value is either a vocabulary term (a class) or '
                           'a literal (a datatype), not both')
    if value_class:
        if kind != 'Property':
            raise PackageError(f'a {kind} does not carry a vocabulary term')
        cls = _resolve(package, value_class)
        if cls in entities:
            raise PackageError(
                f'{value_class} is an entity type; pointing at an entity is '
                f'what a Relationship is for. Declare {name} with rdfs:range '
                f'ngsild:Relationship instead.')
        if cls not in vocabularies:
            raise PackageError(f'{value_class} is not a class the knowledge '
                               f'declares')
        # The value IS one of the vocabulary's individuals, so it arrives as an
        # IRI: {"@id": ...}. The nodeKind makes a string that merely spells the
        # name a violation that says so, rather than an sh:class failure that
        # reads as the wrong individual.
        pairs += [(SH.nodeKind, SH.IRI), (SH['class'], cls)]
    elif datatype:
        iri = _resolve(package, datatype)
        if iri is None or not str(iri).startswith(str(XSD)):
            raise PackageError(f'{datatype} is not an XML Schema datatype')
        pairs.append((SH.datatype, iri))
    return pairs


def add_attribute_constraint(package, shape, attribute, required=False,
                             datatype=None, value_class=None, extend_domain=False):
    """Add `attribute` to `shape` as a complete two-layer property shape.

    Returns {'file', 'line', 'shape', 'attribute', 'kind', 'domainAdded'}. The
    write is a text insertion into the shape's own statement, verified to
    parse before the file is replaced, so every comment around and inside the
    shape survives.

    An attribute the knowledge gives only to other types is refused -- unless
    `extend_domain`, which first gives it to the shape's target types too
    (knowledge.extend_domain: its rdfs:domain becomes the union). If the
    shape cannot then take it, the knowledge is put back as it was.
    """

    shape = str(shape)
    index = package.index('shapes')
    holder = index.file_for(URIRef(shape))
    if holder is None:
        raise PackageError(f'{shape} is not a statement in any shapes file')

    entry = _attribute(package, attribute)
    name = entry.label
    if entry.parents or entry.carrier_kind:
        raise PackageError(
            f'{name} is a sub-attribute: it hangs off an attribute node, not '
            f'off the entity, so it belongs inside the attribute that carries '
            f'it rather than on the shape')
    targets = _shape_targets(package, shape)
    # Only a class-targeted shape has a type for the domain to disagree with.
    elsewhere = bool(targets and entry.domain_iris and
                     not set(entry.domain_iris) & _family(package, targets))
    if elsewhere and not extend_domain:
        raise PackageError(
            f'the knowledge gives {name} to '
            f'{" or ".join(local(d) for d in entry.domain_iris)}, not to '
            f'{", ".join(local(t) for t in targets)}. Add it with its domain extended '
            f'to give it to {", ".join(local(t) for t in targets)} as well.')
    if entry.iri in _constrained_paths(package, shape):
        raise PackageError(f'{curie(package.shapes, shape)} already constrains '
                           f'{name}; edit that constraint instead')
    above = _inherited_constraints(package, shape)
    if entry.iri in above:
        raise PackageError(
            f'{curie(package.shapes, above[entry.iri])} already constrains '
            f'{name} for this type. SHACL conjoins, so declaring it again here '
            f'can only tighten it -- use "Declare on This Type" on the '
            f'inherited constraint, which says whether a change takes effect.')

    kind = entry.kind or 'Property'
    inner = _value_layer(package, kind, datatype, value_class, name)

    # The knowledge first: it may be the very file the shape is in.
    added, restore = [], None
    if elsewhere:
        from .knowledge import extend_domain
        kpath = package.index('knowledge').file_for(URIRef(entry.iri))
        with open(kpath, encoding='utf-8') as handle:
            restore = (kpath, handle.read())
        added = extend_domain(package, entry.iri, targets)['added']
    try:
        return _add_to_shape(package, holder, shape, entry, kind, inner, required,
                             added)
    except Exception:
        if restore is not None:
            with open(restore[0], 'w', encoding='utf-8') as handle:
                handle.write(restore[1])
        raise


def _add_to_shape(package, holder, shape, entry, kind, inner, required, added):
    from .knowledge import _turtle_name
    from .tree import _write_verified
    from ..rdfio import add_property_constraint

    with open(holder, encoding='utf-8') as handle:
        text = handle.read()

    def term(node):
        if isinstance(node, int):
            return str(node)
        return _turtle_name(text, node)

    value_pairs = [(term(SH.path), term(URIRef(PAYLOAD_PATH[kind])))] + \
        [(term(p), term(v)) for p, v in inner]
    outer = [(term(SH.minCount), '1' if required else '0'),
             (term(SH.maxCount), '1'),
             (term(SH.nodeKind), term(SH.BlankNode)),
             (term(SH.property), value_pairs)]
    updated = add_property_constraint(
        holder, shape, term(URIRef(entry.iri)), outer, source=text)
    _write_verified(holder, updated)

    from ..rdfio import TurtleIndex
    block = TurtleIndex(updated).block_for(shape)
    line = None
    for group in property_blocks(updated, block):
        if group.path in (term(URIRef(entry.iri)), f'<{entry.iri}>'):
            line = updated.count('\n', 0, group.start) + 1
    return {'file': holder, 'line': line, 'shape': shape,
            'attribute': entry.iri, 'kind': kind,
            'domainAdded': [curie(package.knowledge, URIRef(c)) for c in added]}


def shape_targets(package, shape):
    """The target classes of a shape, as terms the model would write."""
    from .choices import model_term

    return [model_term(package, t) for t in _shape_targets(package, shape)]


__all__ = ['attribute_options', 'add_attribute_constraint', 'own_shape',
           'shape_targets', 'PAYLOAD_PATH']


# --- sub-attributes -------------------------------------------------------------

def _parent_group(package, shape, parent_path):
    """(file, text, group, parent IRI) for the attribute a sub-attribute goes in."""
    from .tree import _locate

    if not parent_path:
        raise PackageError('a sub-attribute needs the attribute it goes inside')
    path, text, group = _locate(package, str(shape), list(parent_path))
    parent = _resolve(package, parent_path[-1])
    if parent is None:
        raise PackageError(f'{parent_path[-1]} is not a term this package can '
                           f'resolve')
    return path, text, group, str(parent)


def _children_of(package, group):
    return {str(_resolve(package, child.path)) for child in group.children
            if child.path}


def sub_attribute_options(package, shape, parent_path):
    """What may nest inside one attribute's property shape, and its state.

    The knowledge says what is ALLOWED inside: a sub-attribute's rdfs:domain is
    the class of the attribute node that carries it -- ngsild:Relationship for
    `hasTrust`, ngsild:Property for `hasXXXWorkpiece` (choices.sub_attributes_for).
    Those already PLACED inside this parent somewhere come first.
    """
    from .choices import sub_attributes_for

    _, _, group, parent = _parent_group(package, shape, parent_path)
    here = _children_of(package, group)
    out = []
    for entry in sub_attributes_for(package, parent):
        out.append({'iri': entry.iri, 'term': entry.term, 'label': entry.label,
                    'kind': entry.kind or 'Property', 'comment': entry.comment,
                    'domain': entry.domain,
                    'scoped': bool(entry.parents),
                    'status': 'here' if entry.iri in here else 'free',
                    'by': ''})
    out.sort(key=lambda o: (o['status'] != 'free', not o['scoped'],
                            o['label'].lower()))
    return out


def add_sub_attribute_constraint(package, shape, parent_path, attribute,
                                 required=False, datatype=None,
                                 value_class=None):
    """Nest `attribute` inside the property shape at `parent_path`.

    The same two layers an entity attribute gets -- the sub-attribute node, and
    its value -- written INSIDE the parent's `sh:property [ ... ]`, which is how
    the NGSI-LD encoding hangs a sub-attribute off the parent's attribute node.
    Refuses what the knowledge does not allow inside this parent, and what is
    already there.
    """
    import re

    from .choices import sub_attributes_for
    from .knowledge import _turtle_name
    from .tree import _write_verified
    from ..rdfio.writer import INDENT, _block_lines

    path, text, group, parent = _parent_group(package, shape, parent_path)
    entry = _attribute(package, attribute)
    name = entry.label
    allowed = {e.iri for e in sub_attributes_for(package, parent)}
    if entry.iri not in allowed:
        if not (entry.parents or entry.carrier_kind):
            raise PackageError(
                f'{name} is carried by an entity, not by an attribute: the '
                f'knowledge gives it rdfs:domain '
                f'{local(entry.domain_iri) if entry.domain_iri else "nothing"}. '
                f'Add it to the shape itself instead.')
        raise PackageError(
            f'{name} cannot nest inside {local(parent)}: its rdfs:domain says '
            f'it is carried by a {entry.carrier_kind or "different"} node, and '
            f'{local(parent)} is not one.')
    if entry.iri in _children_of(package, group):
        raise PackageError(f'{local(parent)} already carries {name} here; edit '
                           f'that constraint instead')

    kind = entry.kind or 'Property'
    inner = _value_layer(package, kind, datatype, value_class, name)

    def term(node):
        return str(node) if isinstance(node, int) else _turtle_name(text, node)

    pairs = [(term(SH.minCount), '1' if required else '0'),
             (term(SH.maxCount), '1'),
             (term(SH.nodeKind), term(SH.BlankNode)),
             (term(SH.property),
              [(term(SH.path), term(URIRef(PAYLOAD_PATH[kind])))]
              + [(term(p), term(v)) for p, v in inner])]

    # Inside the parent, one level deeper than the line that opens it.
    line_start = text.rfind('\n', 0, group.start) + 1
    base = re.match(r'[ \t]*', text[line_start:]).group(0)
    indent = base + INDENT
    block = (f'{term(SH.property)} [ {term(SH.path)} {term(URIRef(entry.iri))} ;\n'
             + '\n'.join(_block_lines(indent, pairs)))

    at = group.end - 1
    while at > group.start and text[at - 1].isspace():
        at -= 1
    separator = '' if text[at - 1] in '[;' else ' ;'
    updated = text[:at] + f'{separator}\n{indent}{block}' + text[at:]
    _write_verified(path, updated)
    line = updated.count('\n', 0, at) + 2
    return {'file': path, 'line': line, 'shape': str(shape),
            'attribute': entry.iri, 'kind': kind, 'parent': parent}


def attribute_places(package, attribute):
    """Every property shape constraining `attribute`, at any depth.

    [{shape, shapeName, path, file, line}] where `path` is the chain of
    sh:path tokens leading to it -- the address a sub-attribute constraint
    needs. A sub-attribute declared from the Knowledge view has no tree row to
    say WHICH constraint of its parent it belongs in; this is the list it is
    chosen from.
    """
    from ..rdfio import TurtleIndex
    from ..validate.normalise import curie as name_of

    wanted = str(_resolve(package, attribute) or attribute)
    out = []
    for path in package.files('shapes'):
        if not os.path.isfile(path):
            continue
        with open(path, encoding='utf-8') as handle:
            text = handle.read()

        def walk(groups, chain, statement):
            for group in groups:
                here = chain + [group.path]
                if group.path and str(_resolve(package, group.path)) == wanted:
                    out.append({
                        'shape': statement.subject,
                        'shapeName': name_of(package.shapes,
                                             URIRef(statement.subject)),
                        'path': here, 'file': path,
                        'line': text.count('\n', 0, group.start) + 1})
                walk(group.children, here, statement)

        for statement in TurtleIndex(text).blocks:
            walk(property_blocks(text, statement), [], statement)
    return out


# --- editing an attribute in place (the type page) ------------------------------------

def _group_in(text, shape, path_chain):
    """The property group at `path_chain` in `shape`, read from `text`."""
    from ..rdfio import TurtleIndex, find_block

    block = TurtleIndex(text).block_for(str(shape))
    if block is None:
        raise PackageError(f'{shape} is not in this file any more')
    group = find_block(property_blocks(text, block), list(path_chain))
    if group is None:
        raise PackageError(f'no property shape at {" / ".join(path_chain)} in '
                           f'{local(shape)}; the file has changed')
    return group


def _value_slot(package, group):
    """The value layer's sh:path token inside an attribute group, or None."""
    for child in group.children:
        resolved = str(_resolve(package, child.path) or '')
        if resolved in PAYLOAD_PATH.values():
            return child.path
    return None


def _set(text, group, name, value):
    """Change a parameter where it stands, or add it on a line of its own."""
    from ..rdfio import set_parameter

    if group.parameter(name) is None:
        return _add_line(text, group, name, value)
    return set_parameter(text, group, name, value)


def _add_line(text, group, name, value):
    """A new parameter as the group's last, on its own line, indented like
    the others -- the way the file is written by hand."""
    import re

    at = group.end - 1                      # the closing ']'
    while at > group.start and text[at - 1].isspace():
        at -= 1
    body = text[group.start + 1:at]
    if '\n' not in body:
        separator = '' if text[at - 1] in '[;' else ' ;'
        return text[:at] + f'{separator} {name} {value}' + text[at:]
    # Indented like the group's own parameters -- not like its last line,
    # which may be the end of a nested `sh:property [ … ]`.
    own = [start for start, _, _ in (getattr(group, 'parameters', None) or {}).values()]
    if own:
        line_start = text.rfind('\n', 0, max(own)) + 1
        last_line = text[line_start:max(own)]
    else:
        last_line = body.rsplit('\n', 1)[-1]
    indent = re.match(r'[ \t]*', last_line).group(0)
    separator = '' if text[at - 1] == ';' else ' ;'
    return text[:at] + f'{separator}\n{indent}{name} {value}' + text[at:]


def _remove_line(text, group, name):
    """Remove a parameter, and the line it stood on when it stood alone.

    When it was the first thing after the group's `[`, the next parameter is
    pulled up onto that line, so `sh:property [ sh:class X ;` does not leave
    `sh:property [` dangling with nothing after it.
    """
    from ..rdfio import remove_parameter

    _, end, _ = group.parameter(name)
    start = text.rfind(name, group.start, end)
    updated = remove_parameter(text, group, name)
    line_start = updated.rfind('\n', 0, start) + 1
    line_end = updated.find('\n', start)
    line_end = len(updated) if line_end == -1 else line_end
    before = updated[line_start:start]
    after = updated[start:line_end]
    if after.strip():
        return updated
    if not before.strip():
        return updated[:line_start] + updated[line_end + 1:]
    if before.rstrip().endswith('['):
        following = line_end + 1
        while following < len(updated) and updated[following] in ' \t':
            following += 1
        return updated[:start].rstrip(' \t') + ' ' + updated[following:]
    return updated[:start].rstrip(' \t') + updated[line_end:]


def edit_attribute(package, shape, path_chain, presence=None, value=None, counts=None):
    """Change how an attribute is constrained, from the type page.

    `presence` is 'required' or 'optional' and sets the attribute layer's
    sh:minCount; sh:maxCount is left alone. 'required' keeps a minimum that is
    already 1 or more -- "exactly 3" made required again stays 3.
    `counts` ({'min': n, 'max': m or None}) sets both: how many instances --
    datasetIds -- the attribute must have; a max of None removes sh:maxCount. `value` replaces what the value
    must be: {'kind': 'any'} drops the class / datatype, {'datatype': ...} or
    {'valueClass': ...} sets one, through the same checks as adding an
    attribute. Ranges and every other parameter of the value layer stay.

    A value layer written with sh:or or sh:in is refused rather than rewritten:
    those are choices the vocabulary cannot round-trip, and a picker that
    silently replaced one would change what the shape means.
    Returns {'file', 'line'}.
    """
    from .tree import _write_verified
    from .knowledge import _turtle_name

    shape = str(shape)
    holder = package.index('shapes').file_for(URIRef(shape))
    if holder is None:
        raise PackageError(f'{shape} is not in any shapes file')
    with open(holder, encoding='utf-8') as handle:
        text = handle.read()
    chain = list(path_chain)

    if presence is not None:
        if presence not in ('required', 'optional'):
            raise PackageError(f'presence is required or optional, not {presence}')
        group = _group_in(text, shape, chain)
        name = _turtle_name(text, SH.minCount)
        current = group.parameter(name)
        try:
            least = int(str(current[2]).strip()) if current else 0
        except ValueError:
            least = 0
        wanted = (str(least) if least >= 1 else '1') if presence == 'required' else '0'
        text = _set(text, group, name, wanted)

    if counts is not None:
        least, most = counts.get('min'), counts.get('max')
        try:
            least = int(least)
            most = None if most in (None, '') else int(most)
        except (TypeError, ValueError):
            raise PackageError(f'a count is a whole number: {counts}')
        if least < 0 or (most is not None and most < 0):
            raise PackageError('a count is 0 or more')
        if most is not None and least > most:
            raise PackageError(f'at least {least} and at most {most}: no data can '
                               f'satisfy that')
        group = _group_in(text, shape, chain)
        text = _set(text, group, _turtle_name(text, SH.minCount), str(least))
        group = _group_in(text, shape, chain)
        name = _turtle_name(text, SH.maxCount)
        if most is not None:
            text = _set(text, group, name, str(most))
        elif group.parameter(name) is not None:
            text = _remove_line(text, group, name)

    if value is not None:
        group = _group_in(text, shape, chain)
        slot = _value_slot(package, group)
        if slot is None:
            raise PackageError(f'{chain[-1]} has no value layer to constrain; '
                               f'edit it in the .ttl')
        layer = _group_in(text, shape, chain + [slot])
        slot_text = text[layer.start:layer.end]
        if 'sh:or' in slot_text or 'sh:in' in slot_text:
            raise PackageError(
                f'the value of {local(str(_resolve(package, chain[-1])))} is '
                f'written with sh:or or sh:in; change it in the .ttl so its '
                f'meaning is not rewritten behind your back')
        attribute = str(_resolve(package, chain[-1]))
        entry = _attribute(package, attribute)
        kind = entry.kind or 'Property'
        new = [] if value.get('kind') == 'any' else _value_layer(
            package, kind, value.get('datatype') or None,
            value.get('valueClass') or None, entry.label)
        wanted = {}
        for predicate, obj in new:
            if predicate not in (SH.minCount, SH.maxCount):
                wanted[_turtle_name(text, predicate)] = _turtle_name(text, obj)
        # Change what is still wanted where it stands; drop what is not;
        # add the rest. A class swapped for another class rewrites one value.
        for name in ('sh:class', 'sh:datatype', 'sh:nodeKind'):
            target = _group_in(text, shape, chain + [slot])
            if target.parameter(name) is None:
                continue
            if name in wanted:
                text = _set(text, target, name, wanted.pop(name))
            else:
                text = _remove_line(text, target, name)
        for name, written in wanted.items():
            target = _group_in(text, shape, chain + [slot])
            text = _set(text, target, name, written)

    _write_verified(holder, text)
    group = _group_in(text, shape, chain)
    return {'file': holder, 'line': text.count('\n', 0, group.start) + 1}


def remove_property_group(package, shape, path_chain):
    """Take one attribute's property shape out of one shape -- the attribute
    stays declared, and stays constrained wherever else it is."""
    from .remove_attribute import _remove_span
    from .tree import _write_verified
    from ..rdfio import TurtleIndex, find_block

    shape = str(shape)
    holder = package.index('shapes').file_for(URIRef(shape))
    if holder is None:
        raise PackageError(f'{shape} is not in any shapes file')
    with open(holder, encoding='utf-8') as handle:
        text = handle.read()
    statement = TurtleIndex(text).block_for(shape)
    chain = list(path_chain)
    group = _group_in(text, shape, chain)
    parent = find_block(property_blocks(text, statement), chain[:-1]) \
        if len(chain) > 1 else None
    start, end = (parent.start + 1, parent.end - 1) if parent else \
        (statement.start, statement.end)
    updated = _remove_span(text, group, start, end)
    _write_verified(holder, updated)
    return {'file': holder, 'line': text.count('\n', 0, group.start) + 1}
