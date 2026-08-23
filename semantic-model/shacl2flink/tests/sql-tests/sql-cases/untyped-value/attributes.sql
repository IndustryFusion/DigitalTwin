-- A value that declares no datatype.
--
-- This case exists because no model file can produce it. JSON-LD always
-- assigns a type -- 1 becomes xsd:integer, "1" becomes xsd:string -- and
-- create_ngsild_models.py materialises it, so every attributes table derived
-- from a .jsonld has valueType populated.
--
-- The bridge does not. debeziumBridge.js sets valueType only when the
-- expanded attribute carries an @type, and a plain string literal expands to
-- {"@value": "ON"} with none. So a NULL valueType is not a contrived state:
-- it is what production writes for an ordinary string attribute, and this is
-- the only fixture that exercises it.
--
-- What it pins: with no declared type, a sh:datatype xsd:string is satisfied.
-- That is the relaxed reading -- a value is read by its lexical form, not by
-- how it was typed -- and hasString below is the row that depends on it. The
-- alerts in `expected` are the other attributes, which fail for their own
-- reasons; hasString is absent from that list on purpose.
--
-- Regenerating this file from a model would silently delete that coverage.

INSERT INTO `attributes` VALUES
('urn:filter:1\https://industryfusion.github.io/contexts/example/v0/base_entities/hasIntegerOrDouble\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasIntegerOrDouble', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:1\https://industryfusion.github.io/contexts/example/v0/base_entities/hasInteger\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasInteger', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:1\https://industryfusion.github.io/contexts/example/v0/base_entities/hasJSON\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasJSON', '@json', NULL, 'https://uri.etsi.org/ngsi-ld/JsonProperty', '{"simple":"object"}', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:1\https://industryfusion.github.io/contexts/example/v0/base_entities/hasString\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasString', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:1\https://industryfusion.github.io/contexts/example/v0/base_entities/hasDouble\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasDouble', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1.0', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:1\https://industryfusion.github.io/contexts/example/v0/base_entities/hasList\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasList', '@list', NULL, 'https://uri.etsi.org/ngsi-ld/ListProperty', '[1, 2, 3]', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:1\https://industryfusion.github.io/contexts/example/v0/base_entities/hasBoolean\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasBoolean', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'True', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industryfusion.github.io/contexts/example/v0/base_entities/hasIntegerOrDouble\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasIntegerOrDouble', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'True', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industryfusion.github.io/contexts/example/v0/base_entities/hasList\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasList', '@list', NULL, 'https://uri.etsi.org/ngsi-ld/ListProperty', '1', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industryfusion.github.io/contexts/example/v0/base_entities/hasInteger\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasInteger', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1.0', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industryfusion.github.io/contexts/example/v0/base_entities/hasJSON\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasJSON', '@json', NULL, 'https://uri.etsi.org/ngsi-ld/JsonProperty', '1', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industryfusion.github.io/contexts/example/v0/base_entities/hasBoolean\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasBoolean', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industryfusion.github.io/contexts/example/v0/base_entities/hasString\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasString', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industryfusion.github.io/contexts/example/v0/base_entities/hasDouble\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/hasDouble', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:1', 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:2', 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
