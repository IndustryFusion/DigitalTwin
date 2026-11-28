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
"""
ALPHA: the SQL of SPARQL_ENGINE=ladder (see lib/sparql_ladder.py).

    facts   entities, attributes and knowledge as (src, p, s, o, ts)
    pat     one row per triple pattern
    alpha   facts matched against the patterns: the leaves of all trees
    o1..oK  level j joins its left and right rows; inner joins, OPTIONAL and
            NOT EXISTS are the same LEFT JOIN

The rows are kept in the rdf table under predicates of their own: that table is
delivered and re-snapshotted already, so no topic or replication slot is added.
"""
import json
import re
import rdflib

import lib.configs as configs
import lib.utils as utils
import lib.sparql_ladder as ladder

ROW_PREDICATE = 'urn:iff:sparql-ladder:'
# The Join operators the Flink plan of the last KMS translated holds for the
# ladder: its levels once per ladder (the statements of a job reuse them),
# plus what each statement joins itself. sparql_ladder_joins.py counts them in
# a running job's plan; a duplicated level shows as more.
joins = None
RELATIONSHIP = 'https://uri.etsi.org/ngsi-ld/Relationship'
PROPERTY = 'https://uri.etsi.org/ngsi-ld/Property'


def quote(text):
    return "'" + text.replace("'", "''") + "'"


def in_list(column, values):
    return f"{column} IN ({', '.join(quote(v) for v in sorted(values))})"


class Dialect:
    def __init__(self, sqlite):
        self.sqlite = sqlite

    def field(self, column, key):
        """a text of a stored row"""
        return f"json_extract({column}, '$.{key}')" if self.sqlite else f"JSON_VALUE({column}, '$.{key}')"

    def part(self, name):
        """a part of the ROW (sqlite: JSON array) T a ladder function returns"""
        index = ('lvl', 'node', 'side', 'k', 'b', 'path').index(name)
        return f"json_extract(T, '$[{index}]')" if self.sqlite else f'T.{name}'

    def integer(self, expression):
        return f'CAST({expression} AS INTEGER)'

    def is_current(self, column):
        return f'IFNULL({column}, FALSE) IS FALSE'

    def pin(self, aliases, pinned):
        return utils.get_state_ttl_metadata(aliases) + ' ' if pinned and not self.sqlite else ''

    def time(self, column):
        iso = utils.process_sql_dialect(f'SQL_DIALECT_ISO_TIMESTAMP{{{column}}}', self.sqlite)
        return f"IFNULL('\"' || {iso} || '\"', '')"


def facts(dialect, rows):
    """Only what a pattern asks for: the knowledge alone can be hundreds of thousands of triples."""
    asked = {}
    for row in rows:
        asked.setdefault(row['src'], set()).add(row['p'])
    parts = []
    if 'E' in asked:
        parts.append(f"SELECT 'E' AS src, {quote(ladder.RDF_TYPE)} AS p, '<' || id || '>' AS s, "
                     f"'<' || `type` || '>' AS o, '' AS ts FROM entities_view "
                     f"WHERE {dialect.is_current('`deleted`')}")
    for history in ('', 'H'):
        names = asked.get('P' + history, set()) | asked.get('R' + history, set())
        if not names:
            continue
        table = 'attributes' if history else 'attributes_view'
        parts.append(
            f"SELECT CASE `type` WHEN {quote(RELATIONSHIP)} THEN 'R{history}' WHEN {quote(PROPERTY)} "
            f"THEN 'P{history}' ELSE '' END AS src, name AS p, '<' || entityId || '>' AS s, "
            f"CASE WHEN `type` = {quote(RELATIONSHIP)} OR nodeType = '@id' THEN '<' || attributeValue || '>' "
            f"ELSE '\"' || attributeValue || '\"' END AS o, {dialect.time('`observedAt`')} AS ts FROM {table} "
            f"WHERE {dialect.is_current('`deleted`')} AND parentId IS NULL AND {in_list('name', names)}")
    if 'K' in asked:
        # rdf writes numbers without quotes (utils.format_node_type): the ladder
        # reads them so, as numbers (sparql_ladder.kind)
        parts.append(
            "SELECT 'K' AS src, SUBSTR(predicate, 2, LENGTH(predicate) - 2) AS p, subject AS s, "
            f"CAST(`object` AS {'TEXT' if dialect.sqlite else 'STRING'}) "
            f"AS o, '' AS ts FROM rdf WHERE {in_list('predicate', {f'<{p}>' for p in asked['K']})}")
    sql = '\nUNION ALL '.join(parts)
    return sql if dialect.sqlite else sql.replace('SUBSTR(', 'SUBSTRING(').replace('LENGTH(', 'CHAR_LENGTH(')


