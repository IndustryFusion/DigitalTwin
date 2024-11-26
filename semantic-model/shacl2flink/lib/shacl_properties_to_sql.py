from rdflib import Graph
from rdflib.namespace import SH
import os
import sys
import ruamel.yaml
from jinja2 import Template

file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import configs  # noqa: E402
import utils  # noqa: E402


yaml = ruamel.yaml.YAML()

alerts_bulk_table = configs.alerts_bulk_table_name
alerts_bulk_table_object = configs.alerts_bulk_table_object_name

sparql_get_all_relationships = """
SELECT ?nodeshape ?targetclass ?inheritedTargetclass ?propertypath ?mincount ?maxcount ?attributeclass ?severitycode
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?inheritedTargetclass rdfs:subClassOf* ?targetclass .
    ?nodeshape sh:property [
        sh:path ?propertypath ;
        sh:property [
            sh:path ngsi-ld:hasObject ;
            sh:class ?attributeclass ;
        ]
    ] .
    OPTIONAL{?nodeshape sh:property [ sh:path ?propertypath; sh:maxCount ?maxcount ]}
    OPTIONAL{?nodeshape sh:property [ sh:path ?propertypath; sh:minCount ?mincount ]}
    OPTIONAL {
        ?nodeshape sh:property [
            sh:path ?propertypath;
            sh:severity ?severity ;
        ] .
        ?severity rdfs:label ?severitycode .
    }
}
order by ?inhertiedTargetclass
"""  # noqa: E501

sparql_get_all_properties = """
SELECT
    ?nodeshape ?targetclass ?inheritedTargetclass ?propertypath ?mincount ?maxcount ?attributeclass ?nodekind
    ?minexclusive ?maxexclusive ?mininclusive ?maxinclusive ?minlength ?maxlength ?pattern ?severitycode
    (GROUP_CONCAT(CONCAT('"', ?in, '"'); separator=',') as ?ins)
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?inheritedTargetclass rdfs:subClassOf* ?targetclass .
    ?nodeshape sh:property [
        sh:path ?propertypath ;
        sh:property [
            sh:path ngsi-ld:hasValue ;
            sh:nodeKind ?nodekind ;
        ] ;

    ] .
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath ; sh:minCount ?mincount ; ] }
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath ; sh:maxCount ?maxcount ; ] }
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath ; sh:property [sh:path ngsi-ld:hasValue ; sh:minExclusive ?minexclusive ;] ; ] }
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath ; sh:property [sh:path ngsi-ld:hasValue ; sh:maxExclusive ?maxexclusive ;] ; ] }
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath ; sh:property [sh:path ngsi-ld:hasValue ; sh:minInclusive ?mininclusive ;] ; ] }
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath ; sh:property [sh:path ngsi-ld:hasValue ; sh:maxInclusive ?maxinclusive ;] ; ] }
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath ; sh:property [sh:path ngsi-ld:hasValue ; sh:minLength ?minlength ;] ; ] }
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath ; sh:property [sh:path ngsi-ld:hasValue ; sh:maxLength ?maxlength ;] ; ] }
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath ; sh:property [sh:path ngsi-ld:hasValue ; sh:pattern ?pattern ;] ; ] }
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath ; sh:property [sh:path ngsi-ld:hasValue ; sh:in/(rdf:rest*/rdf:first)+ ?in ;] ; ] }
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath ; sh:property [sh:path ngsi-ld:hasValue ; sh:class ?attributeclass ;] ; ] }
    OPTIONAL { ?nodeshape sh:property [ sh:path ?propertypath; sh:severity ?severity ; ] . ?severity rdfs:label ?severitycode .}
}
GROUP BY ?nodeshape ?targetclass ?propertypath ?mincount ?maxcount ?attributeclass ?nodekind
    ?minexclusive ?maxexclusive ?mininclusive ?maxinclusive ?minlength ?maxlength ?pattern ?severitycode ?inheritedTargetclass
order by ?inheritedTargetclass
"""  # noqa: E501
sql_check_relationship_base = """
            INSERT {% if sqlite %}OR REPlACE{% endif %} INTO {{alerts_bulk_table}}
            WITH A1 as (
                    SELECT A.id AS this,
                        A.`type` as typ,
                        IFNULL(A.`deleted`, false) as edeleted,
                        C.`type` AS entity,
                        B.`type` AS link,
                        B.`nodeType` as nodeType,
                        B.`deleted` as `adeleted`,
                        B.`datasetId` as `index`,
                        D.targetClass as targetClass,
                        D.propertyPath as propertyPath,
                        D.propertyClass as propertyClass,
                        D.maxCount as maxCount,
                        D.minCount as minCount,
                        D.severity as severity
                    FROM {{target_class}}_view AS A JOIN `relationshipChecksTable` as D ON A.`type` = D.targetClass
                    LEFT JOIN attributes_view AS B ON B.name = D.propertyPath and B.entityId = A.id
                    LEFT JOIN {{target_class}}_view AS C ON B.`attributeValue` = C.id and B.`type` = 'https://uri.etsi.org/ngsi-ld/Relationship'

            )
"""  # noqa: E501

