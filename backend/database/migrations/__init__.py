
#Database migration manager.

import os
import sys
import re
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timezone

from database.connection import get_db


class MigrationManager:
    #Manages database schema migrations using raw SQL files

    def __init__(self):

        if getattr(sys, 'frozen', False):
            base = Path(sys._MEIPASS) / "backend" / "database" / "migrations"
        else:
            base = Path(__file__).resolve().parent

        self.migration_folder = base / "sql"
        self.migrations_table = "schema_migrations"

        self._ensure_migrations_table()

    def _ensure_migrations_table(self):
        db = get_db()
        cursor = db.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.migrations_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                description TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success INTEGER DEFAULT 1,
                error_message TEXT
            )
        """)

    def get_applied_migrations(self) -> List[str]:
        self._ensure_migrations_table()
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                f"SELECT version FROM {self.migrations_table} "
                f"WHERE success = 1 ORDER BY CAST(version AS INTEGER)"
            )
            return [row[0] for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            return []

    def get_migration_files(self) -> List[Dict]:
        if not self.migration_folder.exists():
            self.migration_folder.mkdir(parents=True, exist_ok=True)
            return []

        files = []
        for file_path in sorted(self.migration_folder.glob("V*.sql")):
            match = re.match(r'^V(\d+)__(.+)\.sql$', file_path.name)
            if not match:
                print(f"  [WARN] Skipping '{file_path.name}': name does "
                      f"not match 'V<number>__<name>.sql'")
                continue
            version = match.group(1)
            description = match.group(2).replace('_', ' ')
            files.append({
                'version': version,
                'filename': file_path.name,
                'description': description,
                'path': file_path,
                'full_path': str(file_path),
            })

        files.sort(key=lambda f: int(f['version']))
        return files

    def get_pending_migrations(self) -> List[Dict]:
        self._ensure_migrations_table()
        applied = set(self.get_applied_migrations())
        all_migrations = self.get_migration_files()
        return [m for m in all_migrations if m['version'] not in applied]

    def _split_sql(self, sql_content: str) -> List[str]:
        statements: List[str] = []
        current: List[str] = []
        i = 0
        length = len(sql_content)
        in_single = False
        in_double = False
        in_line_comment = False
        in_block_comment = False

        while i < length:
            ch = sql_content[i]
            next_ch = sql_content[i + 1] if i + 1 < length else ''

            if in_line_comment:
                if ch == '\n':
                    in_line_comment = False
                i += 1
                continue

            if in_block_comment:
                if ch == '*' and next_ch == '/':
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_single:
                current.append(ch)
                if ch == "'" and next_ch == "'":
                    current.append(next_ch)
                    i += 2
                    continue
                if ch == "'":
                    in_single = False
                i += 1
                continue

            if in_double:
                current.append(ch)
                if ch == '"':
                    in_double = False
                i += 1
                continue

            if ch == '-' and next_ch == '-':
                in_line_comment = True
                i += 2
                continue

            if ch == '/' and next_ch == '*':
                in_block_comment = True
                i += 2
                continue

            if ch == "'":
                in_single = True
                current.append(ch)
                i += 1
                continue

            if ch == '"':
                in_double = True
                current.append(ch)
                i += 1
                continue

            if ch == ';':
                stmt = ''.join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
                i += 1
                continue

            current.append(ch)
            i += 1

        stmt = ''.join(current).strip()
        if stmt:
            statements.append(stmt)

        return statements

    def run_migration(self, migration: Dict) -> bool:
        db = get_db()
        cursor = db.cursor()

        try:
            with open(migration['path'], 'r', encoding='utf-8') as f:
                sql_content = f.read()

            statements = self._split_sql(sql_content)
            print(f"    Parsed {len(statements)} statement(s)")

            cursor.execute("BEGIN")
            try:
                for idx, statement in enumerate(statements, 1):
                    try:
                        cursor.execute(statement)
                    except sqlite3.Error as e:
                        raise RuntimeError(
                            f"Statement {idx}/{len(statements)} failed: {e}\n"
                            f"  SQL: {statement[:200]}"
                        )

                cursor.execute(f"""
                    INSERT INTO {self.migrations_table}
                    (version, filename, description, success)
                    VALUES (?, ?, ?, ?)
                """, (
                    migration['version'],
                    migration['filename'],
                    migration['description'],
                    1,
                ))

                db.commit()
                return True

            except Exception:
                db.rollback()
                raise

        except Exception as e:
            error_msg = str(e)
            try:
                cursor.execute(f"""
                    INSERT INTO {self.migrations_table}
                    (version, filename, description, success, error_message)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    migration['version'],
                    migration['filename'],
                    migration['description'],
                    0,
                    error_msg[:1000],
                ))
                db.commit()
            except Exception as record_error:
                print(f"    [WARN] Could not record failure: {record_error}")

            print(f"    [ERROR] {error_msg}")
            return False

    def migrate(self) -> Dict:
        self._ensure_migrations_table()
        pending = self.get_pending_migrations()

        if not pending:
            return {
                'success': True,
                'message': 'No pending migrations',
                'applied': [],
                'errors': [],
            }

        applied = []
        errors = []

        for migration in pending:
            print(f"  Applying migration: {migration['description']} "
                  f"(v{migration['version']})")

            if self.run_migration(migration):
                applied.append(migration['version'])
                print(f"  [OK] Migration {migration['version']} applied")
            else:
                errors.append({
                    'version': migration['version'],
                    'error': f"Failed to apply migration {migration['version']}",
                })
                print(f"  [FAIL] Migration {migration['version']} failed")
                break

        return {
            'success': len(errors) == 0,
            'message': f"Applied {len(applied)} migrations, {len(errors)} failed",
            'applied': applied,
            'errors': errors,
        }

    def create_migration(self, description: str) -> str:
        if not self.migration_folder.exists():
            self.migration_folder.mkdir(parents=True, exist_ok=True)

        files = self.get_migration_files()
        if files:
            max_version = max(int(f['version']) for f in files)
            new_version = max_version + 1
        else:
            new_version = 1

        safe_description = re.sub(r'[^a-zA-Z0-9]', '_', description.lower())
        safe_description = re.sub(r'_+', '_', safe_description).strip('_')
        filename = f"V{new_version}__{safe_description}.sql"
        filepath = self.migration_folder / filename

        template = f"""-- Migration: {description}
-- Version: {new_version}
-- Created: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC

-- Write your migration SQL here.

"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(template)
        return str(filepath)

    def get_migration_status(self) -> Dict:
        self._ensure_migrations_table()
        applied = self.get_applied_migrations()
        pending = self.get_pending_migrations()
        all_migrations = self.get_migration_files()

        return {
            'total_migrations': len(all_migrations),
            'applied_count': len(applied),
            'pending_count': len(pending),
            'applied_migrations': applied,
            'pending_migrations': [m['description'] for m in pending],
            'migrations': [
                {
                    'version': m['version'],
                    'description': m['description'],
                    'filename': m['filename'],
                    'is_applied': m['version'] in applied,
                }
                for m in all_migrations
            ],
        }


migration_manager = MigrationManager()


def run_migrations() -> Dict:
    return migration_manager.migrate()


def create_migration(description: str) -> str:
    return migration_manager.create_migration(description)


def get_migration_status() -> Dict:
    return migration_manager.get_migration_status()
