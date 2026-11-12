-- sh:in with numbers, booleans, strings and IRIs.
--
-- A value is in the list when its lexical form is a member's and, if the
-- attribute declares a datatype (valueType), the datatypes are the same too:
-- SHACL compares RDF terms. A value that declares none -- the normal case for
-- the bridge, which sets valueType only when the message carries an @type --
-- is read by its lexical form alone, as sh:datatype reads it (see
-- untyped-value).
--
-- urn:filter:1 and :3 hold allowed values without and with a datatype;
-- urn:filter:2 values outside the lists; urn:filter:4 an allowed lexical form
-- with the wrong datatype. `expected` holds the alerts of :2 and :4 only.

INSERT INTO `attributes` VALUES
('urn:filter:1\https://industryfusion.github.io/contexts/example/v0/base_entities/hasLevel\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasLevel', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:1\https://industryfusion.github.io/contexts/example/v0/base_entities/hasFlag\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasFlag', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'true', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:1\https://industryfusion.github.io/contexts/example/v0/base_entities/hasMode\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasMode', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'say "hi"', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:1\https://industryfusion.github.io/contexts/example/v0/base_entities/hasMaterial\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasMaterial', '@id', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'https://industryfusion.github.io/contexts/ontology/v0/material/steel', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industryfusion.github.io/contexts/example/v0/base_entities/hasLevel\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasLevel', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '3', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industryfusion.github.io/contexts/example/v0/base_entities/hasFlag\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasFlag', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'True', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industryfusion.github.io/contexts/example/v0/base_entities/hasMode\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasMode', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'on', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industryfusion.github.io/contexts/example/v0/base_entities/hasMaterial\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasMaterial', '@id', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'https://industryfusion.github.io/contexts/ontology/v0/material/iron', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:3\https://industryfusion.github.io/contexts/example/v0/base_entities/hasLevel\@none', CAST(NULL as STRING), 'urn:filter:3', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasLevel', '@value', 'http://www.w3.org/2001/XMLSchema#integer', 'https://uri.etsi.org/ngsi-ld/Property', '2', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:3\https://industryfusion.github.io/contexts/example/v0/base_entities/hasFlag\@none', CAST(NULL as STRING), 'urn:filter:3', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasFlag', '@value', 'http://www.w3.org/2001/XMLSchema#boolean', 'https://uri.etsi.org/ngsi-ld/Property', 'true', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:3\https://industryfusion.github.io/contexts/example/v0/base_entities/hasMode\@none', CAST(NULL as STRING), 'urn:filter:3', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasMode', '@value', 'http://www.w3.org/2001/XMLSchema#string', 'https://uri.etsi.org/ngsi-ld/Property', 'OFF', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:4\https://industryfusion.github.io/contexts/example/v0/base_entities/hasLevel\@none', CAST(NULL as STRING), 'urn:filter:4', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasLevel', '@value', 'http://www.w3.org/2001/XMLSchema#string', 'https://uri.etsi.org/ngsi-ld/Property', '1', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:4\https://industryfusion.github.io/contexts/example/v0/base_entities/hasFlag\@none', CAST(NULL as STRING), 'urn:filter:4', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasFlag', '@value', 'http://www.w3.org/2001/XMLSchema#string', 'https://uri.etsi.org/ngsi-ld/Property', 'true', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:3', 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:4', 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
