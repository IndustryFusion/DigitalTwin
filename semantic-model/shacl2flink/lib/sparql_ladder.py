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
"""
ALPHA: compile the SPARQL constraints and rules of a KMS into data
(SPARQL_ENGINE=ladder). lib/sparql_ladder_sql.py renders the SQL which runs it.

Every triple pattern becomes a row, every query a join tree over its patterns.
All queries run through ONE ladder of joins on (tree node, key of the shared
variables); what a level does with a row travels with the row. So the Flink job
grows with the height of the highest tree, not with the number of queries.

A binding row is a string of slots joined with SEP: three per pattern (subject,
object, observedAt), the right slots appended to the left ones, an empty slot is
unbound. Terms are written as <iri>, "literal" or _:blank.
"""
import decimal
import json
import math
import re
from rdflib import BNode, Literal, URIRef, Variable, RDF, RDFS, XSD
from rdflib.paths import MulPath
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parser import parseQuery

import lib.utils as utils
from lib.bgp_translation_utils import ngsild
from lib.shacl_construct_to_sql import sparql_get_all_rule_nodes
from lib.shacl_sparql_to_sql import sparql_get_all_sparql_nodes, sparql_get_all_subclasses
import lib.sparql_to_sql as sparql_to_sql

SEP = '\x01'
RDF_TYPE = str(RDF.type)
PAYLOAD = {str(ngsild['hasValue']): 'value', str(ngsild['hasObject']): 'object', str(ngsild['observedAt']): 'time'}
CASTS = {XSD.integer: 'integer', XSD.float: 'float', XSD.string: 'string', XSD.dateTime: 'dateTime'}
AGGREGATES = ('count', 'sum')


class UnsupportedQuery(utils.UnsupportedShape):
    """A query the ladder cannot compile: a build error, never a silent gap."""


def term(node):
    """The one spelling of a term. Unlike utils.format_node_type, numbers are quoted as well."""
    if isinstance(node, URIRef):
        return f'<{node}>'
    if isinstance(node, BNode):
        return f'_:{node}'
    return f'"{node}"'


NUMERIC = (XSD.integer, XSD.decimal, XSD.double, XSD.float, XSD.int, XSD.long, XSD.short,
           XSD.nonNegativeInteger, XSD.positiveInteger, XSD.negativeInteger, XSD.nonPositiveInteger,
           XSD.unsignedInt, XSD.unsignedLong, XSD.unsignedShort, XSD.byte, XSD.unsignedByte)


def constant(node):
    """A constant of an expression as a value of the ladder, its kind with it:
    <iri>, a number bare, true or false, `string` for a string, "literal" else.
    See kind."""
    if isinstance(node, URIRef):
        return f'<{node}>'
    if node.datatype in NUMERIC:
        return str(node)
    if node.datatype == XSD.boolean:
        return 'true' if node.toPython() is True else 'false'
    if node.datatype in (None, XSD.string) or node.language is not None:
        return f'`{node}`'
    return f'"{node}"'


def is_number(text):
    try:
        float(text)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Join trees
# ---------------------------------------------------------------------------

class Leaf:
    height = 0
    slots = 3

    def __init__(self, p, src, s, o, ts=None):
        self.p, self.src = p, src
        self.cs = self.co = None
        self.filters = []
        self.vars = [None, None, None if ts is None else str(ts)]
        for pos, node in enumerate((s, o)):
            if isinstance(node, (Variable, BNode)):
                self.vars[pos] = str(node)
            elif node is not None and pos == 0:
                self.cs = term(node)
            elif isinstance(node, Literal) and node.datatype in NUMERIC:
                # by its value: the knowledge writes a number bare, an attribute in quotes
                self.filters.append(['=', ['s', 1], ['c', constant(node)]])
            elif node is not None:
                self.co = term(node)
        if self.vars[0] is not None and self.vars[0] == self.vars[1]:
            raise UnsupportedQuery(f'the variable ?{self.vars[0]} as subject and object of one triple')
        if ts is not None:
            # observedAt is a triple of its own: an attribute without one does not match
            self.filters.append(['bound', ['s', 2]])

    def layout(self):
        return {var: pos for pos, var in enumerate(self.vars) if var is not None}

    def leaves(self):
        return [self]


