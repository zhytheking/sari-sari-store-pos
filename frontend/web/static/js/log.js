/**
 * login.js — Page-specific logic for the login page.
 *
 * Depends on api-client.js:
 *   - API.auth.login, API.settings.publicNoAuth
 *   - escapeHtml, showToast
 *
 * Owns:
 *   - Role-from-URL parsing
 *   - Password visibility toggle
 *   - Login form submission
 *   - Error rendering
 */


/* ============================================
   ROLE FROM URL
   ============================================ */

function getRoleFromURL() {
    const params = new URLSearchParams(window.location.search);
    const role = params.get('role') || 'owner';
    return (role === 'cashier') ? 'cashier' : 'owner';
}

function updateLoginRoleDisplay() {
    const role = getRoleFromURL();
    const display = document.getElementById('loginRoleDisplay');
    if (!display) return;

    if (role === 'cashier') {
        display.textContent = 'Cashier 🛒';
        display.className = 'role-value cashier';
    } else {
        display.textContent = 'Owner 👑';
        display.className = 'role-value owner';
    }
}


/* ============================================
   PASSWORD TOGGLE
   ============================================ */

function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const btn = input.parentElement.querySelector('.password-toggle');
    const icon = btn ? btn.querySelector('i') : null;

    if (input.type === 'password') {
        input.type = 'text';
        if (icon) icon.className = 'fas fa-eye-slash';
    } else {
        input.type = 'password';
        if (icon) icon.className = 'fas fa-eye';
    }
}


/* ============================================
   MESSAGE HELPERS
   ============================================ */

function shakeCard(card) {
    if (!card) return;
    card.classList.add('shake');
    setTimeout(() => card.classList.remove('shake'), 500);
}

function showFormMessage(message, type) {
    const container = document.getElementById('loginMessage');
    if (!container) return;

    const icon = type === 'success'
        ? 'fa-check-circle'
        : type === 'warning'
            ? 'fa-exclamation-triangle'
            : 'fa-exclamation-circle';

    container.innerHTML = `
        <div class="message ${type}">
            <i class="fas ${icon}"></i>
            <span>${escapeHtml(message)}</span>
        </div>
    `;

    if (type === 'error') {
        setTimeout(() => { container.innerHTML = ''; }, 5000);
    }
}


/* ============================================
   LOGIN ERROR FORMATTER
   ============================================ */

function formatLoginError(data) {
    if (!data) return 'Invalid credentials';
    switch (data.error) {
        case 'role_mismatch':
            return '⚠️ ' + (data.message || 'Wrong role selected');
        case 'account_locked':
            return '🔒 ' + (data.message || 'Account locked');
        case 'account_inactive':
            return '🚫 ' + (data.message || 'Account inactive');
        case 'validation_error':
            return 'Please check your input';
        default:
            return data.message || 'Invalid credentials';
    }
}


/* ============================================
   LOGIN HANDLER
   ============================================ */

async function handleLogin(event) {
    event.preventDefault();

    const username = (document.getElementById('loginUsername').value || '').trim();
    const password = (document.getElementById('loginPassword').value || '').trim();
    const role = getRoleFromURL();
    const loginBtn = document.getElementById('loginBtn');
    const loginCard = document.getElementById('loginCard');

    if (!username || !password) {
        showFormMessage('Please enter both username and password', 'error');
        shakeCard(loginCard);
        return;
    }

    loginBtn.disabled = true;
    loginBtn.innerHTML = '<span class="loading-spinner-small"></span> Logging in...';

    try {
        // Step 1: Authenticate
        const loginResp = await fetch('/api/v1/auth/login', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, role })
        });

        const loginData = await loginResp.json();

        if (!loginResp.ok || !loginData.success) {
            throw new Error(formatLoginError(loginData));
        }

        // Step 2: Verify the cookie works
        const whoResp = await fetch('/api/auth/whoami', {
            credentials: 'same-origin'
        });

        if (!whoResp.ok) {
            throw new Error('Session could not be established. Please try again.');
        }

        const whoData = await whoResp.json();
        const serverRole = whoData.user && whoData.user.role;

        if (serverRole !== 'owner' && serverRole !== 'cashier') {
            throw new Error('Server returned an unexpected role.');
        }

        showFormMessage(
            `✅ Login successful as ${serverRole}! Redirecting...`,
            'success'
        );

        const destination = serverRole === 'owner'
            ? '/admin/dashboard'
            : '/cashier/dashboard';

        window.location.replace(destination);

    } catch (err) {
        console.error('[Login]', err);
        showFormMessage(err.message || 'Login failed', 'error');
        loginBtn.disabled = false;
        loginBtn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Login';
        shakeCard(loginCard);
        const pw = document.getElementById('loginPassword');
        if (pw) {
            pw.value = '';
            pw.focus();
        }
    }
}


/* ============================================
   INIT
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
    updateLoginRoleDisplay();
});
