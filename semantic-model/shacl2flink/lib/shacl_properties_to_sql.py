from rdflib import Graph, RDF, BNode
from rdflib.collection import Collection
from rdflib.namespace import SH
import os
import re
import ruamel.yaml
from jinja2 import Template
from lib.utils import get_full_path_of_shacl_property, NGSILD, UnsupportedShape

import lib.configs as configs
import lib.utils as utils


MAX_SUBPROPERTY_DEPTH = utils.MAX_SUBPROPERTY_DEPTH
# Join aliases for the attribute chain, outermost first. B and E are what the
# first two levels have always been called, so a two-level model's generated
# SQL keeps the same shape.
ATTRIBUTE_ALIASES = ('B', 'E', 'F', 'G', 'H', 'I', 'J', 'K')


def shape_message(g, shape):
    """
    The sh:message a shape gives for its own violations, if any.

    SHACL lets an author replace the generated explanation. Only the shape's
    own message is used -- a message on a nested value shape explains that
    shape, not this one. sh:node resolution copies a referenced shape's message
    onto the referring node, which is how the OPC UA ValueRank messages arrive
    here.
    """
    message = g.value(shape, SH.message)
    return str(message) if message is not None else None


def set_attribute_path(check, paths, property_path):
    """
    Spread an attribute path across the constraint's path columns.

    `paths` runs innermost-first, the columns outermost-first, and the columns
    beyond this constraint's own depth stay NULL -- which is what makes the
    deeper joins fall through for it.
    """
    chain = [property_path] + list(paths[1:])
    for column, path in zip(utils.path_columns(), reversed(chain)):
        check[column] = path


def attribute_level_context(filter_deleted=False):
    """
    The SQL that walks an entity down to the attribute a constraint is about.

    Attribute nesting is resolved by one LEFT JOIN of attributes_view per
    level, each hanging off the previous one's id. That join chain was written
    out by hand for exactly two levels, which is the only reason a third was
    rejected -- nothing about the semantics stops at two. Generating it means
    the depth limit is a number rather than a rewrite.

    A constraint declares its own depth by leaving the deeper path columns
    NULL: `name = NULL` never matches, so the unused joins contribute nothing
    and the COALESCEs fall through to the deepest level that did match.
    """
    columns = utils.path_columns()
    aliases = ATTRIBUTE_ALIASES[:len(columns)]

    def deepest(column):
        """
        The attribute at the constraint's DECLARED depth -- not the deepest
        join that happened to match.

        COALESCE(F, E, B) reads the innermost row that exists, so a constraint
        naming a sub-attribute silently fell back to the PARENT's values when
        that sub-attribute was absent. A1 compensated by refusing such rows
        outright, which made a missing sub-attribute invisible -- and a
        sh:minCount on one could never fire, which is the case it exists to
        catch.

        Selecting by declared depth instead lets the row through with NULLs.
        Every value check is guarded on `index`/`attr_typ` being non-NULL, so
        none of them fire on it; the count checks have no such guard and see
        the zero they are supposed to see.
        """
        if len(aliases) <= 1:
            return f'{aliases[0]}.`{column}`' if aliases else f'`{column}`'
        branches = ' '.join(
            f'WHEN D.`{columns[level]}` IS NOT NULL THEN {aliases[level]}.`{column}`'
            for level in range(len(columns) - 1, 0, -1))
        return f'CASE {branches} ELSE {aliases[0]}.`{column}` END'

    def dataset_index(expression):
        return (f"CASE WHEN {expression} = '@none' THEN '0' "
                f"ELSE {expression} END")

    joins = []
    for level, (column, alias) in enumerate(zip(columns, aliases)):
        parent = 'IS NULL' if level == 0 else f'= {aliases[level - 1]}.id'
        deleted = f' and COALESCE({alias}.`deleted`, false) = false' \
            if filter_deleted else ''
        joins.append(
            f'LEFT JOIN attributes_view AS {alias} ON D.`{column}` = {alias}.name '
            f'and {alias}.entityId = A.id and {alias}.parentId {parent}{deleted}')

    value_paths = ', '.join(f"'{path}'" for path in sorted(VALUE_PATH_ATTRIBUTE_TYPES))

    effective_path = 'COALESCE(' + ', '.join(
        f'D.`{column}`' for column in reversed(columns)) + ')'

    # Every level above the innermost one, rendered as `path[index] ==> `. A
    # level is part of the parent path only when a deeper one exists.
    parent_path = ' || '.join(
        f"CASE WHEN D.`{columns[level + 1]}` IS NULL THEN '' "
        f"ELSE D.`{columns[level]}` || '[' || "
        f"{dataset_index(f'{aliases[level]}.`datasetId`')} || '] ==> ' END"
        for level in range(len(columns) - 1))

    return {
        'attribute_joins': '\n            '.join(joins),
        'deepest': deepest,
        'effective_path': effective_path,
        'parent_path': parent_path,
        'print_path': f"{effective_path} || '[' || "
                      f"{dataset_index(deepest('datasetId'))} || ']'",
        # An absent sub-ATTRIBUTE must still yield a row when its PARENT is
        # present -- that is exactly what a sh:minCount on it has to see, and
        # requiring the join to match made the violation invisible.
        #
        # Two cases must stay excluded. If the parent is absent there are no
        # value nodes for the child to be missing from, so the parent's own
        # count owns that failure and firing here would double-report it. And
        # a value PATH names how to read the parent's value, never a row of
        # its own, so its join can never match and a count over it would
        # report every conforming attribute as missing.
        'level_guard': ' and '.join(
            f'(D.`{columns[level]}` IS NULL or {aliases[level]}.id is not NULL'
            f' or ({aliases[level - 1]}.id is not NULL'
            f' and D.`{columns[level]}` NOT IN ({value_paths})))'
            for level in range(1, len(columns))) or 'true',
    }


# Distinguishes a property node's own parameters from the members of a
# connective on the same node, so the two never land in the same circuit group.
OWN_PARAMS_SUFFIX = '#ownparams'
# SHACL names its logical constraint components this way, and every leaf alert
# is already <sourceConstraintComponent>(<resultPath>). Circuit nodes were the
# one place that departed from it, by substituting a build artifact.
CONNECTIVE_COMPONENTS = {'OR': 'OrConstraintComponent',
                         'AND': 'AndConstraintComponent',
                         'XONE': 'XoneConstraintComponent',
                         'NOT': 'NotConstraintComponent'}


def circuit_event_name(operation, focus):
    """
    Stable identity for a circuit node's alert.

    Derived from the operator and what it constrains, never from the
    constraint id: ids are positional, so inserting one shape renumbered
    every alert after it. The alert key is what Alerta resolves against, so a
    rename leaves the old alert with no producer to clear it.

    Deliberately independent of the constraint's CONTENTS, which makes it more
    stable than a hash would be -- retuning sh:minInclusive keeps the name, and
    keeps the alert.
    """
    component = CONNECTIVE_COMPONENTS.get(operation, 'LogicalConstraintComponent')
    # A blank node is not a name: its id is a parser artifact and changes
    # between runs, so it would be worse than no discriminator at all.
    if focus is None or isinstance(focus, BNode):
        return component
    return f'{component}({focus})'


# Connectives that can fire when NONE of their members fired. These cannot be
# evaluated from the (sparse) trigger rows alone and need the focus-node
# universe re-joined. OR and AND are monotone and do not.
ABSENCE_FIRING_OPERATIONS = ('NOT', 'XONE')

# sh:or, sh:and and sh:xone all take an RDF list of shapes, so the extraction
# pattern is shared and ?connective says which one matched.
CONNECTIVE_OPERATION = {
    str(SH['or']): 'OR',
    str(SH['and']): 'AND',
    str(SH.xone): 'XONE',
    str(SH['not']): 'NOT',
}


def connective_operation(connective):
    """Map a SHACL connective predicate onto a circuit operation."""
    if connective is None:
        return 'OR'
    return CONNECTIVE_OPERATION.get(str(connective), 'OR')


yaml = ruamel.yaml.YAML()

alerts_bulk_table = configs.alerts_bulk_table_name
alerts_bulk_table_object = configs.alerts_bulk_table_object_name
constraint_table_name = configs.constraint_table_name
constraint_trigger_table_name = configs.constraint_trigger_table_name
constraint_combination_table_name = configs.constraint_combination_table_name

sparql_get_all_relationships = """
SELECT ?nodeshape ?targetclass ?inheritedTargetclass ?propertypath ?mincount ?maxcount ?attributeclass ?severitycode ?property ?innerOr ?connective ?ownparams ?clause ?innerconnective
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?inheritedTargetclass rdfs:subClassOf* ?targetclass .
    ?nodeshape (sh:property|(sh:or|sh:and|sh:xone)/rdf:rest*/rdf:first|sh:not)+ ?property .
    ?property sh:path ?propertypath .
    { VALUES ?connective { sh:or sh:and sh:xone }
      ?property ?connective ?outerOr .
      ?outerOr rdf:rest*/rdf:first ?clause . }
    UNION
    { BIND(sh:not AS ?connective)
      ?property sh:not ?clause . }
    UNION
    ## No connective: the property node IS the clause. See the note in
    ## sparql_get_all_properties.
    { ?property sh:path ?propertypath .
      FILTER EXISTS { ?property (sh:minCount|sh:maxCount|sh:nodeKind|sh:property) ?ownparam }
      BIND(?property AS ?clause)
      BIND(true AS ?ownparams) }
        OPTIONAL{?clause sh:maxCount ?maxcount ; }
        OPTIONAL{?clause sh:minCount ?mincount ; }
        OPTIONAL{?clause sh:severity ?severity . ?severity rdfs:label ?severitycode .}
        ?clause     sh:property    ?innerProp .
        { VALUES ?innerconnective { sh:or sh:and sh:xone }
          ?innerProp sh:path ngsi-ld:hasObject ;
              ?innerconnective   ?innerOr .
          ?innerOr rdf:rest*/rdf:first ?innerclause . }
        UNION
        { BIND(sh:not AS ?innerconnective)
          ?innerProp sh:path ngsi-ld:hasObject ;
              sh:not ?innerclause . }
        UNION
        { ?innerProp sh:path ngsi-ld:hasObject .
          FILTER NOT EXISTS { ?innerProp (sh:or|sh:and|sh:xone|sh:not) ?anyinnerconnective }
          BIND(?innerProp AS ?innerclause) }
        OPTIONAL { ?innerclause sh:class ?attributeclass ; }
}
order by ?inhertiedTargetclass
"""  # noqa: E501