sql_check_relationship_property_class = """
            SELECT this AS resource,
                'ClassConstraintComponent(' || `propertyPath` || '[' || CASE WHEN `index` = '@none' THEN '0' ELSE `index` END || '])' AS event,
                'Development' AS environment,
                {% if sqlite %}
                '[SHACL Validator]' AS service,
                {% else %}
                ARRAY ['SHACL Validator'] AS service,
                {% endif %}
                CASE WHEN NOT edeleted AND NOT IFNULL(adeleted, false) AND link IS NOT NULL AND entity IS NULL THEN `severity`
                    ELSE 'ok' END AS severity,
                'customer'  customer,

                CASE WHEN NOT edeleted AND NOT IFNULL(adeleted, false) AND link IS NOT NULL AND entity IS NULL
                        THEN 'Model validation for relationship' || `propertyPath` || 'failed for '|| this || '. Relationship not linked to existing entity of type ' ||  `propertyClass` || '.'
                    ELSE 'All ok' END as `text`
                {%- if sqlite %}
                ,CURRENT_TIMESTAMP
                {%- endif %}
            FROM A1 WHERE A1.propertyClass IS NOT NULL and `index` IS NOT NULL
"""  # noqa: E501

sql_check_relationship_property_count = """
            SELECT this AS resource,
                'CountConstraintComponent(' || `propertyPath` || ')' AS event,
                'Development' AS environment,
                {% if sqlite %}
                '[SHACL Validator]' AS service,
                {% else %}
                ARRAY ['SHACL Validator'] AS service,
                {% endif %}
                CASE WHEN NOT edeleted AND (count(CASE WHEN NOT IFNULL(adeleted, false) THEN link ELSE NULL END) > SQL_DIALECT_CAST(`maxCount` AS INTEGER)
                                            OR count(CASE WHEN NOT IFNULL(adeleted, false) THEN link ELSE NULL END) < SQL_DIALECT_CAST(`minCount` AS INTEGER))
                    THEN `severity`
                    ELSE 'ok' END AS severity,
                'customer'  customer,
                CASE WHEN NOT edeleted AND (count(CASE WHEN NOT IFNULL(adeleted, false) THEN link ELSE NULL END) > SQL_DIALECT_CAST(`maxCount` AS INTEGER)
                                            OR count(CASE WHEN NOT IFNULL(adeleted, false) THEN link ELSE NULL END) < SQL_DIALECT_CAST(`minCount` AS INTEGER))
                    THEN
                        'Model validation for relationship ' || `propertyPath` || 'failed for ' || this || ' . Found ' ||
                            SQL_DIALECT_CAST(count(CASE WHEN NOT IFNULL(adeleted, false) THEN link ELSE NULL END) AS STRING) || ' relationships instead of
                            [' || `minCount` || ', ' || `maxCount` || ']!'
                    ELSE 'All ok' END as `text`
                {%- if sqlite %}
                ,CURRENT_TIMESTAMP
                {%- endif %}
            FROM A1 WHERE `minCount` is NOT NULL or `maxCount` is NOT NULL
            group by this, edeleted, propertyPath, maxCount, minCount, severity
"""  # noqa: E501

sql_check_relationship_nodeType = """
            SELECT this AS resource,
                'NodeKindConstraintComponent(' || `propertyPath` || '[' || CASE WHEN `index` = '@none' THEN '0' ELSE `index` END || '])' AS event,
                'Development' AS environment,
                {% if sqlite %}
                '[SHACL Validator]' AS service,
                {% else %}
                ARRAY ['SHACL Validator'] AS service,
                {% endif %}
                CASE WHEN NOT edeleted AND NOT IFNULL(`adeleted`, false) AND (nodeType <> '{{ property_nodetype }}')
                    THEN `severity`
                    ELSE 'ok' END AS severity,
                'customer'  customer,
                CASE WHEN NOT edeleted AND NOT IFNULL(`adeleted`, false) AND (nodeType <> '{{ property_nodetype }}')
                    THEN
                        'Model validation for relationship ' || `propertyPath` || ' failed for ' || this || ' . NodeType is '|| nodeType || ' but must be an IRI.'
                    ELSE 'All ok' END as `text`
                {%- if sqlite %}
                ,CURRENT_TIMESTAMP
                {%- endif %}
            FROM A1 WHERE `index` IS NOT NULL
"""  # noqa: E501

