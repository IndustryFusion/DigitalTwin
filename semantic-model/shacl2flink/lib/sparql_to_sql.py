#
# Copyright (c) 2022, 2023 Intel Corporation
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

import sys
import re
from rdflib import Graph, Namespace, URIRef, Variable, BNode, Literal
from rdflib.collection import Collection
from rdflib.namespace import RDF, SH, XSD, RDFS
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.algebra import translateQuery
from functools import reduce
import copy


import lib.utils as utils
import lib.bgp_translation_utils as bgp_translation_utils
import lib.configs as configs


sh = Namespace("http://www.w3.org/ns/shacl#")

iff = Namespace("https://industry-fusion.com/types/v0.9/")
IFA = Namespace("https://industry-fusion.com/aggregators/v0.9/")
IFN = Namespace("https://industry-fusion.com/functions/v0.9/")

debug = 0
debugoutput = sys.stdout
dummyvar = 'dummyvar'


properties = {}
relationships = {}
read_from = None
# The projected variables of the last query translated that hold a term
# ('"text"', '<iri>') and not the value of an attribute: what BIND computed.
terms = set()
# the column of an attribute's value, and nothing computed from one
VALUE_COLUMN = re.compile(r'`\w+`\.`attributeValue`')
g = Graph()


def translate_sparql(shaclfile, knowledgefile, sparql_query, target_class, lg):
    """
    Translates shaclfile + knowledgefile into SQL instructions

    Parameters:
        shaclfile (string)    : filename of shacl file
        knowledgefile (string): filename of knowledge file
        sparql_query (string) : query as string
        target_class          : class of the `this` variable

    Returns:
        sql_term (string)
        used sql-tables (dict[string])
    """
    global g
    g = lg
    read_attributes(g)
    parsed_query = None
    try:
        parsed_query = translateQuery(parseQuery(sparql_query))
    except Exception as e:
        raise utils.SparqlValidationFailed(f'The query does not parse: {e}')
    ctx = translate_query(parsed_query, target_class, sparql_query)
    terms.clear()
    computed = ctx.get('computed') or ()
    terms.update(utils.create_varname(var) for var in ctx.get('PV') or () if var in computed)
    return ctx['target_sql'], ctx['sql_tables']


def value_shapes(graph, shape):
    """The property shapes of an attribute's payload: directly under its
    property shape, or under one branch of a connective."""
    clauses = [shape]
    for connective in (SH['or'], SH['and'], SH.xone):
        for branches in graph.objects(shape, connective):
            clauses += Collection(graph, branches)
    clauses += graph.objects(shape, SH['not'])
    for clause in clauses:
        for inner in graph.objects(clause, SH.property):
            yield inner, graph.value(inner, SH.path)


def node_kinds(graph, inner):
    """sh:nodeKind of a value shape, its own or of a branch of its sh:or."""
    yield from graph.objects(inner, SH.nodeKind)
    for branches in graph.objects(inner, SH['or']):
        for branch in Collection(graph, branches):
            yield from graph.objects(branch, SH.nodeKind)


def read_attributes(graph):
    """What the shapes say about attributes, once per graph: every query of a
    package asks for the same. With or without a target, since a shape may be
    reached through sh:node alone. A walk and not a query: rdflib takes half a
    minute for the property paths on a large package."""
    global read_from
    if read_from is not None and read_from[0] is graph and read_from[1] == len(graph):
        return
    properties.clear()
    relationships.clear()
    for shape in graph.subjects(RDF.type, SH.NodeShape):
        for prop in graph.objects(shape, SH.property):
            attributes = [path.toPython() for path in graph.objects(prop, SH.path) if isinstance(path, URIRef)]
            for inner, payload in value_shapes(graph, prop):
                for attribute in attributes:
                    if payload == bgp_translation_utils.ngsild['hasObject']:
                        relationships[attribute] = True
                    elif payload == bgp_translation_utils.ngsild['hasValue']:
                        for kind in node_kinds(graph, inner):
                            # One attribute, an IRI in one shape and a literal
                            # in another: the instance decides.
                            if properties.setdefault(attribute, kind == SH.IRI) != (kind == SH.IRI):
                                properties[attribute] = utils.ANY_VALUE
    read_from = (graph, len(graph))


def translate_query(query, target_class, orig_query):
    """
    Decomposes parsed SparQL object
    query: parsed sparql object
    """
    algebra = query.algebra
    randomstr = 'this' + bgp_translation_utils.get_unique_suffix(16)
    ctx = {
        'namespace_manager': query.prologue.namespace_manager,
        'relationships': relationships,
        'properties': properties,
        'g': g,
        'PV': algebra.PV,
        'classes': {'this': target_class},
        'sql_tables': ['attributes'],
        'bounds': {},
        # $this is an entity, even where the first patterns read nothing of it.
        'entity_variables': {Variable('this'): True},
        'property_variables': {},
        'time_variables': {},
        'tables': {},
        'target_sql': '',
        'target_where': '',
        'target_modifiers': [],
        'add_triples': [(Variable('this'), RDF['type'], Variable(randomstr)),
                        (Variable(randomstr),
                         RDFS['subClassOf'],
                         target_class)],
        'query': orig_query,
        'ttl_aware_tables': []  # Tables which need special handling for TTL (e.g. RDF which is relatatively static)
    }
    if algebra.name == 'SelectQuery' or algebra.name == 'ConstructQuery':
        translate(ctx, algebra)
    else:
        raise utils.WrongSparqlStructure('Only SelectQueries are supported \
currently!')
    ctx['target_sql'] = algebra['target_sql']
    return ctx


def translate(ctx, elem):
    """
    Translate all objects
    """
    if isinstance(elem, URIRef) or isinstance(elem, Literal):
        return utils.format_node_type(elem)
    elif isinstance(elem, Variable):
        try:
            return utils.wrap_ngsild_variable(ctx, elem)
        except Exception as e:
            raise utils.SparqlValidationFailed(str(e))
    if elem.name == 'SelectQuery':
        return translate_select_query(ctx, elem)
    elif elem.name == 'ConstructQuery':
        return translate_construct_query(ctx, elem)
    elif elem.name == 'Project':
        result = translate_project(ctx, elem)
        return result
    elif elem.name == 'Filter':
        translate_filter(ctx, elem)
    elif elem.name == 'BGP':
        translate_BGP(ctx, elem)
    elif elem.name == 'ConditionalAndExpression':
        result = translate_and_expression(ctx, elem)
        return result
    elif elem.name == 'ConditionalOrExpression':
        result = translate_or_expression(ctx, elem)
        return result
    elif elem.name == 'RelationalExpression':
        result = translate_relational_expression(ctx, elem)
        return result
    elif elem.name == 'Join':
        return translate_join(ctx, elem)
    elif elem.name == 'Builtin_NOTEXISTS':
        return translate_notexists(ctx, elem)
    elif elem.name == 'Builtin_EXISTS':
        return translate_notexists(ctx, elem, 'EXISTS')
    elif elem.name == 'Distinct':
        return translate_distinct(ctx, elem)
    elif elem.name == 'LeftJoin':
        return translate_left_join(ctx, elem)
    elif elem.name == 'Extend':
        return translate_extend(ctx, elem)
    elif elem.name == 'Builtin_IF' and is_text(elem, ctx):
        return translate_text(ctx, elem)
    elif elem.name == 'Builtin_IF':
        return translate_builtin_if(ctx, elem)
    elif elem.name in TEXT_FUNCTIONS:
        return translate_text(ctx, elem)
    elif elem.name == 'Builtin_NOW':
        return translate_builtin_now(ctx, elem)
    elif elem.name == 'Function':
        return translate_function(ctx, elem)
    elif elem.name == 'AdditiveExpression':
        return translate_additive_expression(ctx, elem)
    elif elem.name == 'Builtin_BOUND':
        return translate_builtin_bound(ctx, elem)
    elif elem.name == 'AggregateJoin':
        translate_aggregate_join(ctx, elem)
    elif elem.name == 'Group':
        translate_group(ctx, elem)
    elif elem.name == 'Aggregate_Count':
        return translate_aggregate_count(ctx, elem)
    elif elem.name == 'Aggregate_Sum':
        return translate_aggregate_sum(ctx, elem)
    elif elem.name == 'UnaryNot':
        return translate_unary_not(ctx, elem)
    elif elem.name == 'MultiplicativeExpression':
        return translate_multiplicative_expression(ctx, elem)
    else:
        name = SPARQL_NAMES.get(elem.name, re.sub(r'^(Builtin|Aggregate)_', '', elem.name))
        raise utils.WrongSparqlStructure(f'{name} is not supported.')


