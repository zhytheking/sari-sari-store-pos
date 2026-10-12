/**
 * categories.js — Category Management page for owners.
 *
 * Depends on api-client.js.
 */

let _catAllCategories = [];


/* ============================================
   SAFE HELPERS
   ============================================ */

function _catStr(v) { return (v === null || v === undefined) ? '' : String(v); }
function _catNum(v) { const n = Number(v); return isNaN(n) ? 0 : n; }


/* ============================================
   INIT
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
    loadCategories();
});


/* ============================================
   LOAD
   ============================================ */

function loadCategories() {
    const tbody = document.getElementById('categoriesTableBody');
    if (!tbody) return;

    tbody.innerHTML = `
        <tr>
            <td colspan="5" style="text-align:center;padding:40px;">
                <div class="loading-spinner"></div>
                <p style="margin-top:10px;color:#6c757d;">Loading categories...</p>
            </td>
        </tr>
    `;

    API.products.categories.list()
        .then(function (data) {
            if (data && data.success) {
                _catAllCategories = data.data || [];
                _catRenderTable(_catAllCategories);
            } else {
                showToast((data && data.message) || 'Failed to load categories', 'error');
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:40px;color:#dc3545;">Failed to load categories</td></tr>';
            }
        })
        .catch(function (err) {
            console.error('[categories] load:', err);
            showToast('Failed to load categories', 'error');
        });
}


/* ============================================
   RENDER TABLE
   ============================================ */

function _catRenderTable(categories) {
    const tbody = document.getElementById('categoriesTableBody');
    if (!tbody) return;

    if (!categories || categories.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="empty-state">
                    <i class="fas fa-tags"></i>
                    <p>No categories yet. Click "Add Category" to create one.</p>
                </td>
            </tr>
        `;
        return;
    }

    let html = '';
    categories.forEach(function (cat) {
        const count = _catNum(cat.product_count);
        const countClass = count > 0 ? 'product-count' : 'product-count empty';
        const deleteDisabled = count > 0
            ? 'disabled title="Cannot delete — category is used by products"'
            : '';
        const jsSafeName = _catStr(cat.name)
            .replace(/\\/g, '\\\\')
            .replace(/'/g, "\\'");

        html += `
            <tr>
                <td>${cat.id}</td>
                <td><span class="category-name">${escapeHtml(_catStr(cat.name))}</span></td>
                <td><span class="category-description">${escapeHtml(_catStr(cat.description) || '—')}</span></td>
                <td><span class="${countClass}">${count} product${count !== 1 ? 's' : ''}</span></td>
                <td>
                    <button class="btn-delete" ${deleteDisabled}
                            onclick="deleteCategory(${cat.id}, '${jsSafeName}')">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

function filterTable() {
    const input = document.getElementById('searchInput');
    const q = input ? input.value.toLowerCase().trim() : '';
    if (!q) {
        _catRenderTable(_catAllCategories);
        return;
    }
    const filtered = _catAllCategories.filter(function (c) {
        return _catStr(c.name).toLowerCase().indexOf(q) !== -1 ||
               _catStr(c.description).toLowerCase().indexOf(q) !== -1;
    });
    _catRenderTable(filtered);
}


/* ============================================
   ADD CATEGORY MODAL
   ============================================ */

function openAddCategoryModal() {
    const nameEl = document.getElementById('categoryName');
    const descEl = document.getElementById('categoryDescription');
    if (nameEl) nameEl.value = '';
    if (descEl) descEl.value = '';

    const modal = document.getElementById('addCategoryModal');
    if (modal) modal.classList.add('active');
    setTimeout(function () { if (nameEl) nameEl.focus(); }, 100);
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
}

function submitAddCategory(event) {
    event.preventDefault();

    const name = ((document.getElementById('categoryName') || {}).value || '').trim();
    const description = ((document.getElementById('categoryDescription') || {}).value || '').trim();

    if (!name) {
        showToast('Category name is required', 'error');
        return;
    }

    const submitBtn = event.target.querySelector('button[type="submit"]');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...';
    }

    fetch('/api/v1/products/categories', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': getCsrfToken() || ''
        },
        body: JSON.stringify({ name: name, description: description || null })
    })
    .then(function (r) {
        return r.json().then(function (body) {
            return { status: r.status, body: body };
        });
    })
    .then(function (res) {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fas fa-check"></i> Create Category';
        }

        if (res.status === 201 || (res.body && res.body.success)) {
            showToast('Category "' + name + '" created', 'success');
            closeModal('addCategoryModal');
            loadCategories();
        } else if (res.status === 409) {
            showToast('Category "' + name + '" already exists', 'warning');
        } else {
            showToast((res.body && res.body.message) || 'Failed to create category', 'error');
        }
    })
    .catch(function (err) {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fas fa-check"></i> Create Category';
        }
        console.error('[categories] create:', err);
        showToast('Network error', 'error');
    });
}


/* ============================================
   DELETE
   ============================================ */

function deleteCategory(categoryId, categoryName) {
    if (!confirm('Delete category "' + categoryName + '"?\n\nThis cannot be undone.')) {
        return;
    }

    fetch('/api/v1/products/categories/' + categoryId, {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { 'X-CSRF-TOKEN': getCsrfToken() || '' }
    })
    .then(function (r) {
        return r.json().then(function (body) {
            return { status: r.status, body: body };
        });
    })
    .then(function (res) {
        if (res.status === 200 || (res.body && res.body.success)) {
            showToast('Category "' + categoryName + '" deleted', 'success');
            loadCategories();
        } else if (res.status === 409) {
            showToast((res.body && res.body.message) ||
                'Cannot delete — category is in use', 'warning');
        } else {
            showToast((res.body && res.body.message) || 'Failed to delete category', 'error');
        }
    })
    .catch(function (err) {
        console.error('[categories] delete:', err);
        showToast('Network error', 'error');
    });
}


/* ============================================
   MODAL CLOSE ON OUTSIDE CLICK / ESC
   ============================================ */

document.addEventListener('click', function (e) {
    const modal = document.getElementById('addCategoryModal');
    if (e.target === modal) closeModal('addCategoryModal');
});

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeModal('addCategoryModal');
});
