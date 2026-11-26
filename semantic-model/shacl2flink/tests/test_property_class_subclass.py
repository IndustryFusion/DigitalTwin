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
sh:class on the value of a Property is met by an instance of a subclass.

The knowledge types a node with its most specific class (an OPC UA node is a
uacore:Object) while the shape asks for a superclass (uacore:Node). The check
looked up the rdf:type triple alone, so every such value was reported as not
of the class. The end-to-end case is tests/sql-tests/kms-constraints/test34.
"""

import sqlite3

from jinja2 import Template
from rdflib import Graph, Namespace, RDF, RDFS

import lib.configs as configs
import lib.shacl_properties_to_sql as props
import lib.utils as utils

EX = Namespace('https://example.org/subclass/')


def _knowledge_rows():
    """The rdf table as create_rdf_table.py fills it: the knowledge closure."""
    g = Graph()
    g.add((EX.Instance, RDFS.subClassOf, EX.Node))
    g.add((EX.Object, RDFS.subClassOf, EX.Instance))
    g.add((EX.executing, RDF.type, EX.Object))
    g.add((EX.both, RDF.type, EX.Other))
    g.add((EX.both, RDF.type, EX.Object))
    g.add((EX.undeclared, RDF.type, EX.Undeclared))
    closure = utils.transitive_closure(g)
    return [(f'<{s}>', f'<{p}>', f'<{o}>') for s, p, o in closure]


def _class_members():
    ctes = Template(props.sql_class_member_ctes).render(rdf_table_name='rdf')
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE rdf (subject TEXT, predicate TEXT, object TEXT)')
    db.executemany('INSERT INTO rdf VALUES (?, ?, ?)', _knowledge_rows())
    rows = db.execute(f'WITH {ctes.rstrip().rstrip(",")} '
                      'SELECT subject, object FROM rdf_class_members').fetchall()
    return rows


def test_a_node_is_a_member_of_every_superclass_of_its_type():
    members = set(_class_members())
    for cls in (EX.Object, EX.Instance, EX.Node):
        assert (f'<{EX.executing}>', f'<{cls}>') in members


def test_an_undeclared_direct_type_is_kept():
    assert (f'<{EX.undeclared}>', f'<{EX.Undeclared}>') in set(_class_members())


def test_one_row_per_node_and_class():
    # A node of several types reaches a class on several paths; the base
    # joins this table per attribute and must not get a row per path.
    rows = _class_members()
    assert len(rows) == len(set(rows))
    assert rows.count((f'<{EX.both}>', f'<{EX.Node}>')) == 1


def test_the_property_base_looks_up_class_members():
    for sql in props.create_property_sql() + props.create_property_sql(focus=True):
        assert 'rdf_class_members AS (' in sql
        assert 'LEFT JOIN rdf_class_members as C' in sql
        assert "C.predicate = '<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>'" not in sql


def test_the_class_member_inputs_are_pinned():
    _, flink = props.create_property_sql()
    assert "STATE_TTL('T' = '0d', 'S' = '0d')" in flink
    assert "STATE_TTL('rdf_type_closure' = '0d')" in flink
    assert f'FROM {configs.rdf_table_name} AS T' in flink
