#
# Copyright (c) 2026 Intel Corporation
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
"""Transform an OPC UA Semantic Bridge graph (Part 5 output) into an OWL
ontology of Virtual Types (Part 14 of owl_to_virtualtypes.md): every Instance
Declaration becomes a generated "Virtual Type" class, and the Instance
Declaration nodes themselves are dropped from the output.
"""

import hashlib
from dataclasses import dataclass
from typing import Optional

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD, split_uri

from lib.utils import RdfUtils, restore_type_of_node_iris

# Numeric OPC UA ValueRank -> symbolic class name (Part 14 §17).
# -3 ScalarOrOneDimension, -2 Any, -1 Scalar, 0 OneOrMoreDimensions, 1 OneDimension,
# >=2 collapse into MoreDimensions. Missing ValueRank triple defaults to Scalar (-1),
# which is how core.owl.ttl actually encodes the (very common) scalar case.
VALUE_RANK_CLASSES = {
    -3: 'ValueRank_ScalarOrOneDimension',
    -2: 'ValueRank_Any',
    -1: 'ValueRank_Scalar',
    0: 'ValueRank_OneOrMoreDimensions',
    1: 'ValueRank_OneDimension',
}
VALUE_RANK_MORE_DIMENSIONS = 'ValueRank_MoreDimensions'
VALUE_RANK_DEFAULT = -1

# The six symbolic classes are NOT a flat, pairwise-disjoint partition: per OPC UA's
# actual ValueRank semantics they form a subsumption hierarchy rooted at Any (a value
# rank of -2 literally means "scalar or an array of any rank", i.e. it is the
# superset of every other case). ScalarOrOneDimension = Scalar or OneDimension;
# OneOrMoreDimensions = OneDimension or MoreDimensions. OneDimension is therefore a
# legitimate subclass of *both* composite categories, and none of the three
# composite/union classes (Any, ScalarOrOneDimension, OneOrMoreDimensions) are
# disjoint from each other or from their own subclasses -- they overlap by
# definition. Only the three mutually-exclusive leaves (a value is either exactly
# scalar, exactly one-dimensional, or 2+-dimensional -- never more than one of
# those) are genuinely disjoint.
VALUE_RANK_SUBCLASS_OF = {
    'ValueRank_Scalar': ['ValueRank_ScalarOrOneDimension'],
    'ValueRank_OneDimension': ['ValueRank_ScalarOrOneDimension', 'ValueRank_OneOrMoreDimensions'],
    VALUE_RANK_MORE_DIMENSIONS: ['ValueRank_OneOrMoreDimensions'],
    'ValueRank_ScalarOrOneDimension': ['ValueRank_Any'],
    'ValueRank_OneOrMoreDimensions': ['ValueRank_Any'],
}
VALUE_RANK_DISJOINT_LEAVES = ['ValueRank_Scalar', 'ValueRank_OneDimension', VALUE_RANK_MORE_DIMENSIONS]

SEMANTIC_BRIDGE_NS = Namespace('https://industryfusion.github.io/contexts/ontology/v0/semanticbridge/')


@dataclass
class DeclEntry:
    """One entry of an Effective Declaration Tree: a single declared child at a
    given BrowsePath segment, already merged with whatever the direct supertype
    inherited at the same segment.

    `target` is what a restriction on this declaration should actually point
    at, resolved need-based (see OwlBuilder._resolve_target): the inherited
    target unchanged (pure pass-through -- nothing new to say), the real
    declared type directly (a plain Object override/new declaration with no
    extra local content -- the real type already fully specifies itself, no
    synthetic wrapper needed), or a freshly minted Virtual Type (needed
    whenever the declaration itself carries content beyond a bare type
    reference)."""
    base_type: URIRef
    nodeclass: URIRef
    semantic_property: Optional[URIRef]
    is_optional: Optional[bool]
    is_placeholder: bool
    target: Optional[URIRef] = None
    value_rank: Optional[int] = None
    datatype: Optional[URIRef] = None


