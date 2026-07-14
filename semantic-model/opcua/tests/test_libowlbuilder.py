# tests/test_libowlbuilder.py
import unittest
from pathlib import Path

from rdflib import Graph, Namespace
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


def key(name, ns=OPCUA):
    return f'{ns}{name}'


class TestEffectiveDeclarationTree(unittest.TestCase):
    """Fixture recap (see tests/owlbuilder/pump_example.ttl):
        BaseType          -- Drive:DriveType (Mandatory)
          DriveType       -- Motor:MotorType (Mandatory)
            MotorType     -- Temperature:PropertyType/Double (Optional, scalar)
        PumpType <: BaseType, overrides Drive:AdvancedDriveType
          AdvancedDriveType <: DriveType, overrides Motor:AdvancedMotorType
            AdvancedMotorType <: MotorType (no own definer node)
        AdvancedPumpType <: PumpType (no own definer node)
    """

    def setUp(self):
        self.builder = load_builder()

    def test_base_type_declares_drive(self):
        cdt = self.builder.get_cdt(OPCUA['BaseType'])
        self.assertEqual(set(cdt.keys()), {key('Drive')})
        self.assertEqual(cdt[key('Drive')].base_type, OPCUA['DriveType'])
        self.assertFalse(cdt[key('Drive')].is_optional)

    def test_drive_type_declares_motor(self):
        cdt = self.builder.get_cdt(OPCUA['DriveType'])
        self.assertEqual(cdt[key('Motor')].base_type, OPCUA['MotorType'])

    def test_advanced_drive_type_overrides_motor(self):
        cdt = self.builder.get_cdt(OPCUA['AdvancedDriveType'])
        self.assertEqual(cdt[key('Motor')].base_type, OPCUA['AdvancedMotorType'])

    def test_motor_type_declares_temperature(self):
        cdt = self.builder.get_cdt(OPCUA['MotorType'])
        entry = cdt[key('Temperature')]
        self.assertEqual(entry.base_type, OPCUA['PropertyType'])
        self.assertEqual(entry.nodeclass, OPCUA['VariableNodeClass'])
        self.assertEqual(entry.value_rank, -1)  # default: no explicit hasValueRank => Scalar
        self.assertEqual(entry.datatype, OPCUA['Double'])

    def test_advanced_motor_type_inherits_temperature_unchanged(self):
        # AdvancedMotorType has no own definer node in the fixture: pure
        # inheritance, reusing the exact same entries (same DeclEntry objects,
        # same .target) as MotorType -- no new axioms generated for it.
        self.assertEqual(self.builder.get_cdt(OPCUA['AdvancedMotorType']),
                         self.builder.get_cdt(OPCUA['MotorType']))

    def test_pump_type_overrides_drive(self):
        cdt = self.builder.get_cdt(OPCUA['PumpType'])
        self.assertEqual(cdt[key('Drive')].base_type, OPCUA['AdvancedDriveType'])

    def test_advanced_pump_type_inherits_pump_type_unchanged(self):
        self.assertEqual(self.builder.get_cdt(OPCUA['AdvancedPumpType']),
                         self.builder.get_cdt(OPCUA['PumpType']))

    def test_object_override_targets_the_real_type_directly_no_vt(self):
        # A plain Object override/new-declaration with no local extension
        # needs no synthetic Virtual Type: the real declared type already
        # fully specifies itself. Traced through the whole Drive/Motor chain.
        self.assertEqual(self.builder.get_cdt(OPCUA['BaseType'])[key('Drive')].target,
                         OPCUA['DriveType'])
        self.assertEqual(self.builder.get_cdt(OPCUA['DriveType'])[key('Motor')].target,
                         OPCUA['MotorType'])
        self.assertEqual(self.builder.get_cdt(OPCUA['AdvancedDriveType'])[key('Motor')].target,
                         OPCUA['AdvancedMotorType'])
        self.assertEqual(self.builder.get_cdt(OPCUA['PumpType'])[key('Drive')].target,
                         OPCUA['AdvancedDriveType'])

    def test_variable_declaration_always_gets_its_own_target_vt(self):
        # Variables always need their own Virtual Type (to carry
        # ValueRank/Datatype), even with no override at all.
        temp_entry = self.builder.get_cdt(OPCUA['MotorType'])[key('Temperature')]
        self.assertTrue(str(temp_entry.target).split('/')[-1].startswith('VT_'))

    def test_count_own_instance_declarations(self):
        # One physically-declared child each on BaseType (Drive), DriveType
        # (Motor), MotorType (Temperature), AdvancedDriveType (Motor
        # override), PumpType (Drive override) = 5, plus DictionaryEntryType's
        # own "Entry" and Entry's own nested "Label" = 2 more, for 7 total.
        # AdvancedMotorType/AdvancedPumpType/SpecialDictionaryEntryType have
        # no own definer node (pure inheritance) and contribute 0. Label is
        # counted here because counting is recursive (it walks into every
        # declaration's own children, not just the type's own direct ones) --
        # DictionaryEntryType's own "Revision" (no ModellingRule at all) is
        # NOT counted by the default, strict definition; see the next test.
        self.assertEqual(self.builder.count_own_instance_declarations(), 7)

    def test_count_own_instance_declarations_include_unruled(self):
        # Same tree, but now also counting DictionaryEntryType's own
        # "Revision" -- a child with no ModellingRule at all, mirroring the
        # real core.ttl pattern of named States/Transitions inside a
        # StateMachineType-derived type. 7 + 1 = 8.
        self.assertEqual(self.builder.count_own_instance_declarations(include_unruled=True), 8)


