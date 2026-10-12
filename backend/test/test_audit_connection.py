"""
Test that record_audit() does not corrupt the connection pool
or the enclosing transaction.

Semantics:
  - Inside a request context: record_audit uses the request-scoped
    connection and participates in the enclosing transaction.
  - Outside a request: record_audit uses its own connection.
  - It never raises, even on DB failures.
"""
import pytest


class TestRecordAuditOwnConnection:

    def test_record_audit_uses_request_connection(self, app):
        """
        Inside a request context, record_audit should use g.db,
        not a fresh connection from the pool.
        """
        from flask import g
        from backend.api.v1.routes.audit import record_audit
        from backend.database.connection import get_db

        with app.app_context():
            request_conn = get_db()
            assert request_conn is not None
            g_db_before = g.db

            record_audit(
                action='TEST_ACTION',
                category='system',
                details='test row',
                ip_address='127.0.0.1',
            )

            # g.db should be unchanged
            assert g.db is g_db_before

    def test_record_audit_rolls_back_with_parent(self, app, db):
        """
        If record_audit is called inside a transaction that rolls
        back, the audit row must also roll back.
        """
        from backend.api.v1.routes.audit import record_audit
        from backend.database.connection import transaction

        with app.app_context():
            before = db.execute(
                "SELECT COUNT(*) AS n FROM audit_logs "
                "WHERE action = 'TEST_ROLLBACK_ACTION'"
            ).fetchone()['n']

            with pytest.raises(ValueError):
                with transaction():
                    record_audit(
                        action='TEST_ROLLBACK_ACTION',
                        category='system',
                        details='should roll back with parent',
                    )
                    raise ValueError("force rollback")

            after = db.execute(
                "SELECT COUNT(*) AS n FROM audit_logs "
                "WHERE action = 'TEST_ROLLBACK_ACTION'"
            ).fetchone()['n']

            # The audit row must have rolled back with the parent.
            assert after == before, (
                "record_audit row must roll back with parent transaction"
            )

    def test_record_audit_never_raises_on_db_failure(self, app):
        """Even if the DB is broken, record_audit must not raise."""
        from unittest.mock import patch
        from backend.api.v1.routes.audit import record_audit
        from backend.database import connection as conn_module

        with app.app_context():
            def boom(*a, **kw):
                raise RuntimeError("simulated DB failure")

            with patch.object(
                conn_module.DatabaseConnection,
                'get_connection',
                staticmethod(boom),
            ):
                # Must not raise
                record_audit(
                    action='TEST_FAILURE',
                    details='this should be swallowed',
                )
