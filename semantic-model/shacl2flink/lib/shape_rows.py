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
"""The rows of shacl_properties_to_sql's two big shape queries, by walking the graph.

`sparql_get_all_relationships` and `sparql_get_all_properties` read nothing but
the shape tree (plus rdfs:subClassOf for the inherited target classes), yet
rdflib's SPARQL engine needs most of a build to answer them on a large package:
their UNION arms are joined against every property node of the graph, and the
cost grows with the square of the number of property shapes (the OPC UA pump
package: 1,800 property shapes, 30 minutes for the two queries).

The functions here produce the same rows -- same variables, same values, same
multiplicities -- by evaluating the
queries' algebra directly: each pattern is evaluated with the bindings of the
row it extends, the way rdflib evaluates OPTIONAL, and every property path is
evaluated by rdflib's own path code. The SPARQL texts stay in
shacl_properties_to_sql as the definition; tests/test_shape_rows.py checks the
walk against them. One deliberate difference: the two GROUP_CONCAT columns of
the properties query are sorted (see property_rows).
"""

import functools

from rdflib import RDF, RDFS, BNode, Literal, Namespace, URIRef, Variable, XSD
from rdflib.namespace import SH
from rdflib.paths import OneOrMore, ZeroOrMore
from rdflib.plugins.sparql import prepareQuery
from rdflib.query import ResultRow

NGSILD_HAS_OBJECT = URIRef('https://uri.etsi.org/ngsi-ld/hasObject')
NGSILD_VALUE_PATHS = (URIRef('https://uri.etsi.org/ngsi-ld/hasValue'),
                      URIRef('https://uri.etsi.org/ngsi-ld/hasValueList'),
                      URIRef('https://uri.etsi.org/ngsi-ld/hasJSON'))
LIST_CONNECTIVES = (SH['or'], SH['and'], SH.xone)       # the VALUES order of the queries
ALL_CONNECTIVES = (SH['or'], SH['and'], SH.xone, SH['not'])
OWN_PARAMETERS = (SH.minCount, SH.maxCount, SH.nodeKind, SH.property)
TRUE = Literal(True)

# The property paths of the queries, as rdflib's parser builds them.
MEMBERS = (RDF.rest * ZeroOrMore) / RDF.first                            # rdf:rest*/rdf:first
SUBCLASS_STAR = RDFS.subClassOf * ZeroOrMore                             # rdfs:subClassOf*
_CONNECTIVE_MEMBERS = (SH['or'] | SH['and'] | SH.xone) / (RDF.rest * ZeroOrMore) / RDF.first
# (sh:property|(sh:or|sh:and|sh:xone)/rdf:rest*/rdf:first|sh:not)+
REACHABLE = (SH.property | _CONNECTIVE_MEMBERS | SH['not']) * OneOrMore
IN_MEMBERS = SH['in'] / (MEMBERS * OneOrMore)                            # sh:in/(rdf:rest*/rdf:first)+
OR_MEMBERS = SH['or'] / MEMBERS                                          # sh:or/rdf:rest*/rdf:first
PROPERTY_OR_MEMBERS = SH.property / SH['or'] / MEMBERS                   # sh:property/sh:or/rdf:rest*/rdf:first


# The prefixes the two queries use; translate() passes these among others.
QUERY_PREFIXES = {'sh': SH, 'rdf': RDF, 'rdfs': RDFS,
                  'ngsi-ld': Namespace('https://uri.etsi.org/ngsi-ld/')}


@functools.lru_cache(maxsize=None)
def _projection(query_text):
    """The SELECT variables of a query, in order: the labels of its rows."""
    return [Variable(str(v)) for v in prepareQuery(query_text, initNs=QUERY_PREFIXES).algebra['PV']]


def _objects(g, subject, path):
    """Objects of a (possibly path) pattern with a bound subject, with the
    multiplicity rdflib's evaluation gives. A literal has no triples; rdflib's
    path code would take a falsy one (false, 0, "") for an unbound subject."""
    if isinstance(subject, Literal):
        return []
    return [o for _, _, o in g.triples((subject, path, None))]


def _distinct(rows, keys):
    """rdflib evaluates the queries' two UNIONs without the bindings of the
    patterns before them and keeps their solutions as a SET (a non-lazy Join),
    so a clause reached twice -- a list naming one shape twice -- counts once.
    `rows` extend one row by one union's solutions; `keys` are that union's
    variables."""
    seen = set()
    for row in rows:
        key = tuple(row.get(k) for k in keys)
        if key not in seen:
            seen.add(key)
            yield row


def _optional(rows, solutions_of):
    """SPARQL OPTIONAL: each row extended by every compatible solution, or kept
    as it is when there is none. `solutions_of(row)` gives the pattern's
    solutions (dicts) with the row's bindings already applied."""
    for row in rows:
        merged = []
        for solution in solutions_of(row):
            if all(row.get(var) is None or row[var] == value for var, value in solution.items()):
                merged.append({**row, **solution})
        if merged:
            yield from merged
        else:
            yield row


