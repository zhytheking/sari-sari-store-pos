"""
Print the status of all migrations: found on disk, applied in DB,
and any mismatches between the two.
"""
import sqlite3
import re
from pathlib import Path

# Your actual layout: backend/database/migrations/sql/
HERE = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = HERE / "backend" / "database" / "migrations" / "sql"
DB_PATH = HERE / "data" / "sari_sari_pos.db"

print("=" * 70)
print("  MIGRATION STATUS")
print("=" * 70)
print(f"  DB:               {DB_PATH}")
print(f"  Migrations dir:   {MIGRATIONS_DIR}")
print()

# 1. Files on disk
files_on_disk = {}
if MIGRATIONS_DIR.exists():
    for f in sorted(MIGRATIONS_DIR.glob("V*.sql")):
        m = re.match(r'^V(\d+)__(.+)\.sql$', f.name)
        if m:
            files_on_disk[m.group(1)] = f.name
        else:
            # Capture files that DON'T match the pattern
            files_on_disk.setdefault('?', []).append(f.name)

print("  Files on disk (matching V<n>__name.sql):")
if files_on_disk:
    for v in sorted((k for k in files_on_disk if k != '?'), key=int):
        print(f"    V{v:<4} {files_on_disk[v]}")

if files_on_disk.get('?'):
    print()
    print("  Files on disk that DO NOT match the pattern:")
    for name in files_on_disk['?']:
        print(f"    !!! {name}")
    print("  (These will be silently ignored by the runner.)")

if not files_on_disk:
    print("    (none)")
print()

# 2. Applied in DB
applied = {}
if DB_PATH.exists():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        for row in cursor.execute(
            "SELECT version, filename, success FROM schema_migrations "
            "ORDER BY CAST(version AS INTEGER)"
        ):
            applied[row['version']] = {
                'filename': row['filename'],
                'success': row['success'],
            }
    except sqlite3.OperationalError as e:
        print(f"  [WARN] schema_migrations not readable: {e}")
    conn.close()

print("  Applied in DB:")
if applied:
    for v in sorted(applied, key=int):
        info = applied[v]
        status = "OK" if info['success'] else "FAILED"
        print(f"    V{v:<4} {info['filename']:<45} [{status}]")
else:
    print("    (none)")
print()

# 3. Comparison
print("  " + "-" * 66)
print()

disk_versions = {k for k in files_on_disk if k != '?'}
only_on_disk = disk_versions - set(applied)
only_in_db = set(applied) - disk_versions

if only_on_disk:
    print("  Files on disk that are NOT applied:")
    for v in sorted(only_on_disk, key=int):
        print(f"    V{v}  {files_on_disk[v]}")
    print()

if only_in_db:
    print("  Applied in DB but NOT found on disk:")
    for v in sorted(only_in_db, key=int):
        print(f"    V{v}  {applied[v]['filename']}")
    print()

if not only_on_disk and not only_in_db and applied:
    print("  All migrations are applied and accounted for.")
    print()

# 4. Next version
all_versions = disk_versions | set(applied)
next_version = max((int(v) for v in all_versions), default=0) + 1
print(f"  Next migration version should be: V{next_version}")
print("=" * 70)
