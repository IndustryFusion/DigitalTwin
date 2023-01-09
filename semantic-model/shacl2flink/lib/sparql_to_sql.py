# from msilib.schema import tables
import sys
import os
import re
import random
from rdflib import Graph, Namespace, URIRef, Variable, BNode, Literal
from rdflib.namespace import RDF, RDFS, XSD
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.algebra import translateQuery
import owlrl
import copy

file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import utils  # noqa: E402
import configs  # noqa: E402


class WrongSparqlStructure(Exception):
    pass


class SparqlValidationFailed(Exception):
    pass


sh = Namespace("http://www.w3.org/ns/shacl#")
ngsild = Namespace("https://uri.etsi.org/ngsi-ld/")
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
    ?targetclass ?property
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?nodeshape sh:property [
        sh:path ?property ;
        sh:property [
            sh:path ngsild:hasValue ;
        ] ;

    ] .
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

basequery = """
PREFIX iff: <https://industry-fusion.com/types/v0.9/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
PREFIX sh: <http://www.w3.org/ns/shacl#>
SELECT DISTINCT
"""

properties = {}
relationships = {}
g = Graph()


def translate_sparql(shaclfile, knowledgefile, sparql_query, target_class):
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
    g.parse(shaclfile)
    h = Graph()
    h.parse(knowledgefile)
    g += h
    owlrl.RDFSClosure.RDFS_Semantics(g, axioms=True, daxioms=False,
                                     rdfs=True).closure()
    qres = g.query(sparql_get_properties)
    for row in qres:
        if row.property is not None:
            properties[row.property.toPython()] = True

    qres = g.query(sparql_get_relationships)
    for row in qres:
        if row.relationship is not None:
            relationships[row.relationship.toPython()] = True

    parsed_query = translateQuery(parseQuery(sparql_query))
    ctx = translate_query(parsed_query, target_class)
    return ctx['target_sql'], ctx['sql_tables']


def create_tablename(subject, predicate='', namespace_manager=None):
    """
    Creates a sql tablename from an RDF Varialbe.
    e.g. ?var => VARTABLE
    variable: RDF.Variable or RDF.URIRef
    """
    pred = predicate
    subj = ''
    if pred != '' and namespace_manager is not None:
        pred = namespace_manager.compute_qname(predicate)[2]
        pred = pred.upper()
    if isinstance(subject, Variable):
        subj = subject.toPython().upper()[1:]
    elif isinstance(subject, URIRef) and namespace_manager is not None:
        subj = namespace_manager.compute_qname(subject)[2]
        subj = subj.upper()
    else:
        raise SparqlValidationFailed(f'Could not convert subject {subject} to \
table-name')

    return f'{subj}{pred}TABLE'


def create_varname(variable):
    """
    creates a plain varname from RDF varialbe
    e.g. ?var => var
    """
    return variable.toPython()[1:]


def get_rdf_join_condition(r, property_variables, entity_variables,
                           selectvars):
    """
    Create join condition for RDF-term
    e.g. ?table => table.id

    r: RDF term
    property_variables: List of variables containing property values
    entity_variables: List of variables containing entity references
    selectvars: mapping of resolved variables
    """
    if isinstance(r, Variable):
        var = create_varname(r)
        if r in property_variables:
            if var in selectvars:
                return selectvars[var]
            else:
                raise SparqlValidationFailed(f'Could not resolve variable \
?{var} at this point. You might want to rearrange the query to hint to \
translator.')
        elif r in entity_variables:
            raise SparqlValidationFailed(f'Cannot bind enttiy variable {r} to \
plain RDF context')
        elif var in selectvars:  # plain RDF variable
            return selectvars[var]
    elif isinstance(r, URIRef) or isinstance(r, Literal):
        return f'\'{r.toPython()}\''
    else:
        raise SparqlValidationFailed(f'RDF term {r} must either be a Variable, \
IRI or Literal.')


def create_bgp_context(bounds, join_conditions, sql_expression, tables):
    return {
        'bounds': bounds,
        'join_conditions': join_conditions,
        'sql_expression': sql_expression,
        'tables': tables
    }


def translate_query(query, target_class):
    """
    Decomposes parsed SparQL object
    query: parsed sparql object
    """
    algebra = query.algebra
    ctx = {
        'namespace_manager': query.prologue.namespace_manager,
        'PV': algebra.PV,
        'target_used': False,
        'table_id': 0,
        'classes': {'this': target_class},
        'sql_tables': ['attributes'],
        'bounds': {},
        'tables': {},
        'target_sql': '',
        'target_where': '',
        'target_modifiers': [],
        'add_triples': [(Variable('this'), RDF['type'], target_class)]
    }
    if debug:
        print("DEBUG: First Pass.", file=debugoutput)
    if algebra.name == 'SelectQuery':
        translate(ctx, algebra)
    else:
        raise WrongSparqlStructure('Only SelectQueries are supported \
currently!')
    ctx['target_sql'] = algebra['target_sql']
    if debug:
        print('DEBUG: Result: ', ctx['target_sql'], file=debugoutput)
    return ctx


