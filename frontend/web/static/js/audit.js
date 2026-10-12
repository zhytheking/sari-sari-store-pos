/**
 * audit.js — Audit Log page.
 *
 * Depends on api-client.js.
 */

let _auditPage = 1;
let _auditFilters = {
    start_date: '',
    end_date: '',
    category: '',
    result: '',
    search: '',
};
const _AUDIT_PER_PAGE = 30;

function _auditDateInput(d) {
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
    const weekAgo = new Date();
    weekAgo.setDate(today.getDate() - 7);

    const sd = document.getElementById('filterStartDate');
    const ed = document.getElementById('filterEndDate');
    if (sd) sd.value = _auditDateInput(weekAgo);
    if (ed) ed.value = _auditDateInput(today);

    _auditFilters.start_date = sd ? sd.value : '';
    _auditFilters.end_date = ed ? ed.value : '';

    const search = document.getElementById('filterSearch');
    if (search) {
        search.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') applyFilters();
        });
    }

    loadSummary();
    loadAudit(1);
});


/* ============================================
   SUMMARY
   ============================================ */

function loadSummary() {
    API.audit.summary()
        .then(function (data) {
            if (!data || !data.success) return;
            const d = data.data || {};
            const day = d.last_24h || {};

            const setText = function (id, txt) {
                const el = document.getElementById(id);
                if (el) el.textContent = txt;
            };

            setText('statAuth', day.auth || 0);
            setText('statSales', day.sale || 0);
            setText('statStock', day.stock || 0);
            setText('statFailures', d.failures_last_24h || 0);
        })
        .catch(function (err) {
            console.error('[audit] summary:', err);
        });
}


/* ============================================
   LOAD
   ============================================ */