sparql_get_all_properties = """
SELECT
    ?nodeshape ?targetclass ?inheritedTargetclass ?propertypath ?mincount ?maxcount ?attributeclass ?nodekind
    ?minexclusive ?maxexclusive ?mininclusive ?maxinclusive ?minlength ?maxlength ?pattern ?severitycode ?property ?valuepath ?innerOr ?hasValue ?connective ?ownparams ?clause ?innerconnective
    (GROUP_CONCAT(CONCAT('"', ?in, '"'); separator=',') as ?ins)
    (GROUP_CONCAT(?datatype; separator=',') as ?datatypes)
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?inheritedTargetclass rdfs:subClassOf* ?targetclass .
    ?nodeshape (sh:property|(sh:or|sh:and|sh:xone)/rdf:rest*/rdf:first|sh:not)+ ?property .
      ## First-level property. sh:or, sh:and and sh:xone are all an RDF list of
      ## shapes, so one pattern covers them; ?connective carries which it was.
  ?property sh:path ?propertypath .
    { VALUES ?connective { sh:or sh:and sh:xone }
      ?property ?connective ?outerOr .
      ?outerOr rdf:rest*/rdf:first ?clause . }
    UNION
    { BIND(sh:not AS ?connective)
      ?property sh:not ?clause . }
    UNION
    ## The property node's OWN parameters. They are conjoined with any
    ## connective, never a member of it, so they are collected under a separate
    ## group (?ownparams) and published as an independent constraint. When there
    ## is no connective at all this is the only arm that matches, and the node
    ## simply IS the clause -- which is what a shape looks like as written. The
    ## former normalisation pass existed only to wrap that in a singleton sh:or
    ## so the two patterns above could match it.
    ## NOTE: ?property must be re-bound INSIDE the arm. UNION arms are evaluated
    ## independently of the patterns preceding them, so a FILTER here would
    ## otherwise see ?property unbound and match every triple in the graph.
    { ?property sh:path ?propertypath .
      FILTER EXISTS { ?property (sh:minCount|sh:maxCount|sh:nodeKind|sh:property) ?ownparam }
      BIND(?property AS ?clause)
      BIND(true AS ?ownparams) }
    OPTIONAL { ?clause  sh:minCount ?mincount ; }
    OPTIONAL { ?clause sh:maxCount ?maxcount ; }
    OPTIONAL { ?clause sh:severity ?severity . ?severity rdfs:label ?severitycode .}
    ?clause     sh:property    ?innerProp .
    ## Same three cases again one level down, for the value shape. Its
    ## connective gets its own circuit node rather than being folded into the
    ## property's -- see the two-level grouping in translate().
    { VALUES ?innerconnective { sh:or sh:and sh:xone }
      ?innerProp sh:path ?valuepath ;
          ?innerconnective   ?innerOr .
      ?innerOr rdf:rest*/rdf:first ?innerclause . }
    UNION
    { BIND(sh:not AS ?innerconnective)
      ?innerProp sh:path ?valuepath ;
          sh:not ?innerclause . }
    UNION
    { ?innerProp sh:path ?valuepath .
      FILTER NOT EXISTS { ?innerProp (sh:or|sh:and|sh:xone|sh:not) ?anyinnerconnective }
      BIND(?innerProp AS ?innerclause) }
    FILTER(?valuepath = ngsi-ld:hasValue || ?valuepath = ngsi-ld:hasValueList || ?valuepath = ngsi-ld:hasJSON)
    ## Value parameters may sit on the value shape itself or on the branch of a
    ## connective inside it -- `sh:nodeKind sh:Literal` beside `sh:or (datatype
    ## a) (datatype b)` is the common case. Both are read: the branch binds
    ## first and the value shape fills in whatever the branch did not set, so a
    ## parameter written next to a connective is never lost.
    OPTIONAL { ?innerclause sh:minExclusive ?minexclusive ; }
    OPTIONAL { ?innerProp   sh:minExclusive ?minexclusive ; }
    OPTIONAL { ?innerclause sh:maxExclusive ?maxexclusive ; }
    OPTIONAL { ?innerProp   sh:maxExclusive ?maxexclusive ; }
    OPTIONAL { ?innerclause sh:minInclusive ?mininclusive ; }
    OPTIONAL { ?innerProp   sh:minInclusive ?mininclusive ; }
    OPTIONAL { ?innerclause sh:maxInclusive ?maxinclusive ; }
    OPTIONAL { ?innerProp   sh:maxInclusive ?maxinclusive ; }
    OPTIONAL { ?innerclause sh:minLength ?minlength ; }
    OPTIONAL { ?innerProp   sh:minLength ?minlength ; }
    OPTIONAL { ?innerclause sh:maxLength ?maxlength ; }
    OPTIONAL { ?innerProp   sh:maxLength ?maxlength ; }
    OPTIONAL { ?innerclause sh:pattern ?pattern ; }
    OPTIONAL { ?innerProp   sh:pattern ?pattern ; }
    OPTIONAL { ?innerclause sh:in/(rdf:rest*/rdf:first)+ ?in ; }
    OPTIONAL { ?innerProp   sh:in/(rdf:rest*/rdf:first)+ ?in ; }
    OPTIONAL { ?innerclause sh:hasValue ?hasValue ; }
    OPTIONAL { ?innerProp   sh:hasValue ?hasValue ; }
    OPTIONAL { ?innerclause sh:class ?attributeclass ; }
    OPTIONAL { ?innerProp   sh:class ?attributeclass ; }
    OPTIONAL { ?innerclause sh:nodeKind ?nodekind ; }
    OPTIONAL { ?innerProp   sh:nodeKind ?nodekind ; }
    OPTIONAL { ?innerclause sh:or/rdf:rest*/rdf:first ?dtShape  . ?dtShape sh:datatype ?datatype .}
    OPTIONAL { ?innerclause sh:property/sh:or/rdf:rest*/rdf:first ?dtShape  . ?dtShape sh:datatype ?datatype .}
    OPTIONAL { ?innerclause sh:datatype ?datatype ; }
    OPTIONAL { ?innerProp   sh:datatype ?datatype ; }
    ## The datatype of a LIST ELEMENT. It sits on a nested sh:property whose
    ## sh:path is a path EXPRESSION -- ([sh:zeroOrMorePath rdf:rest] rdf:first)
    ## -- rather than a plain predicate, which is what distinguishes it from a
    ## sub-attribute. Without these two arms the element datatype never reached
    ## constraint_table at all, so "a list of integers" compiled to "is a JSON
    ## array" and a list of strings satisfied it.
    OPTIONAL { ?innerclause sh:property ?elemShape . ?elemShape sh:path ?elemPath .
               FILTER(isBlank(?elemPath)) . ?elemShape sh:datatype ?datatype . }
    OPTIONAL { ?innerProp   sh:property ?elemShape . ?elemShape sh:path ?elemPath .
               FILTER(isBlank(?elemPath)) . ?elemShape sh:datatype ?datatype . }
}
GROUP BY ?nodeshape ?targetclass ?propertypath ?mincount ?maxcount ?attributeclass ?nodekind
    ?minexclusive ?maxexclusive ?mininclusive ?maxinclusive ?minlength ?maxlength ?pattern ?severitycode ?inheritedTargetclass ?property ?valuepath ?innerOr ?hasValue ?connective ?ownparams ?clause ?innerconnective
order by ?inheritedTargetclass
"""  # noqa: E501
sql_check_relationship_base = """
            INSERT {% if sqlite %}OR REPlACE{% endif %} INTO {{alerts_bulk_table}}
            WITH A1 as (
                    SELECT /*+ STATE_TTL('D' = '0d') */ A.id AS this,
                        A.`type` as typ,
                        -- Deleted entities stay in A1 and carry the flag, so
                        -- that a count of zero can be told apart from an
                        -- entity that is gone. Read it in the value checks
                        -- directly and in the counts as an aggregate -- never
                        -- as a grouping key. See
                        -- sql_check_relationship_property_count.
                        IFNULL(A.`deleted`, false) as edeleted,
                        C.`type` AS entity,
                        G.subject AS foundClass,
                        {{ deepest('type') }} AS link,
                        {{ deepest('nodeType') }} as nodeType,
                        {{ deepest('deleted') }} as `adeleted`,
                        {{ deepest('datasetId') }} as `index`,
                        D.targetClass as targetClass,
                        {{ effective_path }} as propertyPath,
                        {{ parent_path }} as parentPath,
                        {{ print_path }} as printPath,
                        D.propertyClass as propertyClass,
                        D.attributeType as attributeType,
                        D.maxCount as maxCount,
                        D.minCount as minCount,
                        D.severity as severity,
                        D.id as constraint_id
                    FROM {{target_class}}_view AS A JOIN {{constraint_table}} as D ON A.`type` = D.targetClass
            {{ attribute_joins }}
                    LEFT JOIN {{target_class}}_view AS C ON {{ deepest('attributeValue') }} = C.id and COALESCE(C.`deleted`, false) = false
                    -- The target's CLASS, not merely its existence. C alone
                    -- answers "does the referenced entity exist", which is a
                    -- weaker question than sh:class asks: a relationship
                    -- pointing at an entity that exists but is of the wrong
                    -- class satisfied the check, because `entity` was
                    -- non-null. The knowledge closure materialises
                    -- rdfs:subClassOf transitively, so one lookup decides
                    -- whether the target's type IS the required class or a
                    -- subclass of it, and inheritance keeps working.
                    LEFT JOIN {{rdf_table_name}} as G ON G.subject = '<' || C.`type` || '>'
                        and G.predicate = '<http://www.w3.org/2000/01/rdf-schema#subClassOf>'
                        and G.object = '<' || D.propertyClass || '>'
                    WHERE {{ level_guard }} and D.attributeType = 'https://uri.etsi.org/ngsi-ld/Relationship'
            )
"""  # noqa: E501

sql_check_relationship_property_class = """
            {% set constraint_cond%}
            NOT edeleted AND NOT IFNULL(adeleted, false) AND link IS NOT NULL
            AND (entity IS NULL OR (entity <> propertyClass AND foundClass IS NULL))
            {% endset %}
            SELECT this AS resource,
                'ClassConstraintComponent(' || `parentPath` || `printPath` || ')' AS event,
                `constraint_id` as constraint_id,
                true as triggered,
                `severity` AS severity,
                'Model validation for relationship ' || `propertyPath` || ' failed for '|| this || '. Relationship not linked to existing entity of type ' ||  `propertyClass` || '.'
                    as `text`
                {%- if sqlite %}
                ,CURRENT_TIMESTAMP
                {%- endif %}
            FROM A1 WHERE A1.propertyClass IS NOT NULL and `index` IS NOT NULL and {{ constraint_cond }}
"""  # noqa: E501

# A count of zero means two different things and the count alone cannot tell
# them apart: an entity that is alive and has lost its mandatory attribute MUST
# alert, and an entity that has been deleted MUST NOT. Only `edeleted`
# separates them, so the check has to read it.
#
# It must not be a GROUPING KEY, which is how it was written originally: on
# Flink a deleted entity then MIGRATES its rows from group (id, false) to group
# (id, true) rather than emptying the first, and muting the new group says
# nothing about the old one. That group is only retracted once every row it
# holds is retracted, and an hour of state TTL is enough for those retractions
# to stop arriving, so the alert outlives the entity. Worse, a retraction
# landing in a group whose accumulator was rebuilt from fewer rows drives the
# SUM NEGATIVE and the entity is reported as having "-1 relationships" -- a
# value this expression cannot produce in batch, which is why the SQLite oracle
# agreed throughout.
#
# Filtering deleted entities out of A1 instead was worse still, because it made
# correctness depend on the rows DISAPPEARING and a retraction propagating
# through a LEFT JOIN and a COUNT(DISTINCT). Measured: deleting the kms model in
# Scorpio raised thirteen CountConstraint alerts that never cleared, with every
# row-level check -- all of which carry `NOT edeleted` -- correctly silent. The
# attributes were gone and the count went on being evaluated for the entity.
#
# So: read `edeleted`, but as an AGGREGATE in the HAVING. The group is keyed the
# same whether the entity is alive or deleted, so nothing migrates and no
# accumulator is rebuilt; and the alert is suppressed by re-evaluating the same
# group rather than by waiting for its rows to vanish.
#
# It has to be read INSIDE the counted expression as well, not only in the
# HAVING. The HAVING decides whether to report; the CASE decides what is
# counted. With rows for a deleted incarnation left in A1 and only `adeleted`
# tested, those rows went on contributing to the SUM, and deleting a model and
# reinstalling it under the same ids reported "Found 2 relationships" for
# relationships that exist exactly once -- measured on hasCartridge, hasFilter
# and hasXXXWorkpiece, where tsdb held a single row per attribute. A count must
# count live data only.
sql_check_relationship_property_count = """
            {% set constraint_cond %}
            (MAX(CASE WHEN edeleted THEN 1 ELSE 0 END) = 0 AND
            (SUM(CASE WHEN NOT edeleted AND NOT COALESCE(adeleted, FALSE) AND link IS NOT NULL THEN 1 ELSE 0 END) > SQL_DIALECT_CAST(`maxCount` AS INTEGER)
                                            OR SUM(CASE WHEN NOT edeleted AND NOT COALESCE(adeleted, FALSE) AND link IS NOT NULL THEN 1 ELSE 0 END) < SQL_DIALECT_CAST(`minCount` AS INTEGER)))
            {% endset %}
            SELECT this AS resource,
                'CountConstraintComponent(' || `parentPath` || `propertyPath` || ')' AS event,
                `constraint_id` as constraint_id,
                true as triggered,
                `severity` AS severity,
               'Model validation for relationship ' || `propertyPath` || ' failed for ' || this || '. Found ' ||
                            SQL_DIALECT_CAST(SUM(CASE WHEN NOT edeleted AND NOT COALESCE(adeleted, FALSE) AND link IS NOT NULL THEN 1 ELSE 0 END) AS STRING) || ' relationships instead of [' || IFNULL(`minCount`, '0') || ', ' || IFNULL(`maxCount`, '*') || ']!'
                    as `text`
                {%- if sqlite %}
                ,CURRENT_TIMESTAMP
                {%- endif %}
            FROM A1 WHERE `minCount` is NOT NULL or `maxCount` is NOT NULL
            GROUP BY this, propertyPath, maxCount, minCount, severity, constraint_id, parentPath
            HAVING {{ constraint_cond }}
"""  # noqa: E501

sql_check_relationship_nodeType = """
            {% set constraint_cond %}
            NOT edeleted AND NOT IFNULL(`adeleted`, false) AND (nodeType <> '{{ property_nodetype }}'  OR link <> attributeType)
            {% endset %}
            SELECT this AS resource,
                'NodeKindConstraintComponent(' || `parentPath` || `printPath` || ')' AS event,
                `constraint_id` as constraint_id,
                true as triggered,
                `severity` AS severity,
                'Model validation for relationship ' || `propertyPath` || ' failed for ' || this || '. Either NodeType '|| nodeType || ' is not an IRI or type is not a Relationship.'
                    as `text`
                {%- if sqlite %}
                ,CURRENT_TIMESTAMP
                {%- endif %}
            FROM A1 WHERE `index` IS NOT NULL AND {{ constraint_cond }}
"""  # noqa: E501

