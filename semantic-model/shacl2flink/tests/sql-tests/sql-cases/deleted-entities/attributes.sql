-- Deletion. No model file can express it: create_ngsild_models.py always emits
-- `deleted` as NULL, so every jsonld fixture describes an entity that exists
-- and nothing in the suite ever exercised the path taken when one stops
-- existing. Production reaches it constantly -- deleting an entity in Scorpio
-- makes debeziumBridge publish the entity with deleted=true and EVERY one of
-- its attributes with deleted=true.
--
-- A deleted attribute arrives STRIPPED. debeziumBridge.js keeps only
-- id, parentId, name, entityId, type, datasetId and nodeType (diffAttributes,
-- the pickFields call); attributeValue, valueType, unitCode and lang are
-- dropped. The rows below are shaped that way on purpose -- a fixture that
-- carried the value through would be testing a message the bridge never sends.
--
-- What this pins, and what it cannot:
--   * a deleted ENTITY is not validated at all -- no constraint of any kind
--     reports on it, count or otherwise
--   * a deleted ATTRIBUTE stops counting, so a mandatory one going away is a
--     minCount violation rather than silence
--   * a live entity pointing at a DELETED entity fails sh:class, because the
--     far end no longer exists
--
-- It cannot pin the streaming half. SQLite evaluates this in one batch pass, so
-- the retraction accounting that produced "Found -1 relationships" on Flink has
-- no analogue here -- SUM over 0/1 terms cannot go below zero in batch, which
-- is exactly why the oracle stayed silent while Flink was wrong. That half is
-- covered by tests/bats/test-shacl-flink-e2e.

INSERT INTO `attributes` VALUES
-- urn:filter:1 -- healthy: live filter, live cartridge. Silent.
('urn:filter:1\https://industry-fusion.com/types/v0.9/hasCartridge\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industry-fusion.com/types/v0.9/hasCartridge', '@id', NULL, 'https://uri.etsi.org/ngsi-ld/Relationship', 'urn:filterCartridge:1', '@none', NULL, CAST(NULL AS STRING), false, true, CURRENT_TIMESTAMP),
-- urn:filter:2 -- the entity itself is deleted, so the bridge also deletes its
-- attributes. Nothing about it may be reported: it is gone.
('urn:filter:2\https://industry-fusion.com/types/v0.9/hasCartridge\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industry-fusion.com/types/v0.9/hasCartridge', '@id', NULL, 'https://uri.etsi.org/ngsi-ld/Relationship', CAST(NULL AS STRING), '@none', NULL, CAST(NULL AS STRING), true, true, CURRENT_TIMESTAMP),
-- urn:filter:3 -- the filter lives, its mandatory relationship was deleted.
-- The attribute must stop counting, leaving 0 against sh:minCount 1.
('urn:filter:3\https://industry-fusion.com/types/v0.9/hasCartridge\@none', CAST(NULL as STRING), 'urn:filter:3', 'https://industry-fusion.com/types/v0.9/hasCartridge', '@id', NULL, 'https://uri.etsi.org/ngsi-ld/Relationship', CAST(NULL AS STRING), '@none', NULL, CAST(NULL AS STRING), true, true, CURRENT_TIMESTAMP),
-- urn:filter:4 -- the filter and its relationship both live; the CARTRIDGE at
-- the far end was deleted. This is the reported case: the relationship still
-- counts (so no count violation) but it no longer resolves to an entity.
('urn:filter:4\https://industry-fusion.com/types/v0.9/hasCartridge\@none', CAST(NULL as STRING), 'urn:filter:4', 'https://industry-fusion.com/types/v0.9/hasCartridge', '@id', NULL, 'https://uri.etsi.org/ngsi-ld/Relationship', 'urn:filterCartridge:9', '@none', NULL, CAST(NULL AS STRING), false, true, CURRENT_TIMESTAMP);

INSERT INTO `entities` VALUES
('urn:filter:1', 'https://industry-fusion.com/types/v0.9/filter', false, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:2', 'https://industry-fusion.com/types/v0.9/filter', true, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:3', 'https://industry-fusion.com/types/v0.9/filter', false, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:4', 'https://industry-fusion.com/types/v0.9/filter', false, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filterCartridge:1', 'https://industry-fusion.com/types/v0.9/filterCartridge', false, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filterCartridge:9', 'https://industry-fusion.com/types/v0.9/filterCartridge', true, CURRENT_TIMESTAMP);
