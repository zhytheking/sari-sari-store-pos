/**
 * api-client.js — CANONICAL API + UTILITY FILE
 *
 * Do not redefine any function from this file elsewhere.
 */

const API_BASE_URL = window.location.origin + '/api/v1';

try { localStorage.removeItem('access_token'); } catch (e) {}
try { localStorage.removeItem('refresh_token'); } catch (e) {}
try { localStorage.removeItem('user_role'); } catch (e) {}


/* ============================================
   COOKIE + CSRF
   ============================================ */

function _getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
}

function getCsrfToken() {
    return _getCookie('csrf_access_token');
}


/* ============================================
   SAFE VALUE HELPERS
   ============================================ */

function safeStr(v) {
    return (v === null || v === undefined) ? '' : String(v);
}

function safeNum(v) {
    const n = Number(v);
    return isNaN(n) ? 0 : n;
}


/* ============================================
   API OBJECT
   ============================================ */

const API = {
    baseURL: API_BASE_URL,

    getHeaders() {
        return { 'Content-Type': 'application/json' };
    },

    getStateChangingHeaders() {
        const headers = this.getHeaders();
        const csrf = getCsrfToken();
        if (csrf) headers['X-CSRF-TOKEN'] = csrf;
        return headers;
    },

    async handleResponse(response, options = {}) {
        const skipAuthRedirect = options.skipAuthRedirect === true;

        if (!response.ok) {
            let errorMessage = `HTTP ${response.status}`;
            try {
                const data = await response.json();
                errorMessage = data.message || data.error || errorMessage;
            } catch (e) {
                try {
                    const text = await response.text();
                    if (text) errorMessage = text;
                } catch (e2) { /* ignore */ }
            }

            if (!skipAuthRedirect
                && (response.status === 401 || response.status === 422)) {
                if (!window.location.pathname.includes('/login')) {
                    window.location.replace('/login');
                }
            }
            throw new Error(errorMessage);
        }
        return response.json();
    },

    async get(endpoint, options = {}) {
        const response = await fetch(`${this.baseURL}${endpoint}`, {
            method: 'GET',
            credentials: 'same-origin',
            headers: this.getHeaders()
        });
        return this.handleResponse(response, options);
    },

    async post(endpoint, data) {
        const response = await fetch(`${this.baseURL}${endpoint}`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: this.getStateChangingHeaders(),
            body: JSON.stringify(data)
        });
        return this.handleResponse(response);
    },

    async put(endpoint, data) {
        const response = await fetch(`${this.baseURL}${endpoint}`, {
            method: 'PUT',
            credentials: 'same-origin',
            headers: this.getStateChangingHeaders(),
            body: JSON.stringify(data)
        });
        return this.handleResponse(response);
    },

    async delete(endpoint) {
        const response = await fetch(`${this.baseURL}${endpoint}`, {
            method: 'DELETE',
            credentials: 'same-origin',
            headers: this.getStateChangingHeaders()
        });
        return this.handleResponse(response);
    },

    auth: {
        login: (u, p, r = 'owner') => API.post(
            '/auth/login',
            { username: u, password: p, role: r }
        ),
        logout: () => API.post('/auth/logout', {}),
        me: () => API.get('/auth/me'),
        refresh: () => API.post('/auth/refresh', {}),
        changePassword: (o, n) => API.post(
            '/auth/change-password',
            { old_password: o, new_password: n }
        ),
        listUsers: (params = {}) => {
            const p = Object.assign({ per_page: 200 }, params);
            const q = new URLSearchParams(p).toString();
            return API.get(`/auth/users${q ? '?' + q : ''}`);
        }
    },

    products: {
        list: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return API.get(`/products${q ? '?' + q : ''}`);
        },
        get: (id) => API.get(`/products/${id}`),
        create: (d) => API.post('/products', d),
        update: (id, d) => API.put(`/products/${id}`, d),
        delete: (id) => API.delete(`/products/${id}`),
        search: (q) => API.get(
            `/products/search?q=${encodeURIComponent(q)}`),
        barcode: (b) => API.get(`/products/barcode/${b}`),
        generateBarcode: (id) => API.post(
            `/products/${id}/generate-barcode`, {}),
        reactivate: (id) => API.post(`/products/${id}/reactivate`, {}),
        categories: {
            list: () => API.get('/products/categories'),
            create: (d) => API.post('/products/categories', d),
            delete: (id) => API.delete(`/products/categories/${id}`)
        },
        stockTypes: {
            list: () => API.get('/products/stock-types'),
            create: (d) => API.post('/products/stock-types', d),
            delete: (id) => API.delete(`/products/stock-types/${id}`)
        }
    },

    sales: {
        list: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return API.get(`/sales${q ? '?' + q : ''}`);
        },
        get: (id) => API.get(`/sales/${id}`),
        create: (d) => API.post('/sales', d),
        void: (id, reason) => API.post(`/sales/${id}/void`, { reason }),
        receipt: (id) => API.get(`/sales/${id}/receipt`),
        stats: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return API.get(`/sales/stats${q ? '?' + q : ''}`);
        },
        mySales: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return API.get(`/sales/my-sales${q ? '?' + q : ''}`);
        },
        allSales: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return API.get(`/sales/all-sales${q ? '?' + q : ''}`);
        }
    },

    inventory: {
        transfer: (d) => API.post('/inventory/transfer', d),
        history: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return API.get(`/inventory/history${q ? '?' + q : ''}`);
        },
        lowStock: (t = 10) => API.get(
            `/inventory/low-stock?threshold=${t}`),
        stock: (id) => API.get(`/inventory/${id}/stock`),
        summary: () => API.get('/inventory/summary')
    },

    admin: {
        stock: {
            add: (d) => API.post('/admin/stock/add', d),
            remove: (d) => API.post('/admin/stock/remove', d),
            adjust: (d) => API.post('/admin/stock/adjust', d),
            bulkAdd: (d) => API.post('/admin/stock/bulk-add', d),
            history: (params = {}) => {
                const q = new URLSearchParams(params).toString();
                return API.get(`/admin/stock/history${q ? '?' + q : ''}`);
            },
            summary: () => API.get('/admin/stock/summary')
        },
        settings: {
            get: () => API.get('/admin/settings'),
            update: (s) => API.put('/admin/settings', { settings: s }),
            uploadGcashQr: (formData) => {
                const h = {};
                const csrf = getCsrfToken();
                if (csrf) h['X-CSRF-TOKEN'] = csrf;
                return fetch(`${API.baseURL}/admin/settings/gcash-qr`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: h,
                    body: formData
                }).then(function (r) {
                    return r.json().then(function (body) {
                        if (!r.ok) {
                            throw new Error(
                                (body && body.message) || ('HTTP ' + r.status)
                            );
                        }
                        return body;
                    });
                });
            },
            getGcashQr: () => API.get('/admin/settings/gcash-qr'),
            removeGcashQr: () => API.delete('/admin/settings/gcash-qr')
        },
        users: {
            changePassword: (id, np) => API.post(
                `/admin/users/${id}/change-password`,
                { new_password: np }
            )
        },
        profile: {
            changePassword: (o, n) => API.post(
                '/admin/profile/change-password',
                { old_password: o, new_password: n }
            )
        }
    },

    settings: {
        public: () => API.get('/settings/public'),
        publicNoAuth: () => API.get('/settings/public-no-auth'),
        gcashQr: () => API.get('/settings/gcash-qr')
    },

    reports: {
        sales: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return API.get(`/reports/sales${q ? '?' + q : ''}`);
        },
        products: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return API.get(`/reports/products${q ? '?' + q : ''}`);
        },
        inventory: () => API.get('/reports/inventory'),
        daily: (d = null) => API.get(
            `/reports/daily${d ? '?date=' + d : ''}`),
        profit: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return API.get(`/reports/profit${q ? '?' + q : ''}`);
        },
        analytics: () => API.get('/reports/analytics'),

        exportAllSalesUrl: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return `${API.baseURL}/reports/export/all-sales${q ? '?' + q : ''}`;
        },
        exportMySalesUrl: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return `${API.baseURL}/reports/export/my-sales${q ? '?' + q : ''}`;
        }
    },

    audit: {
        logs: (params = {}) => {
            const q = new URLSearchParams(params).toString();
            return API.get(`/audit/logs${q ? '?' + q : ''}`);
        },
        get: (id) => API.get(`/audit/logs/${id}`),
        summary: () => API.get('/audit/summary')
    }
};


