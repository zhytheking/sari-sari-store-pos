-- ============================================================
-- V2__failed_login_lockouts.sql
-- Creates the login_attempts table for lockout tracking.
--
-- One row per username. Tracks:
--   - attempt_count:    consecutive failed login attempts
--   - locked_until:     set when attempt_count reaches the threshold
--   - last_attempt_at:  last failed attempt time
--
-- The lockout logic reads/writes this table via
-- _record_failed_attempt and _reset_failed_attempts in auth.py.
-- ============================================================

CREATE TABLE IF NOT EXISTS login_attempts (
    username TEXT PRIMARY KEY,
    attempt_count INTEGER DEFAULT 0,
    last_attempt_at TIMESTAMP,
    locked_until TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_login_attempts_username
    ON login_attempts(username);

CREATE INDEX IF NOT EXISTS idx_login_attempts_locked_until
    ON login_attempts(locked_until);
    