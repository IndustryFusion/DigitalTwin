"""One attribute, every shape that constrains it: what holds, all told.

SHACL has no "the" shape of a type. Every shape that targets a Machine is
evaluated against every Machine, and its constraints are CONJOINED: an
entity conforms only if it satisfies all of them. Two shapes saying
`hasPressure maxCount 1` and `minCount 1`, or `< 100` and `< 200`, together
say "required, one, below 100". The type page used to show one row per
shape, so the reader did that arithmetic.

`accumulate` groups the rows of one attribute into one, whose presence and
value are what holds when every unconditional shape is applied; each
contributing shape stays beneath it with what it says, what of that has no
effect (a bound weaker than another's), and the condition it applies under
when it does not apply always. Contradictions are said: two datatypes no
literal can have at once, bounds that admit nothing.
"""

from .typepage import presence, value_text

COUNTS = ('sh:minCount', 'sh:maxCount')
LOWER = ('sh:minInclusive', 'sh:minExclusive')
UPPER = ('sh:maxInclusive', 'sh:maxExclusive')
ONE_OF = ('sh:datatype', 'sh:class', 'sh:nodeKind', 'sh:pattern')
TESTED_RANK = {'untested': 0, 'never fired': 1, 'fires only': 2, 'both ways': 3}
WORDS = {'sh:minCount': 'at least', 'sh:maxCount': 'at most',
         'sh:minInclusive': '≥', 'sh:minExclusive': '>',
         'sh:maxInclusive': '≤', 'sh:maxExclusive': '<'}


def _number(text):
    try:
        return float(str(text).split('^^')[0].strip('"'))
    except ValueError:
        return None


def _layers(row):
    attribute, value = {}, {}
    for parameter in row.get('parameters', []):
        target = attribute if parameter['layer'] == 'attribute' else value
        target.setdefault(parameter['parameter'], parameter['value'])
    return attribute, value


def _bound(rows_params, names, pick):
    """The binding bound among `names` across contributions: (name, value,
    shape) -- `pick` max for lower bounds, min for upper. At an equal value
    an exclusive bound is the stricter one."""
    best = None
    for params, shape in rows_params:
        for name in names:
            number = _number(params.get(name, ''))
            if number is None:
                continue
            exclusive = name.endswith('Exclusive')
            key = (number, exclusive) if pick == 'max' else (-number, exclusive)
            if best is None or key > best[0]:
                best = (key, name, params[name], shape)
    return best[1:] if best else None


def _effective(contributions):
    """(attribute params, value params, notes) when all of them hold."""
    attribute_rows = [(_layers(c)[0], c['shapeName']) for c in contributions]
    value_rows = [(_layers(c)[1], c['shapeName']) for c in contributions]
    attribute, value, notes = {}, {}, []
    for layer_rows, out in ((attribute_rows, attribute), (value_rows, value)):
        low = _bound(layer_rows, ('sh:minCount',), 'max')
        high = _bound(layer_rows, ('sh:maxCount',), 'min')
        if low:
            out['sh:minCount'] = low[1]
        if high:
            out['sh:maxCount'] = high[1]
    low = _bound(value_rows, LOWER, 'max')
    high = _bound(value_rows, UPPER, 'min')
    if low:
        value[low[0]] = low[1]
    if high:
        value[high[0]] = high[1]
    if low and high:
        lo, hi = _number(low[1]), _number(high[1])
        if lo > hi or (lo == hi and (low[0].endswith('Exclusive') or
                                     high[0].endswith('Exclusive'))):
            notes.append(f'{WORDS[low[0]]} {low[1]} ({low[2]}) and {WORDS[high[0]]} '
                         f'{high[1]} ({high[2]}) admit no value')
    for name in ONE_OF:
        seen = []
        for params, shape in value_rows:
            if name in params and params[name] not in [v for v, _ in seen]:
                seen.append((params[name], shape))
        if seen:
            value[name] = seen[0][0]
        if len(seen) > 1:
            said = ' and '.join(f'{v} ({s})' for v, s in seen)
            notes.append(f'a value must be {said} at once' +
                         (': no literal has two datatypes' if name == 'sh:datatype' else ''))
    for layer, params in (('attribute', attribute), ('value', value)):
        lo, hi = _number(params.get('sh:minCount', '')), _number(params.get('sh:maxCount', ''))
        if lo is not None and hi is not None and lo > hi:
            notes.append(f'{layer}: at least {lo:g} and at most {hi:g} admit nothing')
    return attribute, value, notes


