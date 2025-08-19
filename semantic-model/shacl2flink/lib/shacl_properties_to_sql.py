from rdflib import Graph
from rdflib.namespace import SH
import os
import re
import sys
import ruamel.yaml
from jinja2 import Template
from lib.utils import get_full_path_of_shacl_property, NGSILD

file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import configs  # noqa: E402
import utils  # noqa: E402


MAX_SUBPROPERTY_DEPTH = 1

yaml = ruamel.yaml.YAML()

alerts_bulk_table = configs.alerts_bulk_table_name
alerts_bulk_table_object = configs.alerts_bulk_table_object_name
constraint_table_name = configs.constraint_table_name
constraint_trigger_table_name = configs.constraint_trigger_table_name
constraint_combination_table_name = configs.constraint_combination_table_name

sparql_get_all_relationships = """
SELECT ?nodeshape ?targetclass ?inheritedTargetclass ?propertypath ?mincount ?maxcount ?attributeclass ?severitycode ?property ?innerOr
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?inheritedTargetclass rdfs:subClassOf* ?targetclass .
    ?nodeshape sh:property/(sh:or/rdf:rest*/rdf:first/sh:property)* ?property .
    ?property
        sh:path ?propertypath ;
        sh:or ?outerOr .
        ?outerOr rdf:rest*/rdf:first ?clause .
        OPTIONAL{?clause sh:maxCount ?maxcount ; }
        OPTIONAL{?clause sh:minCount ?mincount ; }
        OPTIONAL{?clause sh:severity ?severity . ?severity rdfs:label ?severitycode .}
        ?clause     sh:property    ?innerProp .
        ?innerProp  sh:path ngsi-ld:hasObject ;
        sh:or   ?innerOr .
        ?innerOr rdf:rest*/rdf:first ?innerclause .
        OPTIONAL { ?innerclause sh:class ?attributeclass ; }
}
order by ?inhertiedTargetclass
"""  # noqa: E501