def ladder_ctes(dialect, name, rows, levels):
    """The CTEs facts .. oK of one ladder, as [(name, sql)]. `current` is pinned, see Rule.ladder."""
    pinned = name == 'current'
    pre = f'{name}_'
    columns = ', '.join(f"{dialect.field('`object`', c)} AS {c}" for c in
                        ('p', 'src', 'cs', 'co', 'flt', 'node', 'side', 'path'))
    columns += f", {dialect.field('`object`', 'key')} AS keyspec, " \
               f"{dialect.integer(dialect.field('`object`', 'lvl'))} AS lvl"
    ctes = [(pre + 'facts', facts(dialect, rows)),
            (pre + 'pat', f"SELECT {columns} FROM rdf WHERE predicate = {quote(ROW_PREDICATE + 'pattern:' + name)}")]
    parts = ', '.join(f'{dialect.part(p)} AS {p}' for p in ('lvl', 'node', 'side', 'k', 'b', 'path'))
    ctes.append((pre + 'alpha',
                 f"SELECT {parts} FROM (SELECT {dialect.pin(['f', 'p'], pinned)}"
                 "sparql_route(p.lvl, p.node, p.side, p.keyspec, p.flt, p.path, f.s, f.o, f.ts) AS T "
                 f"FROM {pre}facts AS f JOIN {pre}pat AS p ON f.p = p.p AND f.src = p.src "
                 "WHERE (p.cs = '' OR p.cs = f.s) AND (p.co = '' OR p.co = f.o)) AS routed"))
    for level in range(1, levels + 1):
        def side(which):
            inputs = f"SELECT node, k, b, path FROM {pre}alpha WHERE lvl = {level} AND side = '{which}'"
            if level > 1:
                inputs += f" UNION ALL SELECT node, k, b, path FROM {pre}o{level - 1} WHERE side = '{which}'"
            return inputs
        ctes.append((f'{pre}o{level}',
                     f"SELECT {parts} FROM (SELECT {dialect.pin(['l', 'r'], pinned)}"
                     f"sparql_step({level}, l.path, l.b, r.b) AS T FROM ({side('L')}) AS l "
                     f"LEFT JOIN ({side('R')}) AS r ON l.node = r.node AND l.k = r.k) AS stepped"))
    # Roots are on the last level; a query of one pattern is a leaf above it.
    ctes.append((pre + 'out', f"SELECT node, k, b FROM {pre}o{levels} WHERE side = 'Z' UNION ALL "
                 f"SELECT node, k, b FROM {pre}alpha WHERE side = 'Z'"))
    return ctes


def rule_rows_cte(dialect, kind, columns):
    fields = ', '.join(f"{dialect.field('`object`', c)} AS {alias}" for c, alias in columns.items())
    return kind + '_rule', f"SELECT {fields} FROM rdf WHERE predicate = {quote(ROW_PREDICATE + kind)}"


def statement(dialect, target, ctes, select):
    if dialect.sqlite:
        # Temporary tables, one per level, computed once each. SQLite expands a
        # CTE per reference even when MATERIALIZED, and every level reads the
        # one below more than once: 3.54 refuses ten such levels ("VIEWs and/or
        # subqueries nested too deep").
        tables = ''.join(f'DROP TABLE IF EXISTS temp.{name};\nCREATE TEMP TABLE {name} AS {sql};\n'
                         for name, sql in ctes)
        return f'{tables}INSERT OR REPLACE INTO {target}\n{select};'
    with_clause = 'WITH ' + ',\n'.join(f'{name} AS ({sql})' for name, sql in ctes)
    return f'INSERT INTO {target}\n{with_clause}\n{select};'


