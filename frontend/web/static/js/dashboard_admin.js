/**
 * dashboard_admin.js — Admin dashboard page logic.
 *
 * Depends on api-client.js.
 *
 * Owns:
 *   - Dashboard stats (products, sales today, low stock, out of stock)
 *   - Recent sales table
 *   - Current date display
 *   - Logged-in admin name
 */


/* ============================================
   SAFE HELPERS
   ============================================ */

function _daSafeStr(v) {
    return (v === null || v === undefined) ? '' : String(v);
}

function _daSafeNum(v) {
    const n = Number(v);
    return isNaN(n) ? 0 : n;
}


/* ============================================
   DATE
   ============================================ */

function _daSetCurrentDate() {
    const el = document.getElementById('currentDate');
    if (!el) return;
    const now = new Date();
    const options = {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    };
    el.textContent = now.toLocaleDateString('en-PH', options);
}


/* ============================================
   STATS
   ============================================ */

function loadAdminStats() {
    // Products + low stock + out of stock
    API.products.list({ per_page: 500 })
        .then(function (data) {
            if (!data || !data.success) return;
            const products = (data.data && data.data.items) || [];
            const total = products.length;

            let lowStock = 0;
            let outOfStock = 0;
            products.forEach(function (p) {
                const stock = _daSafeNum(p.stock_quantity);
                if (stock <= 0) {
                    outOfStock += 1;
                } else if (stock <= 10) {
                    lowStock += 1;
                }
            });

            const totalEl = document.getElementById('totalProducts');
            const lowEl = document.getElementById('lowStockItems');
            const outEl = document.getElementById('outOfStock');

            if (totalEl) totalEl.textContent = total;
            if (lowEl) lowEl.textContent = lowStock;
            if (outEl) outEl.textContent = outOfStock;
        })
        .catch(function (err) {
            console.error('[dashboard_admin] products:', err);
        });

    // Today's sales
    API.sales.stats({ period: 'today' })
        .then(function (data) {
            if (!data || !data.success) return;
            const revenue = _daSafeNum(data.data && data.data.total_revenue);
            const el = document.getElementById('todaySales');
            if (el) el.textContent = `₱${revenue.toFixed(2)}`;
        })
        .catch(function (err) {
            console.error('[dashboard_admin] stats:', err);
        });
}


/* ============================================
   RECENT SALES
   ============================================ */

function loadRecentSales() {
    const container = document.getElementById('recentSalesContainer');
    if (!container) return;

    container.innerHTML = `
        <div class="loading-state">
            <div class="loading-spinner"></div>
            <p>Loading recent sales...</p>
        </div>
    `;

    API.sales.list({ per_page: 5 })
        .then(function (data) {
            if (!data || !data.success) {
                throw new Error((data && data.message) || 'Failed to load');
            }
            const sales = (data.data && data.data.items) || [];

            if (sales.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-receipt"></i>
                        <p>No sales recorded yet</p>
                    </div>
                `;
                return;
            }

            let html = `
                <table class="sales-table">
                    <thead>
                        <tr>
                            <th>Invoice</th>
                            <th>Date</th>
                            <th>Customer</th>
                            <th class="text-center">Items</th>
                            <th class="text-right">Total</th>
                            <th class="text-center">Status</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            sales.forEach(function (sale) {
                const status = _daSafeStr(sale.status) || 'completed';
                const statusClass = status === 'completed'
                    ? 'completed'
                    : status === 'pending'
                        ? 'pending'
                        : 'cancelled';

                const customerHtml = _daSafeStr(sale.customer_name).trim()
                    ? escapeHtml(sale.customer_name)
                    : '<span class="customer-empty">—</span>';

                html += `
                    <tr>
                        <td>
                            <span class="invoice-number">
                                ${escapeHtml(_daSafeStr(sale.invoice_number) || 'N/A')}
                            </span>
                        </td>
                        <td>${escapeHtml(formatDate(sale.created_at))}</td>
                        <td>${customerHtml}</td>
                        <td class="text-center">${_daSafeNum(sale.total_items)}</td>
                        <td class="text-right">
                            <span class="amount">
                                ₱${_daSafeNum(sale.final_amount).toFixed(2)}
                            </span>
                        </td>
                        <td class="text-center">
                            <span class="status-badge ${statusClass}">${status}</span>
                        </td>
                    </tr>
                `;
            });

            html += '</tbody></table>';
            container.innerHTML = html;
        })
        .catch(function (err) {
            console.error('[dashboard_admin] recent sales:', err);
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-exclamation-circle"></i>
                    <p>Failed to load recent sales</p>
                    <button class="btn btn-primary"
                            onclick="loadRecentSales()"
                            style="margin-top:12px;">
                        <i class="fas fa-sync"></i> Retry
                    </button>
                </div>
            `;
        });
}


/* ============================================
   ADMIN NAME
   ============================================ */

function loadAdminName() {
    fetch('/api/auth/whoami', { credentials: 'same-origin' })
        .then(function (r) {
            return r.ok ? r.json() : null;
        })
        .then(function (data) {
            if (!data || !data.user) return;
            const el = document.getElementById('adminName');
            if (el) {
                el.textContent = data.user.full_name || 'Administrator';
            }
        })
        .catch(function () { /* silent */ });
}


/* ============================================
   INIT
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
    _daSetCurrentDate();
    loadAdminStats();
    loadRecentSales();
    loadAdminName();
});