sql_check_property_iri_base = """
INSERT {% if sqlite %} OR REPlACE{% endif %} INTO {{alerts_bulk_table}}
WITH A1 AS (SELECT /*+ STATE_TTL('D' = '0d', 'C' = '0d') */ A.id as this,
                   A.`type` as typ,
                   -- Carried, not filtered; see sql_check_relationship_base.
                   IFNULL(A.`deleted`, false) as edeleted,
                   {{ deepest('attributeValue') }} as val,
                   {{ deepest('nodeType') }} as nodeType,
                   {{ deepest('type') }} as attr_typ,
                   {{ deepest('deleted') }} as `adeleted`,
                   {{ deepest('valueType') }} as `valueType`,
                   C.subject as foundVal,
                   C.object as foundClass,
                   {{ deepest('datasetId') }} as `index`,
                   {{ effective_path }} as propertyPath,
                   {{ parent_path }} as parentPath,
                   {{ print_path }} as printPath,
                   D.propertyClass as propertyClass,
                   IFNULL(D.propertyNodetype, 'null') as propertyNodetype,
                   D.attributeType as attributeType,
                   D.maxCount as maxCount,
                   D.minCount as minCount,
                   D.severity as severity,
                   D.minExclusive as minExclusive,
                   D.maxExclusive as maxExclusive,
                   D.minInclusive as minInclusive,
                   D.maxInclusive as maxInclusive,
                   D.minLength as minLength,
                   D.maxLength as maxLength,
                   D.`pattern` as `pattern`,
                   D.ins as ins,
                   D.datatypes as datatypes,
                   D.hasValue as hasValue,
                   D.id as constraint_id
                   FROM `{{target_class}}_view` AS A JOIN {{constraint_table}} as D ON A.`type` = D.targetClass
            {{ attribute_joins }}
            LEFT JOIN {{rdf_table_name}} as C ON C.subject = '<' || {{ deepest('attributeValue') }} || '>'
                and C.predicate = '<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>' and C.object = '<' || D.propertyClass || '>'
             WHERE {{ level_guard }} and (attributeType IS NULL or attributeType IN ('https://uri.etsi.org/ngsi-ld/Property', 'https://uri.etsi.org/ngsi-ld/ListProperty', 'https://uri.etsi.org/ngsi-ld/JsonProperty'))
            )
"""  # noqa: E501

# `edeleted` is read as an aggregate here too, and is not a grouping key -- see
# sql_check_relationship_property_count for what both alternatives cost.
#
# The count is COUNT(DISTINCT `index`) -- the number of distinct datasetIds
# carrying a live attribute, which IS the number of instances, an NGSI-LD
# attribute being (entity, name, datasetId).
#
# It used to be SUM(DISTINCT CASE WHEN ... THEN 1 ELSE 0 END). Every term of
# that is 0 or 1, and summing the DISTINCT values of a set drawn from {0, 1}
# is at most 1 -- so the count could never exceed one however many instances
# existed, and sh:maxCount on a Property could never fire at all. It reported
# the shape as satisfied, which is why nothing noticed. Counting datasetIds
# instead also survives the join fan-out that the DISTINCT was there to
# absorb: one attribute matched by several sub-property joins still counts
# once.
sql_check_property_count = """
{%- set instance_count %}COUNT(DISTINCT CASE WHEN NOT edeleted AND NOT COALESCE(adeleted, FALSE) and attr_typ IS NOT NULL THEN `index` ELSE NULL END){% endset %}
{% set constraint_cond%}
    (MAX(CASE WHEN edeleted THEN 1 ELSE 0 END) = 0 AND
    ({{ instance_count }} > SQL_DIALECT_CAST(`maxCount` AS INTEGER)
                                    OR {{ instance_count }} < SQL_DIALECT_CAST(`minCount` AS INTEGER)))
{% endset %}
SELECT this AS resource,
    'CountConstraintComponent(' || `parentPath` || `propertyPath` || ')' AS event,
    `constraint_id` as constraint_id,
    true as triggered,
    `severity` AS severity,
   'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Found ' ||
                            SQL_DIALECT_CAST({{ instance_count }} AS STRING) || ' properties instead of [' || IFNULL(`minCount`, '0') || ', ' || IFNULL(`maxCount`, '*') || ']!'
        as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1  WHERE `minCount` is NOT NULL or `maxCount` is NOT NULL
GROUP BY this, typ, propertyPath, minCount, maxCount, severity, constraint_id, parentPath
HAVING {{ constraint_cond }}
"""  # noqa: E501

sql_check_property_iri_class = """
{% set constraint_cond%}
NOT edeleted AND attr_typ IS NOT NULL AND NOT IFNULL(adeleted, false) AND (val is NULL OR foundVal is NULL)
{% endset %}

SELECT this AS resource,
    'ClassConstraintComponent(' || `parentPath` || `printPath` || ')' AS event,
    `constraint_id` as constraint_id,
    true as triggered,
    `severity` AS severity,
    'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Invalid value ' || IFNULL(val, 'NULL')  || ' not type of ' || `propertyClass` || '.'
        as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1  WHERE propertyNodetype = '@id' and propertyClass IS NOT NULL and `index` IS NOT NULL AND {{ constraint_cond }}
"""  # noqa: E501

sql_check_property_nodeType = """
{% set constraint_cond%}
NOT edeleted AND NOT IFNULL(adeleted, false)
  AND (nodeType <> `propertyNodetype` OR attr_typ <> attributeType)
{% endset %}
SELECT this AS resource,
    'NodeKindConstraintComponent(' || `parentPath` || `printPath` || ')' AS event,
    `constraint_id` as constraint_id,
    true as triggered,
    `severity` AS severity,
    'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Node is not ' ||
            'of nodetype "' || `nodeType` || '" or not of attribute type "' || attributeType || '"'
        as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
-- A1 coerces a NULL propertyNodetype to the STRING 'null' (see the IFNULL in
-- sql_check_property_iri_base), so `IS NOT NULL` never excludes anything here.
-- A constraint that spans attribute types -- e.g. a count beneath an
-- sh:or(hasValue, hasValueList) -- carries no nodeKind at all, and comparing a
-- real nodeType against the sentinel reported every valid value as a NodeKind
-- violation. Test against the sentinel, not against NULL.
FROM A1 WHERE `propertyNodetype` <> 'null' and `index` IS NOT NULL AND {{ constraint_cond }}
"""  # noqa: E501

sql_check_property_minmax = """
-- Comparability is decided by the lexical form, not by the declared type, and
-- that is deliberate. SHACL compares with the SPARQL operators, where a string
-- and a number are incomparable and the bound counts as violated; pyshacl
-- reports eight such violations in test5 that we do not. But NGSI-LD payloads
-- carry numbers as JSON strings all the time -- height "100", weight "10000"
-- in the kms models -- and reading the declared type strictly would raise a
-- range violation on ordinary data. A value that parses as a number is
-- compared as one. See tests/pyshacl-compare/expected-divergences.txt.
{% set constraint_cond%}
NOT edeleted AND NOT IFNULL(adeleted, false) AND attr_typ IS NOT NULL AND (SQL_DIALECT_CAST(val AS DOUBLE) is NULL or NOT (SQL_DIALECT_CAST(val as DOUBLE) {{ operator }} SQL_DIALECT_CAST(`{{ comparison_value }}` AS DOUBLE)) )
{% endset %}
{% set constraint_cond2%}
typ IS NOT NULL AND attr_typ IS NOT NULL AND NOT (SQL_DIALECT_CAST(val as DOUBLE) {{ operator }} SQL_DIALECT_CAST( `{{ comparison_value }}` as DOUBLE) )
{% endset %}
SELECT this AS resource,
 '{{minmaxname}}ConstraintComponent(' || `parentPath` || `printPath` || ')' AS event,
    `constraint_id` as constraint_id,
    true as triggered,
    `severity` AS severity,
    CASE WHEN {{ constraint_cond }}
        THEN 'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Value ' || IFNULL(val, 'NULL') || ' not comparable with ' || `{{ comparison_value }}` || '.'
        WHEN {{ constraint_cond2}}
        THEN 'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Value ' || IFNULL(val, 'NULL') || ' is not {{ operator }} ' || `{{ comparison_value }}` || '.'
        END as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1 where `{{ comparison_value}}` IS NOT NULL and `index` IS NOT NULL AND ({{ constraint_cond }} OR {{ constraint_cond2 }})
"""  # noqa: E501

sql_check_string_length = """
{% set constraint_cond%}
NOT edeleted  AND NOT IFNULL(adeleted, false) AND attr_typ IS NOT NULL AND {%- if sqlite %} LENGTH(val) {%- else  %} CHAR_LENGTH(val) {%- endif %} {{ operator }} SQL_DIALECT_CAST(`{{ comparison_value }}` AS INTEGER)
{% endset %}
SELECT this AS resource,
 '{{minmaxname}}ConstraintComponent(' || `parentPath` || `printPath` || ')' AS event,
    `constraint_id` as constraint_id,
    true as triggered,
    `severity` AS severity,
    'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Length of ' || IFNULL(val, 'NULL') || ' is {{ operator }} ' || `{{ comparison_value }}` || '.'
         as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1 WHERE `{{ comparison_value }}` IS NOT NULL and `index` IS NOT NULL AND {{ constraint_cond }}
"""  # noqa: E501

sql_check_literal_pattern = """
{% set constraint_cond%}
NOT edeleted AND NOT IFNULL(adeleted, false) AND attr_typ IS NOT NULL AND {%- if sqlite %} NOT (val REGEXP `pattern`) {%- else  %} NOT REGEXP(val, `pattern`) {%- endif %}
{% endset %}
SELECT this AS resource,
 '{{validationname}}ConstraintComponent(' || `parentPath` || `printPath` || ')' AS event,
    `constraint_id` as constraint_id,
    true as triggered,
    `severity` AS severity,
    'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Value ' || IFNULL(val, 'NULL') || ' does not match pattern ' || `pattern`
         as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1 WHERE `pattern` IS NOT NULL and `index` IS NOT NULL AND {{ constraint_cond }}
"""  # noqa: E501

sql_check_literal_in = """
{% set constraint_cond%}
NOT edeleted AND NOT IFNULL(adeleted, false) AND attr_typ IS NOT NULL AND NOT ',' || `ins` || ',' LIKE '%,"' || replace(val, '"', '\\\"') || '",%'
{% endset %}
SELECT this AS resource,
 '{{constraintname}}(' || `parentPath` || `printPath` || ')' AS event,
    `constraint_id` as constraint_id,
    true as triggered,
    `severity` AS severity,
    'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Value ' || IFNULL(val, 'NULL') || ' is not allowed.'
        as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1 where `ins` IS NOT NULL and `index` IS NOT NULL AND {{ constraint_cond }}
"""  # noqa: E501

# Element datatypes for a list, matched against the serialised array. Both
# dialects emit compact JSON for a list -- json.dumps(separators=(',', ':'))
# and JSON.stringify agree -- so the elements can be matched positionally.
# `( ... )?` makes an empty list satisfy every datatype vacuously.
LIST_ELEMENT_PATTERNS = (
    ('integer', r'^\[(-?[0-9]+(,-?[0-9]+)*)?\]$'),
    ('double', r'^\[(-?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?'
               r'(,-?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?)*)?\]$'),
    ('boolean', r'^\[((true|false)(,(true|false))*)?\]$'),
    ('string', r'^\[("(\\.|[^"\\])*"(,"(\\.|[^"\\])*")*)?\]$'),
)


def list_element_checks(sqlite):
    """
    Whether every element of the serialised list matches its declared datatype.

    The argument order of REGEXP is NOT the same in both dialects, and getting
    it wrong fails silently rather than erroring. SQLite follows the SQL
    convention that `X REGEXP Y` is regexp(Y, X), so its function takes
    (pattern, subject); Flink's REGEXP(str, regex) takes (subject, pattern).
    Calling SQLite's with (subject, pattern) compiles the VALUE as a pattern,
    which for a list like ["abc","def"] is a valid character class -- so it
    matched everything and the check passed on every input.

    The scalar datatype checks and sh:pattern already branch on the dialect for
    exactly this reason; this generates the same distinction for lists.
    """
    terms = []
    for name, pattern in LIST_ELEMENT_PATTERNS:
        iri = f'http://www.w3.org/2001/XMLSchema#{name}'
        match = f"`val` REGEXP '{pattern}'" if sqlite \
            else f"REGEXP(`val`, '{pattern}')"
        terms.append(f"(datatypes LIKE '%{iri}%' AND {match})")
    return '\n    OR '.join(terms)


