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
import unittest
from rdflib import Graph, Namespace, URIRef, BNode
from rdflib.namespace import RDFS, SH

import lib.instance_coverage as coverage
from lib.utils import UARDF

OPCUA = Namespace('http://opcfoundation.org/UA/')
EX = Namespace('http://example.org/')
BASE = Namespace('https://industryfusion.github.io/contexts/ontology/v0/base/')
OBJECT = 'object'
VARIABLE = 'variable'
METHOD = 'method'


class StubRdfUtils:
    """The RdfUtils lookups the coverage helpers use, over plain dictionaries."""

    def __init__(self, nodes=None, references=None):
        self.opcuans = OPCUA
        self.nodes = nodes or {}            # node -> (nodeclass, type)
        self.references = references or {}  # (node, reference superclass) -> [(reference, target)]

    def get_type(self, g, node):
        return self.nodes.get(node, (None, None))

    def isObjectNodeClass(self, nodeclass):
        return nodeclass == OBJECT

    def isVariableNodeClass(self, nodeclass):
        return nodeclass == VARIABLE

    def isMethodNodeClass(self, nodeclass):
        return nodeclass == METHOD

    def get_all_subreferences(self, g, node, reference):
        return list(self.references.get((node, reference), []))


def type_graph(*pairs, defined=()):
    """A graph with rdfs:subClassOf pairs and a type node for every type in defined."""
    g = Graph()
    for sub, sup in pairs:
        g.add((sub, RDFS.subClassOf, sup))
    for objtype in defined:
        g.add((EX[f'node_{objtype.split("/")[-1]}'], UARDF['definesType'], objtype))
    return g


def typenode(objtype):
    return EX[f'node_{objtype.split("/")[-1]}']


class TestInstanceObjectTypes(unittest.TestCase):
    def setUp(self):
        self.nodes = {
            EX.root: (OBJECT, EX.AlphaType),
            EX.blocks: (OBJECT, OPCUA.FolderType),
            EX.state: (OBJECT, EX.BetaType),
            EX.level: (VARIABLE, OPCUA.BaseDataVariableType),
            EX.linked: (OBJECT, EX.GammaType),
            EX.organized: (OBJECT, EX.DeltaType),
            EX.ignored: (OBJECT, EX.IgnoredType),
            EX.property: (OBJECT, EX.PropertyChildType),
        }
        self.references = {
            (EX.root, OPCUA.HasChild): [(OPCUA.HasComponent, EX.blocks), (OPCUA.HasProperty, EX.property)],
            (EX.blocks, OPCUA.HasChild): [(OPCUA.HasAddIn, EX.state)],
            (EX.state, OPCUA.HasChild): [(OPCUA.HasComponent, EX.level), (OPCUA.HasComponent, EX.root)],
            (EX.root, OPCUA.NonHierarchicalReferences): [(EX.Connects, EX.linked), (EX.Ignored, EX.ignored)],
            (EX.root, OPCUA.Organizes): [(OPCUA.Organizes, EX.organized)],
        }
        self.rdfutils = StubRdfUtils(self.nodes, self.references)

    def test_follows_children_declarations_and_references(self):
        found = coverage.instance_object_types(Graph(), self.rdfutils, [EX.root], [OPCUA.HasProperty], [EX.Ignored])
        self.assertEqual(found, [EX.AlphaType, OPCUA.FolderType, EX.BetaType, EX.DeltaType, EX.GammaType])

    def test_variables_are_not_types_of_entities(self):
        found = coverage.instance_object_types(Graph(), self.rdfutils, [EX.root], [], [])
        self.assertNotIn(OPCUA.BaseDataVariableType, found)
        self.assertIn(EX.PropertyChildType, found)
        self.assertIn(EX.IgnoredType, found)

    def test_objects_behind_variables_are_reached(self):
        # the entity pass follows a variable's children and references: an object only reached that way is an entity
        self.nodes[EX.target] = (OBJECT, EX.ZetaType)
        self.references[(EX.level, OPCUA.NonHierarchicalReferences)] = [(EX.Connects, EX.target)]
        found = coverage.instance_object_types(Graph(), self.rdfutils, [EX.root], [], [])
        self.assertIn(EX.ZetaType, found)
        self.assertNotIn(OPCUA.BaseDataVariableType, found)

    def test_variables_behind_references_are_not_followed(self):
        # the entity pass ignores a variable a reference points to, so what is behind it is no entity
        self.nodes[EX.far] = (VARIABLE, OPCUA.BaseDataVariableType)
        self.nodes[EX.ghost] = (OBJECT, EX.GhostType)
        self.references[(EX.state, OPCUA.NonHierarchicalReferences)] = [(EX.Connects, EX.far)]
        self.references[(EX.far, OPCUA.NonHierarchicalReferences)] = [(EX.Connects, EX.ghost)]
        found = coverage.instance_object_types(Graph(), self.rdfutils, [EX.root], [], [])
        self.assertNotIn(EX.GhostType, found)
        # the same variable is followed where it is a child as well
        self.references[(EX.blocks, OPCUA.HasChild)].append((OPCUA.HasComponent, EX.far))
        found = coverage.instance_object_types(Graph(), self.rdfutils, [EX.root], [], [])
        self.assertIn(EX.GhostType, found)

    def test_methods_are_not_followed(self):
        self.nodes[EX.method] = (METHOD, None)
        self.nodes[EX.behind] = (OBJECT, EX.BehindType)
        self.references[(EX.root, OPCUA.HasChild)].append((OPCUA.HasComponent, EX.method))
        self.references[(EX.method, OPCUA.HasChild)] = [(OPCUA.HasProperty, EX.behind)]
        found = coverage.instance_object_types(Graph(), self.rdfutils, [EX.root], [], [])
        self.assertNotIn(EX.BehindType, found)

    def test_no_roots(self):
        self.assertEqual(coverage.instance_object_types(Graph(), self.rdfutils, [None], [], []), [])

    def test_type_without_name_is_skipped(self):
        rdfutils = StubRdfUtils({EX.root: (OBJECT, None)})
        self.assertEqual(coverage.instance_object_types(Graph(), rdfutils, [EX.root], [], []), [])