sql_check_property_iri_base = """
INSERT {% if sqlite %} OR REPlACE{% endif %} INTO {{alerts_bulk_table}}
WITH A1 AS (SELECT A.id as this,
                   A.`type` as typ,
                   IFNULL(A.`deleted`, false) as edeleted,
                   B.`attributeValue` as val,
                   B.`nodeType` as nodeType,
                   B.`type` as attr_typ,
                   B.`deleted` as `adeleted`,
                   C.subject as foundVal,
                   C.object as foundClass,
                   B.`datasetId` as `index`,
                   D.propertyPath as propertyPath,
                   D.propertyClass as propertyClass,
                   D.propertyNodetype as propertyNodetype,
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
                   D.ins as ins
                   FROM `{{target_class}}_view` AS A JOIN `propertyChecksTable` as D ON A.`type` = D.targetClass
            LEFT JOIN attributes_view AS B ON D.propertyPath = B.name and B.entityId = A.id
            LEFT JOIN {{rdf_table_name}} as C ON C.subject = '<' || B.`attributeValue` || '>' and B.`type` = 'https://uri.etsi.org/ngsi-ld/Property'
                and C.predicate = '<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>' and C.object = '<' || D.propertyClass || '>'
            )
"""  # noqa: E501

sql_check_property_count = """
SELECT this AS resource,
    'CountConstraintComponent(' || `propertyPath` || ')' AS event,
    'Development' AS environment,
    {%- if sqlite %}
    '[SHACL Validator]' AS service,
    {%- else %}
    ARRAY ['SHACL Validator'] AS service,
    {%- endif %}
    CASE WHEN NOT edeleted AND (count(CASE WHEN NOT IFNULL(adeleted, false) THEN attr_typ ELSE NULL END) > SQL_DIALECT_CAST(`maxCount` AS INTEGER) OR  count(CASE WHEN NOT IFNULL(adeleted, false) THEN attr_typ ELSE NULL END) < SQL_DIALECT_CAST(`minCount` AS INTEGER))
        THEN `severity`
        ELSE 'ok' END AS severity,
    'customer'  customer,
    CASE WHEN NOT edeleted AND (count(CASE WHEN NOT IFNULL(adeleted, false) THEN attr_typ ELSE NULL END) > SQL_DIALECT_CAST(`maxCount` AS INTEGER) OR count(CASE WHEN NOT IFNULL(adeleted, false) THEN attr_typ ELSE NULL END) < SQL_DIALECT_CAST(`minCount` AS STRING))
        THEN 'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '.  Found ' || SQL_DIALECT_CAST(count(CASE WHEN NOT IFNULL(adeleted, false) THEN attr_typ ELSE NULL END) AS STRING) || ' relationships instead of
                            [' || IFNULL('[' || `minCount`, '[0') || IFNULL(`maxCount` || ']', '[') || '!'
        ELSE 'All ok' END as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1  WHERE `minCount` is NOT NULL or `maxCount` is NOT NULL
group by this, typ, propertyPath, minCount, maxCount, severity, edeleted
"""  # noqa: E501

sql_check_property_iri_class = """
SELECT this AS resource,
    'DatatypeConstraintComponent(' || `propertyPath` || '[' || CASE WHEN `index` = '@none' THEN '0' ELSE `index` END || '])' AS event,
    'Development' AS environment,
    {%- if sqlite %}
    '[SHACL Validator]' AS service,
    {%- else %}
    ARRAY ['SHACL Validator'] AS service,
    {%- endif %}
    CASE WHEN NOT edeleted AND attr_typ IS NOT NULL  AND (val is NULL OR foundVal is NULL)
        THEN `severity`
        ELSE 'ok' END AS severity,
    'customer'  customer,
    CASE WHEN NOT edeleted AND attr_typ IS NOT NULL AND (val is NULL OR foundVal is NULL)
        THEN 'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Invalid value ' || IFNULL(val, 'NULL')  || ' not type of ' || `propertyClass` || '.'
        ELSE 'All ok' END as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1  WHERE propertyNodetype = '@id' and propertyClass IS NOT NULL and NOT IFNULL(adeleted, false) and `index` IS NOT NULL
"""  # noqa: E501

