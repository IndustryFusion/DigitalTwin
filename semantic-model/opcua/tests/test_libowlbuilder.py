# tests/test_libowlbuilder.py
import unittest
from pathlib import Path

from rdflib import Graph, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from lib.owlbuilder import OwlBuilder, VALUE_RANK_CLASSES

FIXTURE = Path(__file__).parent / 'owlbuilder' / 'pump_example.ttl'
COMPANION_FIXTURE = Path(__file__).parent / 'owlbuilder' / 'companion_example.ttl'

BASE = Namespace('https://industryfusion.github.io/contexts/ontology/v0/base/')
OPCUA = Namespace('http://opcfoundation.org/UA/')
COMP = Namespace('http://example.org/Companion/')


def load_builder(**kwargs):
    g = Graph()
    g.parse(FIXTURE, format='turtle')
    return OwlBuilder(g, BASE, OPCUA, **kwargs)


class TestEffectiveDeclarationTree(unittest.TestCase):
    def setUp(self):
        self.builder = load_builder()

    def key(self, name):
        return f'{OPCUA}{name}'

    def test_base_type_declares_drive(self):
        cdt = self.builder.get_cdt(OPCUA['BaseType'])
        self.assertEqual(set(cdt.keys()), {self.key('Drive')})
        self.assertEqual(cdt[self.key('Drive')].base_type, OPCUA['DriveType'])
        self.assertFalse(cdt[self.key('Drive')].is_optional)

    def test_drive_type_declares_motor(self):
        cdt = self.builder.get_cdt(OPCUA['DriveType'])
        self.assertEqual(cdt[self.key('Motor')].base_type, OPCUA['MotorType'])

    def test_advanced_drive_type_overrides_motor(self):
        cdt = self.builder.get_cdt(OPCUA['AdvancedDriveType'])
        self.assertEqual(cdt[self.key('Motor')].base_type, OPCUA['AdvancedMotorType'])

    def test_motor_type_declares_temperature(self):
        cdt = self.builder.get_cdt(OPCUA['MotorType'])
        entry = cdt[self.key('Temperature')]
        self.assertEqual(entry.base_type, OPCUA['PropertyType'])
        self.assertEqual(entry.nodeclass, OPCUA['VariableNodeClass'])
        self.assertEqual(entry.value_rank, -1)  # default: no explicit hasValueRank => Scalar
        self.assertEqual(entry.datatype, OPCUA['Double'])

    def test_advanced_motor_type_inherits_temperature_unchanged(self):
        # AdvancedMotorType has no own definer node in the fixture: pure inheritance.
        self.assertEqual(self.builder.get_cdt(OPCUA['AdvancedMotorType']),
                         self.builder.get_cdt(OPCUA['MotorType']))

    def test_pump_type_overrides_drive(self):
        cdt = self.builder.get_cdt(OPCUA['PumpType'])
        self.assertEqual(cdt[self.key('Drive')].base_type, OPCUA['AdvancedDriveType'])

    def test_advanced_pump_type_inherits_pump_type_unchanged(self):
        self.assertEqual(self.builder.get_cdt(OPCUA['AdvancedPumpType']),
                         self.builder.get_cdt(OPCUA['PumpType']))

    def test_resolve_path_follows_dimension_2_override(self):
        # Under BaseType, Drive/Motor is MotorType; under PumpType, the same
        # relative path is AdvancedMotorType because PumpType's Drive is
        # AdvancedDriveType, whose own Motor is overridden.
        path = [self.key('Drive'), self.key('Motor')]
        base_entry = self.builder.resolve_path(OPCUA['BaseType'], path)
        pump_entry = self.builder.resolve_path(OPCUA['PumpType'], path)
        self.assertEqual(base_entry.base_type, OPCUA['MotorType'])
        self.assertEqual(pump_entry.base_type, OPCUA['AdvancedMotorType'])

    def test_resolve_path_missing_returns_none(self):
        self.assertIsNone(self.builder.resolve_path(OPCUA['BaseObjectType'], [self.key('Drive')]))