class Join:
    def __init__(self, left, right, kind='inner', env=None):
        self.left, self.right, self.kind = left, right, kind
        self.conditions = []
        llay, rlay = left.layout(), right.layout()
        self.on = [(['s', llay[v]], rlay[v]) for v in llay if v in rlay]
        # A variable the left side has bound with BIND is part of the key too.
        for var in rlay:
            if env and var in env and var not in llay:
                self.on.append((resolve(env[var], llay), rlay[var]))

    @property
    def height(self):
        return 1 + max(self.left.height, self.right.height)

    @property
    def slots(self):
        return self.left.slots + self.right.slots

    def layout(self):
        result = dict(self.left.layout())
        if self.kind != 'anti':
            for var, slot in self.right.layout().items():
                result.setdefault(var, slot + self.left.slots)
        return result

    def leaves(self):
        return self.left.leaves() + self.right.leaves()


def canonical(tree):
    """A tree as text, the same in every process: what decides a tie between two trees."""
    if isinstance(tree, Leaf):
        return json.dumps([tree.p, tree.src, tree.cs, tree.co, tree.vars, tree.filters], sort_keys=True)
    return json.dumps([tree.kind, canonical(tree.left), canonical(tree.right), tree.conditions], sort_keys=True)


def plan(trees):
    """Join connected trees first and keep the result low: its height is the number of levels needed.
    The trees come in the order rdflib gives their triples, which changes with the process's hash
    seed: sorted first, the same package compiles to the same rows, so a deploy of it keeps the job."""
    trees = sorted(trees, key=canonical)
    while len(trees) > 1:
        best = None
        for i, a in enumerate(trees):
            for j in range(i + 1, len(trees)):
                b = trees[j]
                rank = (not set(a.layout()) & set(b.layout()), 1 + max(a.height, b.height),
                        abs(a.height - b.height), a.slots + b.slots, i, j)
                if best is None or rank < best:
                    best = rank
        i, j = best[-2:]
        right = trees.pop(j)
        left = trees.pop(i)
        trees.append(Join(left, right))
    return trees[0] if trees else None


# ---------------------------------------------------------------------------
# Expressions: ['s', slot] | ['c', term] | [operator, argument...]; before the
# slots are known a variable is ['v', name].
# ---------------------------------------------------------------------------

def variables(ast):
    if ast[0] == 'v':
        return {ast[1]}
    return set().union(set(), *[variables(arg) for arg in ast[1:] if isinstance(arg, list)])


def resolve(ast, layout):
    """Replace the variables with their slots."""
    if ast[0] == 'v':
        if ast[1] not in layout:
            raise UnsupportedQuery(f'the variable ?{ast[1]} where nothing binds it')
        return ['s', layout[ast[1]]]
    return [ast[0]] + [resolve(arg, layout) if isinstance(arg, list) else arg for arg in ast[1:]]


def find_aggregate(ast):
    if ast[0] == 'agg':
        return ast
    return next((found for found in (find_aggregate(a) for a in ast[1:] if isinstance(a, list)) if found), None)


def replace_aggregate(ast, replacement):
    if ast[0] == 'agg':
        return replacement
    return [ast[0]] + [replace_aggregate(a, replacement) if isinstance(a, list) else a for a in ast[1:]]


def to_json(ast):
    return json.dumps(ast, separators=(',', ':'))


def conjuncts(expr):
    if getattr(expr, 'name', None) == 'ConditionalAndExpression':
        return conjuncts(expr.expr) + [c for other in expr.other for c in conjuncts(other)]
    return [expr]


