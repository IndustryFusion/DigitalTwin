
-- ===== STEP 1: first row for a1 (ts 10:00:10) -> count 1 =====
INSERT INTO t VALUES ('a1', 'X', TIMESTAMP '2026-01-01 10:00:10');

-- ===== STEP 2: a SMALLER ts for the same id. Under ORDER BY ts ASC this
--               becomes the new top-1, so the old row must be retracted.
--               The count must still be 1. =====
INSERT INTO t VALUES ('a1', 'Y', TIMESTAMP '2026-01-01 10:00:05');