class TestVirtualTypeEmission(unittest.TestCase):
    def setUp(self):
        self.builder = load_builder()
        self.out = self.builder.run()

    def vt(self, root, path):
        return self.builder._mint_vt_iri(OPCUA[root], [f'{OPCUA}{seg}' for seg in path])

    def type_supers(self, vt):
        """subClassOf targets that are real types/VTs, excluding this VT's own
        restriction blank nodes for whatever it in turn owns as a nested owner."""
        return {o for o in self.out.objects(vt, RDFS.subClassOf) if isinstance(o, URIRef)}

    def test_base_type_drive_has_no_supertype_link(self):
        vt_drive = self.vt('BaseType', ['Drive'])
        self.assertEqual(self.type_supers(vt_drive), {OPCUA['DriveType']})

    def test_pump_type_drive_has_both_override_and_inheritance_edges(self):
        vt_pump_drive = self.vt('PumpType', ['Drive'])
        vt_base_drive = self.vt('BaseType', ['Drive'])
        self.assertEqual(self.type_supers(vt_pump_drive), {OPCUA['AdvancedDriveType'], vt_base_drive})

    def test_pump_type_drive_motor_reflects_nested_override_and_links_to_base(self):
        vt_pump_drive_motor = self.vt('PumpType', ['Drive', 'Motor'])
        vt_base_drive_motor = self.vt('BaseType', ['Drive', 'Motor'])
        self.assertEqual(self.type_supers(vt_pump_drive_motor),
                         {OPCUA['AdvancedMotorType'], vt_base_drive_motor})

    def test_advanced_pump_type_drive_has_single_inheritance_edge_no_override(self):
        vt_adv = self.vt('AdvancedPumpType', ['Drive'])
        vt_pump = self.vt('PumpType', ['Drive'])
        # Same base_type as PumpType's Drive (no override at this level) => exactly
        # one rule-8 edge (AdvancedDriveType) and one rule-9 edge (vt_pump).
        self.assertEqual(self.type_supers(vt_adv), {OPCUA['AdvancedDriveType'], vt_pump})

    def test_mandatory_cardinality_on_owner(self):
        vt_drive = self.vt('BaseType', ['Drive'])
        card_restrictions = [r for r in self.out.subjects(RDF.type, OWL.Restriction)
                             if (r, OWL.onProperty, OPCUA['hasDrive']) in self.out and
                             (r, OWL.onClass, vt_drive) in self.out]
        self.assertEqual(len(card_restrictions), 1)
        card = card_restrictions[0]
        self.assertEqual(int(self.out.value(card, OWL.minQualifiedCardinality)), 1)
        self.assertIn((OPCUA['BaseType'], RDFS.subClassOf, card), self.out)

    def test_some_and_all_values_from_on_owner(self):
        vt_drive = self.vt('BaseType', ['Drive'])
        some = [r for r in self.out.subjects(OWL.someValuesFrom, vt_drive)
                if (r, OWL.onProperty, OPCUA['hasDrive']) in self.out]
        allv = [r for r in self.out.subjects(OWL.allValuesFrom, vt_drive)
                if (r, OWL.onProperty, OPCUA['hasDrive']) in self.out]
        self.assertEqual(len(some), 1)
        self.assertEqual(len(allv), 1)
        self.assertIn((OPCUA['BaseType'], RDFS.subClassOf, some[0]), self.out)
        self.assertIn((OPCUA['BaseType'], RDFS.subClassOf, allv[0]), self.out)

    def test_temperature_valuerank_and_datatype(self):
        vt_temp = self.vt('BaseType', ['Drive', 'Motor', 'Temperature'])
        self.assertIn((vt_temp, RDFS.subClassOf, OPCUA[VALUE_RANK_CLASSES[-1]]), self.out)
        datatype_restrictions = [r for r in self.out.subjects(RDF.type, OWL.Restriction)
                                 if (r, OWL.allValuesFrom, OPCUA['Double']) in self.out]
        self.assertTrue(any((vt_temp, RDFS.subClassOf, r) in self.out for r in datatype_restrictions))

    def test_virtual_types_are_explicitly_typed_owl_class(self):
        # Regression test: a Virtual Type must be an asserted owl:Class, not
        # merely implied by appearing as the object of rdfs:subClassOf/
        # someValuesFrom/etc. Protege's own OWL-API parser infers class-hood
        # from that usage context and renders the tree fine either way, but a
        # literal SPARQL query against the raw triples (e.g. `?c a owl:Class`)
        # only sees what's actually asserted, and found nothing without this.
        vt_drive = self.vt('BaseType', ['Drive'])
        self.assertIn((vt_drive, RDF.type, OWL.Class), self.out)

    def test_original_browsepath_annotation(self):
        vt_temp = self.vt('BaseType', ['Drive', 'Motor', 'Temperature'])
        path = self.out.value(vt_temp, self.builder.SB['originalBrowsePath'])
        self.assertEqual(str(path), f'{OPCUA}Drive/{OPCUA}Motor/{OPCUA}Temperature')

    def test_only_the_three_leaf_valuerank_classes_are_disjoint(self):
        # Scalar, OneDimension and MoreDimensions are mutually exclusive and must
        # be disjoint. Any, ScalarOrOneDimension and OneOrMoreDimensions are
        # composite/union categories that legitimately overlap with their own
        # subclasses (and, in OneDimension's case, with each other) and must NOT
        # be asserted disjoint.
        disjoint_nodes = list(self.out.subjects(RDF.type, OWL.AllDisjointClasses))
        self.assertEqual(len(disjoint_nodes), 1)
        members = set(Collection(self.out, self.out.value(disjoint_nodes[0], OWL.members)))
        self.assertEqual(members, {OPCUA['ValueRank_Scalar'], OPCUA['ValueRank_OneDimension'],
                                   OPCUA['ValueRank_MoreDimensions']})

    def test_valuerank_hierarchy_matches_opcua_semantics(self):
        # Any is the root (-2: scalar or an array of any rank).
        self.assertIn((OPCUA['ValueRank_ScalarOrOneDimension'], RDFS.subClassOf, OPCUA['ValueRank_Any']),
                      self.out)
        self.assertIn((OPCUA['ValueRank_OneOrMoreDimensions'], RDFS.subClassOf, OPCUA['ValueRank_Any']),
                      self.out)
        # ScalarOrOneDimension = Scalar or OneDimension.
        self.assertIn((OPCUA['ValueRank_Scalar'], RDFS.subClassOf, OPCUA['ValueRank_ScalarOrOneDimension']),
                      self.out)
        self.assertIn((OPCUA['ValueRank_OneDimension'], RDFS.subClassOf, OPCUA['ValueRank_ScalarOrOneDimension']),
                      self.out)
        # OneOrMoreDimensions = OneDimension or MoreDimensions -- OneDimension is
        # thus legitimately a subclass of BOTH composite categories.
        self.assertIn((OPCUA['ValueRank_OneDimension'], RDFS.subClassOf, OPCUA['ValueRank_OneOrMoreDimensions']),
                      self.out)
        self.assertIn((OPCUA['ValueRank_MoreDimensions'], RDFS.subClassOf, OPCUA['ValueRank_OneOrMoreDimensions']),
                      self.out)

    def test_no_instance_declaration_nodes_leak_into_output(self):
        leaked = list(self.out.subjects(RDF.type, OPCUA['ObjectNodeClass']))
        self.assertEqual(leaked, [])
        leaked_definer = list(self.out.subjects(self.builder.basens['definesType'], None))
        self.assertEqual(leaked_definer, [])

    def test_class_layer_is_preserved(self):
        self.assertIn((OPCUA['PumpType'], RDF.type, OWL.Class), self.out)
        self.assertIn((OPCUA['PumpType'], RDFS.subClassOf, OPCUA['BaseType']), self.out)

    def test_semantic_bridge_properties_are_declared_object_properties(self):
        # Regression test: core.ttl only ever asserts
        # `opcua:hasX rdfs:subPropertyOf base:SemanticBridgeReferenceType` for
        # these properties, never `a owl:ObjectProperty` -- and never types
        # base:SemanticBridgeReferenceType itself either. Any property used as
        # owl:onProperty in a restriction without being declared a property
        # causes Protege/OWL-API to substitute a synthetic "ErrorN" placeholder
        # class instead, so this must hold for every semantic bridge property
        # actually used in the output.
        for prop in (OPCUA['hasDrive'], OPCUA['hasMotor'], OPCUA['hasTemperature']):
            self.assertIn((prop, RDF.type, OWL.ObjectProperty), self.out)
            self.assertIn((prop, RDFS.subPropertyOf, self.builder.basens['SemanticBridgeReferenceType']),
                          self.out)
        self.assertIn((self.builder.basens['SemanticBridgeReferenceType'], RDF.type, OWL.ObjectProperty),
                      self.out)


