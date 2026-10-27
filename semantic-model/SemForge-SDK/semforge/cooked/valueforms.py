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

"""What an attribute's value may be: its forms, each with its own conditions.

An NGSI-LD attribute carries its value in one of several forms -- a Property's
`value`, a Relationship's `object`, a JsonProperty's `json`, a ListProperty's
`valueList`, … SHACL may allow any choice of them, and each its own
conditions: "a single boolean, or a list of numbers", "a Property or a
JsonProperty". The OPC UA tools write one such choice for every Variable
(a value, or a list of the same); cooked/payloads.py reads them.

Here a value is a list of Forms. Each Form names its payload (and so its
kind), its counts, whether a list may be empty, and an expression tree
(cooked/expression.py) for what the value -- or each item of a list -- must
be. Written back:

- no form: no value layer at all (any value);
- one form: one value layer, `sh:property [ sh:path ngsild:hasValue ; … ]`,
  as nearly every attribute is written by hand -- and edited where it stands
  when it was one already;
- several: the choice of value layers, `sh:or ( [ sh:property [ … ] ] … )`.

What the reader cannot say exactly -- an sh:or of something else, a comment
inside, a value layer with conditions it does not know -- is refused as a
whole, never half-edited. Every write is read back first: it must say what
was meant.
"""

import functools
from dataclasses import dataclass, replace

from rdflib import URIRef
from rdflib.namespace import SH

from ..errors import PackageError
from ..ngsild.kinds import LIST_PAYLOADS, NGSILD, PAYLOAD_NAME
from .expression import (Leaf, Op, _apply, _canonical, _conditions, _read_root, _split,
                         _uncommented, _value, normalize_root, to_json)

# The kinds a form may be, in the order a reader thinks of them; each has its
# payload. GeoProperty shares hasValue with Property, and is not offered.
KINDS = ('Property', 'Relationship', 'JsonProperty', 'ListProperty', 'ListRelationship',
         'LanguageProperty', 'VocabProperty')
KIND_OF = {PAYLOAD_NAME[k]: k for k in KINDS}
WORDS = {'hasValue': 'one value', 'hasObject': 'one entity', 'hasJSON': 'JSON',
         'hasValueList': 'a list of values', 'hasObjectList': 'a list of entities',
         'hasLanguageMap': 'text by language', 'hasVocab': 'a vocabulary term'}


@dataclass(frozen=True)
class Form:
    payload: str                 # hasValue | hasObject | hasJSON | hasValueList | …
    root: Op                     # what the value, or each item of a list, must be
    least: str = '1'             # sh:minCount of the payload
    most: str = '1'              # sh:maxCount of the payload
    may_be_empty: bool = False   # a list that may be ()
    encoded: bool = True         # writes the one value's sh:nodeKind (literal / IRI)

    @property
    def kind(self):
        return KIND_OF.get(self.payload, self.payload)

    @property
    def is_list(self):
        return NGSILD + self.payload in LIST_PAYLOADS


@dataclass(frozen=True)
class Value:
    forms: tuple
    where: str                   # 'slot' (one value layer) | 'attribute' (sh:or) | ''
    slot: str = ''               # the value layer's sh:path as written, when 'slot'
    editable: bool = True
    reason: str = ''


def speller(prefixes):
    """spell(iri) by the longest of `prefixes` that fits, else <iri>."""
    import re

    ordered = sorted(((str(n), str(p)) for p, n in prefixes), key=lambda x: -len(x[0]))

    def spell(iri):
        text = str(iri)
        for namespace, prefix in ordered:
            rest = text[len(namespace):]
            if text.startswith(namespace) and rest and re.match(r'^[\w-]+$', rest):
                return f'{prefix}:{rest}'
        return f'<{text}>'
    return spell


def value_of(found, prefixes):
    """A Value from what payloads.alternatives() read -- for a view that has
    the sh:or's text but not the file (the constraints tree)."""
    pairs = [_form(a, prefixes, prefixes) for a in found]
    reason = next((r for _, r in pairs if r), '')
    return Value(tuple(f for f, _ in pairs), 'attribute', editable=not reason, reason=reason)


@functools.lru_cache(maxsize=4096)
def _root_of(body, prefixes, spelling):
    """_read_root, kept: the same few member texts recur hundreds of times --
    every text attribute of the OPC UA shapes says the same -- and the
    constraints tree reads all 576 of them for every type page."""
    return _read_root(body, prefixes, speller(spelling))


