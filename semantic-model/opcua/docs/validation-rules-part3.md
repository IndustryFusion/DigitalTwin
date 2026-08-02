# Validation Rule Catalog — OPC UA Part 3 (Address Space Model)

This catalog is a first pass: identify and name the checkable rules in the spec text,
before any of them are implemented as SHACL. Each rule has a stable ID, the exact
subclause it was derived from, and a plain-language statement of what would need to
hold in the AddressSpace graph for the rule to pass. Implementation (SHACL shapes,
SPARQL constraints, or — where the rule is a real graph algorithm rather than a shape
— procedural checks) is a separate, later step.

Source: [OPC 10000-3 (Address Space Model)](https://reference.opcfoundation.org/specs/OPC-10000-3/full),
sections 4 (AddressSpace concepts), 5 (Standard NodeClasses), 6 (Type Model for
ObjectTypes and VariableTypes), 7 (Standard ReferenceTypes).

**Part 1 (Overview and Concepts) was checked first and skipped**: it is deliberately
non-normative and contains no "shall"/cardinality language — every structural detail
it mentions is explicitly deferred to Parts 2–5. See conversation history for the
section-by-section confirmation.

## Status legend

| Status | Meaning |
|---|---|
| **Implemented** | A SHACL shape already checks this, in `validation/ontology/*.shacl.ttl`. File named in Notes. |
| **Implemented (reasoner)** | Already enforced, but via the HermiT DL reasoner over `*.vt.owl.ttl` (`owl2vt.py` + `check_consistency.py`'s Virtual-Types machinery), not SHACL. |
| **Gap** | Checkable today (the data the rule needs is already in the OWL graph) but no shape exists yet. |
| **Blocked** | The rule can't be checked yet because `nodeset2owl.py` doesn't currently extract the Attribute(s) it depends on into the graph at all. |
| **New** | Not yet assessed against existing shapes; likely a gap but not cross-checked line-by-line. |
| **Advanced** | Structurally real but not a simple shape — needs a recursive/structural-correspondence check or is otherwise complex to implement. Lower priority. |
| **N/A** | Normative in the spec, but meaningless for this pipeline's model (e.g. multi-Server statements — this pipeline only ever reasons about one AddressSpace/Server's worth of Nodes at a time). |

**Confidence note:** rules marked "verified" below were checked against the primary
subclause text directly. The full source/target NodeClass table for §7 came back from
a single bulk fetch covering ~25 ReferenceTypes; I spot-checked the load-bearing ones
(HasComponent, HasProperty, HasSubtype, Organizes) against what's already implemented
and against independent corroboration from other subclauses, but the more exotic rows
(HasEncoding, HasFieldDescription, UsesDataTypeRefinement, ...) should be re-verified
against primary text before being turned into enforced constraints. I caught and fixed
one real transcription error this way already: an initial fetch of the Part 3 §5.9
attribute-summary table placed `AccessLevelEx` under VariableType instead of Variable;
5.6.2/5.6.5 primary text confirmed the correct placement (see AS-016/AS-017).

---

## §4.2, §4.3 — checked, no rules found

*Pass 3.* §4.2 "URIs" is almost entirely "should"/recommendation-level guidance about
constructing NamespaceUri/ApplicationUri/ProductInstanceUri strings — open-ended by its
own admission ("this specification is very open ended"). The one hard "shall": *"Programs
shall always treat URIs as opaque strings that can only be tested for equality with a
case sensitive string comparison"* — not a graph-shape rule itself, but a constraint on
how any *other* rule in this catalog that compares NamespaceUri values must be
implemented (exact case-sensitive string match, never normalized/case-insensitive).
§4.3 "Object Model" is purely introductory prose defining terms, with no "shall"/"shall
not"/cardinality language at all — confirmed by direct fetch, same pattern as Part 1.

## §4.4 Node Model

| ID | Section | Rule | Status | Notes |
|---|---|---|---|---|
| AS-001 | 4.4.2 | Every Node's NodeClass must be one of the 8 standard NodeClasses (Object, ObjectType, Variable, VariableType, Method, ReferenceType, DataType, View). No other NodeClass may be used, and Clients/Servers may not define or extend NodeClasses. | New | Defense-in-depth: `nodeset2owl.py` only ever emits one of the 8 by construction, so this only matters for validating a foreign/hand-authored graph. |
| AS-002 | 4.4.4 | A SourceNode must not have more than one Reference to the same TargetNode where the ReferenceTypes are "the same for identification purposes" — i.e. identical, or one a subtype of the concrete ReferenceType the other uses. (Spec: "each Node can reference another Node with the same ReferenceType only once... subtypes of concrete ReferenceTypes are considered to be equal to the base concrete ReferenceTypes when identifying References.") | Gap | Non-trivial: requires grouping outgoing References from a SourceNode by target, then checking no two land on the same (SourceNode, TargetNode) pair via ReferenceTypes in the same subtype lineage. |
| AS-003 | 4.4.3 | A Node must not carry attribute-predicates outside the fixed Attribute set defined for its NodeClass (no invented/foreign attributes). | New | Detailed per-NodeClass in §5 (AS-013–AS-022); best implemented as one closed-ish shape per NodeClass rather than a standalone rule. |
| AS-004 | 4.4.3 | Every mandatory Attribute for a Node's NodeClass must be present (cardinality ≥ 1). | New | Detailed per-NodeClass in §5 (AS-013–AS-022). |

## §4.5 Variables

| ID | Section | Rule | Status | Notes |
|---|---|---|---|---|
| AS-005 | 4.5.2, **5.6.3** | A Property (a Node reached via `hasProperty`) must never itself be the SourceNode of **any hierarchical Reference** — not just `hasProperty`. It may still be the SourceNode of NonHierarchical References. | **Partially Implemented** | *Pass 3 upgrade:* 5.6.3 gives the broader, precise rule — "Properties shall not be the SourceNode of any hierarchical References" / "may be the SourceNode of any NonHierarchical References" — wider than pass 1's `hasProperty`-only wording. `validation/ontology/hasProperty.shacl.ttl` → `NoHasPropertyOnVariableNodeShape` only checks the `hasProperty` case, not `hasComponent`/`organizes`/`hasSubtype`/etc. — narrower than the now-confirmed full rule. Independently corroborated by §7 (AS-032's source text: "a Property shall never be the SourceNode of a HasProperty Reference"). |
| AS-006 | 4.5.2 | For a given parent Node, all of its direct Properties (`hasProperty` targets) must have distinct BrowseNames (uniqueness scoped to Property-siblings of the same source). | **Gap** | Not present in `hasProperty.shacl.ttl` today. Generalized by AS-009 (below) for Type/InstanceDeclaration nodes specifically, but this rule applies to *any* node with Properties, not just types. |
| AS-007 | 4.5.3, **5.6.3, 5.6.4** | A Variable reached via `hasComponent` must be a DataVariable, and a DataVariable is only "complex" (allowed to itself have further DataVariable children via `hasComponent`) if it has an incoming `hasComponent` Reference making it one. | **Implemented** | `validation/ontology/hasComponent.shacl.ttl` → `HasComponentVariableTypeConstraint`, `VariableComponentDependencyShape`. *Pass 3:* 5.6.4 gives the fully precise, symmetric version — see AS-057. |
| AS-056 | **5.6.3** | Every Property (a Variable reached via `hasProperty`) must have its `HasTypeDefinition` target be `PropertyType`. | Needs Verification | *Pass 3 finding.* Verified against 5.6.3: "all Properties shall point to the PropertyType" via `HasTypeDefinition`. The quoted text names `PropertyType` specifically rather than saying "or a subtype of it" — unlike every other HasTypeDefinition-narrowing rule in this catalog (AS-010/AS-026/AS-044). Re-check the primary text directly for a subtype allowance before implementing as an exact-match constraint; treating `PropertyType`-only as literal would be an outlier in an otherwise uniformly "subtype-permitted" spec. |
| AS-057 | **5.6.3, 5.6.4** | A Variable's category (Property vs. DataVariable) is mutually exclusive and fully determined by its incoming references: a **Property** must be the TargetNode of ≥1 `hasProperty` Reference and must **not** be the TargetNode of any `hasComponent` Reference; a **DataVariable** must be the TargetNode of ≥1 `hasComponent` Reference (sourced from an Object, ObjectType, DataVariable, or VariableType) and must **not** be the TargetNode of any `hasProperty` Reference. | **Gap** | *Pass 3 finding, fully precise/symmetric version of AS-007.* Verified against both 5.6.3 ("Properties... shall not be the TargetNode of any HasComponent Reference") and 5.6.4 ("DataVariables shall not be the TargetNode of any HasProperty References... a HasComponent Reference pointing to a Variable Node identifies it as a DataVariable"). Not implemented: `hasComponent.shacl.ttl`'s and `hasProperty.shacl.ttl`'s existing shapes check *type* consistency (target must be `BaseDataVariableType`, etc.) but never check that a node isn't reached by **both** `hasProperty` and `hasComponent` simultaneously — the mutual-exclusivity half is a genuine, currently-unimplemented gap. |