def translate(ctx, elem):
    """
    Translate all objects
    """
    if elem.name == 'SelectQuery':
        return translate_select_query(ctx, elem)
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
    elif elem.name == 'Function':
        return translate_function(ctx, elem)
    else:
        raise WrongSparqlStructure(f'SparQL structure {elem.name} not \
supported!')


def translate_function(ctx, function):
    if debug > 2:
        print(f'function: {function}', file=debugoutput)
    bounds = ctx['bounds']
    iri = function.iri
    expr = function.expr
    result = ''
    if iri in XSD:  # CAST
        if len(expr) != 1:
            raise WrongSparqlStructure('XSD function with too many parameters')
        cast = 'notfound'
        var = bounds[create_varname(expr[0])]
        if iri == iri == XSD['integer']:
            cast = 'INTEGER'
        elif iri == iri == XSD['float']:
            cast = 'FLOAT'
        result = f'CAST({var} as {cast})'
    return result


def translate_builtin_if(ctx, builtin_if):
    if debug > 2:
        print(f'Builtin_IF: {builtin_if}', file=debugoutput)
    condition = translate(ctx, builtin_if.arg1)
    if isinstance(builtin_if.arg2, URIRef) or isinstance(builtin_if.arg2, Literal):
        ifyes = f'\'{builtin_if.arg2.toPython()}\''
    else:
        ifyes = translate(ctx, builtin_if.arg2)
    if isinstance(builtin_if.arg3, URIRef) or isinstance(builtin_if.arg3, Literal):
        ifnot = f'\'{builtin_if.arg3.toPython()}\''
    else:
        ifnot = translate(ctx, builtin_if.arg3)
    expression = f'CASE WHEN {condition} THEN {ifyes} ELSE {ifnot} END'
    return expression


def translate_extend(ctx, extend):
    if debug > 2:
        print(f'Extend: {extend}', file=debugoutput)
    translate(ctx, extend.p)
    expression = translate(ctx, extend.expr)
    ctx['bounds'][create_varname(extend.var)] = expression
    extend['target_sql'] = extend.p['target_sql']
    extend['where'] = extend.p['where']


def translate_select_query(ctx, query):
    """
    Decomposes SelectQuery object
    """
    if debug > 2:
        print(f'SelectQuery: {query}', file=debugoutput)
    translate(ctx, query.p)
    query['target_sql'] = query.p['target_sql']
    return


def translate_project(ctx, project):
    """
    Translate Project structure
    """
    if debug > 2:
        print(f'DEBUG: Project: {project}', file=debugoutput)
    translate(ctx, project.p)
    project['target_sql'] = project.p['target_sql']
    project['where'] = project.p['where']
    add_projection_vars_to_tables(ctx)
    wrap_sql_projection(ctx, project)


def add_projection_vars_to_tables(ctx):
    bounds = ctx['bounds']
    for var in ctx['PV']:
        try:
            column = bounds[create_varname(var)]
            column_no_bacticks = column.replace('`', '')
            table_name, column = re.findall(r'^([A-Z0-9_]+)\.(.*)$',
                                            column_no_bacticks)[0]
            if table_name not in ctx['tables']:
                ctx['tables'][table_name] = [f'{column}']
            else:
                ctx['tables'][table_name].append(f'{column}')
        except:
            pass  # variable cannot mapped to a table, ignore it


def wrap_sql_projection(ctx, node):
    bounds = ctx['bounds']
    expression = 'SELECT '
    if 'Distinct' in ctx['target_modifiers']:
        expression += 'DISTINCT '
    if len(ctx['PV']) == 0:
        raise SparqlValidationFailed("No Projection variables given.")

    first = True
    for var in ctx['PV']:
        if first:
            first = False
        else:
            expression += ', '
        try:
            column = bounds[create_varname(var)]
            # column_no_bacticks =  column.replace('`', '')
            expression += f'{column} AS `{create_varname(var)}` '
        except:
            # variable could not be bound, bind it with NULL
            expression += f'NULL AS `{create_varname(var)}`'

    target_sql = node['target_sql']
    target_where = node['where']
    node['target_sql'] = f'{expression} FROM {target_sql}'
    node['target_sql'] = node['target_sql'] + f' WHERE {target_where}' if \
        target_where != '' else node['target_sql']


def translate_filter(ctx, filter):
    """
    Translates Filter object to SQL
    """
    if debug > 2:
        print(f'DEBUG: Filter: {filter}', file=debugoutput)
    translate(ctx, filter.p)
    where1 = translate(ctx, filter.expr)
    where2 = filter.p['where']
    filter['target_sql'] = filter.p['target_sql']
    # merge join condition
    if where1 == '':
        raise SparqlValidationFailed('Error: Filter does not provide condition.')
    if where2 != '':
        where1 += f' and {where2}'
    filter['where'] = where1