sparql_get_all_properties = """
SELECT
    ?nodeshape ?targetclass ?inheritedTargetclass ?propertypath ?mincount ?maxcount ?attributeclass ?nodekind
    ?minexclusive ?maxexclusive ?mininclusive ?maxinclusive ?minlength ?maxlength ?pattern ?severitycode ?property ?valuepath ?innerOr ?hasValue
    (GROUP_CONCAT(CONCAT('"', ?in, '"'); separator=',') as ?ins)
    (GROUP_CONCAT(?datatype; separator=',') as ?datatypes)
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?inheritedTargetclass rdfs:subClassOf* ?targetclass .
    ?nodeshape sh:property/(sh:or/rdf:rest*/rdf:first/sh:property)* ?property .
      ## First-level property
  ?property
    sh:path ?propertypath ;
    sh:or   ?outerOr .
    ?outerOr rdf:rest*/rdf:first ?clause .
    OPTIONAL { ?clause  sh:minCount ?mincount ; }
    OPTIONAL { ?clause sh:maxCount ?maxcount ; }
    OPTIONAL { ?clause sh:severity ?severity . ?severity rdfs:label ?severitycode .}
    ?clause     sh:property    ?innerProp .
    ?innerProp  sh:path        ?valuepath ;
        sh:or   ?innerOr .
    ?innerOr rdf:rest*/rdf:first ?innerclause .
    FILTER(?valuepath = ngsi-ld:hasValue || ?valuepath = ngsi-ld:hasValueList || ?valuepath = ngsi-ld:hasJSON)
    OPTIONAL { ?innerclause sh:minExclusive ?minexclusive ; }
    OPTIONAL { ?innerclause sh:maxExclusive ?maxexclusive ; }
    OPTIONAL { ?innerclause sh:minInclusive ?mininclusive ; }
    OPTIONAL { ?innerclause sh:maxInclusive ?maxinclusive ; }
    OPTIONAL { ?innerclause sh:minLength ?minlength ; }
    OPTIONAL { ?innerclause sh:maxLength ?maxlength ; }
    OPTIONAL { ?innerclause sh:pattern ?pattern ; }
    OPTIONAL { ?innerclause sh:in/(rdf:rest*/rdf:first)+ ?in ; }
    OPTIONAL { ?innerclause sh:hasValue ?hasValue ; }
    OPTIONAL { ?innerclause sh:class ?attributeclass ; }
    OPTIONAL { ?innerclause sh:nodeKind ?nodekind ; }
    OPTIONAL { ?innerclause sh:or/rdf:rest*/rdf:first ?dtShape  . ?dtShape sh:datatype ?datatype .}
    OPTIONAL { ?innerclause sh:property/sh:or/rdf:rest*/rdf:first ?dtShape  . ?dtShape sh:datatype ?datatype .}
    OPTIONAL { ?innerclause sh:datatype ?datatype ; }
}
GROUP BY ?nodeshape ?targetclass ?propertypath ?mincount ?maxcount ?attributeclass ?nodekind
    ?minexclusive ?maxexclusive ?mininclusive ?maxinclusive ?minlength ?maxlength ?pattern ?severitycode ?inheritedTargetclass ?property ?valuepath ?innerOr ?hasValue
order by ?inheritedTargetclass
"""  # noqa: E501
sql_check_relationship_base = """
            INSERT {% if sqlite %}OR REPlACE{% endif %} INTO {{alerts_bulk_table}}
            WITH A1 as (
                    SELECT /*+ STATE_TTL('D' = '0d') */ A.id AS this,
                        A.`type` as typ,
                        IFNULL(A.`deleted`, false) as edeleted,
                        C.`type` AS entity,
                        COALESCE(E.`type`, B.`type`) AS link,
                        COALESCE(E.`nodeType`, B.`nodeType`) as nodeType,
                        COALESCE(E.`deleted`, B.`deleted`) as `adeleted`,
                        COALESCE(E.`datasetId`, B.`datasetId`) as `index`,
                        D.targetClass as targetClass,
                        COALESCE(D.subpropertyPath, D.propertyPath) as propertyPath,
                        CASE WHEN D.subpropertyPath IS NULL THEN '' ELSE D.propertyPath || '[' || CASE WHEN B.`datasetId` = '@none' THEN '0' ELSE B.`datasetId` END || '] ==> ' END as parentPath,
                        COALESCE(D.subpropertyPath, D.propertyPath) || '[' || CASE WHEN  COALESCE(E.`datasetId`, B.`datasetId`) = '@none' THEN '0' ELSE  COALESCE(E.`datasetId`, B.`datasetId`) END || ']' as printPath,
                        D.propertyClass as propertyClass,
                        D.attributeType as attributeType,
                        D.maxCount as maxCount,
                        D.minCount as minCount,
                        D.severity as severity,
                        D.id as constraint_id
                    FROM {{target_class}}_view AS A JOIN {{constraint_table}} as D ON A.`type` = D.targetClass
                    LEFT JOIN attributes_view AS B ON B.name = D.propertyPath and B.entityId = A.id and B.parentId IS NULL and COALESCE(B.`deleted`, false) = false
                    LEFT JOIN attributes_view AS E ON E.name = D.subpropertyPath and E.entityId = A.id and E.parentId = B.id and COALESCE(E.`deleted`, false) = false
                    LEFT JOIN {{target_class}}_view AS C ON COALESCE(E.`attributeValue`, B.`attributeValue`) = C.id and COALESCE(C.`deleted`, false) = false
                    WHERE (D.subpropertyPath IS NULL or E.id is not NULL) and D.attributeType = 'https://uri.etsi.org/ngsi-ld/Relationship'
            )
"""  # noqa: E501

sql_check_relationship_property_class = """
            {% set constraint_cond%}
            NOT edeleted AND NOT IFNULL(adeleted, false) AND link IS NOT NULL AND entity IS NULL
            {% endset %}
            SELECT this AS resource,
                'ClassConstraintComponent(' || `parentPath` || `printPath` || ')' AS event,
                `constraint_id` as constraint_id,
                true as triggered,
                `severity` AS severity,
                'Model validation for relationship' || `propertyPath` || 'failed for '|| this || '. Relationship not linked to existing entity of type ' ||  `propertyClass` || '.'
                    as `text`
                {%- if sqlite %}
                ,CURRENT_TIMESTAMP
                {%- endif %}
            FROM A1 WHERE A1.propertyClass IS NOT NULL and `index` IS NOT NULL and {{ constraint_cond }}
"""  # noqa: E501

