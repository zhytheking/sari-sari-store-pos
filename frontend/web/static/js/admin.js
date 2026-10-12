/**
 * Admin JavaScript for Sari-Sari Store POS System.
 *
 * All utilities (showToast, escapeHtml, formatCurrency, formatDate, etc.)
 * live in api-client.js. 
 */

document.addEventListener('DOMContentLoaded', function() {
    if (document.querySelector('.dashboard-grid')) {
        loadDashboardStats();
        loadUserInfo();
    }
});

/* ============================================
   DASHBOARD STATS
   ============================================ */

function loadDashboardStats() {
    API.sales.stats({ period: 'today' })
        .then(data => {
            if (data.success) {
                const el = document.getElementById('todaySales');
                if (el) el.textContent = data.data.total_sales || 0;
            }
        })
        .catch(error => console.error('Error loading sales stats:', error));

    API.sales.stats({ period: 'month' })
        .then(data => {
            if (data.success) {
                const el = document.getElementById('monthRevenue');
                if (el) el.textContent = formatCurrency(data.data.total_revenue || 0);
            }
        })
        .catch(error => console.error('Error loading revenue stats:', error));

    API.products.list({ per_page: 1 })
        .then(data => {
            if (data.success) {
                const el = document.getElementById('totalProducts');
                if (el) el.textContent = data.data.pagination?.total || 0;
            }
        })
        .catch(error => console.error('Error loading products:', error));

    API.inventory.lowStock(10)
        .then(data => {
            if (data.success) {
                const el = document.getElementById('lowStockItems');
                if (el) el.textContent = data.data.count || 0;
            }
        })
        .catch(error => console.error('Error loading low stock:', error));
}

/* ============================================
   USER INFO — fetched from server, not localStorage
   ============================================ */

function loadUserInfo() {
    fetch('/api/auth/whoami', { credentials: 'same-origin' })
        .then(r => r.ok ? r.json() : null)
        .then(data => {
            if (!data || !data.user) return;
            const el = document.getElementById('adminName');
            if (el) el.textContent = data.user.full_name || 'Admin';
        })
        .catch(() => {});
}

/* ===================
   REPORT GENERATION
   ==================== */

function generateReport() {
    const startDate = document.getElementById('reportStartDate')?.value;
    const endDate = document.getElementById('reportEndDate')?.value;
    const groupBy = document.getElementById('reportGroupBy')?.value || 'day';

    if (!startDate || !endDate) {
        showToast('Please select both start and end dates', 'warning');
        return;
    }

    const container = document.getElementById('reportContent');
    if (container) {
        container.innerHTML = `
            <div class="loading-state">
                <div class="loading-spinner"></div>
                <p>Loading report data...</p>
            </div>
        `;
    }

    API.reports.sales({ start_date: startDate, end_date: endDate, group_by: groupBy })
        .then(data => {
            if (data.success) {
                renderReport(data.data);
            } else if (container) {
                container.innerHTML = `
                    <div class="error-state">
                        <i class="fas fa-exclamation-circle"></i>
                        <p>Failed to load report</p>
                        <button class="btn btn-primary" onclick="generateReport()">Retry</button>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            if (container) {
                container.innerHTML = `
                    <div class="error-state">
                        <i class="fas fa-exclamation-circle"></i>
                        <p>Network error. Please try again.</p>
                        <button class="btn btn-primary" onclick="generateReport()">Retry</button>
                    </div>
                `;
            }
        });
}

function renderReport(data) {
    const container = document.getElementById('reportContent');
    if (!container) return;

    if (!data.daily_data || data.daily_data.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-chart-bar"></i>
                <h3>No data available</h3>
                <p>No sales found in this date range</p>
            </div>
        `;
        return;
    }

    let html = `
        <table class="report-table">
            <thead>
                <tr>
                    <th>Date</th>
                    <th class="text-right">Sales</th>
                    <th class="text-right">Revenue</th>
                    <th class="text-right">Discounts</th>
                    <th class="text-right">Taxes</th>
                    <th class="text-center">Cashiers</th>
                </tr>
            </thead>
            <tbody>
    `;

    data.daily_data.forEach(row => {
        html += `
            <tr>
                <td>${row.date}</td>
                <td class="text-right">${row.sales_count}</td>
                <td class="text-right">${formatCurrency(row.revenue)}</td>
                <td class="text-right">${formatCurrency(row.discounts)}</td>
                <td class="text-right">${formatCurrency(row.taxes)}</td>
                <td class="text-center">${row.cashiers || 0}</td>
            </tr>
        `;
    });

    const summary = data.summary;
    html += `
        <tr style="font-weight:700;background:#f8f9fa;">
            <td><strong>TOTAL</strong></td>
            <td class="text-right"><strong>${summary.total_sales}</strong></td>
            <td class="text-right"><strong>${formatCurrency(summary.total_revenue)}</strong></td>
            <td class="text-right"><strong>${formatCurrency(summary.total_discounts)}</strong></td>
            <td class="text-right"><strong>${formatCurrency(summary.total_taxes)}</strong></td>
            <td class="text-center">—</td>
        </tr>
    `;

    html += '</tbody></table>';
    container.innerHTML = html;
}

function exportReport(format) {
    const startDate = document.getElementById('reportStartDate')?.value;
    const endDate = document.getElementById('reportEndDate')?.value;

    if (!startDate || !endDate) {
        showToast('Please select both start and end dates', 'warning');
        return;
    }

    showToast(`Exporting ${format.toUpperCase()}...`, 'info');
    window.location.href = `/api/v1/reports/sales?start_date=${startDate}&end_date=${endDate}&format=${format}`;
}