sql_check_literal_datatypes = r"""
{%set common_datatypes%}
(datatypes LIKE '%http://www.w3.org/2001/XMLSchema#double%' OR
 datatypes LIKE '%http://www.w3.org/2001/XMLSchema#boolean%' OR
 datatypes LIKE '%http://www.w3.org/2001/XMLSchema#integer%' OR
 datatypes LIKE '%http://www.w3.org/2001/XMLSchema#string%'
)
{%endset%}

{% set check_datatypes %}
(datatypes LIKE '%http://www.w3.org/2001/XMLSchema#double%' AND COALESCE(`valueType`, 'http://www.w3.org/2001/XMLSchema#double') = 'http://www.w3.org/2001/XMLSchema#double'
        AND {%- if sqlite %} `val`  REGEXP '^(?:0|[+-]?(?:\d+\.\d*|\.\d+|\d+(?:[eE][+-]?\d+)))$' {%- else %}
        REGEXP(val, '^(?:0|[+-]?(?:\d+\.\d*|\.\d+|\d+(?:[eE][+-]?\d+)))$') {%- endif %})
    OR (datatypes LIKE '%http://www.w3.org/2001/XMLSchema#integer%' AND COALESCE(`valueType`, 'http://www.w3.org/2001/XMLSchema#integer') = 'http://www.w3.org/2001/XMLSchema#integer'
        AND {%- if sqlite %} `val` REGEXP '^[+-]?\d+$' {%- else %}
        REGEXP(val, '^[+-]?\d+$') {%- endif %})
    OR (datatypes LIKE '%http://www.w3.org/2001/XMLSchema#boolean%' AND COALESCE(`valueType`, 'http://www.w3.org/2001/XMLSchema#boolean') = 'http://www.w3.org/2001/XMLSchema#boolean'
        AND {%- if sqlite %} `val`  REGEXP '^(?i:true|false)$' {%- else %}
        REGEXP(val, '^(?i:true|false)$'){%- endif %})
    OR (datatypes LIKE '%http://www.w3.org/2001/XMLSchema#string%' AND COALESCE(`valueType`, 'http://www.w3.org/2001/XMLSchema#string') = 'http://www.w3.org/2001/XMLSchema#string')
{%endset%}

{% set constraint_cond%}
NOT edeleted AND NOT IFNULL(adeleted, false) AND attr_typ IS NOT NULL AND
        CASE WHEN propertyNodetype = '@value' AND datatypes IS NOT NULL THEN
            CASE
                WHEN `val` IS NULL THEN true -- val cannot be NULL when a datatype is defined
                -- A datatype we cannot inspect the lexical form of is still a
                -- datatype the value has to declare. Accepting anything here
                -- let a sh:datatype naming a custom type -- iff:steelGrade --
                -- compile into a check that could never fire.
                -- Only a declared type that disagrees is a violation. A NULL
                -- valueType means the value declared none, and that is the
                -- normal case: the bridge sets valueType only when the
                -- expanded attribute carries an @type, and nothing in the
                -- live store does. Treating "undeclared" as "wrong" would
                -- alert on every value of every custom-datatype shape.
                WHEN NOT ({{ common_datatypes }}) THEN
                    datatypes NOT LIKE '%' || `valueType` || '%'
                ELSE NOT ({{ check_datatypes }}) -- if val is defined and datatypes are known, we check the value
            END
        WHEN propertyNodetype = '@json' THEN
            -- Valid JSON, not a JSON object. The shape asks for sh:datatype
            -- rdf:JSON and any JSON value satisfies that -- RFC 8259 allows a
            -- scalar at the top level, and an array is the ordinary shape of a
            -- JsonProperty. Requiring an object rejected both, which is a rule
            -- no shape ever stated.
            CASE
                WHEN {%- if sqlite %} json_valid(`val`) {%- else %} `val` IS JSON {%- endif %} THEN false
                ELSE true
            END
        WHEN propertyNodetype = '@list' THEN
            CASE
                WHEN NOT ({%- if sqlite %} json_valid(`val`) AND json_type(`val`) = 'array' {%- else %} `val` IS JSON ARRAY {%- endif %}) THEN true
                WHEN datatypes IS NULL THEN false -- a list with no element datatype declared
                WHEN NOT ({{ common_datatypes }}) THEN false -- we check only common datatypes
                ELSE NOT ({{ check_list_elements }}) -- every element must match
            END
        ELSE false -- we do not check other propertyNodetypes
        END
{% endset %}
SELECT this AS resource,
 '{{constraintname}}(' || `parentPath` || `printPath` || ')' AS event,
    `constraint_id` as constraint_id,
    true as triggered,
    `severity` AS severity,
    'Datatype check failed: ' || CASE WHEN `propertyNodetype` = '@value' THEN
        'value="' || COALESCE(`val`, 'NULL') || '", expected datatypes="' || COALESCE(`datatypes`, 'NULL')
        || '" and found datatype="' || COALESCE(`valueType`, 'NULL') || '" do not match!'  ELSE '" There is a mismatch between value "'
                                            || `val`
                                            || '", expected datatypes "'
                                            || `datatypes`
                                            || '" and '
                                            || 'property node type "'
                                            || `propertyNodetype`
                                            || '".'
        END
       as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1 where `index` IS NOT NULL AND `propertyNodetype` IN ('@value', '@list', '@json') AND ({{ constraint_cond }})
"""  # noqa: E501 W605


sql_check_literal_hasvalue = """
{% set constraint_cond %}
  /* only non-deleted entities with a value present */
  NOT edeleted AND NOT IFNULL(adeleted, false)
  AND attr_typ IS NOT NULL
  /* and the actual value <> the required hasValue constant */
  AND CASE WHEN `valueType` = 'http://www.w3.org/2001/XMLSchema#double' THEN SQL_DIALECT_CAST(val as DOUBLE) <>
        SQL_DIALECT_CAST(hasValue as DOUBLE)
    WHEN `valueType` = 'http://www.w3.org/2001/XMLSchema#integer' THEN SQL_DIALECT_CAST(val as INTEGER) <>
        SQL_DIALECT_CAST(hasValue as INTEGER)
    WHEN `valueType` = 'http://www.w3.org/2001/XMLSchema#boolean' THEN SQL_DIALECT_CAST(val as BOOLEAN) <>
        SQL_DIALECT_CAST(hasValue as BOOLEAN)
    ELSE `val` <> `hasValue`END
{% endset %}
  SELECT this           AS resource,
  'HasValueConstraintComponent('
    || parentPath
    || propertyPath
    || ')'         AS event,
  `constraint_id` as constraint_id,
  TRUE AS triggered,
  `severity` AS severity,
  'Model validation for Property '
      || propertyPath
      || ' failed for '
      || this
      || '. Value "'
      || val
      || '" does not match required "'
      || hasValue
      || '".'
    AS text
  {% if sqlite %}, CURRENT_TIMESTAMP{% endif %}
FROM A1

WHERE hasValue IS NOT NULL AND `index` IS NOT NULL AND {{ constraint_cond }}
"""

sql_insert_constraint_in_alerts = """
INSERT {% if sqlite %} OR REPlACE{% endif %} INTO {{alerts_bulk_table}}
SELECT /*+ STATE_TTL('comb' = '0d', 'ct' = '0d') */
  t.resource,
  t.event,
  'Development'                      AS environment,
    {% if sqlite %}
    '[SHACL Validator]' AS service,
    {% else %}
    ARRAY ['SHACL Validator'] AS service,
    {% endif %}

  MAX(t.severity) AS severity,
  'customer'                        AS customer,
-- sh:message replaces the generated explanation. Every alert -- leaf
-- constraint and circuit node alike -- is published by this one statement, so
-- honouring it here covers all of them. NULL means the shape gave no message
-- and the generated text stands.
 MAX(COALESCE(ct.`message`, t.text)) AS text
    {% if sqlite %}
    ,CURRENT_TIMESTAMP
    {% endif %}
FROM
  constraint_trigger_table AS t
  JOIN constraint_combination_table AS comb
    ON comb.operation = 'PUBLISH'
   AND comb.member_constraint_id = t.constraint_id
  JOIN constraint_table AS ct
    ON ct.id = comb.member_constraint_id
GROUP BY
  t.resource,
  t.event
  HAVING MAX(CASE WHEN t.triggered THEN 1 ELSE 0 END) = 1;
"""  # noqa: E501


"""
One evaluation pass over the constraint circuit.

The circuit is described by two tables: `constraint_table` carries the boolean
connective of every internal node in `operation` plus its `circuit_level`, and
`constraint_combination_table` is the edge list. This template is rendered once
per level, so an arbitrarily nested shape is evaluated by a fixed number of
non-recursive statements known at build time.

`needed_count` is always taken from the static edge list, never from observed
triggers, which is what lets leaves stay sparse and emit only violations.

Connectives that fire on the ABSENCE of a violation (NOT, XONE) additionally
need the set of focus nodes they range over, because "no member fired" is not
observable from the trigger rows alone. Those levels are rendered with
`needs_universe`, which re-joins the entity view. OR and AND are monotone --
they can only fire when at least one member fired, so the resource is always
present in the trigger table -- and are rendered without it.
"""
sql_combine_logic = """
INSERT{% if sqlite %} OR REPlACE {% endif %} INTO constraint_trigger_table
{%- set triggered_expr %}CASE f.operation
    WHEN 'OR'   THEN (f.needed_count = IFNULL(f.fired_count, 0))
    WHEN 'AND'  THEN (IFNULL(f.fired_count, 0) >= 1)
    WHEN 'NOT'  THEN (IFNULL(f.fired_count, 0) = 0)
    WHEN 'XONE' THEN ((f.needed_count - IFNULL(f.fired_count, 0)) <> 1)
  END{% endset %}
WITH
  -- 1) How many members each circuit node has. Static: from the edge list.
  needed AS (
    SELECT /*+ STATE_TTL('constraint_combination_table' = '0d') */
      target_constraint_id,
      COUNT(*) AS needed_count
    FROM
      constraint_combination_table
    WHERE
      operation <> 'PUBLISH'
    GROUP BY
      target_constraint_id
  ),

  -- 2) For each focus node and each circuit node on this level, how many
  --    distinct members actually triggered, plus their collected texts.
  fired AS (
    -- constraint_table and the needed counts are STATIC: loaded once by CDC at
    -- start and never updated. An input not named here inherits
    -- table.exec.state.ttl (an hour), so their join state expired and no
    -- entity arriving afterwards could join against them again -- the circuit
    -- nodes silently stopped producing verdicts while the leaf checks, which
    -- pin constraint_table as 'D', carried on. Connectives are exactly the
    -- constraints that cannot be expressed any other way, so losing them is
    -- invisible in the alert stream: fewer alerts looks like a healthier model.
    SELECT /*+ STATE_TTL('comb' = '0d', 'ct' = '0d', 'nm' = '0d') */
{%- if needs_universe %}
      A.id AS resource,
      ct.id AS target_constraint_id,
      ct.operation AS operation,
      ct.severity AS severity,
      nm.needed_count as needed_count,
      COUNT(DISTINCT CASE WHEN t.triggered THEN t.constraint_id ELSE NULL END) AS fired_count,
      {% if sqlite %}
      -- SQLite: GROUP_CONCAT only takes one argument when DISTINCT
      ct.`eventName` AS events,
      'AND(' || GROUP_CONCAT(DISTINCT t.text) || ')' AS texts
      {% else %}
      -- Calcite: LISTAGG without DISTINCT
      ct.`eventName` AS events,
      LISTAGG(DISTINCT CASE WHEN t.triggered THEN t.text ELSE NULL END, ' AND ') AS texts
      {% endif %}
    FROM {{target_class}}_view AS A
    JOIN
      constraint_table AS ct
      ON A.`type` = ct.targetClass
     AND ct.circuit_level = {{ level }}
    JOIN
      needed AS nm
      ON nm.target_constraint_id = ct.id
    JOIN
      constraint_combination_table AS comb
      ON comb.target_constraint_id = ct.id
     AND comb.operation <> 'PUBLISH'
    LEFT JOIN (
      -- Pre-sort the data for Calcite
      SELECT *
      FROM constraint_trigger_table
      ORDER BY event, text
    ) AS t
      ON t.constraint_id = comb.member_constraint_id
     AND t.resource = A.id
    WHERE IFNULL(A.`deleted`, false) IS FALSE
    GROUP BY
      A.id,
      ct.id,
      ct.operation,
      ct.`eventName`,
      ct.severity,
      nm.needed_count
{%- else %}
      t.resource,
      ct.id AS target_constraint_id,
      ct.operation AS operation,
      ct.severity AS severity,
      nm.needed_count as needed_count,
      COUNT(DISTINCT CASE WHEN t.triggered THEN t.constraint_id ELSE NULL END) AS fired_count,
      {% if sqlite %}
      -- SQLite: GROUP_CONCAT only takes one argument when DISTINCT
      ct.`eventName` AS events,
      'AND(' || GROUP_CONCAT(DISTINCT t.text) || ')' AS texts
      {% else %}
      -- Calcite: LISTAGG without DISTINCT
      ct.`eventName` AS events,
      LISTAGG(DISTINCT CASE WHEN t.triggered THEN t.text ELSE NULL END, ' AND ') AS texts
      {% endif %}
 FROM (
      -- Pre-sort the data for Calcite
      SELECT *
      FROM constraint_trigger_table
      ORDER BY event, text
    ) AS t
    JOIN
      constraint_combination_table AS comb
      ON comb.member_constraint_id = t.constraint_id
     AND comb.operation <> 'PUBLISH'
    JOIN
      constraint_table AS ct
      ON ct.id = comb.target_constraint_id
     AND ct.circuit_level = {{ level }}
    JOIN
      needed AS nm
      ON nm.target_constraint_id   = comb.target_constraint_id
    GROUP BY
      t.resource,
      ct.id,
      ct.operation,
      ct.`eventName`,
      ct.severity,
      nm.needed_count
{%- endif %}
  )

SELECT /*+ STATE_TTL('f' = '0d') */
  f.resource                             AS resource,
  f.events                               AS event,
  f.target_constraint_id                 AS constraint_id,
     ({{ triggered_expr }}) AS triggered,
     CASE WHEN {{ triggered_expr }} THEN f.severity ELSE 'ok' END AS severity,
-- Text must be DETERMINISTIC per node, not an aggregate of member texts.
-- LISTAGG of member texts changes as the member set fills in during
-- convergence, so an unchanged verdict still produced a different alert every
-- time. Measured: one focus node emitted 99 alerts carrying only 2-3 distinct
-- values, and CoreServices' AlertsFilter forwards each of them because it keys
-- on (severity, text). Naming the node instead collapses that to one alert.
-- Member detail remains inspectable in constraint_trigger_table.
-- Identity and explanation are separate. `event` is the stable name of the
-- constraint and is what a clear is addressed to; `text` says what actually
-- happened and is free to change as members report, because a changed text
-- now UPDATES the alert instead of creating a new one under a new key.
-- Absence-firing operators (NOT, XONE) can trigger with no member text at
-- all, so the name stands in.
CASE WHEN {{ triggered_expr }} THEN COALESCE(f.texts, f.events) ELSE 'All ok' END AS text
  {% if sqlite %}
    ,CURRENT_TIMESTAMP AS ts
    {% endif %}
FROM  fired AS f;
;
"""