def _form(alternative, prefixes, spelling):
    """A Form from what payloads.py read; (Form, why not editable).
    `spelling`: the (prefix, namespace) pairs its terms are written with."""
    from rdflib.namespace import SH as shacl

    member = [(k, v) for k, v in alternative.member if k != 'sh:nodeKind']
    body = '[ ' + ' ; '.join(f'<{shacl}{k[3:]}> {v}' for k, v in member) + ' ]'
    root, reason = _root_of(body, tuple(prefixes), tuple(spelling))
    return Form(payload=alternative.payload, root=root, least=alternative.least or '',
                most=alternative.most or '', may_be_empty=alternative.may_be_empty,
                encoded='sh:nodeKind' in dict(alternative.member)), reason


def read_value(package, text, shape, chain):
    """The value of the attribute at `chain` of `shape`, as forms."""
    from .constrain import _group_in, _turtle_name, _value_slot
    from .knowledge import _prefix_lines
    from .payloads import alternatives, prefixes_of

    group = _group_in(text, shape, chain)
    prefixes = prefixes_of(package)
    # Terms as THIS file writes them: by its own prefix lines (as _turtle_name).
    spelling = _prefix_lines(text)

    choice = group.parameter(_turtle_name(text, SH['or']))
    slot = _value_slot(package, group)
    if choice is not None and slot is not None:
        return Value((), 'attribute', editable=False,
                     reason='its value is said both by an sh:or and by a value layer')
    if choice is not None:
        found = alternatives(choice[2], prefixes)
        if not found:
            return Value((), 'attribute', editable=False,
                         reason='its sh:or is not a choice of value forms')
        written = text[choice[0]:choice[1]]
    elif slot is not None:
        layer = _group_in(text, shape, chain + [slot])
        written = text[layer.start:layer.end]
        # One value layer is one form: read by the same reader, as a choice of one.
        found = alternatives(f'( [ <{SH.property}> {written} ] )', prefixes)
        if not found:
            return Value((), 'slot', slot, editable=False,
                         reason='its value layer says something SemForge does not edit here')
    else:
        return Value((), '')
    forms, reasons = [], []
    for alternative in found:
        form, reason = _form(alternative, prefixes, spelling)
        forms.append(form)
        reasons.append(reason)
    reason = next((r for r in reasons if r), '')
    if not reason and not _uncommented(written):
        reason = 'a comment inside it would be lost'
    return Value(tuple(forms), 'attribute' if choice is not None else 'slot', slot or '',
                 editable=not reason, reason=reason)


# --- writing -------------------------------------------------------------------------------

def _literals_and_iris(node):
    """(says a literal, says an IRI) anywhere in the tree."""
    literal = iri = False
    if isinstance(node, Op):
        for child in node.children:
            more = _literals_and_iris(child)
            literal, iri = literal or more[0], iri or more[1]
    elif isinstance(node, Leaf):
        keys = dict(node.conditions)
        literal = 'sh:datatype' in keys or any(k in keys for k in (
            'sh:minLength', 'sh:maxLength', 'sh:pattern', 'sh:minInclusive', 'sh:maxInclusive',
            'sh:minExclusive', 'sh:maxExclusive'))
        iri = 'sh:class' in keys
        value = keys.get('sh:hasValue')
        if value is not None:
            if value.startswith(('"', "'")) or value[:1].isdigit() or value[:1] in '+-' or \
                    value in ('true', 'false'):
                literal = True
            else:
                iri = True
    return literal, iri


def _encoding(form, name):
    """The one value's sh:nodeKind, said again from what it must be: an entity
    is an IRI; a value a literal when every branch says one, an IRI when every
    branch says a class or term; neither when it may be both."""
    if not form.encoded or form.is_list:
        return []
    if form.payload == 'hasObject':
        return [('sh:nodeKind', name(SH.IRI))]
    if form.payload != 'hasValue':
        return []
    literal, iri = _literals_and_iris(form.root)
    if literal and not iri:
        return [('sh:nodeKind', name(SH.Literal))]
    if iri and not literal:
        return [('sh:nodeKind', name(SH.IRI))]
    return []


def _alternative(form, name):
    from .payloads import Alternative

    own, params = _split(normalize_root(form.root))
    member = list(own.conditions) + [(f'sh:{op}', _value(node, name)) for op, node in params] + \
        _encoding(form, name)
    return Alternative(payload=form.payload, kind=form.kind, member=tuple(sorted(member)),
                       least=form.least, most=form.most, may_be_empty=form.may_be_empty)