class Query:
    """One SPARQL query as a join tree plus the expressions its BINDs give."""

    def __init__(self, relationships, outer=None):
        self.relationships = relationships
        self.env = outer.env if outer else {}
        self.entities = outer.entities if outer else {'this'}
        self.aggregated = outer.aggregated if outer else set()
        self.group = None

    def expression(self, e, env=None):
        env = self.env if env is None else env

        def sub(x):
            return self.expression(x, env)

        if isinstance(e, Variable):
            return env.get(str(e), ['v', str(e)])
        if isinstance(e, (Literal, URIRef)):
            return ['c', constant(e)]
        name = e.name
        if name == 'RelationalExpression':
            if e.op in ('IN', 'NOT IN'):
                found = ['or'] + [['=', sub(e.expr), sub(o)] for o in e.other]
                return found if e.op == 'IN' else ['not', found]
            return [e.op, sub(e.expr), sub(e.other)]
        if name in ('ConditionalAndExpression', 'ConditionalOrExpression'):
            return ['and' if 'And' in name else 'or', sub(e.expr)] + [sub(o) for o in e.other]
        if name == 'UnaryNot':
            return ['not', sub(e.expr)]
        if name == 'Builtin_BOUND':
            return ['bound', sub(e.arg)]
        if name == 'Builtin_IF':
            return ['if', sub(e.arg1), sub(e.arg2), sub(e.arg3)]
        if name == 'Builtin_STR':
            return ['string', sub(e.arg)]
        if name == 'Builtin_CONCAT':
            return ['join'] + [sub(a) for a in e.arg]
        if name in ('AdditiveExpression', 'MultiplicativeExpression'):
            result = sub(e.expr)
            for op, other in zip(e.op, e.other):
                result = [op, result, sub(other)]
            return result
        if name == 'Function':
            if e.iri in CASTS and len(e.expr) == 1:
                return [CASTS[e.iri], sub(e.expr[0])]
            raise UnsupportedQuery(f'the function <{e.iri}>')
        if name.startswith('Aggregate_') and name[10:].lower() in AGGREGATES:
            # The attributes whose variables are written inside an aggregate
            # are read with their history, as the classic method does.
            self.aggregated |= variables(self.expression(e.vars, {}))
            return ['agg', name[10:].lower(), e.distinct == 'DISTINCT', sub(e.vars)]
        raise UnsupportedQuery(f'the expression {name}')

    def bgp(self, triples):
        nodes, payload = {}, {}
        # An attribute is a blank node or a variable that holds a payload.
        holders = {s for s, p, _ in triples if str(p) in PAYLOAD}
        for s, p, o in triples:
            if (isinstance(o, BNode) or isinstance(o, Variable) and o in holders) and isinstance(p, URIRef):
                nodes[o] = (s, p)
        for s, p, o in triples:
            if s in nodes and str(p) in PAYLOAD:
                payload.setdefault(s, {})[PAYLOAD[str(p)]] = o
        for s, p, o in triples:
            # Anything else inside the [ ... ] of an attribute would be dropped.
            if (s in payload or s in nodes and str(p).startswith(str(ngsild))) and str(p) not in PAYLOAD:
                raise UnsupportedQuery(f'<{p}> of an attribute')

        # hasValue and observedAt of one attribute are one row of it
        attributes = {}
        for node, content in payload.items():
            key = nodes[node]
            if key in attributes and set(attributes[key]) & set(content):
                key = key + (node,)
            attributes.setdefault(key, {}).update(content)
        leaves = []
        for key, content in attributes.items():
            s, p = key[:2]
            if 'value' in content and 'object' in content:
                raise UnsupportedQuery(f'<{p}> with hasValue and with hasObject')
            is_relationship = 'object' in content or 'value' not in content and str(p) in self.relationships
            leaves.append(Leaf(str(p), 'R' if is_relationship else 'P', s,
                               content.get('object', content.get('value')), content.get('time')))
            self.entities.add(str(s))

        # A relationship counts only when its object exists as an entity.
        subjects = {str(key[0]) for key in attributes} | {str(s) for s, _, _ in triples if not isinstance(s, BNode)}
        for content in attributes.values():
            target = content.get('object')
            if isinstance(target, Variable) and str(target) not in subjects | self.entities:
                leaves.append(Leaf(RDF_TYPE, 'E', target, None))
                self.entities.add(str(target))

        for s, p, o in triples:
            if o in payload or s in payload:
                continue
            if isinstance(p, MulPath):
                p = p.path          # the knowledge holds the closure
            if not isinstance(p, URIRef):
                raise UnsupportedQuery(f'the predicate {p}')
            leaves.append(Leaf(str(p), None, s, o))
        tree = plan(leaves)
        # bound by BIND before the pattern: the pattern holds that value
        for var in sorted({var for leaf in leaves for var in leaf.vars[:2] if var in self.env}):
            if not variables(self.env[var]):
                self.add_condition(tree, ['=', ['v', var], self.env[var]])
        return tree

    def add_condition(self, tree, cond):
        """Put a FILTER as deep as its variables allow: the less a join has to keep, the better."""
        used = variables(cond)
        if isinstance(tree, Leaf):
            const = cond[2][1] if cond[0] == '=' and cond[1][0] == 'v' and cond[2][0] == 'c' else None
            # An IRI, or a text which reads as no number, is matched with the
            # stored term; anything else is compared as evaluate does.
            stored = const if const and kind(const) == 'I' else \
                f'"{lexical(const)}"' if const and kind(const) == 'S' else None
            if stored and tree.vars[1] == cond[1][1] and tree.co is None:
                tree.co = stored
            else:
                tree.filters.append(resolve(cond, tree.layout()))
            return
        for child in (tree.left, tree.right):
            if used and used <= set(child.layout()) and (tree.kind == 'inner' or child is tree.left):
                self.add_condition(child, cond)
                return
        tree.conditions.append(resolve(cond, tree.layout()))

    def tree(self, node):
        name = node.name
        if name in ('SelectQuery', 'ConstructQuery', 'Project', 'Distinct', 'AggregateJoin'):
            return self.tree(node.p)
        if name == 'Group':
            self.group = [str(v) for v in node.expr or [] if isinstance(v, Variable)]
            if len(self.group) != len(node.expr or []):
                raise UnsupportedQuery('GROUP BY an expression')
            return self.tree(node.p)
        if name == 'BGP':
            return self.bgp(node.triples)
        if name in ('Join', 'LeftJoin'):
            left, right = self.tree(node.p1), self.tree(node.p2)
            if name == 'LeftJoin' and getattr(node.expr, 'name', None) != 'TrueFilter':
                raise UnsupportedQuery('a FILTER inside OPTIONAL')
            if left is None and name == 'LeftJoin' and right is not None:
                left = Leaf(RDF_TYPE, 'E', Variable('this'), None)
            if left is None or right is None:
                return right if left is None else left
            return Join(left, right, 'inner' if name == 'Join' else 'left', self.env)
        if name == 'Extend':
            tree = self.tree(node.p)
            self.env[str(node.var)] = self.expression(node.expr)
            return tree
        if name == 'Filter':
            return self.filter(node)
        raise UnsupportedQuery(f'{name} in the WHERE clause')

    def filter(self, node):
        tree = self.tree(node.p)
        if tree is None:
            raise UnsupportedQuery('a FILTER without a triple')
        absent = []
        for cond in conjuncts(node.expr):
            if getattr(cond, 'name', None) == 'Builtin_NOTEXISTS':
                absent.append(cond.graph)
            else:
                self.add_condition(tree, self.expression(cond))
        for graph in absent:
            inner = Query(self.relationships, self).tree(graph)
            if inner is None:
                raise UnsupportedQuery('NOT EXISTS without a triple')
            tree = Join(tree, inner, 'anti', self.env)
        return tree

    def finish(self, tree):
        if tree is None:
            raise UnsupportedQuery('no triple in the WHERE clause')
        for leaf in tree.leaves():
            if leaf.src is None:
                leaf.src = 'E' if leaf.p == RDF_TYPE and leaf.vars[0] in self.entities else 'K'
            if self.group is not None and leaf.src in ('P', 'R') and leaf.vars[1] in self.aggregated:
                leaf.src += 'H'
        return tree


