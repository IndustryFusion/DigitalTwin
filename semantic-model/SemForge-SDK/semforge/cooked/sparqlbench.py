"""The SPARQL workbench: a shape's SPARQL query, the data it runs over, and
what it returns -- edited, run and saved from one page.

What a SPARQL constraint sees is not the case file. Validation (see
validate/orchestrator.py) expands the rules to a fixpoint over the data plus
the knowledge, builds the shape's data view (`current` keeps the latest
observation), adds the knowledge again, and pyshacl -- in advanced mode --
applies the view's rules ONCE MORE, additively, before any constraint runs.
`data_graph` repeats exactly those steps, so a query here returns what it
returns in `semforge test`, and an unguarded rule shows the extra node it
really makes.

A constraint runs once per focus node with `$this` bound, and every solution
is a violation; a rule's CONSTRUCT runs the same way and adds its triples.
"""

import re
import time

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import SH

from ..errors import PackageError
from ..validate.normalise import curie, local

MAIN = '@main'

# (predicate holding the bracket, parameter holding the query) per kind.
KINDS = {'constraint': ('sh:sparql', 'sh:select'), 'rule': ('sh:rule', 'sh:construct')}

# What pyshacl refuses in a constraint body, or reads differently than it looks.
REFUSED = [
    (re.compile(r'\bMINUS\b', re.I), 'MINUS is not allowed in a SHACL-SPARQL query'),
    (re.compile(r'\bVALUES\b', re.I), 'VALUES is not allowed in a SHACL-SPARQL query'),
    (re.compile(r'\bSERVICE\b', re.I), 'SERVICE is not allowed in a SHACL-SPARQL query'),
    (re.compile(r'\bAS\s+[?$]this\b', re.I), '$this cannot be bound with AS'),
    (re.compile(r'\$shapesGraph\b'), '$shapesGraph is not supported by pyshacl'),
    (re.compile(r'\$currentShape\b'), '$currentShape is not supported here'),
]


# --- where the queries are written -----------------------------------------------------

def _literal(raw):
    """The value of a Turtle literal token, exactly as a parser reads it."""
    graph = Graph().parse(data=f'<urn:x:s> <urn:x:p> {raw} .', format='turtle')
    return str(next(graph.objects()))


class _Holder:
    """One `[ … ]` holding a SPARQL body: where each of its values is written.

    `parameters[name] = (start, end, token)`, offsets into the file -- the
    same shape rdfio.blocks uses, so blocks.set_parameter can replace a value.
    Read here rather than with rdfio.blocks._scan_group, which does not keep
    string literals and pairs `a sh:SPARQLConstraint` as a parameter."""

    def __init__(self, text, start, end, keys):
        from ..rdfio.turtle_index import _skip_string

        self.start, self.end, self.parameters = start, end, {}
        i = start + 1
        while i < end - 1:
            char = text[i]
            if char in '"\'':
                i = _skip_string(text, i)
                continue
            if char == '#':
                newline = text.find('\n', i)
                i = end if newline < 0 else newline
                continue
            key = next((k for k in keys if text.startswith(k, i)
                        and not (text[i - 1].isalnum() or text[i - 1] in ':_')), None)
            if key is None:
                i += 1
                continue
            j = i + len(key)
            while j < end and text[j] in ' \t\r\n':
                j += 1
            if j < end and text[j] in '"\'':
                value_end = _skip_string(text, j)
            else:
                value_end = j
                while value_end < end and not text[value_end].isspace() \
                        and text[value_end] not in ';,]':
                    value_end += 1
            self.parameters[key] = (j, value_end, text[j:value_end])
            i = value_end

    def parameter(self, name):
        return self.parameters.get(name)


VALUE_KEYS = ('sh:select', 'sh:construct', 'sh:message', 'sh:severity')


def _bodies(package, shape):
    """([(kind, holder)], text, path) -- a shape's SPARQL holders, in file order."""
    from ..rdfio.blocks import _match_bracket

    index = package.index('shapes')
    path, block = index.block_for(URIRef(shape))
    if path is None:
        raise PackageError(f'{shape} is not a shape written in this package')
    text = index.source_of(path)
    found = []
    for kind, (predicate, _) in KINDS.items():
        pattern = rf'(?<![\w:]){re.escape(predicate)}\s*\['
        for match in re.finditer(pattern, text[block.start:block.end]):
            start = block.start + match.end() - 1
            end = _match_bracket(text, start, block.end)
            found.append((start, kind, _Holder(text, start, end, VALUE_KEYS)))
    found.sort(key=lambda item: item[0])
    return [(kind, holder) for _, kind, holder in found
            if holder.parameter(KINDS[kind][1])], text, path


