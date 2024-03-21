from rdflib import Graph
import owlrl
import os
import sys
from urllib.parse import urlparse
import re
import ruamel.yaml


file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import configs  # noqa: E402
import utils  # noqa: E402
from sparql_to_sql import translate_sparql  # noqa: E402

yaml = ruamel.yaml.YAML()
alerts_bulk_table = configs.alerts_bulk_table_name
alerts_bulk_table_object = configs.alerts_bulk_table_object_name
attributes_insert_table_obj_name = configs.attributes_insert_table_obj_name
sparql_get_all_rule_nodes = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sh: <http://www.w3.org/ns/shacl#>
SELECT ?nodeshape ?targetclass ?construct
where {
    ?nodeshape a sh:NodeShape .
    ?nodeshape sh:targetClass ?targetclass .
    ?nodeshape sh:rule [
            sh:construct ?construct ;
            ] ;
}

"""

sql_check_sparql_base = """
            INSERT {% if sqlite %}OR REPlACE{% endif %} INTO {{alerts_bulk_table}}
            SELECT
            this_left AS resource,
                'SPARQLConstraintComponent({{nodeshape}})' AS event,
                'Development' AS environment,
                {% if sqlite %}
                '[SHACL Validator]' AS service,
                {% else %}
                ARRAY ['SHACL Validator'] AS service,
                {% endif %}
                CASE WHEN this IS NOT NULL
                    THEN '{{severity}}'
                    ELSE 'ok' END AS severity,
                'customer'  customer,
                CASE WHEN this IS NOT NULL
                THEN '{{message}}'
                ELSE 'All ok' END  as `text`
                {%- if sqlite %}
                ,CURRENT_TIMESTAMP
                {%- endif %}

            FROM (SELECT A.this as this_left, B.this as this, * FROM (SELECT id as this from {{targetclass}}_view) as A LEFT JOIN ({{sql_expression}}) as B ON A.this = B.this)
"""  # noqa E501


def strip_class(klass):
    """Get class postfix of IRI

    For instance: "http://example.com/class" => "class"
    Args:
        klass (String): IRI

    Returns:
        string: class
    """
    a = urlparse(klass)
    return os.path.basename(a.path)


def add_variables_to_message(message):
    """Replace ?vars or $vars with SQL term

    For instance: "value is {?value}!" => "value is " || IFNULL(`value`, 'NULL') || '!'
    Args:
        message (string): string with {?var} or {$var} definition

    Returns:
        string: Adapted string
    """
    return re.sub(r"\{([\?\$])(\w*)\}", r"' || IFNULL(`\2`, 'NULL') || '", message)


def translate(shaclfile, knowledgefile):
    """
    Translate shacl properties into SQL constraints.

    Parameters:
        shaclname: filename of SHACL file
        knowledgename: filename of knowledge file

    Returns:
        sql-statement-list: list of plain SQL objects
        (statementset, tables, views): statementset in yaml format

    """
    g = Graph()
    h = Graph()
    g.parse(shaclfile)
    h.parse(knowledgefile)
    g += h
    owlrl.RDFSClosure.RDFS_Semantics(g, axioms=True, daxioms=False, rdfs=True).closure()
    tables_all = []
    views = []
    statementsets = []
    sqlite = ''
    # Get all NGSI-LD Relationship
    qres = g.query(sparql_get_all_rule_nodes)

    for row in qres:
        target_class = row.targetclass
        construct = row.construct.toPython() if row.construct else None
        sql_expression, tables = translate_sparql(shaclfile, knowledgefile, construct, target_class, g)

        sql_command_yaml = utils.process_sql_dialect(sql_expression, False)
        sql_command_sqlite = utils.process_sql_dialect(sql_expression, True)

        sql_command_sqlite += ";"
        sql_command_yaml += ";"
        sql_command_sqlite = '\n' + sql_command_sqlite
        sqlite += sql_command_sqlite
        statementsets.append(sql_command_yaml)
        tables_all += map(utils.snake_case_to_kebab_case, tables)

    views = []
    tables = list(set(tables_all))
    for table in tables:
        if table != configs.rdf_table_obj_name:
            views.append(f'{table}-view')
    tables.append(alerts_bulk_table_object)
    tables.append(configs.rdf_table_name)
    tables.append(configs.attributes_table_obj_name)
    tables.append(attributes_insert_table_obj_name)
    return sqlite, (statementsets, tables, views)
