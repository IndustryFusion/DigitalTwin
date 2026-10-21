"""Completion and hover for a SPARQL query of this package.

Completion reads what is being typed and what comes before it:

  * after PREFIX -- the package's namespaces, written out (`iffBaseEntities:
    <https://…>`);
  * `prefix:` -- that namespace's terms: classes, attributes (with Property or
    Relationship), individuals; a prefix the query has not declared yet is
    declared by the completion itself (its PREFIX line is added);
  * an attribute where a predicate goes also comes as the whole NGSI-LD step,
    `iffBaseEntities:hasState [ ngsild:hasValue ?state ]` -- hasValue for a
    Property, hasObject for a Relationship;
  * `?` or `$` -- the query's variables, and $this;
  * inside `[ … ]` after an attribute -- first the payload its kind reads
    through (ngsild:hasValue for a Property, hasObject for a Relationship, …),
    then the instance's metadata (observedAt, datasetId, unitCode) and the
    sub-attributes its shape nests, each as its own step;
  * anything else -- keywords, built-in functions, and the prefixes.
"""

from .lexer import (FUNCTIONS, KEYWORDS, at, code_tokens, declared_prefixes,
                    prologue_end)
from ..ngsild.kinds import PAYLOAD_NAME as LAYER
from ..ngsild.kinds import is_relationship
from .terms import NGSILD

WORD = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-?$%')
VALUE_KINDS = ('Property', 'GeoProperty')     # the kinds with a unitCode
KIND = {'class': 'class', 'attribute': 'property', 'individual': 'enum', 'ngsild': 'keyword',
        'property': 'property'}


def _item(label, insert, start, end, kind, detail='', doc='', sort='5', snippet=False,
          edits=(), retrigger=False, filter_text=None):
    return {'label': label, 'insert': insert, 'start': start, 'end': end, 'kind': kind,
            'detail': detail, 'documentation': doc, 'sort': f'{sort}{label.lower()}',
            'snippet': snippet, 'edits': list(edits), 'retrigger': retrigger,
            'filter': filter_text or label}


def _word(text, offset):
    start = offset
    while start > 0 and text[start - 1] in WORD:
        start -= 1
    return start, text[start:offset]


def _declare(text, prefix, namespace):
    """The edit that declares a prefix: a PREFIX line where the others are."""
    at_offset = prologue_end(text)
    return (at_offset, at_offset, f'PREFIX {prefix}: <{namespace}>\n')


def _predicate_position(code, start):
    """Is the word at `start` where a predicate goes (after a subject, `;`)?"""
    before = [t for t in code if t.end <= start]
    if not before:
        return False
    last = before[-1]
    if last.text == ';':
        return True
    if last.kind in ('var', 'pname', 'iri') or last.text == ']':
        earlier = before[-2] if len(before) > 1 else None
        return earlier is None or earlier.text in ('.', '{', ';', '}') or \
            (earlier.kind == 'comment')
    return False


def _variable_for(local):
    """hasCartridge -> cartridge: the name a value is usually given."""
    if local.startswith('has') and len(local) > 3:
        return local[3:4].lower() + local[4:]
    return local


def _owner(code, start, declared, terms):
    """The attribute whose `[ … ]` the cursor is in, when it is at a
    predicate position there: (term, its written prefix:local), else None."""
    before = [t for t in code if t.end <= start]
    depth = 0
    for index in range(len(before) - 1, -1, -1):
        token = before[index]
        if token.text == ']':
            depth += 1
        elif token.text == '[':
            if depth:
                depth -= 1
                continue
            if index == 0 or before[-1].text not in ('[', ';'):
                return None
            owner = before[index - 1]
            if owner.kind != 'pname':
                return None
            prefix, _, local = owner.text.partition(':')
            namespace = declared.get(prefix) or terms.namespaces.get(prefix)
            term = terms.terms.get((namespace or '') + local)
            if term is None or term.kind != 'attribute' or term.attribute_kind not in LAYER:
                return None
            return term, owner.text
        elif token.text in ('{', '}') and not depth:
            return None
    return None


