-- A custom sh:datatype meeting a value that declares no type.
--
-- No model file can express this. JSON-LD always assigns a type, so every
-- attributes table derived from a .jsonld has valueType populated -- and that
-- is the case all 84 model fixtures test. Production is the opposite, and not
-- marginally: across the live entity store, not one attribute value carries
-- an @type at all (183 strings, 83 numbers, 12 booleans, none typed).
-- debeziumBridge.js sets valueType only when it finds one, so in production
-- valueType is NULL for every attribute.
--
-- That makes this the branch that actually runs, and it is worth pinning in
-- both directions:
--
--   urn:workpiece:1  valueType NULL           -> silent. Undeclared is not
--                                                wrong. Reading it as wrong
--                                                would alert on every value
--                                                of every custom-datatype
--                                                shape in production.
--   urn:workpiece:2  valueType xsd:string     -> alerts. A type that IS
--                                                declared and is not the one
--                                                asked for is a violation,
--                                                and still has to be caught.
--
-- Delete either row and the check degenerates: keep only the first and a
-- check that never fires still passes; keep only the second and a check that
-- always fires still passes.

INSERT INTO `attributes` VALUES
('urn:workpiece:1\https://industry-fusion.com/types/v0.9/material\@none', CAST(NULL as STRING), 'urn:workpiece:1', 'https://industry-fusion.com/types/v0.9/material', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', '1.4301', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:workpiece:2\https://industry-fusion.com/types/v0.9/material\@none', CAST(NULL as STRING), 'urn:workpiece:2', 'https://industry-fusion.com/types/v0.9/material', '@value', 'http://www.w3.org/2001/XMLSchema#string', 'https://uri.etsi.org/ngsi-ld/Property', '1.4301', '@none', NULL, CAST(NULL AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS BOOLEAN), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:workpiece:1', 'https://industry-fusion.com/types/v0.9/workpiece', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:workpiece:2', 'https://industry-fusion.com/types/v0.9/workpiece', CAST(NULL as BOOLEAN), CURRENT_TIMESTAMP);