def _severity_label(package, text, token):
    """A severity as written (`base:severityCritical`), as a reader says it --
    the prefix resolved the way the file declares it."""
    from ..rdfio.turtle_index import terms
    from .severity import describe

    iri = next((t.iri for t in terms(text) if t.raw == token and not t.quoted),
               token.strip('<>'))
    return describe(package, iri)['label']


def holders(package, shape):
    """Every SPARQL query on a shape, in the order the file writes them."""
    bodies, text, path = _bodies(package, shape)
    out = []
    for position, (kind, group) in enumerate(bodies):
        start, _, raw = group.parameter(KINDS[kind][1])
        message = group.parameter('sh:message')
        severity = group.parameter('sh:severity')
        out.append({
            'index': position, 'kind': kind, 'query': _literal(raw),
            'message': _literal(message[2]) if message else '',
            'severity': severity[2].strip() if severity else '',
            'severityLabel': _severity_label(package, text, severity[2].strip())
            if severity else '',
            'file': path, 'line': text.count('\n', 0, start) + 1})
    return out


def _holder_node(package, shape, kind, query):
    """The holder in the parsed graph whose query is this one: graph order is
    not file order, so it is matched by its text."""
    predicate, key = (SH.sparql, SH.select) if kind == 'constraint' else (SH.rule, SH.construct)
    for node in package.shapes.objects(URIRef(shape), predicate):
        if str(package.shapes.value(node, key) or '') == query:
            return node
    return None


def _prefix_lines(package, holder):
    """sh:prefixes declarations, as pyshacl puts them in front of the query."""
    graph, lines = package.shapes, []
    if holder is None:
        return lines
    for prefixes in graph.objects(holder, SH.prefixes):
        for declaration in graph.objects(prefixes, SH.declare):
            prefix = graph.value(declaration, SH.prefix)
            namespace = graph.value(declaration, SH.namespace)
            if prefix is not None and namespace is not None:
                lines.append(f'PREFIX {prefix}: <{namespace}>')
    return lines


# --- which data ------------------------------------------------------------------------

def sources(package, shape):
    """Main, then the cases this shape reaches, then every other case."""
    from ..expect.store import compose, load_expectations
    from ..validate.applicable import focus_nodes

    reached, others = [], []
    for example in load_expectations(package.path).examples:
        try:
            graph = compose(package, example)
        except PackageError:
            continue
        nodes = focus_nodes(URIRef(shape), package.shapes, graph, package.knowledge)
        entry = {'id': example.path, 'label': example.path, 'expect': example.expect,
                 'focus': len(set(nodes))}
        (reached if entry['focus'] else others).append(entry)
    model_focus = len(set(focus_nodes(URIRef(shape), package.shapes, package.model,
                                      package.knowledge)))
    return [{'id': MAIN, 'label': 'Main', 'expect': '', 'focus': model_focus}] + reached + others


def data_graph(package, shape, source, kind='constraint'):
    """(graph the query runs on, focus nodes, stats) -- validation's own steps.

    A constraint runs on the shape's data VIEW (for `current`, the latest
    observation of each attribute) plus the knowledge, after pyshacl's extra
    rule pass. A rule runs before any view, on every observation: here, the
    rules' fixpoint -- what each rule sees once the others are done."""
    import pyshacl

    from ..expect.store import compose
    from ..ngsild.views import build_view
    from ..rules import run_rules
    from ..validate import shapes as shape_views
    from ..validate.applicable import focus_nodes
    from .casepage import _find_case

    base = package.model if source in ('', MAIN, None) else \
        compose(package, _find_case(package, source))
    run = run_rules(base, package.shapes, package.knowledge)
    view = shape_views.view_of(package.shapes, URIRef(shape))
    if kind == 'rule':
        data = run.graph
        for graph in (package.shapes, package.knowledge, package.model):
            for prefix, namespace in graph.namespaces():
                data.bind(prefix, namespace, override=False)
        focus = sorted(set(focus_nodes(URIRef(shape), package.shapes, data,
                                       package.knowledge)), key=str)
        return data, focus, {'view': 'rules', 'ruleIterations': run.iterations,
                             'lastRulePass': 0, 'knowledge': len(package.knowledge),
                             'graph': 'the rules\' fixpoint, every observation (rules run '
                                      'before the view is built)', 'base': base}
    viewed, _ = build_view(run.graph, view)

    data = Graph()
    for graph in (package.shapes, package.knowledge, package.model):
        for prefix, namespace in graph.namespaces():
            data.bind(prefix, namespace, override=False)
    for triple in viewed:
        data.add(triple)
    for triple in package.knowledge:
        data.add(triple)

    view_shapes = shape_views.partition(package.shapes).get(view, [URIRef(shape)])
    subset = Graph()
    for triple in shape_views.subgraph_for(package.shapes, view_shapes):
        subset.add(triple)
    before = len(data)
    pyshacl.shacl_rules(data, shacl_graph=subset, advanced=True, inplace=True,
                        do_owl_imports=False)

    focus = sorted(set(focus_nodes(URIRef(shape), package.shapes, data, package.knowledge)),
                   key=str)
    stats = {'view': view.value, 'ruleIterations': run.iterations,
             'lastRulePass': len(data) - before, 'knowledge': len(package.knowledge),
             'graph': f'the {view.value} view after the rules, plus the knowledge, '
                      'plus pyshacl\'s own rule pass -- what validation queries',
             'base': base}
    return data, focus, stats