def _inside(text, start, offset, word, term, declared, terms):
    """What goes inside an attribute's `[ … ]`."""
    edits = []
    ngsild = next((p for p, n in declared.items() if n == NGSILD), None)
    if ngsild is None:
        ngsild = 'ngsild'
        edits.append(_declare(text, 'ngsild', NGSILD))
    variable = _variable_for(term.local)
    payload = LAYER[term.attribute_kind]
    said = 'target' if is_relationship(term.attribute_kind) else 'value'
    items = [_item(f'{ngsild}:{payload} ?{variable}', f'{ngsild}:{payload} ${{1:?{variable}}}',
                   start, offset, 'snippet', f'the {said} of this {term.attribute_kind}',
                   sort='0', snippet=True, edits=edits, filter_text=f'{ngsild}:{payload}')]
    metadata = [('observedAt', '?observedAt', 'when this instance was observed'),
                ('datasetId', '?datasetId', 'which instance, when there are several')]
    if term.attribute_kind in VALUE_KINDS:
        metadata.append(('unitCode', '?unit', 'the unit of the value'))
    for name, var, doc in metadata:
        items.append(_item(f'{ngsild}:{name} {var}', f'{ngsild}:{name} ${{1:{var}}}', start,
                           offset, 'snippet', doc, sort='1', snippet=True, edits=edits,
                           filter_text=f'{ngsild}:{name}'))
    for sub_iri in term.subs:
        sub = terms.terms.get(sub_iri)
        known = terms.prefix_for(sub_iri)
        if sub is None or known is None or sub.attribute_kind not in LAYER:
            continue
        prefix = next((p for p, n in declared.items() if n == known[1]), known[0])
        sub_edits = list(edits)
        if prefix not in declared:
            sub_edits.append(_declare(text, prefix, known[1]))
        name = f'{prefix}:{sub.local}'
        sub_var = _variable_for(sub.local)
        sub_payload = LAYER[sub.attribute_kind]
        items.append(_item(
            f'{name} [ {ngsild}:{sub_payload} ?{sub_var} ]',
            f'{name} [ {ngsild}:{sub_payload} ${{1:?{sub_var}}} ]', start, offset, 'snippet',
            f'a sub-attribute of {term.local} ({sub.attribute_kind})', sort='2', snippet=True,
            edits=sub_edits, filter_text=name))
    return items