def translate_notexists(ctx, notexists):
    """
    Translates a FILTER NOT EXISTS expression
    """
    if debug > 2:
        print(f'DEBUG: FILTER NOT EXISTS: {notexists}', file=debugoutput)
    ctx_copy = copy_context(ctx)
    translate(ctx_copy, notexists.graph)
    notexists['target_sql'] = notexists.graph['target_sql']
    notexists['where'] = notexists.graph['where']
    remap_join_constraint_to_where(notexists)
    wrap_sql_projection(ctx_copy, notexists)
    merge_contexts(ctx, ctx_copy)
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


def merge_contexts(ctx, ctx_copy):
    """
    merge global table from ctx_copy into ctx
    ONLY if table in ctx exists, merge it from ctx_copy
    """
    src_tables = ctx_copy['tables']
    target_tables = ctx['tables']

    for table in src_tables:
        if table in target_tables:
            target_table = target_tables[table]
            src_table = src_tables[table]
            for column in src_table:
                if column not in target_table:
                    target_table.append(column)


def copy_context(ctx):
    ctx_copy = copy.deepcopy(ctx)
    ctx_copy['target_sql'] = ''
    ctx_copy['target_modifiers'] = []
    ctx_copy['sql_tables'] = ctx['sql_tables']
    return ctx_copy


def translate_join(ctx, join):
    if debug > 2:
        print(f'DEBUG: JOIN: {join}', file=debugoutput)
    translate(ctx, join.p1)
    translate(ctx, join.p2)
    expr1 = join.p1['target_sql']
    expr2 = join.p2['target_sql']
    where1 = join.p1['where']
    where2 = join.p2['where']
    where = ''

    if where2 == '':
        raise WrongSparqlStructure('Could not join. Emtpy join condition not allowed for left joins.')
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
    if debug > 2:
        print(f'DEBUG: LEFT JOIN: {join}', file=debugoutput)
    translate(ctx, join.p1)
    translate(ctx, join.p2)
    expr1 = join.p1['target_sql']
    expr2 = join.p2['target_sql']
    where1 = join.p1['where']
    where2 = join.p2['where']
    if expr1 == '':
        raise WrongSparqlStructure('Could not left join. Empty join.p1 expression is not allowed. \
Consider rearranging BGPs.')
    if where2 == '':
        raise WrongSparqlStructure('Could not left join. Emtpy join condition not allowed for left joins.')
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


def merge_where_expression(where1, where2):
    if where1 == '' and where2 == '':
        return ''
    elif where1 == '':
        return where2
    elif where2 == '':
        return where1
    else:
        return f'{where1} and {where2}'


def translate_and_expression(ctx, expr):
    """
    Translates AND expression to SQL
    """
    if debug > 2:
        print(f'DEBUG: ConditionalAndExpression: {expr}', file=debugoutput)
    result = translate(ctx, expr.expr)
    for otherexpr in expr.other:
        result += ' and '
        result += translate(ctx, otherexpr)
    return result


def translate_relational_expression(ctx, elem):
    """
    Translates RelationalExpression to SQL
    """
    bounds = ctx['bounds']

    if isinstance(elem.expr, Variable):
        expr = bounds[create_varname(elem.expr)]
    elif isinstance(elem.expr, Literal) or isinstance(elem.expr, URIRef):
        expr = f'\'{elem.expr.toPython()}\''
    else:  # Neither Variable, nor Literal, nor IRI - hope it is further translatable
        expr = translate(ctx, elem.expr)

    if isinstance(elem.other, Variable):
        other = bounds[create_varname(elem.expr)]
    elif isinstance(elem.other, Literal) or isinstance(elem.other, URIRef):
        other = f'\'{elem.other.toPython()}\''
    else:
        raise WrongSparqlStructure(f'Expression {elem.other} not supported!')

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


def map_join_condition(sql_expressions, local_tables, global_tables):
    """
    Map all non-local conditions to global table list for later reference
    local_tables: map of tables and their referenced fields for local BGP
    gloabl_tables: map of tabels and their reference fields globally
    NOTE: Tables are upper case
    """
    for expression in sql_expressions:
        to_match = expression['join_condition']
        num_matches = to_match.count('=')
        pattern = r'[\s]*([^\s]+)[\s]*=[\s]*([^\s]+)[\s]*[and]*' * num_matches
        match = re.findall(pattern, to_match)
        for var in match[0]:
            try:
                table_name, column = re.findall(r'^([A-Z0-9_]+)\.(.*)$', var)[0]
                if table_name not in local_tables:
                    column_no_backticks = column.replace('`', '')
                    if table_name not in global_tables:
                        global_tables[table_name] = column_no_backticks
                    else:
                        global_tables[table_name].append(column_no_backticks)
            except:  # no column variable
                pass


def isentity(ctx, variable):
    if create_varname(variable) in ctx['bounds']:
        table = ctx['bounds'][create_varname(variable)]
    else:
        return False
    if re.search(r'\.id$', table):
        return True
    else:
        return False


