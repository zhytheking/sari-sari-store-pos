/**
 * cashier_sales.js — "My Sales" page for cashiers.
 *
 * Depends on api-client.js.
 *
 * Owns:
 *   - Loading the caller's own sales
 *   - Date + payment filters
 *   - Pagination
 *   - Receipt modal
 *   - CSV export
 *   - Auto-refresh every 30s
 */

let _csCurrentPage = 1;
let _csFilters = { start_date: '', end_date: '', payment_method: '' };
let _csReceiptData = null;
const _CS_PER_PAGE = 20;

let _csAutoTimer = null;
let _csLastSeenSaleId = 0;
const _CS_AUTO_MS = 30000;


/* ============================================
   SAFE HELPERS
   ============================================ */

function _csStr(v) { return (v === null || v === undefined) ? '' : String(v); }
function _csNum(v) { const n = Number(v); return isNaN(n) ? 0 : n; }

function _csToDateInput(d) {
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

    const sd = document.getElementById('filterStartDate');
    const ed = document.getElementById('filterEndDate');

    if (sd) sd.value = _csToDateInput(thirtyAgo);
    if (ed) ed.value = _csToDateInput(today);

    _csFilters.start_date = sd ? sd.value : '';
    _csFilters.end_date = ed ? ed.value : '';

    // ── Export button ──
    const exportBtn = document.getElementById('exportMySalesBtn');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportMySalesCSV);
    }

    loadMySales(1);
    _csStartAutoRefresh();

    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) _csRefreshIfChanged();
    });

    window.addEventListener('beforeunload', _csStopAutoRefresh);
});


/* ============================================
   AUTO REFRESH
   ============================================ */

function _csStartAutoRefresh() {
    _csStopAutoRefresh();
    _csAutoTimer = setInterval(_csRefreshIfChanged, _CS_AUTO_MS);
}

function _csStopAutoRefresh() {
    if (_csAutoTimer) {
        clearInterval(_csAutoTimer);
        _csAutoTimer = null;
    }
}

function _csShouldSkip() {
    if (document.hidden) return true;
    const ae = document.activeElement;
    if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'SELECT' || ae.tagName === 'TEXTAREA')) {
        return true;
    }
    if (document.querySelector('.modal-overlay.active')) return true;
    return false;
}

function _csRefreshIfChanged() {
    if (_csShouldSkip()) return;

    const params = new URLSearchParams();
    params.append('page', 1);
    params.append('per_page', 1);
    if (_csFilters.start_date) params.append('start_date', _csFilters.start_date);
    if (_csFilters.end_date) params.append('end_date', _csFilters.end_date);
    if (_csFilters.payment_method) params.append('payment_method', _csFilters.payment_method);

    fetch('/api/v1/sales/my-sales?' + params.toString(), {
        credentials: 'same-origin'
    })
    .then(function (r) { return r.json(); })
    .then(function (res) {
        if (!res || !res.success) return;
        const latest = (res.data && res.data.latest_sale_id) || 0;
        if (latest > _csLastSeenSaleId) {
            _csLastSeenSaleId = latest;
            loadMySales(_csCurrentPage);
        }
    })
    .catch(function () { /* silent */ });
}


/* ============================================
   LOAD
   ============================================ */