SPARQL_NAMES = {'Union': 'UNION', 'Minus': 'MINUS', 'ToMultiSet': 'VALUES or a sub-select',
                'OrderBy': 'ORDER BY', 'Slice': 'LIMIT/OFFSET', 'UnaryMinus': 'a minus sign before an expression',
                'Graph': 'GRAPH', 'ServiceGraphPattern': 'SERVICE'}


def translate_distinct(ctx, elem):
    ctx['target_modifiers'].append('Distinct')
    translate(ctx, elem.p)
    elem['target_sql'] = elem.p['target_sql']
    elem['where'] = elem.p['where']


def translate_unary_not(ctx, elem):
    expression = translate(ctx, elem.expr)
    return f" NOT ({expression}) "


def process_aggregate(ctx, elem):
    distinct = elem.distinct
    utils.set_is_aggregate_var(ctx, True)
    expression = translate(ctx, elem.vars)
    utils.set_is_aggregate_var(ctx, False)
    distinct_string = 'DISTINCT'
    if distinct != 'DISTINCT':
        distinct_string = ''
    return expression, distinct_string


def translate_aggregate_sum(ctx, elem):
    expression, distinct = process_aggregate(ctx, elem)
    return f"SUM({distinct} {expression})"


def translate_aggregate_count(ctx, elem):
    expression, distinct = process_aggregate(ctx, elem)
    return f"COUNT({distinct} {expression})"


def translate_group(ctx, elem):
    utils.set_group_by_vars(ctx, elem.expr)
    utils.add_group_by_vars(ctx, Variable('this'))
    translate(ctx, elem.p)
    elem['target_sql'] = elem.p['target_sql']
    elem['where'] = elem.p['where']


def translate_aggregate_join(ctx, elem):
    translate(ctx, elem.p)
    vars = utils.get_aggregate_vars(ctx)
    try:
        elem['target_sql'] = bgp_translation_utils.replace_attributes_table_expression(elem.p['target_sql'], vars)
    except Exception:
        raise utils.SparqlValidationFailed('Group by aggregation defined but no aggregated variables found.')
    elem['where'] = elem.p['where']


def translate_builtin_bound(ctx, elem):
    bounds = ctx['bounds']
    varname = utils.create_varname(elem.arg)
    if varname not in bounds:
        raise utils.SparqlValidationFailed(f'?{varname} is not bound here: no pattern the compiler could \
translate gives it a value.')
    return f"{bounds[varname]} IS NOT NULL "


def translate_additive_expression(ctx, elem):
    if isinstance(elem.expr, Variable):
        expr = utils.unwrap_variables(ctx, elem.expr)
    else:  # Neither Variable, nor Literal, nor IRI - hope it is further translatable
        expr = translate(ctx, elem.expr)

    for op, other in zip(elem.op, elem.other):
        if isinstance(other, Variable):
            other_val = utils.unwrap_variables(ctx, other)
        else:
            other_val = translate(ctx, other)
        expr += f" {op} {other_val} "

    return expr


def translate_multiplicative_expression(ctx, elem):
    expr = translate(ctx, elem.expr)

    for op, other in zip(elem.op, elem.other):

        other_val = translate(ctx, other)
        expr += f" {op} {other_val} "

    return expr


def translate_function(ctx, function):
    iri = function.iri
    expr = function.expr
    numargs = len(expr)

    # This is only supporting single parameter functions
    # TODO: Generalize the functin translation for arbitrary parameters
    expression = None
    if iri in XSD:  # CAST
        if numargs != 1:
            raise utils.WrongSparqlStructure('CASTS need only one parameter.')
        expression = translate(ctx, expr[0])

        cast = 'notfound'
        stringcast = False
        if iri != XSD['dateTime']:
            if iri == XSD['integer']:
                cast = 'INTEGER'
            elif iri == XSD['float']:
                cast = 'FLOAT'
            elif iri in (XSD['double'], XSD['decimal']):
                cast = 'DOUBLE'
            elif iri == XSD['string']:
                cast = 'STRING'
                stringcast = True
            if cast == 'notfound':
                raise utils.WrongSparqlStructure(f'The cast xsd:{iri[len(XSD):]}() is not supported.')
            if not stringcast:
                result = f'SQL_DIALECT_CAST(SQL_DIALECT_STRIP_LITERAL{{{expression}}} as {cast})'
            else:
                result = f'SQL_DIALECT_CAST(SQL_DIALECT_STRIP_IRI{{{expression}}} as {cast})'
        else:
            # xsd:dateTime() normalizes its argument into the canonical
            # ISO 8601 UTC string, the same quoted form wrap_ngsild_variable
            # gives observedAt-bound variables -- so FILTER(?ts > xsd:dateTime(
            # ?value)) compares ISO against ISO, lexically == chronologically.
            result = f"'\"' || SQL_DIALECT_ISO_TIMESTAMP{{SQL_DIALECT_STRIP_LITERAL{{{expression}}}}} || '\"'"
    elif iri in IFA:
        udf = utils.strip_class(iri)
        result = f'{udf}('
        utils.set_is_aggregate_var(ctx, True)
        for i in range(0, numargs):
            if i != 0:
                result += ', '
            result += translate_udf_argument(ctx, expr[i])
        utils.set_is_aggregate_var(ctx, False)
        result += ')'
    elif iri in IFN:
        udf = utils.strip_class(iri)
        result = f'{udf}('
        for i in range(0, numargs):
            if i != 0:
                result += ', '
            result += translate_udf_argument(ctx, expr[i])
        utils.set_is_aggregate_var(ctx, False)
        result += ')'
    else:
        raise utils.WrongSparqlStructure(f'The function {iri.toPython()} is not supported.')
    return result


