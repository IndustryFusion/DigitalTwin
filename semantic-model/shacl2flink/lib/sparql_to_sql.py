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
import os
import re
from rdflib import Graph, Namespace, URIRef, Variable, BNode, Literal
from rdflib.namespace import RDF, XSD, RDFS
from rdflib.paths import MulPath
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.algebra import translateQuery
from functools import reduce
import copy


file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import utils  # noqa: E402
import bgp_translation_utils  # noqa: E402


sh = Namespace("http://www.w3.org/ns/shacl#")

iff = Namespace("https://industry-fusion.com/types/v0.9/")
IFA = Namespace("https://industry-fusion.com/aggregators/v0.9/")
IFN = Namespace("https://industry-fusion.com/functions/v0.9/")

debug = 0
debugoutput = sys.stdout
dummyvar = 'dummyvar'


sparql_get_properties = """
PREFIX iff: <https://industry-fusion.com/types/v0.9/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
PREFIX sh: <http://www.w3.org/ns/shacl#>
SELECT
    ?targetclass ?property ((?nodekind = sh:IRI) as ?kind)
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?nodeshape sh:property [
        sh:path ?property ;
        sh:property [
            sh:nodeKind ?nodekind ;
            sh:path ngsild:hasValue ;
        ] ;
    ] .
    OPTIONAL{
    ?nodeshape sh:property [
        sh:property [
            sh:nodeKind ?nodekind ;
            sh:path ngsild:hasValue ;
        ] ;
    ] ;
        }
}

"""

sparql_get_relationships = """
PREFIX iff: <https://industry-fusion.com/types/v0.9/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
PREFIX sh: <http://www.w3.org/ns/shacl#>
SELECT
    ?targetclass ?relationship
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?nodeshape sh:property [
        sh:path ?relationship ;
        sh:property [
            sh:path ngsild:hasObject ;
        ] ;

    ] .
}

"""


properties = {}
relationships = {}
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
    global properties
    global relationships
    g = lg
    qres = g.query(sparql_get_properties)
    for row in qres:
        if row.property is not None:
            properties[row.property.toPython()] = row.kind.toPython() if row.kind is not None else False

    qres = g.query(sparql_get_relationships)
    for row in qres:
        if row.relationship is not None:
            relationships[row.relationship.toPython()] = True
    parsed_query = None
    try:
        parsed_query = translateQuery(parseQuery(sparql_query))
    except:
        raise utils.SparqlValidationFailed('Failed to parse: ' + sparql_query)
    ctx = translate_query(parsed_query, target_class, sparql_query)
    return ctx['target_sql'], ctx['sql_tables']


