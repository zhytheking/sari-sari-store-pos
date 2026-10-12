/**
 * stocks.js — Stock Management page for owners.
 *
 * Depends on api-client.js.
 *
 * Owns:
 *   - Product table with selection
 *   - Add Product modal
 *   - Add / Remove / Adjust Stock modals
 *   - Delete Product modal
 */

let _stkProducts = [];
let _stkProductsById = {};
let _stkSelectedProductId = null;
let _stkCurrentStockAction = null;
let _stkCurrentDeleteProductId = null;
let _stkCategoriesCache = [];
let _stkHasShownStartupNotification = false;

const _STK_REASONS = {
    add: ['Restock', 'New shipment', 'Return from customer', 'Other'],
    remove: ['Damaged', 'Expired', 'Return to supplier', 'Wastage', 'Stolen/Lost', 'Other'],
    adjust: ['Inventory count correction', 'Physical count', 'Other']
};


/* ============================================
   SAFE HELPERS
   ============================================ */

function _stkStr(v) { return (v === null || v === undefined) ? '' : String(v); }
function _stkNum(v) { const n = Number(v); return isNaN(n) ? 0 : n; }


/* ============================================
   INIT
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
    loadProducts();
    loadCategories();

    ['stockModal', 'addProductModal', 'deleteModal'].forEach(function (id) {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('click', function (e) {
                if (e.target === el) {
                    if (id === 'stockModal') closeStockModal();
                    else if (id === 'addProductModal') closeAddProductModal();
                    else closeDeleteModal();
                }
            });
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeStockModal();
            closeAddProductModal();
            closeDeleteModal();
        }
    });
});


/* ============================================
   LOAD PRODUCTS
   ============================================ */

function loadProducts() {
    API.products.list({ per_page: 500, active: 'all' })
        .then(function (data) {
            if (!data || !data.success) {
                throw new Error((data && data.message) || 'Failed');
            }
            _stkProducts = (data.data && data.data.items) || [];
            _stkProductsById = {};
            _stkProducts.forEach(function (p) { _stkProductsById[p.id] = p; });
            _stkRenderTable(_stkProducts);
            _stkUpdateStats(_stkProducts);
            _stkShowStartupNotification(_stkProducts);
            _stkUpdateSelectionHint();
        })
        .catch(function (err) {
            console.error('[stocks] load failed:', err);
            showToast('Failed to load products', 'error');
        });
}


/* ============================================
   CATEGORIES
   ============================================ */

function loadCategories() {
    API.products.categories.list()
        .then(function (data) {
            if (!data || !data.success) return;
            _stkCategoriesCache = data.data || [];
            _stkPopulateCategoryDropdown();
        })
        .catch(function (err) {
            console.error('[stocks] categories:', err);
        });
}

function _stkPopulateCategoryDropdown() {
    const sel = document.getElementById('apCategory');
    if (!sel) return;
    let html = '<option value="">— Uncategorized —</option>';
    _stkCategoriesCache.forEach(function (c) {
        html += '<option value="' + c.id + '">' + escapeHtml(c.name) + '</option>';
    });
    sel.innerHTML = html;
}


/* ============================================
   TABLE
   ============================================ */

function _stkSortProducts(items) {
    function priority(p) {
        const stock = _stkNum(p.stock_quantity);
        const min = _stkNum(p.min_stock_level) || 10;
        if (stock <= 0) return 0;
        if (stock <= min) return 1;
        return 2;
    }
    return items.slice().sort(function (a, b) {
        const pa = priority(a), pb = priority(b);
        if (pa !== pb) return pa - pb;
        return _stkStr(a.name).localeCompare(_stkStr(b.name));
    });
}