def _instance_turtle(data, package, base):
    """The instance data as Turtle (no knowledge), and what the rules derived."""
    knowledge = package.knowledge

    def turtle(triples):
        out = Graph()
        for prefix, namespace in data.namespaces():
            out.bind(prefix, namespace, override=False)
        for triple in triples:
            out.add(triple)
        return out.serialize(format='turtle'), len(out)

    instance = [t for t in data if t not in knowledge]
    derived = [t for t in instance if t not in base]
    text, size = turtle(instance)
    derived_text, derived_size = turtle(derived)
    return {'turtle': text, 'triples': size, 'derived': derived_text,
            'derivedTriples': derived_size}


# --- the page and a run ------------------------------------------------------------------

def pick(found, index=None, query=None, kind=None):
    """The holder a page asked for: by its text (other pages list queries in
    graph order, not file order), else by kind, else by position."""
    if query:
        for holder in found:
            if holder['query'].strip() == query.strip():
                return holder
    if kind and index in (None, ''):
        for holder in found:
            if holder['kind'] == kind:
                return holder
    return found[min(max(int(index or 0), 0), len(found) - 1)]


def bench_page(package, shape, index=0, source=MAIN, query=None, kind=None):
    """Everything the workbench shows when it opens or the data changes."""
    found = holders(package, shape)
    if not found:
        raise PackageError(f'{curie(package.shapes, URIRef(shape))} has no SPARQL query')
    holder = pick(found, index, query, kind)
    data, focus, stats = data_graph(package, shape, source, holder['kind'])
    shown = _instance_turtle(data, package, stats.pop('base'))
    return {
        'shape': str(shape), 'shapeName': curie(package.shapes, URIRef(shape)),
        'label': local(URIRef(shape)), 'holders': found, 'holder': holder,
        'sources': sources(package, shape), 'source': source or MAIN,
        'focus': [_term(data, node) for node in focus],
        'selector': selector(package, shape, focus, holder['query']),
        'data': shown, 'stats': stats}


def _term(graph, node):
    if isinstance(node, URIRef):
        try:
            return graph.namespace_manager.normalizeUri(node).strip('<>')
        except Exception:                            # noqa: BLE001
            return str(node)
    if isinstance(node, BNode):
        return _instance(graph, node) or f'_:{str(node)[:8]}'
    if isinstance(node, Literal):
        return str(node)
    return '' if node is None else str(node)


def _instance(graph, node):
    """An NGSI-LD attribute instance by what it holds -- `[hasValue 21.5 ·
    observedAt …]` -- rather than its meaningless blank node id."""
    from ..ngsild.kinds import NGSILD, PAYLOAD_PATHS

    shown = []
    for predicate, value in sorted(graph.predicate_objects(node), key=lambda pv: str(pv[0])):
        name = str(predicate)
        if name in PAYLOAD_PATHS or name in (NGSILD + 'observedAt', NGSILD + 'datasetId'):
            text = _term(graph, value) if not isinstance(value, BNode) else '[…]'
            shown.append(f'{name[len(NGSILD):]} {text}')
    if not shown:
        return ''
    # The payload first, then its metadata.
    shown.sort(key=lambda part: not part.startswith('has'))
    return '[' + ' · '.join(shown) + ']'