class TestSupertypeChain(unittest.TestCase):
    def test_nearest_first(self):
        g = type_graph((EX.Sub, EX.Mid), (EX.Mid, OPCUA.BaseObjectType))
        self.assertEqual(coverage.supertype_chain(g, EX.Sub), [EX.Sub, EX.Mid, OPCUA.BaseObjectType])

    def test_cycle_terminates(self):
        g = type_graph((EX.A, EX.B), (EX.B, EX.A))
        self.assertEqual(coverage.supertype_chain(g, EX.A), [EX.A, EX.B])

    def test_blank_superclass_ignored(self):
        g = Graph()
        g.add((EX.A, RDFS.subClassOf, BNode()))
        self.assertEqual(coverage.supertype_chain(g, EX.A), [EX.A])

    def test_shape_order_puts_supertypes_first(self):
        g = type_graph((EX.Sub, EX.Mid), (EX.Mid, OPCUA.BaseObjectType), (EX.Other, OPCUA.BaseObjectType))
        self.assertEqual(coverage.shape_order(g, [EX.Sub, EX.Mid, EX.Other]), [EX.Mid, EX.Other, EX.Sub])


class TestNeedsOwnShape(unittest.TestCase):
    def setUp(self):
        self.g = type_graph((EX.BSubType, EX.BType), (EX.BType, OPCUA.BaseObjectType),
                            (EX.MemberSubType, EX.BType), (EX.MidType, EX.BType), (EX.LeafType, EX.MidType),
                            defined=[EX.BSubType, EX.BType, EX.MemberSubType, EX.MidType, EX.LeafType,
                                     OPCUA.BaseObjectType])
        self.rdfutils = StubRdfUtils(references={
            (typenode(EX.MemberSubType), OPCUA.HasChild): [(OPCUA.HasComponent, EX.someVariable)],
            (typenode(EX.MidType), OPCUA.NonHierarchicalReferences): [(EX.Connects, EX.target)],
        })

    def needs(self, objtype, shaped, ignored_hierarchical=(), ignored=()):
        return coverage.needs_own_shape(self.g, self.rdfutils, objtype, set(shaped), list(ignored_hierarchical),
                                        list(ignored))

    def test_already_shaped(self):
        self.assertFalse(self.needs(EX.BType, [EX.BType]))

    def test_memberless_subtype_is_covered_by_supertype(self):
        self.assertFalse(self.needs(EX.BSubType, [EX.BType]))

    def test_subtype_with_members_gets_own_shape(self):
        self.assertTrue(self.needs(EX.MemberSubType, [EX.BType]))

    def test_member_in_between_needs_own_shape(self):
        self.assertTrue(self.needs(EX.LeafType, [EX.BType]))

    def test_ignored_references_are_no_members(self):
        self.assertFalse(self.needs(EX.LeafType, [EX.BType], ignored=[EX.Connects]))
        self.assertFalse(self.needs(EX.MemberSubType, [EX.BType], ignored_hierarchical=[OPCUA.HasComponent]))

    def test_no_rules_no_shape(self):
        # neither BSubType nor BType nor BaseObjectType define a member: a shape would be empty
        self.assertFalse(self.needs(EX.BSubType, []))
        self.assertFalse(self.needs(OPCUA.BaseObjectType, []))

    def test_members_without_shaped_supertype(self):
        self.assertTrue(self.needs(EX.MemberSubType, []))

    def test_lacks_shape(self):
        args = (self.rdfutils, )
        # MemberSubType defines a member of its own: the supertype's shape does not cover it
        self.assertTrue(coverage.lacks_shape(self.g, *args, EX.MemberSubType, {EX.BType}, [], []))
        self.assertFalse(coverage.lacks_shape(self.g, *args, EX.MemberSubType, {EX.MemberSubType}, [], []))
        # BSubType adds nothing to the shaped BType; BaseObjectType defines no member at all
        self.assertFalse(coverage.lacks_shape(self.g, *args, EX.BSubType, {EX.BType}, [], []))
        self.assertFalse(coverage.lacks_shape(self.g, *args, OPCUA.BaseObjectType, set(), [], []))
        # the rules of a type without definition are unknown
        self.assertTrue(coverage.lacks_shape(self.g, *args, EX.UnknownType, set(), [], []))

    def test_type_without_definition(self):
        self.assertFalse(self.needs(EX.UnknownType, []))