def translate_query(query, target_class, orig_query):
    """
    Decomposes parsed SparQL object
    query: parsed sparql object
    """
    algebra = query.algebra
    randomstr = 'this' + bgp_translation_utils.get_random_string(16)
    ctx = {
        'namespace_manager': query.prologue.namespace_manager,
        'relationships': relationships,
        'properties': properties,
        'g': g,
        'PV': algebra.PV,
        'classes': {'this': target_class},
        'sql_tables': ['attributes'],
        'bounds': {},
        'tables': {},
        'target_sql': '',
        'target_where': '',
        'target_modifiers': [],
        'add_triples': [(Variable('this'), RDF['type'], Variable(randomstr)),
                        (Variable(randomstr),
                         RDFS['subClassOf'],
                         target_class)],
        'query': orig_query
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
            return utils.unwrap_variables(ctx, elem)
        except Exception as e:
            raise utils.SparqlValidationFailed(f"Error while unwrapping variables: {str(e)} \
while processing {ctx['query']}")
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
    elif elem.name == 'Distinct':
        ctx['target_modifiers'].append('Distinct')
        translate(ctx, elem.p)
    elif elem.name == 'LeftJoin':
        return translate_left_join(ctx, elem)
    elif elem.name == 'Extend':
        return translate_extend(ctx, elem)
    elif elem.name == 'Builtin_IF':
        return translate_builtin_if(ctx, elem)
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
        raise utils.WrongSparqlStructure(f'SparQL structure {elem.name} not \
supported!')


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
    except:
        raise utils.SparqlValidationFailed('Group by aggregation defined but no aggregated variables found.')
    elem['where'] = elem.p['where']


def translate_builtin_bound(ctx, elem):
    bounds = ctx['bounds']
    varname = utils.create_varname(elem.arg)
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
            elif iri == XSD['string']:
                cast = 'STRING'
                stringcast = True
            if cast == 'notfound':
                raise utils.WrongSparqlStructure('XSD type cast not supported')
            if not stringcast:
                result = f'SQL_DIALECT_CAST(SQL_DIALECT_STRIP_LITERAL{{{expression}}} as {cast})'
            else:
                result = f'SQL_DIALECT_CAST(SQL_DIALECT_STRIP_IRI{{{expression}}} as {cast})'
        else:
            result = f'SQL_DIALECT_TIME_TO_MILLISECONDS{{{expression}}}'
    elif iri in IFA:
        udf = utils.strip_class(iri)
        result = f'{udf}('
        utils.set_is_aggregate_var(ctx, True)
        for i in range(0, numargs):
            if i != 0:
                result += ', '
            expression = translate(ctx, expr[i])
            result += expression
        utils.set_is_aggregate_var(ctx, False)
        result += ')'
    elif iri in IFN:
        udf = utils.strip_class(iri)
        result = f'{udf}('
        for i in range(0, numargs):
            if i != 0:
                result += ', '
            expression = translate(ctx, expr[i])
            result += expression
        utils.set_is_aggregate_var(ctx, False)
        result += ')'
    else:
        raise utils.WrongSparqlStructure(f'Function {iri.toPython()} not supported!')
    return result


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
    property_variables, entity_variables, time_variables, _ = bgp_translation_utils.create_ngsild_mappings(ctx, h)

    translate(ctx, query.p)
    query['target_sql'] = query.p['target_sql']
    query['where'] = query.p['where']
    bgp_translation_utils.merge_vartypes(ctx, property_variables, entity_variables, time_variables)
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

    for (entityId_var, name, attribute_type, value_var, node_type) in columns:
        if first:
            first = False
        else:
            construct_query += "\nUNION ALL\n"
        entityId_varname = entityId_var.toPython()[1:]
        construct_query += "SELECT DISTINCT "
        construct_query += f'{bounds[entityId_varname]} || \'\\\' || \'{name}\' as id,\n'  # id
        construct_query += f'{bounds[entityId_varname]} as entityId,\n'  # entityId
        construct_query += f'\'{name}\' as name,\n'  # name
        construct_query += f'\'{node_type}\' as nodeType,\n'  # nodeType
        construct_query += 'CAST(NULL as STRING) as valueType,\n'  # valueType
        construct_query += '0 as `index`,\n'  # index
        construct_query += f'\'{attribute_type}\' as `type`,\n'
        construct_query += '\'@none\' as `datasetId`,\n'
        construct_query += f"{get_bound_trim_string(ctx, value_var)} as `value`,\n"  # value
        construct_query += 'CAST(NULL as STRING) as `object`\n'  # object
        construct_query += ',SQL_DIALECT_SQLITE_TIMESTAMP\n'  # ts

        construct_query += 'FROM ' + node['target_sql']
        if node['where'] != '':
            construct_query += ' WHERE ' + node['where']
        group_by = create_group_by(ctx)
        if group_by is not None:
            construct_query += f' GROUP BY {group_by}'
    node['target_sql'] = construct_query


def get_bound_trim_string(ctx, boundsvar):
    bounds = ctx['bounds']
    boundsvarname = boundsvar.toPython()[1:]
    if boundsvarname in bounds and boundsvar in ctx['property_variables']:
        if ctx['property_variables'][boundsvar]:
            return f"SQL_DIALECT_STRIP_IRI{{{bounds[boundsvarname]}}}"
        else:
            return f"SQL_DIALECT_STRIP_LITERAL{{{bounds[boundsvarname]}}}"
    elif boundsvarname in bounds and boundsvar in ctx['time_variables']:
        return f"SQL_DIALIFAECT_STRIP_LITERAL{{{bounds[boundsvarname]}}}"
    else:
        raise utils.WrongSparqlStructure(f"Trying to trim non-bound variable ?{boundsvarname} in expression \
{ctx['query']}")


def get_attribute_columns(ctx, node):
    entityId_var = None
    name = None
    properties = ctx['properties']
    value_var = None
    nodetype = '@value'
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
        if value_var in ctx['property_variables'] and ctx['property_variables'][value_var]:
            nodetype = '@id'
        result.append((entityId_var, name.toPython(), attribute_type.toPython(), value_var, nodetype))
    return result


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
        except:
            # variable could not be bound, bind it with NULL
            expression += f'NULL AS `{utils.create_varname(var)}`'

    target_sql = node['target_sql']
    target_where = node['where']
    group_by = create_group_by(ctx)

    if group_by is not None:
        group_by_term = f' GROUP BY {group_by}'
    else:
        group_by_term = ''
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


def translate_notexists(ctx, notexists):
    """
    Translates a FILTER NOT EXISTS expression
    """
    ctx_copy = copy_context(ctx)
    translate(ctx_copy, notexists.graph)
    notexists['target_sql'] = notexists.graph['target_sql']
    notexists['where'] = notexists.graph['where']
    ctx_copy['PV'] = notexists['_vars']
    remap_join_constraint_to_where(notexists)
    wrap_sql_projection(ctx_copy, notexists)
    return f'NOT EXISTS ({notexists["target_sql"]})'


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
    ctx_copy = copy.deepcopy(ctx)
    ctx_copy['target_sql'] = ''
    ctx_copy['target_modifiers'] = []
    ctx_copy['sql_tables'] = ctx['sql_tables']
    return ctx_copy


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
        join['target_sql'] = f' {expr1} JOIN {expr2}'
        where = where1
        join['target_sql'] = join['target_sql'] + f' ON {where2}'
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
        join['target_sql'] = f' {expr1} LEFT JOIN {expr2}'
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


def merge_bgp_context(bgp_context, select=False):
    """
    Iterate through bgp_context and create statement out of it
    Normally, it is created for a join but if select is True, it is creating
    a Select merge
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


def translate_relational_expression(ctx, elem):
    """
    Translates RelationalExpression to SQL
    """

    if isinstance(elem.expr, Variable):
        expr = utils.wrap_ngsild_variable(ctx, elem.expr)
    elif isinstance(elem.expr, Literal) or isinstance(elem.expr, URIRef):
        expr = utils.format_node_type(elem.expr)
    else:  # Neither Variable, nor Literal, nor IRI - hope it is further translatable
        expr = translate(ctx, elem.expr)

    if isinstance(elem.other, Variable):
        other = utils.wrap_ngsild_variable(ctx, elem.other)
    elif isinstance(elem.other, Literal) or isinstance(elem.other, URIRef):
        other = utils.format_node_type(elem.other)
    else:
        other = translate(ctx, elem.other)

    op = elem.op
    if elem.op == '!=':
        op = '<>'
    elif elem.op == '>':
        op = '>'
    elif elem.op == '<':
        op = '<'
    elif elem.op == '>=':
        op = '>='
    elif elem.op == '<=':
        op = '<='

    return f'{expr} {op} {other}'


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
    for s, p, o in bgp.triples:
        if isinstance(p, MulPath):
            p = p.path
        h.add((s, p, o))
        filtered_triples.append((s, p, o))

    property_variables, entity_variables, time_variables, row = bgp_translation_utils.create_ngsild_mappings(ctx, h)

    # before translating, sort the bgp order to allow easier binds
    bgp.triples = bgp_translation_utils.sort_triples(ctx, ctx['bounds'], filtered_triples, h)

    bgp_translation_utils.merge_vartypes(ctx, property_variables, entity_variables, time_variables)
    local_ctx = {}
    local_ctx['bounds'] = ctx["bounds"]
    local_ctx['where'] = ''
    local_ctx['bgp_sql_expression'] = []
    local_ctx['bgp_tables'] = {}
    local_ctx['h'] = h
    local_ctx['row'] = row

    for s, p, o in bgp.triples:
        # If there are properties or relationships, assume it is a NGSI-LD matter
        if (p.toPython() in properties or p.toPython() in relationships) and isinstance(o, BNode):
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

    bgp_join_conditions = []
    if len(local_ctx['bgp_sql_expression']) != 0:
        bgp_join_conditions = []
        if local_ctx['where'] != '':
            bgp_join_conditions.append(local_ctx['where'])
    if local_ctx['bgp_sql_expression']:
        bgp['target_sql'], bgp['where'] = merge_bgp_context(local_ctx['bgp_sql_expression'], True)
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
        alias = "X" + bgp_translation_utils.get_random_string(16)
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
