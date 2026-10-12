#Database connection with pooling support.
#Transaction model:
#Request scope:
#Concurrency:

import sqlite3
import os
import threading
from contextlib import contextmanager

from flask import g, has_request_context, current_app

try:
    from backend.config import config
except ImportError:
    from config import config


class DatabaseConnection:
    #Database connection manager with connection pooling

    _pool = {}
    _pool_lock = threading.Lock()
    _max_pool_size = 10

    @classmethod
    def get_connection(cls, db_path=None):
        #Get a database connection from the pool or create one
        if db_path is None:
            try:
                db_path = current_app.config.get('DB_PATH', config.DB_PATH)
            except RuntimeError:
                db_path = config.DB_PATH

        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        with cls._pool_lock:
            if db_path not in cls._pool:
                cls._pool[db_path] = []

        #Reuse a pooled connection if one is healthy
        with cls._pool_lock:
            while cls._pool[db_path]:
                conn = cls._pool[db_path].pop()
                try:
                    conn.execute("SELECT 1")
                    conn.row_factory = sqlite3.Row
                    return conn
                except sqlite3.Error:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    continue

        #Create a fresh connection
        conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            timeout=30.0,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA cache_size = 10000")
        return conn

    @classmethod
    def return_connection(cls, conn):
        #Return a connection to the pool
        if conn is None:
            return
        try:
            try:
                if current_app:
                    db_path = current_app.config.get(
                        'DB_PATH', config.DB_PATH)
                else:
                    db_path = config.DB_PATH
            except RuntimeError:
                db_path = config.DB_PATH

            with cls._pool_lock:
                if db_path not in cls._pool:
                    cls._pool[db_path] = []
                if len(cls._pool[db_path]) < cls._max_pool_size:
                    cls._pool[db_path].append(conn)
                else:
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    @classmethod
    def close_all(cls):
        with cls._pool_lock:
            for db_path, connections in cls._pool.items():
                for conn in connections:
                    try:
                        conn.close()
                    except Exception:
                        pass
                cls._pool[db_path] = []
            cls._pool.clear()

    @classmethod
    def get_pool_size(cls, db_path=None):
        if db_path is None:
            try:
                if current_app:
                    db_path = current_app.config.get(
                        'DB_PATH', config.DB_PATH)
                else:
                    db_path = config.DB_PATH
            except RuntimeError:
                db_path = config.DB_PATH
        with cls._pool_lock:
            return len(cls._pool.get(db_path, []))


def get_db():

    if has_request_context():
        if 'db' not in g:
            g.db = DatabaseConnection.get_connection()
        return g.db

    return DatabaseConnection.get_connection()


def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        DatabaseConnection.return_connection(db)


def init_db():

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='users'"
    )
    if not cursor.fetchone():
        print("[init_db] Schema not ready — skipping seed")
        DatabaseConnection.return_connection(db)
        return

    # Seed admin
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        import bcrypt
        ph = bcrypt.hashpw(
            'admin123'.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')
        cursor.execute(
            """INSERT INTO users
               (username, password_hash, full_name, email, role, is_active)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('admin', ph, 'Administrator', 'admin@store.com', 'owner', 1)
        )
        print("[init_db] Admin user created: admin / admin123")

    # Seed cashier
    cursor.execute("SELECT id FROM users WHERE username = 'cashier'")
    if not cursor.fetchone():
        import bcrypt
        ph = bcrypt.hashpw(
            'cashier123'.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')
        cursor.execute(
            """INSERT INTO users
               (username, password_hash, full_name, email, role, is_active)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('cashier', ph, 'Cashier User',
             'cashier@store.com', 'cashier', 1)
        )
        print("[init_db] Cashier user created: cashier / cashier123")

    # Seed general category
    cursor.execute("SELECT id FROM categories WHERE name = 'General'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO categories (name, description) VALUES (?, ?)",
            ('General', 'Default category for products')
        )

    # Seed stock types
    cursor.execute("SELECT COUNT(*) FROM stock_types")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO stock_types "
            "(name, icon, color, description) VALUES (?, ?, ?, ?)",
            [
                ('regular',     'fas fa-box',   '#2d6a4f',
                 'Regular stock items'),
                ('premium',     'fas fa-crown', '#ffb703',
                 'Premium quality items'),
                ('discount',    'fas fa-tag',   '#dc3545',
                 'Discounted items'),
                ('new_arrival', 'fas fa-star',  '#0d6efd',
                 'Newly arrived items'),
                ('limited',     'fas fa-clock', '#6f42c1',
                 'Limited quantity items'),
            ]
        )

    DatabaseConnection.return_connection(db)
    print("[init_db] Database seeded successfully")


@contextmanager
def transaction():
    """
    Atomic transaction context manager.

    Guarantees:
      - BEGIN IMMEDIATE is executed before any writes.
      - On any failure (including BEGIN failure), rollback is attempted.
      - The connection is returned to the pool in a clean state.
      - If rollback itself fails, the connection is closed rather than
        reused in a broken state.
    """
    db = get_db()
    began = False

    try:
        cursor = db.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        began = True

        try:
            yield db
            db.commit()
        except Exception:
            # Rollback the transaction. If rollback itself fails,
            # close the connection so it can't poison the pool.
            try:
                db.rollback()
            except Exception:
                try:
                    db.close()
                except Exception:
                    pass
            raise

    except Exception:
        # BEGIN itself failed, or something outside the inner try.
        # Only roll back if BEGIN actually started.
        if began:
            try:
                db.rollback()
            except Exception:
                try:
                    db.close()
                except Exception:
                    pass
        raise

    finally:
        if not has_request_context():
            DatabaseConnection.return_connection(db)


def cleanup_database_pool():
    DatabaseConnection.close_all()
