/**
 * reports.js — Sales Reports page logic.
 *
 * Depends on api-client.js.
 */

let _repCurrentData = null;


/* ============================================
   SAFE HELPERS
   ============================================ */

function _repStr(v) { return (v === null || v === undefined) ? '' : String(v); }
function _repNum(v) { const n = Number(v); return isNaN(n) ? 0 : n; }

function _repDateInput(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}


/* ============================================
   INIT
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
    const today = new Date();
    const thirtyAgo = new Date();
    thirtyAgo.setDate(today.getDate() - 30);

    const sd = document.getElementById('reportStartDate');
    const ed = document.getElementById('reportEndDate');
    if (sd) sd.value = _repDateInput(thirtyAgo);
    if (ed) ed.value = _repDateInput(today);

    loadReport();
});


/* ============================================
   LOAD
   ============================================ */

function loadReport() {
    const sd = document.getElementById('reportStartDate');
    const ed = document.getElementById('reportEndDate');
    const gb = document.getElementById('reportGroupBy');

    const startDate = sd ? sd.value : '';
    const endDate = ed ? ed.value : '';
    const groupBy = (gb ? gb.value : 'day') || 'day';

    if (!startDate || !endDate) {
        showToast('Please select both start and end dates', 'warning');
        return;
    }

    const container = document.getElementById('reportContent');
    const generateBtn = document.getElementById('generateBtn');
    const exportBtns = document.getElementById('exportButtons');
    if (!container) return;

    container.innerHTML = `
        <div class="loading-state">
            <div class="loading-spinner"></div>
            <p style="color:#6c757d;">Loading report data...</p>
        </div>
    `;
    if (exportBtns) exportBtns.style.display = 'none';
    if (generateBtn) generateBtn.disabled = true;

    API.reports.sales({
        start_date: startDate,
        end_date: endDate,
        group_by: groupBy
    })
    .then(function (data) {
        if (data && data.success) {
            _repCurrentData = data.data;
            _repRender(data.data);
            _repUpdateCards(data.data);
            if (exportBtns) exportBtns.style.display = 'flex';
        } else {
            _repRenderError((data && data.message) || 'Failed to load report');
        }
    })
    .catch(function (err) {
        console.error('[reports]', err);
        _repRenderError(err.message || 'Network error');
    })
    .finally(function () {
        if (generateBtn) generateBtn.disabled = false;
    });
}


/* ============================================
   RENDER
   ============================================ */

function _repRenderError(message) {
    const container = document.getElementById('reportContent');
    if (!container) return;
    container.innerHTML = `
        <div class="error-state">
            <i class="fas fa-exclamation-circle"></i>
            <p><strong>Failed to load report</strong></p>
            <p style="font-size:0.8rem;color:#adb5bd;">${escapeHtml(message)}</p>
            <button class="btn-retry" onclick="loadReport()">
                <i class="fas fa-sync"></i> Retry
            </button>
        </div>
    `;
}

function _repRender(data) {
    const container = document.getElementById('reportContent');
    if (!container) return;

    const rows = data.period_data || data.daily_data || [];

    if (!rows.length) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-chart-bar"></i>
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
                    <th class="text-center">Sales</th>
                    <th class="text-right">Revenue</th>
                    <th class="text-right">Discounts</th>
                    <th class="text-center">Cashiers</th>
                </tr>
            </thead>
            <tbody>
    `;

    rows.forEach(function (row) {
        const period = row.period || row.date || '—';
        const salesCount = _repNum(row.sales_count);
        const revenue = _repNum(row.revenue);
        const discounts = _repNum(row.discounts);
        const cashiers = _repNum(row.cashiers);

        html += `
            <tr>
                <td>${escapeHtml(_repStr(period))}</td>
                <td class="text-center">${salesCount}</td>
                <td class="text-right amount">₱${revenue.toFixed(2)}</td>
                <td class="text-right">₱${discounts.toFixed(2)}</td>
                <td class="text-center">${cashiers}</td>
            </tr>
        `;
    });

    const summary = data.summary || {};
    html += `
        <tr class="summary-row">
            <td><strong>TOTAL</strong></td>
            <td class="text-center"><strong>${_repNum(summary.total_sales)}</strong></td>
            <td class="text-right amount">
                <strong>₱${_repNum(summary.total_revenue).toFixed(2)}</strong>
            </td>
            <td class="text-right">
                <strong>₱${_repNum(summary.total_discounts).toFixed(2)}</strong>
            </td>
            <td class="text-center">—</td>
        </tr>
    `;

    html += '</tbody></table>';
    container.innerHTML = html;
}


function _repUpdateCards(data) {
    const summary = data.summary || {};
    const setText = function (id, txt) {
        const el = document.getElementById(id);
        if (el) el.textContent = txt;
    };

    setText('totalSales', '₱' + _repNum(summary.total_revenue).toFixed(2));
    setText('totalOrders', _repNum(summary.total_sales));
    setText('avgOrder', '₱' + _repNum(summary.average_sale).toFixed(2));
    setText('totalDiscounts', '₱' + _repNum(summary.total_discounts).toFixed(2));

    const range = (_repStr(summary.start_date)) + ' → ' +
                  (_repStr(summary.end_date));
    setText('totalSalesSub', range);
    setText('totalOrdersSub', range);
    setText('avgOrderSub', range);
    setText('totalDiscountsSub', range);
}


/* ============================================
   EXPORT
   ============================================ */

function exportReport(format) {
    const sd = document.getElementById('reportStartDate');
    const ed = document.getElementById('reportEndDate');
    const gb = document.getElementById('reportGroupBy');

    const startDate = sd ? sd.value : '';
    const endDate = ed ? ed.value : '';
    const groupBy = (gb ? gb.value : 'day') || 'day';

    if (!startDate || !endDate) {
        showToast('Please select dates first', 'warning');
        return;
    }

    showToast('Exporting ' + format.toUpperCase() + '...', 'info');

    if (format === 'csv') {
        const url = '/api/v1/reports/sales?start_date=' + startDate +
            '&end_date=' + endDate + '&group_by=' + groupBy + '&format=csv';
        fetch(url, { credentials: 'same-origin' })
            .then(function (r) {
                if (!r.ok) throw new Error('Export failed');
                return r.blob();
            })
            .then(function (blob) {
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = 'sales_report_' + startDate + '_to_' + endDate + '.csv';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                showToast('CSV exported', 'success');
            })
            .catch(function (err) {
                console.error(err);
                showToast('Failed to export CSV', 'error');
            });
        return;
    }

    if (format === 'pdf') {
        window.print();
    }
}