class OwlBuilder:
    SB = SEMANTIC_BRIDGE_NS

    def __init__(self, g: Graph, basens: Namespace, opcuans: Namespace, disjoint_valuerank: bool = True,
                 ig: Graph = None, require_modelling_rule: bool = False):
        """
        g: the semantic bridge graph to generate Virtual Types FOR (e.g. di.owl.ttl).
           Only classes/properties actually declared in `g` are scanned as VT
           roots or copied into the output -- this is what makes companion-spec
           processing incremental rather than re-deriving core.owl.ttl's own Virtual
           Types every time.
        ig: already-processed *imported* dependency graph(s) (e.g. core.owl.ttl),
            needed only to resolve cross-file references -- a companion spec's
            types routinely subclass or aggregate core types directly
            (di:SomeType rdfs:subClassOf opcua:BaseObjectType). Never scanned as
            VT roots and never copied into the output; assumed to already have
            its own separately-generated Virtual-Types output that this one's
            ontology header will owl:import.
        require_modelling_rule: if True, a declaration with no recognized
            ModellingRule (Mandatory/Optional/(Mandatory|Optional)Placeholder)
            -- most commonly a named State/Transition inside a
            StateMachineType-derived type -- is skipped entirely: no entry in
            the Effective Declaration Tree, no Virtual Type, no restriction,
            and nothing nested inside it is visited either. Default False
            matches historical behavior (every Object/Variable child is
            processed regardless of ModellingRule presence). This exists so
            a Virtual Type count and an Instance Declaration count can be
            produced from the *same* strict definition of "Instance
            Declaration" -- see count_own_instance_declarations's own
            docstring for why counting one way and minting the other
            produces a mismatched, hard-to-interpret ratio.
        """
        self.g = g
        self.ig = ig if ig is not None else Graph()
        for label, graph in (('g', self.g), ('ig', self.ig)):
            if (None, self.SB['originalBrowsePath'], None) in graph:
                raise ValueError(
                    f'This input ({label}) already looks like a generated Virtual-Types '
                    'ontology: it contains sb:originalBrowsePath annotations, which '
                    'OwlBuilder only ever writes to its own *output*, never reads from '
                    'input. Feeding an already-generated *.vt.owl.ttl file back in as input '
                    '(instead of the original semantic-bridge ttl, e.g. core.owl.ttl rather '
                    'than core.vt.owl.ttl) silently reprocesses Virtual Types as if they were '
                    'real declared OPC UA subtypes -- in particular, '
                    '_add_sibling_type_disjointness sweeps them into spurious '
                    '"mutually exclusive siblings" groups with every other Virtual Type '
                    'that happens to share the same nominal type, producing a false, '
                    'misleading HermiT contradiction that has nothing to do with the '
                    'actual OPC UA model. Pass the semantic-bridge ttl instead.')
        self.basens = basens
        self.opcuans = opcuans
        self.rdfutils = RdfUtils(basens, opcuans)
        self.disjoint_valuerank = disjoint_valuerank
        self.require_modelling_rule = require_modelling_rule
        self.out = Graph()
        self.out.bind('opcua', opcuans)
        self.out.bind('base', basens)
        self.out.bind('sb', self.SB)
        self._cdt_cache = {}
        self._cdt_computing = set()
        self._definer_node_cache = {}
        self._vt_cache = {}
        self._valuerank_vocabulary_emitted = False
        self._own_classes = set(g.subjects(RDF.type, OWL.Class))
        # Part 5 (nodeset2owl.py) rewrites `?instance a ?type` into
        # `?instance base:instanceOf ?type` for Object instance declarations right
        # before serializing core.owl.ttl (see utils.replace_type_of_node_iris), so that
        # downstream JSON-LD validation doesn't confuse declarations with real
        # classes. Undo that here so RdfUtils.get_type() works uniformly for Object
        # and Variable declarations, exactly as it does inside the Part-5/SHACL code.
        # Needed on both graphs independently: `g`'s own declarations and any
        # imported dependency's declarations each went through the same rewrite.
        restore_type_of_node_iris(self.g, self.opcuans, self.basens)
        restore_type_of_node_iris(self.ig, self.opcuans, self.basens)
        # All *read*-side structural lookups (definer nodes, supertypes, browse
        # names, ...) query this combined view, since a companion spec's type
        # hierarchy and declaration trees routinely span both graphs. Only the
        # *write*-side scans (all_target_classes, _copy_class_and_property_layer)
        # are deliberately scoped to `g` alone.
        self.combined = self.g + self.ig
        # get_all_subreferences() re-parses and re-plans a SPARQL query (with a
        # transitive rdfs:subPropertyOf* property path) on every single call. The
        # need-based design calls the HasChild lookup once per *declaration entry*
        # (via _has_local_children), not once per *type* as the old exhaustive
        # design did, so that per-call overhead now dominates runtime on any file
        # with many instance declarations. The set of HasChild subproperties is
        # small and static (an ontology-level fact, independent of instance data),
        # so compute it once here and use plain triple matching everywhere else.
        self._haschild_properties = self._compute_haschild_properties()

    def _compute_haschild_properties(self):
        query = """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?p WHERE { ?p rdfs:subPropertyOf* ?haschild }
        """
        result = self.combined.query(query, initBindings={'haschild': self.opcuans['HasChild']})
        return frozenset(row[0] for row in result)

    def _get_children(self, node):
        """Equivalent to RdfUtils.get_all_subreferences(combined, node,
        HasChild), but via a cached property set and plain triple matching
        instead of a fresh SPARQL query per call (see _compute_haschild_properties)."""
        return [(p, o) for p, o in self.combined.predicate_objects(node) if p in self._haschild_properties]

    def _get_type(self, node):
        """Equivalent to RdfUtils.get_type(combined, node) -- (nodeclass,
        declared-type) -- but via plain triple matching instead of a fresh
        SPARQL query per call. query_realtype has no transitive property
        path at all (unlike get_all_subreferences' rdfs:subPropertyOf*), so
        it never needed SPARQL in the first place; it's just as hot a call
        site (once per declaration entry via _merge_local/_has_local_children)
        and dominates runtime on large files the same way get_all_subreferences
        did (see _compute_haschild_properties's docstring)."""
        opcua_prefix = str(self.opcuans)
        nodeclass = None
        realtype = None
        for t in self.combined.objects(node, RDF.type):
            if t == OWL.NamedIndividual:
                continue
            ts = str(t)
            if ts.startswith(opcua_prefix) and ts.endswith('NodeClass'):
                nodeclass = t
            else:
                realtype = t
        if realtype is None:
            defines = next(self.combined.objects(node, self.basens['definesType']), None)
            if defines is not None and (node, RDF.type, self.opcuans['ObjectTypeNodeClass']) in self.combined:
                realtype = defines
        return nodeclass, realtype

    # ------------------------------------------------------------------
    # Graph primitives
    # ------------------------------------------------------------------

    def _definer_node(self, class_iri):
        if class_iri not in self._definer_node_cache:
            node = next(self.combined.subjects(self.basens['definesType'], class_iri), None)
            self._definer_node_cache[class_iri] = node
        return self._definer_node_cache[class_iri]

    def _direct_supertype(self, class_iri):
        return next(self.combined.objects(class_iri, RDFS.subClassOf), None)

    def _qualified_browsename(self, node):
        """Namespace-URI-qualified BrowseName segment, e.g.
        'http://opcfoundation.org/UA/Drive' (namespace URIs always end in '/'
        or '#', so no separator is needed between the two).

        Deliberately *not* Clark notation ('{uri}name'): Protege's annotation
        renderer treats any literal containing a colon as a possible CURIE and
        extracts the substring before the first ':' as a "prefix" to look up
        against bioregistry.io. A literal starting '{http://...' yields the
        prefix '{http', and '{' is an illegal character in a URI path, which
        crashes java.net.URI.create() when Protege builds the lookup URL.
        Plain concatenation still starts with the harmless prefix 'http' and
        does not crash (it just fails the bioregistry lookup silently)."""
        browsename = next(self.combined.objects(node, self.basens['hasBrowseName']))
        ns_node = next(self.combined.objects(node, self.basens['hasBrowseNameNamespace']))
        ns_uri = next(self.combined.objects(ns_node, self.basens['hasUri']))
        return f'{ns_uri}{browsename}'

    def _value_rank(self, node):
        rank = next(self.combined.objects(node, self.basens['hasValueRank']), None)
        return int(rank) if rank is not None else VALUE_RANK_DEFAULT

    def _datatype(self, node):
        return next(self.combined.objects(node, self.basens['hasDatatype']), None)

    def all_target_classes(self):
        """Every ObjectType/VariableType class actually declared in `g` (not
        `ig`) -- Part 14 requires a Virtual Type generation pass over *every*
        type, not just leaf/concrete ones, since supertype VTs must exist for
        subtypes to link against, but only for types this graph itself
        introduces. An imported dependency's own types (e.g. core.owl.ttl's, when
        processing di.owl.ttl) were already fully virtualized when that dependency
        was processed on its own; re-deriving them here would just duplicate
        that earlier output. The subClassOf* chain is walked over the combined
        graph, since a companion spec's types routinely subclass a core type
        several levels up before reaching BaseObjectType/BaseVariableType."""
        query = """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?type WHERE {
            { ?type rdfs:subClassOf* opcua:BaseObjectType }
            UNION
            { ?type rdfs:subClassOf* opcua:BaseVariableType }
        }
        """
        result = self.combined.query(query, initNs={'opcua': self.opcuans})
        own_classes = set(self.g.subjects(RDF.type, OWL.Class))
        return sorted({row[0] for row in result if row[0] in own_classes}, key=str)

    def count_own_instance_declarations(self, include_unruled=False):
        """Total number of Instance Declarations that `g` itself introduces,
        counted *recursively* at every nesting depth reachable from each of
        `g`'s own ObjectType/VariableType declarations (Methods excluded) --
        i.e. every node get_cdt's own recursive merge actually visits and
        could mint a Virtual Type for. This is deliberately not a one-level,
        un-expanded count: a declaration nested inside another declaration
        (e.g. a Property local to an Object that is itself a child of a
        type) is exactly as real, and exactly as capable of needing its own
        Virtual Type, as a direct child of the type's own definer node --
        counting only the first level silently ignores most of the tree
        Virtual Type generation actually processes.

        By default (include_unruled=False) only a child that carries a
        recognized ModellingRule (Mandatory/Optional/
        (Mandatory|Optional)Placeholder) counts -- the strict OPC UA sense
        of "Instance Declaration", the thing this method is named for.
        Under this strict definition, Virtual Type count is *not*
        guaranteed to stay at or below this count: OPC UA also aggregates
        nodes via HasComponent/HasProperty with no ModellingRule at all --
        commonly the named States/Transitions inside a StateMachineType-
        derived type (e.g. ExclusiveLimitStateMachineType's "High",
        "HighToHighHigh") are not optional-or-mandatory in the usual sense
        (always present, more like fixed enum members) but still carry real
        structure and can still need their own Virtual Type. If the
        Virtual Type count for a file exceeds this strict count, check
        whether that file has any such unruled-but-structural children
        (include_unruled=True) before treating it as a bug: it very often
        is exactly this legitimate case, not an algorithm defect.

        Pass include_unruled=True to also count those nodes. This broader
        count *is* a provable upper bound on Virtual Type count: every node
        it counts is processed by _merge_local's loop exactly once, which
        calls _resolve_target which calls _mint_vt at most once per
        (owner, key) pair (cached, never re-minted), so the Virtual Type
        count can never exceed this broader count -- verified with zero
        exceptions across the full default corpus.

        A node reachable via more than one aggregation edge within the same
        tree -- legal in OPC UA and not uncommon: HasAddIn exists precisely
        to re-expose one real object from a second place, e.g.
        "Identification" both directly on a device and again under a
        grouping folder -- is one Instance Declaration, counted once, not
        once per incoming edge. Confirmed against a SPARQL-based
        cross-check (virtual_type_stats.py's own sparql_count_instance_
        declarations, built independently against the same graphs) across
        the full default corpus: the two now agree exactly."""
        count = 0
        for class_iri in self.all_target_classes():
            definer_node = self._definer_node(class_iri)
            if definer_node is None:
                continue
            seen = set()

            def visit(node, owner):
                nonlocal count
                if node in seen:
                    return
                seen.add(node)
                for _refprop, child in self._get_children(node):
                    nodeclass, base_type = self._get_type(child)
                    if nodeclass == self.opcuans['MethodNodeClass'] or base_type is None:
                        continue
                    is_optional, _ = self.rdfutils.get_modelling_rule(
                        self.combined, child, None, owner)
                    if is_optional is None and not include_unruled:
                        continue
                    # A node reachable via more than one aggregation edge
                    # within the same tree (OPC UA's HasAddIn is built for
                    # exactly this: re-exposing one real object from a
                    # second place, e.g. "Identification" both directly on
                    # a device and again under a grouping folder) is one
                    # Instance Declaration, not two -- only count it the
                    # first time `seen` encounters it; still descend every
                    # time an edge reaches it (harmless no-op via the
                    # `node in seen` guard above once it's already been
                    # visited), since a later edge could be the first to
                    # reach an otherwise-unvisited grandchild.
                    if child not in seen:
                        count += 1
                    visit(child, owner)

            visit(definer_node, class_iri)
        return count

    # ------------------------------------------------------------------
    # Effective Declaration Tree (§4) -- need-based Virtual Type minting
    # ------------------------------------------------------------------
    #
    # A Virtual Type is only minted where a declaration's own content actually
    # differs from what's already established further up the inheritance
    # chain: a type override, a ValueRank/Datatype change (Variables), or the
    # declaration node having its own local children beyond what its nominal
    # type provides (OPC UA lets a declaration retype-by-addition, not just
    # retype-by-substitution -- e.g. a component typed as the bare, empty
    # opcua:BaseObjectType that locally adds its own specific sub-properties;
    # see the "LiveValues" example in PubSubDiagnosticsDataSetWriterType).
    # Pure pass-through (inherited, nothing changed) needs nothing at all:
    # ordinary rdfs:subClassOf already propagates the ancestor's restriction
    # for free. A ModellingRule-only change (same target, different
    # cardinality) doesn't need a new Virtual Type either, just a new
    # cardinality restriction on the owner targeting whatever's already
    # established -- cardinality is a property of the *edge*, not the target.

    def _add_own_variable_type_restrictions(self, class_iri, definer_node):
        """A VariableType (or Variable) can explicitly declare its OWN
        ValueRank/DataType on its own definer node -- an attribute of the
        type itself, distinct from and orthogonal to an *instance
        declaration*'s own ValueRank/DataType where this class happens to
        be the TypeDefinition (see _merge_local/_resolve_target). OPC UA
        requires an instance's ValueRank/DataType to be compatible with its
        own TypeDefinition's, so without asserting this class's own
        explicitly-declared ValueRank/DataType here too, an incompatible
        instance-level override could never surface as a contradiction: the
        instance's Virtual Type would be subClassOf this class (its nominal
        type) but this class itself would carry no ValueRank/DataType
        restriction at all for a reasoner to conflict with.

        Deliberately scoped to only fire when a ValueRank/DataType is
        *explicitly* declared on the type's own definer node, not the
        default-when-absent case (Scalar): only a handful of real
        VariableTypes in core.owl.ttl ever do this (verified: 4, out of ~600
        types), so this is a narrow, low-risk addition, not a blanket new
        axiom asserted on every VariableType regardless of whether it says
        anything about ValueRank/DataType at all."""
        if definer_node is None:
            return
        rank = next(self.combined.objects(definer_node, self.basens['hasValueRank']), None)
        if rank is not None:
            self._add_valuerank_restriction(class_iri, int(rank))
        datatype = next(self.combined.objects(definer_node, self.basens['hasDatatype']), None)
        if datatype is not None:
            self._add_datatype_restriction(class_iri, datatype)

    def get_cdt(self, class_iri):
        """Effective Declaration Tree of class_iri: dict[qualified_browsename
        -> DeclEntry], merged with the direct supertype's own tree (local
        wins on key collision). Each entry's `.target` is resolved need-based
        by _resolve_target, and writes whatever axioms it requires as a side
        effect (only if class_iri belongs to `g` -- see `is_own` throughout)."""
        if class_iri in self._cdt_cache:
            return self._cdt_cache[class_iri]
        if class_iri in self._cdt_computing:
            # Self-referential type (e.g. DictionaryEntryType declares a
            # placeholder child typed as itself): break the cycle by treating
            # the not-yet-resolved ancestor tree as empty at this point.
            return {}
        self._cdt_computing.add(class_iri)
        try:
            super_iri = self._direct_supertype(class_iri)
            parent_tree = self.get_cdt(super_iri) if super_iri is not None else {}
            is_own = class_iri in self._own_classes
            definer_node = self._definer_node(class_iri)
            if is_own:
                self._add_own_variable_type_restrictions(class_iri, definer_node)
            result = self._merge_local(parent_tree, definer_node, class_iri, is_own)
        finally:
            self._cdt_computing.discard(class_iri)
        self._cdt_cache[class_iri] = result
        return result

    def _merge_local(self, parent_tree, source_node, owner, is_own):
        """Merge source_node's own direct HasChild children into parent_tree
        (local declarations override/extend on key collision, otherwise
        pure inheritance pass-through). `owner` is whatever the resulting
        restrictions should be attached to: a real class (from get_cdt) or a
        freshly minted Virtual Type (from _mint_vt's own nested recursion)."""
        result = dict(parent_tree)
        if source_node is None:
            return result
        children = self._get_children(source_node)
        for _refprop, child in children:
            nodeclass, base_type = self._get_type(child)
            if nodeclass == self.opcuans['MethodNodeClass'] or base_type is None:
                continue  # Methods are out of scope for this phase.
            is_optional, is_placeholder = self.rdfutils.get_modelling_rule(self.combined, child, None, owner)
            if self.require_modelling_rule and is_optional is None:
                # No recognized ModellingRule (e.g. a StateMachineType State/
                # Transition): excluded entirely, not just left un-VT'd, so
                # counting and minting agree on what "Instance Declaration" means.
                continue
            key = self._qualified_browsename(child)
            inherited_entry = parent_tree.get(key)
            semantic_property = self.rdfutils.get_semantic_bridge(self.combined, source_node, child)
            entry = DeclEntry(
                base_type=base_type,
                nodeclass=nodeclass,
                semantic_property=semantic_property,
                is_optional=is_optional,
                is_placeholder=is_placeholder,
            )
            if nodeclass == self.opcuans['VariableNodeClass']:
                entry.value_rank = self._value_rank(child)
                entry.datatype = self._datatype(child)
            entry.target = self._resolve_target(owner, key, entry, inherited_entry, child, is_own)
            result[key] = entry
            if is_own and self._needs_owner_restriction(entry, inherited_entry):
                self._write_owner_restriction(owner, entry)
        return result

    def _has_local_children(self, node):
        """Does this specific declaration node have its own direct HasChild
        children (Methods excluded), beyond whatever its nominal type alone
        provides? True only for the rare "retype-by-addition" pattern.

        Respects require_modelling_rule the same way _merge_local does: a
        child with no recognized ModellingRule doesn't count here either
        when that mode is on, since _merge_local would exclude it entirely
        rather than just leave it un-VT'd -- a node whose only local
        children are like that has no local children under this stricter
        definition of "Instance Declaration"."""
        children = self._get_children(node)
        for _ref, child in children:
            nodeclass, base_type = self._get_type(child)
            if nodeclass == self.opcuans['MethodNodeClass'] or base_type is None:
                continue
            if self.require_modelling_rule:
                is_optional, _ = self.rdfutils.get_modelling_rule(self.combined, child, None, None)
                if is_optional is None:
                    continue
            return True
        return False

    def _resolve_target(self, owner, key, entry, inherited_entry, node, is_own):
        """What should a restriction on this declaration point at? See the
        module-level rationale above this class's Effective Declaration Tree
        section for the full reasoning."""
        own_local_children = self._has_local_children(node)

        if entry.nodeclass == self.opcuans['VariableNodeClass']:
            type_changed = inherited_entry is None or inherited_entry.base_type != entry.base_type
            valuerank_changed = inherited_entry is None or inherited_entry.value_rank != entry.value_rank
            datatype_changed = inherited_entry is None or inherited_entry.datatype != entry.datatype
            needs_vt = type_changed or valuerank_changed or datatype_changed or own_local_children
            if not needs_vt:
                return inherited_entry.target  # nothing changed at all: reuse
            return self._mint_vt(owner, key, entry, inherited_entry, node, is_own)

        # Object declaration: a plain type override or brand-new declaration,
        # with no local extension, needs no synthetic wrapper -- the real
        # declared type already fully specifies itself (it's independently
        # processed, like every other class in `all_target_classes()`).
        if own_local_children:
            return self._mint_vt(owner, key, entry, inherited_entry, node, is_own)
        return entry.base_type

    def _needs_owner_restriction(self, entry, inherited_entry):
        if entry.semantic_property is None:
            return False
        if inherited_entry is None:
            return True
        return entry.target != inherited_entry.target or entry.is_optional != inherited_entry.is_optional

    def _write_owner_restriction(self, owner, entry):
        self._add_all_values_from(owner, entry.semantic_property, entry.target)
        if entry.is_optional is False:  # Mandatory or MandatoryPlaceholder
            self._add_cardinality(owner, entry.semantic_property, entry.target)

    # ------------------------------------------------------------------
    # Virtual Type identity (§6-7)
    # ------------------------------------------------------------------

    def _mint_vt(self, owner, key, entry, inherited_entry, node, is_own):
        """Mint (or fetch) the Virtual Type for (owner, key) -- only reached
        when the declaration genuinely needs its own identity (see
        _resolve_target). Namespaced under `owner`'s own namespace (`owner`
        may be a real class or a previously minted VT, both are URIRefs).

        Companion-spec case: `is_own` is False when `owner` belongs to an
        *imported* dependency rather than to the file this OwlBuilder is
        generating output for (e.g. di.owl.ttl reading core.owl.ttl's own
        AnalogUnitType to correctly link/inherit from it). The VT's IRI is
        still computed (deterministically, so our own references match it),
        but its content must NOT be (re-)populated here: that dependency was
        already processed on its own and fully defines this exact VT in its
        own output file, which this file's ontology header owl:imports.
        Populating it again here would just duplicate that file's axioms."""
        cache_key = (str(owner), key)
        if cache_key in self._vt_cache:
            return self._vt_cache[cache_key]
        digest = hashlib.sha256(f'{owner}|{key}'.encode('utf-8')).hexdigest()[:24]
        vt_namespace = Namespace(split_uri(owner)[0])
        vt_iri = vt_namespace[f'VT_{digest}']
        self._vt_cache[cache_key] = vt_iri

        if not is_own:
            return vt_iri  # foreign: bare reference only, see docstring

        self.out.add((vt_iri, RDF.type, OWL.Class))
        self.out.add((vt_iri, self.SB['originalBrowsePath'], Literal(key)))
        self.out.add((vt_iri, RDFS.subClassOf, entry.base_type))  # §8 base typing rule

        if entry.nodeclass == self.opcuans['VariableNodeClass']:
            self._add_valuerank_restriction(vt_iri, entry.value_rank)
            self._add_datatype_restriction(vt_iri, entry.datatype)

        if inherited_entry is not None:
            # §9/§10: narrow relative to whatever was already established --
            # both edges land on vt_iri, so a reasoner can catch a genuinely
            # incompatible narrowing.
            self.out.add((vt_iri, RDFS.subClassOf, inherited_entry.target))

        # Recurse: this VT's own nested declarations = merge(the nominal
        # type's own effective tree, this specific node's own local
        # children) -- exactly what made the "LiveValues" example work.
        self._merge_local(self.get_cdt(entry.base_type), node, vt_iri, is_own)
        return vt_iri

    # ------------------------------------------------------------------
    # Restrictions (§13-16)
    # ------------------------------------------------------------------

    def _ensure_object_property(self, prop):
        if (prop, RDF.type, OWL.ObjectProperty) not in self.out:
            self.out.add((prop, RDF.type, OWL.ObjectProperty))

    def _add_all_values_from(self, owner, prop, target_class):
        # §14 universal restriction, applied unconditionally regardless of
        # ModellingRule -- correct for both Mandatory and Optional, since it
        # vacuously holds when the property has zero values.
        #
        # Deliberately NOT also asserting owl:someValuesFrom here: it is
        # logically equivalent to owl:minQualifiedCardinality(1, ...) under
        # OWL 2 semantics (existsP.C == >=1 P.C without the unique name
        # assumption), so for Mandatory it would be pure redundancy with
        # _add_cardinality below -- and for Optional it would be outright
        # wrong, wrongly forcing every instance to have the relationship,
        # contradicting "optional" (which must permit zero occurrences). §16
        # confirms this: Optional "does not require a minimum-cardinality
        # restriction... may still generate allValuesFrom constraints" --
        # someValuesFrom was never meant to apply there either.
        self._ensure_object_property(prop)
        allv = BNode()
        self.out.add((allv, RDF.type, OWL.Restriction))
        self.out.add((allv, OWL.onProperty, prop))
        self.out.add((allv, OWL.allValuesFrom, target_class))
        self.out.add((owner, RDFS.subClassOf, allv))

    def _add_cardinality(self, owner, prop, target_class):
        self._ensure_object_property(prop)
        card = BNode()
        self.out.add((card, RDF.type, OWL.Restriction))
        self.out.add((card, OWL.onProperty, prop))
        self.out.add((card, OWL.minQualifiedCardinality, Literal(1, datatype=XSD.nonNegativeInteger)))
        self.out.add((card, OWL.onClass, target_class))
        self.out.add((owner, RDFS.subClassOf, card))

    # ------------------------------------------------------------------
    # ValueRank (§17) / Datatype (§18)
    # ------------------------------------------------------------------

    def _ensure_valuerank_vocabulary(self):
        if self._valuerank_vocabulary_emitted:
            return
        names = list(VALUE_RANK_CLASSES.values()) + [VALUE_RANK_MORE_DIMENSIONS]
        for name in names:
            self.out.add((self.opcuans[name], RDF.type, OWL.Class))
        for name, supers in VALUE_RANK_SUBCLASS_OF.items():
            for super_name in supers:
                self.out.add((self.opcuans[name], RDFS.subClassOf, self.opcuans[super_name]))
        if self.disjoint_valuerank:
            disjoint_node = BNode()
            self.out.add((disjoint_node, RDF.type, OWL.AllDisjointClasses))
            members = BNode()
            Collection(self.out, members, [self.opcuans[name] for name in VALUE_RANK_DISJOINT_LEAVES])
            self.out.add((disjoint_node, OWL.members, members))
        self._valuerank_vocabulary_emitted = True

    def _valuerank_class(self, rank):
        self._ensure_valuerank_vocabulary()
        if rank in VALUE_RANK_CLASSES:
            name = VALUE_RANK_CLASSES[rank]
        elif rank is not None and rank >= 2:
            name = VALUE_RANK_MORE_DIMENSIONS
        else:
            name = VALUE_RANK_CLASSES[-2]  # Any: safest fallback for unexpected codes
        return self.opcuans[name]

    def _datatype_property(self):
        prop = self.SB['hasDataType']
        if (prop, RDF.type, OWL.ObjectProperty) not in self.out:
            self.out.add((prop, RDF.type, OWL.ObjectProperty))
            # Unlike the containment property _add_all_values_from
            # deliberately leaves non-functional (see its own comment),
            # DataType is a Mandatory, single-valued Attribute of every OPC
            # UA Variable/VariableType (Part 3's Attributes table) -- not
            # optional, and not per-declaration like a ModellingRule.
            # Declaring it owl:FunctionalProperty here reflects that fact.
            self.out.add((prop, RDF.type, OWL.FunctionalProperty))
        return prop

    def _add_datatype_restriction(self, vt_iri, datatype_iri):
        if datatype_iri is None:
            return
        prop = self._datatype_property()
        allv = BNode()
        self.out.add((allv, RDF.type, OWL.Restriction))
        self.out.add((allv, OWL.onProperty, prop))
        self.out.add((allv, OWL.allValuesFrom, datatype_iri))
        self.out.add((vt_iri, RDFS.subClassOf, allv))
        # someValuesFrom, unlike on the containment property, belongs here:
        # a real Variable always has *some* DataType value (it is Mandatory
        # and functional, see _datatype_property), so asserting existence
        # is simply true, not an overreach the way it would be for an
        # Optional component. Combined with FunctionalProperty, this is what
        # makes an illegal sibling-DataType override (e.g. see
        # tests/owl2vt/test_vt_datatype_contradiction.NodeSet2) a
        # genuine, HermiT-detectable contradiction instead of a
        # vacuously-satisfiable no-op: without forcing existence, two
        # disjoint allValuesFrom fillers on the same VT are trivially
        # satisfied by an instance with zero hasDataType edges.
        somev = BNode()
        self.out.add((somev, RDF.type, OWL.Restriction))
        self.out.add((somev, OWL.onProperty, prop))
        self.out.add((somev, OWL.someValuesFrom, datatype_iri))
        self.out.add((vt_iri, RDFS.subClassOf, somev))

    def _valuerank_property(self):
        prop = self.SB['hasValueRank']
        if (prop, RDF.type, OWL.ObjectProperty) not in self.out:
            self.out.add((prop, RDF.type, OWL.ObjectProperty))
            # ValueRank, like DataType (see _datatype_property), is a
            # Mandatory, single-valued Attribute of every real OPC UA
            # Variable/VariableType -- not a category the thing itself IS
            # a member of. FunctionalProperty here mirrors that fact.
            self.out.add((prop, RDF.type, OWL.FunctionalProperty))
        return prop

    def _add_valuerank_restriction(self, subject, rank):
        """Attach ValueRank as a relationship to a symbolic class via
        sb:hasValueRank, not as a direct rdfs:subClassOf onto the symbolic
        class itself. `subject` is a Virtual Type (an instance
        declaration's own ValueRank) or a real VariableType class (its own
        declared ValueRank, see _add_own_variable_type_restrictions) --
        either way it HAS a ValueRank, it does not become a member of the
        ValueRank_X category the same way it might genuinely be a member of
        its own TypeDefinition's category (§8's rdfs:subClassOf is correct
        there: it really is one). Mirrors _add_datatype_restriction exactly
        (allValuesFrom + someValuesFrom, with hasValueRank Functional): the
        same reasoning applies -- ValueRank is Mandatory and single-valued,
        so someValuesFrom is simply true, and Functional + two disjoint
        someValuesFrom fillers is what makes an incompatible override a
        genuine, HermiT-detectable contradiction rather than a vacuously-
        satisfiable no-op."""
        prop = self._valuerank_property()
        target = self._valuerank_class(rank)
        allv = BNode()
        self.out.add((allv, RDF.type, OWL.Restriction))
        self.out.add((allv, OWL.onProperty, prop))
        self.out.add((allv, OWL.allValuesFrom, target))
        self.out.add((subject, RDFS.subClassOf, allv))
        somev = BNode()
        self.out.add((somev, RDF.type, OWL.Restriction))
        self.out.add((somev, OWL.onProperty, prop))
        self.out.add((somev, OWL.someValuesFrom, target))
        self.out.add((subject, RDFS.subClassOf, somev))

    # ------------------------------------------------------------------
    # Pure-OWL class/property layer passthrough (§19-20)
    # ------------------------------------------------------------------

    def _copy_class_and_property_layer(self):
        for s in self.g.subjects(RDF.type, OWL.Class):
            self.out.add((s, RDF.type, OWL.Class))
            for sup in self.g.objects(s, RDFS.subClassOf):
                self.out.add((s, RDFS.subClassOf, sup))
            for abstract in self.g.objects(s, self.basens['isAbstract']):
                self.out.add((s, self.basens['isAbstract'], abstract))

        # Structural reference-type properties (HasComponent, Aggregates,
        # HasChild, HasOrderedComponent, ...) are already explicitly typed
        # owl:ObjectProperty in the source graph.
        for s in self.g.subjects(RDF.type, OWL.ObjectProperty):
            self.out.add((s, RDF.type, OWL.ObjectProperty))
            for sup in self.g.objects(s, RDFS.subPropertyOf):
                self.out.add((s, RDFS.subPropertyOf, sup))

        # The derived semantic-bridge properties (opcua:has<BrowseName>, ~1047 of
        # them) are NOT: Part 5 only ever asserts
        # `p rdfs:subPropertyOf base:SemanticBridgeReferenceType` for them, never
        # `p a owl:ObjectProperty` -- and base:SemanticBridgeReferenceType itself
        # is never declared as a property either, only ever used as an object.
        # Left alone, every owl:onProperty this module generates in a restriction
        # would reference a wholly undeclared entity. That is exactly what made
        # Protege/the OWL API inject synthetic "ErrorN" placeholder classes (one
        # per occurrence) instead of the real property when loading the previous
        # output -- OWL's punning rules require an entity used as a property to
        # actually be declared as one. Materialize the missing declarations here
        # so every property used in a restriction is properly typed.
        semantic_bridge_root = self.basens['SemanticBridgeReferenceType']
        self.out.add((semantic_bridge_root, RDF.type, OWL.ObjectProperty))
        query = """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?s ?sup WHERE {
            ?s rdfs:subPropertyOf+ ?root .
            ?s rdfs:subPropertyOf ?sup .
        }
        """
        for s, sup in self.g.query(query, initBindings={'root': semantic_bridge_root}):
            self.out.add((s, RDF.type, OWL.ObjectProperty))
            # Each `s` here is one specific has<BrowseName> leaf property (e.g.
            # opcua:hasMotor), minted per (namespace URI, BrowseName) pair by
            # nodesetparser.add_semantic_bridge -- never an intermediate
            # supertype (every one of them is asserted rdfs:subPropertyOf the
            # SemanticBridgeReferenceType root directly, one flat level, see
            # that function). OPC UA's own uniqueness rule (Part 3: no two
            # forward References of a Node may share a BrowseName) means a
            # given owner can only ever have at most one filler for a specific
            # BrowseName's property, so owl:FunctionalProperty here is simply
            # true, not an approximation -- and it's what makes an OPC UA
            # nodeset that (illegally) declares two same-named children under
            # one node a genuine, HermiT-detectable contradiction rather than
            # a silently-accepted no-op. (semantic_bridge_root itself is
            # deliberately NOT made functional two lines up: it is the shared
            # supertype of *all* has<BrowseName> properties, and a real owner
            # legitimately has many differently-named children at once.)
            self.out.add((s, RDF.type, OWL.FunctionalProperty))
            self.out.add((s, RDFS.subPropertyOf, sup))

    def _add_sibling_type_disjointness(self, base_root):
        """For every class under `base_root` with 2+ direct subtypes, assert
        those subtypes pairwise disjoint: an OPC UA instance's TypeDefinition
        (for opcua:BaseObjectType/BaseVariableType) or a value's DataType
        (for opcua:BaseDataType) is always exactly one concrete type, so two
        subtypes that are not in an ancestor/descendant relationship with
        each other are always mutually exclusive (e.g. Int32 and Double are
        both children of Number's descendants; two distinct sibling
        ObjectTypes are equally mutually exclusive TypeDefinitions). This is
        what lets a reasoner catch a subtype overriding a declaration's
        nominal type (or a Variable's Datatype) to an incompatible, unrelated
        type -- the same mechanism ValueRank's disjoint leaves already rely
        on, applied here directly at the class level instead of via a
        Functional-property trick (see _mint_vt's §8/§9 rdfs:subClassOf
        edges: an override's Virtual Type already lands subClassOf both its
        own declared type and the inherited VT, so once the two are asserted
        disjoint the VT itself becomes unsatisfiable, no restriction
        indirection needed).

        Verified against core.owl.ttl before implementing this: zero classes
        anywhere in the ontology have more than one direct rdfs:subClassOf
        (no multi-inheritance), so treating every sibling group as a true
        partition is safe -- this holds for Object/VariableTypes exactly as
        it does for DataTypes.

        OPC UA Interfaces (HasInterface / BaseInterfaceType) are a distinct
        mechanism -- an Interface reference, not a TypeDefinition subtype
        relationship -- and Interface types live in their own tree rooted at
        BaseInterfaceType, never under BaseObjectType, so they never enter
        these sibling groups: an object implementing several Interfaces at
        once is unaffected by this disjointness assertion.

        Scoped like everything else here: a disjointness group is only
        emitted if at least one of its members is newly declared in `g` (the
        rdfs:subClassOf edge to the shared parent lives in `g`, not only in
        `ig`). A companion spec that adds one new subtype under an existing
        core type therefore asserts disjointness for that whole sibling set
        (old members plus the new one), but doesn't re-emit disjointness for
        every *other* parent it didn't touch -- that was already asserted by
        the dependency's own output."""
        descendants = set()
        stack = [base_root]
        while stack:
            current = stack.pop()
            for child in self.combined.subjects(RDFS.subClassOf, current):
                if child not in descendants:
                    descendants.add(child)
                    stack.append(child)

        for parent in descendants | {base_root}:
            children = sorted(self.combined.subjects(RDFS.subClassOf, parent), key=str)
            if len(children) < 2:
                continue
            has_new_member = any((child, RDFS.subClassOf, parent) in self.g for child in children)
            if not has_new_member:
                continue
            disjoint_node = BNode()
            self.out.add((disjoint_node, RDF.type, OWL.AllDisjointClasses))
            members = BNode()
            Collection(self.out, members, children)
            self.out.add((disjoint_node, OWL.members, members))

    def run(self, roots=None, progress=None):
        """Build the OWL ontology of Virtual Types. `progress`, if given, is called as
        progress(index, total, root_iri) right before each root type is
        processed -- useful for CLI feedback, since a full core.owl.ttl run
        generates Virtual Types for hundreds of types with no other visible
        output in between."""
        self._copy_class_and_property_layer()
        self._add_sibling_type_disjointness(self.opcuans['BaseDataType'])
        self._add_sibling_type_disjointness(self.opcuans['BaseObjectType'])
        self._add_sibling_type_disjointness(self.opcuans['BaseVariableType'])
        targets = roots if roots is not None else self.all_target_classes()
        total = len(targets)
        for index, root in enumerate(targets, start=1):
            if progress is not None:
                progress(index, total, root)
            self.get_cdt(root)  # triggers processing; writes root's own restrictions as a side effect
        return self.out
