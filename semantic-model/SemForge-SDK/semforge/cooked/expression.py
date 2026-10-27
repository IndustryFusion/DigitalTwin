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

"""What a value must be, when that is more than one condition: an expression.

Most values are one set of conditions -- `number · 0 – 100` -- and are edited
with the value picker. SHACL can say more on the same value layer: any of
several (`sh:or`), all of them (`sh:and`), exactly one (`sh:xone`), not
(`sh:not`), nested as deep as wanted. The kms says "a number" as

    sh:property [ sh:path ngsild:hasValue ; sh:minInclusive 0.0 ; sh:maxInclusive 100.0 ;
                  sh:or ( [ sh:datatype xsd:double ] [ sh:datatype xsd:integer ] ) ]

The value layer is read as a tree: its root is ALL OF the layer's own
conditions and every connective on it; a connective's branches are condition
sets or connectives again. A branch this cannot say in words -- an sh:node, a
nested sh:property -- is kept as it is written, shown, and not edited; the
rest of the tree around it is.

Writing back changes the layer in place: its own conditions where they stand,
its connectives regenerated from the tree. An expression is regenerated only
if nothing in it is lost by that -- a comment inside one makes it read-only --
and every write is read back first: it must say what was meant.
"""

import re
from dataclasses import dataclass, replace

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF, SH, XSD

from ..errors import PackageError

CONNECTIVES = ('or', 'and', 'xone', 'not')
WORDS = {'or': 'any of', 'and': 'all of', 'xone': 'exactly one of', 'not': 'not'}
# What a condition set may say; anything else makes a branch raw.
CONDITIONS = ('sh:class', 'sh:datatype', 'sh:nodeKind', 'sh:minInclusive', 'sh:maxInclusive',
              'sh:minExclusive', 'sh:maxExclusive', 'sh:minLength', 'sh:maxLength',
              'sh:pattern', 'sh:flags', 'sh:in', 'sh:hasValue')
# What a value layer carries beside its value conditions: left where it stands.
STRUCTURE = ('sh:path', 'sh:minCount', 'sh:maxCount', 'sh:order', 'sh:name',
             'sh:description', 'sh:message', 'sh:severity', 'sh:deactivated', 'sh:group')


@dataclass(frozen=True)
class Leaf:
    conditions: tuple = ()           # (('sh:datatype', 'xsd:double'), …), sorted by key

    def get(self, key):
        return dict(self.conditions).get(key)


@dataclass(frozen=True)
class Op:
    op: str                          # or | and | xone | not
    children: tuple = ()


@dataclass(frozen=True)
class Raw:
    text: str                        # as Turtle; kept, never edited


@dataclass(frozen=True)
class Layer:
    slot: str                        # the value layer's sh:path as written
    root: Op                         # Op('and', (Leaf(own conditions), *connectives))
    editable: bool
    reason: str = ''                 # why not, when not

    @property
    def complex(self):
        return len(self.root.children) > 1


def _local(iri):
    return str(iri)[len(str(SH)):] if str(iri).startswith(str(SH)) else None


# --- reading --------------------------------------------------------------------------

class _Reader:
    """Graph -> tree. Terms are spelled by `spell(iri)`: as the file writes them."""

    def __init__(self, graph, spell):
        self.graph = graph
        self.spell = spell

    def term(self, term):
        if isinstance(term, URIRef):
            return self.spell(term)
        if isinstance(term, Literal):
            def qname(iri):
                spelled = self.spell(URIRef(iri))
                return None if spelled.startswith('<') else spelled
            # Short forms where Turtle's short form is the written one (5,
            # 100.0, true); a double kept as written -- rdflib says 0.6 as 6e-01.
            plain = term.datatype is None or str(term.datatype) != str(XSD.double)
            return term._literal_n3(use_plain=plain, qname_callback=qname)
        if (term, RDF.first, None) in self.graph or term == RDF.nil:
            return '( ' + ' '.join(self.term(t) for t in Collection(self.graph, term)) + ' )' \
                if term != RDF.nil else '()'
        return self.raw(term)

    def raw(self, node):
        """Any blank node as Turtle -- a branch kept as it is."""
        pairs = sorted(self.graph.predicate_objects(node))
        return '[ ' + ' ; '.join(f'{self.term(p)} {self.term(o)}' for p, o in pairs) + ' ]' \
            if pairs else '[ ]'

    def node(self, node):
        """A shape node -- [ … ] in a connective's list -- as a tree node."""
        if not isinstance(node, BNode) or (node, RDF.first, None) in self.graph:
            return Raw(self.term(node))
        conditions, connectives = [], []
        for predicate in sorted(set(self.graph.predicates(node))):
            objects = list(self.graph.objects(node, predicate))
            local = _local(predicate)
            key = f'sh:{local}' if local else None
            if key in CONDITIONS and len(objects) == 1:
                conditions.append((key, self.term(objects[0])))
            elif local in CONNECTIVES and len(objects) == 1:
                connective = self.connective(local, objects[0])
                if connective is None:
                    return Raw(self.raw(node))
                connectives.append(connective)
            else:
                return Raw(self.raw(node))
        parts = ([Leaf(tuple(conditions))] if conditions else []) + connectives
        if len(parts) == 1:
            return parts[0]
        return Op('and', tuple(parts)) if parts else Leaf()

    def connective(self, op, value):
        if op == 'not':
            return Op('not', (self.node(value),))
        if value != RDF.nil and (value, RDF.first, None) not in self.graph:
            return None
        return Op(op, tuple(self.node(m) for m in Collection(self.graph, value)))