def _message(template, row, focus):
    def fill(match):
        name = match.group(2)
        if name == 'this':
            return focus
        return row.get(name, match.group(0))
    return re.sub(r'\{([?$])(\w+)\}', fill, template or '')


def warnings(query, kind, view):
    from ..validate.shapes import _AGGREGATE

    found = [text for pattern, text in REFUSED if pattern.search(query)]
    if kind == 'constraint' and not re.search(r'[$?]this\b', query):
        found.append('the query never mentions $this: it runs once, not per focus node, '
                     'and every row it returns is a violation of every focus node')
    if view == 'current' and _AGGREGATE.search(query):
        found.append('an aggregate in the current view sees one observation per '
                     'attribute: declare semforge:dataView history to aggregate over time')
    return found


def run_query(package, shape, index, source, query):
    """Run an (edited) query the way validation would. Never writes."""
    from rdflib.plugins.sparql import prepareQuery

    found = holders(package, shape)
    holder = found[min(max(int(index or 0), 0), len(found) - 1)]
    kind = holder['kind']
    prefixes = _prefix_lines(package, _holder_node(package, shape, kind, holder['query']))
    data, focus, stats = data_graph(package, shape, source, kind)
    result = {'ok': True, 'kind': kind, 'warnings': warnings(query, kind, stats['view']),
              'focusCount': len(focus)}
    try:
        prepared = prepareQuery('\n'.join(prefixes + [query]))
    except Exception as exc:                         # noqa: BLE001
        return dict(result, ok=False, error=f'the query does not parse: {exc}')
    shape_of_query = prepared.algebra.name
    wanted = 'SelectQuery' if kind == 'constraint' else 'ConstructQuery'
    if shape_of_query != wanted:
        return dict(result, ok=False, error=(
            f'a SPARQL {kind} must be a {"SELECT" if kind == "constraint" else "CONSTRUCT"} '
            f'query; this is a {shape_of_query.replace("Query", "").upper()}'))

    started = time.perf_counter()
    binds = bool(re.search(r'[$?]this\b', query))
    per_focus, columns, constructed = [], [], Graph()
    for prefix, namespace in data.namespaces():
        constructed.bind(prefix, namespace, override=False)
    # The query's own PREFIX names read best in what it constructs.
    for prefix, namespace in re.findall(r'PREFIX\s+([\w-]*):\s*<([^>]*)>', query, re.I):
        constructed.bind(prefix, URIRef(namespace), override=True, replace=True)
    for node in focus if binds else [None]:
        answer = data.query(prepared, initBindings={'this': node} if node is not None else {})
        label = _term(data, node) if node is not None else '(unbound)'
        if kind == 'constraint':
            columns = [str(v) for v in answer.vars or []] or columns
            rows = [{str(k): _term(data, v) for k, v in row.asdict().items()} for row in answer]
            per_focus.append({'node': label, 'rows': rows,
                              'messages': [_message(holder['message'], r, label) for r in rows]})
        else:
            triples = list(answer)
            for triple in triples:
                constructed.add(triple)
            per_focus.append({'node': label, 'triples': len(triples)})
    elapsed = round((time.perf_counter() - started) * 1000)

    result.update(columns=columns, focus=per_focus, ms=elapsed)
    if kind == 'constraint':
        result['violating'] = [f['node'] for f in per_focus if f['rows']]
        if query.strip() != holder['query'].strip():
            saved = run_query(package, shape, index, source, holder['query'])
            result['saved'] = {'violating': saved.get('violating', []),
                               'ok': saved.get('ok', False)}
    else:
        result['constructed'] = constructed.serialize(format='turtle')
        result['triples'] = len(constructed)
    return result


# --- writing ----------------------------------------------------------------------------

def _turtle_long_string(value):
    escaped = value.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
    if escaped.endswith('"'):
        escaped = escaped[:-1] + '\\"'
    return f'"""{escaped}"""'


