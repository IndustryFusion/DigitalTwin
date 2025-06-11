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
import random
from rdflib import Namespace, URIRef, Variable, BNode, Literal
from rdflib.namespace import RDF
import copy


basequery = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT
"""

ngsild = Namespace("https://uri.etsi.org/ngsi-ld/")

file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import utils  # noqa: E402
import configs  # noqa: E402

replace_attributes_prefix = 'REPLACE_ATTRIBUTES_TABLE_FOR_'
replace_attributes_postfix = 'POSTFIX'


def replace_attributes_table_expression(sql_expression, vars):
    for var in vars:
        toreplace = replace_attributes_prefix + var + replace_attributes_postfix
        sql_expression = sql_expression.replace(toreplace, 'attributes')
    sql_expression = re.sub(replace_attributes_prefix + r'[^\s]+' + replace_attributes_postfix,
                            'attributes_view',
                            sql_expression)
    return sql_expression


def create_attribute_table_expression(ctx, attribute_tablename, var):
    if 'group_by_vars' not in ctx:
        expression = f'attributes_view AS {attribute_tablename}'
    else:
        expression = f'{replace_attributes_prefix}{utils.create_varname(var)}{replace_attributes_postfix} \
AS {attribute_tablename}'
    return expression


def merge_vartypes(ctx, property_variables, entity_variables, time_variables):
    if 'property_variables' not in ctx:
        ctx['property_variables'] = property_variables
    else:
        ctx['property_variables'] = {**(ctx['property_variables']), **property_variables}
    if 'entity_variables' not in ctx:
        ctx['entity_variables'] = entity_variables
    else:
        ctx['entity_variables'] = {**(ctx['entity_variables']), **entity_variables}
    if 'time_variables' not in ctx:
        ctx['time_variables'] = time_variables
    else:
        ctx['time_variables'] = {**(ctx['time_variables']), **time_variables}


def isentity(ctx, variable):
    if utils.create_varname(variable) in ctx['bounds']:
        table = ctx['bounds'][utils.create_varname(variable)]
    else:
        return False
    if re.search(r'\.id$', table):
        return True
    else:
        return False


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
        raise utils.SparqlValidationFailed(f'Could not convert subject {subject} to \
table-name')

    return f'{subj}{pred}TABLE'


def merge_where_expression(where1, where2):
    if where1 == '' and where2 == '':
        return ''
    elif where1 == '':
        return where2
    elif where2 == '':
        return where1
    else:
        return f'{where1} and {where2}'


def get_rdf_join_condition(r, property_variables, entity_variables, time_variables,
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
        var = utils.create_varname(r)
        if r in property_variables or r in time_variables:
            variables = property_variables if r in property_variables else time_variables
            if var in selectvars:
                if variables[r]:
                    return "'<'||" + selectvars[var] + "||'>'"
                else:
                    return """'"'||""" + selectvars[var] + """||'"'"""
            else:
                raise utils.SparqlValidationFailed(f'Could not resolve variable \
?{var} at this point. You might want to rearrange the query to hint to \
translator.')
        elif r in entity_variables:
            raise utils.SparqlValidationFailed(f'Cannot bind enttiy variable {r} to \
plain RDF context')
        elif var in selectvars:  # plain RDF variable
            return selectvars[var]
    elif isinstance(r, URIRef) or isinstance(r, Literal):
        return f'{utils.format_node_type(r)}'
    else:
        raise utils.SparqlValidationFailed(f'RDF term {r} must either be a Variable, \
IRI or Literal.')


def sort_triples(ctx, bounds, triples, graph):
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
    def sort_key(triple):

        key = ''
        if not isinstance(triple[0], BNode):
            key += triple[0].toPython()
        else:
            ptriples = graph.triples((None, None, triple[0]))
            for _, p, _ in ptriples:
                key += p.toPython()
        if not isinstance(triple[1], BNode):
            key += triple[1].toPython()
        if not isinstance(triple[2], BNode):
            key += triple[2].toPython()
        else:
            ptriples = graph.triples((triple[2], None, None))
            for _, p, _ in ptriples:
                key += p.toPython()
        return key

    def select_candidates(bounds, triples, graph):
        for s, p, o in triples:
            count = 0
            # look for nodes: (1) NGSI-LD node and (2) plain RDF (3) RDF type definition (4) rest
            if isinstance(s, Variable) and (p.toPython() in ctx['relationships'] or
                                            p.toPython() in ctx['properties']):
                if isinstance(o, BNode):
                    blanktriples = graph.triples((o, None, None))
                    for (bs, bp, bo) in blanktriples:
                        # (1)
                        if utils.create_varname(s) in bounds:
                            count += 1
                            if isinstance(bo, Variable):
                                bounds[utils.create_varname(bo)] = ''
                        elif isinstance(bo, Variable) and utils.create_varname(bo)\
                                in bounds:
                            count += 1
                            bounds[utils.create_varname(s)] = ''
                        elif isinstance(bo, URIRef) or isinstance(bo, Literal):
                            raise utils.SparqlValidationFailed(f'Tried to bind {s}\
to Literal or IRI instead of Variable. Not implemented. Workaround to bind {s}\
to Variable and use FILTER.')
            elif isinstance(s, Variable) and p == RDF['type']:
                # (3)
                # definition means s is variable and p is <a>
                # when ?o is IRI then add ?s
                # when ?o is varible and ?s is bound, then define ?o
                if isinstance(o, URIRef):
                    count += 1
                    if utils.create_varname(s) not in bounds:
                        bounds[utils.create_varname(s)] = ''
                elif isinstance(o, Variable) and utils.create_varname(s) in bounds:
                    count += 1
                    bounds[utils.create_varname(o)] = ''
                elif isinstance(o, Variable) and utils.create_varname(o) in bounds:
                    count += 1
                    bounds[utils.create_varname(s)] = ''
            elif not isinstance(s, BNode) or (p != ngsild['hasValue'] and p !=
                                              ngsild['hasObject'] and p != ngsild['observedAt'] and
                                              p != RDF['type']):  # (2)
                if isinstance(s, Variable) and utils.create_varname(s) in bounds and not isinstance(o, BNode):
                    count += 1
                    if isinstance(o, Variable):
                        bounds[utils.create_varname(o)] = ''
                elif isinstance(o, Variable) and utils.create_varname(o) in bounds:
                    count += 1
                    if isinstance(s, Variable):
                        bounds[utils.create_varname(s)] = ''
                elif isinstance(s, Variable) and isinstance(o, URIRef):
                    count += 1
                    bounds[utils.create_varname(s)] = ''
                elif isinstance(o, BNode):  # rdf with blank nodes
                    blanktriples = graph.triples((o, None, None))
                    for (bs, bp, bo) in blanktriples:
                        if utils.create_varname(s) in bounds:
                            count += 1
                            if isinstance(bo, Variable):
                                bounds[utils.create_varname(bo)] = ''
                        elif isinstance(bo, Variable) and utils.create_varname(bo) in bounds:
                            count += 1
                            bounds[utils.create_varname(s)] = ''
            elif isinstance(s, BNode):
                #  (4)
                count = 1
            else:
                raise utils.SparqlValidationFailed("Could not reorder BGP triples.")
            if count > 0:
                return (s, p, o)

    bounds = copy.deepcopy(bounds)  # do not change the "real" bounds
    result = []
    sorted_triples = sorted(triples, key=sort_key)
    while len(sorted_triples) > 0:
        candidate = select_candidates(bounds, sorted_triples, graph)
        if candidate is None:
            raise utils.SparqlValidationFailed(f"Could not determine the right order \
of triples {str(triples)}")
        result.append(candidate)
        sorted_triples.remove(candidate)
    return result


def get_random_string(num):
    return ''.join(random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(num))


def create_ngsild_mappings(ctx, sorted_graph):
    """Create structure which help to detect property/relationship variables
        
        We have to treat property and entity variables different
        since these are stored in different tables compared to
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
    time_variables = {}
    for s, p, o in sorted_graph:
        if p == ngsild['hasValue']:
            if isinstance(o, Variable):
                # It is a property, but is it Literal or IRI?
                isIri = None
                for _, prop_p, _ in sorted_graph.triples((None, None, s)):
                    prop_plain = prop_p.toPython()
                    if prop_plain in ctx['properties'] and isIri is None:
                        isIri = ctx['properties'][prop_plain]
                    else:
                        raise utils.WrongSparqlStructure(f"Unexpected property structure found for property \
{prop_p}. Check if the prefix + property exists in the shacl definion.\n Check expression {ctx['query']}.")
                property_variables[o] = isIri
        if p == ngsild['hasObject']:
            if isinstance(o, Variable):
                entity_variables[o] = True
        if p.toPython() in ctx['relationships']:
            if isinstance(s, Variable):
                entity_variables[s] = True
        if p.toPython() in ctx['properties']:
            if isinstance(s, Variable):
                entity_variables[s] = True
        if p == ngsild['observedAt']:
            if isinstance(o, Variable):
                # it is always a Literal but is it a property or a relationship?
                isRel = None
                for _, prop_p, _ in sorted_graph.triples((None, None, s)):
                    prop_plain = prop_p.toPython()
                    if prop_plain in ctx['relationships'] and isRel is None:
                        isRel = True
                    elif isRel is None:
                        isRel = False
                    else:
                        raise utils.WrongSparqlStructure('Unexpected time(observedAt) property structure found.')
                time_variables[o] = isRel

    return property_variables, entity_variables, time_variables


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
        utils.SparqlValidationFailed: limitation in SPARQL translation implementation
    """ # noqa E501

    # We got a triple <?var, p, []> where p is a shacle specified property
    # Now we need the ngsild part to determine if it is a relationship or not
    ngsildtype = list(local_ctx['h'].predicates(subject=o))
    ngsildvar = list(local_ctx['h'].objects(subject=o))
    if len(ngsildtype) != 1 or len(ngsildvar) != 1:
        raise utils.SparqlValidationFailed(f'No matching ngsiltype or ngsildvar found for variable \
{s.toPython()} while parsing {ctx["query"]}')
    if not isinstance(ngsildvar[0], Variable):
        raise utils.SparqlValidationFailed(f'Binding of {s} to concrete iri|literal not (yet) supported. \
Consider to use a variable and FILTER. Target query is {ctx["query"]}')
    # Now we have 3 parts:
    # ?subject_var p [ hasValue|hasObject ?object_var]
    # subject_table, attribute_table, object_table
    subject_tablename = f'{s.toPython().upper()}TABLE'[1:]
    subject_varname = f'{s.toPython()}'[1:]
    subject_sqltable = f'{configs.kafka_topic_ngsi_prefix_name}'
    attribute_sqltable = utils.camelcase_to_snake_case(utils.strip_class(p))
    attribute_tablename = f'{subject_varname.upper()}{attribute_sqltable.upper()}TABLE'
    if ngsildtype[0] == ngsild['hasValue']:
        if utils.create_varname(ngsildvar[0]) not in local_ctx['bounds']:
            local_ctx['bounds'][ngsildvar[0].toPython()[1:]] = f'`{attribute_tablename}`.`attributeValue`'
        if attribute_tablename not in local_ctx['bgp_tables'] and attribute_tablename not in ctx['tables']:
            sql_expression = create_attribute_table_expression(ctx, attribute_tablename, ngsildvar[0])
            join_condition = f"{attribute_tablename}.name = '{p}' and {subject_tablename}.id = \
{attribute_tablename}.entityId and {attribute_tablename}.type = '{str(ngsild['Property'])}' and \
IFNULL({attribute_tablename}.`deleted`, FALSE) IS FALSE and {attribute_tablename}.parentId IS NULL"
            local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                    'join_condition': f'{join_condition}'})
        local_ctx['bgp_tables'][attribute_tablename] = []

    elif ngsildtype[0] == ngsild['hasObject']:
        # In case of Relationships there are two cases:
        # (1) object_var is not defined
        # (2) object_var is already definied but no subject_var
        if not isinstance(ngsildvar[0], Variable):
            raise utils.SparqlValidationFailed(f'Binding {s} to non-variable {ngsildvar[0]} not supported. \
Consider using a variable and FILTER instead.')
        object_varname = f'{ngsildvar[0].toPython()}'[1:]
        object_sqltable = f'{configs.kafka_topic_ngsi_prefix_name}'
        object_tablename = f'{object_varname.upper()}TABLE'
        if object_varname not in local_ctx['bounds']:
            # case (1)
            join_condition = f"{attribute_tablename}.name = '{p}' and {attribute_tablename}.entityId = \
{subject_tablename}.id and IFNULL({attribute_tablename}.`deleted`, FALSE) IS FALSE and \
{attribute_tablename}.parentId IS NULL"
            sql_expression = create_attribute_table_expression(ctx, attribute_tablename, ngsildvar[0])
            local_ctx['bgp_tables'][attribute_tablename] = []

            local_ctx['bgp_tables'][object_tablename] = []
            local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                    'join_condition': f'{join_condition}'})
            local_ctx['bgp_sql_expression'].append({'statement': f'{object_sqltable}_view AS {object_tablename}',
                                                    'join_condition': f'{object_tablename}.id = \
{attribute_tablename}.`attributeValue` and {attribute_tablename}.type = \'{str(ngsild["Relationship"])}\' \
and IFNULL({object_tablename}.`deleted`, FALSE) IS FALSE'})
            ctx['sql_tables'].append(object_sqltable)
            local_ctx['bounds'][object_varname] = f'{object_tablename}.`id`'
        else:
            # case (2)
            join_condition = f'{attribute_tablename}.`attributeValue` = \
{object_tablename}.id and {attribute_tablename}.type = \
\'{str(ngsild["Relationship"])}\' and IFNULL({attribute_tablename}.`deleted`, FALSE) IS FALSE'
            sql_expression = create_attribute_table_expression(ctx, attribute_tablename, ngsildvar[0])
            local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                    'join_condition': f'{join_condition}'})
            join_condition = f"{attribute_tablename}.name = '{p}' and {attribute_tablename}.entityId = \
{subject_tablename}.id  AND IFNULL({subject_tablename}.`deleted`, FALSE) IS FALSE and \
{attribute_tablename}.parentId IS NULL"
            sql_expression = f'{subject_sqltable}_view AS {subject_tablename}'
            ctx['sql_tables'].append(subject_sqltable)
            local_ctx['bgp_tables'][attribute_tablename] = []
            local_ctx['bgp_tables'][subject_tablename] = []
            local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                   'join_condition': f'{join_condition}'})
            if subject_varname not in local_ctx['bounds']:
                local_ctx['bounds'][subject_varname] = f'`{subject_tablename}`.`id`'
    else:
        # it must be a time value
        if ngsildtype[0] != ngsild['observedAt']:
            raise utils.SparqlValidationFailed(f"Internal implementation error. Found unexpected NGSI-LD \
property {ngsildtype[0]} in {ctx['query']}")
        if utils.create_varname(ngsildvar[0]) not in local_ctx['bounds']:
            local_ctx['bounds'][ngsildvar[0].toPython()[1:]] = f'`{attribute_tablename}`.`ts`'
        if attribute_tablename not in local_ctx['bgp_tables'] and attribute_tablename not in ctx['tables']:
            raise utils.SparqlValidationFailed(f"observedAt attributes can currently only be retrieved in \
conjunction with the respective hasValue/hasObject attribues/relationships. \
E.g. ?entity <p> [ngsild:hasValue ?var] . ?entity <p> [ngsild:observedAt ?varTs]. Found in query {ctx['query']}")
        local_ctx['bgp_tables'][attribute_tablename] = []


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
        utils.SparqlValidationFailed: Reports implementation limitations
    """ # noqa E501
    # must be  RDF query
    if not isinstance(p, URIRef):
        raise utils.SparqlValidationFailed("NON IRI RDF-predicate not (yet) supported.")
    if isinstance(s, BNode):  # Blank node subject, e.g. ([], p, o) is handled by respective (s, p2, []) nodes
        return
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
    if isinstance(s, Variable) and (s in ctx['entity_variables'] or isentity(ctx, s)):
        # special case p == rdf-type
        if p == RDF['type']:
            entity = local_ctx['bounds'].get(utils.create_varname(s))
            if entity is None:  # create entity table based on type definition
                subject_tablename = f'{s.toPython().upper()}TABLE'[1:]
                subject_varname = f'{s.toPython()}'[1:]
                subject_sqltable = f'{configs.kafka_topic_ngsi_prefix_name}'

                join_condition = ''
                if isinstance(o, URIRef):
                    join_condition = f"'<'||{subject_tablename}.`type`||'>' = '<{o.toPython()}>'"
                else:
                    object_join_bound = get_rdf_join_condition(o,
                                                               ctx['property_variables'],
                                                               ctx['entity_variables'],
                                                               ctx['time_variables'],
                                                               local_ctx['bounds'])
                    join_condition = f"'<'||{subject_tablename}.`type`||'>' = {object_join_bound}"
                local_ctx['bgp_sql_expression'].append({'statement': f'{subject_sqltable}_view AS {subject_tablename}',
                                                        'join_condition': join_condition})
                ctx['sql_tables'].append(subject_sqltable)
                local_ctx['bounds'][subject_varname] = f'{subject_tablename}.`id`'
                local_ctx['bgp_tables'][subject_tablename] = []
                # predicate_join_condition = f"{rdftable_name}.predicate = '<" + RDFS['subClassOf'].toPython() + ">'"
                # object_join_condition = f"{rdftable_name}.object = '<{o.toPython()}>'"
                # subject_join_condition = f"{rdftable_name}.subject = '<' || {subject_tablename}.`type` || '>'"
                # join_condition = f"{subject_join_condition} and {predicate_join_condition} and
                # {object_join_condition}"
                # statement = f"{configs.rdf_table_name} as {rdftable_name}"
                # local_ctx['bgp_sql_expression'].append({'statement': statement, 'join_condition': join_condition})
                return
            else:
                entity = entity.replace('.`id`', '.id')  # Normalize cases when id is quoted
                entity_column = entity.replace('.id', '.type')
                if isinstance(o, Variable):
                    # OK let's process the special case here
                    # Two cases: (1) object variable is bound (2) object variable unknown

                    object_join_bound = get_rdf_join_condition(o,
                                                               ctx['property_variables'],
                                                               ctx['entity_variables'],
                                                               ctx['time_variables'],
                                                               local_ctx['bounds'])
                    if object_join_bound is None:
                        # (2)
                        # bind variable with type column of subject
                        # add variable to local table
                        local_ctx['bounds'][utils.create_varname(o)] = entity_column
                        ctx['property_variables'][o] = True  # Treat it as property
                        # IRI (even though it is from an entity)
                        return
                    else:
                        # (1)
                        # variable is bound, so get it and link it with bound value
                        objvar = local_ctx['bounds'][utils.create_varname(o)]
                        local_ctx['where'] = merge_where_expression(local_ctx['where'],
                                                                    f"'<'||{entity_column}||'>' = {objvar}")
                        return
                else:
                    # subject entity variable but object is no variable
                    local_ctx['where'] = merge_where_expression(local_ctx['where'],
                                                                f"'<'||{entity_column}||'>' \
= {utils.format_node_type(o)}")
                    return
        else:
            raise utils.SparqlValidationFailed("Cannot query generic RDF term with NGSI-LD entity subject.")
    else:
        # No special case.
        # Check if subject is non bound and if non bound whether it can be bound
        subject_join_bound = get_rdf_join_condition(s, ctx['property_variables'],
                                                    ctx['entity_variables'], ctx['time_variables'], local_ctx['bounds'])
        if subject_join_bound is None:
            if not isinstance(s, Variable):
                raise utils.SparqlValidationFailed("Could not resolve {s} and not a variable")
            # Variable not found, needs to be added
            subj_column = f'`{rdftable_name}`.`subject`'
            local_ctx['bounds'][utils.create_varname(s)] = subj_column
            subject_join_bound = None
        subject_join_condition = f'{rdftable_name}.subject = {subject_join_bound}'\
            if subject_join_bound is not None else None
    predicate_join_condition = f'{rdftable_name}.predicate = {utils.format_node_type(p)}'
    # Process object join condition
    # object variables which are referencing ngsild-entities are forbidden
    if isinstance(o, Variable) and o in ctx['entity_variables']:
        raise utils.SparqlValidationFailed('Cannot bind NGSI-LD Entities to RDF objects.')
    # two cases: (1) object is either variable or Literal/IRI (2) object is Blank Node
    if not isinstance(o, BNode):  # (1)
        object_join_bound = get_rdf_join_condition(o, ctx['property_variables'],
                                                   ctx['entity_variables'], ctx['time_variables'], local_ctx['bounds'])
        if object_join_bound is None:
            if not isinstance(o, Variable):
                raise utils.SparqlValidationFailed("Could not resolve {o} not being a variable")
            # Variable not found, needs to be added
            local_ctx['bounds'][utils.create_varname(o)] = f'{rdftable_name}.object'
            object_join_bound = None
        object_join_condition = f'{rdftable_name}.object = {object_join_bound}' \
            if object_join_bound is not None else None
        join_condition = f'{predicate_join_condition}'
        # if we found join condition for subject and object, add them
        if subject_join_condition is not None:
            join_condition = f'{subject_join_condition} and {join_condition}'
        if object_join_condition is not None:
            join_condition += f' and {object_join_condition}'
        sql_expression = f'{configs.rdf_table_name} AS {rdftable_name}'
        local_ctx['bgp_tables'][rdftable_name] = []
        local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                'join_condition': f'{join_condition}'})
    else:  # (2)
        # We need to translate (s, p1, []), ([], p2, o) which means to join two tables
        # rdf as table1 on table1.predicate = p1 (and table1.subject = cond1) and table1.object = BN join
        # rdf as table2 on table2.predicate = p2 (and table2.object = cond2) and table2.subject = table1.object
        # (no need to check table2.subject = BN)
        sql_expression = f'{configs.rdf_table_name} AS {rdftable_name}'
        blankjoincondition = f'{rdftable_name}.object LIKE \'_:%\''
        join_condition = f'{predicate_join_condition} and {blankjoincondition}'
        if subject_join_condition is not None:
            join_condition = f'{subject_join_condition} and {join_condition}'
        local_ctx['bgp_tables'][rdftable_name] = []
        local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                'join_condition': f'{join_condition}'})

        for (bs, bp, bo) in local_ctx['h'].triples((o, None, None)):
            bo_rdftable_name = create_tablename(bo, bp, ctx['namespace_manager']) + get_random_string(10)
            bo_predicate_join_condition = f'{bo_rdftable_name}.predicate = {utils.format_node_type(bp)} and \
{rdftable_name}.object = {bo_rdftable_name}.subject'
            object_join_bound = get_rdf_join_condition(bo, ctx['property_variables'],
                                                       ctx['entity_variables'],
                                                       ctx['time_variables'],
                                                       local_ctx['bounds'])
            if object_join_bound is None:
                if not isinstance(bo, Variable):
                    raise utils.SparqlValidationFailed("Could not resolve {bo} not being a variable")
                # Variable not found, needs to be added
                local_ctx['bounds'][utils.create_varname(bo)] = f'{bo_rdftable_name}.object'
                object_join_bound = None
            object_join_condition = f'{bo_rdftable_name}.object = {object_join_bound}' \
                if object_join_bound is not None else None
            join_condition = f'{bo_predicate_join_condition}'
            # if we found join condition for subject and object, add them
            if subject_join_condition is not None:
                join_condition = f'{subject_join_condition} and {join_condition}'
            if object_join_condition is not None:
                join_condition += f' and {object_join_condition}'
            sql_expression = f'{configs.rdf_table_name} AS {bo_rdftable_name}'
            local_ctx['bgp_tables'][bo_rdftable_name] = []
            local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                    'join_condition': f'{join_condition}'})