/* ============================================
   HTML / FORMAT HELPERS
   ============================================ */

const _HTML_ESCAPE_MAP = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
};

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text).replace(/[&<>"']/g, ch => _HTML_ESCAPE_MAP[ch]);
}

function formatCurrency(amount) {
    const n = Number(amount) || 0;
    return `₱${n.toFixed(2)}`;
}


/* ============================================
   DATE / TIME
   ============================================ */

function _parseServerDate(dateString) {
    if (!dateString) return null;
    let s = String(dateString).trim();
    if (!s) return null;
    s = s.replace(' ', 'T');
    const hasTz = /Z$/i.test(s) || /[+-]\d{2}:\d{2}$/.test(s);
    if (!hasTz) s += 'Z';
    const d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
}

function formatDate(dateString) {
    const d = _parseServerDate(dateString);
    if (!d) return '';
    return d.toLocaleString('en-PH', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });
}

function formatDateOnly(dateString) {
    const d = _parseServerDate(dateString);
    if (!d) return '';
    return d.toLocaleDateString('en-PH', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    });
}

function formatTimeOnly(dateString) {
    const d = _parseServerDate(dateString);
    if (!d) return '';
    return d.toLocaleTimeString('en-PH', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });
}

function formatRelativeTime(dateString) {
    const date = _parseServerDate(dateString);
    if (!date) return '';
    const now = new Date();
    const diffSec = Math.floor((now - date) / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);

    if (diffSec < 10) return 'just now';
    if (diffSec < 60) return `${diffSec} sec ago`;
    if (diffMin < 60) return `${diffMin} min ago`;
    if (diffHr < 24) return `${diffHr} hr ago`;
    if (diffDay === 1) return 'yesterday';
    if (diffDay < 7) return `${diffDay} days ago`;
    if (diffDay < 30) return `${Math.floor(diffDay / 7)} wk ago`;
    return date.toLocaleDateString('en-PH', {
        month: 'short', day: 'numeric', year: 'numeric'
    });
}