def alerts_statement(dialect, ctes):
    """
    The alerts of all constraints. An entity which is deleted keeps its row and
    turns to ok, which closes its alerts.
    """
    ctes = ctes + [rule_rows_cte(dialect, 'constraint', {'rule': 'rule', 'type': 'cls', 'event': 'event',
                                                         'severity': 'severity', 'msg': 'msg'})]
    service = "'[SHACL Validator]'" if dialect.sqlite else "ARRAY ['SHACL Validator']"
    hit = f"v.b IS NOT NULL AND {dialect.is_current('e.`deleted`')}"
    select = f"""SELECT {dialect.pin(['x'], True)}resource, event, 'Development' AS environment, {service} AS service,
    CASE WHEN MAX(hit) = 1 THEN MAX(CASE WHEN hit = 1 THEN severity END) ELSE 'ok' END AS severity,
    'customer' AS customer,
    CASE WHEN MAX(hit) = 1 THEN MAX(CASE WHEN hit = 1 THEN `text` END) ELSE 'All ok' END AS `text`
    {', CURRENT_TIMESTAMP' if dialect.sqlite else ''}
FROM (SELECT {dialect.pin(['e', 'v'], True)}e.id AS resource, e.event AS event, e.severity AS severity,
        CASE WHEN {hit} THEN 1 ELSE 0 END AS hit,
        CASE WHEN {hit} THEN sparql_text(e.msg, v.b) END AS `text`
    FROM (SELECT {dialect.pin(['e', 'r'], True)}e.id AS id, e.`deleted` AS `deleted`, r.rule AS rule,
            r.event AS event, r.severity AS severity, r.msg AS msg
        FROM entities_view AS e JOIN constraint_rule AS r ON e.`type` = r.cls) AS e
    LEFT JOIN current_out AS v ON v.node = e.rule AND v.k = '<' || e.id || '>' || {char(dialect)}) AS x
GROUP BY resource, event"""
    return statement(dialect, configs.alerts_bulk_table_name, ctes, select)


def char(dialect):
    return 'char(1)' if dialect.sqlite else 'CHR(1)'


def attributes_select(dialect, source):
    """rows (name, suffix, entity, val) as rows of the attributes table"""
    null = 'CAST(NULL AS STRING)' if not dialect.sqlite else 'CAST(NULL AS TEXT)'
    return f"""SELECT DISTINCT entity || suffix AS id, {null} AS parentId, entity AS entityId, name,
    CASE WHEN SUBSTR(val, 1, 1) = '<' THEN '@id' ELSE '@value' END AS nodeType, {null} AS valueType,
    '{PROPERTY}' AS `type`, CASE WHEN SUBSTR(val, 1, 1) IN ('<', '"', '\'\'', '`')
    THEN SUBSTR(val, 2, LENGTH(val) - 2) ELSE val END AS attributeValue, '@none' AS datasetId,
    {null} AS unitCode, {null} AS lang, FALSE AS `deleted`, FALSE AS synced
    {', CURRENT_TIMESTAMP' if dialect.sqlite else ''}
FROM ({source}) AS constructed WHERE val IS NOT NULL AND entity IS NOT NULL"""


def constructs_statement(dialect, ctes, has_construct, has_aggregate):
    ctes = list(ctes)
    suffix = 'sqlite_id' if dialect.sqlite else 'id'
    common = {'rule': 'rule', 'name': 'name', suffix: 'suffix', 'entity': 'entity', 'value': 'val'}
    sources = []
    if has_construct:
        ctes.append(rule_rows_cte(dialect, 'construct', common))
        sources.append(f"SELECT {dialect.pin(['o', 'r'], True)}r.name AS name, r.suffix AS suffix, "
                       "sparql_text(r.entity, o.b) AS entity, sparql_value(r.val, o.b) AS val "
                       "FROM current_out AS o JOIN construct_rule AS r ON o.node = r.rule")
    if has_aggregate:
        ctes.append(rule_rows_cte(dialect, 'aggregate', {**common, 'group': 'grp', 'function': 'func',
                                                         'argument': 'argument'}))
        if dialect.sqlite:
            total = 'CAST(CAST(SUM(CAST(arg AS REAL)) AS INTEGER) AS TEXT)'
        else:
            total = 'CAST(CAST(SUM(TRY_CAST(arg AS DOUBLE)) AS BIGINT) AS STRING)'
        text = 'TEXT' if dialect.sqlite else 'STRING'
        ctes.append(('aggregate_input',
                     "SELECT r.name AS name, r.suffix AS suffix, r.entity AS entity, r.val AS val, r.func AS func, "
                     "sparql_group(r.grp, o.b) AS grp, sparql_text(r.argument, o.b) AS arg "
                     "FROM history_out AS o JOIN aggregate_rule AS r ON o.node = r.rule"))
        ctes.append(('aggregated',
                     f"SELECT name, suffix, entity, val, grp || {char(dialect)} || '\"' || CASE func "
                     f"WHEN 'count' THEN CAST(COUNT(arg) AS {text}) "
                     f"WHEN 'count-distinct' THEN CAST(COUNT(DISTINCT arg) AS {text}) ELSE {total} END || '\"' AS b "
                     "FROM aggregate_input GROUP BY name, suffix, entity, val, func, grp"))
        sources.append("SELECT name, suffix, sparql_text(entity, b) AS entity, sparql_value(val, b) AS val "
                       "FROM aggregated")
    sql = attributes_select(dialect, '\nUNION ALL '.join(sources))
    if not dialect.sqlite:
        sql = sql.replace('SUBSTR(', 'SUBSTRING(').replace('LENGTH(', 'CHAR_LENGTH(')
    return statement(dialect, 'attributes_insert_filter' if dialect.sqlite else 'attributes_insert', ctes, sql)