def save_query(package, shape, index, query, expected):
    """Write an edited query over the one at `index`. `expected` is the query
    the page started from: if the file says something else now, nothing is
    written. Returns {'file', 'line'}."""
    from .tree import _write_verified
    from ..rdfio.blocks import set_parameter

    bodies, text, path = _bodies(package, shape)
    index = int(index)
    if not 0 <= index < len(bodies):
        raise PackageError('no such SPARQL query on this shape')
    kind, group = bodies[index]
    key = KINDS[kind][1]
    current = _literal(group.parameter(key)[2])
    if current != expected:
        raise PackageError('the query changed in the file since the workbench opened it; '
                           'reopen the workbench to see the file\'s version')
    if not query.strip():
        raise PackageError('an empty query would check nothing')
    updated = set_parameter(text, group, key, _turtle_long_string(query))
    _write_verified(path, updated)
    written = Graph().parse(data=updated, format='turtle')
    predicate, slot = (SH.sparql, SH.select) if kind == 'constraint' else (SH.rule, SH.construct)
    values = {str(written.value(h, slot)) for h in written.objects(URIRef(shape), predicate)}
    if query not in values:                        # never: the parse round-trip said so
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        raise PackageError('the query did not survive being written; the file is unchanged')
    return {'file': path, 'line': text.count('\n', 0, group.parameter(key)[0]) + 1}


SKELETON = """
{prefixes}

# $this is each node the shape selects (its target), bound before this runs.
# Every row returned is a violation of that node.
SELECT $this
WHERE {{
    $this ?attribute ?value .
    FILTER(1 = 0)    # fires on nothing yet: write the condition that is wrong
}}
"""


def add_constraint(package, shape, message):
    """Append a SPARQL constraint that fires on nothing, ready to be written in
    the workbench. Returns the new holder's index."""
    from .tree import _write_verified

    if not (message or '').strip():
        raise PackageError('a SPARQL constraint needs its message: what a violation means')
    index = package.index('shapes')
    path, block = index.block_for(URIRef(shape))
    if path is None:
        raise PackageError(f'{shape} is not a shape written in this package')
    text = index.source_of(path)
    statement = text[block.start:block.end].rstrip()
    if not statement.endswith('.'):
        raise PackageError('the shape statement does not end with "." where expected')
    cut = block.start + len(statement) - 1
    while cut > block.start and text[cut - 1] in ' \t\n':
        cut -= 1

    own = str(next((n for p, n in package.shapes.namespaces()
                    if str(URIRef(shape)).startswith(str(n))), ''))
    lines = sorted(f'PREFIX {p}: <{n}>' for p, n in package.shapes.namespaces()
                   if p and str(n) != own and p not in ('sh', 'owl', 'brick', 'csvw', 'dc',
                                                        'dcat', 'dcmitype', 'dcterms', 'dcam',
                                                        'doap', 'foaf', 'geo', 'odrl', 'org',
                                                        'prof', 'prov', 'qb', 'schema', 'skos',
                                                        'sosa', 'ssn', 'time', 'vann', 'void',
                                                        'wgs', 'xml'))
    body = SKELETON.format(prefixes='\n'.join(lines))
    escaped = message.replace('\\', '\\\\').replace('"', '\\"')
    addition = (f' ;\n    sh:sparql [ a sh:SPARQLConstraint ;\n'
                f'            sh:message "{escaped}" ;\n'
                f'            sh:select {_turtle_long_string(body)} ]')
    updated = text[:cut] + addition + text[cut:]
    _write_verified(path, updated)
    written = Graph().parse(data=updated, format='turtle')
    count = len(list(written.objects(URIRef(shape), SH.sparql)))
    if count != len(list(package.shapes.objects(URIRef(shape), SH.sparql))) + 1:
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        raise PackageError('the constraint did not land on the shape; the file is unchanged')
    from ..package import load
    return {'file': path, 'index': len(holders(load(package.path), shape)) - 1,
            'line': text.count('\n', 0, cut) + 2}


# --- removing ---------------------------------------------------------------------------

COMPONENT = 'SPARQLConstraintComponent'


def _asserting(package, shape):
    """[(expectations.yaml, case, resource)] -- the asserts that name this
    shape's SPARQL constraints. They name the shape and the component, not one
    query, so they are about ALL of a shape's SPARQL constraints at once."""
    from ..expect.store import _yaml, expectation_files

    wanted = f'{curie(package.shapes, URIRef(shape))}/{COMPONENT}'
    found = []
    for path in expectation_files(package.path):
        with open(path, encoding='utf-8') as handle:
            raw = _yaml().load(handle) or {}
        for entry in raw.get('examples') or []:
            for item in entry.get('asserts') or []:
                if str(item.get('constraint', '')) == wanted:
                    found.append((path, str(entry.get('path', '')), str(item.get('resource', ''))))
    return found