def create_relationship_sql():
    levels = attribute_level_context(filter_deleted=True)
    sql_command_yaml = Template(sql_check_relationship_base).render(
        alerts_bulk_table=constraint_trigger_table_name,
        constraint_table=constraint_table_name,
        target_class="entities",
        rdf_table_name=configs.rdf_table_name,
        sqlite=False, **levels)
    sql_command_sqlite = Template(sql_check_relationship_base).render(
        alerts_bulk_table=constraint_trigger_table_name,
        constraint_table=constraint_table_name,
        target_class="entities",
        rdf_table_name=configs.rdf_table_name,
        sqlite=True, **levels)
    sql_command_yaml += \
        Template(sql_check_relationship_property_class).render(
            alerts_bulk_table=constraint_trigger_table_name,
            constraint_table=constraint_table_name,
            target_class="entities",
            sqlite=False)
    sql_command_sqlite += \
        Template(sql_check_relationship_property_class).render(
            alerts_bulk_table=constraint_trigger_table_name,
            constraint_table=constraint_table_name,
            target_class="entities",
            sqlite=True)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += \
        Template(sql_check_relationship_property_count).render(
            alerts_bulk_table=constraint_trigger_table_name,
            constraint_table=constraint_table_name,
            target_class="entities",
            sqlite=False)
    sql_command_sqlite += \
        Template(sql_check_relationship_property_count).render(
            alerts_bulk_table=constraint_trigger_table_name,
            constraint_table=constraint_table_name,
            target_class="entities",
            sqlite=True)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_relationship_nodeType).render(
        alerts_bulk_table=constraint_trigger_table_name,
        constraint_table=constraint_table_name,
        property_nodetype='@id',
        property_nodetype_description='an IRI',
        sqlite=False
    )
    sql_command_sqlite += Template(sql_check_relationship_nodeType).render(
        alerts_bulk_table=constraint_trigger_table_name,
        constraint_table=constraint_table_name,
        property_nodetype='@id',
        property_nodetype_description='an IRI',
        sqlite=True
    )
    sql_command_sqlite += ";"
    sql_command_yaml += ";"
    sql_command_sqlite = utils.process_sql_dialect(sql_command_sqlite, True)
    sql_command_yaml = utils.process_sql_dialect(sql_command_yaml, False)
    return sql_command_sqlite, sql_command_yaml


def create_property_sql():

    levels = attribute_level_context()
    sql_command_yaml = Template(
        sql_check_property_iri_base).render(
        alerts_bulk_table=constraint_trigger_table_name,
        constraint_table=constraint_table_name,
        target_class="entities",
        rdf_table_name=configs.rdf_table_name,
        sqlite=False, **levels
    )
    sql_command_sqlite = Template(sql_check_property_iri_base).render(
        alerts_bulk_table=constraint_trigger_table_name,
        constraint_table=constraint_table_name,
        target_class="entities",
        rdf_table_name=configs.rdf_table_name,
        sqlite=True, **levels
    )
    sql_command_yaml += Template(
        sql_check_property_nodeType).render(
        alerts_bulk_table=constraint_trigger_table_name,
        sqlite=False
    )
    sql_command_sqlite += Template(sql_check_property_nodeType).render(
        alerts_bulk_table=constraint_trigger_table_name,
        sqlite=True
    )
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += \
        Template(sql_check_property_iri_class).render(
            alerts_bulk_table=constraint_trigger_table_name,
            sqlite=False)
    sql_command_sqlite += \
        Template(sql_check_property_iri_class).render(
            alerts_bulk_table=constraint_trigger_table_name,
            sqlite=True)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_property_minmax).render(
        operator='>',
        comparison_value='minExclusive',
        minmaxname="MinExclusive",
        sqlite=False
    )
    sql_command_sqlite += \
        Template(sql_check_property_minmax).render(
            operator='>',
            comparison_value='minExclusive',
            minmaxname="MinExclusive",
            sqlite=True)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_property_minmax).render(
        operator='<',
        minmaxname="MaxExclusive",
        comparison_value='maxExclusive',
        sqlite=False
    )
    sql_command_sqlite += \
        Template(sql_check_property_minmax).render(
            operator='<',
            minmaxname="MaxExclusive",
            comparison_value='maxExclusive',
            sqlite=True)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_property_minmax).render(
        operator='<=',
        comparison_value='maxInclusive',
        minmaxname="MaxInclusive",
        sqlite=False
    )
    sql_command_sqlite += \
        Template(sql_check_property_minmax).render(
            operator='<=',
            comparison_value='maxInclusive',
            minmaxname="MaxInclusive",
            sqlite=True)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_property_minmax).render(
        operator='>=',
        comparison_value='minInclusive',
        minmaxname="MinInclusive",
        sqlite=False
    )
    sql_command_sqlite += \
        Template(sql_check_property_minmax).render(
            operator='>=',
            comparison_value='minInclusive',
            minmaxname="MinInclusive",
            sqlite=True)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_literal_in).render(
        alerts_bulk_table=constraint_trigger_table_name,
        sqlite=False,
        constraintname="InConstraintComponent"
    )
    sql_command_sqlite += Template(sql_check_literal_in).render(
        alerts_bulk_table=constraint_trigger_table_name,
        sqlite=True,
        constraintname="InConstraintComponent"
    )
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_literal_pattern).render(
        validationname="Pattern",
        sqlite=False
    )
    sql_command_sqlite += \
        Template(sql_check_literal_pattern).render(
            validationname="Pattern",
            sqlite=True)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_property_count).render(
        sqlite=False
    )
    sql_command_sqlite += \
        Template(sql_check_property_count).render(
            sqlite=True)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_string_length).render(
        operator='<',
        comparison_value="minLength",
        minmaxname="MinLength",
        sqlite=False
    )
    sql_command_sqlite += Template(sql_check_string_length).render(
        operator='<',
        comparison_value="minLength",
        minmaxname="MinLength",
        sqlite=True
    )
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_string_length).render(
        operator='>',
        comparison_value="maxLength",
        minmaxname="MaxLength",
        sqlite=False
    )
    sql_command_sqlite += Template(sql_check_string_length).render(
        operator='>',
        comparison_value="maxLength",
        minmaxname="MaxLength",
        sqlite=True
    )
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_literal_datatypes).render(
        constraintname="DatatypeConstraintComponent",
        check_list_elements=list_element_checks(False),
        sqlite=False
    )
    sql_command_sqlite += Template(sql_check_literal_datatypes).render(
        constraintname="DatatypeConstraintComponent",
        check_list_elements=list_element_checks(True),
        sqlite=True
    )
    sql_command_sqlite = utils.process_sql_dialect(sql_command_sqlite, True)
    sql_command_yaml = utils.process_sql_dialect(sql_command_yaml, False)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_literal_hasvalue).render(
        constraintname="DatatypeConstraintComponent",
        sqlite=False
    )
    sql_command_sqlite += Template(sql_check_literal_hasvalue).render(
        constraintname="DatatypeConstraintComponent",
        sqlite=True
    )
    sql_command_sqlite += ";"
    sql_command_yaml += ";"
    sql_command_sqlite = utils.process_sql_dialect(sql_command_sqlite, True)
    sql_command_yaml = utils.process_sql_dialect(sql_command_yaml, False)
    return sql_command_sqlite, sql_command_yaml


LIST_CONNECTIVES = ((SH['and'], 'AND'), (SH['or'], 'OR'), (SH.xone, 'XONE'))


class ShapeCycle(Exception):
    """A cyclic shape graph cannot be unrolled into a finite circuit."""


def agreed_message(checks, member_ids):
    """
    A circuit node's message, taken from its members when they all agree.

    The connective is what actually fires for a shape like the OPC UA
    ValueRank -- the branches are only its inputs -- so the node has to carry
    the message or the author's text never reaches an alert. Members that
    disagree have no single explanation, so the generated one stands.
    """
    members = set(member_ids)
    messages = {check.get('message') for check in checks
                if check.get('id') in members}
    return messages.pop() if len(messages) == 1 else None


def emit_circuit_node(ctx, operation, member_ids, target_class, focus=None):
    """Add one internal circuit node over `member_ids` and return its id."""
    node_id = ctx['next_id']
    ctx['next_id'] += 1
    severity_of = next((c for c in ctx['checks'] if c.get('id') == member_ids[0]), None)
    check = utils.init_constraint_check()
    check['id'] = node_id
    check['operation'] = operation
    check['targetClass'] = target_class
    check['eventName'] = circuit_event_name(operation, focus)
    check['severity'] = (severity_of or {}).get('severity') or 'warning'
    check['message'] = agreed_message(ctx['checks'], member_ids)
    check['circuit_level'] = utils.circuit_level_of(ctx['checks'], member_ids)
    ctx['checks'].append(check)
    for member in member_ids:
        ctx['combination'].append({'operation': operation,
                                   'member_constraint_id': member,
                                   'target_constraint_id': node_id})
    return node_id


def walk_shape(g, shape, target_class, ctx):
    """
    Build the circuit for `shape` and return its node id, or None if nothing
    underneath it produced constraints.

    Recursion is what makes arbitrary nesting work: every branch returns an id
    that the enclosing connective can use as a member, so depth falls out
    rather than needing another query arm per level. Each node is named as it
    is emitted (Tseitin), so the encoding stays linear instead of distributing
    into an exponential number of terms.
    """
    key = (shape, target_class)
    if key in ctx['memo']:
        return ctx['memo'][key]
    if key in ctx['stack']:
        raise ShapeCycle(f'shape graph is cyclic at {shape}: a cycle has no '
                         f'finite circuit, and Flink SQL has no fixpoint to '
                         f'evaluate one with')
    ctx['stack'].add(key)

    members = []
    # Property shapes already have a circuit node from the property-level pass.
    for prop in g.objects(shape, SH.property):
        # A property node contributes up to two groups: the members of its own
        # connective, and its own parameters. Both are members of the enclosing
        # node-level shape, so both must be consumed here -- missing one would
        # publish it separately and take it out of the node-level logic.
        for key in ((str(prop), target_class),
                    (str(prop) + OWN_PARAMS_SUFFIX, target_class)):
            top = ctx['property_top'].get(key)
            if top is not None:
                members.append(top)
                ctx['consumed'].add(key)

    for predicate, operation in LIST_CONNECTIVES:
        for collection in g.objects(shape, predicate):
            branches = [walk_shape(g, branch, target_class, ctx)
                        for branch in Collection(g, collection)]
            branches = [b for b in branches if b is not None]
            if branches:
                members.append(emit_circuit_node(ctx, operation, branches,
                                                 target_class, shape))
    for inner in g.objects(shape, SH['not']):
        inner_id = walk_shape(g, inner, target_class, ctx)
        if inner_id is not None:
            members.append(emit_circuit_node(ctx, 'NOT', [inner_id],
                                             target_class, shape))

    ctx['stack'].discard(key)
    if not members:
        result = None
    elif len(members) == 1:
        result = members[0]
    else:
        # Every constraint on a shape must hold: implicit conjunction.
        result = emit_circuit_node(ctx, 'AND', members, target_class, shape)
    ctx['memo'][key] = result
    return result


