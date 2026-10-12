/**
 * all_sales.js — "All Sales" page for owners.
 *
 * Depends on api-client.js.
 *
 * Owns:
 *   - Loading all sales across cashiers
 *   - Stats grid, cashier breakdown, payment breakdown
 *   - Filters (date range, cashier, payment method)
 *   - Pagination
 *   - Receipt modal
 *   - Auto-refresh every 30s
 */

let _asPage = 1;
let _asFilters = {
    start_date: '',
    end_date: '',
    payment_method: '',
    cashier_id: ''
};
let _asReceipt = null;
const _AS_PER_PAGE = 20;

let _asTimer = null;
let _asLastSeen = 0;
const _AS_MS = 30000;


/* ============================================
   SAFE HELPERS
   ============================================ */

function _asStr(v) { return (v === null || v === undefined) ? '' : String(v); }
function _asNum(v) { const n = Number(v); return isNaN(n) ? 0 : n; }

function _asInitials(name) {
    const s = _asStr(name).trim();
    if (!s) return '??';
    const parts = s.split(/\s+/).filter(Boolean);
    if (parts.length === 0) return '??';
    return parts.map(function (w) { return w[0] || ''; }).join('')
        .slice(0, 2).toUpperCase() || '??';
}

function _asDateInput(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function _asFormatPayment(method) {
    if (!method) return 'N/A';
    const map = { cash: 'Cash', gcash: 'GCash' };
    return map[method] || method;
}


/* ============================================
   INIT
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
    const today = new Date();
    const oneYearAgo = new Date();
    oneYearAgo.setFullYear(today.getFullYear() - 1);

    const sd = document.getElementById('filterStartDate');
    const ed = document.getElementById('filterEndDate');
    if (sd) sd.value = _asDateInput(oneYearAgo);
    if (ed) ed.value = _asDateInput(today);

    _asFilters.start_date = sd ? sd.value : '';
    _asFilters.end_date = ed ? ed.value : '';

    loadAllSales(1);
    _asStartAutoRefresh();

    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) _asRefreshIfChanged();
    });

    window.addEventListener('beforeunload', _asStopAutoRefresh);
});


/* ============================================
   AUTO REFRESH
   ============================================ */

function _asStartAutoRefresh() {
    _asStopAutoRefresh();
    _asTimer = setInterval(_asRefreshIfChanged, _AS_MS);
}

function _asStopAutoRefresh() {
    if (_asTimer) {
        clearInterval(_asTimer);
        _asTimer = null;
    }
}

function _asShouldSkip() {
    if (document.hidden) return true;
    const ae = document.activeElement;
    if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'SELECT' || ae.tagName === 'TEXTAREA')) {
        return true;
    }
    if (document.querySelector('.modal-overlay.active')) return true;
    return false;
}

function _asRefreshIfChanged() {
    if (_asShouldSkip()) return;

    const params = new URLSearchParams();
    params.append('page', 1);
    params.append('per_page', 1);
    if (_asFilters.start_date) params.append('start_date', _asFilters.start_date);
    if (_asFilters.end_date) params.append('end_date', _asFilters.end_date);
    if (_asFilters.payment_method) params.append('payment_method', _asFilters.payment_method);
    if (_asFilters.cashier_id) params.append('cashier_id', _asFilters.cashier_id);

    fetch('/api/v1/sales/all-sales?' + params.toString(), {
        credentials: 'same-origin'
    })
    .then(function (r) { return r.json(); })
    .then(function (res) {
        if (!res || !res.success) return;
        const latest = (res.data && res.data.latest_sale_id) || 0;
        if (latest > _asLastSeen) {
            _asLastSeen = latest;
            loadAllSales(_asPage);
        }
    })
    .catch(function () { /* silent */ });
}


/* ============================================
   LOAD
   ============================================ */