def removal_plan(package, shape, index):
    """What removing one SPARQL query would take with it -- asked before it is done."""
    found = holders(package, shape)
    index = int(index)
    if not 0 <= index < len(found):
        raise PackageError('no such SPARQL query on this shape')
    holder = found[index]
    constraints = [h for h in found if h['kind'] == 'constraint']
    last = holder['kind'] == 'constraint' and len(constraints) == 1
    asserts = _asserting(package, shape) if holder['kind'] == 'constraint' else []
    return {'holder': holder, 'last': last,
            'asserts': [{'file': f, 'case': c, 'resource': r} for f, c, r in asserts],
            'others': len(constraints) - 1 if holder['kind'] == 'constraint' else 0}


def _cut(text, start, end):
    """(start, end) of the text to delete for the group at [start, end): the
    predicate and its `[ … ]`, with the `;` that joins it to the statement."""
    after = end
    while after < len(text) and text[after] in ' \t\r\n':
        after += 1
    if after < len(text) and text[after] == ';':
        # More of the statement follows: take the ';' and the space up to the
        # next predicate. The indentation in front of `start` is kept and now
        # stands in front of that predicate.
        after += 1
        while after < len(text) and text[after] in ' \t\r\n':
            after += 1
        return start, after
    # The last part of the statement: take the ';' before it instead.
    before = start
    while before > 0 and text[before - 1] in ' \t\r\n':
        before -= 1
    if before == 0 or text[before - 1] != ';':
        raise PackageError('this query is all the shape statement says; remove the shape '
                           'instead')
    before -= 1
    while before > 0 and text[before - 1] in ' \t':
        before -= 1                     # "X ;" leaves "X .", not "X  ."
    return before, end


def remove_holder(package, shape, index, expected, drop_asserts=False):
    """Remove one SPARQL constraint or rule: its whole `[ … ]`, nothing else.
    `expected` is the query the page shows; a file that says something else
    now is left alone. With `drop_asserts`, the asserts no remaining query
    could satisfy go too. Returns {'file', 'line', 'asserts': n}."""
    from .tree import _write_verified

    plan = removal_plan(package, shape, index)
    bodies, text, path = _bodies(package, shape)
    kind, group = bodies[int(index)]
    if plan['holder']['query'] != expected:
        raise PackageError('the query changed in the file since the workbench opened it; '
                           'reopen it to see the file\'s version')
    predicate = KINDS[kind][0]
    head = text.rfind(predicate, 0, group.start)
    if head < 0 or text[head + len(predicate):group.start].strip():
        raise PackageError('could not find where this query is attached to the shape')
    cut_start, cut_end = _cut(text, head, group.end)
    updated = text[:cut_start] + text[cut_end:]

    link, slot = (SH.sparql, SH.select) if kind == 'constraint' else (SH.rule, SH.construct)
    before = Graph().parse(data=text, format='turtle')
    after = Graph().parse(data=updated, format='turtle')
    holder_node = next(h for h in before.objects(URIRef(shape), link)
                       if str(before.value(h, slot) or '') == expected)
    removed = len(before.cbd(holder_node)) + 1
    if len(after) != len(before) - removed or \
            len(list(after.objects(URIRef(shape), link))) != \
            len(list(before.objects(URIRef(shape), link))) - 1:
        raise PackageError('removing it would have changed more than the query; '
                           'the file is unchanged')
    _write_verified(path, updated)

    dropped = 0
    if drop_asserts and plan['last'] and plan['asserts']:
        dropped = _drop_asserts(package, shape)
    return {'file': path, 'line': text.count('\n', 0, cut_start) + 1, 'asserts': dropped}


def _drop_asserts(package, shape):
    from ..expect.store import _yaml, expectation_files

    wanted = f'{curie(package.shapes, URIRef(shape))}/{COMPONENT}'
    dropped = 0
    for path in expectation_files(package.path):
        with open(path, encoding='utf-8') as handle:
            raw = _yaml().load(handle) or {}
        changed = False
        for entry in raw.get('examples') or []:
            asserts = entry.get('asserts')
            if not asserts:
                continue
            keep = [a for a in asserts if str(a.get('constraint', '')) != wanted]
            if len(keep) != len(asserts):
                dropped += len(asserts) - len(keep)
                del asserts[:]
                asserts.extend(keep)
                changed = True
        if changed:
            with open(path, 'w', encoding='utf-8') as handle:
                _yaml().dump(raw, handle)
    return dropped


# --- the selector, said ------------------------------------------------------------------