sparql_get_node_shapes = """
SELECT DISTINCT ?nodeshape ?inheritedTargetclass
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?inheritedTargetclass rdfs:subClassOf* ?targetclass .
}
"""


def apply_node_level_logic(g, prefixes, constraint_checks,
                           constraint_combination, property_top, next_id):
    """
    Build circuits for connectives attached directly to a NodeShape.

    These group whole shapes rather than the values of one path, so their
    branches may each constrain a different property. A SPARQL property path
    can reach the leaves but cannot report the tree that groups them, which is
    why this walks the graph instead.

    Returns (next_id, consumed, roots): `consumed` are property shapes that are
    now members of a node-level connective and must not raise their own alert,
    `roots` are the circuit nodes to publish.
    """
    ctx = {'checks': constraint_checks, 'combination': constraint_combination,
           'next_id': next_id, 'property_top': property_top,
           'consumed': set(), 'memo': {}, 'stack': set()}
    roots = []
    for row in utils.in_stable_order(g.query(sparql_get_node_shapes, initNs=prefixes)):
        nodeshape = row.nodeshape
        target_class = row.inheritedTargetclass.toPython()
        for predicate, operation in LIST_CONNECTIVES:
            for collection in g.objects(nodeshape, predicate):
                branches = [walk_shape(g, branch, target_class, ctx)
                            for branch in Collection(g, collection)]
                branches = [b for b in branches if b is not None]
                if branches:
                    roots.append(emit_circuit_node(ctx, operation, branches,
                                                   target_class, nodeshape))
        for inner in g.objects(nodeshape, SH['not']):
            inner_id = walk_shape(g, inner, target_class, ctx)
            if inner_id is not None:
                roots.append(emit_circuit_node(ctx, 'NOT', [inner_id],
                                               target_class, nodeshape))
    return ctx['next_id'], ctx['consumed'], roots


def inject_synthetic_circuit(constraint_checks, constraint_combination, next_id):
    """
    Graft a NOT node and a level-2 AND node onto already-extracted constraints.

    Debug only, see the call site. Deliberately adds no PUBLISH edge, so the
    synthetic verdicts land in constraint_trigger_table and never reach
    alerts_bulk. Returns the next free constraint id.
    """
    leaf = next((check for check in constraint_checks
                 if check['operation'] is None and check['targetClass']), None)
    if leaf is None:
        print('SHACL_DEBUG_SYNTHETIC_CIRCUIT: no leaf with a targetClass, skipping')
        return next_id
    target_class = leaf['targetClass']

    not_id = next_id
    next_id += 1
    not_node = utils.init_constraint_check()
    not_node['id'] = not_id
    not_node['operation'] = 'NOT'
    not_node['circuit_level'] = utils.circuit_level_of(constraint_checks, [leaf['id']])
    not_node['targetClass'] = target_class
    not_node['severity'] = 'warning'
    constraint_checks.append(not_node)
    constraint_combination.append({'operation': 'NOT',
                                   'member_constraint_id': leaf['id'],
                                   'target_constraint_id': not_id})

    # Pair the NOT with an existing OR node so the AND lands on level 2.
    members = [not_id]
    or_node = next((check for check in constraint_checks
                    if check['operation'] == 'OR' and
                    check['targetClass'] == target_class), None)
    if or_node is not None:
        members.append(or_node['id'])

    and_id = next_id
    next_id += 1
    and_node = utils.init_constraint_check()
    and_node['id'] = and_id
    and_node['operation'] = 'AND'
    and_node['circuit_level'] = utils.circuit_level_of(constraint_checks, members)
    and_node['targetClass'] = target_class
    and_node['severity'] = 'warning'
    constraint_checks.append(and_node)
    for member in members:
        constraint_combination.append({'operation': 'AND',
                                       'member_constraint_id': member,
                                       'target_constraint_id': and_id})

    print(f'SHACL_DEBUG_SYNTHETIC_CIRCUIT: NOT({leaf["id"]})={not_id}, '
          f'AND{tuple(members)}={and_id} at level {and_node["circuit_level"]}, '
          f'targetClass={target_class}')
    return next_id


sparql_get_countonly_parameters = """
SELECT ?nodeshape ?targetclass ?inheritedTargetclass ?propertypath ?mincount ?maxcount ?severitycode ?property
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?inheritedTargetclass rdfs:subClassOf* ?targetclass .
    ?nodeshape (sh:property|(sh:or|sh:and|sh:xone)/rdf:rest*/rdf:first|sh:not)+ ?property .
    ?property sh:path ?propertypath .
    ## A property node whose counts are conjoined with a connective and which
    ## has no value shape of its own. The main queries reach a constraint only
    ## through a value shape, so this case is picked up separately rather than
    ## by making that join optional -- the attribute type then has to be
    ## derived from the connective, which is a graph walk, not a join.
    FILTER EXISTS { ?property (sh:or|sh:and|sh:xone|sh:not) ?anyconnective }
    FILTER NOT EXISTS { ?property sh:property ?anyvalueshape }
    FILTER EXISTS { ?property (sh:minCount|sh:maxCount) ?anycount }
    OPTIONAL { ?property sh:minCount ?mincount ; }
    OPTIONAL { ?property sh:maxCount ?maxcount ; }
    OPTIONAL { ?property sh:severity ?severity . ?severity rdfs:label ?severitycode .}
}
"""  # noqa: E501

# Value path -> the NGSI-LD attribute type it implies.
VALUE_PATH_ATTRIBUTE_TYPES = {
    'https://uri.etsi.org/ngsi-ld/hasValue': 'https://uri.etsi.org/ngsi-ld/Property',
    'https://uri.etsi.org/ngsi-ld/hasValueList': 'https://uri.etsi.org/ngsi-ld/ListProperty',
    'https://uri.etsi.org/ngsi-ld/hasJSON': 'https://uri.etsi.org/ngsi-ld/JsonProperty',
    'https://uri.etsi.org/ngsi-ld/hasObject': 'https://uri.etsi.org/ngsi-ld/Relationship',
}


def branch_attribute_type(g, property_node):
    """
    Attribute type of a property node that only carries counts.

    Its own shape says nothing about whether the attribute is a Property or a
    Relationship, so the answer comes from the value shapes inside the
    connective it is conjoined with. Sorted, so a shape that mixes them
    compiles to the same thing on every run rather than picking whichever
    binding the store happened to yield first.
    """
    found = set()
    for clause in connective_clauses(g, property_node):
        for value_shape in g.objects(clause, SH.property):
            for path in g.objects(value_shape, SH.path):
                attribute_type = VALUE_PATH_ATTRIBUTE_TYPES.get(str(path))
                if attribute_type is not None:
                    found.add((str(path), attribute_type))
    types = {attribute_type for _, attribute_type in found}
    if len(types) > 1:
        # The branches disagree: an OPC UA variable is a Property when scalar
        # and a ListProperty when an array, and `sh:maxCount 1` on the node
        # above them means one attribute of EITHER kind. Committing to one
        # branch would count only that kind and alert on the other, so the
        # count spans them -- expressed as no attribute type at all.
        return (None, None)
    return sorted(found)[0] if found else (None, None)


def connective_clauses(g, node):
    """Every branch of every connective directly on this node."""
    for predicate, _ in LIST_CONNECTIVES:
        for collection in g.objects(node, predicate):
            for branch in Collection(g, collection):
                yield branch
    for branch in g.objects(node, SH['not']):
        yield branch


# Paths that make a nested sh:property a VALUE shape rather than an attribute
# shape. Anything else at that position names an NGSI-LD attribute.
NGSILD_VALUE_PATHS = frozenset(VALUE_PATH_ATTRIBUTE_TYPES)


def shape_subtree(g, shape):
    """Every shape node at or beneath this one."""
    seen, frontier = set(), [shape]
    while frontier:
        node = frontier.pop()
        if node in seen:
            continue
        seen.add(node)
        frontier.extend(g.objects(node, SH.property))
        frontier.extend(connective_clauses(g, node))
    return seen


def attribute_shapes(g):
    """
    Every property shape that names an NGSI-LD attribute, with its node shape.

    These are the shapes that must produce constraints. Only node-level
    connectives are descended through: a shape nested inside an attribute shape
    describes that attribute -- its value (ngsi-ld:hasValue and friends), or its
    rdf:type -- rather than naming an attribute of its own, and the compiler
    folds those into the attribute's constraint instead of emitting one.
    """
    for nodeshape in g.subjects(RDF.type, SH.NodeShape):
        if not list(g.objects(nodeshape, SH.targetClass)):
            continue
        seen, frontier = set(), [nodeshape]
        while frontier:
            shape = frontier.pop()
            if shape in seen:
                continue
            seen.add(shape)
            frontier.extend(connective_clauses(g, shape))
            for prop in g.objects(shape, SH.property):
                paths = list(g.objects(prop, SH.path))
                if len(paths) == 1 and str(paths[0]) not in NGSILD_VALUE_PATHS \
                        and paths[0] != RDF.type:
                    yield nodeshape, prop, paths[0]


# Everything on a referenced shape that describes THAT SHAPE rather than the
# value nodes it constrains. Targets are explicitly ignored by sh:node (the
# referenced shape applies to the referring node's values, not to its own
# targets), and the rest are annotations the compiler does not translate.
#
# sh:message is NOT in this list. It describes violations of the constraints
# being copied, and those constraints are now the referring node's -- so the
# message travels with them. This is where the OPC UA generator puts its
# ValueRank messages, and dropping them left the alert with a generated text
# that named a blank node's datatype instead of the rank it violated.
NODE_SHAPE_ANNOTATIONS = frozenset({
    RDF.type, SH.targetClass, SH.targetNode, SH.targetObjectsOf,
    SH.targetSubjectsOf, SH.name, SH.description, SH.order, SH.group,
})

CONNECTIVE_PREDICATES = frozenset({SH['or'], SH['and'], SH.xone, SH['not']})

# A reference chain longer than this is a cycle in practice. The limit exists
# to terminate, not to express a real modelling bound.
MAX_NODE_SHAPE_DEPTH = 10


def node_shape_cycles(g):
    """
    Reference cycles, named by the shapes that form them.

    Inlining resolves a cycle by expanding it forever, so it has to be found
    first. Reporting it as the cycle it is matters: expansion turns A -> B -> A
    into a self-reference on A after one round, and telling an author that A
    references itself when they wrote two shapes sends them to the wrong file.
    """
    edges = {}
    for referring, shape in g.subject_objects(SH.node):
        edges.setdefault(referring, set()).add(shape)

    problems, state = [], {}

    def visit(node, stack):
        state[node] = 'open'
        for following in sorted(edges.get(node, ()), key=str):
            if state.get(following) == 'open':
                cycle = stack[stack.index(following):] + [following]
                trail = ' -> '.join(f'<{n}>' for n in cycle)
                problems.append(f'sh:node references form a cycle: {trail}')
            elif following not in state:
                visit(following, stack + [following])
        state[node] = 'done'

    for node in sorted(edges, key=str):
        if node not in state:
            visit(node, [node])
    return problems


def clone_shape_node(g, node, mapping):
    """
    Copy a shape subtree, minting a fresh blank node for every blank node.

    Sharing the original blank nodes instead would be cheaper and wrong twice
    over. A referenced shape used by several properties would give them one
    shared set of clause nodes, so their constraints would collide; and the
    shared nodes stay reachable from the referenced shape as well as from the
    referring one, so walking up from a value shape finds two parents. The
    second one is not hypothetical -- it silently reparented a hasValueList
    count from `hasVariable ==> hasValueList` to a top-level `hasValueList`,
    which then fired on every valid scalar.
    """
    if not isinstance(node, BNode):
        return node
    if node in mapping:
        return mapping[node]
    fresh = BNode()
    mapping[node] = fresh
    for predicate, obj in sorted(g.predicate_objects(node), key=str):
        g.add((fresh, predicate, clone_shape_node(g, obj, mapping)))
    return fresh


def remove_shape(g, shape):
    """Drop a shape and everything only it can reach."""
    frontier, seen = [shape], set()
    while frontier:
        node = frontier.pop()
        if node in seen:
            continue
        seen.add(node)
        for predicate, obj in list(g.predicate_objects(node)):
            if isinstance(obj, BNode):
                frontier.append(obj)
            g.remove((node, predicate, obj))