## §4.6 TypeDefinitionNodes

| ID | Section | Rule | Status | Notes |
|---|---|---|---|---|
| AS-008 | 4.6.1, **7.13** | Every Node of NodeClass Object or Variable must have exactly one outgoing `HasTypeDefinition` Reference. | Gap | *Pass 3 upgrade:* directly confirmed with hard "shall" language — "Each Variable and each Object shall be the SourceNode of exactly one HasTypeDefinition Reference" (7.13), previously only inferred loosely from 4.6.1. Cardinality half of the rule; see AS-035 for the target-NodeClass-consistency half. |
| AS-009 | 4.6.4, **6.2.6** | A TypeDefinitionNode, or **any** InstanceDeclaration anywhere within its InstanceDeclarationHierarchy (not just the root), must never reach two different Nodes with the same BrowseName via forward hierarchical References. | Gap | *Pass 2 update:* 6.2.6 gives the precise, recursive form of this rule ("applies to the targets of forward hierarchical References from any InstanceDeclaration") — sharper than the 4.6.4 wording I had in pass 1, which only mentioned the TypeDefinitionNode/InstanceDeclaration source loosely. **Caveat (from 6.4.4.4.4/6.4.4.4.5, pass 2):** does not apply to children whose ModellingRule is `OptionalPlaceholder`/`MandatoryPlaceholder` — those are explicitly meant to allow arbitrary/multiple instance BrowseNames, so uniqueness only needs to hold among the *type-defined* (Mandatory/Optional, fixed-BrowseName) children. |
| AS-010 | 4.6.4, 6.4.3, **6.3.3.3** | An instance's `HasTypeDefinition` target must be the same TypeDefinitionNode as the InstanceDeclaration it derives from, or a subtype of it — narrowing only, never a mismatch or widening. | **Implemented (reasoner)** | *Pass 2 update:* 6.3.3.3 confirms this with explicit "shall" language ("shall be the same or a subtype of the TypeDefinitionNode specified in the supertype") and clarifies it's actually a special case of the more general AS-044 (any single-cardinality NonHierarchical Reference on an overridden Node, not just HasTypeDefinition specifically). Still conceptually covered by the Virtual-Types/HermiT machinery (`owl2vt.py`/`check_consistency.py`); a SHACL-only equivalent would need `rdfs:subClassOf*` checks in the style of `hasComponent.shacl.ttl`. |
| AS-011 | 4.6.4, **6.2.7** | Instances derived from an InstanceDeclaration must keep the same BrowseName **and NodeClass** as that InstanceDeclaration — both "shall never change" (6.2.7). | Advanced | *Pass 2 update:* 6.2.7 adds the NodeClass-immutability half, which pass 1 missed (only had BrowseName). Still needs a structural-correspondence walk matching an instance subtree's shape against its type's InstanceDeclarationHierarchy — not a simple shape. Same Placeholder-exemption caveat as AS-009 applies to BrowseName (NodeClass immutability has no such exemption — it always holds). |
| AS-012 | 6.4.3 | Where the type definition directly connects two InstanceDeclaration Nodes with a Reference, an instance's corresponding two Nodes (reached via the same Reference position) must be the *same* Node, not independently duplicated — this only applies to directly-connected pairs, not indirect ones. | Advanced | Niche; spec gives a compliant/non-compliant example (A1/A2 vs A3) rather than a general formula — would need care to generalize correctly. |
| AS-038 | 6.2.1 | Every InstanceDeclaration (an Object/Variable/Method Node with an outgoing `HasModellingRule` Reference) must be reachable via a forward hierarchical Reference chain from **exactly one** TypeDefinitionNode — no InstanceDeclaration may belong to two different TypeDefinitionNodes. | Gap | *Pass 2 finding.* A genuine global graph constraint: "There shall be no two TypeDefinitionNodes referencing the same InstanceDeclaration" / "an InstanceDeclaration belongs to exactly one TypeDefinitionNode" (6.2.1). |
| AS-039 | 6.2.1 | An **instance's** `HasTypeDefinition` target must never be abstract (`IsAbstract=true`) — even though the InstanceDeclaration it derives from may legitimately point to an abstract type. | Gap | *Pass 2 finding.* "The type of an InstanceDeclaration may be abstract, however the instance must be of a concrete type" (6.2.1). Connects AS-008/AS-010's HasTypeDefinition rules to the `IsAbstract` Attribute from AS-015/AS-017/AS-018/AS-021. |
| — | 4.5.2, 4.6.4 | "A Node and its Properties" / "A TypeDefinitionNode and its InstanceDeclarations" must reside in the same Server. | N/A | This pipeline models one AddressSpace's worth of Nodes at a time; multi-Server placement isn't represented. |
| — | 4.4.4 | OPC UA does *not* require that a Reference's TargetNode exist — dangling References are explicitly permitted. | N/A (explicitly permissive) | Noted so a future "no dangling references" rule isn't added by mistake; the spec says the opposite. |
| — | 6.3.3.3 | "A subtype **should** not override a Node unless it needs to change it." | N/A (advisory) | "Should", not "shall" — a best-practice recommendation, not a validation rule. |

## §4.7 Event Model

*Pass 3 addition.* §4.7.1 "General" is mostly Service/runtime-behavior prose (how
Clients subscribe to Events), not AddressSpace-graph shape — skipped for the same reason
Part 1's service-set sections were. Two genuine structural findings from 4.7.2/4.7.3, one
of them independently confirmed by §9:

