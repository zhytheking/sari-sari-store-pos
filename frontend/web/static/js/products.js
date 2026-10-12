/**
 * products.js — CANONICAL PRODUCTS PAGE LOGIC
 *
 * ============================================================
 * READ THIS BEFORE EDITING
 * ============================================================
 *
 * Depends on api-client.js (loaded by base.html).
 *
 * This file owns:
 *   - Loading the product list from /api/v1/products
 *   - Rendering the products table
 *   - Category filter buttons
 *   - Stock type filter dropdown
 *   - Search input
 *   - Pagination
 *
 * This file does NOT own:
 *   - escapeHtml / formatCurrency / formatDate (api-client.js)
 *   - The navbar, footer, or global toast container (base.html)
 *
 * ============================================================
 */

let allProducts = [];
let currentCategory = 'all';
let currentStockType = 'all';
let currentPage = 1;
let totalPages = 1;
let perPage = 20;


/* ============================================================
   SAFE HELPERS — never throw on null/undefined
   ============================================================ */

function _safeStr(v) {
    return (v === null || v === undefined) ? '' : String(v);
}

function _safeNum(v) {
    const n = Number(v);
    return isNaN(n) ? 0 : n;
}


/* ============================================================
   INIT
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {
    if (!document.getElementById('productsTableBody')) return;
    loadProducts(1);
    loadCategories();
});


/* ============================================================
   LOAD PRODUCTS
   ============================================================ */

function loadProducts(page) {
    page = page || 1;
    currentPage = page;

    const tbody = document.getElementById('productsTableBody');
    const emptyState = document.getElementById('emptyState');
    if (!tbody) return;

    tbody.innerHTML = `
        <tr>
            <td colspan="7" style="text-align:center;padding:40px;">
                <div class="loading-spinner"
                     style="margin:0 auto 12px;"></div>
                <p style="color:#6c757d;margin:0;">Loading products…</p>
            </td>
        </tr>
    `;
    if (emptyState) emptyState.style.display = 'none';

    const params = { page: page, per_page: perPage, active: 'true' };
    if (currentCategory !== 'all') params.category = currentCategory;

    const searchEl = document.getElementById('productSearch');
    const q = searchEl ? searchEl.value.trim() : '';
    if (q.length >= 2) params.search = q;

    API.products.list(params)
        .then(function (data) {
            if (!data || !data.success) {
                throw new Error((data && data.message) ||
                                'Failed to load products');
            }
            const payload = data.data || {};
            allProducts = Array.isArray(payload.items)
                ? payload.items
                : [];
            applyClientFilter();
            updateProductCount(
                (payload.pagination && payload.pagination.total) ||
                allProducts.length
            );
            updatePagination(payload.pagination);
        })
        .catch(function (err) {
            console.error('[products] load failed:', err);
            renderLoadError(err.message || 'Unknown error');
        });
}


function renderLoadError(message) {
    const tbody = document.getElementById('productsTableBody');
    if (!tbody) return;

    tbody.innerHTML = `
        <tr>
            <td colspan="7" style="text-align:center;padding:40px;">
                <i class="fas fa-exclamation-circle"
                   style="font-size:2.5rem;color:#dc3545;display:block;
                          margin-bottom:12px;"></i>
                <h3 style="margin:0 0 6px 0;color:#1a1a2e;">
                    Failed to load products
                </h3>
                <p style="color:#6c757d;font-size:0.85rem;margin:0 0 14px 0;">
                    ${escapeHtml(message)}
                </p>
                <button onclick="loadProducts(1)"
                        style="padding:10px 24px;background:#2d6a4f;
                               color:white;border:none;border-radius:10px;
                               font-weight:600;cursor:pointer;">
                    <i class="fas fa-sync"></i> Retry
                </button>
            </td>
        </tr>
    `;
}


/* ============================================================
   CATEGORIES
   ============================================================ */