def inline_node_shape(g, referring, shape):
    """
    Copy one referenced shape's constraints onto the node that references it.

    `sh:node S` says the value nodes conform to S, and S carries exactly what
    would otherwise be written inline. Conjoining the two is therefore the
    whole of the semantics -- for the subset that reaches here.
    """
    problems = []
    mapping = {}
    own_connectives = [p for p in CONNECTIVE_PREDICATES if (referring, p, None) in g]

    for predicate, obj in sorted(g.predicate_objects(shape), key=str):
        if predicate in NODE_SHAPE_ANNOTATIONS:
            continue
        if predicate == SH.deactivated:
            # Dropping it would activate constraints the author switched off;
            # copying it would switch off the referring shape's own ones too.
            problems.append(
                f'sh:deactivated on <{shape}> referenced by sh:node is not '
                f'supported: its constraints cannot be conjoined without '
                f'either activating them or deactivating the referring shape.')
            continue
        if predicate in CONNECTIVE_PREDICATES and own_connectives:
            # connective_clauses() iterates EVERY connective on a node and
            # yields their branches as one set, so two sh:or lists on the same
            # node read as a single wider sh:or. That turns an AND of two
            # disjunctions into one disjunction -- strictly weaker, and
            # invisible in the output.
            problems.append(
                f'sh:node <{shape}> carries sh:{str(predicate).rsplit("#", 1)[-1]} '
                f'and the referring shape already carries a connective. '
                f'Conjoining them would read as a single wider connective and '
                f'silently weaken the constraint.')
            continue
        if predicate != SH.property and (referring, predicate, None) in g \
                and obj not in set(g.objects(referring, predicate)):
            problems.append(
                f'sh:node <{shape}> sets {predicate} to {obj}, but the '
                f'referring shape already sets it to '
                f'{sorted(str(o) for o in g.objects(referring, predicate))}. '
                f'The compiler cannot conjoin two values of the same parameter.')
            continue
        g.add((referring, predicate, clone_shape_node(g, obj, mapping)))

    return problems


def expand_node_shapes(g):
    """
    Replace every sh:node reference with the constraints it points at.

    The OPC UA generator factors its ValueRank constraints into named shapes
    and references them, rather than inlining the same sh:or(hasValue,
    hasValueList) at every variable. Nothing downstream understands the
    indirection, so a referencing property shape reached the extractor with no
    value shape at all. Resolving it here means the extractor, the circuit
    builder and every SQL template stay untouched.
    """
    cycles = node_shape_cycles(g)
    if cycles:
        raise UnsupportedShape(
            'the following shapes cannot be compiled and would be silently '
            'unvalidated:\n  - ' + '\n  - '.join(cycles))

    referenced = set()
    for _ in range(MAX_NODE_SHAPE_DEPTH):
        references = sorted(g.subject_objects(SH.node),
                            key=lambda pair: (str(pair[0]), str(pair[1])))
        if not references:
            break
        problems = []
        for referring, shape in references:
            g.remove((referring, SH.node, shape))
            referenced.add(shape)
            problems.extend(inline_node_shape(g, referring, shape))
        if problems:
            raise UnsupportedShape(
                'the following shapes cannot be compiled and would be '
                'silently unvalidated:\n  - ' + '\n  - '.join(problems))
    else:
        raise UnsupportedShape(
            f'sh:node references nest deeper than {MAX_NODE_SHAPE_DEPTH}, '
            f'which means they form a cycle.')

    # Every reference now owns a private copy, so the original is dead weight
    # -- and not harmlessly so: its value shapes still answer graph-wide
    # queries, which is how an orphaned hasValueList count came to be
    # published in its own right. A shape with targets of its own is a real
    # node shape that happens to also be referenced, so it stays.
    for shape in sorted(referenced, key=str):
        if not list(g.objects(shape, SH.targetClass)):
            remove_shape(g, shape)


def unsupported_shapes(g, compiled):
    """
    Shapes the extractor will not compile, as a list of messages.

    `compiled` is the set of property nodes that produced at least one
    constraint.
    """
    problems = []
    seen_messages = set()

    # NGSI-LD value predicates the data path cannot represent. create_ngsild_
    # models builds the attributes table from hasValue/hasObject/hasValueList/
    # hasJSON only, so an attribute carrying one of these produces no attribute
    # row at all -- the entity row exists and the attribute simply is not
    # there. A shape constraining one is therefore not merely unchecked: a
    # count over it reports "Found 0" for an attribute that is present, and any
    # bound on it can never fire. Rejected until the data path can see them.
    for value_shape in g.subjects(SH.path, None):
        for path in g.objects(value_shape, SH.path):
            path = str(path)
            if not path.startswith(str(NGSILD) + 'has'):
                continue
            if path in VALUE_PATH_ATTRIBUTE_TYPES:
                continue
            supported = ', '.join(sorted(
                p.rsplit('/', 1)[-1] for p in VALUE_PATH_ATTRIBUTE_TYPES))
            problems.append(
                f'<{path}> is an NGSI-LD value path the data pipeline does not '
                f'build attributes for, so a shape using it would report a '
                f'present attribute as missing rather than checking it. '
                f'Supported value paths are: {supported}.')

    # The extractor descends one connective on the property shape and one on
    # the value shape. A connective on a BRANCH is a third level: its members
    # would contribute nothing, exactly the way a value-level sh:xone used to.
    for value_shape in g.subjects(SH.path, None):
        paths = [str(path) for path in g.objects(value_shape, SH.path)]
        if not any(path in NGSILD_VALUE_PATHS for path in paths):
            continue
        for branch in connective_clauses(g, value_shape):
            for predicate, operation in LIST_CONNECTIVES + ((SH['not'], 'NOT'),):
                if list(g.objects(branch, predicate)):
                    problems.append(
                        f'sh:{operation.lower()} nested inside a branch of the value '
                        f'shape of <{paths[0]}> is not supported. Connectives are '
                        f'descended one level on the property shape and one on the '
                        f'value shape; a third level would contribute no constraint.')

    for nodeshape, prop, path in attribute_shapes(g):
        # The constraint may be attributed to a sub-attribute rather than to
        # this shape -- iff:assembly carrying only iff:torque compiles to a
        # constraint on torque. So the requirement is that the subtree
        # contributes something, not this exact node.
        if not any(str(node) in compiled for node in shape_subtree(g, prop)):
            problems.append(
                f'the property shape for <{path}> in node shape <{nodeshape}> '
                f'produced no constraint. It would be accepted and never checked. '
                f'Check that it has a value shape (sh:property with an ngsi-ld '
                f'path) and that its parameters are ones the compiler supports.')

    return [p for p in problems if not (p in seen_messages or seen_messages.add(p))]