def translate_udf_argument(ctx, arg):
    """UDF arguments live in the numeric domain: a time-bound variable is
    handed to the UDF as epoch milliseconds (the UDFs' contract, e.g.
    statetime subtracts its inputs), not as the quoted ISO string the
    serialization/comparison domain uses."""
    if isinstance(arg, Variable) and arg in ctx.get('time_variables', {}):
        return utils.unwrap_variables(ctx, arg)
    return translate(ctx, arg)


TEXT_FUNCTIONS = ('Builtin_CONCAT', 'Builtin_STR')


def is_text(elem, ctx=None):
    """Whether an expression is a text whatever it is applied to: what CONCAT
    and STR give, a variable BIND gave such a text, or IF chooses between two
    texts, one of them given so. (An IF between two constants is compiled as
    it was before.)"""
    if isinstance(elem, Variable):
        return ctx is not None and is_text_variable(ctx, elem)
    name = getattr(elem, 'name', None)
    if name == 'Builtin_IF':
        return all(is_text(arg, ctx) or is_string(arg) for arg in (elem.arg2, elem.arg3)) and \
            (is_text(elem.arg2, ctx) or is_text(elem.arg3, ctx))
    return name in TEXT_FUNCTIONS


def is_string(elem):
    """A constant simple literal, a string or one with a language."""
    return isinstance(elem, Literal) and (elem.datatype in (None, XSD.string) or elem.language is not None)


def is_text_variable(ctx, elem):
    return isinstance(elem, Variable) and elem in ctx.get('texts', ())


BOOLEANS = ('RelationalExpression', 'ConditionalAndExpression', 'ConditionalOrExpression', 'UnaryNot',
            'Builtin_BOUND', 'Builtin_EXISTS', 'Builtin_NOTEXISTS')


def is_boolean(elem):
    return getattr(elem, 'name', None) in BOOLEANS or (isinstance(elem, Literal) and elem.datatype == XSD.boolean)


def is_no_text(ctx, elem):
    """What is no text whatever it is applied to."""
    if is_number(elem) or is_boolean(elem) or isinstance(elem, URIRef) or \
            (isinstance(elem, Literal) and not is_string(elem)):
        return True
    return isinstance(elem, Variable) and elem not in ctx.get('texts', ()) and \
        (elem in ctx['time_variables'] or elem in ctx.get('booleans', ()) or elem in ctx.get('no_texts', ()) or
         elem in ctx.get('moments', ()) or
         ctx['property_variables'].get(elem) is True or
         (elem in ctx['entity_variables'] and elem not in ctx['property_variables']))


def argument_of_concat(ctx, elem):
    """CONCAT takes texts. What is no text for sure is refused: SPARQL gives no
    result for it, and STR gives its text."""
    if getattr(elem, 'name', None) == 'Builtin_IF':
        condition = translate(ctx, elem.arg1)
        return f'(CASE WHEN {condition} THEN {argument_of_concat(ctx, elem.arg2)} ' \
               f'WHEN NOT ({condition}) THEN {argument_of_concat(ctx, elem.arg3)} END)'
    if is_no_text(ctx, elem):
        name = elem.n3() if isinstance(elem, (Variable, URIRef)) else sparql_constant(elem) \
            if isinstance(elem, Literal) else None
        raise utils.WrongSparqlStructure(f'CONCAT takes texts, and {name} is none. Use STR({name}).' if name else
                                         'CONCAT takes texts, and a number or a truth value is none. Use STR(…).')
    return text_at_run_time(ctx, elem, numbers=True)


def text_at_run_time(ctx, elem, numbers):
    """The text of what is a text only at run time, NULL when it is none: what
    the knowledge holds is a text if it is a string, a Property's value if it
    is no IRI (and, unless numbers, no number), and what BIND computed if its
    term is a string."""
    if not isinstance(elem, Variable) or elem in ctx.get('lexicals', {}):
        return lexical(ctx, elem)
    term = translate(ctx, elem)
    column = ctx['bounds'][utils.create_varname(elem)]
    if elem in ctx['property_variables'] and elem not in ctx.get('computed', ()):
        conditions = []
        if ctx['property_variables'][elem] == utils.ANY_VALUE:
            conditions.append(f"{column.replace('attributeValue', 'nodeType')} <> '@id'")
        if not numbers:
            conditions.append(f'SQL_DIALECT_NUMBER{{{column}}} IS NULL')
        return f"(CASE WHEN {' AND '.join(conditions)} THEN {column} END)" if conditions else column
    if is_knowledge_variable(ctx, elem) or elem in ctx.get('computed', ()):
        return f'SQL_DIALECT_STRING_OF_TERM{{{brace_free(term)}}}'
    return lexical(ctx, elem)


def sparql_constant(literal):
    """A constant as it is written in a query."""
    if literal.datatype in NUMERIC or literal.datatype == XSD.boolean:
        return str(literal)
    xsd = str(XSD)
    if literal.datatype is not None and str(literal.datatype).startswith(xsd):
        return f'"{literal}"^^xsd:{str(literal.datatype)[len(xsd):]}'
    return literal.n3()


def is_knowledge_variable(ctx, elem):
    """A variable whose term the knowledge gives: an IRI, a string, a number or
    a blank node, each written as its term."""
    if elem in ctx['property_variables'] or elem in ctx['time_variables'] or elem in ctx.get('computed', ()) \
            or elem in ctx['entity_variables']:
        return False
    bound = ctx['bounds'].get(utils.create_varname(elem), '')
    return re.search(r"\.`?(object|subject)`?$", bound) is not None


def brace_free(sql):
    """SQL whose string constants hold no brace: what a dialect macro may take
    as its argument. A brace becomes a character code."""
    out, quoted, i = [], False, 0
    while i < len(sql):
        char = sql[i]
        if char == "'":
            if quoted and sql[i + 1:i + 2] == "'":
                out.append("''")
                i += 2
                continue
            quoted = not quoted
        if quoted and char in '{}':
            out.append("' || SQL_DIALECT_CHAR_" + ('OPEN' if char == '{' else 'CLOSE') + " || '")
        else:
            out.append(char)
        i += 1
    return ''.join(out)


def translate_text(ctx, elem):
    """CONCAT or STR: a simple literal, its text written by lexical()."""
    return f"('\"' || {brace_free(lexical(ctx, elem))} || '\"')"


def lexical(ctx, elem):
    """The text of an expression, without the quotes or brackets of its term.

    A constant is written as it is, and what an attribute holds is read
    without its delimiters: stripping them would also take such characters out
    of the text. Only a term computed or read from the knowledge loses one
    delimiter at each end. An unbound argument is NULL, and so is the text.
    """
    if isinstance(elem, (URIRef, Literal)):
        return sql_text(str(elem))
    if isinstance(elem, Variable):
        return lexical_of_variable(ctx, elem)
    name = getattr(elem, 'name', None)
    if name == 'Builtin_STR':
        return lexical(ctx, elem.arg)
    if name == 'Builtin_CONCAT':
        # CONCAT() has rdf:nil for its arguments
        arguments = elem.arg if isinstance(elem.arg, list) else []
        return '(' + ' || '.join(argument_of_concat(ctx, arg) for arg in arguments) + ')' if arguments else "''"
    if name == 'Builtin_IF':
        # a condition without a value chooses neither: the text is unbound
        condition = translate(ctx, elem.arg1)
        return f'(CASE WHEN {condition} THEN {lexical(ctx, elem.arg2)} ' \
               f'WHEN NOT ({condition}) THEN {lexical(ctx, elem.arg3)} END)'
    if name == 'Builtin_NOW':
        return f'SQL_DIALECT_ISO_TIMESTAMP{{{translate(ctx, elem)}}}'
    if is_boolean(elem):
        condition = translate(ctx, elem)
        return f"(CASE WHEN {condition} THEN 'true' WHEN NOT ({condition}) THEN 'false' END)"
    return f'SQL_DIALECT_STRIP_TERM{{{brace_free(translate(ctx, elem))}}}'


