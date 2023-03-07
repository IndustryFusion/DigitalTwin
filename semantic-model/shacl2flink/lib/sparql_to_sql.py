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
from rdflib.namespace import RDF, XSD
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.algebra import translateQuery
import copy

file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import utils  # noqa: E402
import bgp_translation_utils  # noqa: E402


sh = Namespace("http://www.w3.org/ns/shacl#")

iff = Namespace("https://industry-fusion.com/types/v0.9/")
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

    parsed_query = translateQuery(parseQuery(sparql_query))
    ctx = translate_query(parsed_query, target_class)
    return ctx['target_sql'], ctx['sql_tables']


def translate_query(query, target_class):
    """
    Decomposes parsed SparQL object
    query: parsed sparql object
    """
    algebra = query.algebra
    ctx = {
        'namespace_manager': query.prologue.namespace_manager,
        'relationships': relationships,
        'properties': properties,
        'g': g,
        'PV': algebra.PV,
        'classes': {'this': target_class},
        'sql_tables': ['attributes'],
        'bounds': {},
        'target_sql': '',
        'target_where': '',
        'target_modifiers': [],
        'add_triples': [(Variable('this'), RDF['type'], target_class)]
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
    else:
        raise utils.WrongSparqlStructure(f'SparQL structure {elem.name} not \
supported!')


def translate_function(ctx, function):
    bounds = ctx['bounds']
    iri = function.iri
    expr = function.expr
    result = ''
    if iri in XSD:  # CAST
        if len(expr) != 1:
            raise utils.WrongSparqlStructure('XSD function with too many parameters')
        cast = 'notfound'
        var = bounds[utils.create_varname(expr[0])]
        if iri == iri == XSD['integer']:
            cast = 'INTEGER'
        elif iri == iri == XSD['float']:
            cast = 'FLOAT'
        result = f'CAST({var} as {cast})'
    return result


def translate_builtin_now(ctx, builtin_now):
    return 'SQL_DIALECT_CURRENT_TIMESTAMP'


def translate_builtin_if(ctx, builtin_if):
    condition = translate(ctx, builtin_if.arg1)
    if isinstance(builtin_if.arg2, URIRef) or isinstance(builtin_if.arg2, Literal):
        ifyes = utils.format_node_type(builtin_if.arg2)
    else:
        ifyes = translate(ctx, builtin_if.arg2)
    if isinstance(builtin_if.arg3, URIRef) or isinstance(builtin_if.arg3, Literal):
        ifnot = utils.format_node_type(builtin_if.arg3)
    else:
        ifnot = translate(ctx, builtin_if.arg3)
    expression = f'CASE WHEN {condition} THEN {ifyes} ELSE {ifnot} END'
    return expression


def translate_extend(ctx, extend):
    translate(ctx, extend.p)
    if isinstance(extend.expr, Literal) or isinstance(extend.expr, URIRef):
        expression = utils.format_node_type(extend.expr)
    else:
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
    property_variables, entity_variables, _ = bgp_translation_utils.create_ngsild_mappings(ctx, h)
    translate(ctx, query.p)
    query['target_sql'] = query.p['target_sql']
    query['where'] = query.p['where']
    bgp_translation_utils.merge_vartypes(ctx, property_variables, entity_variables)
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
    (entityId_var, name, attribute_type, value_var, node_type) = get_attribute_column(ctx, node)
    entityId_varname = entityId_var.toPython()[1:]

    bounds = ctx['bounds']
    construct_query = "SQL_DIALECT_INSERT_ATTRIBUTES\n"
    construct_query += "SELECT "
    construct_query += f'{bounds[entityId_varname]} || \'\\\' || \'{name}\',\n'  # id
    construct_query += f'{bounds[entityId_varname]},\n'  # entityId
    construct_query += f'\'{name}\',\n'  # name
    construct_query += f'\'{node_type}\',\n'  # nodeType
    construct_query += 'CAST(NULL as STRING),\n'  # valueType
    construct_query += '0,\n'  # index
    construct_query += f'\'{attribute_type}\',\n'
    construct_query += f"{get_bound_trim_string(ctx, value_var)},\n"  # value
    construct_query += 'CAST(NULL as STRING)\n'  # object
    construct_query += ',SQL_DIALECT_SQLITE_TIMESTAMP\n'  # ts
    construct_query += 'FROM ' + node['target_sql']
    construct_query += ' WHERE ' + node['where']
    node['target_sql'] = construct_query


def get_bound_trim_string(ctx, boundsvar):
    bounds = ctx['bounds']
    boundsvarname = boundsvar.toPython()[1:]
    if boundsvarname in bounds and boundsvar in ctx['property_variables']:
        if ctx['property_variables'][boundsvar]:
            return f"SQL_DIALECT_STRIP_IRI({bounds[boundsvarname]})"
        else:
            return f"SQL_DIALECT_STRIP_LITERAL({bounds[boundsvarname]})"
    else:
        raise utils.WrongSparqlStructure('Trying to trim non-bound variable')


def get_attribute_column(ctx, node):
    entityId_var = None
    name = None

    value_var = None
    nodetype = '@value'
    bnode = None
    for (s, p, o) in node['template']:
        if p.toPython() in properties:
            if entityId_var is not None:
                raise utils.WrongSparqlStructure('Construction of more than one attributes \
not yet implemented!')
            entityId_var = s
            name = p
            bnode = o
        if p.toPython() in relationships:
            raise utils.WrongSparqlStructure('Construction of relationship not yet implemented')
    for (s, p, o) in node['template']:
        if s == bnode:
            value_var = o
    if entityId_var is None or name is None or value_var is None:
        raise utils.WrongSparqlStructure('No attribute constructed in construct query!')
    attribute_type = bgp_translation_utils.ngsild['Property'] if value_var in ctx['property_variables'] else \
        bgp_translation_utils.ngsild['Relationship']
    if value_var in ctx['property_variables'] and ctx['property_variables'][value_var]:
        nodetype = '@id'
    return (entityId_var, name.toPython(), attribute_type.toPython(), value_var, nodetype)


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
            # column_no_bacticks =  column.replace('`', '')
            expression += f'{column} AS `{utils.create_varname(var)}` '
        except:
            # variable could not be bound, bind it with NULL
            expression += f'NULL AS `{utils.create_varname(var)}`'

    target_sql = node['target_sql']
    target_where = node['where']
    node['target_sql'] = f'{expression} FROM {target_sql}'
    node['target_sql'] = node['target_sql'] + f' WHERE {target_where}' if \
        target_where != '' else node['target_sql']


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
    if expr1 == '':
        raise utils.WrongSparqlStructure('Could not left join. Empty join.p1 expression is not \
allowed. Consider rearranging BGPs.')
    if where2 == '':
        raise utils.WrongSparqlStructure('Could not left join. Emtpy join condition not allowed \
for left joins.')
    # There might be a case that there is no sql expression. Example:
    # The BGP {?var1 <p> ?var2} creates only a condition but not table
    # if ?var1 and ?vars are already bound.
    # case 1: with expr2 and where2
    # case 2: without expression but where2
    if expr2 != '':  # case 1
        join['target_sql'] = f' {expr1} LEFT JOIN {expr2}'
        join['where'] = where1
        join['target_sql'] = join['target_sql'] + f' ON {where2}'
    else:  # case 2
        join['target_sql'] = expr1
        if where1:
            join['where'] = f'(({where1} and {where2}) or {where1})'
        else:
            join['where'] = where2
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
    result = translate(ctx, expr.expr)
    for otherexpr in expr.other:
        result += ' and '
        result += translate(ctx, otherexpr)
    return result


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
        raise utils.WrongSparqlStructure(f'Expression {elem.other} not supported!')

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
    for s, p, o in bgp.triples:
        h.add((s, p, o))

    property_variables, entity_variables, row = bgp_translation_utils.create_ngsild_mappings(ctx, h)

    # before translating, sort the bgp order to allow easier binds
    bgp.triples = bgp_translation_utils.sort_triples(ctx, ctx['bounds'], bgp.triples, h)

    bgp_translation_utils.merge_vartypes(ctx, property_variables, entity_variables)
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
        elif p != bgp_translation_utils.ngsild['hasValue'] and p != bgp_translation_utils.ngsild['hasObject']:
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