class TestSelfReferentialTypeTerminates(unittest.TestCase):
    """Regression test for a real pattern in the OPC UA core nodeset: a type
    (e.g. DictionaryEntryType) declaring a placeholder child typed as itself.
    Without the `_visited` guard in emit_vt_tree, this recurses forever."""

    def setUp(self):
        self.builder = load_builder()

    def key(self, name):
        return f'{OPCUA}{name}'

    def test_cdt_contains_self_reference_without_hanging(self):
        cdt = self.builder.get_cdt(OPCUA['DictionaryEntryType'])
        self.assertEqual(cdt[self.key('Entry')].base_type, OPCUA['DictionaryEntryType'])

    def test_run_terminates_and_stops_expanding_at_first_repetition(self):
        self.builder.run(roots=[OPCUA['DictionaryEntryType']])
        # Only the one-level-deep VT should ever have been minted; a second,
        # nested "Entry/Entry" level must never have been generated.
        minted_paths = {path for (_root, path) in self.builder._vt_iri_cache}
        self.assertIn((self.key('Entry'),), minted_paths)
        self.assertNotIn((self.key('Entry'), self.key('Entry')), minted_paths)

    def test_forward_referenced_supertype_vt_is_not_dangling(self):
        # Regression test: scanning SpecialDictionaryEntryType (a subclass of
        # DictionaryEntryType with no own definer node) as root reaches
        # DictionaryEntryType's own two-level self-reference ("Entry/Entry") one
        # step further than DictionaryEntryType's own root-scan ever does (its
        # cycle cutoff kicks in a level earlier, since DictionaryEntryType is
        # "already visited" as soon as it's its own root). The rule-9 link then
        # mints DictionaryEntryType's "Entry/Entry" VT purely as a forward
        # reference. It must still end up with its own rdfs:subClassOf edge
        # (to DictionaryEntryType), not just rdf:type owl:Class + the
        # originalBrowsePath annotation and nothing else.
        out = self.builder.run(roots=[OPCUA['SpecialDictionaryEntryType']])
        path = (self.key('Entry'), self.key('Entry'))
        dangling_vt = self.builder._vt_iri_cache[(str(OPCUA['DictionaryEntryType']), path)]
        supers = {o for o in out.objects(dangling_vt, RDFS.subClassOf) if isinstance(o, URIRef)}
        self.assertIn(OPCUA['DictionaryEntryType'], supers)