class TestShapeAddsNothing(unittest.TestCase):
    def setUp(self):
        self.g = type_graph((EX.SubType, EX.MidType), (EX.MidType, EX.BType))
        self.shapes = Graph()
        self.add_shape(EX.BType, EX.hasCount)

    def add_shape(self, objtype, *paths):
        shape = URIRef(f'{objtype}Shape')
        self.shapes.add((shape, SH.targetClass, objtype))
        for path in paths:
            prop, inner = BNode(), BNode()
            self.shapes.add((shape, SH.property, prop))
            self.shapes.add((prop, SH.path, path))
            self.shapes.add((prop, SH.property, inner))
            self.shapes.add((inner, SH.path, EX.hasValue))

    def test_same_rules_as_the_nearest_shaped_supertype(self):
        self.add_shape(EX.SubType, EX.hasCount)
        self.assertTrue(coverage.shape_adds_nothing(self.g, self.shapes, EX.SubType))

    def test_additional_rule(self):
        self.add_shape(EX.SubType, EX.hasCount, EX.hasExtra)
        self.assertFalse(coverage.shape_adds_nothing(self.g, self.shapes, EX.SubType))

    def test_without_shaped_supertype(self):
        self.add_shape(EX.Empty)
        self.add_shape(EX.Other, EX.hasCount)
        self.assertTrue(coverage.shape_adds_nothing(self.g, self.shapes, EX.Empty))
        self.assertFalse(coverage.shape_adds_nothing(self.g, self.shapes, EX.Other))

    def test_restore(self):
        before = set(self.shapes)
        self.add_shape(EX.SubType, EX.hasCount)
        self.shapes.remove((None, SH.targetClass, EX.BType))
        coverage.restore(self.shapes, before)
        self.assertEqual(set(self.shapes), before)