| ID | Section | Rule | Status | Notes |
|---|---|---|---|---|
| AS-052 | 4.7.2 | Every EventType Node must be of NodeClass ObjectType — there is no separate "EventType" NodeClass; EventTypes are ObjectTypes by convention. | Gap | Verified against 4.7.2: "EventTypes are represented as ObjectTypes in the AddressSpace and do not have a special NodeClass associated to them." |
| AS-053 | 4.7.2, **9** | Every EventType, other than `BaseEventType` itself, must derive (directly or transitively via `HasSubtype`) from `BaseEventType`. | Gap | *Pass 3: upgraded from Needs-Verification to confirmed* — independently corroborated in §9 ("This establishes that BaseEventType is the obligatory root"), in addition to 4.7.2's "all other EventTypes derive from" it. Structurally the EventType-hierarchy analog of AS-024 (every ReferenceType except the root has exactly one supertype). |
| — | 9 | "Every time a ModelChangeEvent is issued for a Node, its NodeVersion shall be changed, and every time the NodeVersion is changed, a ModelChangeEvent shall be generated." | N/A | A temporal/runtime co-occurrence rule (event emission ⟺ Attribute change over time), not a static single-snapshot graph property — this pipeline validates one AddressSpace snapshot, not a change history (same reasoning as the §6.5 N/A entry). |

*Pass 5* skimmed several concrete §9 EventType entries (BaseEventType, SystemEventType,
AuditEventType) looking for a broadly-applicable "every EventType must have these
Properties" rule beyond the BaseEventType-root requirement above — found none; §9 itself
states BaseEventType's own field list is defined in Part 5, not Part 3, and every other
EventType is handled individually rather than under a general schema rule.

## §4.8 Methods — checked, no rules found

*Pass 4.* Purely conceptual (what a Method is, how it's invoked via the Call Service,
how Clients discover it by browsing). No "shall"/"shall not" language at all — confirmed
by direct fetch. All of this section's actual normative content lives in 5.7 (Method
NodeClass Attributes, AS-019/AS-020) and 6.2.4/6.3.3.3 (Method Argument override rules,
AS-040), which were already covered in earlier passes.

## §4.9 Roles — checked, no Part 3-normative rules found