function loadCategories() {
    const container = document.getElementById('categoriesContainer');
    if (!container) return;

    API.products.categories.list()
        .then(function (data) {
            if (!data || !data.success) return;

            let html = `
                <button class="category-btn active"
                        data-category="all"
                        onclick="filterCategory('all')">
                    <i class="fas fa-th-list"></i> All
                </button>
            `;

            (data.data || []).forEach(function (c) {
                const safeName = escapeHtml(c.name);
                const jsName = _safeStr(c.name)
                    .replace(/\\/g, '\\\\')
                    .replace(/'/g, "\\'");
                html += `
                    <button class="category-btn"
                            data-category="${safeName}"
                            onclick="filterCategory('${jsName}')">
                        <i class="fas fa-tag"></i> ${safeName}
                    </button>
                `;
            });
            container.innerHTML = html;
        })
        .catch(function (err) {
            console.error('[products] categories:', err);
        });
}

function filterCategory(category) {
    currentCategory = category;
    currentPage = 1;
    document.querySelectorAll('.category-btn').forEach(function (btn) {
        btn.classList.toggle('active', btn.dataset.category === category);
    });
    applyClientFilter();
}

function filterByStockType() {
    const sel = document.getElementById('stockTypeFilter');
    currentStockType = sel ? sel.value : 'all';
    applyClientFilter();
}

function searchProducts() {
    applyClientFilter();
}

function clearSearch() {
    const el = document.getElementById('productSearch');
    if (el) el.value = '';
    applyClientFilter();
}

function resetFilters() {
    const searchEl = document.getElementById('productSearch');
    if (searchEl) searchEl.value = '';

    const typeEl = document.getElementById('stockTypeFilter');
    if (typeEl) typeEl.value = 'all';

    currentCategory = 'all';
    currentStockType = 'all';
    currentPage = 1;

    document.querySelectorAll('.category-btn').forEach(function (btn) {
        btn.classList.toggle('active', btn.dataset.category === 'all');
    });

    loadProducts(1);
}


/* ============================================================
   CLIENT-SIDE FILTER
   ============================================================ */

function applyClientFilter() {
    let list = Array.isArray(allProducts) ? allProducts.slice() : [];

    if (currentCategory !== 'all') {
        list = list.filter(function (p) {
            return p.category_name === currentCategory;
        });
    }
    if (currentStockType !== 'all') {
        list = list.filter(function (p) {
            return p.stock_type === currentStockType;
        });
    }

    const searchEl = document.getElementById('productSearch');
    const q = (searchEl ? searchEl.value : '').toLowerCase().trim();
    if (q.length >= 1) {
        list = list.filter(function (p) {
            return _safeStr(p.name).toLowerCase().indexOf(q) !== -1
                || _safeStr(p.barcode).toLowerCase().indexOf(q) !== -1
                || _safeStr(p.category_name).toLowerCase().indexOf(q) !== -1;
        });
    }

    renderProducts(list);
    updateProductCount(list.length);
}


/* ============================================================
   SORT + RENDER
   ============================================================ */

function sortProducts(items) {
    function priority(p) {
        const stock = _safeNum(p.stock_quantity);
        const minStock = _safeNum(p.min_stock_level) || 10;
        if (stock <= 0) return 0;
        if (stock <= minStock) return 1;
        return 2;
    }
    return items.slice().sort(function (a, b) {
        const pa = priority(a);
        const pb = priority(b);
        if (pa !== pb) return pa - pb;
        return _safeStr(a.name).localeCompare(_safeStr(b.name));
    });
}

function renderProducts(products) {
    const tbody = document.getElementById('productsTableBody');
    const emptyState = document.getElementById('emptyState');
    if (!tbody) return;

    if (!Array.isArray(products) || products.length === 0) {
        if (emptyState) emptyState.style.display = 'block';
        tbody.innerHTML = '';
        return;
    }

    if (emptyState) emptyState.style.display = 'none';

    const sorted = sortProducts(products);
    let html = '';

    sorted.forEach(function (p) {
        const stock = _safeNum(p.stock_quantity);
        const minStock = _safeNum(p.min_stock_level) || 10;

        let status, statusClass, rowClass;
        if (stock <= 0) {
            status = 'Out of Stock';
            statusClass = 'out';
            rowClass = 'row-out-of-stock';
        } else if (stock <= minStock) {
            status = 'Low Stock';
            statusClass = 'low';
            rowClass = 'row-low-stock';
        } else {
            status = 'In Stock';
            statusClass = 'in-stock';
            rowClass = '';
        }

        const imageHtml = p.product_image
            ? '<img src="' + escapeHtml(p.product_image) +
              '" class="product-image-thumb" alt="">'
            : '<div class="product-image-thumb" ' +
              'style="display:flex;align-items:center;' +
              'justify-content:center;color:#adb5bd;">' +
              '<i class="fas fa-box"></i></div>';

        html += `
            <tr class="${rowClass}"
                onclick="window.location.href='/product/${p.id}'">
                <td>${imageHtml}</td>
                <td class="product-name-cell">${escapeHtml(_safeStr(p.name))}</td>
                <td>${p.barcode
                        ? escapeHtml(_safeStr(p.barcode))
                        : '<span style="color:#adb5bd;">—</span>'}</td>
                <td>${escapeHtml(_safeStr(p.category_name) || 'Uncategorized')}</td>
                <td class="text-right">
                    ₱${_safeNum(p.selling_price).toFixed(2)}
                </td>
                <td class="text-center">${stock}</td>
                <td class="text-center">
                    <span class="stock-badge ${statusClass}">${status}</span>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

function viewProduct(id) {
    window.location.href = '/product/' + id;
}

function updateProductCount(count) {
    const el = document.getElementById('productCount');
    if (el) el.textContent = count || 0;
}


/* ============================================================
   PAGINATION
   ============================================================ */

function updatePagination(pagination) {
    const container = document.getElementById('paginationContainer');
    if (!container) return;

    if (!pagination || pagination.pages <= 1) {
        container.innerHTML = '';
        return;
    }

    const totalPages = pagination.pages;
    const currentPage = pagination.page;
    let html = '';

    html += '<button class="btn btn-sm" ' +
            'onclick="loadProducts(' + (currentPage - 1) + ')" ' +
            (currentPage <= 1 ? 'disabled' : '') + '>' +
            '<i class="fas fa-chevron-left"></i></button>';

    const start = Math.max(1, currentPage - 2);
    const end = Math.min(totalPages, start + 4);

    if (start > 1) {
        html += '<button class="btn btn-sm" ' +
                'onclick="loadProducts(1)">1</button>';
        if (start > 2) html += '<span style="padding:0 6px;">…</span>';
    }

    for (let i = start; i <= end; i++) {
        const active = i === currentPage;
        html += '<button class="btn btn-sm ' +
                (active ? 'btn-primary' : '') + '" ' +
                'onclick="loadProducts(' + i + ')">' + i + '</button>';
    }

    if (end < totalPages) {
        if (end < totalPages - 1) {
            html += '<span style="padding:0 6px;">…</span>';
        }
        html += '<button class="btn btn-sm" ' +
                'onclick="loadProducts(' + totalPages + ')">' +
                totalPages + '</button>';
    }

    html += '<button class="btn btn-sm" ' +
            'onclick="loadProducts(' + (currentPage + 1) + ')" ' +
            (currentPage >= totalPages ? 'disabled' : '') + '>' +
            '<i class="fas fa-chevron-right"></i></button>';

    container.innerHTML = html;
}