class TestDefinesMembers(unittest.TestCase):
    def test_methods_give_no_rule(self):
        rdfutils = StubRdfUtils(nodes={EX.method: (METHOD, None), EX.count: (VARIABLE, OPCUA.BaseDataVariableType)},
                                references={(EX.typenode, OPCUA.HasChild): [(OPCUA.HasComponent, EX.method)]})
        self.assertFalse(coverage.defines_members(Graph(), rdfutils, EX.typenode, [], []))
        rdfutils.references[(EX.typenode, OPCUA.HasChild)].append((OPCUA.HasComponent, EX.count))
        self.assertTrue(coverage.defines_members(Graph(), rdfutils, EX.typenode, [], []))

    def test_interface_and_organizes_count(self):
        g = Graph()
        g.add((EX.node, OPCUA.HasInterface, EX.interfaceNode))
        rdfutils = StubRdfUtils()
        self.assertTrue(coverage.defines_members(g, rdfutils, EX.node, [], []))
        rdfutils = StubRdfUtils(references={(EX.other, OPCUA.Organizes): [(OPCUA.Organizes, EX.x)]})
        self.assertTrue(coverage.defines_members(Graph(), rdfutils, EX.other, [], []))
        self.assertFalse(coverage.defines_members(Graph(), StubRdfUtils(), EX.other, [], []))