def sort_triples(bounds, triples, graph):
    """Sort a BGP according to dependencies. Externally dependent triples come
    first

    Sort triples with respect to already bound variables
    try to move triples without any bound variable to the end

    Args:
    bounds (dictionary): already bound variables
    triples (dictionary): triples to be sorted
    graph (RDFlib Graph): graph containing the same triples as 'triples' but
    searchable with RDFlib
    """
    def select_candidates(bounds, triples, graph):
        for s, p, o in triples:
            count = 0
            # look for nodes: (1) NGSI-LD node and (2) plain RDF (3) RDF type definition (3) rest
            if isinstance(s, Variable) and (p.toPython() in relationships or
                                            p.toPython() in properties):
                if isinstance(o, BNode):
                    blanktriples = graph.triples((o, None, None))
                    for (bs, bp, bo) in blanktriples:
                        # (1)
                        if create_varname(s) in bounds:
                            count += 1
                            if isinstance(bo, Variable):
                                bounds[create_varname(bo)] = ''
                        elif isinstance(bo, Variable) and create_varname(bo)\
                                in bounds:
                            count += 1
                            bounds[create_varname(s)] = ''
                        elif isinstance(bo, URIRef) or isinstance(bo, Literal):
                            raise SparqlValidationFailed(f'Tried to bind {s}\
to Literal or IRI instead of Variable. Not implemented. Workaround to bind {s}\
to Variable and use FILTER.')
            elif isinstance(s, Variable) and p == RDF['type']:
                # (3)
                # definition means s is variable and p is <a>
                # when ?o is IRI then add ?s
                # when ?o is varible and ?s is bound, then define ?o
                if isinstance(o, URIRef):
                    count += 1
                    if create_varname(s) not in bounds:
                        bounds[create_varname(s)] = ''
                elif isinstance(o, Variable) and create_varname(s) in bounds:
                    count += 1
                    bounds[create_varname(o)] = ''
            elif not isinstance(s, BNode) or (p != ngsild['hasValue'] and p !=
                                              ngsild['hasObject'] and p != RDF['type']):  # (2)
                if isinstance(s, Variable) and create_varname(s) in bounds:
                    count += 1
                    if isinstance(o, Variable):
                        bounds[create_varname(o)] = ''
                elif isinstance(o, Variable) and create_varname(o) in bounds:
                    count += 1
                    if isinstance(s, Variable):
                        bounds[create_varname(s)] = ''
            elif isinstance(s, BNode):
                #  (4)
                count = 1
            else:
                raise SparqlValidationFailed("Could not reorder BGP triples.")
            if count > 0:
                return (s, p, o)

    bounds = copy.deepcopy(bounds)  # do not change the "real" bounds
    result = []
    while len(triples) > 0:
        candidate = select_candidates(bounds, triples, graph)
        if candidate is None:
            raise SparqlValidationFailed("Could not determine the right order\
of triples")
        result.append(candidate)
        triples.remove(candidate)

    return result


def get_random_string(num):
    return ''.join(random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(num))