def pattern_rows(rule, tree, levels, root_key):
    """
    The rows of one tree. The root sits on level `levels`, every node one level
    below its parent, so a level feeds the next one only. A left row carries the
    path up to where its branch joins from the right, per level:
    [join kind, conditions, right slots, next side, next key, next node].
    """
    rows = []

    def walk(tree, level, node, side, key, path):
        if isinstance(tree, Leaf):
            rows.append({'p': tree.p, 'src': tree.src, 'cs': tree.cs or '', 'co': tree.co or '',
                         'flt': to_json(['and'] + tree.filters) if tree.filters else '',
                         'lvl': level + 1, 'node': node, 'side': side, 'key': to_json(key),
                         'path': to_json([path.get(i, 0) for i in range(1, levels + 1)]) if side == 'L' else ''})
            return
        walk.joins += 1
        this = f'{rule}.{walk.joins}'
        step = [tree.kind, ['and'] + tree.conditions if tree.conditions else 0, tree.right.slots, side, key, node]
        walk(tree.left, level - 1, this, 'L', [left for left, _ in tree.on], {**path, level: step})
        walk(tree.right, level - 1, this, 'R', [['s', right] for _, right in tree.on], {})

    walk.joins = 0
    walk(tree, levels, rule, 'Z', root_key, {})
    return rows


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