def lexical_of_variable(ctx, var):
    term = translate(ctx, var)           # says it if the variable is unbound
    if var in ctx.get('lexicals', {}):
        return ctx['lexicals'][var]      # a text BIND gave: as it was built
    column = ctx['bounds'][utils.create_varname(var)]
    if var in ctx.get('booleans', ()):
        return f"(CASE WHEN {column} THEN 'true' WHEN NOT ({column}) THEN 'false' END)"
    if var in ctx.get('moments', ()):
        return f'SQL_DIALECT_ISO_TIMESTAMP{{{column}}}'
    if var in ctx['property_variables'] and var not in ctx.get('computed', ()):
        return column
    if var in ctx['time_variables']:
        return f'SQL_DIALECT_ISO_TIMESTAMP{{{column}}}'
    if var in ctx['entity_variables']:
        return column
    return f'SQL_DIALECT_STRIP_TERM{{{brace_free(term)}}}'


def sql_text(text):
    """A text as an SQL string. A brace is written as a character code: the
    dialect macros cannot have one in their argument."""
    parts = re.split(r'([{}])', text.replace("'", "''"))
    return '(' + ' || '.join('SQL_DIALECT_CHAR_' + ('OPEN' if part == '{' else 'CLOSE') if part in ('{', '}')
                             else f"'{part}'" for part in parts if part != '') + ')' if text else "''"


def translate_builtin_now(ctx, builtin_now):
    return 'SQL_DIALECT_CURRENT_TIMESTAMP'


def translate_builtin_if(ctx, builtin_if):
    condition = translate(ctx, builtin_if.arg1)
    ifyes = translate(ctx, builtin_if.arg2)
    ifnot = translate(ctx, builtin_if.arg3)

    expression = f'CASE WHEN {condition} THEN {ifyes} ELSE {ifnot} END'
    return expression


def translate_extend(ctx, extend):
    translate(ctx, extend.p)

    expression = translate(ctx, extend.expr)
    if isinstance(extend.expr, Variable):
        if extend.expr in ctx['entity_variables']:
            raise utils.SparqlValidationFailed(f'?{extend.expr} is an entity, and another name for an entity \
(BIND) is not supported. Use ?{extend.expr} itself.')
        # another name for the same value: what it is, it is under this name, too
        for kinds in ('property_variables', 'time_variables'):
            if extend.expr in ctx[kinds]:
                ctx[kinds] = {**ctx[kinds], extend.var: ctx[kinds][extend.expr]}
                expression = ctx['bounds'][utils.create_varname(extend.expr)]
        for kinds in ('computed', 'texts', 'booleans', 'no_texts', 'moments'):
            if extend.expr in ctx.get(kinds, ()):
                ctx[kinds] = ctx[kinds] | {extend.var}
        if extend.expr in ctx.get('lexicals', {}):
            ctx['lexicals'] = {**ctx['lexicals'], extend.var: ctx['lexicals'][extend.expr]}
    else:
        if utils.get_group_by_vars(ctx) is None:
            ctx['computed'] = ctx.get('computed', set()) | {extend.var}
        if is_boolean(extend.expr) and not isinstance(extend.expr, Literal):
            ctx['booleans'] = ctx.get('booleans', set()) | {extend.var}
        if isinstance(extend.expr, Literal) and not is_string(extend.expr):
            ctx['no_texts'] = ctx.get('no_texts', set()) | {extend.var}
        if getattr(extend.expr, 'name', None) == 'Builtin_NOW':
            ctx['moments'] = ctx.get('moments', set()) | {extend.var}
        if is_text(extend.expr, ctx):
            ctx['texts'] = ctx.get('texts', set()) | {extend.var}
            # its text, kept to be read again without stripping the term
            ctx['lexicals'] = {**ctx.get('lexicals', {}), extend.var: brace_free(lexical(ctx, extend.expr))}
            expression = f"('\"' || {ctx['lexicals'][extend.var]} || '\"')"

    ctx['bounds'][utils.create_varname(extend.var)] = expression
    extend['target_sql'] = extend.p['target_sql']
    extend['where'] = extend.p['where']


def translate_select_query(ctx, query):
    """
    Decomposes SelectQuery object
    """
    translate(ctx, query.p)
    query['target_sql'] = query.p['target_sql']
    return


def translate_construct_query(ctx, query):
    """
    Decomposes SelectQuery object
    """
    h = Graph()
    for s, p, o in query.template:
        h.add((s, p, o))
    property_variables, entity_variables, time_variables = bgp_translation_utils.create_ngsild_mappings(ctx, h)

    translate(ctx, query.p)
    query['target_sql'] = query.p['target_sql']
    query['where'] = query.p['where']
    bgp_translation_utils.merge_vartypes(ctx, property_variables, entity_variables, time_variables, True)
    wrap_sql_construct(ctx, query)
    return


def translate_project(ctx, project):
    """
    Translate Project structure
    """
    translate(ctx, project.p)
    project['target_sql'] = project.p['target_sql']
    project['where'] = project.p['where']
    # if this is part of a construct query, ctx['PV'] is None, so do not wrap
    if ctx['PV'] is not None:
        wrap_sql_projection(ctx, project)


def wrap_sql_construct(ctx, node):
    # For the time being, only wrap properties, no relationships
    columns = get_attribute_columns(ctx, node)
    first = True
    construct_query = "SQL_DIALECT_INSERT_ATTRIBUTES\n"
    bounds = ctx['bounds']
    # Every UNION ALL branch below reads the same FROM, so the same knowledge
    # has to be pinned in each of them. A rule whose rdf join expires stops
    # writing its attributes back, silently.
    select_hint = rdf_state_ttl_hint(node['target_sql'])

    for (entityId_var, name, attribute_type, value_var, node_type) in columns:
        if first:
            first = False
        else:
            construct_query += "\nUNION ALL\n"
        entityId_varname = entityId_var.toPython()[1:]
        entityId = bounds[entityId_varname]
        # Name the attribute the way its other writer does, so the rule
        # updates the existing instance instead of adding a second one beside
        # it. See utils.attribute_id_suffix.
        id = f"{entityId} || SQL_DIALECT_ATTRIBUTE_ID{{{name}}}"
        construct_query += f"SELECT {select_hint}DISTINCT "
        construct_query += f'{id} as id,\n'
        construct_query += 'CAST(NULL as STRING) as parentId,\n'
        construct_query += f'{bounds[entityId_varname]} as entityId,\n'  # entityId
        construct_query += f'\'{name}\' as name,\n'  # name
        construct_query += f'{expression_or_text(node_type)} as nodeType,\n'  # nodeType
        construct_query += 'CAST(NULL as STRING) as valueType,\n'  # valueType
        construct_query += f'\'{attribute_type}\' as `type`,\n'
        construct_query += f"{get_bound_trim_string(ctx, value_var)} as `attributeValue`,\n"  # value
        construct_query += '\'@none\' as `datasetId`,\n'
        construct_query += 'CAST(NULL as STRING) as unitCode,\n'  # unitCode
        construct_query += 'CAST(NULL as STRING) as lang,\n'  # unitCode
        construct_query += 'false as `deleted`,\n'  # unitCode
        construct_query += 'false as `synched`\n'  # unitCode
        construct_query += ',SQL_DIALECT_SQLITE_TIMESTAMP\n'  # ts

        construct_query += 'FROM ' + node['target_sql']
        if node['where'] != '':
            construct_query += ' WHERE ' + node['where']
        group_by = create_group_by(ctx)
        if group_by is not None:
            construct_query += f' GROUP BY {group_by}'
    node['target_sql'] = construct_query