function loadMySales(page) {
    _csCurrentPage = page || 1;
    const container = document.getElementById('salesTableContainer');
    if (!container) return;

    container.innerHTML = `
        <div class="loading-state">
            <div class="loading-spinner"></div>
            <p>Loading your sales...</p>
        </div>
    `;

    const params = new URLSearchParams();
    params.append('page', _csCurrentPage);
    params.append('per_page', _CS_PER_PAGE);
    if (_csFilters.start_date) params.append('start_date', _csFilters.start_date);
    if (_csFilters.end_date) params.append('end_date', _csFilters.end_date);
    if (_csFilters.payment_method) params.append('payment_method', _csFilters.payment_method);

    fetch('/api/v1/sales/my-sales?' + params.toString(), {
        credentials: 'same-origin'
    })
    .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    })
    .then(function (data) {
        if (!data || !data.success) {
            throw new Error((data && data.message) || 'Failed to load');
        }

        const payload = data.data || {};
        _csLastSeenSaleId = payload.latest_sale_id || _csLastSeenSaleId;

        try { _csRenderTable(payload.items || []); }
        catch (e) { console.error('[cashier_sales] renderTable:', e); }

        try { _csUpdateStats(payload.summary || {}, payload.today || {}, payload.week || {}); }
        catch (e) { console.error('[cashier_sales] stats:', e); }

        try { _csUpdatePagination(payload.pagination || {}); }
        catch (e) { console.error('[cashier_sales] pagination:', e); }
    })
    .catch(function (err) {
        console.error('[cashier_sales] load failed:', err);
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-circle"></i>
                <h3>Failed to load sales</h3>
                <p>${escapeHtml(err.message || 'Unknown error')}</p>
                <button class="btn btn-primary"
                        onclick="loadMySales(1)"
                        style="padding:10px 24px;border:none;
                               border-radius:10px;background:#2d6a4f;
                               color:white;cursor:pointer;">
                    <i class="fas fa-sync"></i> Retry
                </button>
            </div>
        `;
    });
}


/* ============================================
   RENDER TABLE
   ============================================ */

function _csRenderTable(sales) {
    const container = document.getElementById('salesTableContainer');
    if (!container) return;

    if (!Array.isArray(sales) || sales.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-receipt"></i>
                <h3>No sales found</h3>
                <p>You haven't made any sales in this date range</p>
                <a href="/admin/pos">
                    <i class="fas fa-cash-register"></i> Make a Sale
                </a>
            </div>
        `;
        return;
    }

    let html = `
        <table class="sales-table">
            <thead>
                <tr>
                    <th>Invoice</th>
                    <th>Date &amp; Time</th>
                    <th>Customer</th>
                    <th class="text-center">Items</th>
                    <th>Payment</th>
                    <th>GCash Ref</th>
                    <th class="text-right">Total</th>
                    <th class="text-center">Action</th>
                </tr>
            </thead>
            <tbody>
    `;

    sales.forEach(function (sale) {
        const isGcash = sale.payment_method === 'gcash';
        const refHtml = (isGcash && sale.payment_reference)
            ? `<span class="reference-code">•••${escapeHtml(_csStr(sale.payment_reference))}</span>`
            : '<span class="reference-empty">—</span>';
        const customerHtml = _csStr(sale.customer_name).trim()
            ? escapeHtml(sale.customer_name)
            : '<span class="customer-empty">—</span>';

        html += `
            <tr>
                <td>
                    <span class="invoice-number">
                        ${escapeHtml(_csStr(sale.invoice_number))}
                    </span>
                </td>
                <td>${escapeHtml(formatDate(sale.created_at))}</td>
                <td>${customerHtml}</td>
                <td class="text-center">${_csNum(sale.total_items)}</td>
                <td>
                    <span class="payment-badge ${escapeHtml(_csStr(sale.payment_method))}">
                        ${escapeHtml(_csFormatPayment(sale.payment_method))}
                    </span>
                </td>
                <td>${refHtml}</td>
                <td class="text-right">
                    <span class="amount">
                        ₱${_csNum(sale.final_amount).toFixed(2)}
                    </span>
                </td>
                <td class="text-center">
                    <button class="btn-view" onclick="viewSale(${sale.id})">
                        <i class="fas fa-eye"></i> View
                    </button>
                </td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}


function _csFormatPayment(method) {
    if (!method) return 'N/A';
    const map = { cash: 'Cash', gcash: 'GCash' };
    return map[method] || method;
}


/* ============================================
   STATS
   ============================================ */

function _csUpdateStats(summary, today, week) {
    const setText = function (id, txt) {
        const el = document.getElementById(id);
        if (el) el.textContent = txt;
    };

    setText('statTodayCount', _csNum(today.count));
    setText('statTodayRevenue', '₱' + _csNum(today.revenue).toFixed(2));

    setText('statWeekCount', _csNum(week.count));
    setText('statWeekRevenue', '₱' + _csNum(week.revenue).toFixed(2));

    setText('statTotalCount', _csNum(summary.total_transactions));
    setText('statTotalRevenue', '₱' + _csNum(summary.total_revenue).toFixed(2));

    setText('statAvgSale', '₱' + _csNum(summary.average_sale).toFixed(2));
}


/* ============================================
   PAGINATION
   ============================================ */

function _csUpdatePagination(pagination) {
    const wrapper = document.getElementById('paginationWrapper');
    const info = document.getElementById('paginationInfo');
    const controls = document.getElementById('paginationControls');
    if (!wrapper || !info || !controls) return;

    const totalPages = _csNum(pagination.pages);
    const currentPage = _csNum(pagination.page) || 1;
    const total = _csNum(pagination.total);
    const perPage = _csNum(pagination.per_page) || _CS_PER_PAGE;

    if (totalPages <= 1) {
        wrapper.style.display = 'none';
        return;
    }

    wrapper.style.display = 'flex';

    const startItem = (currentPage - 1) * perPage + 1;
    const endItem = Math.min(currentPage * perPage, total);
    info.textContent = 'Showing ' + startItem + '-' + endItem + ' of ' + total + ' sales';

    let startPage = Math.max(1, currentPage - 2);
    let endPage = Math.min(totalPages, startPage + 4);
    if (endPage - startPage < 4) startPage = Math.max(1, endPage - 4);

    let html = '';
    html += `<button onclick="loadMySales(${currentPage - 1})"
                     ${currentPage <= 1 ? 'disabled' : ''}>
                <i class="fas fa-chevron-left"></i>
             </button>`;

    if (startPage > 1) {
        html += `<button onclick="loadMySales(1)">1</button>`;
        if (startPage > 2) {
            html += `<span style="padding:0 8px;color:#6c757d;">...</span>`;
        }
    }
    for (let i = startPage; i <= endPage; i++) {
        const active = i === currentPage;
        html += `<button onclick="loadMySales(${i})"
                         class="${active ? 'active' : ''}">${i}</button>`;
    }
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            html += `<span style="padding:0 8px;color:#6c757d;">...</span>`;
        }
        html += `<button onclick="loadMySales(${totalPages})">${totalPages}</button>`;
    }
    html += `<button onclick="loadMySales(${currentPage + 1})"
                     ${currentPage >= totalPages ? 'disabled' : ''}>
                <i class="fas fa-chevron-right"></i>
             </button>`;

    controls.innerHTML = html;
}


/* ============================================
   FILTERS
   ============================================ */

function applyFilters() {
    const sd = document.getElementById('filterStartDate');
    const ed = document.getElementById('filterEndDate');
    const fp = document.getElementById('filterPayment');

    _csFilters.start_date = sd ? sd.value : '';
    _csFilters.end_date = ed ? ed.value : '';
    _csFilters.payment_method = fp ? fp.value : '';

    loadMySales(1);
}

function resetFilters() {
    const today = new Date();
    const thirtyAgo = new Date();
    thirtyAgo.setDate(today.getDate() - 30);

    const sd = document.getElementById('filterStartDate');
    const ed = document.getElementById('filterEndDate');
    const fp = document.getElementById('filterPayment');

    if (sd) sd.value = _csToDateInput(thirtyAgo);
    if (ed) ed.value = _csToDateInput(today);
    if (fp) fp.value = '';

    _csFilters.start_date = sd ? sd.value : '';
    _csFilters.end_date = ed ? ed.value : '';
    _csFilters.payment_method = '';

    loadMySales(1);
}


/* ============================================
   RECEIPT MODAL
   ============================================ */

function viewSale(saleId) {
    const modal = document.getElementById('receiptModal');
    const body = document.getElementById('receiptBody');
    if (!modal || !body) return;

    body.textContent = 'Loading...';
    modal.classList.add('active');

    fetch('/api/v1/sales/' + saleId + '/receipt', {
        credentials: 'same-origin'
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data && data.success) {
            _csReceiptData = data.data;
            body.textContent = _csBuildReceiptText(data.data);
        } else {
            body.textContent = 'Failed to load receipt: ' +
                ((data && data.message) || 'Unknown error');
        }
    })
    .catch(function (err) {
        console.error('[cashier_sales] receipt:', err);
        body.textContent = 'Failed to load receipt. Please try again.';
    });
}

function _csBuildReceiptText(r) {
    const width = 40;
    const line = '-'.repeat(width);

    const pad = function (str, len, align) {
        str = String(str);
        if (str.length >= len) return str.substring(0, len);
        const padding = ' '.repeat(len - str.length);
        return align === 'right' ? padding + str : str + padding;
    };
    const center = function (str, len) {
        str = String(str);
        if (str.length >= len) return str.substring(0, len);
        const leftPad = Math.floor((len - str.length) / 2);
        return ' '.repeat(leftPad) + str;
    };

    const out = [];
    out.push(center('LONGGANIGGA', width));
    out.push(center('SARI-SARI STORE', width));
    out.push(line);
    out.push('Invoice:  ' + _csStr(r.invoice_number));
    out.push('Date:     ' + formatDate(r.date));

    if (_csStr(r.customer).trim()) {
        out.push('Customer: ' + r.customer);
    }
    out.push('Cashier:  ' + _csStr(r.cashier));
    out.push(line);
    out.push(pad('Item', 20) + pad('Qty', 5, 'right') + pad('Total', 15, 'right'));
    out.push(line);

    (r.items || []).forEach(function (item) {
        out.push(
            pad(_csStr(item.name).substring(0, 19), 20) +
            pad(_csNum(item.quantity), 5, 'right') +
            pad('₱' + _csNum(item.subtotal).toFixed(2), 15, 'right')
        );
    });

    out.push(line);
    out.push(pad('Subtotal', 25) + pad('₱' + _csNum(r.subtotal).toFixed(2), 15, 'right'));

    if (_csNum(r.discount) > 0) {
        out.push(pad('Discount', 25) + pad('-₱' + _csNum(r.discount).toFixed(2), 15, 'right'));
    }
    out.push(pad('Tax', 25) + pad('₱' + _csNum(r.tax).toFixed(2), 15, 'right'));
    out.push(pad('TOTAL', 25) + pad('₱' + _csNum(r.total).toFixed(2), 15, 'right'));
    out.push(line);
    out.push(pad('Payment Method', 25) + pad(_csFormatPayment(r.payment_method), 15, 'right'));
    out.push(pad('Amount Paid', 25) + pad('₱' + _csNum(r.payment_amount).toFixed(2), 15, 'right'));
    out.push(pad('Change', 25) + pad('₱' + _csNum(r.change).toFixed(2), 15, 'right'));

    if (r.payment_reference) {
        out.push(pad('GCash Ref', 25) + pad('•••' + r.payment_reference, 15, 'right'));
    }
    out.push(line);
    out.push(center('Thank you for your purchase!', width));

    return out.join('\n');
}


function closeReceiptModal() {
    const modal = document.getElementById('receiptModal');
    if (modal) modal.classList.remove('active');
    _csReceiptData = null;
}


function printReceipt() {
    if (!_csReceiptData) {
        showToast('No receipt to print', 'warning');
        return;
    }
    const win = window.open('', '_blank', 'width=400,height=600');
    if (!win) {
        showToast('Please allow popups to print', 'warning');
        return;
    }

    const r = _csReceiptData;
    let html = '<!DOCTYPE html><html><head><title>Receipt</title><style>';
    html += 'body{font-family:"Courier New",monospace;font-size:12px;';
    html += 'padding:20px;max-width:300px;margin:0 auto;}';
    html += '.header{text-align:center;border-bottom:1px dashed #000;';
    html += 'padding-bottom:10px;margin-bottom:10px;}';
    html += '.header h2{font-size:14px;margin:0;}';
    html += '.items{width:100%;margin:10px 0;}';
    html += '.items td{padding:2px 0;}';
    html += '.text-right{text-align:right;}';
    html += '.totals{border-top:1px dashed #000;padding-top:10px;margin-top:10px;}';
    html += '.total-line{display:flex;justify-content:space-between;padding:2px 0;}';
    html += '.grand-total{font-weight:bold;font-size:14px;';
    html += 'border-top:1px solid #000;padding-top:5px;margin-top:5px;}';
    html += '.footer{text-align:center;margin-top:15px;padding-top:10px;';
    html += 'border-top:1px dashed #000;}';
    html += '</style></head><body>';
    html += '<div class="header"><h2>🏪 Saliga Sari-Sari Store</h2>';
    html += '<p>' + escapeHtml(_csStr(r.date)) + '</p>';
    html += '<p>Invoice: ' + escapeHtml(_csStr(r.invoice_number)) + '</p>';
    html += '</div>';
    html += '<table class="items"><tr><th style="text-align:left;">Item</th>';
    html += '<th class="text-right">Qty</th><th class="text-right">Price</th>';
    html += '<th class="text-right">Total</th></tr>';

    (r.items || []).forEach(function (item) {
        html += '<tr><td>' + escapeHtml(_csStr(item.name)) + '</td>';
        html += '<td class="text-right">' + _csNum(item.quantity) + '</td>';
        html += '<td class="text-right">' + _csNum(item.price).toFixed(2) + '</td>';
        html += '<td class="text-right">' + _csNum(item.subtotal).toFixed(2) + '</td></tr>';
    });

    html += '</table>';
    html += '<div class="totals">';
    html += '<div class="total-line"><span>Subtotal</span><span>' +
            _csNum(r.subtotal).toFixed(2) + '</span></div>';
    if (_csNum(r.discount) > 0) {
        html += '<div class="total-line"><span>Discount</span><span>-' +
                _csNum(r.discount).toFixed(2) + '</span></div>';
    }
    html += '<div class="total-line"><span>Tax</span><span>' +
            _csNum(r.tax).toFixed(2) + '</span></div>';
    html += '<div class="total-line grand-total"><span>TOTAL</span><span>' +
            _csNum(r.total).toFixed(2) + '</span></div>';
    html += '</div>';
    html += '<div style="border-top:1px dashed #000;margin:8px 0;"></div>';
    html += '<div class="total-line"><span>Payment</span><span>' +
            _csNum(r.payment_amount).toFixed(2) + '</span></div>';
    html += '<div class="total-line"><span>Change</span><span>' +
            _csNum(r.change).toFixed(2) + '</span></div>';
    if (r.payment_reference) {
        html += '<div class="total-line"><span>GCash Ref</span><span>•••' +
                escapeHtml(r.payment_reference) + '</span></div>';
    }
    html += '<div class="total-line"><span>Cashier</span><span>' +
            escapeHtml(_csStr(r.cashier)) + '</span></div>';
    html += '<div class="footer"><p>Thank you for your purchase!</p></div>';
    html += '<script>window.print();window.close();<\/script>';
    html += '</body></html>';

    win.document.write(html);
    win.document.close();
}


/* ============================================
   EXPORT CSV
   ============================================ */

function exportMySalesCSV() {
    const params = {};

    if (_csFilters.start_date) params.start_date = _csFilters.start_date;
    if (_csFilters.end_date) params.end_date = _csFilters.end_date;
    if (_csFilters.payment_method) params.payment_method = _csFilters.payment_method;

    const url = API.reports.exportMySalesUrl(params);

    showToast('Preparing CSV download…', 'info');

    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
        if (a.parentNode) a.parentNode.removeChild(a);
    }, 100);
}


/* ============================================
   MODAL CLOSE
   ============================================ */

document.addEventListener('click', function (e) {
    const modal = document.getElementById('receiptModal');
    if (e.target === modal) closeReceiptModal();
});

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeReceiptModal();
});