def create_ngsild_mappings(ctx, sorted_graph):
    """Create structure which help to detect property/relationship variables
        
        We have to treat property and entity variables different
        since these are stored in different tables comparaed to
        plain RDF.
        entity variable is before a ngsild:property or ngsild:relationship (as defined in shacl.ttl by sh:property) or
        after iff:hasObject as Relationship.
        property_variable is after ngsild:hasValue
        Example BGP:
        BNode('Nc26056f5cd4647b697135d4a71ebc35a') <https://uri.etsi.org/ngsi-ld/hasObject> ?f .
        ?f <https://industry-fusion.com/types/v0.9/state> BNode('N4268834d83074ba1a14c199b3d6de955') .
        ?this <https://industry-fusion.com/types/v0.9/hasFilter> BNode('Nc26056f5cd4647b697135d4a71ebc35a') .
        ?this <'https://industry-fusion.com/types/v0.9/state'> BNode('Nd6d77ea8f25945c58c9ff19c8f853094') .
        BNode('N4268834d83074ba1a14c199b3d6de955') <'https://uri.etsi.org/ngsi-ld/hasValue'> ?v2 .
        BNode('Nd6d77ea8f25945c58c9ff19c8f853094') <'https://uri.etsi.org/ngsi-ld/hasValue> ?v1 .
        Would lead to:
        property_variables = {"v2": True, "v1": True}
        entity_variables = {"f": True, "this": True}
        row = {"f": "https://industry-fusion.com/types/v0.9/filter", "this": "https://industry-fusion.com/types/v0.9/cutter",
               "v1": "https://industry-fusion.com/types/v0.9/cutter", "v2": "https://industry-fusion.com/types/v0.9/filter"}

    Args:
        ctx (dictionary): sparql context containing metadata and results
        sorted_graph (dictionary): triples from bgp with defined order
    Returns:
        Touple of Property_variables, entity_variables, row dictionaries containing the respective
        predicates and mapping
    """  # noqa E501

    property_variables = {}
    entity_variables = {}
    for s, p, o in sorted_graph:
        if p == ngsild['hasValue']:
            if isinstance(o, Variable):
                property_variables[o] = True
        if p == ngsild['hasObject']:
            if isinstance(o, Variable):
                entity_variables[o] = True
        if p.toPython() in relationships:
            if isinstance(s, Variable):
                entity_variables[s] = True
        if p.toPython() in properties:
            if isinstance(s, Variable):
                entity_variables[s] = True
    # For every entity or property_variable, find out to which entity class it belongs to.
    # Straight forward way is to create another sparql query against shacl.ttl to validate
    # that varialbles have a meaningful target.
    # It is okay to have ambiguities but if there is no result an exception is thrown, because this query
    # cannot lead to a result at all.
    if property_variables or entity_variables:

        sparqlvalidationquery = ''
        equivalence = []
        variables = []
        for key, value in ctx['classes'].items():
            sparqlvalidationquery += f'?{key} rdfs:subClassOf <{value.toPython()}> .\n'
            sparqlvalidationquery += f'<{value.toPython()}> rdfs:subClassOf ?{key} .\n'
        for entity in entity_variables.keys():
            sparqlvalidationquery += f'?{entity}shape sh:targetClass ?{entity} .\n'
            variables.append(entity)
            for s, p, o in sorted_graph.triples((entity, None, None)):
                property_class = sorted_graph.value(o, ngsild['hasObject'])
                if property_class is not None:
                    sparqlvalidationquery += f'?{s}shape sh:property [ sh:path <{p}> ; sh:property \
[ sh:path ngsild:hasObject;  sh:class ?{property_class} ] ] .\n'
        for property in property_variables:
            variables.append(property)
            sparqlvalidationquery += f'?{property}shape sh:targetClass ?{property} .\n'
            for s, p, o in sorted_graph.triples((None, ngsild['hasValue'], property)):
                for p in sorted_graph.predicates(object=s):
                    sparqlvalidationquery += f'?{property}shape sh:property [ sh:path <{p}> ; ] .\n'
                    for subj in sorted_graph.subjects(predicate=p, object=s):
                        if isinstance(subj, Variable):
                            equivalence.append(f'{subj.toPython()}shape = ?{property}shape')
        query = basequery
        for variable in variables:
            query += f'?{variable} '
        query += '\nwhere {\n' + sparqlvalidationquery
        first = True
        for equiv in equivalence:
            if first:
                first = False
                query += 'filter('
            else:
                query += ' && '
            query += equiv
        if not first:
            query += ')\n}'
        else:
            query += '}'

        # Now execute the validation query
        # For the time being only unique resolutions of classes are allowed.
        # TODO: Implement multi class resolutions
        if debug > 2:
            print(f'DEBUG: Validation Query: {query}', file=debugoutput)
        qres = g.query(query)
        if debug > 2:
            print(f'DEBUG: Result of Validation Query: {list(qres)}', file=debugoutput)
        if len(qres) != 1:
            raise SparqlValidationFailed("Validation of BGP failed. It either contradicts what is defined in \
SHACL or is too ambigue!")
    else:
        # no ngsi-ld variables found, so do not try to infer the types
        qres = []

    row = None
    for r in qres:
        row = r
    return property_variables, entity_variables, row