def _optional_value(rows, var, values_of):
    """OPTIONAL { <bound term> <path> ?var }."""
    return _optional(rows, lambda row: [{var: v} for v in values_of(row)])


def _head(g):
    """?nodeshape a sh:NodeShape ; sh:targetClass ?targetclass .
    ?inheritedTargetclass rdfs:subClassOf* ?targetclass .
    ?nodeshape (sh:property|(sh:or|sh:and|sh:xone)/rdf:rest*/rdf:first|sh:not)+ ?property .
    ?property sh:path ?propertypath ."""
    for nodeshape in g.subjects(RDF.type, SH.NodeShape):
        for targetclass in g.objects(nodeshape, SH.targetClass):
            inherited = [s for s, _, _ in g.triples((None, SUBCLASS_STAR, targetclass))]
            reachable = _objects(g, nodeshape, REACHABLE)
            for inherited_class in inherited:
                for prop in reachable:
                    for propertypath in g.objects(prop, SH.path):
                        yield {'nodeshape': nodeshape, 'targetclass': targetclass,
                               'inheritedTargetclass': inherited_class,
                               'property': prop, 'propertypath': propertypath}


OUTER_UNION = ('connective', 'outerOr', 'clause', 'ownparams')
INNER_UNION = ('valuepath', 'innerconnective', 'innerOr', 'innerclause')


def _outer_clauses(g, row):
    """The UNION that binds ?clause: a member of the property's connective, the
    shape under its sh:not, or -- with its own parameters -- the property itself."""
    return _distinct(_outer_arms(g, row), OUTER_UNION)


def _outer_arms(g, row):
    prop = row['property']
    for connective in LIST_CONNECTIVES:
        for outer in g.objects(prop, connective):
            for clause in _objects(g, outer, MEMBERS):
                yield {**row, 'connective': connective, 'outerOr': outer, 'clause': clause}
    for clause in g.objects(prop, SH['not']):
        yield {**row, 'connective': SH['not'], 'clause': clause}
    for propertypath in g.objects(prop, SH.path):
        if propertypath == row['propertypath'] and \
                any((prop, p, None) in g for p in OWN_PARAMETERS):
            yield {**row, 'clause': prop, 'ownparams': TRUE}


def _counts_and_severity(g, rows):
    """The OPTIONALs on the clause's counts and severity."""
    rows = _optional_value(rows, 'maxcount', lambda r: g.objects(r['clause'], SH.maxCount))
    rows = _optional_value(rows, 'mincount', lambda r: g.objects(r['clause'], SH.minCount))
    return _optional_value(rows, 'severitycode', lambda r: [
        label for severity in g.objects(r['clause'], SH.severity)
        for label in g.objects(severity, RDFS.label)])


def _inner_clauses(g, row, valuepaths):
    """The UNION that binds ?innerclause below a value shape ?innerProp whose
    sh:path is one of `valuepaths(innerProp)` (bound to ?valuepath when that is
    a variable of the query)."""
    return _distinct(_inner_arms(g, row, valuepaths), INNER_UNION)


def _inner_arms(g, row, valuepaths):
    inner = row['innerProp']
    for connective in LIST_CONNECTIVES:
        for valuepath in valuepaths(inner):
            for inner_or in g.objects(inner, connective):
                for clause in _objects(g, inner_or, MEMBERS):
                    yield {**row, **valuepath, 'innerconnective': connective,
                           'innerOr': inner_or, 'innerclause': clause}
    for valuepath in valuepaths(inner):
        for clause in g.objects(inner, SH['not']):
            yield {**row, **valuepath, 'innerconnective': SH['not'], 'innerclause': clause}
    for valuepath in valuepaths(inner):
        if not any((inner, p, None) in g for p in ALL_CONNECTIVES):
            yield {**row, **valuepath, 'innerclause': inner}


def _to_result_rows(rows, labels):
    names = [str(label) for label in labels]
    return [ResultRow({label: row[name] for label, name in zip(labels, names)
                       if row.get(name) is not None}, labels) for row in rows]


def relationship_rows(g, query_text):
    """The rows of `sparql_get_all_relationships` (`query_text`) over `g`."""
    labels = _projection(query_text)

    def has_object(inner):
        return [{}] if (inner, SH.path, NGSILD_HAS_OBJECT) in g else []

    def rows():
        for head in _head(g):
            for row in _counts_and_severity(g, _outer_clauses(g, head)):
                for inner in g.objects(row['clause'], SH.property):
                    yield from _optional_value(
                        _inner_clauses(g, {**row, 'innerProp': inner}, has_object),
                        'attributeclass', lambda r: g.objects(r['innerclause'], SH['class']))
    return _to_result_rows(rows(), labels)


# The value parameters of sparql_get_all_properties, in the order of its
# OPTIONALs: each is read on ?innerclause first, then on ?innerProp.
VALUE_PARAMETERS = (('minexclusive', SH.minExclusive), ('maxexclusive', SH.maxExclusive),
                    ('mininclusive', SH.minInclusive), ('maxinclusive', SH.maxInclusive),
                    ('minlength', SH.minLength), ('maxlength', SH.maxLength),
                    ('pattern', SH.pattern), ('in', IN_MEMBERS), ('hasValue', SH.hasValue),
                    ('attributeclass', SH['class']), ('nodekind', SH.nodeKind))

