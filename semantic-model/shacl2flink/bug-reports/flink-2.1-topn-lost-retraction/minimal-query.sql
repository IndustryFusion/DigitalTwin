
-- COUNT over a top-1 view: exactly one row per id, so this must stay 1.
INSERT INTO rowcount SELECT 1 AS k, COUNT(*) AS cnt FROM v;
