"""
One-time fix: add users.password_changed_at and register V3.

Why this exists:
  - The intended migration file was named V2_password_changed_at.sql
    (one underscore) and would not be picked up by the migration
    runner's regex (^V(\d+)__(.+)\.sql$, two underscores required).
  - V2 is already taken by V2__failed_login_lockouts.sql.
  - The column needs to exist for token staleness checks to work.

This script:
  1. Adds password_changed_at if it doesn't exist.
  2. Records a V3 entry in schema_migrations so the version counter
     moves forward correctly.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "sari_sari_pos.db"

print("=" * 60)
print("  ADD password_changed_at COLUMN")
print("=" * 60)
print(f"  DB: {DB_PATH}")

if not DB_PATH.exists():
    print("  [ERROR] Database not found.")
    raise SystemExit(1)

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 1. Add the column
cursor.execute("PRAGMA table_info(users)")
cols = [r['name'] for r in cursor.fetchall()]

if 'password_changed_at' in cols:
    print("  Column 'password_changed_at' already exists.")
else:
    cursor.execute(
        "ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP"
    )
    print("  Column 'password_changed_at' added.")

# 2. Record V3 in the migrations table
cursor.execute("SELECT version FROM schema_migrations WHERE version = '3'")
if cursor.fetchone():
    print("  V3 already recorded in schema_migrations.")
else:
    cursor.execute("""
        INSERT INTO schema_migrations
        (version, filename, description, success)
        VALUES (?, ?, ?, ?)
    """, ('3', 'V3__password_changed_at.sql',
          'password_changed_at', 1))
    print("  V3 recorded in schema_migrations.")

conn.commit()
conn.close()

print("  [OK] Done.")
print("=" * 60)