function loadAudit(page) {
    _auditPage = page || 1;
    const container = document.getElementById('auditTableContainer');
    if (!container) return;

    container.innerHTML = `
        <div class="loading-state">
            <div class="loading-spinner"></div>
            <p>Loading audit log...</p>
        </div>
    `;

    const params = {
        page: _auditPage,
        per_page: _AUDIT_PER_PAGE,
    };
    if (_auditFilters.start_date) params.start_date = _auditFilters.start_date;
    if (_auditFilters.end_date) params.end_date = _auditFilters.end_date;
    if (_auditFilters.category) params.category = _auditFilters.category;
    if (_auditFilters.result) params.result = _auditFilters.result;
    if (_auditFilters.search) params.search = _auditFilters.search;

    API.audit.logs(params)
        .then(function (data) {
            if (!data || !data.success) {
                throw new Error((data && data.message) || 'Failed to load');
            }
            const payload = data.data || {};
            _auditRenderTable(payload.items || []);
            _auditUpdatePagination(payload.pagination || {});
        })
        .catch(function (err) {
            console.error('[audit] load:', err);
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-exclamation-circle"></i>
                    <h3>Failed to load audit log</h3>
                    <p>${escapeHtml(err.message || 'Unknown error')}</p>
                    <button class="btn btn-primary"
                            onclick="loadAudit(1)"
                            style="padding:10px 24px;border:none;
                                   border-radius:10px;background:#2d6a4f;
                                   color:white;cursor:pointer;margin-top:10px;">
                        <i class="fas fa-sync"></i> Retry
                    </button>
                </div>
            `;
        });
}


/* ============================================
   RENDER
   ============================================ */

function _auditRenderTable(items) {
    const container = document.getElementById('auditTableContainer');
    if (!container) return;

    if (!Array.isArray(items) || items.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-history"></i>
                <h3>No audit entries found</h3>
                <p>Try widening the date range or clearing filters</p>
            </div>
        `;
        return;
    }

    let html = `
        <table class="audit-table">
            <thead>
                <tr>
                    <th style="width:150px;">Time</th>
                    <th style="width:150px;">User</th>
                    <th style="width:100px;">Category</th>
                    <th style="width:170px;">Action</th>
                    <th>Details</th>
                    <th style="width:90px;">Result</th>
                    <th style="width:120px;">IP</th>
                </tr>
            </thead>
            <tbody>
    `;

    items.forEach(function (e) {
        const cat = safeStr(e.category) || 'system';
        const result = safeStr(e.result) || 'success';
        const username = safeStr(e.username) || 'System';
        const fullName = safeStr(e.full_name) || '—';
        const role = safeStr(e.role) || 'system';

        const time = formatDate(e.timestamp);

        html += `
            <tr>
                <td class="time-cell">${escapeHtml(time)}</td>
                <td>
                    <div class="user-cell">
                        <span class="username">${escapeHtml(username)}</span>
                        <span class="role">${escapeHtml(role)}</span>
                    </div>
                </td>
                <td>
                    <span class="category-badge ${escapeHtml(cat)}">
                        ${escapeHtml(cat)}
                    </span>
                </td>
                <td>
                    <span class="action-cell">${escapeHtml(safeStr(e.action))}</span>
                </td>
                <td class="details-cell">${escapeHtml(safeStr(e.details))}</td>
                <td>
                    <span class="result-badge ${escapeHtml(result)}">
                        ${escapeHtml(result)}
                    </span>
                </td>
                <td class="ip-cell">${escapeHtml(safeStr(e.ip_address) || '—')}</td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}

function _auditUpdatePagination(pagination) {
    const wrapper = document.getElementById('paginationWrapper');
    const info = document.getElementById('paginationInfo');
    const controls = document.getElementById('paginationControls');
    if (!wrapper || !info || !controls) return;

    const totalPages = safeNum(pagination.pages);
    const currentPage = safeNum(pagination.page) || 1;
    const total = safeNum(pagination.total);
    const perPage = safeNum(pagination.per_page) || _AUDIT_PER_PAGE;

    if (totalPages <= 1) {
        wrapper.style.display = 'none';
        return;
    }

    wrapper.style.display = 'flex';

    const startItem = (currentPage - 1) * perPage + 1;
    const endItem = Math.min(currentPage * perPage, total);
    info.textContent =
        'Showing ' + startItem + '-' + endItem + ' of ' + total + ' entries';

    let startPage = Math.max(1, currentPage - 2);
    let endPage = Math.min(totalPages, startPage + 4);
    if (endPage - startPage < 4) startPage = Math.max(1, endPage - 4);

    let html = '';
    html += `<button onclick="loadAudit(${currentPage - 1})"
                     ${currentPage <= 1 ? 'disabled' : ''}>
                <i class="fas fa-chevron-left"></i>
             </button>`;

    if (startPage > 1) {
        html += `<button onclick="loadAudit(1)">1</button>`;
        if (startPage > 2) {
            html += `<span style="padding:0 8px;color:#6c757d;">...</span>`;
        }
    }
    for (let i = startPage; i <= endPage; i++) {
        const active = i === currentPage;
        html += `<button onclick="loadAudit(${i})"
                         class="${active ? 'active' : ''}">${i}</button>`;
    }
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            html += `<span style="padding:0 8px;color:#6c757d;">...</span>`;
        }
        html += `<button onclick="loadAudit(${totalPages})">${totalPages}</button>`;
    }
    html += `<button onclick="loadAudit(${currentPage + 1})"
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
    const cat = document.getElementById('filterCategory');
    const res = document.getElementById('filterResult');
    const s = document.getElementById('filterSearch');

    _auditFilters.start_date = sd ? sd.value : '';
    _auditFilters.end_date = ed ? ed.value : '';
    _auditFilters.category = cat ? cat.value : '';
    _auditFilters.result = res ? res.value : '';
    _auditFilters.search = s ? s.value.trim() : '';

    loadAudit(1);
}

function resetFilters() {
    const today = new Date();
    const weekAgo = new Date();
    weekAgo.setDate(today.getDate() - 7);

    const sd = document.getElementById('filterStartDate');
    const ed = document.getElementById('filterEndDate');
    const cat = document.getElementById('filterCategory');
    const res = document.getElementById('filterResult');
    const s = document.getElementById('filterSearch');

    if (sd) sd.value = _auditDateInput(weekAgo);
    if (ed) ed.value = _auditDateInput(today);
    if (cat) cat.value = '';
    if (res) res.value = '';
    if (s) s.value = '';

    _auditFilters = {
        start_date: sd ? sd.value : '',
        end_date: ed ? ed.value : '',
        category: '',
        result: '',
        search: '',
    };

    loadAudit(1);
}