def data_rows(rules, levels):
    """[(predicate, row)], and the pattern rows per ladder"""
    rows, patterns = [], {}
    for rule in rules:
        for row in ladder.pattern_rows(rule.name, rule.tree, levels[rule.ladder], rule.root_key):
            patterns.setdefault(rule.ladder, []).append(row)
            rows.append(('pattern:' + rule.ladder, row))
        rows += rule.rows
    return rows, patterns


def insert_rows(rows, table):
    """The rows as triples: subject a running number, object the row as JSON"""
    if not rows:
        return ''
    values = ',\n'.join(f"({quote(f'<{ROW_PREDICATE}row:{num}>')}, {quote(ROW_PREDICATE + kind)}, "
                        f"{quote(json.dumps(row, separators=(',', ':'), sort_keys=True))}, 0)"
                        for num, (kind, row) in enumerate(rows))
    return f'INSERT INTO {table} VALUES\n{values};\n'


def translate(shaclfile, knowledgefile, knowledge, prefixes):
    """
    Compile all SPARQL constraints and rules.

    Args:
        shaclfile, knowledgefile: filenames
        knowledge: the parsed knowledge
        prefixes: of the KMS

    Returns:
        sqlite script, (Flink statements, tables, views), postgres script
    """
    g = utils.transitive_closure(utils.load_graph(shaclfile, knowledgefile))
    shapes = rdflib.Graph()
    shapes.parse(shaclfile)
    rules = ladder.compile_rules(g, shapes + knowledge, prefixes)
    if not rules:
        return '', ([], [], []), ''
    levels = {}
    for rule in rules:
        levels[rule.ladder] = max(levels.get(rule.ladder, 1), rule.tree.height)
    rows, patterns = data_rows(rules, levels)
    kinds = {kind for kind, _ in rows}

    def render(dialect):
        ctes = {name: ladder_ctes(dialect, name, patterns[name], levels[name]) for name in patterns}
        statements = []
        if 'constraint' in kinds:
            statements.append(alerts_statement(dialect, ctes['current']))
        if kinds & {'construct', 'aggregate'}:
            needed = (ctes['current'] if 'construct' in kinds else []) + ctes.get('history', [])
            statements.append(constructs_statement(dialect, needed, 'construct' in kinds, 'aggregate' in kinds))
        return statements

    global joins
    flink = render(Dialect(False))
    shared = {}
    for name in patterns:
        levels_sql = ladder_ctes(Dialect(False), name, patterns[name], levels[name])
        shared[name] = count_joins(' '.join(sql for _, sql in levels_sql))
    uses = {'current': ('constraint' in kinds) + ('construct' in kinds),
            'history': int(bool(kinds & {'construct', 'aggregate'}))}
    joins = sum(count_joins(text) for text in flink) - sum(max(uses.get(name, 1) - 1, 0) * n
                                                           for name, n in shared.items())
    sqlite = insert_rows(rows, '`rdf`') + '\n'.join(render(Dialect(True))) + '\n'
    tables = [configs.alerts_bulk_table_object_name, configs.rdf_table_name, configs.attributes_table_obj_name,
              configs.kafka_topic_ngsi_prefix_name]
    if kinds & {'construct', 'aggregate'}:
        tables.append(configs.attributes_insert_table_obj_name)
    views = ['attributes-view', 'entities-view']
    return sqlite, (flink, tables, views), insert_rows(rows, '"rdf"')


def count_joins(sql):
    return len(re.findall(r'\bJOIN\b', sql))