sql_check_property_nodeType = """
SELECT this AS resource,
 'NodeKindConstraintComponent(' || `propertyPath` || '[' || CASE WHEN `index` = '@none' THEN '0' ELSE `index` END || '])' AS event,
    'Development' AS environment,
     {%- if sqlite -%}
    '[SHACL Validator]' AS service,
    {%- else %}
    ARRAY ['SHACL Validator'] AS service,
    {%- endif %}
    CASE WHEN NOT edeleted AND NOT IFNULL(adeleted, false) AND (nodeType <> `propertyNodetype`)
        THEN `severity`
        ELSE 'ok' END AS severity,
    'customer'  customer,
    CASE WHEN NOT edeleted AND NOT IFNULL(adeleted, false) AND (nodeType <> `propertyNodetype`)
        THEN 'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Node is not ' ||
            CASE WHEN `propertyNodetype` = '@id' THEN ' an IRI' ELSE 'a Literal' END
        ELSE 'All ok' END as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1 WHERE propertyNodetype IS NOT NULL and `index` IS NOT NULL
"""  # noqa: E501

sql_check_property_minmax = """
SELECT this AS resource,
 '{{minmaxname}}ConstraintComponent(' || `propertyPath` || '[' || CASE WHEN `index` = '@none' THEN '0' ELSE `index` END || '])' AS event,
    'Development' AS environment,
     {%- if sqlite -%}
    '[SHACL Validator]' AS service,
    {%- else %}
    ARRAY ['SHACL Validator'] AS service,
    {%- endif %}
    CASE WHEN NOT edeleted AND attr_typ IS NOT NULL AND (SQL_DIALECT_CAST(val AS DOUBLE) is NULL or NOT (SQL_DIALECT_CAST(val as DOUBLE) {{ operator }} SQL_DIALECT_CAST(`{{ comparison_value }}` AS DOUBLE)) )
        THEN `severity`
        ELSE 'ok' END AS severity,
    'customer'  customer,
    CASE WHEN NOT edeleted AND attr_typ IS NOT NULL AND (SQL_DIALECT_CAST(val AS DOUBLE) is NULL or NOT (SQL_DIALECT_CAST(val as DOUBLE) {{ operator }} SQL_DIALECT_CAST(`{{ comparison_value }}` AS DOUBLE)) )
        THEN 'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Value ' || IFNULL(val, 'NULL') || ' not comparable with ' || `{{ comparison_value }}` || '.'
        WHEN typ IS NOT NULL AND attr_typ IS NOT NULL AND NOT (SQL_DIALECT_CAST(val as DOUBLE) {{ operator }} SQL_DIALECT_CAST( `{{ comparison_value }}` as DOUBLE) )
        THEN 'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Value ' || IFNULL(val, 'NULL') || ' is not {{ operator }} ' || `{{ comparison_value }}` || '.'
        ELSE 'All ok' END as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1 where `{{ comparison_value}}` IS NOT NULL and `index` IS NOT NULL
"""  # noqa: E501

sql_check_string_length = """
SELECT this AS resource,
 '{{minmaxname}}ConstraintComponent(' || `propertyPath` || '[' || CASE WHEN `index` = '@none' THEN '0' ELSE `index` END || '])' AS event,
    'Development' AS environment,
     {%- if sqlite -%}
    '[SHACL Validator]' AS service,
    {%- else %}
    ARRAY ['SHACL Validator'] AS service,
    {%- endif %}
    CASE WHEN NOT edeleted  AND attr_typ IS NOT NULL AND {%- if sqlite %} LENGTH(val) {%- else  %} CHAR_LENGTH(val) {%- endif %} {{ operator }} SQL_DIALECT_CAST(`{{ comparison_value }}` AS INTEGER)
        THEN `severity`
        ELSE 'ok' END AS severity,
    'customer'  customer,
    CASE WHEN NOT edeleted AND attr_typ IS NOT NULL AND {%- if sqlite %} LENGTH(val) {%- else  %} CHAR_LENGTH(val) {%- endif %} {{ operator }} SQL_DIALECT_CAST(`{{ comparison_value }}` as INTEGER)
        THEN 'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Length of ' || IFNULL(val, 'NULL') || ' is {{ operator }} ' || `{{ comparison_value }}` || '.'
        ELSE 'All ok' END as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1 WHERE `{{ comparison_value }}` IS NOT NULL and `index` IS NOT NULL
"""  # noqa: E501

