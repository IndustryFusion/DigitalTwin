
-- ===== STEP 1: first row for a1 (ts 10:00:05) =====
INSERT INTO t VALUES ('a1', 'X', TIMESTAMP '2026-01-01 10:00:05');

-- ===== STEP 2: a LARGER ts -> new top-1 under DESC. Count must stay 1. =====
INSERT INTO t VALUES ('a1', 'Y', TIMESTAMP '2026-01-01 10:00:10');