def selector(package, shape, focus, query):
    """How `$this` gets its value: the shape's target, applied by the engine
    before the query runs -- said in words, and as the SPARQL it amounts to."""
    from .shapes import targets, used_by

    declared = targets(package, URIRef(shape))
    if declared:
        said = '; '.join(t['text'] for t in declared)
    else:
        users = used_by(package, URIRef(shape))
        said = ('no target of its own: the nodes the shapes using it reach (' +
                ', '.join(curie(package.shapes, URIRef(u)) for u in users) + ')'
                if users else 'no target: it selects nothing')
    shown = focus[:50]
    values = ' '.join(f'<{node}>' for node in shown) + (' …' if len(focus) > 50 else '')
    binds = bool(re.search(r'[$?]this\b', query))
    return {
        'text': said, 'count': len(focus), 'binds': binds,
        'sparql': ('# Added by the SHACL engine, not written in the query: $this is\n'
                   '# bound to each node the shape selects, one run per node.\n'
                   f'VALUES $this {{ {values} }}') if binds else
                  ('# The query never mentions $this: it runs once, unbound, and every\n'
                   '# row it returns is a violation of every selected node.')}


# --- Inspect: every variable, and why rows were dropped ----------------------------------

ABOVE = ('Project', 'Distinct', 'Reduced', 'Slice', 'OrderBy', 'ToMultiSet')


def _contains(part, name):
    if not hasattr(part, 'name'):
        return False
    if part.name == name:
        return True
    return any(_contains(part[k], name) for k in ('p', 'p1', 'p2') if k in part)


def _filters_inside(part):
    """A FILTER below the outer ones: a Filter node, or the condition rdflib
    folds into an OPTIONAL (LeftJoin.expr)."""
    if not hasattr(part, 'name'):
        return False
    if part.name == 'Filter':
        return True
    if part.name == 'LeftJoin' and getattr(part.get('expr'), 'name', '') != 'TrueFilter':
        return True
    return any(_filters_inside(part[k]) for k in ('p', 'p1', 'p2') if k in part)


def _explainable(algebra):
    """(pattern, [Filter], notes): the query's WHERE as rows are made, its
    outer FILTERs taken off to be checked one by one."""
    part, notes = algebra.p, []
    while hasattr(part, 'name'):
        if part.name in ABOVE:
            part = part.p
        elif part.name == 'Extend' and _contains(part.p, 'AggregateJoin'):
            part = part.p                    # (COUNT(?x) AS ?n): computed after grouping
        elif part.name in ('AggregateJoin', 'Group'):
            if part.name == 'AggregateJoin':
                notes.append('the rows before GROUP BY: an aggregate is computed from them')
            part = part.p
        else:
            break
    filters = []
    while hasattr(part, 'name') and part.name == 'Filter':
        filters.append(part)
        part = part.p
    if _filters_inside(part):
        notes.append('a FILTER inside OPTIONAL or a nested group acts inside it; only the '
                     'outer FILTERs are checked one by one')
    return part, filters, notes


def _conjuncts(expr):
    if getattr(expr, 'name', '') == 'ConditionalAndExpression':
        out = []
        for part in [expr['expr']] + list(expr.get('other') or []):
            out.extend(_conjuncts(part))
        return out
    return [expr]


XSD = 'http://www.w3.org/2001/XMLSchema#'
PLAIN_TYPES = {URIRef(XSD + t) for t in ('integer', 'decimal', 'double', 'boolean')}


def _held(part, solution):
    """True / False, or None when evaluating it is an error (an unbound
    variable, a type clash): FILTER counts that as false, but it is worth
    seeing that it was not a plain no. rdflib's own _ebv folds the two."""
    from rdflib import Variable
    from rdflib.plugins.sparql.operators import EBV
    from rdflib.plugins.sparql.sparql import SPARQLError

    try:
        if isinstance(part, Variable):
            if part not in solution:
                return None
            value = solution[part]
        elif isinstance(part, Literal):
            value = part
        else:
            value = part.eval(solution)
        if isinstance(value, SPARQLError):
            return None
        return bool(EBV(value))
    except Exception:                                # noqa: BLE001
        return None


