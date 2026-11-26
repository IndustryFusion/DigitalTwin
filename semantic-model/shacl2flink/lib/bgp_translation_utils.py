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
import re
import itertools
from rdflib import Namespace, URIRef, Variable, BNode, Literal
from rdflib.namespace import RDF, RDFS
from rdflib.paths import InvPath, MulPath, Path, SequencePath
import copy
import lib.utils as utils
import lib.configs as configs


basequery = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT
"""

ngsild = Namespace("https://uri.etsi.org/ngsi-ld/")


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


PAYLOADS = (ngsild['hasValue'], ngsild['hasObject'], ngsild['observedAt'])


def steps(s, p, o):
    """A pattern with a property path as patterns without one: `<a>/<b>` and
    `^<a>`, in any combination, and rdfs:subClassOf*, which the knowledge
    holds as its closure."""
    if isinstance(p, SequencePath):
        found = []
        for number, step in enumerate(p.args):
            last = number == len(p.args) - 1
            following = p.args[number + 1] if not last else None
            end = o if last else BNode() if following in PAYLOADS else Variable('path' + get_unique_suffix(8))
            found += steps(s, step, end)
            s = end
        return found
    if isinstance(p, InvPath):
        return steps(o, p.arg, s)
    if isinstance(p, MulPath) and p.path == RDFS.subClassOf and p.zero and p.more:
        return [(s, p.path, o)]
    if isinstance(p, Path):
        raise utils.SparqlValidationFailed(f'The property path {p.n3()} is not supported. Only <a>/<b>, ^<a> and \
rdfs:subClassOf* are.')
    return [(s, p, o)]


def normalise_attributes(triples):
    """Every way to read an attribute, in the one form that is translated:
    `?entity predicate [ ngsild:hasValue|hasObject|observedAt ?variable ]`.

      * `?s p ?a . ?a ngsild:hasValue ?v` -- a named instance
      * `?s p [ ngsild:hasValue ?v ; ngsild:observedAt ?t ]` -- several at once
      * `?s p [ ngsild:hasValue "x" ]` -- a constant: a variable, and a condition
      * `?s p/ngsild:hasValue ?v` -- a path

    Returns (triples, {variable: constant}, the variables of targets, the
    variables of entities named by their IRI). What NGSI-LD says and the tables
    do not hold is refused here, by name, rather than becoming a join on the
    knowledge that never matches.
    """
    plain = []
    constants = {}
    for s, p, o in triples:
        plain += steps(s, p, o)

    nodes = {s for s, p, o in plain if p in PAYLOADS and not isinstance(s, URIRef)}
    holders = {}
    for s, p, o in plain:
        if o in nodes and p not in PAYLOADS:
            holders.setdefault(o, []).append((s, p))
    result = []
    targets = set()
    entities = {}                                     # an entity named by its IRI: its variable
    for s, p, o in plain:
        if o in holders and p not in PAYLOADS:
            continue                                  # written with each of its payloads, below
        if s in nodes and p not in PAYLOADS:
            name = p.n3() if isinstance(p, URIRef) else f'?{p}'
            if isinstance(p, URIRef) and p in ngsild:
                raise utils.SparqlValidationFailed(f'ngsild:{p[len(ngsild):]} of an attribute cannot be read. \
Only ngsild:hasValue, ngsild:hasObject and ngsild:observedAt can.')
            raise utils.SparqlValidationFailed(f'{name} is read from an attribute, not from an entity: \
sub-attributes cannot be queried.')
        if s in nodes and p in PAYLOADS:
            if s not in holders:
                raise utils.SparqlValidationFailed(f'ngsild:{p[len(ngsild):]} is read from something that is no \
attribute in the same group of patterns. Write it as ?entity <attribute> [ ngsild:{p[len(ngsild):]} ?variable ].')
            if len({holder for holder, _ in holders[s]}) > 1 or len({predicate for _, predicate in holders[s]}) > 1:
                raise utils.SparqlValidationFailed(f'{s.n3()} is the instance of two attributes; an instance belongs \
to one.')
            if isinstance(o, (URIRef, Literal)):
                variable = Variable('const' + get_unique_suffix(8))
                constants[variable] = o
                if p == ngsild['hasObject']:
                    targets.add(variable)
                o = variable
            for holder, predicate in holders[s]:
                if isinstance(holder, URIRef):
                    # a certain entity: a variable, and a condition
                    if holder not in entities:
                        entities[holder] = Variable('const' + get_unique_suffix(8))
                        constants[entities[holder]] = holder
                    holder = entities[holder]
                if isinstance(holder, BNode):
                    raise utils.SparqlValidationFailed(f'{predicate.n3()} is read from an attribute, not from an \
entity: sub-attributes cannot be queried.')
                instance = BNode()
                result += [(holder, predicate, instance), (instance, p, o)]
            continue
        result.append((s, p, o))
    return result, constants, targets, set(entities.values())


def register_attributes(ctx, triples):
    """What a pattern reads as an attribute is one, whether or not a shape with
    a target says so: `[ ngsild:hasObject ?x ]` cannot be anything else. Shapes
    only add what a value is, an IRI or a literal (sh:nodeKind)."""
    payload = {}
    for s, p, o in triples:
        if p in PAYLOADS:
            payload.setdefault(s, set()).add(p)
    relationships, properties = {}, {}
    for s, p, o in triples:
        if o in payload and p not in PAYLOADS:
            if ngsild['hasObject'] in payload[o]:
                relationships[p.toPython()] = True
            elif p.toPython() not in ctx['relationships']:
                properties[p.toPython()] = utils.ANY_VALUE
    for s, p, o in triples:
        if isinstance(s, Variable) and not isinstance(o, BNode) and not isinstance(p, Variable):
            kind = 'hasObject' if p.toPython() in {**ctx['relationships'], **relationships} else 'hasValue'
            if kind == 'hasObject' or p.toPython() in {**ctx['properties'], **properties}:
                error = utils.SparqlValidationFailed(f'{p.n3()} is an attribute, and an attribute is read in two \
steps: ?{s} <attribute> [ ngsild:{kind} {o.n3()} ].')
                error.pattern = describe_triple(ctx, [], (s, p, o))
                raise error
    if relationships or properties:
        ctx['relationships'] = {**ctx['relationships'], **relationships}
        ctx['properties'] = {**properties, **ctx['properties']}


def describe_triple(ctx, graph, triple):
    """A pattern as one would write it, for a message."""
    manager = ctx.get('namespace_manager')

    def said(term):
        if isinstance(term, BNode):
            inner = [f'{said(p)} {said(o)}' for _, p, o in graph.triples((term, None, None))]
            return f'[ {" ; ".join(inner)} ]' if inner else '[ ]'
        try:
            return term.n3(manager)
        except Exception:
            return str(term)
    return ' '.join(said(term) for term in triple)


def merge_vartypes(ctx, property_variables, entity_variables, time_variables, written=False):
    # What the knowledge has bound stays the knowledge's, in its own form --
    # except that a rule's template says as what a value is `written`.
    known = {**ctx.get('property_variables', {}), **ctx.get('time_variables', {})} if 'bounds' in ctx else {}
    property_variables = {var: kind for var, kind in property_variables.items()
                          if written or 'bounds' not in ctx or var in known or
                          utils.create_varname(var) not in ctx['bounds']}
    if 'property_variables' not in ctx:
        ctx['property_variables'] = property_variables
    else:
        known = ctx['property_variables']
        ctx['property_variables'] = {**known, **{var: kind for var, kind in property_variables.items()
                                                 if kind != utils.ANY_VALUE or var not in known}}
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
                if variables[r] == utils.ANY_VALUE:
                    return f'({utils.wrap_any_value(selectvars[var])})'
                if variables[r]:
                    return "'<'||" + selectvars[var] + "||'>'"
                else:
                    return """'"'||""" + selectvars[var] + """||'"'"""
            else:
                raise utils.SparqlValidationFailed(f'Could not resolve variable \
?{var} at this point. You might want to rearrange the query to hint to \
translator.')
        elif r in entity_variables:
            raise utils.SparqlValidationFailed(f'?{r} is an entity, and the knowledge holds no entities. \
Read an attribute of it as ?{r} <attribute> [ ngsild:hasValue|hasObject ?variable ].')
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

    def from_attribute(term):
        # What an attribute gives is read from the attribute before anything
        # is asked about it in the knowledge.
        return isinstance(term, Variable) and utils.create_varname(term) not in bounds and \
            any((None, payload, term) in graph for payload in PAYLOADS)

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
                            if isinstance(p, Variable):
                                bounds[utils.create_varname(p)] = ''
                        elif isinstance(bo, Variable) and utils.create_varname(bo)\
                                in bounds and bp != ngsild['observedAt']:
                            # (a time is read with its attribute, not to find it)
                            count += 1
                            bounds[utils.create_varname(s)] = ''
                            if isinstance(p, Variable):
                                bounds[utils.create_varname(p)] = ''
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
                if from_attribute(s) or from_attribute(o):
                    count = 0
                elif isinstance(s, Variable) and utils.create_varname(s) in bounds and not isinstance(o, BNode):
                    count += 1
                    if isinstance(o, Variable):
                        bounds[utils.create_varname(o)] = ''
                elif isinstance(o, Variable) and utils.create_varname(o) in bounds:
                    count += 1
                    if isinstance(s, Variable):
                        bounds[utils.create_varname(s)] = ''
                elif isinstance(s, Variable) and isinstance(o, (URIRef, Literal)):
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
            inside = [t for t in sorted_triples if isinstance(t[0], BNode) and isinstance(t[2], (URIRef, Literal)) and
                      any(True for _ in graph.triples((None, None, t[0]))) and
                      not any(parent in sorted_triples for parent in graph.triples((None, None, t[0])))]
            if inside and len(inside) == len(sorted_triples):
                said = ' .  '.join(describe_triple(ctx, graph, parent) for parent in
                                   dict.fromkeys(p for t in inside for p in graph.triples((None, None, t[0]))))
                raise utils.SparqlValidationFailed(f'A constant inside a blank node of the knowledge is not \
supported: {said}. Use a variable and compare it in a FILTER.')
            rest = ' .  '.join(describe_triple(ctx, graph, t) for t in sorted_triples
                               if not isinstance(t[0], BNode) or
                               not any(True for _ in graph.triples((None, None, t[0]))))
            raise utils.SparqlValidationFailed(f"These patterns are not connected with ?this or with \
anything read before them: {rest}")
        result.append(candidate)
        sorted_triples.remove(candidate)
    return result


ALIAS_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
_alias_counter = itertools.count()


def get_unique_suffix(num):
    """
    A suffix that makes a generated SQL alias unique.

    This used to be random, which meant the same shapes compiled to different
    SQL on every build -- so every rebuild looked like a change to helm even
    when nothing had. Uniqueness within one translation is all that is needed,
    and a counter gives that without the churn. Rendered in the same alphabet
    and width so aliases keep their shape.
    """
    value = next(_alias_counter)
    digits = []
    for _ in range(num):
        value, remainder = divmod(value, len(ALIAS_ALPHABET))
        digits.append(ALIAS_ALPHABET[remainder])
    return ''.join(reversed(digits))


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
{prop_p}. Check if the prefix + property exists in the shacl definion.")
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


def knowledge_literal(variable):
    return utils.SparqlValidationFailed(f'?{variable} is a value of an attribute and a literal of the knowledge, which \
writes numbers otherwise than the platform. Compare them in a FILTER, or let them meet on an IRI.')


def second_value(s, p, what):
    return utils.SparqlValidationFailed(f'Two {what} of {p.n3()} of {s.n3()} are read, which are two instances of one \
attribute. Read the second one in a FILTER EXISTS or NOT EXISTS.')


def attribute_name_condition(ctx, local_ctx, p, attribute_tablename):
    """How the attribute of a variable predicate is found: by the name the
    variable has already, else any, and the variable is bound to its name."""
    bound = None
    if utils.create_varname(p) in local_ctx['bounds']:
        if f'`{attribute_tablename}`.`name`' == local_ctx['bounds'][utils.create_varname(p)]:
            return f"{attribute_tablename}.name = {attribute_tablename}.name"
        bound = get_rdf_join_condition(p, ctx['property_variables'], ctx['entity_variables'],
                                       ctx['time_variables'], local_ctx['bounds'])
    if bound is not None:
        return f"'<'||{attribute_tablename}.name||'>' = {bound}"
    local_ctx['bounds'][utils.create_varname(p)] = f'`{attribute_tablename}`.`name`'
    ctx['property_variables'][p] = True
    return f"{attribute_tablename}.name IS NOT NULL"


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
        raise utils.SparqlValidationFailed('An attribute is read as ?entity <attribute> \
[ ngsild:hasValue|hasObject ?variable ].')
    if not isinstance(ngsildvar[0], Variable):
        raise utils.SparqlValidationFailed(f'Binding of {s} to concrete iri|literal not (yet) supported. \
Consider to use a variable and FILTER.')
    # Now we have 3 parts:
    # ?subject_var p [ hasValue|hasObject ?object_var]
    # subject_table, attribute_table, object_table
    subject_tablename = f'{s.toPython().upper()}TABLE'[1:]
    subject_varname = f'{s.toPython()}'[1:]
    subject_sqltable = f'{configs.kafka_topic_ngsi_prefix_name}'
    subquery = ctx.get('subquery', '')
    if isinstance(p, Variable):
        # `?this ?attribute [ ngsild:hasValue ?v ]`: any attribute, its name is
        # what the variable is.
        attribute_tablename = f'{subject_varname.upper()}ANY{utils.create_varname(p).upper()}ATTRIBUTETABLE{subquery}'
        name_condition = attribute_name_condition(ctx, local_ctx, p, attribute_tablename)
    else:
        attribute_sqltable = utils.camelcase_to_snake_case(utils.strip_class(p))
        attribute_tablename = f'{subject_varname.upper()}{attribute_sqltable.upper()}TABLE{subquery}'
        name_condition = f"{attribute_tablename}.name = '{p}'"
    if ngsildtype[0] == ngsild['hasValue']:
        column = f'`{attribute_tablename}`.`attributeValue`'
        bound = local_ctx['bounds'].get(utils.create_varname(ngsildvar[0]))
        if bound is None:
            if column in local_ctx['bounds'].values():
                raise second_value(s, p, 'values')
            local_ctx['bounds'][ngsildvar[0].toPython()[1:]] = column
        elif bound != column:
            # One variable in two places: what is in both has to be the same.
            kind = ctx['properties'].get(p.toPython(), utils.ANY_VALUE)
            term = utils.wrap_any_value(column) if kind == utils.ANY_VALUE else \
                f"'<'||{column}||'>'" if kind else f"'\"'||{column}||'\"'"
            other = get_rdf_join_condition(ngsildvar[0], ctx['property_variables'], ctx['entity_variables'],
                                           ctx['time_variables'], local_ctx['bounds'])
            if ngsildvar[0] in ctx.get('lexicals', {}):
                # a text BIND gave, as it was built; a text is no IRI
                same = f'{column} = {ctx["lexicals"][ngsildvar[0]]} AND SQL_DIALECT_NUMBER{{{column}}} IS NULL' \
                    if kind is not True else 'FALSE'
                if kind == utils.ANY_VALUE:
                    same += f" AND {column.replace('attributeValue', 'nodeType')} <> '@id'"
            elif ngsildvar[0] in ctx.get('computed', ()):
                # what BIND gives is a term already: its text is the value's
                same = f'{column} = SQL_DIALECT_STRIP_LITERAL{{{bound}}}'
            elif ngsildvar[0] not in ctx['property_variables'] and kind is not True and \
                    re.search(r'\.`?object`?$', bound):
                raise knowledge_literal(ngsildvar[0])
            else:
                same = f'({term}) = {other}'
            local_ctx['where'] = merge_where_expression(local_ctx['where'], same)
        if attribute_tablename not in local_ctx['bgp_tables'] and attribute_tablename not in ctx['tables']:
            sql_expression = create_attribute_table_expression(ctx, attribute_tablename, ngsildvar[0])
            join_condition = f"{name_condition} and {subject_tablename}.id = \
{attribute_tablename}.entityId and {attribute_tablename}.type = '{str(ngsild['Property'])}' and \
IFNULL({attribute_tablename}.`deleted`, FALSE) IS FALSE and {attribute_tablename}.parentId IS NULL"
            if bound is not None and subject_varname not in local_ctx['bounds']:
                # the value is known and the entity is not
                join_condition = join_condition.replace(
                    f'{subject_tablename}.id = {attribute_tablename}.entityId and ', '')
                local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                        'join_condition': f'{join_condition}'})
                sql_expression = f'{subject_sqltable}_view AS {subject_tablename}'
                join_condition = f'{subject_tablename}.id = {attribute_tablename}.entityId and \
IFNULL({subject_tablename}.`deleted`, FALSE) IS FALSE'
                ctx['sql_tables'].append(subject_sqltable)
                local_ctx['bounds'][subject_varname] = f'`{subject_tablename}`.`id`'
                local_ctx['bgp_tables'][subject_tablename] = []
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
        read = attribute_tablename in local_ctx['bgp_tables'] or attribute_tablename in ctx['tables']
        target = ctx.get('targets', {}).get(ngsildvar[0])
        if target is not None:
            # A certain target: its IRI is compared, whether or not it exists.
            if read:
                raise second_value(s, p, 'targets')
            local_ctx['bgp_sql_expression'].append({
                'statement': create_attribute_table_expression(ctx, attribute_tablename, ngsildvar[0]),
                'join_condition': f"{name_condition} and {attribute_tablename}.entityId = {subject_tablename}.id and \
{attribute_tablename}.`attributeValue` = '{target}' and {attribute_tablename}.type = '{str(ngsild['Relationship'])}' \
and IFNULL({attribute_tablename}.`deleted`, FALSE) IS FALSE and {attribute_tablename}.parentId IS NULL"})
            local_ctx['bgp_tables'][attribute_tablename] = []
        elif object_varname not in local_ctx['bounds']:
            # case (1)
            if read:
                raise second_value(s, p, 'targets')
            join_condition = f"{name_condition} and {attribute_tablename}.entityId = \
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
        elif read:
            # read before: it has to be this target
            local_ctx['where'] = merge_where_expression(
                local_ctx['where'], f"{attribute_tablename}.`attributeValue` = {local_ctx['bounds'][object_varname]}")
        elif subject_varname in local_ctx['bounds'] and \
                (subject_tablename in ctx['tables'] or subject_tablename in local_ctx['bgp_tables']):
            # both are known: only the relationship between them is read
            local_ctx['bgp_sql_expression'].append({
                'statement': create_attribute_table_expression(ctx, attribute_tablename, ngsildvar[0]),
                'join_condition': f"{name_condition} and {attribute_tablename}.entityId = \
{local_ctx['bounds'][subject_varname]} and {attribute_tablename}.`attributeValue` = \
{local_ctx['bounds'][object_varname]} and {attribute_tablename}.type = '{str(ngsild['Relationship'])}' and \
IFNULL({attribute_tablename}.`deleted`, FALSE) IS FALSE and {attribute_tablename}.parentId IS NULL"})
            local_ctx['bgp_tables'][attribute_tablename] = []
        else:
            # case (2)
            join_condition = f'{attribute_tablename}.`attributeValue` = \
{object_tablename}.id and {attribute_tablename}.type = \
\'{str(ngsild["Relationship"])}\' and IFNULL({attribute_tablename}.`deleted`, FALSE) IS FALSE'
            sql_expression = create_attribute_table_expression(ctx, attribute_tablename, ngsildvar[0])
            local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                    'join_condition': f'{join_condition}'})
            join_condition = f"{name_condition} and {attribute_tablename}.entityId = \
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
property {ngsildtype[0]}")
        if utils.create_varname(ngsildvar[0]) not in local_ctx['bounds']:
            # observedAt is a column of its own now. It used to be read from `ts`,
            # the Kafka record timestamp, because the bridge wrote it there --
            # which put a wall-clock retention policy in charge of an event
            # time. `ts` is the write time now and would silently make every
            # rule that filters on observedAt compare against the wrong clock.
            local_ctx['bounds'][ngsildvar[0].toPython()[1:]] = f'`{attribute_tablename}`.`observedAt`'
        elif local_ctx['bounds'][utils.create_varname(ngsildvar[0])] != f'`{attribute_tablename}`.`observedAt`':
            # one time in two places
            local_ctx['where'] = merge_where_expression(
                local_ctx['where'],
                f"`{attribute_tablename}`.`observedAt` = {local_ctx['bounds'][utils.create_varname(ngsildvar[0])]}")
        if attribute_tablename not in local_ctx['bgp_tables'] and attribute_tablename not in ctx['tables']:
            raise utils.SparqlValidationFailed("observedAt attributes can currently only be retrieved in \
conjunction with the respective hasValue/hasObject attribues/relationships. \
E.g. ?entity <p> [ngsild:hasValue ?var] . ?entity <p> [ngsild:observedAt ?varTs].")
        local_ctx['bgp_tables'][attribute_tablename] = []
        # No time, no solution: the column is there for every instance.
        local_ctx['where'] = merge_where_expression(local_ctx['where'],
                                                    f'`{attribute_tablename}`.`observedAt` IS NOT NULL')


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
        raise utils.SparqlValidationFailed('A variable as predicate is only supported for an attribute: \
?entity ?attribute [ ngsild:hasValue|hasObject ?variable ].')
    if isinstance(s, BNode):  # Blank node subject, e.g. ([], p, o) is handled by respective (s, p2, []) nodes
        if not any(True for _ in local_ctx['h'].triples((None, None, s))):
            raise utils.SparqlValidationFailed('A blank node as the subject of a pattern of the knowledge, with \
nothing pointing at it, is not supported. Use a variable.')
        return
    # predicate must be static for now
    # NGSI-LD entity variables cannot be referenced in plain RDF with one exception:
    # ?var a ?type is allowed an the only connection between the knowledge and the model
    # if a new variable is found, which is neither property, nor entity, it will be bound
    # by RDF query
    rdftable_name = create_tablename(s, p, ctx['namespace_manager']) + get_unique_suffix(10)

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
            raise utils.SparqlValidationFailed(f'?{s} is an entity, and the knowledge holds no entities. \
An attribute of it is read as ?{s} <attribute> [ ngsild:hasValue|hasObject ?variable ].')
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
        raise utils.SparqlValidationFailed(f'?{o} is an entity, and the knowledge holds no entities. A \
relationship to it is read as ?entity <relationship> [ ngsild:hasObject ?{o} ].')
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
        if object_join_bound is not None and isinstance(o, Variable) and \
                ctx['property_variables'].get(o, True) is not True:
            raise knowledge_literal(o)
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
        # [ ] in a query stands for any node, an IRI as well as a blank node
        sql_expression = f'{configs.rdf_table_name} AS {rdftable_name}'
        join_condition = f'{predicate_join_condition}'
        if subject_join_condition is not None:
            join_condition = f'{subject_join_condition} and {join_condition}'
        local_ctx['bgp_tables'][rdftable_name] = []
        local_ctx['bgp_sql_expression'].append({'statement': f'{sql_expression}',
                                                'join_condition': f'{join_condition}'})

        for (bs, bp, bo) in local_ctx['h'].triples((o, None, None)):
            bo_rdftable_name = create_tablename(bo, bp, ctx['namespace_manager']) + get_unique_suffix(10)
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