sql_check_literal_pattern = """
SELECT this AS resource,
 '{{validationname}}ConstraintComponent(' || `propertyPath` || '[' || CASE WHEN `index` = '@none' THEN '0' ELSE `index` END || '])' AS event,
    'Development' AS environment,
     {%- if sqlite -%}
    '[SHACL Validator]' AS service,
    {%- else %}
    ARRAY ['SHACL Validator'] AS service,
    {%- endif %}
    CASE WHEN NOT edeleted AND attr_typ IS NOT NULL AND {%- if sqlite %} NOT (val REGEXP `pattern`) {%- else  %} NOT REGEXP(val, `pattern`) {%- endif %}
        THEN `severity`
        ELSE 'ok' END AS severity,
    'customer'  customer,
    CASE WHEN NOT edeleted AND attr_typ IS NOT NULL AND {%- if sqlite %} NOT (val REGEXP `pattern`) {%- else  %} NOT REGEXP(val, `pattern`) {%- endif %}
        THEN 'Model validation for Property ' || `propertyPath` || ' failed for ' || this || '. Value ' || IFNULL(val, 'NULL') || ' does not match pattern ' || `pattern`
        ELSE 'All ok' END as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1 WHERE `pattern` IS NOT NULL and `index` IS NOT NULL
"""  # noqa: E501

sql_check_literal_in = """
SELECT this AS resource,
 '{{constraintname}}('|| `propertyPath` || '[' || CASE WHEN `index` = '@none' THEN '0' ELSE `index` END || '])' AS event,
    'Development' AS environment,
     {%- if sqlite -%}
    '[SHACL Validator]' AS service,
    {%- else %}
    ARRAY ['SHACL Validator'] AS service,
    {%- endif %}
    CASE WHEN NOT edeleted AND attr_typ IS NOT NULL AND NOT ',' || `ins` || ',' LIKE '%,"' || replace(val, '"', '\\\"') || '",%'
        THEN `severity`
        ELSE 'ok' END AS severity,
    'customer'  customer,
    CASE WHEN NOT edeleted AND attr_typ IS NOT NULL AND NOT ',' || `ins` || ',' LIKE '%,"' || replace(val, '"', '\\\"') || '",%'
        THEN 'Model validation for Property propertyPath failed for ' || this || '. Value ' || IFNULL(val, 'NULL') || ' is not allowed.'
        ELSE 'All ok' END as `text`
        {% if sqlite %}
        ,CURRENT_TIMESTAMP
        {% endif %}
FROM A1 where `ins` IS NOT NULL and `index` IS NOT NULL
"""  # noqa: E501