def _no_effect(contribution, attribute, value):
    """What this contribution says that the others already outdo."""
    own_attribute, own_value = _layers(contribution)
    found = []
    for params, effective in ((own_attribute, attribute), (own_value, value)):
        for name in ('sh:minCount',) + LOWER:
            mine = _number(params.get(name, ''))
            if mine is None:
                continue
            best_name = next((n for n in (('sh:minCount',) if name == 'sh:minCount'
                                          else LOWER) if n in effective), None)
            if best_name and (best_name, effective[best_name]) != (name, params[name]):
                found.append(f'{name} {params[name]}')
        for name in ('sh:maxCount',) + UPPER:
            mine = _number(params.get(name, ''))
            if mine is None:
                continue
            best_name = next((n for n in (('sh:maxCount',) if name == 'sh:maxCount'
                                          else UPPER) if n in effective), None)
            if best_name and (best_name, effective[best_name]) != (name, params[name]):
                found.append(f'{name} {params[name]}')
    return found


def _list_notes(package, basis, value):
    """An sh:in list in one shape checked against what the others say about
    the same value; two lists sharing nothing admit nothing."""
    from .listcheck import list_conflicts

    lists = [(m['inList']['items'], m['shapeName']) for m in basis if m.get('inList')]
    if not lists or package is None:
        return []
    notes = []
    shared = list(lists[0][0])
    for items, _ in lists[1:]:
        shared = [i for i in shared if i in items]
    if len(lists) > 1 and not shared:
        notes.append('the sh:in lists of ' + ' and '.join(s for _, s in lists) +
                     ' share no value: nothing can be given')
    return notes + list_conflicts(package, value, shared or lists[0][0])


def accumulate(rows, package=None):
    """Rows of the type page, one per (shape, attribute) -> one per attribute.

    A row constrained by a single shape is returned as it was. A row
    constrained by several gets `contributions` (the per-shape rows, each
    with `noEffect`), its presence and value as they hold when all apply,
    and `notes` for contradictions."""
    groups, order = {}, []
    for row in rows:
        key = tuple(row.get('path') or [row['label']])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    out = []
    for key in order:
        members = groups[key]
        if len(members) == 1:
            out.append(members[0])
            continue
        always = [m for m in members if not m.get('condition')]
        basis = always or members
        attribute, value, notes = _effective(basis)
        notes += _list_notes(package, basis, value)
        for member in members:
            member['noEffect'] = _no_effect(member, attribute, value) \
                if member in always and len(always) > 1 else []
        first = basis[0]
        raw = [tuple(v.split(' ', 1)) if ' ' in v else (v, '')
               for m in basis for v in m.get('verbatim', [])]
        merged = dict(first)
        merged.update({
            'presence': presence(attribute.get('sh:minCount'), attribute.get('sh:maxCount')),
            'value': value_text(first['kind'], value, [r for r in raw if r[0] == 'sh:or']),
            'verbatim': sorted({v for m in basis for v in m.get('verbatim', [])}),
            'violations': sorted({v for m in members for v in m['violations']}),
            'tested': max((m.get('tested', 'untested') for m in members),
                          key=lambda t: TESTED_RANK.get(t, 0)),
            'contributions': members,
            'notes': notes,
            'shapes': [m['shapeName'] for m in members],
            # Edited through one of its shapes: the page asks which.
            'inherited': not any(not m.get('inherited') for m in members),
            'valueEditable': any(m.get('valueEditable') and not m.get('inherited')
                                 for m in members),
            'condition': '' if always else first.get('condition', ''),
            'via': '' if any(not m.get('via') for m in members) else first.get('via', ''),
        })
        out.append(merged)
    return out