def complete(text, offset, terms):
    """[item] for the cursor at `offset`; each item says what it replaces."""
    start, word = _word(text, offset)
    code = code_tokens(text)
    before = [t for t in code if t.end <= start]
    declared = declared_prefixes(text)
    items = []

    owner = _owner(code, start, declared, terms)
    if owner is not None and not word.startswith(('?', '$')):
        items.extend(_inside(text, start, offset, word, owner[0], declared, terms))
        if ':' not in word:
            return items

    if before and before[-1].kind == 'name' and before[-1].upper == 'PREFIX':
        for prefix, namespace in sorted(terms.namespaces.items()):
            if prefix in declared:
                continue
            items.append(_item(f'{prefix}:', f'{prefix}: <{namespace}>', start, offset,
                               'module', namespace, sort='1'))
        return items

    if word.startswith(('?', '$')):
        names = {t.text[1:] for t in code if t.kind == 'var' and t.start != start}
        names.add('this')
        for name in sorted(names):
            items.append(_item(f'{word[0]}{name}', f'{word[0]}{name}', start, offset,
                               'variable', '$this: each node the shape selects'
                               if name == 'this' else 'variable', sort='1'))
        return items

    if ':' in word:
        prefix, _, local = word.partition(':')
        namespace = declared.get(prefix) or terms.namespaces.get(prefix)
        if not namespace:
            return []
        edits = [] if prefix in declared else [_declare(text, prefix, namespace)]
        predicate = _predicate_position(code, start)
        for term in sorted(terms.in_namespace(namespace), key=lambda t: t.local.lower()):
            name = f'{prefix}:{term.local}'
            doc = '\n\n'.join(p for p in (term.comment, f'<{term.iri}>') if p)
            rank = {'attribute': '1', 'class': '2', 'individual': '3'}.get(term.kind, '4')
            items.append(_item(name, name, start, offset, KIND.get(term.kind, 'text'),
                               term.detail, doc, sort=rank, edits=edits))
            if predicate and term.kind == 'attribute' and term.attribute_kind in LAYER:
                ngsild = next((p for p, n in declared.items() if n == NGSILD), None)
                step_edits = list(edits)
                if ngsild is None:
                    ngsild = 'ngsild'
                    step_edits.append(_declare(text, 'ngsild', NGSILD))
                variable = _variable_for(term.local)
                layer = LAYER[term.attribute_kind]
                items.append(_item(
                    f'{name} [ {ngsild}:{layer} ?{variable} ]',
                    f'{name} [ {ngsild}:{layer} ${{1:?{variable}}} ]', start, offset,
                    'snippet', f'{term.attribute_kind}: its '
                    f'{"target" if is_relationship(term.attribute_kind) else "value"}',
                    doc, sort=rank, snippet=True, edits=step_edits, filter_text=name))
        return items

    upper = word.upper()
    for keyword in sorted(KEYWORDS):
        if keyword.startswith(upper):
            items.append(_item(keyword, keyword, start, offset, 'keyword', sort='2'))
    for function in sorted(FUNCTIONS):
        if function.startswith(upper):
            items.append(_item(f'{function}()', f'{function}($1)', start, offset, 'function',
                               'built-in function', sort='3', snippet=True,
                               filter_text=function))
    for prefix, namespace in sorted(terms.namespaces.items()):
        if prefix.lower().startswith(word.lower()):
            edits = [] if prefix in declared else [_declare(text, prefix, namespace)]
            items.append(_item(f'{prefix}:', f'{prefix}:', start, offset, 'module', namespace,
                               sort='1' if prefix in declared else '4', edits=edits,
                               retrigger=True))
    return items


def hover(text, offset, terms):
    """Markdown for what is under the cursor: a name's full IRI and what the
    knowledge says about it."""
    token = at(text, offset)
    if token is None:
        return None
    if token.kind == 'pname':
        prefix, _, local = token.text.partition(':')
        namespace = declared_prefixes(text).get(prefix) or terms.namespaces.get(prefix)
        if not namespace:
            return f'`{prefix}:` is not a prefix this query or the package declares'
        iri = namespace + local
    elif token.kind == 'iri':
        iri = token.text[1:-1]
    elif token.kind == 'var' and token.text[1:] == 'this':
        return ('**$this** — each node the shape selects, bound by the SHACL engine before '
                'the query runs (one run per node)')
    else:
        return None
    term = terms.terms.get(iri)
    if term is None:
        said = ('not declared in the knowledge' if terms.own(iri) else
                'a term from outside this package')
        return f'`<{iri}>`\n\n{said}'
    lines = [f'**{term.local}** · {term.detail}', f'`<{iri}>`']
    if term.comment:
        lines.append(term.comment)
    if term.kind == 'attribute' and term.attribute_kind in LAYER:
        said = 'target' if is_relationship(term.attribute_kind) else 'value'
        lines.append(f'Read its {said} as `{term.local} [ ngsild:{LAYER[term.attribute_kind]} '
                     f'?{_variable_for(term.local)} ]` — the object is an attribute instance')
        if term.subs:
            lines.append('Sub-attributes: ' + ', '.join(
                f'`{s.rsplit("/", 1)[-1].rsplit("#", 1)[-1]}`' for s in term.subs))
        if iri not in terms.compiled:
            lines.append('⚠ No shape nests its payload: shacl2flink would read it as a plain '
                         'triple')
    elif term.kind in ('attribute', 'property'):
        lines.append(f'A plain property, not an NGSI-LD attribute: its value is the object '
                     f'itself — `?x {term.local} ?value`')
    return '\n\n'.join(lines)