def expression_or_text(value):
    return value if '`' in value or value.startswith('CASE ') else f"'{value}'"


def get_bound_trim_string(ctx, boundsvar):
    bounds = ctx['bounds']
    boundsvarname = boundsvar.toPython()[1:]
    if boundsvarname in bounds and boundsvar in ctx.get('lexicals', {}):
        # its text, a quote in it kept
        return ctx['lexicals'][boundsvar]
    if boundsvarname in bounds and boundsvar in ctx['property_variables']:
        if ctx['property_variables'][boundsvar] == utils.ANY_VALUE:
            column = bounds[boundsvarname]
            if VALUE_COLUMN.fullmatch(column):
                return column
            return f"CASE WHEN {column} LIKE '<%' THEN SQL_DIALECT_STRIP_IRI{{{column}}} \
ELSE SQL_DIALECT_STRIP_LITERAL{{{column}}} END"
        if ctx['property_variables'][boundsvar]:
            return f"SQL_DIALECT_STRIP_IRI{{{bounds[boundsvarname]}}}"
        else:
            return f"SQL_DIALECT_STRIP_LITERAL{{{bounds[boundsvarname]}}}"
    elif boundsvarname in bounds and boundsvar in ctx['time_variables']:
        return f"SQL_DIALECT_STRIP_LITERAL{{{bounds[boundsvarname]}}}"
    else:
        raise utils.WrongSparqlStructure(f"Trying to trim non-bound variable ?{boundsvarname}.")


def get_attribute_columns(ctx, node):
    entityId_var = None
    name = None
    properties = ctx['properties']
    value_var = None
    predicates = {}
    result = []
    for (s, p, o) in node['template']:
        if p.toPython() in properties:
            predicates[o.toPython()] = (s, p)
        elif p.toPython() in relationships:
            raise utils.WrongSparqlStructure('Construction of relationship not yet implemented')
    for (s, p, o) in node['template']:
        if s.toPython() not in predicates:
            continue
        value_var = o
        entityId_var, name = predicates[s.toPython()]
        attribute_type = bgp_translation_utils.ngsild['Property'] if value_var in ctx['property_variables'] else \
            bgp_translation_utils.ngsild['Relationship']
        kind = ctx['property_variables'].get(value_var)
        nodetype = '@id' if kind else '@value'
        if kind == utils.ANY_VALUE:
            # what the value itself is
            column = ctx['bounds'].get(utils.create_varname(value_var), '')
            nodetype = column.replace('attributeValue', 'nodeType') if VALUE_COLUMN.fullmatch(column) else \
                f"CASE WHEN {column} LIKE '<%' THEN '@id' ELSE '@value' END"
        result.append((entityId_var, name.toPython(), attribute_type.toPython(), value_var, nodetype))
    return result


def rdf_state_ttl_hint(target_sql):
    """Pin the knowledge in place for the query block that reads it.

    `rdf` holds the ontology. It is written once when the KMS is deployed and
    never again, so unlike entities_view and attributes_view -- which the
    debezium connector re-snapshots every flink.ttl/2 -- nothing refreshes it.
    In Flink a join keeps its right side as STATE, not as a table that is
    simply there, so under the job's table.exec.state.ttl the knowledge expires
    an hour after deployment and the join stops matching.

    What that does to a constraint depends on how it reads the knowledge, and
    both directions are wrong. An inner join yields no rows, so the constraint
    goes silent and a real violation is never reported. A FILTER NOT EXISTS
    compiles to LEFT JOIN ... IS NULL, which then holds vacuously, so the
    constraint fires against data that is perfectly valid. Measured on a live
    cluster: the same violating entity raised its alert 100 s after the job
    started and raised nothing at all 531 s in, with a 300 s ttl.

    Nothing catches it. The SQLite oracle has no state and no ttl, so it keeps
    answering correctly and agreeing with itself, and the divergence only shows
    up against a Flink job that has been running for an hour.

    entities_view and attributes_view joins are pinned for the same reason,
    and the resync does NOT save them: once a join's state has expired, a
    full re-snapshot flowing through it produces nothing, because the dedup
    rank in front folds identical re-publications into no-ops that never
    refresh downstream state (measured: ~560 resynced records entered the
    expired joins of every SPARQL rule, zero came out). The pinned state is
    bounded -- the views are deduplicated changelogs, one live row per key.

    The aliases are read back out of the FROM clause rather than threaded
    through the translator, so a hint is emitted for exactly the tables
    visible in THIS query block. Hints are query-block scoped: naming an alias
    from an inner sub-select here would be silently ignored, which would look
    fixed without being fixed.
    """
    aliases = re.findall(
        r'\b(?:rdf|entities_view|attributes_view)\s+AS\s+(\w+)',
        target_sql, re.IGNORECASE)
    if not aliases:
        return ''
    return utils.get_state_ttl_metadata(sorted(set(aliases))) + ' '


def wrap_sql_projection(ctx, node):
    bounds = ctx['bounds']
    expression = 'SELECT '
    if 'Distinct' in ctx['target_modifiers']:
        expression += 'DISTINCT '
    if len(ctx['PV']) == 0:
        raise utils.SparqlValidationFailed("No Projection variables given.")

    first = True
    for var in ctx['PV']:
        if first:
            first = False
        else:
            expression += ', '
        try:
            column = bounds[utils.create_varname(var)]
            expression += f'{column} AS `{utils.create_varname(var)}` '
        except Exception:
            # variable could not be bound, bind it with NULL
            expression += f'CAST(NULL AS STRING) AS `{utils.create_varname(var)}` '

    target_sql = node['target_sql']
    target_where = node['where']
    group_by = create_group_by(ctx)

    if group_by is not None:
        group_by_term = f' GROUP BY {group_by}'
    else:
        group_by_term = ''
    # The hint goes immediately after SELECT and BEFORE any DISTINCT: Flink
    # parses anything following DISTINCT as a select item, so a hint placed
    # there is a syntax error and the whole statement set fails to deploy.
    expression = re.sub(r'^SELECT ',
                        lambda m: m.group(0) + rdf_state_ttl_hint(target_sql),
                        expression, count=1)
    node['target_sql'] = f'{expression} FROM {target_sql}'
    node['target_sql'] = node['target_sql'] + f' WHERE {target_where}' if \
        target_where != '' else node['target_sql']
    node['target_sql'] = node['target_sql'] + f' {group_by_term}' if \
        group_by_term != '' else node['target_sql']