def process_ngsild_spo(ctx, local_ctx, s, p, o):
    """Processes triple which relates to NGSI-LD objects

    Typical NGSI-LD reference in SPARQL looks like this:
    ?id p [hasValue|hasObject ?var|iri|literal]
    id is id of NGSI-LD object
    p is predicate of NGSI-LD as defined in SHACL
    hasValue|hasObject dependent on whether p describes a property or a relationship
    var|uri either binds var to the pattern or a concrete literal|iri

    case 1: hasValue + ?var, ?id already bound
    select idptable.hasValue from attribues as idptable where idptable.id = idtable.p
    case 2: hasObject + ?var, ?id already bound(known)
    if ?id is bound and ?var is not bound and hasObject attribute is used:
    The p-attribute is looked up in the attributes table and the ?var-id is looked up in the respective
    type[?var] table. e.g. ?id p [hasObject ?var] =>
        Select * from attributes as idptable join type[?var] as vartable where idptable.id = idtable.p and idptable.hasObject = vartable.id
    case 3: hasObject + ?var, ?id is not bound(known) but ?var is known
        Select * from type[?id] as idtable join attributes as idptable where idtable.p = idptable.id  and idptable.hasObject = vartable.id

    Args:
        ctx (dictionary): RDFlib context from SPARQL parser
        local_ctx (dictionary): local context only relevant for current BGP
        s (RDFlib term): subject
        p (RDFLib term): predicate
        o (RDFLib term): object

    Raises:
        SparqlValidationFailed: limitation in SPARQL translation implementation
    """ # noqa E501

    if debug > 1:
        print(f'DEBUG: Processing as NGSILD {s, p, o}', file=debugoutput)
    # We got a triple <?var, p, []> where p is a shacle specified property
    # Now we need the ngsild part to determine if it is a relationship or not
    ngsildtype = list(local_ctx['h'].predicates(subject=o))
    ngsildvar = list(local_ctx['h'].objects(subject=o))
    if len(ngsildtype) != 1 or len(ngsildvar) != 1:
        raise SparqlValidationFailed(f'No matching ngsiltype or ngsildvar found for variable {s.toPython()}')
    if not isinstance(ngsildvar[0], Variable):
        raise SparqlValidationFailed(f'Binding of {s} to concrete iri|literal not (yet) supported. \
Consider to use a variable and FILTER.')
    # Now we have 3 parts:
    # ?subject_var p [ hasValue|hasObject ?object_var]
    # subject_table, attribute_table, object_table
    subject_tablename = f'{s.toPython().upper()}TABLE'[1:]
    subject_varname = f'{s.toPython()}'[1:]
    subject_sqltable = utils.camelcase_to_snake_case(utils.strip_class(local_ctx['row'][subject_varname]))
    attribute_sqltable = utils.camelcase_to_snake_case(utils.strip_class(p))
    attribute_tablename = f'{subject_varname.upper()}{attribute_sqltable.upper()}TABLE'
    # In case of Properties, no additional tables are defined
    if ngsildtype[0] == ngsild['hasValue']:
        if create_varname(ngsildvar[0]) not in local_ctx['bounds']:
            local_ctx['selvars'][ngsildvar[0].toPython()[1:]] = f'`{attribute_tablename}`.`{ngsildtype[0]}`'
            local_ctx['bounds'][ngsildvar[0].toPython()[1:]] = f'`{attribute_tablename}`.`{ngsildtype[0]}`'
        join_condition = f'{attribute_tablename}.id = {subject_tablename}.`{p}`'
        sql_expression = f'attributes_view AS {attribute_tablename}'
        local_ctx['bgp_tables'][attribute_tablename] = []
        local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                'join_condition': f'{join_condition}'})
    else:
        # In case of Relationships there are two cases:
        # (1) object_var is not defined
        # (2) object_var is already definied but no subject_var
        if ngsildtype[0] != ngsild['hasObject']:
            raise SparqlValidationFailed("Internal implementation error")
        if not isinstance(ngsildvar[0], Variable):
            raise SparqlValidationFailed(f'Binding {s} to non-variable {ngsildvar[0]} not supported. \
Consider using a variable and FILTER instead.')
        object_varname = f'{ngsildvar[0].toPython()}'[1:]
        object_sqltable = utils.camelcase_to_snake_case(utils.strip_class(local_ctx['row'][object_varname]))
        object_tablename = f'{object_varname.upper()}TABLE'
        if object_varname not in local_ctx['bounds']:
            # case (1)
            join_condition = f'{attribute_tablename}.id = {subject_tablename}.`{p}`'
            sql_expression = f'attributes_view AS {attribute_tablename}'
            local_ctx['bgp_tables'][attribute_tablename] = []
            local_ctx['bgp_tables'][object_tablename] = []
            local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                    'join_condition': f'{join_condition}'})
            local_ctx['bgp_sql_expression'].append({'statement': f'{object_sqltable}_view AS {object_tablename}',
                                                    'join_condition': f'{object_tablename}.id = \
{attribute_tablename}.`{ngsildtype[0].toPython()}`'})
            ctx['sql_tables'].append(object_sqltable)
            # if object_varname not in local_ctx['bounds']:
            local_ctx['selvars'][object_varname] = f'{object_tablename}.`id`'
            local_ctx['bounds'][object_varname] = f'{object_tablename}.`id`'
        else:
            # case (2)
            join_condition = f'{attribute_tablename}.`{ngsildtype[0].toPython()}` = {object_tablename}.id'
            sql_expression = f'attributes_view AS {attribute_tablename}'
            local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                    'join_condition': f'{join_condition}'})
            join_condition = f'{attribute_tablename}.id = {subject_tablename}.`{p}`'
            sql_expression = f'{subject_sqltable}_view AS {subject_tablename}'
            ctx['sql_tables'].append(subject_sqltable)
            local_ctx['bgp_tables'][attribute_tablename] = []
            local_ctx['bgp_tables'][subject_tablename] = []
            local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                   'join_condition': f'{join_condition}'})
            if subject_varname not in local_ctx['bounds']:
                local_ctx['selvars'][subject_varname] = f'`{subject_tablename}`.`id`'
                local_ctx['bounds'][subject_varname] = f'`{subject_tablename}`.`id`'


