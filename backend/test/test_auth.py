import time
import bcrypt
import pytest


# ═══════
# LOGIN
# ═══════

class TestLoginSuccess:
    """Happy-path login."""

    def test_owner_login_returns_tokens(self, client):
        resp = client.post('/api/v1/auth/login', json={
            'username': 'admin',
            'password': 'admin123',
            'role': 'owner',
        })
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert data['success'] is True
        assert 'access_token' in data['data']
        assert 'refresh_token' in data['data']
        assert data['data']['user']['role'] == 'owner'
        assert data['data']['user']['username'] == 'admin'

    def test_owner_login_sets_cookies(self, client):
        resp = client.post('/api/v1/auth/login', json={
            'username': 'admin',
            'password': 'admin123',
            'role': 'owner',
        })
        # The response should include Set-Cookie headers
        cookies = resp.headers.getlist('Set-Cookie')
        assert any('access_token' in c for c in cookies)
        assert any('refresh_token' in c for c in cookies)

    def test_cashier_login_returns_cashier_role(self, client, owner_headers):
        # Create the cashier via register
        client.post('/api/v1/auth/register', headers=owner_headers, json={
            'username': 'kassier',
            'password': 'Cashier123',
            'full_name': 'Kassier Test',
            'email': 'kassier@test.local',
            'role': 'cashier',
        })

        resp = client.post('/api/v1/auth/login', json={
            'username': 'kassier',
            'password': 'Cashier123',
            'role': 'cashier',
        })
        assert resp.status_code == 200
        assert resp.get_json()['data']['user']['role'] == 'cashier'


class TestLoginFailure:
    #Bad credentials, wrong role, inactive accounts

    def test_wrong_password_returns_401(self, client):
        resp = client.post('/api/v1/auth/login', json={
            'username': 'admin',
            'password': 'wrong_password',
            'role': 'owner',
        })
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['error'] == 'authentication_failed'
        # Should include remaining attempts
        assert 'attempts_remaining' in data or 'message' in data

    def test_unknown_user_returns_401(self, client):
        resp = client.post('/api/v1/auth/login', json={
            'username': 'nobody_here_xyz',
            'password': 'whatever',
            'role': 'owner',
        })
        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'authentication_failed'

    def test_missing_fields_returns_400(self, client):
        resp = client.post('/api/v1/auth/login', json={
            'username': '',
            'password': '',
        })
        assert resp.status_code == 400

    def test_cashier_with_owner_role_returns_403(
        self, client, owner_headers
    ):
        # Create cashier
        client.post('/api/v1/auth/register', headers=owner_headers, json={
            'username': 'kassier2',
            'password': 'Cashier123',
            'full_name': 'Kassier Two',
            'email': 'kassier2@test.local',
            'role': 'cashier',
        })

        # Try to log in with owner role
        resp = client.post('/api/v1/auth/login', json={
            'username': 'kassier2',
            'password': 'Cashier123',
            'role': 'owner',
        })
        assert resp.status_code == 403
        assert resp.get_json()['error'] == 'role_mismatch'


# ════════
# LOCKOUT
# ════════

class TestLockout:
    """Failed-attempt lockout. Global threshold, no enumeration."""

    def test_lockout_after_five_failed_attempts(self, client, db):
        """
        Five wrong passwords lock the account. The 6th returns
        account_locked, even with the correct password.
        """
        # Create a dedicated user so we don't lock out the shared admin
        pwd_hash = bcrypt.hashpw(b'correct_pass', bcrypt.gensalt()).decode()
        db.execute(
            """INSERT INTO users (username, password_hash, full_name, role, is_active)
               VALUES (?, ?, ?, ?, ?)""",
            ('lockout_test', pwd_hash, 'Lockout Test', 'owner', 1),
        )
        db.commit()

        # Five wrong attempts
        for i in range(5):
            r = client.post('/api/v1/auth/login', json={
                'username': 'lockout_test',
                'password': 'wrong',
                'role': 'owner',
            })
            # First 4 should be 401 with attempts_remaining
            if i < 4:
                assert r.status_code == 401, (
                    f"Attempt {i+1} expected 401, got {r.status_code}: {r.get_json()}"
                )

        # The 5th should have locked it. Check the 6th is locked.
        r = client.post('/api/v1/auth/login', json={
            'username': 'lockout_test',
            'password': 'wrong',
            'role': 'owner',
        })
        assert r.status_code == 403
        data = r.get_json()
        assert data['error'] == 'account_locked'
        assert 'remaining_minutes' in data

    def test_locked_account_rejects_correct_password(self, client, db):
       
        #Even the correct password is rejected while the account is locked.
        
        pwd_hash = bcrypt.hashpw(b'correct_pass', bcrypt.gensalt()).decode()
        db.execute(
            """INSERT INTO users (username, password_hash, full_name, role, is_active)
               VALUES (?, ?, ?, ?, ?)""",
            ('lockout_test2', pwd_hash, 'Lockout Two', 'owner', 1),
        )
        db.commit()

        # Lock it
        for _ in range(5):
            client.post('/api/v1/auth/login', json={
                'username': 'lockout_test2',
                'password': 'wrong',
                'role': 'owner',
            })

        # Correct password should still be rejected
        r = client.post('/api/v1/auth/login', json={
            'username': 'lockout_test2',
            'password': 'correct_pass',
            'role': 'owner',
        })
        assert r.status_code == 403
        assert r.get_json()['error'] == 'account_locked'