class TestVirtualTypeEmission(unittest.TestCase):
    def setUp(self):
        self.builder = load_builder()
        self.out = self.builder.run()

    def vt(self, owner, local_name, ns=OPCUA):
        """Look up an already-minted VT from the cache (populated by run())."""
        return self.builder._vt_cache[(str(OPCUA[owner]), key(local_name, ns))]

    def test_base_type_drive_restriction_targets_drive_type_directly(self):
        allv = [r for r in self.out.subjects(OWL.allValuesFrom, OPCUA['DriveType'])
                if (r, OWL.onProperty, OPCUA['hasDrive']) in self.out]
        self.assertEqual(len(allv), 1)
        self.assertIn((OPCUA['BaseType'], RDFS.subClassOf, allv[0]), self.out)

    def test_pump_type_drive_restriction_targets_advanced_drive_type_directly(self):
        allv = [r for r in self.out.subjects(OWL.allValuesFrom, OPCUA['AdvancedDriveType'])
                if (r, OWL.onProperty, OPCUA['hasDrive']) in self.out]
        self.assertEqual(len(allv), 1)
        self.assertIn((OPCUA['PumpType'], RDFS.subClassOf, allv[0]), self.out)

    def test_advanced_pump_type_gets_no_new_restrictions_at_all(self):
        # Pure pass-through (no own definer node): zero new axioms, relies
        # entirely on the class-level rdfs:subClassOf PumpType edge.
        restrictions_owned = [s for s in self.out.subjects(RDFS.subClassOf, None)
                              if s == OPCUA['AdvancedPumpType']]
        # AdvancedPumpType still has its one class-layer subClassOf(PumpType)
        # edge; it must NOT additionally own any owl:Restriction blank nodes.
        owned_restrictions = [o for _, o in self.out.predicate_objects(OPCUA['AdvancedPumpType'])
                              if (o, RDF.type, OWL.Restriction) in self.out]
        self.assertEqual(owned_restrictions, [])
        self.assertTrue(restrictions_owned)  # sanity: the class itself is in the graph

    def test_mandatory_cardinality_on_owner(self):
        card_restrictions = [r for r in self.out.subjects(RDF.type, OWL.Restriction)
                             if (r, OWL.onProperty, OPCUA['hasDrive']) in self.out and
                             (r, OWL.onClass, OPCUA['DriveType']) in self.out]
        self.assertEqual(len(card_restrictions), 1)
        card = card_restrictions[0]
        self.assertEqual(int(self.out.value(card, OWL.minQualifiedCardinality)), 1)
        self.assertIn((OPCUA['BaseType'], RDFS.subClassOf, card), self.out)

    def test_no_some_values_from_anywhere(self):
        # someValuesFrom is deliberately never emitted: logically equivalent
        # to minQualifiedCardinality(1, ...) for Mandatory (redundant), and
        # outright wrong for Optional (wrongly forces existence).
        self.assertEqual(len(list(self.out.subjects(OWL.someValuesFrom, None))), 0)

    def test_optional_variable_has_no_cardinality_restriction(self):
        # Temperature is Optional: allValuesFrom must exist on MotorType, but
        # no minQualifiedCardinality restriction should target its VT.
        vt_temp = self.vt('MotorType', 'Temperature')
        allv = [r for r in self.out.subjects(OWL.allValuesFrom, vt_temp)
                if (r, OWL.onProperty, OPCUA['hasTemperature']) in self.out]
        card = [r for r in self.out.subjects(RDF.type, OWL.Restriction)
                if (r, OWL.onClass, vt_temp) in self.out]
        self.assertEqual(len(allv), 1)
        self.assertIn((OPCUA['MotorType'], RDFS.subClassOf, allv[0]), self.out)
        self.assertEqual(card, [])

    def test_temperature_valuerank_and_datatype(self):
        vt_temp = self.vt('MotorType', 'Temperature')
        self.assertIn((vt_temp, RDFS.subClassOf, OPCUA[VALUE_RANK_CLASSES[-1]]), self.out)
        datatype_restrictions = [r for r in self.out.subjects(RDF.type, OWL.Restriction)
                                 if (r, OWL.allValuesFrom, OPCUA['Double']) in self.out]
        self.assertTrue(any((vt_temp, RDFS.subClassOf, r) in self.out for r in datatype_restrictions))

    def test_sibling_datatypes_are_disjoint(self):
        # Double and String are both direct children of BaseDataType in the
        # fixture -- a value can't be both, so they must be disjoint (the
        # same mechanism catching a Datatype override to an incompatible
        # sibling type, analogous to the ValueRank leaves).
        self.assertIn({OPCUA['Double'], OPCUA['String']}, self.all_disjoint_sets())

    def test_virtual_types_are_explicitly_typed_owl_class(self):
        # Regression test: a Virtual Type must be an asserted owl:Class, not
        # merely implied by appearing as the object of rdfs:subClassOf/etc.
        # Protege's own OWL-API parser infers class-hood from usage context
        # and renders the tree fine either way, but a literal SPARQL query
        # against the raw triples (e.g. `?c a owl:Class`) only sees what's
        # actually asserted.
        vt_temp = self.vt('MotorType', 'Temperature')
        self.assertIn((vt_temp, RDF.type, OWL.Class), self.out)

    def test_original_browsepath_annotation_is_the_local_key(self):
        # Annotation is now just the local BrowsePath segment where the VT is
        # minted, not a full multi-level path from some "root" -- there is no
        # more "root" concept driving generation.
        vt_temp = self.vt('MotorType', 'Temperature')
        path = self.out.value(vt_temp, self.builder.SB['originalBrowsePath'])
        self.assertEqual(str(path), key('Temperature'))

    def all_disjoint_sets(self):
        return [set(Collection(self.out, self.out.value(node, OWL.members)))
                for node in self.out.subjects(RDF.type, OWL.AllDisjointClasses)]

    def test_only_the_three_leaf_valuerank_classes_are_disjoint(self):
        # Scalar, OneDimension and MoreDimensions are mutually exclusive and must
        # be disjoint. Any, ScalarOrOneDimension and OneOrMoreDimensions are
        # composite/union categories that legitimately overlap with their own
        # subclasses (and, in OneDimension's case, with each other) and must NOT
        # be asserted disjoint.
        expected = {OPCUA['ValueRank_Scalar'], OPCUA['ValueRank_OneDimension'],
                    OPCUA['ValueRank_MoreDimensions']}
        self.assertIn(expected, self.all_disjoint_sets())

    def test_valuerank_hierarchy_matches_opcua_semantics(self):
        # Any is the root (-2: scalar or an array of any rank).
        self.assertIn((OPCUA['ValueRank_ScalarOrOneDimension'], RDFS.subClassOf, OPCUA['ValueRank_Any']),
                      self.out)
        self.assertIn((OPCUA['ValueRank_OneOrMoreDimensions'], RDFS.subClassOf, OPCUA['ValueRank_Any']),
                      self.out)
        # ScalarOrOneDimension = Scalar or OneDimension.
        one_dim = OPCUA['ValueRank_OneDimension']
        scalar_or_one_dim = OPCUA['ValueRank_ScalarOrOneDimension']
        one_or_more_dims = OPCUA['ValueRank_OneOrMoreDimensions']
        self.assertIn((OPCUA['ValueRank_Scalar'], RDFS.subClassOf, scalar_or_one_dim), self.out)
        self.assertIn((one_dim, RDFS.subClassOf, scalar_or_one_dim), self.out)
        # OneOrMoreDimensions = OneDimension or MoreDimensions -- OneDimension is
        # thus legitimately a subclass of BOTH composite categories.
        self.assertIn((one_dim, RDFS.subClassOf, one_or_more_dims), self.out)
        self.assertIn((OPCUA['ValueRank_MoreDimensions'], RDFS.subClassOf, one_or_more_dims), self.out)

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
    In the fixture, that declaration ("Entry") also has its own local extra
    child ("Label"), which forces a Virtual Type to be minted (a plain
    self-reference with no local extension needs no VT at all) -- and minting
    it recurses into get_cdt(DictionaryEntryType) while that very call is
    still being computed, exactly the cycle the `_cdt_computing` guard in
    get_cdt exists to break."""

    def setUp(self):
        self.builder = load_builder()

    def test_cdt_contains_self_reference_without_hanging(self):
        cdt = self.builder.get_cdt(OPCUA['DictionaryEntryType'])
        self.assertEqual(cdt[key('Entry')].base_type, OPCUA['DictionaryEntryType'])

    def test_entry_gets_its_own_vt_because_of_local_extension(self):
        out = self.builder.run(roots=[OPCUA['DictionaryEntryType']])
        entry_vt = self.builder._vt_cache[(str(OPCUA['DictionaryEntryType']), key('Entry'))]
        self.assertTrue(str(entry_vt).split('/')[-1].startswith('VT_'))
        self.assertIn((entry_vt, RDFS.subClassOf, OPCUA['DictionaryEntryType']), out)

    def test_entrys_own_local_label_child_still_gets_processed(self):
        # Despite the cycle guard truncating the ancestor side of the merge,
        # the VT's OWN local children (from the "Entry" node itself, not from
        # walking back into DictionaryEntryType) must still be picked up.
        out = self.builder.run(roots=[OPCUA['DictionaryEntryType']])
        entry_vt = self.builder._vt_cache[(str(OPCUA['DictionaryEntryType']), key('Entry'))]
        label_vt = self.builder._vt_cache[(str(entry_vt), key('Label'))]
        allv = [r for r in out.subjects(OWL.allValuesFrom, label_vt)
                if (r, OWL.onProperty, OPCUA['hasLabel']) in out]
        self.assertEqual(len(allv), 1)
        self.assertIn((entry_vt, RDFS.subClassOf, allv[0]), out)
        self.assertIn((label_vt, RDFS.subClassOf, OPCUA['PropertyType']), out)

    def test_special_dictionary_entry_type_reuses_the_same_entry_no_redundant_vt(self):
        # SpecialDictionaryEntryType <: DictionaryEntryType has no own definer
        # node: pure pass-through, reusing the exact same (cached) entry/target
        # -- no separate re-derivation happens just because a different class
        # is used as the processing root.
        self.builder.run(roots=[OPCUA['DictionaryEntryType'], OPCUA['SpecialDictionaryEntryType']])
        self.assertEqual(self.builder.get_cdt(OPCUA['SpecialDictionaryEntryType']),
                         self.builder.get_cdt(OPCUA['DictionaryEntryType']))


class TestRequireModellingRule(unittest.TestCase):
    """DictionaryEntryType's own definer node directly aggregates "Revision"
    (nodei2005) with no opcua:HasModellingRule triple at all, mirroring the
    real core.ttl pattern of named States/Transitions inside a
    StateMachineType-derived type. Default behavior (require_modelling_rule=
    False) processes it like any other declaration; require_modelling_rule=
    True must exclude it -- and everything nested inside it, though this
    fixture's Revision is a leaf -- entirely: no entry in the Effective
    Declaration Tree, no Virtual Type, no restriction on the owner."""

    def test_default_processes_the_unruled_child(self):
        builder = load_builder()
        cdt = builder.get_cdt(OPCUA['DictionaryEntryType'])
        self.assertIn(key('Revision'), cdt)
        out = builder.run(roots=[OPCUA['DictionaryEntryType']])
        # No ModellingRule at all means is_optional is None: allValuesFrom is
        # still written (unconditional, §14), but no cardinality restriction
        # (that only fires for is_optional is False, i.e. Mandatory).
        allv = [r for r in out.subjects(OWL.onProperty, OPCUA['hasRevision'])
                if (r, RDF.type, OWL.Restriction) in out]
        self.assertEqual(len(allv), 1)
        self.assertIn(OWL.allValuesFrom, [p for p in out.predicates(allv[0], None)])

    def test_require_modelling_rule_excludes_the_unruled_child(self):
        builder = load_builder(require_modelling_rule=True)
        cdt = builder.get_cdt(OPCUA['DictionaryEntryType'])
        self.assertNotIn(key('Revision'), cdt)
        self.assertIn(key('Entry'), cdt)  # Entry has a real ModellingRule, still processed
        out = builder.run(roots=[OPCUA['DictionaryEntryType']])
        self.assertEqual(list(out.subjects(OWL.onProperty, OPCUA['hasRevision'])), [])

    def test_require_modelling_rule_matches_strict_declaration_count(self):
        # The whole point: with require_modelling_rule=True, the number of
        # Virtual Types minted for DictionaryEntryType's own declarations
        # should be derivable from the strict (ModellingRule-only) count,
        # not the broader one that also counts Revision.
        builder = load_builder(require_modelling_rule=True)
        strict_count = builder.count_own_instance_declarations(include_unruled=False)
        broad_count = builder.count_own_instance_declarations(include_unruled=True)
        self.assertEqual(strict_count, 7)
        self.assertEqual(broad_count, 8)
        out = builder.run()
        vt_count = sum(1 for c in out.subjects(RDF.type, OWL.Class)
                       if str(c).split('/')[-1].startswith('VT_'))
        self.assertLessEqual(vt_count, strict_count)


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
    """Mirrors the real di.ttl (imports core.ttl) scenario at small scale
    (see tests/owlbuilder/companion_example.ttl):
        comp:SpecialPumpType <: opcua:PumpType
          declares a brand-new Variable "Extra" of its own.
        comp:SpecialMotorType <: opcua:MotorType
          overrides "Temperature"'s ValueRank (Scalar -> OneDimension, same
          Datatype), which must link back to pump_example.ttl's own already-
          generated VT(MotorType, "Temperature") as a bare reference."""

    def setUp(self):
        ig = Graph()
        ig.parse(FIXTURE, format='turtle')
        g = Graph()
        g.parse(COMPANION_FIXTURE, format='turtle')
        self.builder = OwlBuilder(g, BASE, OPCUA, ig=ig)
        self.out = self.builder.run()

    def test_count_own_instance_declarations_excludes_imported_dependency(self):
        # Only the companion's own new "Extra" and "Temperature" (override)
        # declarations should count -- PumpType/BaseType/... belong to
        # pump_example.ttl's own (separately counted) contribution.
        self.assertEqual(self.builder.count_own_instance_declarations(), 2)

    def test_all_target_classes_excludes_the_imported_dependencys_own_types(self):
        roots = self.builder.all_target_classes()
        self.assertIn(COMP['SpecialPumpType'], roots)
        self.assertIn(COMP['SpecialMotorType'], roots)
        self.assertNotIn(OPCUA['PumpType'], roots)
        self.assertNotIn(OPCUA['MotorType'], roots)

    def test_new_variable_gets_a_fully_populated_vt_in_the_companion_namespace(self):
        vt = self.builder._vt_cache[(str(COMP['SpecialPumpType']), key('Extra'))]
        self.assertTrue(str(vt).startswith(str(COMP)), f'expected companion namespace, got {vt}')
        self.assertIn((vt, RDFS.subClassOf, OPCUA['PropertyType']), self.out)

    def test_valuerank_override_mints_new_vt_linking_to_foreign_vt_as_bare_reference(self):
        # SpecialMotorType's own new VT for "Temperature" (ValueRank
        # overridden to OneDimension) must link back to MotorType's own
        # "Temperature" VT (from the dependency, ValueRank Scalar) -- but
        # that foreign VT must be a bare reference, no duplicated content.
        new_vt = self.builder._vt_cache[(str(COMP['SpecialMotorType']), key('Temperature'))]
        foreign_vt = self.builder._vt_cache[(str(OPCUA['MotorType']), key('Temperature'))]
        self.assertTrue(str(new_vt).startswith(str(COMP)))
        self.assertTrue(str(foreign_vt).startswith(str(OPCUA)))
        self.assertIn((new_vt, RDFS.subClassOf, OPCUA['ValueRank_OneDimension']), self.out)
        self.assertIn((new_vt, RDFS.subClassOf, foreign_vt), self.out)
        self.assertEqual(list(self.out.predicate_objects(foreign_vt)), [],
                         "dependency's own VT must be a bare reference, not duplicated content")

    def test_no_pump_example_classes_or_properties_are_copied_into_the_output(self):
        # _copy_class_and_property_layer must stay scoped to the companion
        # file's own new content; PumpType/BaseType etc. belong to
        # pump_example.ttl's own (separately generated) output.
        self.assertNotIn((OPCUA['PumpType'], RDF.type, OWL.Class), self.out)
        self.assertNotIn((OPCUA['BaseType'], RDF.type, OWL.Class), self.out)
        self.assertIn((COMP['SpecialPumpType'], RDF.type, OWL.Class), self.out)

    def test_new_datatype_sibling_picks_up_full_disjoint_set(self):
        # comp:CompanionEnum is a NEW child of opcua:BaseDataType, which
        # pump_example.ttl's own Double/String already extend. The companion
        # file's disjointness must include the full sibling set (old members
        # it doesn't own plus the new one it does), not just its own new
        # member in isolation.
        disjoint_sets = [set(Collection(self.out, self.out.value(node, OWL.members)))
                         for node in self.out.subjects(RDF.type, OWL.AllDisjointClasses)]
        expected = {OPCUA['Double'], OPCUA['String'], COMP['CompanionEnum']}
        self.assertIn(expected, disjoint_sets)


if __name__ == '__main__':
    unittest.main()