def process_rdf_spo(ctx, local_ctx, s, p, o):
    """Processes a subject, predicate, object triple and create sql term for it
    
    This processing assumes that the triple contains no ngsi-ld related term (such as hasObject, hasValue) and is a pure RDF triple
    Note that there cannot be arbitrate RDF terms. In our framework, the RDF(knowledge) is immutable. Everything which
    can change must be an NGSI-LD object(model). Therefore, for instance, there cannot be a term like:
    <ngsild-id> <pred> <object>
    because <pred> cannot be a defined NGSI-LD property/relationship (otherwise it would not be processed here)
    A "generic" relationship between knowledge and model is impossible then (because it would be either a NGSI-LD defined relation or
    the immutable knowledge must reference id's of the (mutable) model which is not possible by definition)

    Args:
        ctx (dictionary): global context derived from RDFlib SPARQL parser
        local_ctx (dictionary): local context only relevant for the BGP processing
        s (RDFLib term): subject
        p (RDFLib term): predicate
        o (RDFLib term): object

    Raises:
        SparqlValidationFailed: Reports implementation limitations
    """ # noqa E501
    # must be  RDF query
    if debug > 1:
        print(f'Processing as RDF query: {s, p, o}', file=debugoutput)
    if not isinstance(p, URIRef):
        raise SparqlValidationFailed("NON IRI RDF-predicate not (yet) supported.")
    # predicate must be static for now
    # NGSI-LD entity variables cannot be referenced in plain RDF with one exception:
    # ?var a ?type is allowed an the only connection between the knowledge and the model
    # if a new variable is found, which is neither property, nor entity, it will be bound
    # by RDF query
    rdftable_name = create_tablename(s, p, ctx['namespace_manager']) + get_random_string(10)

    # Process Subject.
    # If subject is variable AND NGSI-LD Entity, there is a few special cases which are allowed.
    # e.g. ?var a ?type
    # e.g. ?var a <iri>/Literal
    # relationship between NGSI-LD Entity subject and RDF term is otherwise forbidden
    subject_join_condition = None
    if isinstance(s, Variable) and (s in local_ctx['entity_variables'] or isentity(ctx, s)):
        if p == RDF['type']:
            entity = local_ctx['bounds'].get(create_varname(s))
            if entity is None and isinstance(o, URIRef):  # create entity table based on type definition
                subject_tablename = f'{s.toPython().upper()}TABLE'[1:]
                subject_varname = f'{s.toPython()}'[1:]
                subject_sqltable = utils.camelcase_to_snake_case(utils.strip_class(local_ctx['row'][subject_varname]))
                local_ctx['bgp_sql_expression'].append({'statement': f'{subject_sqltable}_view AS {subject_tablename}',
                                                        'join_condition': ''})
                ctx['sql_tables'].append(subject_sqltable)
                local_ctx['selvars'][subject_varname] = f'{subject_tablename}.`id`'
                local_ctx['bounds'][subject_varname] = f'{subject_tablename}.`id`'
                local_ctx['bgp_tables'][subject_tablename] = []
                predicate_join_condition = f"{rdftable_name}.predicate = '" + RDFS['subClassOf'].toPython() + "'"
                object_join_condition = f"{rdftable_name}.object = '{o.toPython()}'"
                subject_join_condition = f"{rdftable_name}.subject = {subject_tablename}.`type`"
                join_condition = f"{subject_join_condition} and {predicate_join_condition} and {object_join_condition}"
                statement = f"{configs.rdf_table_name} as {rdftable_name}"
                local_ctx['bgp_sql_expression'].append({'statement': statement, 'join_condition': join_condition})
                return
            else:
                entity = entity.replace('.`id`', '.id')  # Normalize cases when id is quoted
                entity_table = entity.replace('.id', '')
                entity_column = entity.replace('.id', '.type')
                global_tables = ctx['tables']
                if entity_table not in global_tables:
                    global_tables[entity_table] = []
                global_tables[entity_table].append('type')
                if isinstance(o, Variable):
                    # OK let's process the special case here
                    # Two cases: (1) object variable is bound (2) object variable unknown

                    object_join_bound = get_rdf_join_condition(o, local_ctx['property_variables'],
                                                               local_ctx['entity_variables'], local_ctx['bounds'])
                    if object_join_bound is None:
                        # (2)
                        # bind variable with type column of subject
                        # add variable to local table
                        local_ctx['selvars'][create_varname(o)] = entity_column
                        local_ctx['bounds'][create_varname(o)] = entity_column
                        return
                    else:
                        # (1)
                        # variable is bound, so get it and link it with bound value
                        objvar = local_ctx['bounds'][create_varname(o)]
                        local_ctx['where'] = merge_where_expression(local_ctx['where'], f'{entity_column} = {objvar}')
                        return
                else:
                    # subject entity variable but object is no variable
                    local_ctx['where'] = merge_where_expression(local_ctx['where'], f'{entity_column} = \'{o}\'')
                    return
        else:
            raise SparqlValidationFailed("Cannot query generic RDF term with NGSI-LD entity subject.")
    else:
        # No special case. Check if subject is non bound and if non bound whether it can be bound
        subject_join_bound = get_rdf_join_condition(s, local_ctx['property_variables'],
                                                    local_ctx['entity_variables'], local_ctx['bounds'])
        if subject_join_bound is None:
            if not isinstance(s, Variable):
                raise SparqlValidationFailed("Could not resolve {s} and not a variable")
            # Variable not found, needs to be added
            subj_column = f'`{rdftable_name}`.`subject`'
            local_ctx['selvars'][create_varname(s)] = subj_column
            local_ctx['bounds'][create_varname(s)] = subj_column
            subject_join_bound = None
        subject_join_condition = f'{rdftable_name}.subject = {subject_join_bound}'\
            if subject_join_bound is not None else None
    predicate_join_condition = f'{rdftable_name}.predicate = \'{p.toPython()}\''
    # Process object join condition
    # object variables which are referencing ngsild-entities are forbidden
    if isinstance(o, Variable) and o in local_ctx['entity_variables']:
        raise SparqlValidationFailed('Cannot bind NGSI-LD Entities to RDF objects.')
    object_join_bound = get_rdf_join_condition(o, local_ctx['property_variables'],
                                               local_ctx['entity_variables'], local_ctx['bounds'])
    if object_join_bound is None:
        if not isinstance(o, Variable):
            raise SparqlValidationFailed("Could not resolve {o} not being a variable")
        # Variable not found, needs to be added
        local_ctx['selvars'][create_varname(o)] = f'{rdftable_name}.object'
        local_ctx['bounds'][create_varname(o)] = f'{rdftable_name}.object'
        object_join_bound = None
    object_join_condition = f'{rdftable_name}.object = {object_join_bound}' if object_join_bound is not None else None
    join_condition = f'{predicate_join_condition}'
    # if we found join condition for subject and object, add them
    if subject_join_condition is not None:
        join_condition = f'{subject_join_condition} and {join_condition}'
    if object_join_condition is not None:
        join_condition += f' and {object_join_condition}'
    sql_expression = f'{configs.rdf_table_name} AS {rdftable_name}'
    local_ctx['bgp_tables'][rdftable_name] = []
    local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}', 'join_condition': f'{join_condition}'})