def _uncommented(text):
    """Text with strings and IRIs blanked: a '#' left is a comment."""
    text = re.sub(r'"""(?:.|\n)*?"""|"(?:[^"\\\n]|\\.)*"|<[^>\s]*>', '""', text)
    return '#' not in text


def _prefix_head(prefixes):
    return ''.join(f'@prefix {p}: <{n}> .\n' for p, n in prefixes)


HOLDER = URIRef('urn:semforge:holder')


def read_layer(package, text, shape, chain):
    """The value layer of the attribute at `chain` as an expression, or None
    when it has no value layer (or one this does not edit as a value)."""
    from .constrain import _group_in, _turtle_name, _value_slot
    from .payloads import prefixes_of

    group = _group_in(text, shape, chain)
    slot = _value_slot(package, group)
    if slot is None:
        return None
    layer = _group_in(text, shape, chain + [slot])
    root, reason = _read_root(text[layer.start:layer.end], prefixes_of(package),
                              lambda iri: _turtle_name(text, iri))
    if not reason and len(root.children) > 1:
        written = [layer.parameter(_turtle_name(text, SH[c])) for c in CONNECTIVES]
        if any(w is not None and not _uncommented(text[w[0]:w[1]]) for w in written):
            reason = 'a comment inside it would be lost'
    return Layer(slot=slot, root=root, editable=not reason, reason=reason)


def _read_root(body, prefixes, spell):
    """(root, why it is not editable) of a value layer written as `body`."""
    try:
        graph = Graph().parse(data=f'{_prefix_head(prefixes)}<{HOLDER}> <{SH.property}> {body} .',
                              format='turtle')
    except Exception as exc:                       # noqa: BLE001
        raise PackageError(f'the value does not read: {exc}') from None
    node = graph.value(HOLDER, SH.property)
    reader = _Reader(graph, spell)
    conditions, connectives, reason = [], [], ''
    for predicate in sorted(set(graph.predicates(node))):
        local = _local(predicate)
        key = f'sh:{local}' if local else str(predicate)
        objects = list(graph.objects(node, predicate))
        if key in STRUCTURE:
            continue
        if key in CONDITIONS and len(objects) == 1:
            conditions.append((key, reader.term(objects[0])))
        elif local in CONNECTIVES and len(objects) == 1:
            found = reader.connective(local, objects[0])
            if found is None:
                reason = f'its {key} is not a list'
            else:
                connectives.append(found)
        else:
            reason = f'it says {reader.term(predicate)}, which this does not edit'
    return Op('and', (Leaf(tuple(conditions)),) + tuple(connectives)), reason


def _canonical(root, prefixes, spell):
    """`root` as it reads back once written: the same reader on both sides, so
    a number or a list compares as written, whatever spelling it came in."""
    own, params = _split(normalize_root(root))
    parts = [f'{spell(SH[k[3:]])} {v}' for k, v in own.conditions] + \
        [f'{spell(SH[op])} {_value(node, spell)}' for op, node in params]
    found, _ = _read_root('[ ' + ' ; '.join(parts) + ' ]', prefixes, spell)
    return normalize_root(found)


# --- the shape of a tree ------------------------------------------------------------------

def normalize(node):
    """The same meaning, said once: no one-branch connectives, no all-of
    inside all-of, no empty condition set inside an all-of. An empty set is
    "anything": dropped from an all-of it changes nothing; from an any-of it
    would change everything, so there it stays."""
    if isinstance(node, Op):
        children = []
        for child in node.children:
            child = normalize(child)
            if child is None:
                continue
            if node.op == 'and' and isinstance(child, Leaf) and not child.conditions:
                continue
            if node.op == 'and' and isinstance(child, Op) and child.op == 'and':
                children.extend(child.children)
            else:
                children.append(child)
        if not children:
            return Leaf() if node.op == 'and' else None
        if node.op != 'not' and len(children) == 1:
            return children[0]
        return Op(node.op, tuple(children))
    return node