sql_check_relationship_property_count = """
            {% set constraint_cond %}
            NOT edeleted AND (SUM(CASE WHEN NOT COALESCE(adeleted, FALSE) AND link IS NOT NULL THEN 1 ELSE 0 END) > SQL_DIALECT_CAST(`maxCount` AS INTEGER)
                                            OR SUM(CASE WHEN NOT COALESCE(adeleted, FALSE) AND link IS NOT NULL THEN 1 ELSE 0 END) < SQL_DIALECT_CAST(`minCount` AS INTEGER))
            {% endset %}
            SELECT this AS resource,
                'CountConstraintComponent(' || `parentPath` || `propertyPath` || ')' AS event,
                `constraint_id` as constraint_id,
                true as triggered,
                `severity` AS severity,
               'Model validation for relationship ' || `propertyPath` || 'failed for ' || this || ' . Found ' ||
                            SQL_DIALECT_CAST(SUM(CASE WHEN NOT COALESCE(adeleted, FALSE) AND link IS NOT NULL THEN 1 ELSE 0 END) AS STRING) || ' relationships instead of [' || `minCount` || ', ' || `maxCount` || ']!'
                    as `text`
                {%- if sqlite %}
                ,CURRENT_TIMESTAMP
                {%- endif %}
            FROM A1 WHERE `minCount` is NOT NULL or `maxCount` is NOT NULL
            GROUP BY this, edeleted, propertyPath, maxCount, minCount, severity, constraint_id, parentPath
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
                'Model validation for relationship ' || `propertyPath` || ' failed for ' || this || ' . Either NodeType '|| nodeType || ' is not an IRI or type is not a Relationship.'
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
                   IFNULL(A.`deleted`, false) as edeleted,
                   COALESCE(E.`attributeValue` ,B.`attributeValue`) as val,
                   COALESCE(E.`nodeType`, B.`nodeType`) as nodeType,
                   COALESCE(E.`type`, B.`type`) as attr_typ,
                   COALESCE(E.`deleted`, B.`deleted`) as `adeleted`,
                   COALESCE(E.`valueType`, B.`valueType`) as `valueType`,
                   C.subject as foundVal,
                   C.object as foundClass,
                   COALESCE(E.`datasetId`, B.`datasetId`) as `index`,
                   COALESCE(D.subpropertyPath, D.propertyPath) as propertyPath,
                   CASE WHEN D.subpropertyPath IS NULL THEN '' ELSE D.propertyPath || '[' || CASE WHEN B.`datasetId` = '@none' THEN '0' ELSE B.`datasetId` END || '] ==> ' END as parentPath,
                   COALESCE(D.subpropertyPath, D.propertyPath) || '[' || CASE WHEN  COALESCE(E.`datasetId`, B.`datasetId`) = '@none' THEN '0' ELSE  COALESCE(E.`datasetId`, B.`datasetId`) END || ']' as printPath,
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
            LEFT JOIN attributes_view AS B ON D.propertyPath = B.name and B.entityId = A.id and B.parentId IS NULL
             LEFT JOIN attributes_view AS E ON D.subpropertyPath = E.name and E.entityId = A.id and B.id = E.parentId
            LEFT JOIN {{rdf_table_name}} as C ON C.subject = '<' || COALESCE(E.attributeValue, B.attributeValue) || '>'
                and C.predicate = '<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>' and C.object = '<' || D.propertyClass || '>'
             WHERE (D.subpropertyPath IS NULL or E.id is not NULL) and attributeType IN ('https://uri.etsi.org/ngsi-ld/Property', 'https://uri.etsi.org/ngsi-ld/ListProperty', 'https://uri.etsi.org/ngsi-ld/JsonProperty')
            )
"""  # noqa: E501

