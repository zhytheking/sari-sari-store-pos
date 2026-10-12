/**
 * dashboard_cashier.js — Cashier dashboard page logic.
 *
 * Depends on api-client.js.
 */


/* ============================================
   SAFE HELPERS
   ============================================ */

function _dcSafeStr(v) {
    return (v === null || v === undefined) ? '' : String(v);
}

function _dcSafeNum(v) {
    const n = Number(v);
    return isNaN(n) ? 0 : n;
}


/* ============================================
   DATE
   ============================================ */

function _dcSetCurrentDate() {
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

function loadCashierStats() {
    // Today's sales
    API.sales.stats({ period: 'today' })
        .then(function (data) {
            if (!data || !data.success) return;
            const d = data.data || {};
            const revenue = _dcSafeNum(d.total_revenue);
            const sales = _dcSafeNum(d.total_sales);
            const avg = _dcSafeNum(d.average_sale);

            const revEl = document.getElementById('todaySales');
            const ordEl = document.getElementById('todayOrders');
            const avgEl = document.getElementById('avgOrder');

            if (revEl) revEl.textContent = `₱${revenue.toFixed(2)}`;
            if (ordEl) ordEl.textContent = sales;
            if (avgEl) avgEl.textContent = `₱${avg.toFixed(2)}`;
        })
        .catch(function (err) {
            console.error('[dashboard_cashier] stats:', err);
        });

    // Products count
    API.products.list({ per_page: 500 })
        .then(function (data) {
            if (!data || !data.success) return;
            const items = (data.data && data.data.items) || [];
            const el = document.getElementById('totalProducts');
            if (el) el.textContent = items.length;
        })
        .catch(function (err) {
            console.error('[dashboard_cashier] products:', err);
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
                throw new Error((data && data.message) || 'Failed');
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
                const status = _dcSafeStr(sale.status) || 'completed';
                const statusClass = status === 'completed'
                    ? 'completed'
                    : status === 'pending'
                        ? 'pending'
                        : 'cancelled';

                html += `
                    <tr>
                        <td>
                            <span class="invoice-number">
                                ${escapeHtml(_dcSafeStr(sale.invoice_number) || 'N/A')}
                            </span>
                        </td>
                        <td>${escapeHtml(formatDate(sale.created_at))}</td>
                        <td>${escapeHtml(_dcSafeStr(sale.customer_name) || 'Walk-in')}</td>
                        <td class="text-center">${_dcSafeNum(sale.total_items)}</td>
                        <td class="text-right">
                            <span class="amount">
                                ₱${_dcSafeNum(sale.final_amount).toFixed(2)}
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
            console.error('[dashboard_cashier] recent sales:', err);
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
   CASHIER NAME
   ============================================ */

function loadCashierName() {
    fetch('/api/auth/whoami', { credentials: 'same-origin' })
        .then(function (r) {
            return r.ok ? r.json() : null;
        })
        .then(function (data) {
            if (!data || !data.user) return;
            const el = document.getElementById('cashierName');
            if (el) {
                el.textContent = data.user.full_name || 'Cashier';
            }
        })
        .catch(function () { /* silent */ });
}


/* ============================================
   INIT
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
    _dcSetCurrentDate();
    loadCashierStats();
    loadRecentSales();
    loadCashierName();
});
