Issue: #985

# Proposal

## Why

An OPC UA type can add members to a child through the child's instance declaration, beyond what the child's own type defines (for example a child declared as `BaseObjectType` or `FunctionalGroupType` that declares additional variables). These members are part of the owning type's definition, but the generated SHACL only validates what types define, so they are never checked. In addition, shacl2flink accepts a constraint written underneath a relationship's `ngsi-ld:hasObject` and compiles it into a check that can never fire, so such a shape looks validated while it is not.

## What Changes

- The OPC UA shape generation validates members that a child declaration adds beyond its type, through the relationship to the child: the owning type's shape constrains the referenced entity with a node shape for the declaration, in addition to the constraints of the child's type. Entity types are unchanged.
- Only additions in a direct child object (one relationship) are validated. Deeper additions are reported by the generator once per owning type.
- shacl2flink evaluates a node shape on the object of a relationship against the referenced entity, and raises one alert per owning entity and relationship, whose text names the referenced entity and the violated inner constraint.
- shacl2flink rejects at build time every constraint underneath `ngsi-ld:hasObject` that it cannot evaluate, instead of compiling a check that never fires. **BREAKING** for shapes that rely on the silent acceptance: they now fail the build.
- The SemForge SDK shows the cause of a violated nested node shape and counts the shapes reached through it as reached.
- Placeholder members that a declaration adds are constrained like type-defined placeholders: the class of each referenced entity and the count of distinct `datasetId`s.
- shacl2flink's offline models keep every instance of an attribute with its own `datasetId`. Today an instance without a `datasetId` is merged into an instance with a `datasetId` and the same value, so offline checks and the comparison with pyshacl count one instance too few.

## Capabilities

### New Capabilities
- `opcua/instance-declaration-shapes`: the shapes generated for members that an instance declaration adds beyond the declared child's type, their depth limit and the report of what is not validated.
- `shacl2flink/node-shapes-across-relationships`: streaming validation of node shapes applied to the object of a relationship, the alert it raises, and the rejection of constraints underneath `ngsi-ld:hasObject` that cannot be evaluated.
- `semforge-sdk/nested-node-results`: how the SDK and the editor report results of node shapes reached through a relationship: their cause, and whether a shape is reached.
- `shacl2flink/attribute-instances`: how the offline models keep the instances of a multi-instance attribute apart and how the checks count them.

### Modified Capabilities

## Impact

- **opcua**: `owl2instances.py` and the shape library generate the nested shapes and the report of deeper additions; the generated `shacl.ttl` of models with such declarations gains shapes, and their KMS packages change accordingly.
- **shacl2flink**: the SQL generation for relationships gains a check on the referenced entity's attributes; `unsupported_shapes` gains a rule; the documentation of the supported SHACL subset (`docs/supported-features.md`) changes; the Flink job gains joins with pinned state, bounded by the live model.
- **SemForge SDK**: the validation adapter, the shape page reach and the constraint enumerator; the VS Code extension shows the cause.
- **shacl2flink offline models**: `create_ngsild_models.py`, used by the SQLite cases and the pyshacl comparison, keeps attribute instances apart; expected results of existing SQLite cases with equal values across instances may change.
- **Contracts**: no contract between components changes. The form of the generated shapes is shared by opcua, shacl2flink and the SemForge SDK and is specified in the three capabilities. Alerts keep their format; a new event name (`NodeConstraintComponent`) appears for the new check.

## Out of Scope

- Validating members added more than one relationship deep.
- Generating types for such children (virtual types) or changing the type of any entity.
- Validating members added to a variable's properties beyond what its variable type defines.
- Changing how existing constraints of a type are generated or evaluated, apart from keeping attribute instances apart in the offline models.
- Replacing `datasetId` as the key of attribute instances.
