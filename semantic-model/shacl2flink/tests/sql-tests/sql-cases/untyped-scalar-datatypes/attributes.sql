-- The four common datatypes meeting values that declare no type.
--
-- This is the branch production runs. Across the live entity store not one
-- attribute value carries an @type -- 183 strings, 83 numbers, 12 booleans,
-- none typed -- so debeziumBridge.js leaves valueType NULL for every
-- attribute, while every model fixture has it populated because JSON-LD
-- always assigns one.
--
-- With valueType NULL the COALESCE in each arm of the datatype check makes
-- the type comparison vacuously true, so the lexical form alone decides. That
-- is the relaxed reading, and it is what these rows pin:
--
--   urn:wellformed:1  1.5 / 42 / true / anything  -> silent
--   urn:malformed:1   abc / 1.5 / yes             -> alerts on double,
--                                                    integer and boolean
--
-- And one consequence worth stating rather than discovering: malformed's
-- aString holds 99 and does NOT alert. The string arm has no lexical test --
-- every value is a well-formed string -- so with no declared type a
-- sh:datatype xsd:string accepts anything at all. That is the price of the
-- relaxed reading, and it is deliberate; the absent alert is part of what
-- this case asserts.

INSERT INTO `attributes` VALUES
('urn:wellformed:1\https://industry-fusion.com/types/v0.9/aDouble\@none', CAST(NULL as STRING), 'urn:wellformed:1', 'https://industry-fusion.com/types/v0.9/aDouble', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1.5', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:wellformed:1\https://industry-fusion.com/types/v0.9/anInteger\@none', CAST(NULL as STRING), 'urn:wellformed:1', 'https://industry-fusion.com/types/v0.9/anInteger', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '42', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:wellformed:1\https://industry-fusion.com/types/v0.9/aBoolean\@none', CAST(NULL as STRING), 'urn:wellformed:1', 'https://industry-fusion.com/types/v0.9/aBoolean', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'true', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:wellformed:1\https://industry-fusion.com/types/v0.9/aString\@none', CAST(NULL as STRING), 'urn:wellformed:1', 'https://industry-fusion.com/types/v0.9/aString', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'anything', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:malformed:1\https://industry-fusion.com/types/v0.9/aDouble\@none', CAST(NULL as STRING), 'urn:malformed:1', 'https://industry-fusion.com/types/v0.9/aDouble', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'abc', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:malformed:1\https://industry-fusion.com/types/v0.9/anInteger\@none', CAST(NULL as STRING), 'urn:malformed:1', 'https://industry-fusion.com/types/v0.9/anInteger', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1.5', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:malformed:1\https://industry-fusion.com/types/v0.9/aBoolean\@none', CAST(NULL as STRING), 'urn:malformed:1', 'https://industry-fusion.com/types/v0.9/aBoolean', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', 'yes', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:malformed:1\https://industry-fusion.com/types/v0.9/aString\@none', CAST(NULL as STRING), 'urn:malformed:1', 'https://industry-fusion.com/types/v0.9/aString', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '99', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:wellformed:1', 'https://industry-fusion.com/types/v0.9/workpiece', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:malformed:1', 'https://industry-fusion.com/types/v0.9/workpiece', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
