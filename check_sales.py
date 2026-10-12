"""
Quick diagnostic: how many sales are in the database right now?
Run from project root: python check_sales.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "sari_sari_pos.db"

if not DB_PATH.exists():
    print(f"ERROR: Database not found at {DB_PATH}")
    raise SystemExit(1)

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# ── Counts ──
cur.execute("SELECT COUNT(*) AS n FROM sales")
total = cur.fetchone()["n"]
print(f"Total sales rows:   {total}")

cur.execute("SELECT COUNT(*) AS n FROM sales WHERE status = 'completed'")
completed = cur.fetchone()["n"]
print(f"Completed sales:    {completed}")

cur.execute("SELECT COUNT(*) AS n FROM sales WHERE status = 'voided'")
voided = cur.fetchone()["n"]
print(f"Voided sales:       {voided}")

cur.execute("SELECT COUNT(*) AS n FROM sale_items")
items = cur.fetchone()["n"]
print(f"Sale items rows:    {items}")

# ── Status breakdown ──
print()
print("Status breakdown:")
cur.execute("SELECT status, COUNT(*) AS n FROM sales GROUP BY status")
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"  {r['status']:<12} {r['n']}")
else:
    print("  (no rows)")

# ── Most recent 10 ──
print()
print("Most recent 10 sales:")
cur.execute("""
    SELECT s.id, s.invoice_number, s.user_id, u.username,
           s.final_amount, s.status, s.created_at
    FROM sales s
    LEFT JOIN users u ON s.user_id = u.id
    ORDER BY s.id DESC
    LIMIT 10
""")
rows = cur.fetchall()
if rows:
    print(f"  {'ID':<5} {'Invoice':<28} {'User':<12} {'Amount':>10} {'Status':<12} Created")
    print("  " + "-" * 90)
    for r in rows:
        amt = float(r["final_amount"] or 0)
        print(f"  {r['id']:<5} {r['invoice_number']:<28} "
              f"{(r['username'] or '?'):<12} "
              f"₱{amt:>9.2f} {r['status']:<12} {r['created_at']}")
else:
    print("  (no sales at all)")

conn.close()