class Rule:
    """A compiled query: its tree, where it runs and the rows which say what becomes of its result."""

    def __init__(self, name, query, tree):
        self.name, self.query, self.tree = name, query, tree
        self.layout = tree.layout()
        # Attribute history is unbounded, so it must not enter pinned joins.
        self.ladder = 'current' if query.group is None else 'history'
        self.root_key = []
        self.rows = []              # (kind, row)

    def value(self, var):
        return resolve(self.query.env.get(var, ['v', var]), self.layout)


def message_ast(message, rule):
    parts = ['concat']
    for part in re.split(r'(\{[?$]\w+\})', message):
        var = re.fullmatch(r'\{[?$](\w+)\}', part)
        if var:
            parts.append(rule.value(var[1]))
        elif part:
            parts.append(['c', f'"{part}"'])
    return parts


def parse(text):
    try:
        return translateQuery(parseQuery(text)).algebra
    except Exception as err:
        raise utils.SparqlValidationFailed(f'Failed to parse: {text}') from err


def failing_for(shape, text, err):
    query = re.sub(r'^\s*PREFIX.*$', '', text, flags=re.M | re.I).strip()
    return UnsupportedQuery(f'SPARQL_ENGINE=ladder does not support {err}. Change the query of {shape} or build with '
                            f'SPARQL_ENGINE=classic. The query:\n{query}')


def constraint_rules(g, prefixes, relationships):
    rules = []
    for num, row in enumerate(utils.in_stable_order(g.query(sparql_get_all_sparql_nodes, initNs=prefixes))):
        name = f'S{num}'
        text = row.select.toPython()
        try:
            query = Query(relationships)
            tree = query.finish(query.tree(parse(text)))
            if query.group is not None:
                raise UnsupportedQuery('GROUP BY in a constraint')
            rule = Rule(name, query, tree)
            rule.root_key = [rule.value('this')]
            msg = to_json(message_ast(row.message.toPython(), rule))
        except UnsupportedQuery as err:
            raise failing_for(row.nodeshape, text, err) from err
        event = f'SPARQLConstraintComponent({utils.strip_class(row.nodeshape.toPython())})'
        severity = row.severitylabel.toPython() if row.severitylabel is not None else 'warning'
        types = {str(row.targetclass)}
        for sub in g.query(sparql_get_all_subclasses, initNs=prefixes, initBindings={'targetclass': row.targetclass}):
            types.add(str(sub.subclass))
        rule.rows = [('constraint', {'rule': name, 'type': cls, 'event': event, 'severity': severity, 'msg': msg})
                     for cls in sorted(types)]
        rules.append(rule)
    return rules


