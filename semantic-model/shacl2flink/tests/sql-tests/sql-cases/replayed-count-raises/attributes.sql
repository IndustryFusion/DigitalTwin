--
-- Copyright (c) 2026 IndustryFusion Foundation
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--   http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.
--
-- Count raises replayed after a statementset redeploy (issue #977).
--
-- A redeploy replays constraint_trigger_table, so the new job starts out
-- reading the raises its predecessor left there. The rows planted below are
-- those raises -- one per count check and entity, with the text the previous
-- job wrote. The checks then run over the current model. Every key the checks
-- evaluate must be written again, or the planted raise is what gets published:
--
--   urn:filter:1  satisfied now: one cartridge, one strength   -> both close
--   urn:filter:2  still violated: no cartridge, two strengths  -> both stay
--                 open, with the verdict of this run, not the replayed text
--   urn:filter:3  deleted, with its attributes                 -> both close
--
-- constraint_id 0 is the hasCartridge count and 1 the hasStrength count, in
-- the order shacl.ttl declares them.

INSERT INTO `constraint_trigger_table` VALUES
('urn:filter:1', 'CountConstraintComponent(https://industry-fusion.com/types/v0.9/hasCartridge)', 0, true, 'warning', 'Model validation for relationship https://industry-fusion.com/types/v0.9/hasCartridge failed for urn:filter:1. Found 10 relationships instead of [1, 1]!', CURRENT_TIMESTAMP),
('urn:filter:1', 'CountConstraintComponent(https://industry-fusion.com/types/v0.9/hasStrength)', 1, true, 'warning', 'Model validation for Property https://industry-fusion.com/types/v0.9/hasStrength failed for urn:filter:1. Found 10 properties instead of [1, 1]!', CURRENT_TIMESTAMP),
('urn:filter:2', 'CountConstraintComponent(https://industry-fusion.com/types/v0.9/hasCartridge)', 0, true, 'warning', 'Model validation for relationship https://industry-fusion.com/types/v0.9/hasCartridge failed for urn:filter:2. Found 10 relationships instead of [1, 1]!', CURRENT_TIMESTAMP),
('urn:filter:2', 'CountConstraintComponent(https://industry-fusion.com/types/v0.9/hasStrength)', 1, true, 'warning', 'Model validation for Property https://industry-fusion.com/types/v0.9/hasStrength failed for urn:filter:2. Found 10 properties instead of [1, 1]!', CURRENT_TIMESTAMP),
('urn:filter:3', 'CountConstraintComponent(https://industry-fusion.com/types/v0.9/hasCartridge)', 0, true, 'warning', 'Model validation for relationship https://industry-fusion.com/types/v0.9/hasCartridge failed for urn:filter:3. Found 10 relationships instead of [1, 1]!', CURRENT_TIMESTAMP),
('urn:filter:3', 'CountConstraintComponent(https://industry-fusion.com/types/v0.9/hasStrength)', 1, true, 'warning', 'Model validation for Property https://industry-fusion.com/types/v0.9/hasStrength failed for urn:filter:3. Found 10 properties instead of [1, 1]!', CURRENT_TIMESTAMP);

INSERT INTO `attributes` VALUES
('urn:filter:1\https://industry-fusion.com/types/v0.9/hasCartridge\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industry-fusion.com/types/v0.9/hasCartridge', '@id', NULL, 'https://uri.etsi.org/ngsi-ld/Relationship', 'urn:filterCartridge:1', '@none', NULL, CAST(NULL AS STRING), false, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:1\https://industry-fusion.com/types/v0.9/hasStrength\@none', CAST(NULL as STRING), 'urn:filter:1', 'https://industry-fusion.com/types/v0.9/hasStrength', '@value', 'http://www.w3.org/2001/XMLSchema#double', 'https://uri.etsi.org/ngsi-ld/Property', '0.9', '@none', NULL, CAST(NULL AS STRING), false, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industry-fusion.com/types/v0.9/hasStrength\@none', CAST(NULL as STRING), 'urn:filter:2', 'https://industry-fusion.com/types/v0.9/hasStrength', '@value', 'http://www.w3.org/2001/XMLSchema#double', 'https://uri.etsi.org/ngsi-ld/Property', '0.9', '@none', NULL, CAST(NULL AS STRING), false, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:2\https://industry-fusion.com/types/v0.9/hasStrength\urn:index:1', CAST(NULL as STRING), 'urn:filter:2', 'https://industry-fusion.com/types/v0.9/hasStrength', '@value', 'http://www.w3.org/2001/XMLSchema#double', 'https://uri.etsi.org/ngsi-ld/Property', '0.8', 'urn:index:1', NULL, CAST(NULL AS STRING), false, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
-- urn:filter:3 is deleted, and the bridge deletes its attributes stripped of
-- their values (see sql-cases/deleted-entities).
('urn:filter:3\https://industry-fusion.com/types/v0.9/hasCartridge\@none', CAST(NULL as STRING), 'urn:filter:3', 'https://industry-fusion.com/types/v0.9/hasCartridge', '@id', NULL, 'https://uri.etsi.org/ngsi-ld/Relationship', CAST(NULL AS STRING), '@none', NULL, CAST(NULL AS STRING), true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('urn:filter:3\https://industry-fusion.com/types/v0.9/hasStrength\@none', CAST(NULL as STRING), 'urn:filter:3', 'https://industry-fusion.com/types/v0.9/hasStrength', '@value', NULL, 'https://uri.etsi.org/ngsi-ld/Property', CAST(NULL AS STRING), '@none', NULL, CAST(NULL AS STRING), true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO `entities` VALUES
('urn:filter:1', 'https://industry-fusion.com/types/v0.9/filter', false, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:2', 'https://industry-fusion.com/types/v0.9/filter', false, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filter:3', 'https://industry-fusion.com/types/v0.9/filter', true, CURRENT_TIMESTAMP);
INSERT INTO `entities` VALUES
('urn:filterCartridge:1', 'https://industry-fusion.com/types/v0.9/filterCartridge', false, CURRENT_TIMESTAMP);
