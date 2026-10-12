-- ============================================================
-- V4__audit_logs_enhance.sql
-- Extend audit_logs with structured columns for filtering.
--
-- New columns:
--   category   TEXT  -- 'auth' | 'sale' | 'stock' | 'product'
--                    -- | 'user' | 'settings' | 'system'
--   action     TEXT  -- already exists; e.g. 'LOGIN', 'SALE_CREATE'
--   target_type TEXT -- 'user' | 'product' | 'sale' | 'setting' | null
--   target_id  INTEGER -- the affected row's ID
--   result     TEXT  -- 'success' | 'failure'
--   metadata   TEXT  -- free-form JSON (small)
-- ============================================================

-- SQLite does not support adding columns to a table with UNIQUE
-- or PRIMARY KEY constraints via ALTER TABLE without a rewrite.
-- audit_logs has neither on the columns we want to add, so
-- ALTER TABLE ADD COLUMN works.

ALTER TABLE audit_logs ADD COLUMN category TEXT DEFAULT 'system';
ALTER TABLE audit_logs ADD COLUMN target_type TEXT;
ALTER TABLE audit_logs ADD COLUMN target_id INTEGER;
ALTER TABLE audit_logs ADD COLUMN result TEXT DEFAULT 'success';
ALTER TABLE audit_logs ADD COLUMN metadata TEXT;

CREATE INDEX IF NOT EXISTS idx_audit_logs_category
    ON audit_logs(category);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at
    ON audit_logs(timestamp);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action_category
    ON audit_logs(action, category);