def output_attributes(template, relationships):
    """[(entity variable, attribute, value variable)] of a CONSTRUCT"""
    nodes = {o: (s, p) for s, p, o in template if isinstance(o, BNode)}
    result = []
    for s, p, o in template:
        if s not in nodes:
            continue
        entity, name = nodes[s]
        if p != ngsild['hasValue'] or str(name) in relationships or not isinstance(o, Variable) or \
                not isinstance(entity, Variable):
            raise UnsupportedQuery('constructing anything else than the value of a Property from a variable')
        result.append((str(entity), str(name), str(o)))
    if not result or len(result) * 2 != len(template):
        raise UnsupportedQuery('a CONSTRUCT template which is not a list of attributes')
    return sorted(result)


def construct_rules(g, relationships):
    rules = []
    found = sorted(g.query(sparql_get_all_rule_nodes),
                   key=lambda r: (str(r.nodeshape), str(r.construct), str(r.targetclass)))
    for num, row in enumerate(found):
        name = f'C{num}'
        text = row.construct.toPython()
        try:
            algebra = parse(text)
            query = Query(relationships)
            tree = query.tree(algebra)
            if tree is None:
                raise UnsupportedQuery('no triple in the WHERE clause')
            # the rule applies to the instances of its target class only
            tree = Join(tree, Leaf(RDF_TYPE, 'E', Variable('this'), Variable('this type')))
            tree = Join(tree, Leaf(str(RDFS.subClassOf), 'K', Variable('this type'), row.targetclass))
            rule = Rule(name, query, query.finish(tree))
            rule.rows = [construct_row(rule, *output)
                         for output in output_attributes(algebra.template, relationships)]
        except UnsupportedQuery as err:
            raise failing_for(row.nodeshape, text, err) from err
        rules.append(rule)
    return rules


def construct_row(rule, entity, attribute, var):
    query = rule.query
    row = {'rule': rule.name, 'name': attribute, 'id': utils.attribute_id_suffix(attribute),
           'sqlite_id': utils.attribute_id_suffix(attribute, sqlite=True)}
    value = query.env.get(var, ['v', var])
    if query.group is None:
        row.update(entity=to_json(rule.value(entity)), value=to_json(resolve(value, rule.layout)))
        return 'construct', row
    # the group is the GROUP BY variables plus the instance of the target class
    group = sorted({*query.group, entity, 'this'})
    layout = {v: pos for pos, v in enumerate(group)}
    aggregate = find_aggregate(value)
    if aggregate is None:
        raise UnsupportedQuery('GROUP BY without an aggregate in the constructed value')
    value = resolve(replace_aggregate(value, ['s', len(group)]), layout)
    _, function, distinct, argument = aggregate
    row.update(entity=to_json(['s', layout[entity]]), value=to_json(value),
               group=to_json([rule.value(v) for v in group]), function=function + ('-distinct' if distinct else ''),
               argument=to_json(resolve(argument, rule.layout)))
    return 'aggregate', row


def compile_rules(g, knowledge_graph, prefixes):
    """
    Args:
        g: shapes and knowledge with the closure of the classes, for the constraints
        knowledge_graph: shapes and knowledge, for the rules
        prefixes: of the queries over the graphs
    """
    # The same reading of the shapes as the classic method.
    relationships = set()
    for graph in (g, knowledge_graph):
        sparql_to_sql.read_attributes(graph)
        relationships |= set(sparql_to_sql.relationships)
    return constraint_rules(g, prefixes, relationships) + construct_rules(knowledge_graph, relationships)


# ---------------------------------------------------------------------------
# Evaluation. The Flink twin is FlinkSqlGateway/sparql-udf; both are tested
# with tests/sparql-ladder-vectors.json.
# ---------------------------------------------------------------------------