def translate_filter(ctx, filter):
    """
    Translates Filter object to SQL
    """
    translate(ctx, filter.p)
    where1 = translate(ctx, filter.expr)
    where2 = filter.p['where']
    filter['target_sql'] = filter.p['target_sql']
    # merge join condition
    if where1 == '':
        raise utils.SparqlValidationFailed('Error: Filter does not provide condition.')
    if where2 != '':
        where1 += f' and {where2}'
    filter['where'] = where1


def translate_notexists(ctx, notexists, kind='NOT EXISTS'):
    """
    Translates a FILTER NOT EXISTS or FILTER EXISTS expression
    """
    ctx_copy = copy_context(ctx)
    # The tables it reads are its own: under an outer alias it would see the
    # outer row instead of looking for another one.
    ctx_copy['subquery'] = bgp_translation_utils.get_unique_suffix(6)
    translate(ctx_copy, notexists.graph)
    notexists['target_sql'] = notexists.graph['target_sql']
    notexists['where'] = notexists.graph['where']
    # _vars is a set, and wrap_sql_projection emits the projection in
    # iteration order, so an unsorted one reorders the SELECT columns of a
    # NOT EXISTS subquery from build to build.
    ctx_copy['PV'] = sorted(notexists['_vars'], key=str)
    remap_join_constraint_to_where(notexists)
    wrap_sql_projection(ctx_copy, notexists)
    return f'{kind} ({notexists["target_sql"]})'


def remap_join_constraint_to_where(node):
    """
    Workaround for Flink - currently correlated variables in "on" condition are
    not working in not-exists subqueries
    Therefore they are remapped to "where" conditions. This will make the
    query more inefficient but hopefully it
    can be reomved once FLINK fixed the issue. This method only works so far
    for rdf tables.
    """
    pattern1 = r'(\S*.subject = \S*) and'
    pattern2 = r'and (\S*.object = \S*)'
    toreplace = node['target_sql']
    match1 = re.findall(pattern1, toreplace)
    match2 = re.findall(pattern2, toreplace)
    toreplace = re.sub(pattern1, '', toreplace)
    toreplace = re.sub(pattern2, '', toreplace)
    node['target_sql'] = toreplace
    first = False
    if node['where'] == '':
        first = True
    for match in match1:
        if first:
            node['where'] = node['where'] + f'{match}'
            first = False
        else:
            node['where'] = node['where'] + f' and {match}'
    for match in match2:
        node['where'] = node['where'] + f' and {match}'


def copy_context(ctx):
    # avoid deep copy of graph. it is not needed and creates problems with oxigraph
    graph = ctx['g']
    del ctx['g']
    ctx_copy = copy.deepcopy(ctx)
    # copy graph manually into the new structure
    ctx['g'] = ctx_copy['g'] = graph
    ctx_copy['target_sql'] = ''
    ctx_copy['target_modifiers'] = []
    ctx_copy['sql_tables'] = ctx['sql_tables']
    return ctx_copy


def grouped(expression, condition):
    """A join as the right side of another one: in parentheses, where nothing
    of the left side can be seen. What an inner condition says about the left
    side's entity it says about the first table's, which is the same one
    (`condition`, the outer ON)."""
    if ' JOIN ' not in expression:
        return expression
    own = set(re.findall(r'\b(?:rdf|\w+_view|REPLACE_ATTRIBUTES\w+) AS (\w+)', expression))
    for entity, attribute in re.findall(r'(\w+)\.`?id`? = (\w+)\.entityId', condition) + \
            [(e, a) for a, e in re.findall(r'(\w+)\.entityId = (\w+)\.`?id`?', condition)]:
        if attribute in own and entity not in own:
            expression = re.sub(rf'`?\b{entity}\b`?\.`?id\b`?', f'{attribute}.entityId', expression)
    without_text = re.sub(r"'[^']*'", '', expression)
    if set(re.findall(r'`?\b([A-Za-z_]\w*)\b`?\.`?(?:\w+)', without_text)) - own:
        raise utils.WrongSparqlStructure('An OPTIONAL or a group whose patterns are connected with each other only \
through something outside of it, or that names an entity by its IRI, is not supported. Write an OPTIONAL for each, \
or connect them.')
    return f'({expression})'


def translate_join(ctx, join):
    translate(ctx, join.p1)
    translate(ctx, join.p2)
    expr1 = join.p1['target_sql']
    expr2 = join.p2['target_sql']
    where1 = join.p1['where']
    where2 = join.p2['where']
    where = ''

    if where2 == '':
        raise utils.WrongSparqlStructure('Could not join. Emtpy join condition not allowed \
for left joins.')
    if expr2 != '' and expr1 != '':
        join['target_sql'] = f' {expr1} JOIN {grouped(expr2, where2)}'
        where = where1
        join['target_sql'] = join['target_sql'] + f' ON {where2}'
    elif expr2 == '':
        # the right side adds conditions on what the left side reads -- not
        # on what an OPTIONAL there may not have found
        optional = [table for table in ctx.get('optional_tables', ()) if re.search(rf'\b{table}\b', where2)]
        if optional:
            raise utils.WrongSparqlStructure('An attribute read in an OPTIONAL is read again after it. Read it before \
the OPTIONAL, or only in it.')
        join['target_sql'] = expr1
    else:
        join['target_sql'] = expr2

    if where == '':
        if where1:
            where = f'({where1} and {where2})'
        else:
            where = where2
    join['where'] = where
    return


def translate_left_join(ctx, join):
    translate(ctx, join.p1)
    translate(ctx, join.p2)
    expr1 = join.p1['target_sql']
    expr2 = join.p2['target_sql']
    where1 = join.p1['where']
    where2 = join.p2['where']
    # The FILTER of an OPTIONAL decides whether there is something optional, so
    # it belongs to the join, not to what is joined.
    if getattr(join.get('expr'), 'name', 'TrueFilter') != 'TrueFilter':
        if expr2 == '':
            raise utils.WrongSparqlStructure('An OPTIONAL with a FILTER, around patterns on attributes that are read \
before it, is not supported. Put the condition where it is used, or read another attribute in the OPTIONAL.')
        condition = translate(ctx, join['expr'])
        where2 = f'{where2} and {condition}' if where2 else condition
    if expr1 == '' and expr2 == '':
        raise utils.WrongSparqlStructure('Could not left join. Empty join.p1 and join.p2 expression is not \
allowed. Consider rearranging BGPs.')
    if expr2 == '' and where2 == '':
        # Nothing to join. Can e.g. happen when time attributes are joined OPTIONAL and the attribute
        # value has been referenced earlier
        join['target_sql'] = expr1
        join['where'] = where1
        return

    if where2 == '' and expr1 != '' and expr2 != '':
        raise utils.WrongSparqlStructure('Could not left join. Emtpy join condition not allowed \
for left joins.')
    # There might be a case that there is no sql expression. Example:
    # The BGP {?var1 <p> ?var2} creates only a condition but not table
    # if ?var1 and ?vars are already bound.
    # case 1: with expr1,expr2 and where2
    # case 2: without expr2 but where2
    # case 3: with expr2 but without expr1
    if expr2 != '' and expr1 != '':  # case 1
        ctx['optional_tables'] = ctx.get('optional_tables', set()) | set(
            re.findall(r'\bAS (\w+)', expr2))
        join['target_sql'] = f' {expr1} LEFT JOIN {grouped(expr2, where2)}'
        join['where'] = where1
        join['target_sql'] = join['target_sql'] + f' ON {where2}'
    elif expr2 == '' and expr1 != '':  # case 2
        join['target_sql'] = expr1
        if where1:
            join['where'] = f'(({where1} and {where2}) or {where1})'
        else:
            join['where'] = where2
    else:
        join['target_sql'] = expr2
        if where1 == '':
            join['where'] = where2
        elif where2 == '':
            join['where'] = where1
        else:
            join['where'] = f'(({where1} and {where2}) or {where1})'
    return