# ═════════
# REGISTER
# ═════════

class TestRegister:
    #Owner-only user creation

    def test_owner_can_register_cashier(self, client, owner_headers):
        resp = client.post('/api/v1/auth/register', headers=owner_headers, json={
            'username': 'newcashier',
            'password': 'Cashier123',
            'full_name': 'New Cashier',
            'email': 'newcashier@test.local',
            'role': 'cashier',
        })
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()['data']
        assert data['username'] == 'newcashier'
        assert data['role'] == 'cashier'
        assert data['is_active'] is True

    def test_cashier_cannot_register(self, client, cashier_headers):
        resp = client.post('/api/v1/auth/register', headers=cashier_headers, json={
            'username': 'someone_else',
            'password': 'Password123',
            'full_name': 'Someone Else',
            'email': 'someone@test.local',
            'role': 'cashier',
        })
        assert resp.status_code == 403

    def test_register_without_token_returns_401(self, client):
        resp = client.post('/api/v1/auth/register', json={
            'username': 'anon',
            'password': 'Password123',
            'full_name': 'Anon User',
            'email': 'anon@test.local',
            'role': 'cashier',
        })
        assert resp.status_code == 401

    def test_register_weak_password_rejected(self, client, owner_headers):
        resp = client.post('/api/v1/auth/register', headers=owner_headers, json={
            'username': 'weakling',
            'password': 'short',
            'full_name': 'Weak Password',
            'email': 'weak@test.local',
            'role': 'cashier',
        })
        assert resp.status_code == 400

    def test_register_duplicate_username_returns_409(
        self, client, owner_headers
    ):
        # First creation succeeds
        r1 = client.post('/api/v1/auth/register', headers=owner_headers, json={
            'username': 'duplicate',
            'password': 'Password123',
            'full_name': 'Dup One',
            'email': 'dup1@test.local',
            'role': 'cashier',
        })
        assert r1.status_code == 201

        # Second should fail
        r2 = client.post('/api/v1/auth/register', headers=owner_headers, json={
            'username': 'duplicate',
            'password': 'Password123',
            'full_name': 'Dup Two',
            'email': 'dup2@test.local',
            'role': 'cashier',
        })
        assert r2.status_code == 409
        assert r2.get_json()['error'] == 'user_exists'


# ═════════════
# CURRENT USER
# ═════════════

class TestMe:
    def test_me_requires_auth(self, client):
        resp = client.get('/api/v1/auth/me')
        assert resp.status_code == 401

    def test_me_returns_current_user(self, client, owner_headers):
        resp = client.get('/api/v1/auth/me', headers=owner_headers)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['username'] == 'admin'
        assert data['role'] == 'owner'


# ═══════════════
# CHANGE PASSWORD
# ═══════════════

