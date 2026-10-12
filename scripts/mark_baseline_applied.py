"""
Mark V1__baseline as already applied on an existing database.

Run this ONCE on a database that was created by the old init_db()
(before migrations existed). It inserts a row into schema_migrations
so that V1__baseline.sql does NOT try to CREATE TABLE on tables
that already exist.

Usage:
    python scripts/mark_baseline_applied.py

Safe to run multiple times — it will not duplicate the row.
"""
import sqlite3
import sys
from pathlib import Path

# Locate the DB the same way the app does
project_root = Path(__file__).resolve().parent.parent
db_path = project_root / "data" / "sari_sari_pos.db"

# Allow override via env
import os
env_path = os.environ.get("DB_PATH")
if env_path:
    db_path = Path(env_path)

print("=" * 60)
print("  MARK BASELINE MIGRATION AS APPLIED")
print("=" * 60)
print(f"  DB path: {db_path}")

if not db_path.exists():
    print(f"  [ERROR] Database not found at {db_path}")
    sys.exit(1)

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Ensure the migrations table exists
cursor.execute("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version TEXT NOT NULL UNIQUE,
        filename TEXT NOT NULL,
        description TEXT NOT NULL,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        success INTEGER DEFAULT 1,
        error_message TEXT
    )
""")

# Check if V1 is already there
cursor.execute("SELECT version FROM schema_migrations WHERE version = '1'")
if cursor.fetchone():
    print("  V1__baseline is already marked as applied.")
    conn.close()
    sys.exit(0)

# Sanity check: does the DB actually have the baseline schema?
cursor.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
)
if not cursor.fetchone():
    print("  [ERROR] This database does not have the baseline schema.")
    print("  The users table is missing.")
    print("  If this is a fresh DB, run: python run.py --init-db")
    conn.close()
    sys.exit(1)

# Insert the baseline marker
cursor.execute("""
    INSERT INTO schema_migrations
    (version, filename, description, success)
    VALUES (?, ?, ?, ?)
""", (
    '1',
    'V1__baseline.sql',
    'baseline',
    1,
))

conn.commit()
conn.close()

print("  [OK] V1__baseline marked as applied.")
print("=" * 60)