*Pass 3.* §4.9 is almost entirely about runtime Session→Role mapping and permission
*evaluation* logic (Client authentication, endpoint/application/user-identity mapping
rules, `Bad_UserAccessDenied` semantics) — Service/authorization behavior, not
AddressSpace graph shape. The one structural-sounding detail ("Roles appear under the
Roles Object in the Server Address Space") comes with no NodeClass/type requirement in
Part 3 itself — it's explicitly deferred to OPC 10000-5 and OPC 10000-18. Nothing here
meets this catalog's bar for a checkable rule; recorded so this section isn't silently
skipped without explanation, same treatment as Part 1.

## §4.10 Interfaces and AddIns for Objects

*Pass 2 addition — not covered in the first pass at all. This directly firms up
what AS-037 had only cited from an unverified bulk §7 table.*

| ID | Section | Rule | Status | Notes |
|---|---|---|---|---|
| AS-048 | 4.10.2 | An Object must not have a `HasInterface` Reference to Interface I unless the Object's own TypeDefinitionNode (its ObjectType, directly or via its supertype chain) also has (or inherits) a `HasInterface` Reference to I. | Gap | Verified against 4.10.2 primary text: "The Interface shall not be applied on the Object when the Interface cannot be applied on the TypeDefinitionNode of the Object." |
| AS-049 | 4.10.2 | When an ObjectType has a `HasInterface` Reference to Interface I, every **Mandatory** InstanceDeclaration in I's fully-inherited InstanceDeclarationHierarchy must have a corresponding similar Node (same BrowsePath, ModellingRule=Mandatory) in the ObjectType's own fully-inherited InstanceDeclarationHierarchy. | Gap | Verified against 4.10.2 primary text. Structurally the Interface-implementation analog of the subtyping-inheritance rules (AS-042–046) — an Interface's mandatory members must be "pulled in," the same way a supertype's mandatory InstanceDeclarations are. The Optional-member equivalent uses "should" (advisory), not "shall" — not a hard rule. |
| AS-050 | 4.10.2 | `HasInterface`: TargetNode must be an (abstract) ObjectType that is a subtype of `BaseInterfaceType`. SourceNode may be an ObjectType or an Object. Multiple `HasInterface` References from the same source are permitted. | Gap | Verified against 4.10.2 primary text (source/multiplicity confirmed via paraphrase rather than a single verbatim quote — moderate-high confidence). |
| AS-051 | 4.10.3 | `HasAddIn`: TargetNode must be an instance Node (an Object of any ObjectType — no special supertype requirement, unlike `HasInterface`'s `BaseInterfaceType` constraint). SourceNode may be an ObjectType or an Object. Multiple `HasAddIn` References from the same source are permitted. | Gap | Verified against 4.10.3 primary text (moderate-high confidence, same caveat as AS-050). |

## §5 Standard NodeClasses — per-NodeClass Attribute cardinality

Each row below corresponds to one `sh:NodeShape` (one per NodeClass) with several
`sh:property` children — the natural SHACL shape for "this NodeClass has these
mandatory and these optional Attributes."

*Pass 4 checked §5.5.4 and 5.6.1, pass 5 checked §5.6.6 — all three confirmed
non-normative* (the same "client-side creation" procedural pattern as Part 1's service
sets — 5.5.4's one static claim, "Objects... have a HasTypeDefinition Reference pointing
to its ObjectType," just restates AS-008; 5.6.6's parallel claim for Variables restates
the same plus AS-047's minimum-components rule; 5.6.1 is a pure organizational pointer to
5.6.2–5.6.5). No remaining unconfirmed subsections in §5.5/§5.6.

| ID | Section | Rule | Status | Notes |
|---|---|---|---|---|
| AS-013 | 5.2 | Base NodeClass (applies to every Node regardless of NodeClass): `NodeId`, `NodeClass`, `BrowseName`, `DisplayName` mandatory (=1 each); `Description`, `WriteMask`, `UserWriteMask`, `RolePermissions`, `UserRolePermissions`, `AccessRestrictions` optional (≤1 each). | Gap | Foundational; uniform across all 8 NodeClasses per the spec's own summary table, not independently re-verified per NodeClass since the pattern is structurally guaranteed to be uniform. |
| AS-014 | 5.5.1 | Object NodeClass: `EventNotifier` mandatory (=1). No Object-specific optional Attributes. | Gap | Verified against 5.5.1 primary text directly. |
| AS-015 | 5.5.2 | ObjectType NodeClass: `IsAbstract` mandatory (=1). No `EventNotifier`. | Gap | Verified against 5.5.2 primary text directly. |
| AS-016 | 5.6.2 | Variable NodeClass: `Value`, `DataType`, `ValueRank`, `AccessLevel`, `UserAccessLevel`, `Historizing` mandatory (=1 each); `ArrayDimensions`, `MinimumSamplingInterval`, `AccessLevelEx` optional (≤1 each). | Partially Gap | Verified against 5.6.2 primary text directly (this is the correction to the bad table transcription — `AccessLevelEx` belongs here, not on VariableType). `ValueRank`/`ArrayDimensions` cardinality is covered by `rankValue.shacl.ttl`; the rest (`Value`, `DataType`, `AccessLevel`, `UserAccessLevel`, `Historizing`, `AccessLevelEx`, `MinimumSamplingInterval`) are gaps. |
| AS-017 | 5.6.5 | VariableType NodeClass: `DataType`, `ValueRank`, `IsAbstract` mandatory (=1 each); `Value`, `ArrayDimensions` optional (≤1 each). No `AccessLevelEx`. | Partially Gap | Verified against 5.6.5 primary text directly. `ValueRank` covered by `rankValue.shacl.ttl`; `DataType`, `IsAbstract`, `Value` are gaps. |
| AS-018 | 5.3.2 | ReferenceType NodeClass: `IsAbstract`, `Symmetric` mandatory (=1 each). `InverseName` is *conditionally* mandatory: present (=1) iff `Symmetric=false`; must be absent iff `Symmetric=true`. | **Blocked** | `nodeset2owl.py` does not currently extract `InverseName` into the graph at all (confirmed: no reference to it in `lib/nodesetparser.py`). Needs an upstream extraction change before this is checkable. |
| AS-019 | 5.7.1 | Method NodeClass: `Executable`, `UserExecutable` mandatory (=1 each). No other Method-specific Attributes (`InputArguments`/`OutputArguments` are optional *Properties* via `hasProperty`, not Attributes — see AS-020). | Gap | Verified against 5.7.1 primary text directly. |
| AS-020 | 5.7.1 | If a Method has an `InputArguments` or `OutputArguments` Property, its DataType must be `Argument` and its ValueRank must indicate a one-dimensional array. | Needs Verification | Reasonable inference from 5.7.1's text, but the exact ValueRank value wasn't independently confirmed against the `Argument` DataType's own definition (§8.6) — re-check before implementing. |
| AS-021 | 5.8.3, **8.32** | DataType NodeClass: `IsAbstract` mandatory (=1). `DataTypeDefinition` is *conditionally* mandatory (=1): required if the DataType is (a subtype of) Structure, Union, Enumeration, OptionSet, or a UInteger-subtype representing an OptionSet; optional (≤1) otherwise. | **Blocked** | `nodeset2owl.py` does not currently extract `DataTypeDefinition` into the graph at all (confirmed via grep). Needs upstream extraction work first. *Pass 5 (8.32):* a satellite detail once this is unblocked — "a non-abstract Structure shall have one or more fields defined directly or from a super type," i.e. `DataTypeDefinition`'s Fields list must be non-empty (directly or via inheritance) for any concrete Structure subtype. Same blocker, not independently actionable. |
| AS-022 | 5.4 | View NodeClass: `ContainsNoLoops`, `EventNotifier` mandatory (=1 each). If `ContainsNoLoops=true`, the subgraph of forward hierarchical References reachable from Nodes organized by this View must contain **no directed cycle** back to any Node already in that subgraph. | New | This is the one rule in this catalog that's a genuine **graph algorithm** (cycle detection) rather than a cardinality/type shape — matches your "graph algorithms, mainly SHACL" framing directly. Implementable as a SPARQL property-path self-reachability query (`?x (hierarchicalRefUnion)+ ?x` within the View's scope) or, more robustly, a procedural DFS in Python. |
| AS-023 | 5.3.3.1 | A ReferenceType Node, as SourceNode, may only use `HasSubtype` or `HasProperty` References — it must not be the SourceNode of any other Reference type. | Gap | Verified against 5.3.3 primary text directly. |
| AS-024 | 5.3.3.3 | Every ReferenceType Node except the root `References` type must have exactly one supertype; the ReferenceType hierarchy is single-inheritance only. | Gap | Verified against 5.3.3 primary text directly. In this repo's model, ReferenceType subtyping is materialized as `rdfs:subClassOf` on the class URIs directly (see `nodesetparser.py`'s `get_typedefinition_from_references`), so this becomes: every `opcua:ObjectProperty` individual except `opcua:References` has exactly one direct `rdfs:subClassOf` edge. |
| AS-025 | 5.8.6.1 | A SubtypeRestriction Object must be referenced from exactly one DataType Node via `HasDataTypeRefinement`; it must only be used on Variables that are themselves instances (never on InstanceDeclarations or VariableTypes); its own DataType must exactly match the DataType it restricts. | Advanced | Niche. `HasDataTypeRefinement`/`SubtypeRestrictionType` are not modelled by `nodeset2owl.py` at all today — lowest priority in this catalog. *Pass 3 (5.8.5.1/5.8.5.2):* the more general `DataTypeRefinement` Object (of which SubtypeRestriction is one kind) has the same "exactly one owning DataType" cardinality, plus: it must not reference any Node via `HasFieldDescription` that isn't a real field of the DataType it refines, and at most one Variable per field. Same "not modelled, lowest priority" status applies. |
| AS-058 | 5.8.1, **5.8.4** | A `DataTypeEncoding` Object is owned by **exactly one** DataType — two different DataType Nodes must never point to the same `DataTypeEncoding` Object (via `HasEncoding`), and every `HasEncoding` Reference must be **bidirectional** (both the forward and inverse Reference present). | **Gap — status corrected in pass 5, was wrongly Blocked** | Verified against 5.8.1: "Each DataTypeEncoding is used by exactly one DataType, that is, it is not permitted for two DataTypes to point to the same DataTypeEncoding." 5.8.4 adds the existence + bidirectionality requirement — "If a DataType Node is exposed in the AddressSpace, it shall provide its DataTypeEncodings using HasEncoding References. These References shall be bi-directional." *Pass 5 correction:* earlier passes marked this Blocked by analogy with AS-018/AS-021, but that was imprecise — `InverseName`/`DataTypeDefinition` are genuinely unparsed XML **Attributes**, while `HasEncoding` is a plain **Reference**, and `nodesetparser.py`'s `references_ignore()` only special-cases `HasSubtype`/`HasTypeDefinition` — every other Reference, including `HasEncoding`, is captured generically. Empirically confirmed: a fresh `core.owl.ttl` build contains real `opcua:hasEncoding` triples connecting DataTypes to `DataTypeEncoding` Objects. Genuinely checkable today. |
| AS-059 | **8.7, 8.24, 8.30, 8.33** | Direct subtypes of `BaseDataType`, `Integer`, `Number`, and `UInteger` may only be defined in NamespaceIndex 0 — vendors/companion specs must reuse the existing concrete leaves rather than adding new direct children of these specific abstract roots. `Enumeration` is confirmed **not** subject to this restriction. | Gap | *Pass 4: individually verified all 4 primary subclauses directly (identical wording in each: "Any direct subtype shall only be defined in NamespaceIndex 0") plus 8.14 (Enumeration) directly, confirming the sentence does not appear there.* This corrects pass 3's low-confidence version, which had folded `Enumeration` into this same closed set based on a single broad skim — that inclusion was wrong, now positively disproven rather than just suspected. A clean example of why single-pass bulk fetches in this catalog get a confidence caveat and a second look. |
| AS-060 | **8.14** | A concrete Enumeration DataType that does not directly inherit from the abstract `Enumeration` DataType may only **restrict** its immediate supertype's enumeration values when subtyped further — it must not add new values or change the text associated with an inherited value. | Gap | *Pass 4: verified directly against 8.14* — "Any enumeration DataType not directly inheriting from the Enumeration DataType can only restrict the enumeration values of its supertype... shall neither add enumeration values nor change the text associated to the enumeration value." (Days→Workdays is a valid restriction; the reverse is not.) Consistent with the narrowing-only pattern seen repeatedly elsewhere in this catalog (AS-026/027/028/040/046/055). Scoped precisely: this restricts *deeper* subtyping of an already-concrete enumeration, not the initial value set a type picks when it first derives from the abstract `Enumeration` root (see AS-061). |
| AS-061 | **8.14** | Every concrete Enumeration DataType must derive, directly or transitively via `HasSubtype`, from the abstract `Enumeration` DataType. | Gap | *Pass 4 finding.* Verified directly: "All enumeration DataTypes shall inherit from this DataType." Same family as AS-024 (every ReferenceType except `References` has exactly one supertype) and AS-053 (every EventType derives from `BaseEventType`) — a recurring "closed, single-rooted hierarchy" pattern across ReferenceTypes, EventTypes, and now Enumerations. |