class TestChangePassword:
    def test_change_password_success(self, client, cashier_headers, owner_headers):
        # Create a fresh cashier
        client.post('/api/v1/auth/register', headers=owner_headers, json={
            'username': 'pwdchanger',
            'password': 'OldPass123',
            'full_name': 'Password Changer',
            'email': 'pwd@test.local',
            'role': 'cashier',
        })
        login = client.post('/api/v1/auth/login', json={
            'username': 'pwdchanger',
            'password': 'OldPass123',
            'role': 'cashier',
        })
        assert login.status_code == 200
        token = login.get_json()['data']['access_token']
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        resp = client.post('/api/v1/auth/change-password', headers=headers, json={
            'old_password': 'OldPass123',
            'new_password': 'NewPass456',
        })
        assert resp.status_code == 200

        # Old password no longer works
        r = client.post('/api/v1/auth/login', json={
            'username': 'pwdchanger',
            'password': 'OldPass123',
            'role': 'cashier',
        })
        assert r.status_code == 401

        # New password works
        r = client.post('/api/v1/auth/login', json={
            'username': 'pwdchanger',
            'password': 'NewPass456',
            'role': 'cashier',
        })
        assert r.status_code == 200

    def test_change_password_wrong_old(self, client, owner_headers):
        resp = client.post('/api/v1/auth/change-password',
                           headers=owner_headers, json={
            'old_password': 'wrong_old',
            'new_password': 'NewPass456',
        })
        assert resp.status_code == 401

    def test_change_password_weak_new(self, client, owner_headers):
        resp = client.post('/api/v1/auth/change-password',
                           headers=owner_headers, json={
            'old_password': 'admin123',
            'new_password': 'short',
        })
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════
# STALE TOKEN
# ═══════════════════════════════════════════════════════════════

class TestStaleToken:
    """
    After a password change, tokens issued before the change must
    be rejected with code='token_stale'.
    """

    def test_token_stale_after_password_change(
        self, client, owner_headers, db
    ):
        # Create a user, log in, capture the token
        client.post('/api/v1/auth/register', headers=owner_headers, json={
            'username': 'stale_test',
            'password': 'OldPass123',
            'full_name': 'Stale User',
            'email': 'stale@test.local',
            'role': 'cashier',
        })

        login = client.post('/api/v1/auth/login', json={
            'username': 'stale_test',
            'password': 'OldPass123',
            'role': 'cashier',
        })
        assert login.status_code == 200
        old_token = login.get_json()['data']['access_token']
        old_headers = {
            'Authorization': f'Bearer {old_token}',
            'Content-Type': 'application/json',
        }

        # Confirm the token works
        r = client.get('/api/v1/auth/me', headers=old_headers)
        assert r.status_code == 200

        # Now change the password
        r = client.post('/api/v1/auth/change-password',
                        headers=old_headers, json={
            'old_password': 'OldPass123',
            'new_password': 'NewPass456',
        })
        assert r.status_code == 200

        # Give the DB a moment to persist the password_changed_at
        time.sleep(0.1)

        # Now the old token should be rejected
        r = client.get('/api/v1/auth/me', headers=old_headers)
        assert r.status_code == 401
        assert r.get_json()['error'] == 'token_stale'


# ══════════════════
# ROLE ENFORCEMENT
# ══════════════════
class TestRoleEnforcement:

    def test_cashier_cannot_list_users(self, client, cashier_headers):
        r = client.get('/api/v1/auth/users', headers=cashier_headers)
        assert r.status_code == 403

    def test_owner_can_list_users(self, client, owner_headers):
        r = client.get('/api/v1/auth/users', headers=owner_headers)
        assert r.status_code == 200

    def test_cashier_cannot_create_product(self, client, cashier_headers):
        r = client.post('/api/v1/products', headers=cashier_headers, json={
            'name': 'Test Product',
            'purchase_price': 10,
            'selling_price': 20,
        })
        assert r.status_code == 403


# ════════════
# DEACTIVATION
# ════════════

class TestDeactivation:
    def test_deactivated_user_token_rejected(
        self, client, owner_headers, db
    ):
        # Create a cashier
        client.post('/api/v1/auth/register', headers=owner_headers, json={
            'username': 'deact_test',
            'password': 'Deact123',
            'full_name': 'Deactivate Me',
            'email': 'deact@test.local',
            'role': 'cashier',
        })

        # Log in
        login = client.post('/api/v1/auth/login', json={
            'username': 'deact_test',
            'password': 'Deact123',
            'role': 'cashier',
        })
        assert login.status_code == 200
        token = login.get_json()['data']['access_token']
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

        # Token works
        r = client.get('/api/v1/auth/me', headers=headers)
        assert r.status_code == 200

        # Deactivate the user directly in the DB
        db.execute(
            "UPDATE users SET is_active = 0 WHERE username = 'deact_test'"
        )
        db.commit()

        # Token now rejected
        r = client.get('/api/v1/auth/me', headers=headers)
        assert r.status_code == 401
        assert r.get_json()['error'] == 'account_inactive'