def _same(one, other, prefixes, spell):
    """Do two Values say the same, once written and read back?"""
    if len(one.forms) != len(other.forms):
        return False
    for a, b in zip(one.forms, other.forms):
        if (a.payload, a.least, a.most, a.may_be_empty) != \
                (b.payload, b.least, b.most, b.may_be_empty):
            return False
        if normalize_root(a.root) != _canonical(b.root, prefixes, spell):
            return False
    return True


def write_value(package, shape, chain, forms):
    """Write `forms` as the value of the attribute at `chain`; {'file', 'line'}.
    Refuses -- and changes nothing -- unless it reads back as meant."""
    from .constrain import _add_line, _group_in, _remove_line, _set, _turtle_name
    from .expression import write_layer
    from .payloads import _layer, prefixes_of, render
    from .remove_attribute import _remove_span
    from .tree import _write_verified

    shape, chain = str(shape), list(chain)
    holder = package.index('shapes').file_for(URIRef(shape))
    if holder is None:
        raise PackageError(f'{shape} is not in any shapes file')
    with open(holder, encoding='utf-8') as handle:
        text = handle.read()
    before = read_value(package, text, shape, chain)
    if not before.editable:
        raise PackageError(f'the value of {chain[-1]} is edited in the .ttl: {before.reason}')
    payloads = [f.payload for f in forms]
    if len(set(payloads)) != len(payloads):
        raise PackageError('each form once: two of the same kind say nothing a single one '
                           'does not')
    forms = tuple(replace(f, root=normalize_root(f.root)) for f in forms)

    def name(iri):
        return _turtle_name(text, iri)

    old = before.forms
    if before.where == 'slot' and len(forms) == 1 and len(old) == 1 and \
            (forms[0].payload, forms[0].least, forms[0].most) == \
            (old[0].payload, old[0].least, old[0].most) and not forms[0].is_list:
        # One value layer, still one: changed where it stands, comments and all.
        form = forms[0]
        own, *rest = form.root.children
        root = Op('and', (Leaf(tuple(sorted(own.conditions + tuple(_encoding(form, name))))),)
                  + tuple(rest))
        made = write_layer(package, shape, chain, root)
    else:
        group = _group_in(text, shape, chain)
        if before.where == 'slot':
            layer = _group_in(text, shape, chain + [before.slot])
            text = _remove_span(text, layer, group.start, group.end)
        elif before.where == 'attribute':
            text = _remove_line(text, group, _turtle_name(text, SH['or']))
        alternatives = tuple(_alternative(f, name) for f in forms)
        group = _group_in(text, shape, chain)
        if len(alternatives) == 1:
            text = _add_line(text, group, _turtle_name(text, SH.property),
                             f'[ {_layer(alternatives[0], name)} ]')
        elif alternatives:
            from .constrain import _indent_of

            text = _set(text, group, _turtle_name(text, SH['or']),
                        render(alternatives, name, _indent_of(text, group.start)))
        made = None
    if made is None:
        after = read_value(package, text, shape, chain)
        if not _same(after, Value(forms, ''), prefixes_of(package), name):
            raise PackageError('the value would not read back as meant; nothing was changed')
        _write_verified(holder, text)
        group = _group_in(text, shape, chain)
        made = {'file': holder, 'line': text.count('\n', 0, group.start) + 1}
    return made


# --- the edits the panel asks for ------------------------------------------------------------

# A single value's list, the same kind of thing many times.
LISTS = {'hasValue': 'hasValueList', 'hasObject': 'hasObjectList'}
# What the value picker sets: what kind of thing the value is.
TYPE = ('sh:class', 'sh:datatype', 'sh:nodeKind')


def _unchanged(package, shape, chain):
    holder = package.index('shapes').file_for(URIRef(str(shape)))
    return {'file': holder, 'line': 0, 'changed': False}