def normalize_root(root):
    """A layer's root: Op('and', (Leaf(own conditions), *connectives)).
    Condition sets at the top join the layer's own where no key clashes."""
    flat = normalize(Op('and', root.children if isinstance(root, Op) and root.op == 'and'
                        else (root,)))
    parts = list(flat.children) if isinstance(flat, Op) and flat.op == 'and' else \
        ([flat] if flat is not None else [])
    own, rest = {}, []
    for part in parts:
        if isinstance(part, Leaf) and not set(dict(part.conditions)) & set(own):
            own.update(part.conditions)
        else:
            rest.append(part)
    return Op('and', (Leaf(tuple(sorted(own.items()))),) + tuple(rest))


# --- words ---------------------------------------------------------------------------------

def words(node, kind='Property', tag=True):
    """One part in words. `tag`: a number says which (double, integer) --
    beside another number type it must be told apart; alone it need not."""
    from .typepage import NUMBER_TYPES, value_text

    if isinstance(node, Leaf):
        params = dict(node.conditions)
        said = value_text(kind, params, [])
        datatype = params.get('sh:datatype')
        if tag and datatype in NUMBER_TYPES:
            # Two number types side by side must be told apart.
            said = said.replace('number', f'number ({datatype.split(":")[-1]})', 1)
        if 'sh:hasValue' in params:
            said = f'exactly {params["sh:hasValue"]}' if said == 'any value' \
                else f'{said} · exactly {params["sh:hasValue"]}'
        return said
    if isinstance(node, Raw):
        return node.text
    return WORDS[node.op]


def to_json(node, kind='Property'):
    if isinstance(node, Leaf):
        return {'kind': 'leaf', 'words': words(node, kind),
                'conditions': [{'parameter': k, 'value': v} for k, v in node.conditions]}
    if isinstance(node, Raw):
        return {'kind': 'raw', 'words': node.text}
    return {'kind': 'op', 'op': node.op, 'words': WORDS[node.op],
            'children': [to_json(c, kind) for c in node.children]}


def clause(node, kind='Property'):
    """A part of an expression in words: `any of: number (double) | n/a`."""
    if isinstance(node, Op):
        joint = ' and ' if node.op == 'and' else ' | '
        inner = joint.join(clause(c, kind) for c in node.children)
        return f'{WORDS[node.op]}: {inner}' if node.op != 'not' else f'not ({inner})'
    return words(node, kind)


def describe(layer, kind='Property'):
    """One line, every part as written: `0 – 100 · any of: number (double) |
    number (integer)`. The pages say a value with valueforms.say()."""
    own, *rest = layer.root.children
    parts = ([words(own, kind)] if own.conditions else []) + [clause(c, kind) for c in rest]
    return ' · '.join(parts)


# --- writing -------------------------------------------------------------------------------

def _member(node, name):
    if isinstance(node, Leaf):
        inner = ' ; '.join(f'{name(SH[k[3:]])} {v}' for k, v in node.conditions)
        return f'[ {inner} ]' if inner else '[ ]'
    if isinstance(node, Raw):
        return node.text
    leaves = [c for c in node.children if isinstance(c, Leaf)]
    ops = [c for c in node.children if isinstance(c, Op)]
    if node.op == 'and' and len(leaves) <= 1 and len(leaves) + len(ops) == len(node.children) \
            and len({c.op for c in ops}) == len(ops) and 'and' not in {c.op for c in ops}:
        # One node says all of it, as written by hand: [ ranges ; sh:or ( … ) ].
        parts = [f'{name(SH[k[3:]])} {v}' for leaf in leaves for k, v in leaf.conditions]
        parts += [f'{name(SH[c.op])} {_value(c, name)}' for c in ops]
        return '[ ' + ' ; '.join(parts) + ' ]'
    return f'[ {name(SH[node.op])} {_value(node, name)} ]'


def _value(op, name):
    if op.op == 'not':
        return _member(op.children[0], name)
    return '( ' + ' '.join(_member(c, name) for c in op.children) + ' )'


def _split(root):
    """(own conditions, [(connective, value Op)]): the first of each kind goes
    on the layer; a second, or a condition set that clashes with the layer's
    own, joins one all-of."""
    own, *rest = root.children
    params, extra = {}, []
    for node in rest:
        if isinstance(node, Op) and node.op not in params:
            params[node.op] = node
        else:
            extra.append(node)
    if extra:
        if 'and' in params:
            params['and'] = Op('and', params['and'].children + tuple(extra))
        else:
            params['and'] = Op('and', tuple(extra))
    return own, [(op, params[op]) for op in CONNECTIVES if op in params]