# GROUP BY of sparql_get_all_properties: every projected variable but the two
# aggregates.
AGGREGATES = ('ins', 'datatypes')


def _concat_in(value):
    """CONCAT('"', ?in, '"') as rdflib 7 evaluates it inside GROUP_CONCAT: a
    string literal is quoted; anything else is an error, and GROUP_CONCAT adds
    the error's message (rdflib keeps errors as values)."""
    if not isinstance(value, Literal):
        return 'Non-literal passes as string: %r' % value
    if value.datatype and value.datatype != XSD.string:
        return 'Non-string datatype-literal passes as string: %r' % value
    return f'"{value}"'


def _in_on_value_shape(g, row):
    """OPTIONAL { ?innerProp sh:in/(rdf:rest*/rdf:first)+ ?in } as rdflib 7
    evaluates it when the OPTIONAL before it has bound ?in: its path code tests
    the bound object with `not obj`, so a falsy ?in (0, false, "") matches every
    member of the value shape's sh:in and the row is repeated once per member.
    Reproduced because rdflib's rows are the reference; it only repeats entries
    of the ins and datatypes concatenations, which the SQL tests by membership."""
    bound = row.get('in')
    members = _objects(g, row['innerProp'], IN_MEMBERS)
    if bound is not None and not bound:
        return [{'in': bound} for _ in members]
    return [{'in': m} for m in members]


def _element_datatypes(g, shape):
    """?shape sh:property ?elemShape . ?elemShape sh:path ?elemPath .
    FILTER(isBlank(?elemPath)) . ?elemShape sh:datatype ?datatype ."""
    return [{'elemShape': elem, 'elemPath': path, 'datatype': datatype}
            for elem in g.objects(shape, SH.property)
            for path in g.objects(elem, SH.path) if isinstance(path, BNode)
            for datatype in g.objects(elem, SH.datatype)]


def property_rows(g, query_text):
    """The rows of `sparql_get_all_properties` (`query_text`) over `g`."""
    labels = _projection(query_text)
    group_vars = [str(v) for v in labels if str(v) not in AGGREGATES]

    def valuepaths(inner):
        return [{'valuepath': p} for p in g.objects(inner, SH.path)]

    def ungrouped():
        for head in _head(g):
            for row in _counts_and_severity(g, _outer_clauses(g, head)):
                for inner in g.objects(row['clause'], SH.property):
                    rows = (r for r in _inner_clauses(g, {**row, 'innerProp': inner}, valuepaths)
                            if r['valuepath'] in NGSILD_VALUE_PATHS)
                    for var, path in VALUE_PARAMETERS:
                        rows = _optional_value(rows, var, lambda r, p=path: _objects(g, r['innerclause'], p))
                        if var == 'in':
                            rows = _optional(rows, lambda r: _in_on_value_shape(g, r))
                        else:
                            rows = _optional_value(rows, var, lambda r, p=path: _objects(g, r['innerProp'], p))
                    rows = _optional(rows, lambda r: [
                        {'dtShape': m, 'datatype': d} for m in _objects(g, r['innerclause'], OR_MEMBERS)
                        for d in g.objects(m, SH.datatype)])
                    rows = _optional(rows, lambda r: [
                        {'dtShape': m, 'datatype': d} for m in _objects(g, r['innerclause'], PROPERTY_OR_MEMBERS)
                        for d in g.objects(m, SH.datatype)])
                    rows = _optional_value(rows, 'datatype', lambda r: g.objects(r['innerclause'], SH.datatype))
                    rows = _optional_value(rows, 'datatype', lambda r: g.objects(r['innerProp'], SH.datatype))
                    rows = _optional(rows, lambda r: _element_datatypes(g, r['innerclause']))
                    rows = _optional(rows, lambda r: _element_datatypes(g, r['innerProp']))
                    yield from rows

    groups = {}
    for row in ungrouped():
        key = tuple(row.get(v) for v in group_vars)
        group = groups.get(key)
        if group is None:
            group = groups[key] = {'row': {v: row.get(v) for v in group_vars}, 'ins': [], 'datatypes': []}
        if row.get('in') is not None:
            group['ins'].append(_concat_in(row['in']))
        if row.get('datatype') is not None:
            group['datatypes'].append(str(row['datatype']))
    result = []
    for group in groups.values():
        row = dict(group['row'])
        # Sorted: SPARQL leaves the order of GROUP_CONCAT undefined, and
        # rdflib's depends on Python's string hashing, so the same shapes gave
        # "integer,double" in one build and "double,integer" in the next. The
        # generated SQL only tests membership (LIKE), so the order carries no
        # meaning; sorting makes it a function of the shapes.
        row['ins'] = Literal(','.join(sorted(group['ins'])))
        row['datatypes'] = Literal(','.join(sorted(group['datatypes'])))
        result.append(row)
    return _to_result_rows(result, labels)