def set_type(package, shape, chain, value):
    """What the value picker says the value is -- {'datatype'}, {'valueClass'}
    or {'kind': 'any'} -- in every form at once; ranges, lengths and patterns
    stay. Checked as a new attribute's value is (constrain._value_layer)."""
    from .constrain import _attribute, _resolve, _turtle_name, _value_layer
    from ..ngsild.kinds import is_relationship

    holder = package.index('shapes').file_for(URIRef(str(shape)))
    if holder is None:
        raise PackageError(f'{shape} is not in any shapes file')
    with open(holder, encoding='utf-8') as handle:
        text = handle.read()
    current = read_value(package, text, str(shape), list(chain))
    if not current.editable:
        raise PackageError(f'the value of {chain[-1]} is edited in the .ttl: {current.reason}')
    if not current.forms:
        raise PackageError(f'{chain[-1]} has no value layer; add a form in the value editor')
    connectives = sorted({f'sh:{n.op}' for f in current.forms
                          for n in normalize_root(f.root).children[1:] if isinstance(n, Op)})
    if connectives:
        # One type beside an expression would contradict it ("text" and
        # "any of: number"): what it is, is said in the expression.
        raise PackageError(f'the value of {chain[-1]} is an expression ({", ".join(connectives)}): '
                           f'change it in the value editor')
    entry = _attribute(package, str(_resolve(package, chain[-1])))
    relationship = any(is_relationship(f.kind) for f in current.forms)
    pairs = [] if value.get('kind') == 'any' else _value_layer(
        package, 'Relationship' if relationship else 'Property',
        value.get('datatype') or None, value.get('valueClass') or None, entry.label)
    wanted = [('sh:' + str(p)[len(str(SH)):], _turtle_name(text, o)) for p, o in pairs
              if p not in (SH.minCount, SH.maxCount, SH.nodeKind)]
    forms = []
    for form in current.forms:
        own, *rest = normalize_root(form.root).children
        kept = [(k, v) for k, v in own.conditions if k not in TYPE]
        root = Op('and', (Leaf(tuple(sorted(kept + wanted))),) + tuple(rest))
        # As the picker always wrote it: a vocabulary term or an entity is an
        # IRI, and says so (sh:nodeKind sh:IRI); a datatype says it is a
        # literal by itself, and "any value" says nothing.
        forms.append(replace(form, root=root, encoded=any(k == 'sh:class' for k, _ in wanted)))
    return write_value(package, shape, chain, tuple(forms))


def edit_value(package, shape, chain, action):
    """One change to the value's forms, or to what one form must be.

    action: {'op': 'lists' (value: bool) | 'addform' (kind) | 'removeform' | 'formkind' (kind) |
    'empty' (value: bool) | any edit of cooked/expression.py, 'form': index}.
    """
    holder = package.index('shapes').file_for(URIRef(str(shape)))
    if holder is None:
        raise PackageError(f'{shape} is not in any shapes file')
    with open(holder, encoding='utf-8') as handle:
        text = handle.read()
    value = read_value(package, text, str(shape), list(chain))
    if not value.editable:
        raise PackageError(f'the value of {chain[-1]} is edited in the .ttl: {value.reason}')
    forms = list(value.forms)
    what = action.get('op')

    def at():
        index = int(action.get('form') if action.get('form') is not None else -1)
        if not 0 <= index < len(forms):
            raise PackageError('that form is not there any more')
        return index

    def payload_for(kind):
        if kind not in KINDS:
            raise PackageError(f'{kind} is not a kind a value may take here')
        return PAYLOAD_NAME[kind]

    if what == 'lists':
        # "Allow a list too": the one value's conditions, for each item of a
        # list that may be empty -- an OPC UA array. Off: the lists go.
        scalars = [f for f in forms if not f.is_list]
        if action.get('value'):
            if any(f.is_list for f in forms):
                return _unchanged(package, shape, chain)
            if len(scalars) != 1 or scalars[0].payload not in LISTS:
                raise PackageError('a list is allowed beside one single value')
            one = scalars[0]
            forms.append(Form(payload=LISTS[one.payload], root=one.root, may_be_empty=True))
        else:
            if not any(f.is_list for f in forms):
                return _unchanged(package, shape, chain)
            if not scalars:
                raise PackageError('the value is only a list: there is no single value to keep')
            forms = scalars
    elif what == 'addform':
        payload = payload_for(action.get('kind'))
        forms.append(Form(payload=payload, root=Op('and', (Leaf(),)),
                          may_be_empty=NGSILD + payload in LIST_PAYLOADS))
    elif what == 'removeform':
        del forms[at()]
    elif what == 'formkind':
        index = at()
        payload = payload_for(action.get('kind'))
        forms[index] = replace(forms[index], payload=payload,
                               may_be_empty=NGSILD + payload in LIST_PAYLOADS and
                               forms[index].may_be_empty)
    elif what == 'empty':
        index = at()
        if not forms[index].is_list:
            raise PackageError('only a list may be empty')
        forms[index] = replace(forms[index], may_be_empty=bool(action.get('value')))
    else:
        index = at()
        forms[index] = replace(forms[index], root=_apply(
            forms[index].root, action, _conditions(package, text, action)))
    return write_value(package, shape, chain, tuple(forms))


