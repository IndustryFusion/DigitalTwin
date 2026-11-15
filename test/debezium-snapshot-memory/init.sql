--
-- Copyright (c) 2026 IndustryFusion Foundation
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--    http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.
--
-- A knowledge table shaped like shacl2flink's `rdf` (create_rdf_table.py),
-- sized like the OPC UA pumps package: 219,500 triples of ~175 bytes
-- (measured on the real table: subject 78, predicate 50, object 47 bytes on
-- average). The row count, not the byte volume, is what fills the Connect
-- heap, so the synthetic rows only need the same count and shape.
CREATE TABLE public.rdf (
    subject text NOT NULL,
    predicate text NOT NULL,
    object text,
    index bigint NOT NULL,
    PRIMARY KEY (subject, predicate, index)
);

INSERT INTO public.rdf
SELECT '<http://opcfoundation.org/UA/Pumps/' || md5(n::text) || md5((n * 7)::text) || '>',
       '<http://www.w3.org/2000/01/rdf-schema#' || (ARRAY['subClassOf', 'domain', 'range', 'label'])[1 + n % 4] || '>',
       '<http://opcfoundation.org/UA/' || md5((n * 13)::text) || '>',
       n % 10
FROM generate_series(1, 219500) AS n;