def translate(shaclefile, knowledgefile, prefixes):
    """
    Translate shacl properties into SQL constraints.

    Parameters:
        filename: filename of SHACL file

    Returns:
        sql-statement-list: list of plain SQL objects
        (statementset, tables, views): statementset in yaml format

    """
    g = Graph()
    h = Graph()
    g.parse(shaclefile)
    h.parse(knowledgefile)
    g += h
    # Resolve sh:node before anything reads the shapes, so the extractor only
    # ever sees inlined constraints.
    expand_node_shapes(g)
    tables = [alerts_bulk_table_object, configs.attributes_table_obj_name,
              configs.rdf_table_obj_name]
    views = [configs.attributes_view_obj_name]
    statementsets = []
    value_statementsets = []
    sqlite = ''
    postgres_constraints = ''
    # Get all NGSI-LD Relationship

    constraint_checks = []
    constraint_combination = []
    constraint_id_counter = 0
    depth_problems = set()

    property_nodes = {}          # property node -> its clause keys
    property_connectives = {}
    clause_nodes = {}            # clause key -> the leaf constraints it holds
    clause_connectives = {}
    focus_paths = {}             # property node -> the path it constrains
    qres = utils.in_stable_order(g.query(sparql_get_all_relationships, initNs=prefixes))
    for row in qres:
        paths = get_full_path_of_shacl_property(g, row.property)
        if len(paths) > MAX_SUBPROPERTY_DEPTH + 1:
            depth_problems.add(
                f'subproperty depth {len(paths)} is not supported (limit '
                f'{MAX_SUBPROPERTY_DEPTH + 1}) in path {paths}')
            continue
        check = utils.init_constraint_check()
        target_class = row.inheritedTargetclass.toPython() \
            if row.targetclass else None
        property_path = row.propertypath.toPython() if row.propertypath \
            else None
        property_class = row.attributeclass.toPython() if row.attributeclass \
            else None
        mincount = row.mincount.toPython() if row.mincount is not None else 0
        maxcount = row.maxcount.toPython() if row.maxcount is not None else None
        property = row.property.toPython()
        # A property node's own parameters are conjoined with any connective on
        # that node, not a member of it, so they get their own group. At arity
        # 1 that group publishes directly, which is exactly the conjunction.
        node_key = (property + OWN_PARAMS_SUFFIX, target_class) \
            if getattr(row, 'ownparams', None) else (property, target_class)
        # A value shape's connective is its own circuit node, fed into the
        # property's. Folding the two together would evaluate the inner one
        # with the outer one's operator -- fine while both were OR, since OR
        # flattens, but XONE(a, OR(b, c)) is not XONE(a, b, c).
        clause_key = (node_key, str(getattr(row, 'clause', property)))
        clause_connectives[clause_key] = \
            connective_operation(getattr(row, 'innerconnective', None))
        if node_key not in property_nodes.keys():
            property_nodes[node_key] = []
        if clause_key not in property_nodes[node_key]:
            property_nodes[node_key].append(clause_key)
        property_connectives[node_key] = \
            connective_operation(getattr(row, 'connective', None))
        focus_paths[node_key] = property_path
        severitycode = row.severitycode.toPython() if row.severitycode \
            else 'warning'
        check['targetClass'] = target_class
        set_attribute_path(check, paths, property_path)
        check['message'] = shape_message(g, row.property)
        check['propertyClass'] = property_class
        check['attributeType'] = 'https://uri.etsi.org/ngsi-ld/Relationship'
        check['maxCount'] = maxcount
        check['minCount'] = mincount
        check['severity'] = severitycode
        check['id'] = constraint_id_counter
        constraint_checks.append(check)
        clause_nodes.setdefault(clause_key, []).append(constraint_id_counter)
        constraint_id_counter += 1
    # Get all NGSI-LD Properties
    qres = utils.in_stable_order(g.query(sparql_get_all_properties, initNs=prefixes))
    for row in qres:
        paths = get_full_path_of_shacl_property(g, row.property)
        if len(paths) > MAX_SUBPROPERTY_DEPTH + 1:
            depth_problems.add(
                f'subproperty depth {len(paths)} is not supported (limit '
                f'{MAX_SUBPROPERTY_DEPTH + 1}) in path {paths}')
            continue
        check = utils.init_constraint_check()
        nodeshape = row.nodeshape.toPython()
        target_class = row.inheritedTargetclass.toPython() \
            if row.targetclass else None
        property_path = row.propertypath.toPython() if row.propertypath \
            else None
        property_class = row.attributeclass.toPython() if row.attributeclass\
            else None
        mincount = row.mincount.toPython() if row.mincount is not None else None
        maxcount = row.maxcount.toPython() if row.maxcount is not None else None
        property = row.property.toPython()
        # A property node's own parameters are conjoined with any connective on
        # that node, not a member of it, so they get their own group. At arity
        # 1 that group publishes directly, which is exactly the conjunction.
        node_key = (property + OWN_PARAMS_SUFFIX, target_class) \
            if getattr(row, 'ownparams', None) else (property, target_class)
        # A value shape's connective is its own circuit node, fed into the
        # property's. Folding the two together would evaluate the inner one
        # with the outer one's operator -- fine while both were OR, since OR
        # flattens, but XONE(a, OR(b, c)) is not XONE(a, b, c).
        clause_key = (node_key, str(getattr(row, 'clause', property)))
        clause_connectives[clause_key] = \
            connective_operation(getattr(row, 'innerconnective', None))
        if node_key not in property_nodes.keys():
            property_nodes[node_key] = []
        if clause_key not in property_nodes[node_key]:
            property_nodes[node_key].append(clause_key)
        property_connectives[node_key] = \
            connective_operation(getattr(row, 'connective', None))
        focus_paths[node_key] = property_path
        severitycode = row.severitycode.toPython() if row.severitycode \
            else 'warning'
        nodekind = row.nodekind if row.nodekind else None
        valuepath = row.valuepath
        # Every one of these tests `is not None` rather than truthiness, and
        # that is not style: rdflib.Literal(0) is FALSY. Written as
        # `if row.maxinclusive`, a bound of 0 -- "at most zero errors", "not
        # above zero" -- was read as "no bound given" and the constraint was
        # dropped from the build. Nothing said so; the shape simply stopped
        # being enforced, which is indistinguishable from a conformant model.
        min_exclusive = row.minexclusive.toPython() if row.minexclusive \
            is not None else None
        max_exclusive = row.maxexclusive.toPython() if row.maxexclusive \
            is not None else None
        min_inclusive = row.mininclusive.toPython() if row.mininclusive \
            is not None else None
        max_inclusive = row.maxinclusive.toPython() if row.maxinclusive \
            is not None else None
        min_length = row.minlength.toPython() if row.minlength is not None \
            else None
        max_length = row.maxlength.toPython() if row.maxlength is not None \
            else None
        pattern = row.pattern.toPython() if row.pattern is not None else None
        ins = row.ins.toPython() if str(row.ins) != '' else None
        # GROUP_CONCAT does not define an order, so the same shape can yield
        # 'integer,double' or 'double,integer' from one build to the next.
        datatypes = ','.join(sorted(row.datatypes.toPython().split(','))) \
            if str(row.datatypes) != '' else None
        hasValue = row.hasValue if row.hasValue is not None else None

        check['targetClass'] = target_class
        set_attribute_path(check, paths, property_path)
        check['message'] = shape_message(g, row.property)
        check['propertyClass'] = property_class
        if nodekind == SH.IRI:
            check['propertyNodetype'] = '@id'
        elif nodekind == SH.Literal:
            check['propertyNodetype'] = '@value'
        else:
            check['propertyNodetype'] = None
        if valuepath == NGSILD['hasValue']:
            check['attributeType'] = 'https://uri.etsi.org/ngsi-ld/Property'
            if hasValue is not None:
                hasValue = hasValue.toPython()
        elif valuepath == NGSILD['hasJSON']:
            check['attributeType'] = 'https://uri.etsi.org/ngsi-ld/JsonProperty'
            check['propertyNodetype'] = '@json'
            if hasValue is not None:
                hasValue = hasValue.toPython()
        elif valuepath == NGSILD['hasValueList']:
            check['attributeType'] = 'https://uri.etsi.org/ngsi-ld/ListProperty'
            check['propertyNodetype'] = '@list'
            if hasValue:
                hasValue = utils.rdf_list_to_pylist(g, hasValue)
        check['maxCount'] = maxcount
        check['minCount'] = mincount
        check['severity'] = severitycode
        check['minExclusive'] = min_exclusive
        check['maxExclusive'] = max_exclusive
        check['minInclusive'] = min_inclusive
        check['maxInclusive'] = max_inclusive
        check['minLength'] = min_length
        check['maxLength'] = max_length
        check['pattern'] = pattern
        check['ins'] = ins
        check['datatypes'] = datatypes
        check['hasValue'] = hasValue
        check['id'] = constraint_id_counter
        ins_is_broken = False
        quoted_string_list_pattern = r'^"[^"]*"(?:,\s*"[^"]*")*$'
        if ins:
            if not re.match(quoted_string_list_pattern, ins):
                ins_is_broken = True
        if ins_is_broken:
            print(f"Warning: Conversion of sh:in list failed for nodeshape {nodeshape}. Please check. Currently only \
string elements in list are supported.")
            check['ins'] = None
        constraint_checks.append(check)
        clause_nodes.setdefault(clause_key, []).append(constraint_id_counter)
        constraint_id_counter += 1

    # Counts written beside a connective, on a node with no value shape of its
    # own. They are conjoined with the connective, so they get their own group
    # and publish independently -- see sparql_get_countonly_parameters.
    for row in utils.in_stable_order(g.query(sparql_get_countonly_parameters, initNs=prefixes)):
        paths = get_full_path_of_shacl_property(g, row.property)
        if len(paths) > MAX_SUBPROPERTY_DEPTH + 1:
            depth_problems.add(
                f'subproperty depth {len(paths)} is not supported (limit '
                f'{MAX_SUBPROPERTY_DEPTH + 1}) in path {paths}')
            continue
        value_path, attribute_type = branch_attribute_type(g, row.property)
        if not list(connective_clauses(g, row.property)):
            # Nothing in the connective says what kind of attribute this is, so
            # there is no count to compile.
            continue
        target_class = row.inheritedTargetclass.toPython() if row.targetclass else None
        property_path = row.propertypath.toPython() if row.propertypath else None
        check = utils.init_constraint_check()
        check['targetClass'] = target_class
        set_attribute_path(check, paths, property_path)
        check['message'] = shape_message(g, row.property)
        check['attributeType'] = attribute_type
        if value_path == 'https://uri.etsi.org/ngsi-ld/hasValueList':
            check['propertyNodetype'] = '@list'
        elif value_path == 'https://uri.etsi.org/ngsi-ld/hasJSON':
            check['propertyNodetype'] = '@json'
        check['minCount'] = row.mincount.toPython() \
            if row.mincount is not None else None
        check['maxCount'] = row.maxcount.toPython() \
            if row.maxcount is not None else None
        check['severity'] = row.severitycode.toPython() if row.severitycode else 'warning'
        check['id'] = constraint_id_counter
        node_key = (row.property.toPython() + OWN_PARAMS_SUFFIX, target_class)
        clause_key = (node_key, 'countonly')
        clause_connectives[clause_key] = 'OR'
        if node_key not in property_nodes.keys():
            property_nodes[node_key] = []
        if clause_key not in property_nodes[node_key]:
            property_nodes[node_key].append(clause_key)
        property_connectives[node_key] = 'OR'
        focus_paths[node_key] = property_path
        constraint_checks.append(check)
        clause_nodes.setdefault(clause_key, []).append(constraint_id_counter)
        constraint_id_counter += 1

    def fold(members, operation, target_class, focus):
        """
        Collapse members into one circuit node, or pass a lone member through.

        OR/AND/XONE at arity 1 all reduce to "violated iff the member
        violated", so the member can stand in for the group. NOT does not.
        """
        nonlocal constraint_id_counter
        if len(members) == 1 and operation != 'NOT':
            return members[0]
        target_constraint_id = constraint_id_counter
        constraint_id_counter += 1
        check = utils.init_constraint_check()
        severity_id = members[0] if members else None
        severity_object = next((d for d in constraint_checks
                                if d.get('id') == severity_id), None)
        check['id'] = target_constraint_id
        check['severity'] = severity_object['severity'] if severity_object else 'warning'
        # Internal node of the constraint circuit. The target class is needed
        # so that connectives which fire on the ABSENCE of a violation
        # (NOT, XONE) can be scoped to the right set of focus nodes.
        check['operation'] = operation
        check['targetClass'] = target_class
        check['eventName'] = circuit_event_name(operation, focus)
        check['message'] = agreed_message(constraint_checks, members)
        check['circuit_level'] = utils.circuit_level_of(constraint_checks, members)
        constraint_checks.append(check)
        for member in members:
            constraint_combination.append({'operation': operation,
                                           'member_constraint_id': member,
                                           'target_constraint_id': target_constraint_id})
        return target_constraint_id

    # A value shape's connective folds first, then the property's folds over
    # the results. Two levels, so a connective inside a value shape keeps its
    # own operator instead of inheriting the one above it.
    clause_top = {}
    for clause_key, members in clause_nodes.items():
        clause_top[clause_key] = fold(members,
                                      clause_connectives.get(clause_key, 'OR'),
                                      clause_key[0][1],
                                      focus_paths.get(clause_key[0]))

    # Build the circuit node for each property shape but do NOT publish yet: a
    # property that turns out to sit under a node-level connective has to feed
    # that connective instead of raising an alert of its own.
    property_top = {}
    for property_node, clause_keys in property_nodes.items():
        members = [clause_top[key] for key in clause_keys if key in clause_top]
        if not members:
            continue
        property_top[property_node] = fold(
            members, property_connectives.get(property_node, 'OR'), property_node[1],
            focus_paths.get(property_node))

    # Connectives attached directly to a NodeShape group whole shapes, so their
    # branches can each constrain a different property. Only a graph walk can
    # recover that tree -- see apply_node_level_logic.
    constraint_id_counter, consumed, node_level_roots = apply_node_level_logic(
        g, prefixes, constraint_checks, constraint_combination,
        property_top, constraint_id_counter)

    for property_node, top_id in property_top.items():
        if property_node in consumed:
            continue
        constraint_combination.append({'operation': 'PUBLISH',
                                       'member_constraint_id': top_id,
                                       'target_constraint_id': -1})
    for root_id in node_level_roots:
        constraint_combination.append({'operation': 'PUBLISH',
                                       'member_constraint_id': root_id,
                                       'target_constraint_id': -1})

    # Debug hook. The extractor cannot yet emit AND/NOT/XONE or a circuit deeper
    # than one level, so there is no way to exercise those code paths against a
    # real cluster. Setting SHACL_DEBUG_SYNTHETIC_CIRCUIT grafts a small
    # multi-level circuit onto existing constraints, which keeps the generated
    # SQL and the constraint rows consistent with each other. Never set in
    # production: it publishes nothing, but it does add rows to constraint_table.
    if os.getenv('SHACL_DEBUG_SYNTHETIC_CIRCUIT'):
        constraint_id_counter = inject_synthetic_circuit(
            constraint_checks, constraint_combination, constraint_id_counter)

    tables.append(configs.kafka_topic_ngsi_prefix_name)
    views.append(configs.kafka_topic_ngsi_prefix_name + "-view")
    sqlite += '\n'
    sqlite += "\n".join(utils.add_table_values(constraint_checks,
                                               utils.constraint_table,
                                               utils.SQL_DIALECT.SQLITE,
                                               configs.constraint_table_name))
    postgres_constraints += '\n'
    postgres_constraints += "\n".join(utils.add_table_values(constraint_checks,
                                                             utils.constraint_table,
                                                             utils.SQL_DIALECT.POSTGRES,
                                                             configs.constraint_table_name))
    sql_command_yaml = utils.add_table_values(constraint_checks,
                                              utils.constraint_table,
                                              utils.SQL_DIALECT.SQL,
                                              configs.constraint_table_name)
    value_statementsets.extend(sql_command_yaml)
    tables.append(configs.constraint_table_object_name)
    postgres_constraints += '\n'
    postgres_constraints += "\n".join(utils.add_table_values(constraint_combination,
                                                             utils.constraint_combination_table,
                                                             utils.SQL_DIALECT.POSTGRES,
                                                             configs.constraint_combination_table_name))
    sqlite += '\n'
    sqlite += "\n".join(utils.add_table_values(constraint_combination,
                                               utils.constraint_combination_table,
                                               utils.SQL_DIALECT.SQLITE,
                                               configs.constraint_combination_table_name))
    sql_command_yaml = utils.add_table_values(constraint_combination,
                                              utils.constraint_combination_table,
                                              utils.SQL_DIALECT.SQL,
                                              configs.constraint_combination_table_name)
    value_statementsets.extend(sql_command_yaml)
    sqlite += '\n'
    sql_command_sqlite, sql_command_yaml = create_relationship_sql()
    statementsets.append(sql_command_yaml)
    sqlite += sql_command_sqlite
    sqlite += '\n'
    sql_command_sqlite, sql_command_yaml = create_property_sql()
    sqlite += sql_command_sqlite
    statementsets.append(sql_command_yaml)

    # Evaluate the constraint circuit bottom up, one statement per level. The
    # levels are known at build time, so no recursion is needed at runtime.
    levels = sorted({check['circuit_level'] for check in constraint_checks
                     if check['circuit_level'] > 0})
    for level in levels:
        needs_universe = any(check['circuit_level'] == level and
                             check['operation'] in ABSENCE_FIRING_OPERATIONS
                             for check in constraint_checks)
        sql_command_yaml = Template(sql_combine_logic).render(
            alerts_bulk_table=alerts_bulk_table,
            constraint_trigger_table=constraint_trigger_table_name,
            constraint_combination_table=constraint_combination_table_name,
            target_class="entities",
            level=level,
            needs_universe=needs_universe,
            sqlite=False)
        sql_command_sqlite = Template(sql_combine_logic).render(
            alerts_bulk_table=alerts_bulk_table,
            constraint_trigger_table=constraint_trigger_table_name,
            constraint_combination_table=constraint_combination_table_name,
            target_class="entities",
            level=level,
            needs_universe=needs_universe,
            sqlite=True)
        statementsets.append(sql_command_yaml)
        sqlite += sql_command_sqlite
    tables.append(configs.constraint_combination_table_object_name)
    tables.append(configs.constraint_trigger_table_object_name)
    sqlite += '\n'
    sql_command_yaml = Template(sql_insert_constraint_in_alerts).render(
        alerts_bulk_table=alerts_bulk_table,
        constraint_table=constraint_table_name,
        constraint_trigger_table=constraint_trigger_table_name,
        constraint_combination_table=constraint_combination_table_name,
        target_class="entities",
        sqlite=False)
    sql_command_sqlite = Template(sql_insert_constraint_in_alerts).render(
        alerts_bulk_table=alerts_bulk_table,
        constraint_table=constraint_table_name,
        constraint_trigger_table=constraint_trigger_table_name,
        constraint_combination_table=constraint_combination_table_name,
        target_class="entities",
        sqlite=True)
    statementsets.append(sql_command_yaml)
    sqlite += sql_command_sqlite
    sqlite += '\n'
    tables.append(utils.class_to_obj_name(configs.constraint_table_object_name))
    # Fail loud. Every problem is collected first so one build reports all of
    # them, rather than making the author rediscover them one at a time.
    compiled = {node.removesuffix(OWN_PARAMS_SUFFIX)
                for node, _ in property_nodes if property_nodes[(node, _)]}
    problems = sorted(depth_problems) + unsupported_shapes(g, compiled)
    if problems:
        raise UnsupportedShape(
            'the following shapes cannot be compiled and would be silently '
            'unvalidated:\n  - ' + '\n  - '.join(problems))

    return sqlite, (statementsets, tables, views, value_statementsets, postgres_constraints)