sql_check_property_count = """
{% set constraint_cond%}
    NOT edeleted AND (SUM(DISTINCT CASE WHEN NOT COALESCE(adeleted, FALSE) and attr_typ IS NOT NULL THEN 1 ELSE 0 END) > SQL_DIALECT_CAST(`maxCount` AS INTEGER)
                                    OR SUM(DISTINCT CASE WHEN NOT COALESCE(adeleted, FALSE) and attr_typ is NOT NULL THEN 1 ELSE 0 END) < SQL_DIALECT_CAST(`minCount` AS INTEGER))
{% endset %}
SELECT this AS resource,
    'CountConstraintComponent(' || `parentPath` || `propertyPath` || ')' AS event,
    `constraint_id` as constraint_id,
    true as triggered,
    `severity` AS severity,
   'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '.  Found ' ||
                            SQL_DIALECT_CAST(SUM(DISTINCT CASE WHEN NOT COALESCE(adeleted, FALSE) and attr_typ IS NOT NULL THEN 1 ELSE 0 END) AS STRING) || ' relationships instead of [' || IFNULL('[' || `minCount`, '0')
                            || ', ' || IFNULL(`maxCount` || ']', '[') || '!'
        as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1  WHERE `minCount` is NOT NULL or `maxCount` is NOT NULL
GROUP BY this, typ, propertyPath, minCount, maxCount, severity, edeleted, constraint_id, parentPath
HAVING {{ constraint_cond }}
"""  # noqa: E501

sql_check_property_iri_class = """
{% set constraint_cond%}
NOT edeleted AND attr_typ IS NOT NULL AND NOT IFNULL(adeleted, false) AND (val is NULL OR foundVal is NULL)
{% endset %}

SELECT this AS resource,
    'DatatypeConstraintComponent(' || `parentPath` || `printPath` || ')' AS event,
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
NOT edeleted AND NOT IFNULL(adeleted, false) AND (nodeType <> `propertyNodetype` OR attr_typ <> attributeType)
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
FROM A1 WHERE propertyNodetype IS NOT NULL and `index` IS NOT NULL AND {{ constraint_cond }}
"""  # noqa: E501

sql_check_property_minmax = """
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
    'Model validation for Property propertyPath failed for ' || this || '. Value ' || IFNULL(val, 'NULL') || ' is not allowed.'
        as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1 where `ins` IS NOT NULL and `index` IS NOT NULL AND {{ constraint_cond }}
"""  # noqa: E501

sql_check_literal_datatypes = """
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
                WHEN NOT ({{ common_datatypes }}) THEN false -- we check only common datatypes
                ELSE NOT ({{ check_datatypes }}) -- if val is defined and datatypes are known, we check the value
            END
        WHEN propertyNodetype = '@json' THEN
            CASE
                WHEN {%- if sqlite %} json_valid(`val`) AND json_type(`val`) = 'object' {%- else %} `val` IS JSON OBJECT {%- endif %} THEN false
                ELSE true
            END
        WHEN propertyNodetype = '@list' THEN
            CASE
                WHEN {%- if sqlite %} json_valid(`val`) AND json_type(`val`) = 'array' {%- else %} `val` IS JSON ARRAY {%- endif %} THEN false
                ELSE true
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
 MAX(t.text) AS text
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


sql_combine_or_into_alerts = """
INSERT{% if sqlite %} OR REPlACE {% endif %} INTO constraint_trigger_table
WITH
  -- 1) How many members each OR-rule has
  needed AS (
    SELECT /*+ STATE_TTL('constraint_combination_table' = '0d') */
      target_constraint_id,
      COUNT(*) AS needed_count
    FROM
      constraint_combination_table
    WHERE
      operation = 'OR'
    GROUP BY
      target_constraint_id
  ),

  -- 2) For each resource/target, find how many distinct members actually triggered
  --    and collect their events
  fired AS (
    SELECT /*+ STATE_TTL('comb' = '0d') */ DISTINCT
      t.resource,
      comb.target_constraint_id,
      nm.needed_count as needed_count,
      COUNT(DISTINCT CASE WHEN t.triggered THEN t.constraint_id ELSE NULL END) AS fired_count,
      {% if sqlite %}
      -- SQLite: GROUP_CONCAT only takes one argument when DISTINCT
      'OR Constraint id ' || comb.target_constraint_id AS events,
      'AND(' || GROUP_CONCAT(DISTINCT t.text) || ')' AS texts
      {% else %}
      -- Calcite: LISTAGG without DISTINCT
      'OR Constraint id ' || CAST(comb.target_constraint_id as STRING) AS events,
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
     AND comb.operation            = 'OR'
    JOIN
      needed AS nm
      ON nm.target_constraint_id   = comb.target_constraint_id
    GROUP BY
      t.resource,
      comb.target_constraint_id,
      nm.needed_count
  )