def write_layer(package, shape, chain, root):
    """Write `root` as the value layer at `chain` of `shape`. Returns
    {'file', 'line'}. Refuses -- and changes nothing -- when the result does
    not read back as `root` says."""
    from .constrain import _group_in, _remove_line, _set, _turtle_name
    from .tree import _write_verified

    shape, chain = str(shape), list(chain)
    holder = package.index('shapes').file_for(URIRef(shape))
    if holder is None:
        raise PackageError(f'{shape} is not in any shapes file')
    with open(holder, encoding='utf-8') as handle:
        text = handle.read()
    before = read_layer(package, text, shape, chain)
    if before is None:
        raise PackageError(f'{chain[-1]} has no value layer; edit it in the .ttl')
    if not before.editable:
        raise PackageError(f'the value of {chain[-1]} is edited in the .ttl: {before.reason}')
    root = normalize_root(root)
    own, params = _split(root)

    def name(iri):
        return _turtle_name(text, iri)

    target = chain + [before.slot]
    old = dict(before.root.children[0].conditions)
    new = dict(own.conditions)
    for key in sorted(set(old) | set(new)):
        spelled = _turtle_name(text, SH[key[3:]])
        layer = _group_in(text, shape, target)
        if key in new and old.get(key) != new[key]:
            text = _set(text, layer, spelled, new[key])
        elif key not in new:
            text = _remove_line(text, layer, spelled)
    for op in CONNECTIVES:
        spelled = _turtle_name(text, SH[op])
        layer = _group_in(text, shape, target)
        if layer.parameter(spelled) is not None:
            text = _remove_line(text, layer, spelled)
    for op, node in params:
        layer = _group_in(text, shape, target)
        text = _set(text, layer, _turtle_name(text, SH[op]), _value(node, name))

    from .payloads import prefixes_of

    after = read_layer(package, text, shape, chain)
    if after is None or normalize_root(after.root) != _canonical(root, prefixes_of(package), name):
        raise PackageError('the value would not read back as meant; nothing was changed')
    _write_verified(holder, text)
    group = _group_in(text, shape, chain)
    return {'file': holder, 'line': text.count('\n', 0, group.start) + 1}


# --- the edits the page asks for -------------------------------------------------------------

def _at(root, address):
    node = root
    for index in address:
        if not isinstance(node, Op) or not 0 <= index < len(node.children):
            raise PackageError('that part of the expression is not there any more')
        node = node.children[index]
    return node


def _put(root, address, new):
    """`root` with the node at `address` replaced by `new` (None removes it)."""
    if not address:
        return new
    head, rest = address[0], address[1:]
    children = list(root.children)
    if rest:
        children[head] = _put(children[head], rest, new)
    elif new is None:
        del children[head]
    else:
        children[head] = new
    return replace(root, children=tuple(children))


def edit(package, shape, chain, action):
    """One change to the value's expression, as the page asks for it.

    action: {'op': 'set' | 'unset' | 'add' | 'remove' | 'wrap' | 'unwrap' | 'retype' |
    'combine', 'node': [index, …] from the root, 'parameter', 'value',
    'connective'}.

    - set / unset a condition of a condition set at `node`;
    - add a branch (a condition) to the connective at `node`;
    - remove the node;
    - wrap the node in a connective -- with a new second branch, for any of /
      exactly one of / all of; alone, for not;
    - unwrap: a connective replaced by its branches (a not by what it negates);
    - retype: any of, all of and exactly one of changed into each other;
    - combine (the value picker's "Combine with another condition…"): the
      layer's own value conditions become one branch of any of / exactly one
      of beside the new one; `not` adds the new one as "not".

    The same change in every form the value takes -- one value and each item
    of a list alike -- written by the one writer of values
    (valueforms.write_value). valueforms.edit_value changes one form.
    """
    from .valueforms import read_value, write_value

    holder = package.index('shapes').file_for(URIRef(str(shape)))
    if holder is None:
        raise PackageError(f'{shape} is not in any shapes file')
    with open(holder, encoding='utf-8') as handle:
        text = handle.read()
    value = read_value(package, text, str(shape), list(chain))
    if not value.forms:
        raise PackageError(f'{chain[-1]} has no value layer; add a form in the value editor')
    if not value.editable:
        raise PackageError(f'the value of {chain[-1]} is edited in the .ttl: {value.reason}')
    condition = _conditions(package, text, action)
    return write_value(package, shape, chain, tuple(
        replace(form, root=_apply(form.root, action, condition)) for form in value.forms))


