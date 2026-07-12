#
# Copyright (c) 2024 Intel Corporation
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
"""Transform an OPC UA Semantic Bridge graph (Part 5 output) into a pure OWL
ontology (Part 14 of semantic_bridge_to_owl.md): every Instance Declaration
becomes a generated "Virtual Type" class, and the Instance Declaration nodes
themselves are dropped from the output.
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
# which is how core.ttl actually encodes the (very common) scalar case.
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
    inherited at the same segment."""
    base_type: URIRef
    nodeclass: URIRef
    semantic_property: Optional[URIRef]
    is_optional: Optional[bool]
    is_placeholder: bool
    value_rank: Optional[int] = None
    datatype: Optional[URIRef] = None


class OwlBuilder:
    SB = SEMANTIC_BRIDGE_NS

    def __init__(self, g: Graph, basens: Namespace, opcuans: Namespace, disjoint_valuerank: bool = True,
                 ig: Graph = None):
        """
        g: the semantic bridge graph to generate Virtual Types FOR (e.g. di.ttl).
           Only classes/properties actually declared in `g` are scanned as VT
           roots or copied into the output -- this is what makes companion-spec
           processing incremental rather than re-deriving core.ttl's own Virtual
           Types every time.
        ig: already-processed *imported* dependency graph(s) (e.g. core.ttl),
            needed only to resolve cross-file references -- a companion spec's
            types routinely subclass or aggregate core types directly
            (di:SomeType rdfs:subClassOf opcua:BaseObjectType). Never scanned as
            VT roots and never copied into the output; assumed to already have
            its own separately-generated pure-OWL output that this one's
            ontology header will owl:import.
        """
        self.g = g
        self.ig = ig if ig is not None else Graph()
        self.basens = basens
        self.opcuans = opcuans
        self.rdfutils = RdfUtils(basens, opcuans)
        self.disjoint_valuerank = disjoint_valuerank
        self.out = Graph()
        self.out.bind('opcua', opcuans)
        self.out.bind('base', basens)
        self.out.bind('sb', self.SB)
        self._cdt_cache = {}
        self._definer_node_cache = {}
        self._vt_iri_cache = {}
        self._valuerank_vocabulary_emitted = False
        # Part 5 (nodeset2owl.py) rewrites `?instance a ?type` into
        # `?instance base:instanceOf ?type` for Object instance declarations right
        # before serializing core.ttl (see utils.replace_type_of_node_iris), so that
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
        introduces. An imported dependency's own types (e.g. core.ttl's, when
        processing di.ttl) were already fully virtualized when that dependency
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

    def count_own_instance_declarations(self):
        """Total number of physically-declared Instance Declaration nodes
        (Object/Variable children directly on a type's own definer node,
        Methods excluded) that `g` itself introduces -- i.e. the raw nodes
        Virtual Type generation is replacing, one level per type. This is
        deliberately the *un*-expanded count: it does not follow inheritance
        or recurse into nested declarations' own children (that recursive
        unrolling, done separately per root by emit_vt_tree, is exactly what
        makes the Virtual Type count larger than this). Filtering mirrors
        get_cdt's own loop exactly, just counting instead of building
        DeclEntry objects."""
        count = 0
        for class_iri in self.all_target_classes():
            definer_node = self._definer_node(class_iri)
            if definer_node is None:
                continue
            children = self.rdfutils.get_all_subreferences(
                self.combined, definer_node, self.opcuans['HasChild'])
            for _refprop, child in children:
                nodeclass, base_type = self.rdfutils.get_type(self.combined, child)
                if nodeclass == self.opcuans['MethodNodeClass'] or base_type is None:
                    continue
                count += 1
        return count

    # ------------------------------------------------------------------
    # Effective Declaration Tree (§4)
    # ------------------------------------------------------------------

    def get_cdt(self, class_iri):
        if class_iri in self._cdt_cache:
            return self._cdt_cache[class_iri]
        super_iri = self._direct_supertype(class_iri)
        result = dict(self.get_cdt(super_iri)) if super_iri is not None else {}
        definer_node = self._definer_node(class_iri)
        if definer_node is not None:
            children = self.rdfutils.get_all_subreferences(self.combined, definer_node, self.opcuans['HasChild'])
            for _refprop, child in children:
                nodeclass, base_type = self.rdfutils.get_type(self.combined, child)
                if nodeclass == self.opcuans['MethodNodeClass']:
                    continue  # Methods are out of scope for this phase.
                if base_type is None:
                    continue
                key = self._qualified_browsename(child)
                semantic_property = self.rdfutils.get_semantic_bridge(self.combined, definer_node, child)
                is_optional, is_placeholder = self.rdfutils.get_modelling_rule(self.combined, child, None, class_iri)
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
                result[key] = entry
        self._cdt_cache[class_iri] = result
        return result

    def resolve_path(self, class_iri, path):
        """Dimension-1 helper (§9): does `path` exist in class_iri's Effective
        Declaration Tree? Used to decide whether a Virtual Type should link back
        to the corresponding Virtual Type of the root type's direct supertype."""
        if class_iri is None:
            return None
        entry = self.get_cdt(class_iri).get(path[0])
        if entry is None:
            return None
        return entry if len(path) == 1 else self.resolve_path(entry.base_type, path[1:])

    # ------------------------------------------------------------------
    # Virtual Type identity (§6-7)
    # ------------------------------------------------------------------

    def _mint_vt_iri(self, root_iri, path):
        """Mint (or fetch) the Virtual Type IRI for (root_iri, path), and fully
        self-type it -- base typing rule (§8), ValueRank/Datatype (§17-18), and
        the supertype-VT link (§9) -- right here, at first creation.

        This must be self-contained rather than relying on emit_vt_tree's
        top-down walk to "happen to visit" this exact (root, path) pair: rule 9
        mints a VT for the *supertype's own* root as a forward reference, and
        for self-referential types (see the `_visited` guard in emit_vt_tree)
        that supertype's own top-down walk may never actually reach the same
        depth -- its cycle cutoff kicks in one level earlier, since from its
        own root the self-reference is "already visited" immediately, whereas
        a subtype reaches the same class one level later. Without this, such a
        forward-referenced VT would be minted (typed owl:Class, annotated) but
        never get a subClassOf axiom of its own -- a dangling Virtual Type with
        no relation to any original class.

        Companion-spec case: `root_iri` may belong to an *imported* dependency
        rather than to the file this OwlBuilder is generating output for (e.g.
        di.ttl's rule-9 link to a supertype VT rooted at a core.ttl type). Such
        a VT's IRI must still be namespaced under its *own* root (not always
        `opcuans`, which was a bug -- every companion spec's Virtual Types were
        landing under opcua: regardless of the spec's own namespace), but its
        content must NOT be (re-)populated here: that root's own dependency was
        already processed on its own and fully defines this exact VT (the hash
        is deterministic, so the IRI matches) in its own output file, which
        this file's ontology header owl:imports. Populating it again here would
        just duplicate that entire file's worth of axioms."""
        key = (str(root_iri), tuple(path))
        if key in self._vt_iri_cache:
            return self._vt_iri_cache[key]
        qualified_path = '/'.join(path)
        digest = hashlib.sha256(f'{root_iri}|{qualified_path}'.encode('utf-8')).hexdigest()[:24]
        vt_namespace = Namespace(split_uri(root_iri)[0])
        vt_iri = vt_namespace[f'VT_{digest}']
        self._vt_iri_cache[key] = vt_iri

        if (root_iri, RDF.type, OWL.Class) not in self.g:
            return vt_iri  # foreign root: bare reference only, see docstring

        self.out.add((vt_iri, RDF.type, OWL.Class))
        self.out.add((vt_iri, self.SB['originalBrowsePath'], Literal(qualified_path)))

        entry = self.resolve_path(root_iri, path)
        if entry is not None:
            self.out.add((vt_iri, RDFS.subClassOf, entry.base_type))  # §8 base typing rule

            if entry.nodeclass == self.opcuans['VariableNodeClass']:
                self.out.add((vt_iri, RDFS.subClassOf, self._valuerank_class(entry.value_rank)))
                self._add_datatype_restriction(vt_iri, entry.datatype)

            super_root = self._direct_supertype(root_iri)
            if super_root is not None and self.resolve_path(super_root, path) is not None:
                super_vt = self._mint_vt_iri(super_root, path)  # §9 inheritance (covers §10 override too)
                self.out.add((vt_iri, RDFS.subClassOf, super_vt))
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
        return prop

    def _add_datatype_restriction(self, vt_iri, datatype_iri):
        if datatype_iri is None:
            return
        prop = self._datatype_property()
        r = BNode()
        self.out.add((r, RDF.type, OWL.Restriction))
        self.out.add((r, OWL.onProperty, prop))
        self.out.add((r, OWL.allValuesFrom, datatype_iri))
        self.out.add((vt_iri, RDFS.subClassOf, r))

    # ------------------------------------------------------------------
    # Virtual Type + restriction emission (§8-16)
    # ------------------------------------------------------------------

    def emit_vt_tree(self, root_iri, current_class, path_prefix, _visited=frozenset()):
        # `_visited` guards against genuinely self-referential OPC UA types.
        # The standard core nodeset itself contains these: e.g. DictionaryEntryType
        # declares an OptionalPlaceholder child "<DictionaryEntryName>" typed as
        # DictionaryEntryType itself (a dictionary/tree of arbitrarily many named
        # entries), and DictionaryFolderType does the same. Dimension-2 recursion
        # (recursing into entry.base_type) has no natural base case for such types,
        # so without this guard emit_vt_tree recurses forever. The fix: once we'd
        # revisit a class already on the current root-to-here recursion path, still
        # emit that level's Virtual Type and restriction (so the recursive
        # BrowsePath is representable at least one level deep), but stop descending
        # further into its children.
        visited = _visited | {current_class}
        for key, entry in self.get_cdt(current_class).items():
            full_path = path_prefix + [key]
            vt = self._mint_vt_iri(root_iri, full_path)  # self-typing: §8, §9, §17-18

            owner = self._mint_vt_iri(root_iri, path_prefix) if path_prefix else root_iri
            if entry.semantic_property is not None:
                self._add_all_values_from(owner, entry.semantic_property, vt)
                if entry.is_optional is False:  # Mandatory or MandatoryPlaceholder
                    self._add_cardinality(owner, entry.semantic_property, vt)

            if entry.base_type not in visited:
                self.emit_vt_tree(root_iri, entry.base_type, full_path, visited)  # dimension-2 recursion

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
            self.out.add((s, RDFS.subPropertyOf, sup))

    def _add_datatype_disjointness(self):
        """For every DataType (rooted at opcua:BaseDataType) with 2+ direct
        subtypes, assert those subtypes pairwise disjoint: a value cannot
        simultaneously be of two different sibling DataTypes (e.g. Int32 and
        Double are both children of Number's descendants; two distinct custom
        Structures or Enumerations are equally mutually exclusive). This is
        what lets a reasoner catch a subtype overriding a Variable's Datatype
        to an incompatible sibling type, the same way ValueRank's disjoint
        leaves catch a ValueRank override.

        Verified against core.ttl before implementing this: zero classes
        anywhere in the ontology have more than one direct rdfs:subClassOf
        (no multi-inheritance), so treating every sibling group as a true
        partition is safe.

        Scoped like everything else here: a disjointness group is only
        emitted if at least one of its members is newly declared in `g` (the
        rdfs:subClassOf edge to the shared parent lives in `g`, not only in
        `ig`). A companion spec that adds one new subtype under an existing
        core DataType therefore asserts disjointness for that whole sibling
        set (old members plus the new one), but doesn't re-emit disjointness
        for every *other* DataType parent it didn't touch -- that was already
        asserted by the dependency's own output."""
        base_datatype = self.opcuans['BaseDataType']
        descendants = set()
        stack = [base_datatype]
        while stack:
            current = stack.pop()
            for child in self.combined.subjects(RDFS.subClassOf, current):
                if child not in descendants:
                    descendants.add(child)
                    stack.append(child)

        for parent in descendants | {base_datatype}:
            children = list(self.combined.subjects(RDFS.subClassOf, parent))
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
        """Build the pure-OWL ontology. `progress`, if given, is called as
        progress(index, total, root_iri) right before each root type is
        processed -- useful for CLI feedback, since a full core.ttl run
        generates Virtual Types for hundreds of types with no other visible
        output in between."""
        self._copy_class_and_property_layer()
        self._add_datatype_disjointness()
        targets = roots if roots is not None else self.all_target_classes()
        total = len(targets)
        for index, root in enumerate(targets, start=1):
            if progress is not None:
                progress(index, total, root)
            self.emit_vt_tree(root, root, [])
        return self.out