class TestMethodsAreIgnored(unittest.TestCase):
    def test_method_declaration_produces_no_children_in_cdt(self):
        # No Method declarations in the fixture at all; this documents the
        # intended behaviour (see semantic_bridge_to_owl.md discussion): Methods
        # are skipped entirely for this phase, verified functionally by the
        # `nodeclass == MethodNodeClass: continue` guard in get_cdt.
        builder = load_builder()
        cdt = builder.get_cdt(OPCUA['MotorType'])
        for entry in cdt.values():
            self.assertNotEqual(entry.nodeclass, OPCUA['MethodNodeClass'])


class TestCompanionSpecIncrementalVirtualTypes(unittest.TestCase):
    """Mirrors the real di.ttl (imports core.ttl) scenario at small scale:
    companion_example.ttl declares comp:SpecialPumpType, a subclass of
    pump_example.ttl's opcua:PumpType, loaded here as an imported (`ig`)
    dependency rather than as the main graph."""

    def setUp(self):
        ig = Graph()
        ig.parse(FIXTURE, format='turtle')
        g = Graph()
        g.parse(COMPANION_FIXTURE, format='turtle')
        self.builder = OwlBuilder(g, BASE, OPCUA, ig=ig)
        self.out = self.builder.run()

    def test_all_target_classes_excludes_the_imported_dependencys_own_types(self):
        roots = self.builder.all_target_classes()
        self.assertIn(COMP['SpecialPumpType'], roots)
        self.assertNotIn(OPCUA['PumpType'], roots)
        self.assertNotIn(OPCUA['BaseType'], roots)

    def test_new_component_gets_a_fully_populated_vt_in_the_companion_namespace(self):
        key = f'{OPCUA}Extra'
        vt = self.builder._mint_vt_iri(COMP['SpecialPumpType'], [key])
        self.assertTrue(str(vt).startswith(str(COMP)), f'expected companion namespace, got {vt}')
        self.assertIn((vt, RDFS.subClassOf, OPCUA['MotorType']), self.out)

    def test_inherited_declaration_links_to_a_bare_reference_not_a_duplicate(self):
        # SpecialPumpType inherits "Drive" from PumpType (an imported-dependency
        # type). Rule 9 must link to PumpType's own Virtual Type for that path,
        # but must NOT re-populate its content here -- pump_example.ttl's own
        # separate processing run already fully defines it, and this file's
        # ontology header is assumed to owl:import that output.
        drive_key = f'{OPCUA}Drive'
        pump_vt = self.builder._mint_vt_iri(OPCUA['PumpType'], [drive_key])
        self.assertTrue(str(pump_vt).startswith(str(OPCUA)))
        self.assertEqual(list(self.out.predicate_objects(pump_vt)), [],
                         'imported dependency\'s own VT must be a bare reference, not duplicated content')

    def test_no_pump_example_classes_or_properties_are_copied_into_the_output(self):
        # _copy_class_and_property_layer must stay scoped to the companion
        # file's own new content; PumpType/BaseType etc. belong to
        # pump_example.ttl's own (separately generated) output.
        self.assertNotIn((OPCUA['PumpType'], RDF.type, OWL.Class), self.out)
        self.assertNotIn((OPCUA['BaseType'], RDF.type, OWL.Class), self.out)
        self.assertIn((COMP['SpecialPumpType'], RDF.type, OWL.Class), self.out)


if __name__ == '__main__':
    unittest.main()