def _conditions(package, text, action):
    """condition(spec=None) -> (parameter, value as the file writes it)."""
    from .tree import _parameter_value

    def condition(spec=None):
        spec = spec or action
        parameter = spec.get('parameter')
        if parameter not in CONDITIONS:
            raise PackageError(f'{parameter} is not a condition on a value')
        if not str(spec.get('value') or '').strip():
            raise PackageError(f'{parameter} needs a value')
        if parameter == 'sh:hasValue':
            from .tree import _list_value
            value = _list_value(package, text, [spec.get('value')])[2:-2]
        else:
            value = _parameter_value(package, text, parameter, spec.get('value'))
        return parameter, value

    return condition


def _apply(root, action, condition):
    """One edit of an expression tree, as the page asks for it (see edit())."""
    what = action.get('op')
    address = [int(i) for i in action.get('node') or []]
    if what == 'addgroup':
        # A group arrives with its branches: one branch alone would be no group.
        node, op = _at(root, address), action.get('connective')
        if not isinstance(node, Op) or node.op == 'not':
            raise PackageError('a group is added inside any of, all of or exactly one of')
        branches = tuple(Leaf((condition(spec),)) for spec in action.get('conditions') or [])
        if op not in CONNECTIVES or len(branches) < (1 if op == 'not' else 2):
            raise PackageError('a group is not with one condition, any of / exactly one '
                               'of / all of with two or more')
        root = _put(root, address, Op(node.op, node.children + (Op(op, branches),)))
    elif what in ('set', 'unset'):
        node = _at(root, address)
        if not isinstance(node, Leaf):
            raise PackageError('conditions are set on a set of conditions, not on a connective')
        conditions = dict(node.conditions)
        if what == 'set':
            key, value = condition()
            conditions[key] = value
        else:
            conditions.pop(action.get('parameter'), None)
        root = _put(root, address, Leaf(tuple(sorted(conditions.items()))))
    elif what == 'add':
        node = _at(root, address)
        if not isinstance(node, Op) or node.op == 'not':
            raise PackageError('a branch is added to any of, all of or exactly one of')
        root = _put(root, address, Op(node.op, node.children + (Leaf((condition(),)),)))
    elif what == 'remove':
        if not address:
            raise PackageError('the whole value is not removed here; use "any value"')
        root = _put(root, address, None)
    elif what == 'wrap':
        op = action.get('connective')
        if op not in CONNECTIVES:
            raise PackageError(f'{op} is not a connective')
        node = _at(root, address)
        branches = (node,) if op == 'not' else (node, Leaf((condition(),)))
        root = _put(root, address, Op(op, branches))
    elif what == 'unwrap':
        node = _at(root, address)
        if not isinstance(node, Op) or not address:
            raise PackageError('only a connective inside the value is unwrapped')
        if len(node.children) != 1 and node.op != 'and':
            raise PackageError(f'{WORDS[node.op]} has {len(node.children)} branches: '
                               f'remove all but one first')
        parent = _at(root, address[:-1])
        index = address[-1]
        children = list(parent.children)
        children[index:index + 1] = list(node.children)
        root = _put(root, address[:-1], replace(parent, children=tuple(children)))
    elif what == 'retype':
        node, op = _at(root, address), action.get('connective')
        if not isinstance(node, Op) or not address or node.op == 'not' or \
                op not in ('or', 'and', 'xone'):
            raise PackageError('any of, all of and exactly one of change into each other')
        root = _put(root, address, Op(op, node.children))
    elif what == 'combine':
        op = action.get('connective')
        own, *rest = root.children
        new = Leaf((condition(),))
        if op in ('or', 'xone') and not own.conditions:
            raise PackageError('the value is any value so far: say what it must be '
                               'first, then what else it may be')
        if op == 'not':
            root = Op('and', (own,) + tuple(rest) + (Op('not', (new,)),))
        elif op in ('or', 'xone'):
            # Everything the value is now -- its own conditions AND every
            # connective already on it -- is one branch; the new one the other.
            # Leaving a connective outside would still demand it of the new
            # branch: "a number, or n/a" would refuse "n/a" for not being one.
            now = normalize(Op('and', (own,) + tuple(rest)))
            root = Op('and', (Leaf(), Op(op, (now, new))))
        else:
            raise PackageError(f'combine with any of, exactly one of or not -- not {op}')
    else:
        raise PackageError(f'{what} is not an edit of an expression')
    return root
