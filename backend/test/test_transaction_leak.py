"""
Test that the transaction() context manager always cleans up,
even when BEGIN IMMEDIATE itself fails.

sqlite3.Connection and sqlite3.Cursor are C extension types —
their methods cannot be patched with unittest.mock.patch.object.
We inject a Python-level wrapper instead.
"""
import sqlite3

import pytest


class _BeginFailingCursor:
    """Wraps a real cursor and fails on the first BEGIN."""

    def __init__(self, real_cursor):
        self._real = real_cursor
        self._begin_failed_once = False

    def execute(self, sql, *args, **kwargs):
        if (not self._begin_failed_once
                and sql.strip().upper().startswith("BEGIN")):
            self._begin_failed_once = True
            raise sqlite3.OperationalError("database is locked")
        return self._real.execute(sql, *args, **kwargs)

    def fetchone(self):
        return self._real.fetchone()

    def fetchall(self):
        return self._real.fetchall()

    def close(self):
        return self._real.close()

    def __getattr__(self, name):
        return getattr(self._real, name)


class _BeginFailingConnection:
    """Wraps a real connection and hands out wrapped cursors."""

    def __init__(self, real_conn):
        self._real = real_conn

    def cursor(self, *args, **kwargs):
        return _BeginFailingCursor(self._real.cursor(*args, **kwargs))

    def commit(self):
        return self._real.commit()

    def rollback(self):
        return self._real.rollback()

    def close(self):
        return self._real.close()

    def execute(self, sql, *args, **kwargs):
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class TestTransactionCleanup:

    def test_transaction_returns_clean_connection_on_begin_failure(
        self, app, db
    ):
        """
        If BEGIN IMMEDIATE fails, the context manager must propagate
        the exception and not leave the connection broken.
        """
        from backend.database.connection import (
            DatabaseConnection, transaction,
        )

        with app.app_context():
            real_conn = DatabaseConnection.get_connection()
            wrapped = _BeginFailingConnection(real_conn)

            original_get = DatabaseConnection.get_connection
            try:
                DatabaseConnection.get_connection = staticmethod(
                    lambda *a, **kw: wrapped
                )

                with pytest.raises(sqlite3.OperationalError):
                    with transaction():
                        pass  # never reached
            finally:
                DatabaseConnection.get_connection = original_get

            # Connection should still be usable for a fresh transaction.
            with transaction() as tdb:
                tdb.execute("SELECT 1")

    def test_transaction_rolls_back_on_body_failure(self, app):
        """
        A failure inside the transaction body must roll back,
        and the connection must remain usable afterward.
        """
        from backend.database.connection import transaction

        with app.app_context():
            with pytest.raises(ValueError):
                with transaction() as tdb:
                    tdb.execute("SELECT 1")
                    raise ValueError("intentional failure")

            # Connection should still be usable.
            with transaction() as tdb:
                tdb.execute("SELECT 1")