def create_relationship_sql():
    sql_command_yaml = Template(sql_check_relationship_base).render(
        alerts_bulk_table=alerts_bulk_table,
        target_class="entity",
        sqlite=False)
    sql_command_sqlite = Template(sql_check_relationship_base).render(
        alerts_bulk_table=alerts_bulk_table,
        target_class="entity",
        sqlite=True)
    sql_command_yaml += \
        Template(sql_check_relationship_property_class).render(
            alerts_bulk_table=alerts_bulk_table,
            target_class="entity",
            sqlite=False)
    sql_command_sqlite += \
        Template(sql_check_relationship_property_class).render(
            alerts_bulk_table=alerts_bulk_table,
            target_class="entity",
            sqlite=True)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += \
        Template(sql_check_relationship_property_count).render(
            alerts_bulk_table=alerts_bulk_table,
            target_class="entity",
            sqlite=False)
    sql_command_sqlite += \
        Template(sql_check_relationship_property_count).render(
            alerts_bulk_table=alerts_bulk_table,
            target_class="entity",
            sqlite=True)
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += Template(sql_check_relationship_nodeType).render(
        alerts_bulk_table=alerts_bulk_table,
        property_nodetype='@id',
        property_nodetype_description='an IRI',
        sqlite=False
    )
    sql_command_sqlite += Template(sql_check_relationship_nodeType).render(
        alerts_bulk_table=alerts_bulk_table,
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
        alerts_bulk_table=alerts_bulk_table,
        target_class="entity",
        rdf_table_name=configs.rdf_table_name,
        sqlite=False
    )
    sql_command_sqlite = Template(sql_check_property_iri_base).render(
        alerts_bulk_table=alerts_bulk_table,
        target_class="entity",
        rdf_table_name=configs.rdf_table_name,
        sqlite=True
    )
    sql_command_yaml += Template(
        sql_check_property_nodeType).render(
        alerts_bulk_table=alerts_bulk_table,
        sqlite=False
    )
    sql_command_sqlite += Template(sql_check_property_nodeType).render(
        alerts_bulk_table=alerts_bulk_table,
        sqlite=True
    )
    sql_command_yaml += "\nUNION ALL"
    sql_command_sqlite += "\nUNION ALL"
    sql_command_yaml += \
        Template(sql_check_property_iri_class).render(
            alerts_bulk_table=alerts_bulk_table,
            sqlite=False)
    sql_command_sqlite += \
        Template(sql_check_property_iri_class).render(
            alerts_bulk_table=alerts_bulk_table,
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
        alerts_bulk_table=alerts_bulk_table,
        sqlite=False,
        constraintname="InConstraintComponent"
    )
    sql_command_sqlite += Template(sql_check_literal_in).render(
        alerts_bulk_table=alerts_bulk_table,
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
    sqlite = ''
    # Get all NGSI-LD Relationship

    qres = g.query(sparql_get_all_relationships, initNs=prefixes)
    relationshp_checks = []
    for row in qres:
        check = {}
        target_class = row.inheritedTargetclass.toPython() \
            if row.targetclass else None
        property_path = row.propertypath.toPython() if row.propertypath \
            else None
        property_class = row.attributeclass.toPython() if row.attributeclass \
            else None
        mincount = row.mincount.toPython() if row.mincount else 0
        maxcount = row.maxcount.toPython() if row.maxcount else None
        severitycode = row.severitycode.toPython() if row.severitycode \
            else 'warning'
        check['targetClass'] = target_class
        check['propertyPath'] = property_path
        check['propertyClass'] = property_class
        check['maxCount'] = maxcount
        check['minCount'] = mincount
        check['severity'] = severitycode
        relationshp_checks.append(check)
    # Get all NGSI-LD Properties
    qres = g.query(sparql_get_all_properties, initNs=prefixes)
    property_checks = []
    for row in qres:
        check = {}
        nodeshape = row.nodeshape.toPython()
        target_class = row.inheritedTargetclass.toPython() \
            if row.targetclass else None
        property_path = row.propertypath.toPython() if row.propertypath \
            else None
        property_class = row.attributeclass.toPython() if row.attributeclass\
            else None
        mincount = row.mincount.toPython() if row.mincount else None
        maxcount = row.maxcount.toPython() if row.maxcount else None
        severitycode = row.severitycode.toPython() if row.severitycode \
            else 'warning'
        nodekind = row.nodekind
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

        check['targetClass'] = target_class
        check['propertyPath'] = property_path
        check['propertyClass'] = property_class
        check['propertyNodetype'] = '@id' if nodekind == SH.IRI else '@value'
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
        ins_is_broken = False
        if ins:
            for in_val in ins:
                if 'Non-string datatype-literal passes as string' in in_val:
                    ins_is_broken = True
        if ins_is_broken:
            print(f"Warning: Conversion of sh:in list failed for nodeshape {nodeshape}. Please check. Currently only \
string elements in list are supported.")
            check['ins'] = None
        property_checks.append(check)
    tables.append(configs.kafka_topic_ngsi_prefix_name)
    views.append(configs.kafka_topic_ngsi_prefix_name + "-view")
    sqlite += '\n'
    sqlite += utils.add_relationship_checks(relationshp_checks, utils.SQL_DIALECT.SQLITE)
    sql_command_yaml = utils.add_relationship_checks(relationshp_checks, utils.SQL_DIALECT.SQL)
    statementsets.append(sql_command_yaml)
    sqlite += '\n'
    sqlite += utils.add_property_checks(property_checks, utils.SQL_DIALECT.SQLITE)
    sql_command_yaml = utils.add_property_checks(property_checks, utils.SQL_DIALECT.SQL)
    statementsets.append(sql_command_yaml)
    sqlite += '\n'
    sql_command_sqlite, sql_command_yaml = create_relationship_sql()
    statementsets.append(sql_command_yaml)
    sqlite += sql_command_sqlite
    sqlite += '\n'
    sql_command_sqlite, sql_command_yaml = create_property_sql()
    sqlite += sql_command_sqlite
    statementsets.append(sql_command_yaml)
    tables.append(utils.class_to_obj_name(utils.relationship_checks_tablename))
    tables.append(utils.class_to_obj_name(utils.property_checks_tablename))
    return sqlite, (statementsets, tables, views)
