-- sh:hasValue compared against values that declare no type.
--
-- The shape asks for the string "1.0". With no declared type the check falls
-- to its ELSE arm and compares val against the constant directly, so what
-- matters is that both stay the strings they are.
--
--   urn:gauge:1  setting "1.0"  -> silent, it is the required value
--   urn:gauge:2  setting "1"    -> alerts, a different string
--
-- This case could not be written until the constraint table stopped declaring
-- its columns STRING. SQLite has no STRING type and derives affinity from the
-- letters of the name, so STRING landed in NUMERIC affinity and turned the
-- stored "1.0" into 1 -- after which "1" and "1.0" compared equal and neither
-- row alerted. Flink keeps the string and would have alerted on gauge:2, so
-- the oracle and the engine disagreed on every constraint parameter that
-- looked like a number.

INSERT INTO `attributes` VALUES
('urn:gauge:1\https://industry-fusion.com/types/v0.9/setting\@none', CAST(NULL as STRING), 'urn:gauge:1', 'https://industry-fusion.com/types/v0.9/setting', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1.0', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:gauge:2\https://industry-fusion.com/types/v0.9/setting\@none', CAST(NULL as STRING), 'urn:gauge:2', 'https://industry-fusion.com/types/v0.9/setting', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:gauge:1', 'https://industry-fusion.com/types/v0.9/gauge', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:gauge:2', 'https://industry-fusion.com/types/v0.9/gauge', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