def expression(expr, graph):
    """A FILTER expression read back as SPARQL, near enough to recognise."""
    from rdflib import Variable

    if isinstance(expr, Variable):
        return f'?{expr}'
    if isinstance(expr, (URIRef, BNode, Literal)):
        if isinstance(expr, Literal):
            if expr.datatype in PLAIN_TYPES:
                return str(expr)              # 1, 2.5, true -- as written
            return expr.n3(graph.namespace_manager)
        return _term(graph, expr) if isinstance(expr, URIRef) else '[]'
    name = getattr(expr, 'name', '')
    text = lambda key: expression(expr[key], graph)  # noqa: E731
    if name == 'RelationalExpression':
        other = expr.get('other')
        if isinstance(other, list):
            return f'{text("expr")} {expr["op"]} ({", ".join(expression(o, graph) for o in other)})'
        return f'{text("expr")} {expr["op"]} {text("other")}'
    if name in ('ConditionalAndExpression', 'ConditionalOrExpression'):
        glue = ' && ' if name == 'ConditionalAndExpression' else ' || '
        return '(' + glue.join(expression(p, graph)
                               for p in [expr['expr']] + list(expr.get('other') or [])) + ')'
    if name in ('AdditiveExpression', 'MultiplicativeExpression'):
        out = text('expr')
        for op, other in zip(expr.get('op') or [], expr.get('other') or []):
            out += f' {op} {expression(other, graph)}'
        return out
    if name == 'UnaryNot':
        inner = text('expr')
        atomic = not hasattr(expr['expr'], 'name') or expr['expr'].name.startswith('Builtin_')
        return f'!{inner}' if atomic or inner.startswith('(') else f'!({inner})'
    if name == 'UnaryMinus':
        return f'-{text("expr")}'
    if name in ('Builtin_EXISTS', 'Builtin_NOTEXISTS'):
        return ('EXISTS' if name == 'Builtin_EXISTS' else 'NOT EXISTS') + ' { … }'
    if name.startswith('Builtin_'):
        args = [expression(expr[k], graph) for k in ('arg', 'arg1', 'arg2', 'arg3')
                if k in expr and expr[k] is not None]
        return f'{name[len("Builtin_"):]}({", ".join(args)})'
    if name == 'Function':
        return f'{_term(graph, expr["iri"])}({", ".join(expression(a, graph) for a in expr["expr"])})'
    return str(expr)


def inspect(package, shape, index, source, query):
    """The query taken apart, its text untouched: per focus node, every row
    its WHERE makes with every variable, and for each outer FILTER part
    whether it held -- so a row that was dropped says what dropped it."""
    from rdflib import Variable
    from rdflib.plugins.sparql import prepareQuery
    from rdflib.plugins.sparql.evaluate import evalPart
    from rdflib.plugins.sparql.sparql import QueryContext

    found = holders(package, shape)
    holder = found[min(max(int(index or 0), 0), len(found) - 1)]
    prefixes = _prefix_lines(package, _holder_node(package, shape, holder['kind'],
                                                   holder['query']))
    data, focus, _ = data_graph(package, shape, source, holder['kind'])
    try:
        prepared = prepareQuery('\n'.join(prefixes + [query]))
    except Exception as exc:                         # noqa: BLE001
        return {'ok': False, 'error': f'the query does not parse: {exc}'}
    pattern, filters, notes = _explainable(prepared.algebra)
    checks = [(f, part) for f in filters for part in _conjuncts(f.expr)]
    order = []
    for name in re.findall(r'[?$](\w+)', query):
        if name not in order:
            order.append(name)

    started = time.perf_counter()
    binds = bool(re.search(r'[$?]this\b', query))
    per_focus, seen_vars = [], set()
    for node in focus if binds else [None]:
        ctx = QueryContext(data, initBindings={Variable('this'): node} if node is not None
                           else {})
        ctx.prologue = prepared.prologue
        rows, kept, total = [], 0, 0
        for solution in evalPart(ctx, pattern):
            total += 1
            values = {str(k): _term(data, v) for k, v in solution.items()
                      if isinstance(k, Variable)}
            seen_vars.update(values)
            results, all_hold = [], True
            for f, part in checks:
                scoped = solution.forget(ctx, _except=f._vars) \
                    if not f.no_isolated_scope else solution
                held = _held(part, scoped)
                results.append(held)
                all_hold = all_hold and bool(held)
            kept += all_hold
            if len(rows) < 100:
                rows.append({'values': values, 'checks': results, 'kept': all_hold})
        per_focus.append({'node': _term(data, node) if node is not None else '(unbound)',
                          'rows': rows, 'total': total, 'kept': kept})
    columns = ['this'] if 'this' in seen_vars else []
    columns += [v for v in order if v in seen_vars and v not in columns]
    columns += sorted(v for v in seen_vars if v not in columns)
    return {'ok': True, 'kind': holder['kind'], 'columns': columns,
            'filters': [expression(part, data) for _, part in checks],
            'focus': per_focus, 'notes': notes,
            'ms': round((time.perf_counter() - started) * 1000)}