## §6 Type Model for ObjectTypes/VariableTypes (subtyping, instantiation)

Much of this section is **already implemented**, via the Virtual-Types machinery
(`owl2vt.py`, `lib/owlbuilder.py`) and HermiT-based consistency checking
(`check_consistency.py`), rather than as `validation/ontology/*.shacl.ttl` shapes.
Pass 2 went deeper here — §6.2 (Definitions), §6.3.3 (Overriding InstanceDeclarations),
and §6.4.4.2–6.4.4.4 (ModellingRules details) were skipped entirely in pass 1 (only
6.2.8, 6.3.2, and 6.4.4.1's intro were checked) — and turned up a real, currently
unimplemented gap that closely parallels the ValueRank-narrowing rule that *is* already
implemented (AS-046 below).

| ID | Section | Rule | Status | Notes |
|---|---|---|---|---|
| AS-026 | 6.2.8 | The `DataType` Attribute of a Variable/VariableType may only be overridden with a **subtype** of the originally-declared DataType — never an unrelated type or a supertype. | **Implemented (reasoner)** | Matches this repo's "Enforce DataType existence in Virtual Types" / sibling-type-override-contradiction work in `owl2vt.py`/`check_consistency.py`. |
| AS-027 | 6.2.8 | The `ValueRank` Attribute may only be **further restricted** when overridden: `Any`→anything; `ScalarOrOneDimension`→`Scalar` or `OneDimension`; `OneOrMoreDimensions`→a specific dimension count (≥0); all other values must stay unchanged. | **Implemented, verified correct** | `validation/ontology/rankValue.shacl.ttl`'s `OPCUANodeShape` SPARQL constraint implements exactly this narrowing table (I checked its SPARQL body line-by-line against the spec's four cases — they match). |
| AS-028 | 6.2.8 | The `ArrayDimensions` Attribute, when overridden, may only change a `0` entry to a concrete positive value or be newly added where absent; all other existing entries must remain unchanged. | **Gap** | `rankValue.shacl.ttl` checks `ArrayDimensions` is a well-formed list of positive integers and that its length matches `ValueRank`, but does **not** check the narrowing-only (0→concrete, others frozen) constraint against a supertype/prior value. |
| AS-029 | 6.3.2 | A subtype inherits all Attribute values from its supertype except `NodeId` (always unique per Node); other Attributes may be freely overridden/refined; Attributes the supertype left optional-and-unset may be newly set on the subtype. | New | Mostly implicit in how the pipeline constructs subclasses; not an explicit standalone check today. |
| AS-030 | 6.4.3 | For Variables and Objects, `HasTypeDefinition` must point to the same TypeDefinitionNode as their InstanceDeclaration, or a subtype of it. | *(duplicate)* | Same rule as AS-010 — cross-referenced, not a separate item. |
| AS-040 | 6.2.4, **6.3.3.3** | A subtype overriding a Method InstanceDeclaration's Arguments: (a) must **not remove** any existing argument; (b) must **not** change (narrow) the DataType of any argument whose original DataType was already **concrete** — only arguments with an **abstract** original DataType may be narrowed to a concrete/more-specific subtype; (c) may append **additional** arguments only if they are **optional** and placed strictly **after** all of the supertype's existing arguments — mandatory arguments must never be added. | Gap | *Pass 2 finding.* 6.3.3.3 gives the sharp, conditional version of this ("A subtype shall not override an argument... defined with a concrete DataType"; "shall not remove an argument"; "shall not add mandatory additional arguments... may append optional arguments after all existing arguments"); 6.2.4's looser "may specialize the DataType of arguments" was the first hint of this in pass 1's underlying source material but wasn't itself opened as a section. |
| AS-041 | 6.2.9 | For TypeDefinitionNodes defined in OPC 10000-5 (the standard Information Model), the NodeIds of their InstanceDeclarations are fixed by the standard and must be reused identically by every Server that implements that type. | Advanced | *Pass 2 finding.* Only checkable against an external reference catalog of Part 5's well-known NodeIds, which isn't otherwise part of this pipeline's scope — lowest priority. For non-standard (vendor) TypeDefinitionNodes, different Servers may legitimately assign different NodeIds to the same InstanceDeclaration (identified instead by BrowsePath, per 6.2.9's opening statement). |
| AS-042 | 6.3.3.3 | An InstanceDeclaration may only be overridden if it is **directly** referenced (via a forward hierarchical Reference) from the TypeDefinitionNode being overridden — a deeper (grandchild-or-below) InstanceDeclaration cannot be overridden directly from the root; each intermediate level must itself be materialized/overridden down to that point. | Gap | *Pass 2 finding.* "It is only possible to override InstanceDeclarations that are directly referenced from the TypeDefinitionNode" (6.3.3.3). |
| AS-043 | 6.3.3.3 | When both endpoints of a hierarchical Reference are themselves overridden Nodes, the Reference between them in the subtype must use the **same ReferenceType** as the corresponding Reference in the supertype, or a **subtype** of that ReferenceType. | Gap | *Pass 2 finding.* "A Reference is replaced if it goes between two overridden Nodes and has the same ReferenceType as a Reference defined in the supertype. The Reference specified in the subtype may be a subtype of the ReferenceType used in the parent type" (6.3.3.3). |
| AS-044 | 6.3.3.3 | For a single-cardinality NonHierarchical Reference (e.g. `HasTypeDefinition`) on an overridden InstanceDeclaration, if its target changes, the new target must have the **same NodeClass** as the original — and, for Object/Variable targets specifically, the **same TypeDefinitionNode or a subtype of it**. | Gap | *Pass 2 finding.* Generalizes AS-010 (which is the `HasTypeDefinition`-specific instance of this rule) to any single-valued NonHierarchical Reference. Source: "Any NonHierarchical References... are treated as new References unless the ReferenceType only allows a single Reference per SourceNode. When [it does]... the new target shall have the same NodeClass and for Objects and Variables also the same type or a subtype of the type specified in the parent" (6.3.3.3). |
| AS-045 | 6.3.3.3 | Every **overriding** InstanceDeclaration Node (i.e. a Node materialized in a subtype's own hierarchy to override an inherited one) must have its **own** `HasModellingRule` and `HasTypeDefinition` References — even when their values are unchanged from the supertype's corresponding InstanceDeclaration. These are never left implicitly inherited without being materialized on the overriding Node itself. | Gap | *Pass 2 finding.* "Each overriding InstanceDeclaration needs its own HasModellingRule and HasTypeDefinition References, even if they have not been changed" (6.3.3.3). Strengthens AS-008's cardinality rule specifically for the override case. |
| AS-046 | **6.4.4.2**, 6.4.4.3 | When a Node's `ModellingRule` differs from the ModellingRule on the InstanceDeclaration it was seeded from — whether via subtype-override of a supertype's InstanceDeclaration (6.3.3.3), or via reusing another type's instance as an InstanceDeclaration of a new type (6.4.4.3's "second case") — the change must be a **narrowing** per this table (constraints may only tighten, never loosen): `Mandatory`→`Mandatory` only; `Optional`→`Mandatory` or `Optional`; `MandatoryPlaceholder`→`MandatoryPlaceholder` only; `OptionalPlaceholder`→`MandatoryPlaceholder` or `OptionalPlaceholder`. | **Gap — genuinely unimplemented today** | *Pass 2 finding, high-value.* Verified against 6.4.4.2's Table 21 and its explicit general principle ("constraints shall only be tightened, not loosened... it is not allowed to specify on the supertype that an instance shall exist with the ModellingRule Mandatory and on the subtype make this ModellingRule Optional"). I checked: `validation/ontology/modellingRule.shacl.ttl` only validates `hasModellingRule` cardinality (≤1) and that its value is one of the 5 known ModellingRule NodeIds — it does **not** check narrowing legality against a supertype/seed. `lib/owlbuilder.py` references ModellingRule handling extensively (for correctly *building* Virtual Types) but I found no comparison of a child's ModellingRule against its inherited one to reject illegal loosening. This is structurally the closest parallel in this whole catalog to the already-implemented `rankValue.shacl.ttl` ValueRank-narrowing check (AS-027) — same shape of problem, same fix pattern, but not yet built. Per 6.4.4.3, this only applies when the Node is itself acting as an InstanceDeclaration of a further type (composition or subtyping) — a plain "normal" leaf-level instance's ModellingRule (if it even has one) is unconstrained. |
| AS-047 | 6.4.4.4.1–6.4.4.4.5 | Each of the 5 standard ModellingRules constrains how many "similar Nodes" (6.2.4: same BrowseName + NodeClass, and same-or-subtype TypeDefinition) must/may exist per conforming instance of the TypeDefinitionNode: `Mandatory` = the same BrowsePath must exist in every instance; `Optional` = 0 or 1, fixed BrowseName; `ExposesItsArray` = exactly one instance per element of the referenced array-valued Variable, connected via the same hierarchical ReferenceType as the type definition; `OptionalPlaceholder` = 0 or more instances, arbitrary BrowseNames, no other constraint; `MandatoryPlaceholder` = 1 or more instances required, arbitrary BrowseNames. | Advanced | *Pass 2 finding.* Verified against 6.4.4.4.1–6.4.4.4.5 primary text. This is a **type↔instance cross-consistency** check (for every Node whose `HasTypeDefinition` points at TypeX, confirm the right children exist per TypeX's InstanceDeclarationHierarchy+ModellingRules) — structurally more involved than a single-Node SHACL shape, and conceptually closer to what the Virtual-Types/HermiT machinery already reasons about than a new standalone rule. §6.5 ("Changing Type Definitions that are already used") restates the `Mandatory` case from the type-evolution angle rather than the instantiation angle — same underlying invariant, not a separate rule; also N/A here since this pipeline validates one static snapshot, not a change history. |

## §7 Standard ReferenceTypes — source/target NodeClass constraints

| ID | Section | Rule | Status | Notes |
|---|---|---|---|---|
| AS-031 | 7 | `HasComponent`: SourceNode must be Object, ObjectType, DataVariable, or VariableType; TargetNode must be Variable, Object, or Method. | **Implemented** | `validation/ontology/hasComponent.shacl.ttl` → `HasComponentTargetConstraint`, `HasComponentTargetSourceConstraint`. |
| AS-032 | 7 | `HasProperty`: TargetNode must be Variable NodeClass (used as a Property); SourceNode may be any NodeClass. | **Implemented** | `validation/ontology/hasProperty.shacl.ttl` → `OPCUAHasPropertyRuleShape`. |
| AS-033 | **7.10** | `HasSubtype`: Source and Target must be the same NodeClass, one of ObjectType, VariableType, DataType, or ReferenceType. | Gap | *Pass 3: verified* against 7.10 primary text directly — "The SourceNode... shall be an ObjectType, a VariableType, a DataType or a ReferenceType"; "the TargetNode shall be of the same NodeClass as the SourceNode." Not found as an explicit shape. In this repo's model, subtyping is materialized directly as `rdfs:subClassOf` rather than an explicit `hasSubtype` predicate (see AS-024's note), so implementation would mean: every `rdfs:subClassOf` pair must have matching NodeClass individuals on both ends. |
| AS-034 | **7.11** | `Organizes`: SourceNode must be Object, ObjectType, or View; TargetNode may be any NodeClass. | Gap | *Pass 3: verified* against 7.11 primary text directly — matches exactly. Advisory (not "shall") refinement from 5.5.3: an Object source "should always be" specifically of `FolderType` or a subtype. 5.5.3 also confirms `Organizes` References "do not prevent loops" and can combine with `HasChild` References to "span multiple hierarchies" — useful corroboration for why AS-022's `ContainsNoLoops` check is a real, non-vacuous rule (loops are structurally possible, not prevented by construction). |
| AS-035 | **7.13** | `HasTypeDefinition`: SourceNode must be Object or Variable; TargetNode must be ObjectType (if source is Object) or VariableType (if source is Variable). | Gap | *Pass 3: verified* against 7.13 primary text directly — "If the SourceNode is an Object, then the TargetNode shall be an ObjectType; if the SourceNode is a Variable, then the TargetNode shall be a VariableType." Type-consistency half of AS-008's rule (cardinality half). |
| AS-036 | **7.12** | `HasModellingRule`: SourceNode must be Object, Variable, or Method; TargetNode must be an Object of ObjectType `ModellingRule` or a subtype; a Node has **at most one** `HasModellingRule` Reference. | **Implemented** | *Pass 3: verified* against 7.12 primary text directly — "Each Node shall be the SourceNode of at most one HasModellingRule Reference," matching `modellingRule.shacl.ttl`'s existing `sh:maxCount 1`. The cardinality and target-set checks are implemented; the SourceNode-NodeClass constraint (Object/Variable/Method only) is not separately asserted but is lower-risk since `nodeset2owl.py` only ever emits `hasModellingRule` on those NodeClasses by construction. |
| AS-037 | 7 | Remaining specialized ReferenceTypes (`HasFieldDescription`, `HasFieldDescriptionSetMandatory`, `IsDisabledOptionalField`, `UsesSubtypeRestriction`, `AllowedSubtype`, `HasDataTypeRefinement`) each have their own source/target NodeClass constraint. | New / Low priority | Listed for completeness — this row has shrunk to just the `DataTypeRefinement`/`SubtypeRestriction` family (7.25–7.30), none of which is modelled by `nodeset2owl.py`, all lowest priority. Not individually spot-checked. *Pass 2:* `HasInterface`/`HasAddIn` moved out — see AS-050/AS-051. *Pass 3:* `HasSubtype`/`Organizes`/`HasTypeDefinition`/`HasModellingRule` moved out — see AS-033–036. *Pass 4:* `GeneratesEvent`/`HasEventSource`/`HasNotifier` moved out — see AS-062–064. *Pass 5:* `AlwaysGeneratesEvent`/`HasEncoding`/`IsDeprecated`/`HasStructuredComponent`/`AssociatedWith`/`UsesDataTypeRefinement` moved out — see AS-065–070. |
| AS-054 | **5.7.2** | `HasArgumentDescription` (a subtype of `HasComponent`): SourceNode must be Method; TargetNode must be Variable. Used to reference a Method's argument metadata (`InputArguments`/`OutputArguments`, see AS-020). | Gap | *Pass 3 finding.* Verified against 5.7.2 primary text directly. |
| AS-055 | **5.7.3** | `HasOptionalInputArgumentDescription` (a subtype of `HasArgumentDescription`): within a Method's `InputArguments` array, every optional argument must be positioned strictly **after** all non-optional (mandatory) arguments. | Gap | *Pass 3 finding.* Verified against 5.7.3 primary text directly: "Optional input arguments shall always follow any non-optional input arguments in the InputArguments array." Same "new/optional goes after existing/mandatory, never inserted or reordered" pattern seen repeatedly elsewhere in this catalog (AS-040's Method-argument-override rule, AS-028's ArrayDimensions narrowing, AS-046's ModellingRule narrowing) — worth implementing consistently if any one of this family gets built. |
| AS-062 | **7.15** | `GeneratesEvent`: SourceNode must be ObjectType, VariableType, or a Method InstanceDeclaration; TargetNode must be an ObjectType representing an EventType — `BaseEventType` or a subtype of it. | Gap | *Pass 4 finding.* Verified against 7.15 primary text directly. Independently corroborates AS-053's "every EventType derives from BaseEventType" rule via the TargetNode constraint here. `GeneratesEvent`/`HasEventSource` References are already captured generically by `nodeset2owl.py` (confirmed: referenced in `lib/utils.py`'s `get_ignored_references`, used to *exclude* them from Virtual-Types generation, which only makes sense if they're present in the base `.owl.ttl` graph already) — so this is checkable today, not blocked. |
| AS-063 | **7.17** | `HasEventSource` (a subtype of `HierarchicalReferences`): SourceNode must be an Object or View with the `SubscribeToEvents` bit set in its `EventNotifier` Attribute, or an ObjectType (when referencing an InstanceDeclaration — not itself considered a subscription source); TargetNode may be any NodeClass capable of generating events. **Following only `HasEventSource` References (or its subtypes) from any Node must never lead back to that same Node** — multiple distinct paths to the same descendant are explicitly permitted, but a cycle back to the origin is not. | **Gap — genuine graph algorithm** | *Pass 4 finding.* Verified against 7.17 primary text directly: "Starting from Node 'A'... following References of the HasEventSource ReferenceType or of its subtypes it shall never be possible to return to 'A'." This is a **second, unconditional** cycle-detection rule in this catalog (alongside AS-022) — unlike AS-022 (only checked when a View's `ContainsNoLoops=true`), this one has no opt-out: `HasEventSource`/`HasNotifier` chains must always be acyclic, full stop. Same implementation approach as AS-022 (SPARQL property-path self-reachability, or procedural DFS), but globally scoped rather than per-View. |
| AS-064 | **7.18** | `HasNotifier` (a subtype of `HasEventSource`): TargetNode must be an Object that is itself a source of Event Subscriptions. If the TargetNode of a `HasNotifier` Reference generates (or forwards) Event type X, the SourceNode must also provide/forward Event type X. | Advanced | *Pass 4 finding.* Verified against 7.18 primary text directly. The event-propagation-consistency half requires combining `GeneratesEvent` (AS-062) with `HasNotifier` chains transitively — genuinely more involved than a single-Node shape; lower priority given this repo's pipeline doesn't otherwise process the Event Model much beyond capturing the raw References. |
| AS-065 | **7.16** | `AlwaysGeneratesEvent` (a subtype of `GeneratesEvent`): SourceNode must be specifically a Method InstanceDeclaration (narrower than `GeneratesEvent`'s Method-InstanceDeclaration-or-ObjectType-or-VariableType); TargetNode must be `BaseEventType` or a subtype. Semantically: the Method **must** generate this Event on every call (vs. `GeneratesEvent`'s more permissive "may generate"). | Gap | *Pass 5 finding.* Verified against 7.16 primary text directly. |
| AS-066 | **7.14** | `HasEncoding`: SourceNode must be a subtype of the `Structure` DataType; TargetNode must be an Object of `DataTypeEncodingType` or a subtype. | **Gap** *(corrected — see AS-058)* | *Pass 5 finding.* Verified against 7.14 primary text directly. Completes the NodeClass-constraint half of AS-058 (which covers HasEncoding's cardinality/bidirectionality). |
| AS-067 | **7.21** | `IsDeprecated`: SourceNode may be any NodeClass; TargetNode must be an Object representing the information-model version in which the SourceNode was first deprecated. | **Gap** | *Pass 5 finding.* Verified against 7.21 primary text directly. Empirically confirmed present in generated graphs (`opcua:IsDeprecated`-derived triples found in a fresh `core.owl.ttl` build) — captured generically like any other plain Reference, not blocked. |
| AS-068 | **7.22** | `HasStructuredComponent`: SourceNode must be a VariableType or Variable with a `Structure` DataType; TargetNode must be a Variable representing a field (scalar case) or an array element with a positional BrowseName (`<V[N]>`, array case). Distinguished from `ExposesItsArray` (AS-047) by BrowseName stability: `HasStructuredComponent`'s BrowseNames are position-bound (reordering shifts values and can delete higher-indexed elements); `ExposesItsArray`'s are position-independent (elements keep their original value/identity through reordering). | Advanced | *Pass 5 finding.* Verified against 7.22/7.22.2 primary text directly. The "TargetNode represents a real field of the DataType" half is effectively blocked on `DataTypeDefinition` (AS-021) even though the Reference itself would be captured generically. |
| AS-069 | **7.23** | `AssociatedWith`: SourceNode and TargetNode must both be Objects. This ReferenceType is symmetric with no `InverseName`. | **Gap** | *Pass 5 finding.* Verified against 7.23 primary text directly. A concrete, real-world instance of AS-018's general Symmetric⟹no-InverseName conditional rule. Empirically confirmed present in generated graphs. |
| AS-070 | **7.24** | `UsesDataTypeRefinement`: SourceNode must be a Variable with a Structured DataType; TargetNode must be an Object of `DataTypeRefinementType`/`SubtypeRestrictionType`. | Advanced | *Pass 5 finding.* Verified against 7.24 primary text directly. Same DataTypeDefinition-dependency caveat as AS-068/AS-025. |

---

## Summary

**Pass 1** covered §4.4, §4.5, §4.6, §5.2–5.8.3/5.8.6.1, §6.2.8/6.3.2/6.4.3, and a single
bulk-table fetch of §7 — and produced AS-001–AS-037.

**Pass 2** went back for everything pass 1 skipped in the sections most load-bearing for
this repo's existing Virtual-Types machinery: all of §6.2 (Definitions, only 6.2.8 had
been read), §6.3.3 (Overriding InstanceDeclarations, not opened at all), §6.4.4.2–6.4.4.4
(ModellingRules details, only the 6.4.4.1 intro had been read), §6.5, and §4.10
(Interfaces/AddIns, not opened at all despite AS-037 already citing unverified
`HasInterface`/`HasAddIn` rows from the bulk §7 table). It added AS-038–AS-051, refined
AS-009/AS-010/AS-011 with sharper citations and previously-missed detail (NodeClass
immutability, the Placeholder-BrowseName exemption), and replaced the placeholder
Method-argument rule with 6.3.3.3's precise conditional version.

**Pass 3** verified everything pass 2 had flagged as bulk-table-sourced-only or entirely
unopened: all four §7 ReferenceTypes actually used in the catalog (`HasSubtype`,
`Organizes`, `HasTypeDefinition`, `HasModellingRule` — AS-033–036, now all individually
confirmed against primary text), plus §4.7 Event Model, §4.9 Roles, §4.2/§4.3, the
remaining §5 subsections (5.5.3 FolderType, 5.6.3/5.6.4 Properties/DataVariable formal
definitions, 5.7.2/5.7.3 Method-argument ReferenceTypes), §5.8.1 (DataTypeEncoding
exclusivity), §5.8.5 (DataTypeRefinement detail), and a light skim of §8/§9. It added
AS-052–AS-060, upgraded AS-008/AS-033–036's confidence from inferred to directly quoted,
and — the most consequential single finding of this pass — broadened AS-005 and
sharpened AS-007 into the fully precise, symmetric AS-057 (a Property and a DataVariable
are mutually exclusive by their incoming references, and that mutual exclusivity is
**not currently checked** despite adjacent, related shapes already existing for each
side individually).

**Pass 4** closed out the "still not opened" list from pass 3: §4.8 Methods (confirmed
non-normative, like §4.3/§4.9), the Event-related §7 ReferenceTypes (`GeneratesEvent`,
`HasEventSource`, `HasNotifier` — AS-062–064), §5.5.4/§5.6.1 (confirmed non-normative),
§5.8.2/§5.8.4 (DataTypeEncoding detail, AS-058 updated), and — the main event —
individually verified AS-059's numeric-DataType-namespace claim against all 4 relevant
primary subclauses (`BaseDataType`, `Integer`, `Number`, `UInteger`, all confirmed
identical) plus `Enumeration`'s (8.14, confirmed **absent**), positively disproving
pass 3's low-confidence guess rather than leaving it as a hedge. It added AS-061–AS-064.

**Pass 5** closed the remaining short list from pass 4: §5.6.6 (confirmed non-normative,
parallels 5.5.4 exactly as predicted); six more §7 ReferenceTypes (`AlwaysGeneratesEvent`,
`HasEncoding`, `IsDeprecated`, `HasStructuredComponent`, `AssociatedWith`,
`UsesDataTypeRefinement` — AS-065–070); a deeper §8 pass (`Structure`'s own subclause,
8.32); and a targeted §9 skim for any broadly-applicable EventType property rule (found
none, confirmed by the spec's own text that BaseEventType's field list is Part 5's
responsibility, not Part 3's). It also produced this catalog's second self-correction:
checking `nodesetparser.py`'s `references_ignore()` directly (rather than trusting the
earlier "not extracted, confirmed via grep" note by analogy) showed that `HasEncoding` —
unlike the genuinely-unparsed `InverseName`/`DataTypeDefinition` **Attributes** — is a
plain **Reference**, captured generically like any other. Verified empirically: a fresh
`core.owl.ttl` build contains real `opcua:hasEncoding` triples. **AS-058's status was
wrong and is now corrected** from Blocked to Gap.

- **70 distinct rules** identified (AS-001–AS-070; AS-030 is a cross-referenced duplicate
  of AS-010, not counted separately), plus 6 explicitly-excluded statements (multi-Server
  residency ×2, two "should"-not-"shall" advisories, one temporal/runtime-only rule, one
  opaque-string-comparison implementation note) recorded for traceability rather than
  silently dropped. Five full sections/section-groups (§4.3, §4.8, §4.9, §5.5.4+§5.6.1,
  §5.6.6) were opened and confirmed to contain no Part-3-normative structural rules at
  all — same treatment as Part 1, not silently skipped.
- **7 already implemented** (5 as SHACL shapes, 2 via the HermiT/Virtual-Types reasoner) —
  genuinely working today, not just planned. No new "already implemented" findings in
  passes 3–5, but pass 3 did confirm `modellingRule.shacl.ttl`'s existing cardinality
  check (AS-036) matches the spec's "at most one" language exactly.
- **2 blocked** on `nodeset2owl.py` not yet extracting the XML **Attribute** the rule
  depends on (`InverseName`, `DataTypeDefinition`) — down from 3 after AS-058's pass-5
  correction; `HasEncoding`/`DataTypeEncoding` moved to Gap.
- **3 rules are real graph/cross-consistency algorithms, not simple shapes**: AS-022
  (View `ContainsNoLoops` — cycle detection, conditional on the Attribute), AS-063
  (`HasEventSource` chains — cycle detection, **unconditional**, pass 4 finding), and
  AS-047 (per-ModellingRule instantiation cardinality — a type↔instance
  cross-consistency check).
- **AS-046 remains the single highest-value finding across all five passes**: a
  genuinely unimplemented gap (ModellingRule narrowing on override, Table 21) that is
  structurally the closest parallel anywhere in this catalog to a rule that *is* already
  implemented and verified correct (AS-027, ValueRank narrowing) — same shape of problem,
  same fix pattern, not yet built. See the code-level note next to
  `validation/ontology/modellingRule.shacl.ttl` for the implementation-side pointer.
- **Two kinds of error caught across five passes, both worth remembering**: (1)
  transcription errors from single-pass bulk fetches (AS-016/017's `AccessLevelEx`
  placement, pass 1; AS-059's wrong `Enumeration` inclusion, suspected pass 3, disproven
  pass 4) and (2) a status-classification error from reasoning by analogy instead of
  checking the actual code (AS-058 marked Blocked without verifying `references_ignore()`
  directly, corrected pass 5). Different failure modes, same fix: check the primary
  source directly rather than trust an inference, however reasonable it looked at the
  time.
- The rest are gaps of varying confidence/priority, marked as such above rather than
  presented as uniformly ready to implement.

**Still not opened, candidates for a pass 6** (very short list at this point): the
`DataTypeRefinement`/`SubtypeRestriction` family in AS-037 (`HasFieldDescription` and its
4 siblings, 7.25–7.30) — none of the underlying constructs are modelled by
`nodeset2owl.py`, so this is genuinely lowest priority even once verified; the bulk of
§8's ~60 concrete DataType entries and §9's EventType catalog beyond the two rounds of
targeted spot-checks so far — both sections are explicitly type inventories and every
check across two passes has confirmed low/no yield, so further coverage here is a
diminishing-returns judgment call rather than a known gap in confidence.
