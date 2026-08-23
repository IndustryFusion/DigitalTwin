-- sh:maxCount on a Property, across datasetIds.
--
-- An NGSI-LD attribute is (entity, name, datasetId), so urn:filter:11 below
-- carries TWO instances of hasStrength and must violate sh:maxCount 1.
--
--   urn:filter:10  one instance          -> silent
--   urn:filter:11  two instances         -> CountConstraintComponent
--   urn:filter:12  no instance at all    -> CountConstraintComponent (minCount)

INSERT INTO `attributes` VALUES
('urn:filter:10\https://industry-fusion.com/types/v0.9/hasStrength\@none', CAST(NULL as STRING), 'urn:filter:10', 'https://industry-fusion.com/types/v0.9/hasStrength', '@value', 'http://www.w3.org/2001/XMLSchema#double', 'https://uri.etsi.org/ngsi-ld/Property', '0.9', '@none', NULL, CAST(NULL AS STRING), false, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:11\https://industry-fusion.com/types/v0.9/hasStrength\@none', CAST(NULL as STRING), 'urn:filter:11', 'https://industry-fusion.com/types/v0.9/hasStrength', '@value', 'http://www.w3.org/2001/XMLSchema#double', 'https://uri.etsi.org/ngsi-ld/Property', '0.9', '@none', NULL, CAST(NULL AS STRING), false, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:11\https://industry-fusion.com/types/v0.9/hasStrength\urn:index:1', CAST(NULL as STRING), 'urn:filter:11', 'https://industry-fusion.com/types/v0.9/hasStrength', '@value', 'http://www.w3.org/2001/XMLSchema#double', 'https://uri.etsi.org/ngsi-ld/Property', '0.8', 'urn:index:1', NULL, CAST(NULL AS STRING), false, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO `entities` VALUES
('urn:filter:10', 'https://industry-fusion.com/types/v0.9/filter', false, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:11', 'https://industry-fusion.com/types/v0.9/filter', false, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:12', 'https://industry-fusion.com/types/v0.9/filter', false, CURRENT_TIMESTAMP);