class TestUncoveredTerms(unittest.TestCase):
    def setUp(self):
        self.ontology = type_graph((EX.BSubType, EX.BType), (EX.BType, OPCUA.BaseObjectType),
                                   (OPCUA.FolderType, OPCUA.BaseObjectType))
        self.ontology.add((EX.hasLevel, RDFS.domain, EX.BType))
        self.ontology.add((EX.hasState, RDFS.domain, OPCUA.FolderType))
        self.shapes = Graph()
        shape, prop = EX.BTypeShape, BNode()
        self.shapes.add((shape, SH.targetClass, EX.BType))
        self.shapes.add((shape, SH.property, prop))
        self.shapes.add((prop, SH.path, EX.hasLevel))
        self.expand = lambda name: EX[name.split(':', 1)[1]] if name.startswith('ex:') else URIRef(name)

    def uncovered(self, instances):
        return coverage.uncovered_terms(instances, self.expand, self.shapes, [self.ontology],
                                        exempt_attributes=[BASE.hasNodeRef])

    def test_covered_subtype_entity(self):
        instances = [{'id': 'urn:x', 'type': 'ex:BSubType', '@context': [], 'ex:hasLevel': {},
                      str(BASE.hasNodeRef): {}}]
        self.assertEqual(self.uncovered(instances), {})

    def test_gaps_are_reported_per_type(self):
        instances = [
            {'id': 'urn:f', 'type': str(OPCUA.FolderType), 'ex:hasState': {}, 'ex:hasExtra': {}},
            {'id': 'urn:u', 'type': 'ex:UnknownType'},
        ]
        result = self.uncovered(instances)
        self.assertEqual(result[OPCUA.FolderType], {'no_shape': True, 'undeclared': {EX.hasExtra},
                                                    'unconstrained': {EX.hasState, EX.hasExtra}})
        self.assertTrue(result[EX.UnknownType]['no_shape'])

    def test_type_without_rules_needs_no_shape(self):
        instances = [{'id': 'urn:f', 'type': str(OPCUA.FolderType)}]
        self.assertTrue(self.uncovered(instances)[OPCUA.FolderType]['no_shape'])
        result = coverage.uncovered_terms(instances, self.expand, self.shapes, [self.ontology],
                                          lacks_shape=lambda objtype, targets: False)
        self.assertEqual(result, {})

    def test_format(self):
        result = self.uncovered([{'id': 'urn:f', 'type': str(OPCUA.FolderType), 'ex:hasExtra': {}}])
        compact = lambda iri: str(iri).rsplit('/', 1)[-1]  # noqa: E731
        self.assertEqual(coverage.format_uncovered(result, compact),
                         ['FolderType: no shape; not declared: hasExtra; not constrained: hasExtra'])

    def test_covering_domain_over_graphs(self):
        extra = Graph()
        extra.add((EX.hasOther, RDFS.domain, OPCUA.BaseObjectType))
        supertypes = coverage.all_supertypes([self.ontology, extra], EX.BSubType)
        self.assertEqual(supertypes, {EX.BSubType, EX.BType, OPCUA.BaseObjectType})
        self.assertTrue(coverage.has_covering_domain([self.ontology, extra], EX.hasOther, supertypes))
        self.assertFalse(coverage.has_covering_domain([self.ontology], EX.hasOther, supertypes))

    def add_declaration_shape(self):
        """BType's relationship hasBlocks applies the declaration shape BlocksDeclaration (path hasState) to the
        entity it refers to, as an instance declaration that adds members beyond the child's type does."""
        rel, obj, decl_prop = BNode(), BNode(), BNode()
        self.shapes.add((EX.BTypeShape, SH.property, rel))
        self.shapes.add((rel, SH.path, EX.hasBlocks))
        self.shapes.add((rel, SH.property, obj))
        self.shapes.add((obj, SH.path, coverage.NGSILD_HAS_OBJECT))
        self.shapes.add((obj, SH.node, EX.BlocksDeclaration))
        self.shapes.add((EX.BlocksDeclaration, SH.property, decl_prop))
        self.shapes.add((decl_prop, SH.path, EX.hasState))
        self.shapes.add((EX.FolderTypeShape, SH.targetClass, OPCUA.FolderType))

    def test_declaration_shape_constrains_the_referred_entity(self):
        self.add_declaration_shape()
        instances = [
            {'id': 'urn:b', 'type': 'ex:BType', 'ex:hasLevel': {},
             'ex:hasBlocks': [{'type': 'Relationship', 'object': 'urn:f'}]},
            {'id': 'urn:f', 'type': str(OPCUA.FolderType), 'ex:hasState': {}},
        ]
        self.ontology.add((EX.hasBlocks, RDFS.domain, EX.BType))
        self.assertEqual(self.uncovered(instances), {})

    def test_declaration_shape_applies_only_to_referred_entities(self):
        self.add_declaration_shape()
        instances = [
            {'id': 'urn:b', 'type': 'ex:BType', 'ex:hasLevel': {},
             'ex:hasBlocks': {'type': 'Relationship', 'object': 'urn:f'}},
            {'id': 'urn:g', 'type': str(OPCUA.FolderType), 'ex:hasState': {}},
        ]
        self.ontology.add((EX.hasBlocks, RDFS.domain, EX.BType))
        self.assertEqual(self.uncovered(instances)[OPCUA.FolderType]['unconstrained'], {EX.hasState})

    def test_subtype_with_own_members_without_shape_is_named(self):
        g = type_graph((EX.UnitSubType, EX.UnitType), (EX.UnitType, OPCUA.BaseObjectType),
                       defined=[EX.UnitSubType, EX.UnitType, OPCUA.BaseObjectType])
        rdfutils = StubRdfUtils(references={
            (typenode(EX.UnitSubType), OPCUA.HasChild): [(OPCUA.HasComponent, EX.extraVariable)],
        })
        shapes = Graph()
        shapes.add((EX.UnitTypeShape, SH.targetClass, EX.UnitType))
        instances = [{'id': 'urn:u', 'type': 'ex:UnitSubType'}]

        def lacks(objtype, targets):
            return coverage.lacks_shape(g, rdfutils, objtype, targets, [], [])

        result = coverage.uncovered_terms(instances, self.expand, shapes, [g], lacks_shape=lacks)
        self.assertTrue(result[EX.UnitSubType]['no_shape'])
        # without the member of its own, the supertype's shape covers the subtype
        rdfutils.references = {}
        self.assertEqual(coverage.uncovered_terms(instances, self.expand, shapes, [g], lacks_shape=lacks), {})

    def test_referred_entities(self):
        self.assertEqual(coverage.referred_entities({'type': 'Relationship', 'object': 'urn:a'}), ['urn:a'])
        self.assertEqual(coverage.referred_entities([{'type': 'Relationship', 'object': 'urn:a'},
                                                     {'type': 'Property', 'value': 1}, 'text']), ['urn:a'])
        self.assertEqual(coverage.referred_entities({'type': 'Relationship'}), [])


if __name__ == '__main__':
    unittest.main()