def merge_bgp_context(bgp_context, select=False, subquery=False):
    """
    Iterate through bgp_context and create statement out of it
    Normally, it is created for a join but if select is True, it is creating
    a Select merge

    In a subquery every condition goes to the WHERE: Flink cannot plan an ON
    that names something of the outer query, and takes the same from a WHERE.
    """
    expression = ''
    where = ''
    first = True
    for expr in bgp_context:
        if first:
            first = False
            if not select:
                expression += f'{expr["statement"]} ON {expr["join_condition"]}'
            else:
                where = expr["join_condition"]
                expression = f'{expr["statement"]}'
        elif subquery:
            expression += f' JOIN {expr["statement"]} ON 1 = 1'
            where += f' and {expr["join_condition"]}'
        else:
            expression += f' JOIN {expr["statement"]} ON {expr["join_condition"]}'
    return expression, where


def translate_and_expression(ctx, expr):
    """
    Translates AND expression to SQL
    """
    result = '(' + translate(ctx, expr.expr)
    for otherexpr in expr.other:
        result += ' and '
        result += translate(ctx, otherexpr)
    return result + ')'


def translate_or_expression(ctx, expr):
    """
    Translates OR expression to SQL
    """
    result = '(' + translate(ctx, expr.expr)
    for otherexpr in expr.other:
        result += ' or '
        result += translate(ctx, otherexpr)
    return result + ')'


NUMERIC = (XSD.integer, XSD.decimal, XSD.double, XSD.float, XSD.int, XSD.long, XSD.short, XSD.byte,
           XSD.nonNegativeInteger, XSD.positiveInteger, XSD.nonPositiveInteger, XSD.negativeInteger,
           XSD.unsignedInt, XSD.unsignedLong, XSD.unsignedShort)


def is_literal_variable(ctx, elem):
    """A variable whose text may be a number: an attribute's value that is no
    IRI, or something read from the knowledge. A time is compared as a time,
    what BIND gives has its form already, and a text CONCAT or STR gives is
    no number."""
    if not isinstance(elem, Variable) or elem in ctx['time_variables'] or elem in ctx['entity_variables']:
        return False
    if elem in ctx['property_variables']:
        return ctx['property_variables'][elem] is not True
    if elem in ctx.get('computed', ()):
        return elem not in ctx.get('texts', ())
    bound = ctx['bounds'].get(utils.create_varname(elem), '')
    return re.search(r"\.`?(object|subject)`?$", bound) is not None


def as_number(ctx, elem):
    """The number a side of a comparison is, as SQL, or None when it is none
    for sure: what is no number at run time is NULL."""
    if isinstance(elem, Literal):
        return str(elem.toPython()) if elem.datatype in NUMERIC else None
    if is_literal_variable(ctx, elem):
        utils.add_aggregate_var_to_context(ctx, utils.create_varname(elem))
        column = ctx['bounds'].get(utils.create_varname(elem))
        if column is None:
            return None
        if elem in ctx.get('computed', ()):
            column = f'SQL_DIALECT_STRIP_LITERAL{{{column}}}'
        return f'SQL_DIALECT_NUMBER{{{column}}}'
    return None


def is_number(elem):
    """Whether an expression is a number whatever it is applied to."""
    if isinstance(elem, Literal):
        return elem.datatype in NUMERIC
    name = getattr(elem, 'name', '')
    if name == 'Function':
        return elem.iri in (XSD['integer'], XSD['float'], XSD['double'], XSD['decimal'])
    return name in ('AdditiveExpression', 'MultiplicativeExpression')


def comparable(ctx, elem):
    """A side of a comparison, as the text of its RDF term."""
    if isinstance(elem, Variable):
        if elem in ctx['entity_variables'] and elem not in ctx['property_variables'] and \
                utils.create_varname(elem) in ctx['bounds']:
            return f"'<' || {ctx['bounds'][utils.create_varname(elem)]} || '>'"
        return utils.wrap_ngsild_variable(ctx, elem)
    if isinstance(elem, (Literal, URIRef)):
        return utils.format_node_type(elem)
    # Neither Variable, nor Literal, nor IRI - hope it is further translatable
    return translate(ctx, elem)


def equals(ctx, left, right, op='='):
    """SPARQL's = and != : of numbers by their value, else of the terms. A
    text is no number, so a value that reads like one is not equal to it."""
    for one, other in ((left, right), (right, left)):
        if is_text(one, ctx) and isinstance(other, Variable) and other in ctx['property_variables'] and \
                other not in ctx.get('computed', ()) and ctx['property_variables'][other] is not True:
            column = ctx['bounds'].get(utils.create_varname(other))
            if column is not None:
                return f"(CASE WHEN SQL_DIALECT_NUMBER{{{column}}} IS NULL " \
                       f"THEN {comparable(ctx, left)} {op} {comparable(ctx, right)} ELSE {op == '<>'} END)"
        if is_number(one) and is_literal_variable(ctx, other):
            number = as_number(ctx, one) or comparable(ctx, one)
            return f'{as_number(ctx, other)} {op} {number}'
    return f'{comparable(ctx, left)} {op} {comparable(ctx, right)}'