function renderRelativeTime(dateString) {
    const txt = formatRelativeTime(dateString);
    if (txt === 'just now') {
        return `<span class="relative-time fresh">
                    <span class="relative-dot"></span>just now
                </span>`;
    }
    if (txt.includes('min ago') || txt.includes('sec ago')) {
        return `<span class="relative-time recent">${txt}</span>`;
    }
    return `<span class="relative-time">${txt}</span>`;
}

function refreshRelativeTimes() {
    document.querySelectorAll('[data-timestamp]').forEach(el => {
        const raw = el.getAttribute('data-timestamp');
        if (!raw) return;
        const fresh = renderRelativeTime(raw);
        const existing = el.querySelector('.relative-time');
        if (existing) {
            existing.outerHTML = fresh;
        } else {
            el.insertAdjacentHTML('beforeend', ' ' + fresh);
        }
    });
}


/* ============================================
   TOASTS
   ============================================ */

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) {
        const c = document.createElement('div');
        c.id = 'toastContainer';
        c.className = 'toast-container';
        document.body.appendChild(c);
        return showToast(message, type);
    }

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="fas ${icons[type] || icons.info}"></i>
        <span>${escapeHtml(message)}</span>
        <button type="button" aria-label="Close">
            <i class="fas fa-times"></i>
        </button>
    `;
    toast.querySelector('button').addEventListener('click', () => {
        if (toast.parentElement) toast.remove();
    });
    container.appendChild(toast);

    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.animation = 'slideOut 0.3s ease forwards';
            setTimeout(() => {
                if (toast.parentElement) toast.remove();
            }, 300);
        }
    }, 5000);
}


/* ============================================
   MISC HELPERS
   ============================================ */

function debounce(fn, ms) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}

function throttle(fn, ms) {
    let last = 0;
    return function (...args) {
        const now = Date.now();
        if (now - last >= ms) {
            last = now;
            fn.apply(this, args);
        }
    };
}

function showLoading(message = 'Loading...') {
    const overlay = document.getElementById('loadingOverlay');
    const messageEl = document.getElementById('loadingMessage');
    if (overlay) {
        overlay.style.display = 'flex';
        if (messageEl) messageEl.textContent = message;
    }
}

function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.style.display = 'none';
}

function getCart() {
    try {
        return JSON.parse(localStorage.getItem('cart') || '[]');
    } catch (e) {
        return [];
    }
}

function saveCart(cart) {
    localStorage.setItem('cart', JSON.stringify(cart));
    updateCartBadge();
}

function updateCartBadge() {
    const cart = getCart();
    const total = cart.reduce((sum, item) => sum + (item.quantity || 0), 0);
    const badge = document.getElementById('cartCount');
    if (badge) badge.textContent = total;
}


/* ============================================
   LOGOUT
   ============================================ */

async function logoutUser(event) {
    if (event) event.preventDefault();
    if (!confirm('Are you sure you want to logout?')) return;

    const logoutBtn = document.getElementById('logoutNavLink');
    if (logoutBtn) {
        logoutBtn.innerHTML =
            '<i class="fas fa-spinner fa-spin"></i> Logging out...';
        logoutBtn.style.pointerEvents = 'none';
    }

    try {
        await fetch('/api/auth/logout', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' }
        });
    } catch (err) {
        console.warn('[Logout] Network error:', err);
    }

    try { sessionStorage.removeItem('checkoutCart'); } catch (e) {}

    setTimeout(() => {
        window.location.replace('/');
    }, 300);
}


/* ============================================
   MOBILE NAV
   ============================================ */

function toggleMenu() {
    const navLinks = document.getElementById('navLinks');
    if (navLinks) navLinks.classList.toggle('active');
}


/* ============================================
   LOGIN PAGE — AUTOFILL KILLER
   ============================================ */

function clearAutofilledFields() {
    const username = document.getElementById('loginUsername');
    const password = document.getElementById('loginPassword');
    if (!username || !password) return;

    function clearFields() {
        if (username.value !== '') username.value = '';
        if (password.value !== '') password.value = '';
    }

    clearFields();
    setTimeout(clearFields, 50);
    setTimeout(clearFields, 200);

    username.addEventListener('focus', function () {
        if (this.value !== '') this.value = '';
    });
    password.addEventListener('focus', function () {
        if (this.value !== '') this.value = '';
    });
}


/* ============================================
   BOOT
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
    refreshRelativeTimes();
    setInterval(refreshRelativeTimes, 30000);
    updateCartBadge();

    if (document.getElementById('loginUsername')) {
        clearAutofilledFields();
    }
});
