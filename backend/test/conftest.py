import os
import sys
import sqlite3
import tempfile
from pathlib import Path

import pytest

# ── Path setup ──────────────────────────────────────────────
TEST_DIR = Path(__file__).resolve().parent      # backend/test/
BACKEND_DIR = TEST_DIR.parent                   # backend/
PROJECT_ROOT = BACKEND_DIR.parent               # project root

for _p in (str(PROJECT_ROOT), str(BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bcrypt as _bcrypt_module

_ORIGINAL_GENSALT = _bcrypt_module.gensalt
_TEST_BCRYPT_ROUNDS = 4


def _fast_gensalt(rounds=_TEST_BCRYPT_ROUNDS, prefix=b'2b'):
    #Force bcrypt to use the minimum cost during tests
    return _ORIGINAL_GENSALT(rounds=_TEST_BCRYPT_ROUNDS, prefix=prefix)


_bcrypt_module.gensalt = _fast_gensalt


# ════════════════════════════════════════════════════════════
# PERFORMANCE PATCH: cache the dummy hash used by login lockout
# ════════════════════════════════════════════════════════════

# ══════════════════
# APP + DB FIXTURES
# ══════════════════

@pytest.fixture(scope='function')
def app():
    """
    Fresh Flask app + temp SQLite DB for each test.

    Uses a temp file (not :memory:) so migrations and pooling
    behave identically to production.
    """
    fd, db_path = tempfile.mkstemp(suffix='.db', prefix='pos_test_')
    os.close(fd)

    # Env vars must be set BEFORE the config module imports
    os.environ['APP_ENV'] = 'testing'
    os.environ['DB_PATH'] = db_path
    os.environ['SECRET_KEY'] = 'test-secret-do-not-use-in-prod'
    os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-do-not-use-in-prod'
    os.environ['RATELIMIT_ENABLED'] = 'False'

    # Drop pooled connections from the previous test
    try:
        from database.connection import cleanup_database_pool
        cleanup_database_pool()
    except Exception:
        pass

    from config import TestingConfig
    TestingConfig.DB_PATH = db_path

    from app import create_app
    flask_app = create_app(TestingConfig())
    flask_app.config['TESTING'] = True

    with flask_app.app_context():
        try:
            from database.migrations import migration_manager
            result = migration_manager.migrate()
            if result.get('errors'):
                raise RuntimeError(
                    f"Migrations failed on temp DB:\n"
                    f"  applied: {result.get('applied')}\n"
                    f"  errors:  {result.get('errors')}\n"
                    f"  db:      {db_path}"
                )
        except ImportError:
            pass

        from database.connection import init_db
        try:
            init_db()
        except Exception:
            pass

    yield flask_app

    try:
        from database.connection import cleanup_database_pool
        cleanup_database_pool()
    except Exception:
        pass

    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture(scope='function')
def client(app):
    #Flask test client
    return app.test_client()


@pytest.fixture(scope='function')
def db(app):
    #Raw sqlite3 connection to the same temp DB (read-only)
    conn = sqlite3.connect(app.config['DB_PATH'])
    conn.row_factory = sqlite3.Row
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ══════════════
# AUTH FIXTURES
# ══════════════

@pytest.fixture(scope='function')
def owner_token(client):
    #Access token for the seeded owner (admin / admin123)
    resp = client.post('/api/v1/auth/login', json={
        'username': 'admin',
        'password': 'admin123',
        'role': 'owner'
    })
    assert resp.status_code == 200, (
        f"Owner login failed: {resp.status_code} {resp.get_json()}"
    )
    return resp.get_json()['data']['access_token']


@pytest.fixture(scope='function')
def owner_headers(owner_token):
    return {
        'Authorization': f'Bearer {owner_token}',
        'Content-Type': 'application/json'
    }


@pytest.fixture(scope='function')
def cashier_token(client, owner_headers):
    
    resp = client.post('/api/v1/auth/register', headers=owner_headers, json={
        'username': 'testcashier',
        'password': 'Cashier123',
        'full_name': 'Test Cashier',
        'email': 'cashier@test.local',
        'role': 'cashier'
    })
    assert resp.status_code == 201, (
        f"Cashier creation failed: {resp.status_code} {resp.get_json()}"
    )

    resp = client.post('/api/v1/auth/login', json={
        'username': 'testcashier',
        'password': 'Cashier123',
        'role': 'cashier'
    })
    assert resp.status_code == 200, (
        f"Cashier login failed: {resp.status_code} {resp.get_json()}"
    )
    return resp.get_json()['data']['access_token']


@pytest.fixture(scope='function')
def cashier_headers(cashier_token):
    return {
        'Authorization': f'Bearer {cashier_token}',
        'Content-Type': 'application/json'
    }


# ══════════════════════
# SAMPLE DATA FIXTURES
# ══════════════════════

@pytest.fixture(scope='function')
def sample_product(client, owner_headers):
    #Create one product and return its JSON representation
    resp = client.post('/api/v1/products', headers=owner_headers, json={
        'name': 'Test Product',
        'description': 'A test product',
        'barcode': '1000000000001',
        'purchase_price': 50.00,
        'selling_price': 75.00,
        'stock_quantity': 100,
        'min_stock_level': 10,
        'unit': 'pc',
        'tax_rate': 0
    })
    assert resp.status_code == 201, (
        f"Product creation failed: {resp.status_code} {resp.get_json()}"
    )
    return resp.get_json()['data']


@pytest.fixture(scope='function')
def second_product(client, owner_headers):
    #Create a second product for tests that need two
    resp = client.post('/api/v1/products', headers=owner_headers, json={
        'name': 'Second Product',
        'barcode': '1000000000002',
        'purchase_price': 20.00,
        'selling_price': 30.00,
        'stock_quantity': 50,
        'min_stock_level': 5,
        'unit': 'pc',
        'tax_rate': 0
    })
    assert resp.status_code == 201, (
        f"Second product creation failed: {resp.status_code} {resp.get_json()}"
    )
    return resp.get_json()['data']