# --- said ----------------------------------------------------------------------------------
#
# One wording for a value, wherever it is shown: the type and shape pages, the
# constraints view, the value editor. Four describers had grown, and said the
# same value four ways ("number · 0 – 100" here, "0 – 100 · any of: number
# (double) | number (integer)" there).

def _kind(form):
    return 'Relationship' if form.payload in ('hasObject', 'hasObjectList') else 'Property'


def member_text(root, kind='Property'):
    """What the value (or each item of a list) must be: `number · 0 – 100`.

    Its own conditions first, then its connectives -- except a choice between
    number types only ("double or integer"), which is what "a number" means
    to the reader, and is said so.
    """
    from .expression import clause, words
    from .typepage import NUMBER_TYPES

    own, *rest = normalize_root(root).children
    conditions = dict(own.conditions)
    kept = []
    for node in rest:
        numbers = isinstance(node, Op) and node.op == 'or' and all(
            isinstance(c, Leaf) and set(dict(c.conditions)) == {'sh:datatype'} and
            dict(c.conditions)['sh:datatype'] in NUMBER_TYPES for c in node.children)
        if numbers and 'sh:datatype' not in conditions:
            conditions['sh:datatype'] = dict(node.children[0].conditions)['sh:datatype']
        else:
            kept.append(node)
    parts = [words(Leaf(tuple(sorted(conditions.items()))), kind, tag=False)] \
        if conditions else []
    parts += [clause(node, kind) for node in kept]
    return ' · '.join(parts) or ('an entity' if kind == 'Relationship' else 'any value')


def form_words(form):
    """One form with its kind: `a list of values (may be empty): number`."""
    tail = ' (may be empty)' if form.may_be_empty else ''
    return f'{WORDS.get(form.payload, form.payload)}{tail}: {member_text(form.root, _kind(form))}'


def say(value):
    """The whole value in words, as every view shows it.

    One plain value says its conditions; a value or a list of the same, "…,
    or a list of them"; anything else, each form with its kind.
    """
    forms = value.forms
    if not forms:
        return 'any value'
    plain = ('hasValue', 'hasObject')
    if len(forms) == 1:
        form = forms[0]
        if form.payload in plain:
            return member_text(form.root, _kind(form))
        if form.is_list:
            tail = ' (possibly empty)' if form.may_be_empty else ''
            return f'a list of: {member_text(form.root, _kind(form))}{tail}'
        return form_words(form)
    scalars = [f for f in forms if not f.is_list]
    lists = [f for f in forms if f.is_list]
    if len(scalars) == 1 and len(lists) == 1 and scalars[0].payload in plain:
        one, many = scalars[0], lists[0]
        tail = ' (possibly empty)' if many.may_be_empty else ''
        if normalize_root(one.root) == normalize_root(many.root):
            return f'{member_text(one.root, _kind(one))}, or a list of them{tail}'
        return (f'{member_text(one.root, _kind(one))}, '
                f'or a list of: {member_text(many.root, _kind(many))}{tail}')
    return ', or '.join(form_words(f) for f in forms)


def to_payload(value):
    """The value as the panel draws it."""
    return {'forms': [{'kind': f.kind, 'payload': f'ngsi-ld:{f.payload}', 'list': f.is_list,
                       'mayBeEmpty': f.may_be_empty, 'said': form_words(f),
                       'expression': to_json(normalize_root(f.root), _kind(f))}
                      for f in value.forms],
            'said': say(value), 'editable': value.editable, 'reason': value.reason,
            'kinds': list(KINDS), 'lists': lists_switch(value)}


def lists_switch(value):
    """Which way the 'lists' edit goes from here: 'single' -- one value, which
    may also become a list of the same ("Allow a list too"); 'allowed' -- one
    value or a list of it ("One value only"); '' -- neither."""
    if not value.editable:
        return ''
    scalars = [f for f in value.forms if not f.is_list]
    lists = [f for f in value.forms if f.is_list]
    if len(value.forms) == 1 and scalars and scalars[0].payload in LISTS:
        return 'single'
    if len(scalars) == 1 and lists and scalars[0].payload in LISTS:
        return 'allowed'
    return ''