function loadAllSales(page) {
    _asPage = page || 1;
    const container = document.getElementById('salesTableContainer');
    if (!container) return;

    container.innerHTML = `
        <div class="loading-state">
            <div class="loading-spinner"></div>
            <p>Loading sales...</p>
        </div>
    `;

    const params = new URLSearchParams();
    params.append('page', _asPage);
    params.append('per_page', _AS_PER_PAGE);
    if (_asFilters.start_date) params.append('start_date', _asFilters.start_date);
    if (_asFilters.end_date) params.append('end_date', _asFilters.end_date);
    if (_asFilters.payment_method) params.append('payment_method', _asFilters.payment_method);
    if (_asFilters.cashier_id) params.append('cashier_id', _asFilters.cashier_id);

    fetch('/api/v1/sales/all-sales?' + params.toString(), {
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
        _asLastSeen = payload.latest_sale_id || _asLastSeen;

        try { _asRenderTable(payload.items || []); }
        catch (e) { console.error('[all_sales] renderTable:', e); }

        try { _asUpdateStats(payload.summary || {}); }
        catch (e) { console.error('[all_sales] stats:', e); }

        try { _asRenderCashierBreakdown(payload.cashier_breakdown || []); }
        catch (e) { console.error('[all_sales] cashier breakdown:', e); }

        try {
            _asRenderPaymentBreakdown(
                payload.payment_breakdown || [],
                _asNum(payload.summary && payload.summary.total_revenue)
            );
        } catch (e) { console.error('[all_sales] payment breakdown:', e); }

        try { _asPopulateCashierDropdown(payload.cashiers || []); }
        catch (e) { console.error('[all_sales] cashier dropdown:', e); }

        try { _asUpdatePagination(payload.pagination || {}); }
        catch (e) { console.error('[all_sales] pagination:', e); }
    })
    .catch(function (err) {
        console.error('[all_sales] load failed:', err);
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-circle"></i>
                <h3>Failed to load sales</h3>
                <p>${escapeHtml(err.message || 'Unknown error')}</p>
                <button class="btn btn-primary"
                        onclick="loadAllSales(1)"
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
   TABLE
   ============================================ */

function _asRenderTable(sales) {
    const container = document.getElementById('salesTableContainer');
    if (!container) return;

    if (!Array.isArray(sales) || sales.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-receipt"></i>
                <h3>No sales found</h3>
                <p>No sales match the current filters</p>
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
                    <th>Cashier</th>
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
        const cashierName = _asStr(sale.cashier_name || sale.username) || 'Unknown';
        const initials = _asInitials(cashierName);
        const isGcash = sale.payment_method === 'gcash';
        const refHtml = (isGcash && sale.payment_reference)
            ? `<span class="reference-code">•••${escapeHtml(_asStr(sale.payment_reference))}</span>`
            : '<span class="reference-empty">—</span>';
        const customerHtml = _asStr(sale.customer_name).trim()
            ? escapeHtml(sale.customer_name)
            : '<span class="customer-empty">—</span>';

        html += `
            <tr>
                <td>
                    <span class="invoice-number">
                        ${escapeHtml(_asStr(sale.invoice_number))}
                    </span>
                </td>
                <td>${escapeHtml(formatDate(sale.created_at))}</td>
                <td>
                    <div class="cashier-cell">
                        <div class="cashier-avatar-sm">${escapeHtml(initials)}</div>
                        <span class="cashier-name-sm">${escapeHtml(cashierName)}</span>
                    </div>
                </td>
                <td>${customerHtml}</td>
                <td class="text-center">${_asNum(sale.total_items)}</td>
                <td>
                    <span class="payment-badge ${escapeHtml(_asStr(sale.payment_method))}">
                        ${escapeHtml(_asFormatPayment(sale.payment_method))}
                    </span>
                </td>
                <td>${refHtml}</td>
                <td class="text-right">
                    <span class="amount">
                        ₱${_asNum(sale.final_amount).toFixed(2)}
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


/* ============================================
   STATS
   ============================================ */

function _asUpdateStats(summary) {
    const setText = function (id, txt) {
        const el = document.getElementById(id);
        if (el) el.textContent = txt;
    };
    setText('statTransactions', _asNum(summary.total_transactions));
    setText('statRevenue', '₱' + _asNum(summary.total_revenue).toFixed(2));
    setText('statAvg', '₱' + _asNum(summary.average_sale).toFixed(2));
    setText('statDiscounts', '₱' + _asNum(summary.total_discounts).toFixed(2));
}


/* ============================================
   BREAKDOWNS
   ============================================ */

function _asRenderCashierBreakdown(breakdown) {
    const container = document.getElementById('cashierList');
    if (!container) return;

    if (!Array.isArray(breakdown) || breakdown.length === 0) {
        container.innerHTML =
            '<div style="text-align:center;color:#6c757d;padding:20px;">No sales in this range</div>';
        return;
    }

    let html = '';
    breakdown.forEach(function (c) {
        const name = _asStr(c.full_name || c.username) || 'Unknown';
        const initials = _asInitials(name);
        const isActive = String(_asFilters.cashier_id) === String(c.user_id);
        const saleCount = _asNum(c.sale_count);
        const avg = _asNum(c.average_sale);
        const total = _asNum(c.total_revenue);

        html += `
            <div class="cashier-item ${isActive ? 'active' : ''}"
                 onclick="filterByCashier(${c.user_id})">
                <div class="cashier-avatar">${escapeHtml(initials)}</div>
                <div class="cashier-meta">
                    <div class="cashier-name">${escapeHtml(name)}</div>
                    <small>
                        ${saleCount} sale${saleCount !== 1 ? 's' : ''}
                        · Avg ₱${avg.toFixed(2)}
                    </small>
                </div>
                <div class="cashier-revenue">₱${total.toFixed(2)}</div>
            </div>
        `;
    });
    container.innerHTML = html;
}

function filterByCashier(userId) {
    if (String(_asFilters.cashier_id) === String(userId)) {
        _asFilters.cashier_id = '';
        const el = document.getElementById('filterCashier');
        if (el) el.value = '';
    } else {
        _asFilters.cashier_id = userId;
        const el = document.getElementById('filterCashier');
        if (el) el.value = userId;
    }
    loadAllSales(1);
}

function _asRenderPaymentBreakdown(breakdown, totalRevenue) {
    const container = document.getElementById('paymentList');
    if (!container) return;

    if (!Array.isArray(breakdown) || breakdown.length === 0) {
        container.innerHTML =
            '<div style="text-align:center;color:#6c757d;padding:20px;">No data</div>';
        return;
    }

    const safeTotal = _asNum(totalRevenue);
    let html = '';
    breakdown.forEach(function (p) {
        const amt = _asNum(p.total);
        const cnt = _asNum(p.count);
        const percent = safeTotal > 0 ? (amt / safeTotal) * 100 : 0;
        const pct = isFinite(percent) ? percent.toFixed(1) : '0.0';

        html += `
            <div class="payment-item">
                <div class="payment-top">
                    <span class="payment-name">${escapeHtml(_asFormatPayment(p.method))}</span>
                    <span class="payment-count">${cnt} sale${cnt !== 1 ? 's' : ''}</span>
                </div>
                <div class="payment-bar">
                    <div class="payment-bar-fill" style="width:${pct}%"></div>
                </div>
                <div class="payment-total">₱${amt.toFixed(2)} (${pct}%)</div>
            </div>
        `;
    });
    container.innerHTML = html;
}


/* ============================================
   CASHIER DROPDOWN
   ============================================ */

function _asPopulateCashierDropdown(cashiers) {
    const select = document.getElementById('filterCashier');
    if (!select) return;

    const currentValue = select.value;
    select.innerHTML = '<option value="">All Cashiers</option>';

    if (Array.isArray(cashiers)) {
        cashiers.forEach(function (c) {
            if (!c || c.id === null || c.id === undefined) return;
            const opt = document.createElement('option');
            opt.value = c.id;
            const label = _asStr(c.full_name || c.username) || ('User ' + c.id);
            const role = _asStr(c.role);
            opt.textContent = role ? (label + ' (' + role + ')') : label;
            select.appendChild(opt);
        });
    }

    if (currentValue) select.value = currentValue;
}


/* ============================================
   PAGINATION
   ============================================ */

function _asUpdatePagination(pagination) {
    const wrapper = document.getElementById('paginationWrapper');
    const info = document.getElementById('paginationInfo');
    const controls = document.getElementById('paginationControls');
    if (!wrapper || !info || !controls) return;

    const totalPages = _asNum(pagination.pages);
    const currentPage = _asNum(pagination.page) || 1;
    const total = _asNum(pagination.total);
    const perPage = _asNum(pagination.per_page) || _AS_PER_PAGE;

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
    html += `<button onclick="loadAllSales(${currentPage - 1})"
                     ${currentPage <= 1 ? 'disabled' : ''}>
                <i class="fas fa-chevron-left"></i>
             </button>`;

    if (startPage > 1) {
        html += `<button onclick="loadAllSales(1)">1</button>`;
        if (startPage > 2) {
            html += `<span style="padding:0 8px;color:#6c757d;">...</span>`;
        }
    }
    for (let i = startPage; i <= endPage; i++) {
        const active = i === currentPage;
        html += `<button onclick="loadAllSales(${i})"
                         class="${active ? 'active' : ''}">${i}</button>`;
    }
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            html += `<span style="padding:0 8px;color:#6c757d;">...</span>`;
        }
        html += `<button onclick="loadAllSales(${totalPages})">${totalPages}</button>`;
    }
    html += `<button onclick="loadAllSales(${currentPage + 1})"
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
    const fc = document.getElementById('filterCashier');

    _asFilters.start_date = sd ? sd.value : '';
    _asFilters.end_date = ed ? ed.value : '';
    _asFilters.payment_method = fp ? fp.value : '';
    _asFilters.cashier_id = fc ? fc.value : '';

    loadAllSales(1);
}

function resetFilters() {
    const today = new Date();
    const oneYearAgo = new Date();
    oneYearAgo.setFullYear(today.getFullYear() - 1);

    const sd = document.getElementById('filterStartDate');
    const ed = document.getElementById('filterEndDate');
    const fp = document.getElementById('filterPayment');
    const fc = document.getElementById('filterCashier');

    if (sd) sd.value = _asDateInput(oneYearAgo);
    if (ed) ed.value = _asDateInput(today);
    if (fp) fp.value = '';
    if (fc) fc.value = '';

    _asFilters = {
        start_date: sd ? sd.value : '',
        end_date: ed ? ed.value : '',
        payment_method: '',
        cashier_id: ''
    };

    loadAllSales(1);
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
            _asReceipt = data.data;
            body.textContent = _asBuildReceiptText(data.data);
        } else {
            body.textContent = 'Failed to load receipt: ' +
                ((data && data.message) || 'Unknown error');
        }
    })
    .catch(function (err) {
        console.error('[all_sales] receipt:', err);
        body.textContent = 'Failed to load receipt. Please try again.';
    });
}

function _asBuildReceiptText(r) {
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
    out.push('Invoice:  ' + _asStr(r.invoice_number));
    out.push('Date:     ' + formatDate(r.date));
    if (_asStr(r.customer).trim()) out.push('Customer: ' + r.customer);
    out.push('Cashier:  ' + _asStr(r.cashier));
    out.push(line);
    out.push(pad('Item', 20) + pad('Qty', 5, 'right') + pad('Total', 15, 'right'));
    out.push(line);

    (r.items || []).forEach(function (item) {
        out.push(
            pad(_asStr(item.name).substring(0, 19), 20) +
            pad(_asNum(item.quantity), 5, 'right') +
            pad('₱' + _asNum(item.subtotal).toFixed(2), 15, 'right')
        );
    });

    out.push(line);
    out.push(pad('Subtotal', 25) + pad('₱' + _asNum(r.subtotal).toFixed(2), 15, 'right'));
    if (_asNum(r.discount) > 0) {
        out.push(pad('Discount', 25) + pad('-₱' + _asNum(r.discount).toFixed(2), 15, 'right'));
    }
    out.push(pad('Tax', 25) + pad('₱' + _asNum(r.tax).toFixed(2), 15, 'right'));
    out.push(pad('TOTAL', 25) + pad('₱' + _asNum(r.total).toFixed(2), 15, 'right'));
    out.push(line);
    out.push(pad('Payment Method', 25) + pad(_asFormatPayment(r.payment_method), 15, 'right'));
    out.push(pad('Amount Paid', 25) + pad('₱' + _asNum(r.payment_amount).toFixed(2), 15, 'right'));
    out.push(pad('Change', 25) + pad('₱' + _asNum(r.change).toFixed(2), 15, 'right'));
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
    _asReceipt = null;
}

function printReceipt() {
    if (!_asReceipt) {
        showToast('No receipt to print', 'warning');
        return;
    }
    const win = window.open('', '_blank', 'width=400,height=600');
    if (!win) {
        showToast('Please allow popups to print', 'warning');
        return;
    }

    const r = _asReceipt;
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
    html += '<p>' + escapeHtml(_asStr(r.date)) + '</p>';
    html += '<p>Invoice: ' + escapeHtml(_asStr(r.invoice_number)) + '</p>';
    if (_asStr(r.customer).trim()) {
        html += '<p>Customer: ' + escapeHtml(r.customer) + '</p>';
    }
    html += '</div>';
    html += '<table class="items"><tr><th style="text-align:left;">Item</th>';
    html += '<th class="text-right">Qty</th><th class="text-right">Price</th>';
    html += '<th class="text-right">Total</th></tr>';

    (r.items || []).forEach(function (item) {
        html += '<tr><td>' + escapeHtml(_asStr(item.name)) + '</td>';
        html += '<td class="text-right">' + _asNum(item.quantity) + '</td>';
        html += '<td class="text-right">' + _asNum(item.price).toFixed(2) + '</td>';
        html += '<td class="text-right">' + _asNum(item.subtotal).toFixed(2) + '</td></tr>';
    });

    html += '</table>';
    html += '<div class="totals">';
    html += '<div class="total-line"><span>Subtotal</span><span>' +
            _asNum(r.subtotal).toFixed(2) + '</span></div>';
    if (_asNum(r.discount) > 0) {
        html += '<div class="total-line"><span>Discount</span><span>-' +
                _asNum(r.discount).toFixed(2) + '</span></div>';
    }
    html += '<div class="total-line"><span>Tax</span><span>' +
            _asNum(r.tax).toFixed(2) + '</span></div>';
    html += '<div class="total-line grand-total"><span>TOTAL</span><span>' +
            _asNum(r.total).toFixed(2) + '</span></div>';
    html += '</div>';
    html += '<div style="border-top:1px dashed #000;margin:8px 0;"></div>';
    html += '<div class="total-line"><span>Payment</span><span>' +
            _asNum(r.payment_amount).toFixed(2) + '</span></div>';
    html += '<div class="total-line"><span>Change</span><span>' +
            _asNum(r.change).toFixed(2) + '</span></div>';
    if (r.payment_reference) {
        html += '<div class="total-line"><span>GCash Ref</span><span>•••' +
                escapeHtml(r.payment_reference) + '</span></div>';
    }
    html += '<div class="total-line"><span>Cashier</span><span>' +
            escapeHtml(_asStr(r.cashier)) + '</span></div>';
    html += '<div class="footer"><p>Thank you for your purchase!</p></div>';
    html += '<script>window.print();window.close();<\/script>';
    html += '</body></html>';

    win.document.write(html);
    win.document.close();
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