SELECT /*+ STATE_TTL('ct' = '0d') */
  f.resource                             AS resource,
  f.events                               AS event,
  f.target_constraint_id                 AS constraint_id,
     (f.needed_count = IFNULL(f.fired_count, 0)) AS triggered,
     CASE WHEN f.needed_count = IFNULL(f.fired_count, 0) THEN ct.severity ELSE 'ok' END AS severity,
CASE WHEN f.needed_count = IFNULL(f.fired_count, 0) THEN f.texts ELSE 'All ok' END AS text
  {% if sqlite %}
    ,CURRENT_TIMESTAMP AS ts
    {% endif %}
FROM  constraint_table AS ct JOIN  fired AS f  ON ct.id = f.target_constraint_id;
;
"""


def create_relationship_sql():
    sql_command_yaml = Template(sql_check_relationship_base).render(
        alerts_bulk_table=constraint_trigger_table_name,
        constraint_table=constraint_table_name,
        target_class="entities",
        sqlite=False)
    sql_command_sqlite = Template(sql_check_relationship_base).render(
        alerts_bulk_table=constraint_trigger_table_name,
        constraint_table=constraint_table_name,
        target_class="entities",
        sqlite=True)
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

    sql_command_yaml = Template(
        sql_check_property_iri_base).render(
        alerts_bulk_table=constraint_trigger_table_name,
        constraint_table=constraint_table_name,
        target_class="entities",
        rdf_table_name=configs.rdf_table_name,
        sqlite=False
    )
    sql_command_sqlite = Template(sql_check_property_iri_base).render(
        alerts_bulk_table=constraint_trigger_table_name,
        constraint_table=constraint_table_name,
        target_class="entities",
        rdf_table_name=configs.rdf_table_name,
        sqlite=True
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
        sqlite=False
    )
    sql_command_sqlite += Template(sql_check_literal_datatypes).render(
        constraintname="DatatypeConstraintComponent",
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

    property_nodes = {}
    qres = g.query(sparql_get_all_relationships, initNs=prefixes)
    for row in qres:
        paths = get_full_path_of_shacl_property(g, row.property)
        if len(paths) > MAX_SUBPROPERTY_DEPTH + 1:
            print(f"Warning, subproperty depth {len(paths)} not supported in paths {paths}")
            continue
        check = utils.init_constraint_check()
        target_class = row.inheritedTargetclass.toPython() \
            if row.targetclass else None
        property_path = row.propertypath.toPython() if row.propertypath \
            else None
        property_class = row.attributeclass.toPython() if row.attributeclass \
            else None
        mincount = row.mincount.toPython() if row.mincount else 0
        maxcount = row.maxcount.toPython() if row.maxcount else None
        property = row.property.toPython()
        if (property, target_class) not in property_nodes.keys():
            property_nodes[(property, target_class)] = []
        severitycode = row.severitycode.toPython() if row.severitycode \
            else 'warning'
        check['targetClass'] = target_class
        if len(paths) >= 2:
            check['subpropertyPath'] = property_path
            check['propertyPath'] = paths[1]
        else:
            check['propertyPath'] = property_path
            check['subpropertyPath'] = None
        check['propertyClass'] = property_class
        check['attributeType'] = 'https://uri.etsi.org/ngsi-ld/Relationship'
        check['maxCount'] = maxcount
        check['minCount'] = mincount
        check['severity'] = severitycode
        check['id'] = constraint_id_counter
        constraint_checks.append(check)
        property_nodes[(property, target_class)].append(constraint_id_counter)
        constraint_id_counter += 1
    # Get all NGSI-LD Properties
    qres = g.query(sparql_get_all_properties, initNs=prefixes)
    for row in qres:
        paths = get_full_path_of_shacl_property(g, row.property)
        if len(paths) > MAX_SUBPROPERTY_DEPTH + 1:
            print(f"Warning, subproperty depth {len(paths)} not supported in paths {paths}")
            continue
        check = utils.init_constraint_check()
        nodeshape = row.nodeshape.toPython()
        target_class = row.inheritedTargetclass.toPython() \
            if row.targetclass else None
        property_path = row.propertypath.toPython() if row.propertypath \
            else None
        property_class = row.attributeclass.toPython() if row.attributeclass\
            else None
        mincount = row.mincount.toPython() if row.mincount else None
        maxcount = row.maxcount.toPython() if row.maxcount else None
        property = row.property.toPython()
        if (property, target_class) not in property_nodes.keys():
            property_nodes[(property, target_class)] = []
        severitycode = row.severitycode.toPython() if row.severitycode \
            else 'warning'
        nodekind = row.nodekind if row.nodekind else None
        valuepath = row.valuepath
        min_exclusive = row.minexclusive.toPython() if row.minexclusive \
            is not None else None
        max_exclusive = row.maxexclusive.toPython() if row.maxexclusive \
            else None
        min_inclusive = row.mininclusive.toPython() if row.mininclusive \
            is not None else None
        max_inclusive = row.maxinclusive.toPython() if row.maxinclusive \
            else None
        min_length = row.minlength.toPython() if row.minlength is not None \
            else None
        max_length = row.maxlength.toPython() if row.maxlength is not None \
            else None
        pattern = row.pattern.toPython() if row.pattern is not None else None
        ins = row.ins.toPython() if str(row.ins) != '' else None
        datatypes = row.datatypes.toPython() if str(row.datatypes) != '' else None
        hasValue = row.hasValue if row.hasValue is not None else None

        check['targetClass'] = target_class
        if len(paths) >= 2:
            check['subpropertyPath'] = property_path
            check['propertyPath'] = paths[1]
        else:
            check['propertyPath'] = property_path
            check['subpropertyPath'] = None
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
        property_nodes[(property, target_class)].append(constraint_id_counter)
        constraint_id_counter += 1

    for property_node in property_nodes.keys():
        if len(property_nodes[property_node]) == 1:
            constraint_id = property_nodes[property_node][0]
            # Only single "OR" mean that this can be published directly
            # Add Publish rule to direct publish it to alerts
            combination = {}
            combination['operation'] = 'PUBLISH'
            combination['member_constraint_id'] = constraint_id
            combination['target_constraint_id'] = -1
            constraint_combination.append(combination)
        else:
            target_constraint_id = constraint_id_counter
            constraint_id_counter += 1
            or_combination = {}
            or_combination['operation'] = 'PUBLISH'
            or_combination['member_constraint_id'] = target_constraint_id
            or_combination['target_constraint_id'] = -1
            constraint_combination.append(or_combination)
            check = utils.init_constraint_check()
            severity_id = None
            if len(property_nodes[property_node]) > 0:
                severity_id = property_nodes[property_node][0]
            # We take severity of first object for now
            severity_object = next((d for d in constraint_checks if d.get('id') == severity_id), None)
            check['id'] = target_constraint_id
            check['severity'] = severity_object['severity']
            constraint_checks.append(check)
            for id in property_nodes[property_node]:
                combination = {}
                combination['operation'] = 'OR'
                combination['member_constraint_id'] = id
                combination['target_constraint_id'] = target_constraint_id
                constraint_combination.append(combination)

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

    sql_command_yaml = Template(sql_combine_or_into_alerts).render(
        alerts_bulk_table=alerts_bulk_table,
        constraint_trigger_table=constraint_trigger_table_name,
        constraint_combination_table=constraint_combination_table_name,
        sqlite=False)
    sql_command_sqlite = Template(sql_combine_or_into_alerts).render(
        alerts_bulk_table=alerts_bulk_table,
        constraint_trigger_table=constraint_trigger_table_name,
        constraint_combination_table=constraint_combination_table_name,
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
    return sqlite, (statementsets, tables, views, value_statementsets, postgres_constraints)