def translate_relational_expression(ctx, elem):
    """
    Translates RelationalExpression to SQL

    The tables hold every value as text. Two numbers are compared as numbers,
    though, as SPARQL does: as texts, "9" is more than "10".
    """
    op = '<>' if elem.op == '!=' else elem.op
    if op in ('IN', 'NOT IN'):
        joint, one = (' or ', '=') if op == 'IN' else (' and ', '<>')
        return '(' + joint.join(equals(ctx, elem.expr, other, one) for other in elem.other) + ')'
    if op in ('=', '<>'):
        return equals(ctx, elem.expr, elem.other, op)
    for one, other in ((elem.expr, elem.other), (elem.other, elem.expr)):
        if is_text(one, ctx):
            # Texts are ordered by their characters. A text and a number are
            # not ordered, as in SPARQL: no value, also under a negation.
            if is_no_text(ctx, other):
                return 'CAST(NULL AS BOOLEAN)'
            sides = {id(one): lexical(ctx, one), id(other): text_at_run_time(ctx, other, numbers=False)}
            return f'({sides[id(elem.expr)]} {op} {sides[id(elem.other)]})'

    left, right = as_number(ctx, elem.expr), as_number(ctx, elem.other)
    if left is not None and right is not None:
        if is_number(elem.expr) or is_number(elem.other):
            return f'{left} {op} {right}'
        # Both only known at run time: numbers as numbers, texts as texts, and
        # a number with a text not at all.
        return f'(CASE WHEN {left} IS NOT NULL AND {right} IS NOT NULL THEN {left} {op} {right} ' \
               f'WHEN {left} IS NULL AND {right} IS NULL ' \
               f'THEN {comparable(ctx, elem.expr)} {op} {comparable(ctx, elem.other)} END)'
    if left is not None and not isinstance(elem.expr, Literal) and is_number(elem.other):
        return f'{left} {op} {comparable(ctx, elem.other)}'
    if right is not None and not isinstance(elem.other, Literal) and is_number(elem.expr):
        return f'{comparable(ctx, elem.expr)} {op} {right}'
    return f'{comparable(ctx, elem.expr)} {op} {comparable(ctx, elem.other)}'


def translate_BGP(ctx, bgp):
    """Translates a Basic Graph Pattern into SQL term

    Assumption is that the model data is provided in NGSI-LD tables and Knowlege data as triples in
    a RDF table

    Args:
        ctx (dictionary): Contains the results and metadata, e.g. variable mapping, resulting sql expression
        bgp (dictionary): BGP structure provided by RDFLib SPARQL parser

    Raises:
        bgp_translation_utils.WrongSparqlStructure: Problems with SPARQL metadata, or features which are not implemented
        bgp_translation_utils.SparqlValidationFailed: Problems with SPARQL parsing, dependencies
    """
    # Add triples one time
    add_triples = ctx['add_triples']
    for triple in add_triples:
        bgp.triples.append(triple)
    ctx['add_triples'] = []

    # Translate set of triples into Graph for later processing
    if len(bgp.triples) == 0:
        bgp['where'] = ''
        bgp['target_sql'] = ''
        return
    h = Graph()
    filtered_triples = []
    triples = []
    for s, p, o in bgp.triples:
        triples.append((s, p, o))
    triples, constants, targets, entities = bgp_translation_utils.normalise_attributes(triples)
    bgp_translation_utils.register_attributes(ctx, triples)
    ctx['targets'] = {**ctx.get('targets', {}), **{variable: constants.pop(variable) for variable in targets}}
    named = []
    for variable in sorted(entities, key=str):
        # an entity named by its IRI is read from the entities by its id
        table = f'{utils.create_varname(variable).upper()}TABLE'
        named.append({'statement': f'{configs.kafka_topic_ngsi_prefix_name}_view AS {table}',
                      'join_condition': f"{table}.id = '{constants.pop(variable)}' and \
IFNULL({table}.`deleted`, FALSE) IS FALSE"})
        ctx['bounds'][utils.create_varname(variable)] = f'{table}.`id`'
        ctx['sql_tables'].append(configs.kafka_topic_ngsi_prefix_name)
    for s, p, o in triples:
        h.add((s, p, o))
        filtered_triples.append((s, p, o))

    property_variables, entity_variables, time_variables = bgp_translation_utils.create_ngsild_mappings(ctx, h)

    # before translating, sort the bgp order to allow easier binds
    bgp.triples = bgp_translation_utils.sort_triples(ctx, ctx['bounds'], filtered_triples, h)

    bgp_translation_utils.merge_vartypes(ctx, property_variables, entity_variables, time_variables)
    local_ctx = {}
    local_ctx['bounds'] = ctx["bounds"]
    local_ctx['where'] = ''
    local_ctx['bgp_sql_expression'] = named
    local_ctx['bgp_tables'] = {}
    for statement in named:
        local_ctx['bgp_tables'][statement['statement'].rsplit(' ', 1)[-1]] = []
    local_ctx['h'] = h

    for s, p, o in bgp.triples:
        try:
            # If there are properties or relationships, assume it is a NGSI-LD matter
            if (p.toPython() in ctx['properties'] or p.toPython() in ctx['relationships']) and isinstance(o, BNode):
                if isinstance(s, Variable):
                    bgp_translation_utils.process_ngsild_spo(ctx, local_ctx, s, p, o)
            elif p != bgp_translation_utils.ngsild['hasValue'] and p != \
                    bgp_translation_utils.ngsild['hasObject'] and p != \
                    bgp_translation_utils.ngsild['observedAt']:
                # must be  RDF query
                bgp_translation_utils.process_rdf_spo(ctx, local_ctx, s, p, o)

            else:
                if debug > 1:
                    print(f'DEBUG: Ignoring: {s, p, o}', file=debugoutput)
        except (utils.SparqlValidationFailed, utils.WrongSparqlStructure) as e:
            e.pattern = bgp_translation_utils.describe_triple(ctx, h, (s, p, o))
            raise
    for variable, constant in constants.items():
        local_ctx['where'] = bgp_translation_utils.merge_where_expression(
            local_ctx['where'], equals(ctx, variable, constant))

    bgp_join_conditions = []
    if len(local_ctx['bgp_sql_expression']) != 0:
        bgp_join_conditions = []
        if local_ctx['where'] != '':
            bgp_join_conditions.append(local_ctx['where'])
    if local_ctx['bgp_sql_expression']:
        bgp['target_sql'], bgp['where'] = merge_bgp_context(local_ctx['bgp_sql_expression'], True,
                                                            'subquery' in ctx)
        for condition in bgp_join_conditions:
            # A condition between things bound already: lost here, it would
            # let everything through.
            bgp['where'] = bgp_translation_utils.merge_where_expression(bgp['where'], condition)
    else:
        bgp['target_sql'] = ''
        bgp['where'] = local_ctx['where']

    ctx['tables'] = {**(ctx['tables']), **local_ctx['bgp_tables']}


def create_subbounds(ctx, node):
    group_by_vars = utils.get_group_by_vars(ctx)
    aggregate_vars = utils.get_aggregate_vars(ctx)
    subquery_vars = ''
    aliasmap = {}
    bounds = ctx['bounds']
    first = True
    for var in group_by_vars + aggregate_vars:
        if first:
            first = False
        else:
            subquery_vars += ', '
        alias = "X" + bgp_translation_utils.get_unique_suffix(16)
        column_name = bounds[var]
        aliasmap[column_name] = alias
        subquery_vars += f'{column_name} as {alias}'
        bounds[var] = alias
    node['column_alias'] = aliasmap
    return subquery_vars


def replace_column_by_alias(node, value):
    aliasmap = node['column_alias']
    for k, v in aliasmap.items():
        value = value.replace(k, v)
    return value


def create_order_by(ctx):
    aggregate_vars = utils.get_aggregate_vars(ctx)
    timevars = utils.get_timevars(ctx, aggregate_vars)
    result = ', '.join(timevars)
    return result


def create_group_by(ctx):
    bounds = ctx['bounds']
    group_by_vars = utils.get_group_by_vars(ctx)
    result = None
    if group_by_vars is not None:
        result = reduce(lambda x, y: f'{x}, {y}', map(lambda x: bounds[x],
                        group_by_vars))
    return result