def translate_BGP(ctx, bgp):
    """Translates a Basic Graph Pattern into SQL term

    Assumption is that the model data is provided in NGSI-LD tables and Knowlege data as triples in
    a RDF table

    Args:
        ctx (dictionary): Contains the results and metadata, e.g. variable mapping, resulting sql expression
        bgp (dictionary): BGP structure provided by RDFLib SPARQL parser

    Raises:
        WrongSparqlStructure: Problems with SPARQL metadata, or features which are not implemented
        SparqlValidationFailed: Problems with SPARQL parsing, dependencies
    """
    if debug > 2:
        print(f'DEBUG: BGP: {bgp}', file=debugoutput)
    # Assumes a 'Basic Graph Pattern'
    if not bgp.name == 'BGP':
        raise WrongSparqlStructure('No BGP!')
    # Add triples one time
    add_triples = ctx['add_triples']
    for triple in add_triples:
        bgp.triples.append(triple)
    ctx['add_triples'] = []

    # Translate set of triples into Graph for later processing
    if len(bgp.triples) == 0:
        bgp['sql_context'] = {}
        bgp['where'] = ''
        bgp['target_sql'] = ''
        return
    h = Graph()
    for s, p, o in bgp.triples:
        h.add((s, p, o))

    property_variables, entity_variables, row = create_ngsild_mappings(ctx, h)

    # before translating, sort the bgp order to allow easier binds
    bgp.triples = sort_triples(ctx['bounds'], bgp.triples, h)

    local_ctx = {}
    local_ctx['bounds'] = ctx["bounds"]
    local_ctx['selvars'] = {}
    local_ctx['where'] = ''
    local_ctx['bgp_sql_expression'] = []
    local_ctx['bgp_tables'] = {}
    local_ctx['property_variables'] = property_variables
    local_ctx['entity_variables'] = entity_variables
    local_ctx['h'] = h
    local_ctx['row'] = row

    for s, p, o in bgp.triples:
        # If there are properties or relationships, assume it is a NGSI-LD matter
        if (p.toPython() in properties or p.toPython() in relationships) and isinstance(o, BNode):
            if isinstance(s, Variable):
                process_ngsild_spo(ctx, local_ctx, s, p, o)
        elif p != ngsild['hasValue'] and p != ngsild['hasObject']:
            # must be  RDF query
            process_rdf_spo(ctx, local_ctx, s, p, o)

        else:
            if debug > 1:
                print(f'DEBUG: Ignoring: {s, p, o}', file=debugoutput)

    bgp_join_conditions = []
    if len(local_ctx['bgp_sql_expression']) != 0:
        map_join_condition(local_ctx['bgp_sql_expression'], local_ctx['bgp_tables'], ctx['tables'])
        bgp_join_conditions = []
        if local_ctx['where'] != '':
            bgp_join_conditions.append(local_ctx['where'])
    bgp['sql_context'] = create_bgp_context(local_ctx['selvars'], bgp_join_conditions,
                                            local_ctx['bgp_sql_expression'], local_ctx['bgp_tables'])
    tables = ctx['tables']
    for table, value in local_ctx['bgp_tables'].items():
        if table not in tables:
            tables[table] = []
        tables[table] += value
    if local_ctx['bgp_sql_expression']:
        bgp['target_sql'], bgp['where'] = merge_bgp_context(local_ctx['bgp_sql_expression'], True)
    else:
        bgp['target_sql'] = ''
        bgp['where'] = local_ctx['where']