function _stkRenderTable(items) {
    const tbody = document.getElementById('stockTableBody');
    if (!tbody) return;

    if (!items || items.length === 0) {
        tbody.innerHTML = `
            <tr><td colspan="6" style="text-align:center;padding:40px;color:#6c757d;">
                <i class="fas fa-box-open" style="font-size:2rem;display:block;margin-bottom:10px;"></i>
                No products found
            </td></tr>
        `;
        return;
    }

    const sorted = _stkSortProducts(items);
    let html = '';

    sorted.forEach(function (product) {
        const stock = _stkNum(product.stock_quantity);
        const minStock = _stkNum(product.min_stock_level) || 10;

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

        const isSelected = product.id === _stkSelectedProductId ? 'selected' : '';
        const imageHtml = product.product_image
            ? '<img src="' + escapeHtml(product.product_image) +
              '" class="product-image-thumb" alt="' + escapeHtml(product.name) + '">'
            : '<div class="product-image-thumb" style="display:flex;align-items:center;justify-content:center;color:#adb5bd;"><i class="fas fa-box"></i></div>';

        html += `
            <tr class="${rowClass} ${isSelected}"
                data-product-id="${product.id}"
                onclick="selectRow(${product.id})">
                <td>${imageHtml}</td>
                <td><strong>${escapeHtml(_stkStr(product.name))}</strong></td>
                <td>${escapeHtml(_stkStr(product.category_name) || 'Uncategorized')}</td>
                <td><strong>${stock}</strong></td>
                <td>${minStock}</td>
                <td><span class="stock-badge ${statusClass}">${status}</span></td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

function filterTable() {
    const input = document.getElementById('searchInput');
    const q = input ? input.value.toLowerCase().trim() : '';
    if (!q) {
        _stkRenderTable(_stkProducts);
        return;
    }
    const filtered = _stkProducts.filter(function (p) {
        return _stkStr(p.name).toLowerCase().indexOf(q) !== -1 ||
               _stkStr(p.category_name).toLowerCase().indexOf(q) !== -1;
    });
    _stkRenderTable(filtered);
}


/* ============================================
   STATS
   ============================================ */

function _stkUpdateStats(products) {
    const total = products.length;
    let lowStock = 0, outOfStock = 0, totalValue = 0;

    products.forEach(function (p) {
        const stock = _stkNum(p.stock_quantity);
        const min = _stkNum(p.min_stock_level) || 10;
        if (stock <= 0) outOfStock += 1;
        else if (stock <= min) lowStock += 1;
        totalValue += stock * _stkNum(p.purchase_price);
    });

    const t = document.getElementById('totalProducts');
    if (t) t.textContent = total;
    const l = document.getElementById('lowStockCount');
    if (l) l.textContent = lowStock;
    const o = document.getElementById('outOfStockCount');
    if (o) o.textContent = outOfStock;
    const v = document.getElementById('inStockValue');
    if (v) v.textContent = '₱' + totalValue.toFixed(2);
}


/* ============================================
   STARTUP BANNER
   ============================================ */

function _stkShowStartupNotification(products) {
    if (_stkHasShownStartupNotification) return;
    _stkHasShownStartupNotification = true;

    const outOfStock = products.filter(function (p) {
        return _stkNum(p.stock_quantity) === 0;
    });
    const lowStock = products.filter(function (p) {
        const s = _stkNum(p.stock_quantity);
        const m = _stkNum(p.min_stock_level) || 10;
        return s > 0 && s <= m;
    });

    if (!outOfStock.length && !lowStock.length) return;

    const banner = document.getElementById('stockBanner');
    const bannerText = document.getElementById('stockBannerText');
    if (banner && bannerText) {
        const parts = [];
        if (outOfStock.length) parts.push('<strong>' + outOfStock.length + ' out of stock</strong>');
        if (lowStock.length) parts.push('<strong>' + lowStock.length + ' low stock</strong>');
        bannerText.innerHTML = '⚠️ ' + parts.join(' · ') + ' — needs your attention.';
        banner.style.display = 'flex';
    }
}


/* ============================================
   ROW SELECTION
   ============================================ */

function selectRow(productId) {
    if (_stkSelectedProductId === productId) {
        _stkSelectedProductId = null;
    } else {
        _stkSelectedProductId = productId;
    }

    document.querySelectorAll('#stockTableBody tr[data-product-id]').forEach(function (tr) {
        const pid = parseInt(tr.getAttribute('data-product-id'), 10);
        tr.classList.toggle('selected', pid === _stkSelectedProductId);
    });

    _stkUpdateSelectionHint();
}

function _stkUpdateSelectionHint() {
    const hint = document.getElementById('selectionHint');
    const nameEl = document.getElementById('selectedProductName');
    const stockEl = document.getElementById('selectedProductStock');
    if (!hint || !nameEl || !stockEl) return;

    if (_stkSelectedProductId && _stkProductsById[_stkSelectedProductId]) {
        const p = _stkProductsById[_stkSelectedProductId];
        nameEl.textContent = p.name;
        stockEl.textContent = _stkNum(p.stock_quantity);
        hint.classList.add('visible');
    } else {
        hint.classList.remove('visible');
    }
}


/* ============================================
   STOCK MODAL
   ============================================ */

function openStockModal(action) {
    if (!_stkSelectedProductId || !_stkProductsById[_stkSelectedProductId]) {
        showToast('⚠️ Select a product from the table first', 'warning');
        return;
    }

    const product = _stkProductsById[_stkSelectedProductId];
    _stkCurrentStockAction = action;

    const titles = { add: 'Add Stock', remove: 'Remove Stock', adjust: 'Adjust Stock' };
    const icons = { add: '📥', remove: '📤', adjust: '⚙️' };
    const qtyLabels = {
        add: 'Quantity',
        remove: 'Quantity',
        adjust: 'New Quantity (exact)'
    };

    const iconEl = document.getElementById('stockModalIcon');
    if (iconEl) iconEl.textContent = icons[action];
    const titleEl = document.getElementById('stockModalTitle');
    if (titleEl) titleEl.textContent = titles[action] + ' — ' + product.name;
    const subEl = document.getElementById('stockModalSubtitle');
    if (subEl) subEl.innerHTML = 'Current stock: <strong>' +
        _stkNum(product.stock_quantity) + '</strong>';
    const qtyLabelEl = document.getElementById('stockQtyLabel');
    if (qtyLabelEl) qtyLabelEl.textContent = qtyLabels[action];

    const qtyInput = document.getElementById('stockQtyInput');
    if (qtyInput) {
        qtyInput.value = (action === 'adjust') ? _stkNum(product.stock_quantity) : 1;
        qtyInput.min = (action === 'adjust') ? '0' : '1';
    }

    const reasonEl = document.getElementById('stockReasonSelect');
    if (reasonEl) {
        reasonEl.innerHTML = _STK_REASONS[action].map(function (r) {
            return '<option value="' + escapeHtml(r) + '">' + escapeHtml(r) + '</option>';
        }).join('');
    }

    const submitBtn = document.getElementById('stockSubmitBtn');
    if (submitBtn) {
        submitBtn.className = 'btn';
        if (action === 'add') {
            submitBtn.classList.add('btn-add-stock');
            submitBtn.textContent = 'Add Stock';
        } else if (action === 'remove') {
            submitBtn.classList.add('btn-remove-stock');
            submitBtn.textContent = 'Remove Stock';
        } else {
            submitBtn.classList.add('btn-adjust-stock');
            submitBtn.textContent = 'Set Quantity';
        }
    }

    const noteEl = document.getElementById('stockNoteInput');
    if (noteEl) noteEl.value = '';
    const errEl = document.getElementById('stockModalError');
    if (errEl) errEl.classList.remove('visible');

    const modal = document.getElementById('stockModal');
    if (modal) modal.classList.add('active');
    setTimeout(function () {
        if (qtyInput) { qtyInput.focus(); qtyInput.select(); }
    }, 80);
}

function closeStockModal() {
    const modal = document.getElementById('stockModal');
    if (modal) modal.classList.remove('active');
    _stkCurrentStockAction = null;
}

function submitStockForm(event) {
    event.preventDefault();
    if (!_stkCurrentStockAction) return;

    const product = _stkProductsById[_stkSelectedProductId];
    if (!product) {
        _stkShowModalError('stockModalError', 'Product no longer exists. Reload.');
        return;
    }

    const qty = parseInt((document.getElementById('stockQtyInput') || {}).value, 10);
    const reason = (document.getElementById('stockReasonSelect') || {}).value;
    const note = ((document.getElementById('stockNoteInput') || {}).value || '').trim() || null;

    if (isNaN(qty)) { _stkShowModalError('stockModalError', 'Enter a whole number.'); return; }
    if ((_stkCurrentStockAction === 'add' || _stkCurrentStockAction === 'remove') && qty <= 0) {
        _stkShowModalError('stockModalError', 'Quantity must be greater than 0.'); return;
    }
    if (_stkCurrentStockAction === 'remove' && qty > _stkNum(product.stock_quantity)) {
        _stkShowModalError('stockModalError',
            'Cannot remove ' + qty + ' — only ' + _stkNum(product.stock_quantity) + ' in stock.');
        return;
    }
    if (_stkCurrentStockAction === 'adjust' && qty < 0) {
        _stkShowModalError('stockModalError', 'Quantity cannot be negative.'); return;
    }

    let payload;
    if (_stkCurrentStockAction === 'add') {
        payload = { product_id: product.id, quantity: qty, reason: reason, note: note };
        _stkSendStockRequest('/api/v1/admin/stock/add', payload);
    } else if (_stkCurrentStockAction === 'remove') {
        payload = { product_id: product.id, quantity: qty, reason: reason, note: note };
        _stkSendStockRequest('/api/v1/admin/stock/remove', payload);
    } else {
        payload = { product_id: product.id, new_quantity: qty, reason: reason, note: note };
        _stkSendStockRequest('/api/v1/admin/stock/adjust', payload);
    }
}

function _stkSendStockRequest(endpoint, payload) {
    const btn = document.getElementById('stockSubmitBtn');
    const originalText = btn ? btn.textContent : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    }

    fetch(endpoint, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': getCsrfToken() || ''
        },
        body: JSON.stringify(payload)
    })
    .then(function (r) { return r.json(); })
    .then(function (body) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
        if (body && body.success) {
            showToast(body.message || 'Stock updated', 'success');
            closeStockModal();
            loadProducts();
        } else {
            _stkShowModalError('stockModalError', (body && body.message) || 'Failed');
        }
    })
    .catch(function (err) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
        console.error('[stocks] submit failed:', err);
        _stkShowModalError('stockModalError', 'Network error. Try again.');
    });
}


/* ============================================
   ADD PRODUCT MODAL
   ============================================ */

function openAddProductModal() {
    const form = document.getElementById('addProductForm');
    if (form) form.reset();

    const setVal = function (id, v) {
        const el = document.getElementById(id);
        if (el) el.value = v;
    };
    setVal('apPurchasePrice', '0.00');
    setVal('apSellingPrice', '0.00');
    setVal('apStockQuantity', '0');
    setVal('apMinStockLevel', '10');
    setVal('apUnit', 'pc');
    setVal('apTaxRate', '0');

    const inline = document.getElementById('inlineCategoryForm');
    if (inline) inline.style.display = 'none';

    _stkPopulateCategoryDropdown();

    const modal = document.getElementById('addProductModal');
    if (modal) modal.classList.add('active');
    setTimeout(function () {
        const el = document.getElementById('apName');
        if (el) el.focus();
    }, 80);
}

function closeAddProductModal() {
    const modal = document.getElementById('addProductModal');
    if (modal) modal.classList.remove('active');
}

function generateBarcodeForNewProduct() {
    let digits = '';
    for (let i = 0; i < 12; i++) digits += Math.floor(Math.random() * 10);
    if (digits[0] === '0') digits = '1' + digits.slice(1);

    let sum = 0;
    for (let i = 0; i < 12; i++) {
        sum += parseInt(digits[i], 10) * (i % 2 === 0 ? 1 : 3);
    }
    const check = (10 - (sum % 10)) % 10;

    const el = document.getElementById('apBarcode');
    if (el) el.value = digits + check;
}

function submitAddProduct(event) {
    event.preventDefault();

    const name = ((document.getElementById('apName') || {}).value || '').trim();
    const barcode = ((document.getElementById('apBarcode') || {}).value || '').trim() || null;
    const categoryId = (document.getElementById('apCategory') || {}).value || null;
    const purchase = parseFloat((document.getElementById('apPurchasePrice') || {}).value || 0);
    const selling = parseFloat((document.getElementById('apSellingPrice') || {}).value || 0);
    const stock = parseInt((document.getElementById('apStockQuantity') || {}).value || 0, 10);
    const minStock = parseInt((document.getElementById('apMinStockLevel') || {}).value || 10, 10);
    const unit = ((document.getElementById('apUnit') || {}).value || '').trim() || 'pc';
    const taxRate = parseFloat((document.getElementById('apTaxRate') || {}).value || 0);
    const description = ((document.getElementById('apDescription') || {}).value || '').trim() || null;

    if (!name) {
        _stkShowModalError('addProductError', 'Product name is required.');
        return;
    }
    if (selling < purchase) {
        _stkShowModalError('addProductError', 'Selling price must be ≥ purchase price.');
        return;
    }

    const payload = {
        name: name,
        barcode: barcode,
        description: description,
        category_id: categoryId ? parseInt(categoryId, 10) : null,
        purchase_price: purchase,
        selling_price: selling,
        stock_quantity: stock,
        min_stock_level: minStock,
        unit: unit,
        tax_rate: taxRate,
        stock_type: 'regular',
        product_image: null
    };

    const btn = document.getElementById('addProductSubmitBtn');
    const originalText = btn ? btn.textContent : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...';
    }

    fetch('/api/v1/products', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': getCsrfToken() || ''
        },
        body: JSON.stringify(payload)
    })
    .then(function (r) { return r.json(); })
    .then(function (body) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
        if (body && body.success) {
            showToast('Product "' + name + '" created', 'success');
            closeAddProductModal();
            loadProducts();
            loadCategories();
        } else {
            _stkShowModalError('addProductError',
                (body && body.message) || 'Failed to create product.');
        }
    })
    .catch(function (err) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
        console.error('[stocks] create failed:', err);
        _stkShowModalError('addProductError', 'Network error.');
    });
}


/* ============================================
   DELETE PRODUCT
   ============================================ */

function openDeleteModal() {
    if (!_stkSelectedProductId || !_stkProductsById[_stkSelectedProductId]) {
        showToast('⚠️ Select a product from the table first', 'warning');
        return;
    }

    const product = _stkProductsById[_stkSelectedProductId];
    _stkCurrentDeleteProductId = product.id;

    const subEl = document.getElementById('deleteModalSubtitle');
    if (subEl) {
        subEl.innerHTML = 'Delete <strong>' + escapeHtml(product.name) +
            '</strong>?<br><span style="font-size:0.82rem;">This hides it ' +
            'from all lists. Sale history is kept.</span>';
    }

    const errEl = document.getElementById('deleteModalError');
    if (errEl) errEl.classList.remove('visible');

    const modal = document.getElementById('deleteModal');
    if (modal) modal.classList.add('active');
}

function closeDeleteModal() {
    const modal = document.getElementById('deleteModal');
    if (modal) modal.classList.remove('active');
    _stkCurrentDeleteProductId = null;
}

function confirmDeleteProduct() {
    if (!_stkCurrentDeleteProductId) return;

    const btn = document.getElementById('deleteConfirmBtn');
    const originalText = btn ? btn.textContent : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deleting...';
    }

    fetch('/api/v1/products/' + _stkCurrentDeleteProductId, {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { 'X-CSRF-TOKEN': getCsrfToken() || '' }
    })
    .then(function (r) { return r.json(); })
    .then(function (body) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
        if (body && body.success) {
            showToast('Product deleted', 'success');
            closeDeleteModal();
            _stkSelectedProductId = null;
            _stkUpdateSelectionHint();
            loadProducts();
        } else {
            _stkShowModalError('deleteModalError',
                (body && body.message) || 'Delete failed');
        }
    })
    .catch(function (err) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
        console.error('[stocks] delete failed:', err);
        _stkShowModalError('deleteModalError', 'Network error.');
    });
}


/* ============================================
   INLINE CATEGORY (from Add Product modal)
   ============================================ */

function openAddCategoryInline() {
    const el = document.getElementById('inlineCategoryForm');
    if (el) el.style.display = 'block';
    const input = document.getElementById('newCategoryName');
    if (input) {
        input.value = '';
        setTimeout(function () { input.focus(); }, 80);
    }
}

function cancelInlineCategory() {
    const el = document.getElementById('inlineCategoryForm');
    if (el) el.style.display = 'none';
}

function saveInlineCategory() {
    const name = ((document.getElementById('newCategoryName') || {}).value || '').trim();
    if (!name) {
        showToast('Enter a category name', 'warning');
        return;
    }

    fetch('/api/v1/products/categories', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': getCsrfToken() || ''
        },
        body: JSON.stringify({ name: name, description: null })
    })
    .then(function (r) { return r.json(); })
    .then(function (body) {
        if (body && body.success) {
            showToast('Category "' + name + '" created', 'success');
            cancelInlineCategory();
            loadCategories();
        } else if (body && body.error === 'category_exists') {
            showToast('Category "' + name + '" already exists', 'warning');
        } else {
            showToast((body && body.message) || 'Failed to create category', 'error');
        }
    })
    .catch(function (err) {
        console.error('[stocks] create category:', err);
        showToast('Network error', 'error');
    });
}


/* ============================================
   MODAL ERROR HELPER
   ============================================ */

function _stkShowModalError(elementId, message) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = message;
    el.classList.add('visible');
}