def lexical(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'     # STR of a truth value, as SPARQL writes it
    return value[1:-1] if len(value) > 1 and value[0] in '<"\'`' else value


NUMBER = re.compile(r'[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?')


def kind(value):
    """I an IRI, P a literal of the data (an attribute's value, a text of the
    knowledge), T a text (what STR and CONCAT give), S a string constant, N a
    number (of the knowledge, a constant, computed), B a truth value."""
    if isinstance(value, bool) or value in ('true', 'false'):
        return 'B'
    first = value[:1]
    if first in ('<', '_'):
        return 'I'
    if first == "'":
        return 'T'
    if first == '`':
        return 'S'
    if first == '"':
        return 'P'
    return 'N' if NUMBER.fullmatch(value) else 'P'


def number(value):
    """The value of a number, or of a literal of the data which reads as one, else None"""
    if value is None or isinstance(value, bool):
        return None
    text = lexical(value)
    return float(text) if kind(value) in ('N', 'P') and NUMBER.fullmatch(text) else None


def number_term(value):
    """Written out, a whole number without a fraction, as SQL writes an INTEGER"""
    if not math.isfinite(value):
        return None
    return '0' if value == 0 else f'{decimal.Decimal(repr(value)).normalize():f}'


def float_term(value):
    """xsd:float of a number, written as SPARQL writes it"""
    return repr(float(value)) if math.isfinite(value) else None


ORDER = {'=': lambda x, y: x == y, '!=': lambda x, y: x != y, '<': lambda x, y: x < y,
         '>': lambda x, y: x > y, '<=': lambda x, y: x <= y, '>=': lambda x, y: x >= y}


def compare(op, left, right):
    """As the classic method compiles SPARQL's comparisons: numbers by their
    value, texts by their characters; a text and a number are unequal and not
    ordered; a number and a literal which reads as none are an error."""
    kinds = kind(left), kind(right)
    numbers = number(left), number(right)
    unequal = {'=': False, '!=': True}.get(op)
    if 'S' in kinds:
        # a string constant: by its text with any literal, else as the terms
        other = kinds[1] if kinds[0] == 'S' else kinds[0]
        if other in ('S', 'T', 'P'):
            return ORDER[op](lexical(left), lexical(right))
        return ORDER[op](rdf_term(left), rdf_term(right))
    if 'T' in kinds:
        other, k = (right, kinds[1]) if kinds[0] == 'T' else (left, kinds[0])
        if k == 'T' or k == 'P' and number(other) is None:
            return ORDER[op](lexical(left), lexical(right))
        return unequal
    if None not in numbers:
        return ORDER[op](*numbers)
    if 'N' in kinds and 'I' not in kinds and 'B' not in kinds:
        return None             # a number and a literal which reads as none
    if kinds == ('P', 'P') and numbers == (None, None):
        return ORDER[op](lexical(left), lexical(right))
    if kinds in (('I', 'I'), ('B', 'B')):
        return ORDER[op](lexical(left), lexical(right)) if op in ('=', '!=') else None
    return unequal


def rdf_term(value):
    """The text of a value's RDF term, as the classic method compares terms"""
    k = kind(value)
    if k in ('S', 'T', 'P'):
        return f'"{lexical(value)}"'
    return lexical(value) if k == 'B' else value


DATETIME = re.compile(r'([0-9]{4}-[0-9]{2}-[0-9]{2})[T ]([0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,3})[0-9]*)?Z?')


def truth(value):
    return value if isinstance(value, bool) else {'true': True, 'false': False}.get(value)


def evaluate(ast, slots):
    op = ast[0]
    if op == 's':
        return slots[ast[1]] or None if ast[1] < len(slots) else None
    if op == 'c':
        return ast[1]
    if op in ('and', 'or'):
        # SPARQL's logic of three values: an error (None) decides nothing
        # when another operand decides alone
        values = [truth(evaluate(a, slots)) for a in ast[1:]]
        decisive = op == 'or'
        if any(v is decisive for v in values):
            return decisive
        return None if any(v is None for v in values) else not decisive
    if op == 'bound':
        return evaluate(ast[1], slots) is not None
    if op == 'if':
        condition = truth(evaluate(ast[1], slots))
        if condition is None:
            return None             # an error in the condition is an error of IF
        return evaluate(ast[2] if condition else ast[3], slots)
    if op == 'concat':
        # the text of a message: every value as its text, NULL for none
        values = [evaluate(a, slots) for a in ast[1:]]
        return "'" + ''.join('NULL' if v is None else lexical(v) for v in values) + "'"
    args = [evaluate(a, slots) for a in ast[1:]]
    if any(a is None for a in args):
        return None
    if op == 'not':
        value = truth(args[0])
        return None if value is None else not value
    if op in ORDER:
        return compare(op, *args)
    if op == 'string':
        return f"'{lexical(args[0])}'"
    if op == 'join':
        # SPARQL CONCAT takes texts: a number, an IRI or a truth value is none
        if any(kind(a) not in ('T', 'S', 'P') for a in args):
            return None
        return "'" + ''.join(lexical(a) for a in args) + "'"
    if op == 'dateTime':
        match = DATETIME.fullmatch(lexical(args[0]))
        return f'"{match[1]}T{match[2]}.{(match[3] or "").ljust(3, "0")}Z"' if match else None
    numbers = [number(a) for a in args]
    if any(n is None for n in numbers):
        return None
    if op == 'integer':
        return f'{int(numbers[0])}' if abs(numbers[0]) < 1e18 else None
    if op == 'float':
        return float_term(numbers[0])
    left, right = numbers
    if op == '/' and right == 0:
        return None
    return number_term(left + right if op == '+' else left - right if op == '-' else
                       left * right if op == '*' else left / right)


def key_part(value):
    """Equal values, equal keys: a number by its value, a text and a literal of
    the data which reads as no number by their characters."""
    if isinstance(value, bool):
        value = lexical(value)
    n = number(value)
    if n is not None:
        return '#' + (number_term(n) or lexical(value))
    if kind(value) in ('T', 'S', 'P'):
        return "'" + lexical(value)
    return value


def make_key(key, slots):
    """Unbound never joins. Every part ends with SEP, so no two keys run into each other."""
    values = [evaluate(part, slots) for part in key]
    return None if any(v is None for v in values) else ''.join(key_part(v) + SEP for v in values)


def holds(condition, slots):
    return not condition or evaluate(condition, slots) is True


def udf_route(lvl, node, side, key, flt, path, s, o, ts):
    """A fact as a leaf row: [level, node, side, key, bindings, path] or NULL"""
    if s is None or o is None:
        return None
    slots = [v.replace(SEP, '') for v in (s, o, ts or '')]
    if not holds(json.loads(flt) if flt else None, slots):
        return None
    return json.dumps([lvl, node, side, make_key(json.loads(key), slots), SEP.join(slots), path])


def udf_step(level, path, left, right):
    """A joined row as an input of the next level, or NULL"""
    if left is None or not path:
        return None
    kind, condition, width, side, key, node = json.loads(path)[level - 1]
    if kind == 'inner' and right is None or kind == 'anti' and right is not None:
        return None
    bindings = left + SEP + (right if right is not None else SEP * (width - 1))
    slots = bindings.split(SEP)
    if not holds(condition, slots):
        return None
    return json.dumps([level + 1, node, side, make_key(key, slots), bindings, path if side == 'L' else ''])


def udf_value(expression, bindings):
    if expression is None or bindings is None:
        return None
    value = evaluate(json.loads(expression), bindings.split(SEP))
    return lexical(value) if isinstance(value, bool) else value


def udf_text(expression, bindings):
    value = udf_value(expression, bindings)
    return None if value is None else lexical(value)


def udf_group(group, bindings):
    if group is None or bindings is None:
        return None
    slots = bindings.split(SEP)
    return SEP.join(evaluate(g, slots) or '' for g in json.loads(group))


SQLITE_FUNCTIONS = {'sparql_route': (9, udf_route), 'sparql_step': (4, udf_step), 'sparql_value': (2, udf_value),
                    'sparql_text': (2, udf_text), 'sparql_group': (2, udf_group)}


def register_sqlite(connection):
    for name, (num_args, function) in SQLITE_FUNCTIONS.items():
        connection.create_function(name, num_args, function, deterministic=True)
