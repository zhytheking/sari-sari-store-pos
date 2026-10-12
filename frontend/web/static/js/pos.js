/**
 * pos.js — Point of Sale page logic.
 *
 * Depends on api-client.js.
 *
 * Owns:
 *   - Product grid (search, filter, render)
 *   - Cart operations
 *   - Barcode entry modal (manual + camera)
 *   - Payment modal (cash + GCash)
 *   - Auto-refresh every 15s
 */

/* ============================================
   STATE
   ============================================ */

let posProducts = [];
let posProductsMap = new Map();
let posCart = [];
let currentPaymentTotal = 0;
let currentPaymentMethod = 'cash';
let isLoadingProducts = false;
let posSearchQuery = '';
let _gcashQrLoadedFor = null;

// Camera
let cameraStream = null;
let scanInterval = null;
let zxingReader = null;
let lastScannedCode = null;
let lastScannedAt = 0;

// Auto-refresh
let autoRefreshTimer = null;
let lastRefreshAt = 0;
const AUTO_REFRESH_MS = 15000;


/* ============================================
   SAFE HELPERS
   ============================================ */

function _posStr(v) { return (v === null || v === undefined) ? '' : String(v); }
function _posNum(v) { const n = Number(v); return isNaN(n) ? 0 : n; }


/* ============================================
   MODAL / FOCUS CHECKS
   ============================================ */

function isAnyModalOpen() {
    const ids = ['barcodeEntryModal', 'paymentModal'];
    for (let i = 0; i < ids.length; i++) {
        const el = document.getElementById(ids[i]);
        if (el && el.classList.contains('active')) return true;
    }
    return false;
}

function isSearchFocused() {
    const s = document.getElementById('posSearch');
    return s && document.activeElement === s;
}

function isCartBusy() { return posCart.length > 0; }

function shouldSkipAutoRefresh() {
    if (isAnyModalOpen()) return true;
    if (isSearchFocused()) return true;
    if (isCartBusy()) return true;
    if (document.hidden) return true;
    return false;
}


/* ============================================
   PRODUCTS
   ============================================ */

function loadPosProducts(silent) {
    silent = !!silent;
    if (isLoadingProducts) return;
    isLoadingProducts = true;

    const grid = document.getElementById('posProductGrid');
    const refreshBtn = document.getElementById('refreshProductsBtn');
    if (!grid) {
        isLoadingProducts = false;
        return;
    }

    if (!silent) {
        grid.innerHTML = `
            <div style="grid-column:1/-1;padding:40px 20px;text-align:center;">
                <div class="loading-spinner" style="margin:0 auto;"></div>
                <p style="margin-top:10px;color:#6c757d;">Loading products...</p>
            </div>
        `;
    }

    if (refreshBtn && !silent) {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }

    fetch('/api/v1/products?per_page=500&active=all', {
        credentials: 'same-origin'
    })
    .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    })
    .then(function (data) {
        if (!data || !data.success) {
            throw new Error((data && data.message) || 'Failed to load products');
        }

        posProducts = (data.data && data.data.items) || [];
        posProductsMap = new Map();
        posProducts.forEach(function (p) { posProductsMap.set(p.id, p); });

        renderFilteredProducts();

        const countEl = document.getElementById('productCount');
        if (countEl) {
            const sellable = posProducts.filter(function (p) {
                return p.is_active !== false && _posNum(p.stock_quantity) > 0;
            }).length;
            countEl.textContent = sellable + ' available';
        }

        lastRefreshAt = Date.now();

        const emptyBanner = document.getElementById('emptyBanner');
        if (emptyBanner) {
            emptyBanner.classList.toggle('visible', posProducts.length === 0);
        }

        if (posProducts.length === 0 && !silent) {
            grid.innerHTML = `
                <div style="grid-column:1/-1;padding:40px 20px;text-align:center;color:#6c757d;">
                    <i class="fas fa-box-open" style="font-size:3rem;color:#dee2e6;display:block;margin-bottom:15px;"></i>
                    <p style="font-weight:600;margin:0;">No products in database</p>
                    <p style="font-size:0.85rem;margin-top:8px;">
                        Add products in <a href="/admin/stocks" style="color:#2d6a4f;">Stocks</a>
                    </p>
                </div>
            `;
        }
    })
    .catch(function (err) {
        console.error('[POS] Load failed:', err);
        if (!silent) {
            grid.innerHTML = `
                <div style="grid-column:1/-1;padding:40px 20px;text-align:center;">
                    <i class="fas fa-exclamation-circle" style="font-size:2.5rem;color:#dc3545;display:block;margin-bottom:15px;"></i>
                    <p style="color:#495057;font-weight:600;margin:0;">Failed to load products</p>
                    <p style="color:#6c757d;font-size:0.85rem;margin:5px 0 15px;">${escapeHtml(err.message)}</p>
                    <button onclick="loadPosProducts(false)" style="padding:10px 24px;background:#2d6a4f;color:#fff;border:none;border-radius:10px;font-weight:600;cursor:pointer;">
                        <i class="fas fa-sync-alt"></i> Retry
                    </button>
                </div>
            `;
        }
    })
    .finally(function () {
        isLoadingProducts = false;
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
        }
    });
}

function startAutoRefresh() {
    stopAutoRefresh();
    autoRefreshTimer = setInterval(function () {
        if (shouldSkipAutoRefresh()) return;
        loadPosProducts(true);
    }, AUTO_REFRESH_MS);
}

function stopAutoRefresh() {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
    }
}


/* ============================================
   FILTER + RENDER
   ============================================ */

function renderFilteredProducts() {
    const q = posSearchQuery.trim().toLowerCase();
    if (!q) {
        renderPosProducts(posProducts);
        updateSearchHint('', 0, posProducts.length);
        return;
    }

    const filtered = posProducts.filter(function (p) {
        const name = _posStr(p.name).toLowerCase();
        const barcode = _posStr(p.barcode).toLowerCase();
        const category = _posStr(p.category_name).toLowerCase();
        return name.indexOf(q) !== -1 ||
               barcode.indexOf(q) !== -1 ||
               category.indexOf(q) !== -1;
    });

    renderPosProducts(filtered);
    updateSearchHint(q, filtered.length, posProducts.length);
}

function updateSearchHint(query, matchCount, totalCount) {
    const hint = document.getElementById('searchHint');
    const text = document.getElementById('searchHintText');
    if (!hint || !text) return;

    if (!query) {
        hint.classList.remove('visible');
        return;
    }

    text.innerHTML = '<i class="fas fa-filter"></i> Showing <strong>' +
        matchCount + '</strong> of ' + totalCount +
        ' products for "<strong>' + escapeHtml(query) + '</strong>"';
    hint.classList.add('visible');

    const clearBtn = document.getElementById('posSearchClear');
    if (clearBtn) clearBtn.classList.add('visible');
}

function clearPosSearch() {
    const input = document.getElementById('posSearch');
    if (input) input.value = '';
    posSearchQuery = '';
    renderFilteredProducts();
    updateSearchHint('', 0, 0);
    const clearBtn = document.getElementById('posSearchClear');
    if (clearBtn) clearBtn.classList.remove('visible');
    if (input) input.focus();
}

function renderPosProducts(products) {
    const grid = document.getElementById('posProductGrid');
    if (!grid) return;

    if (!products || products.length === 0) {
        grid.innerHTML = '<p style="grid-column:1/-1;text-align:center;color:#6c757d;padding:20px;">No products found</p>';
        return;
    }

    const fragment = document.createDocumentFragment();

    products.forEach(function (product) {
        const stock = _posNum(product.stock_quantity);
        const isActive = product.is_active !== false;
        const isOutOfStock = stock <= 0;
        const canSell = isActive && !isOutOfStock;

        const card = document.createElement('div');
        let klass = 'pos-product-item';
        if (!isActive) klass += ' inactive';
        else if (isOutOfStock) klass += ' out-of-stock';
        card.className = klass;

        let stockText;
        if (!isActive) stockText = 'Inactive product';
        else if (isOutOfStock) stockText = 'Out of stock';
        else stockText = stock + ' left';

        card.title = _posStr(product.name) + '\nPrice: ₱' +
            _posNum(product.selling_price).toFixed(2) + '\n' + stockText +
            '\nBarcode: ' + (_posStr(product.barcode) || '—');

        if (canSell) {
            card.addEventListener('click', function () {
                addToPosCart(product.id);
            });
        }

        card.innerHTML =
            '<div class="item-name">' + escapeHtml(_posStr(product.name)) + '</div>' +
            '<div class="item-price">₱' + _posNum(product.selling_price).toFixed(2) + '</div>' +
            '<div class="item-stock">' + stockText + '</div>';

        fragment.appendChild(card);
    });

    grid.innerHTML = '';
    grid.appendChild(fragment);
}


/* ============================================
   BARCODE MODAL — TABS
   ============================================ */

function openBarcodeEntry() {
    const modal = document.getElementById('barcodeEntryModal');
    if (!modal) return;
    modal.classList.add('active');
    switchScanTab('manual');

    const input = document.getElementById('barcodeEntryInput');
    if (input) {
        input.value = '';
        input.classList.remove('error');
        setTimeout(function () { input.focus(); }, 100);
    }
}

function closeBarcodeEntry() {
    const modal = document.getElementById('barcodeEntryModal');
    if (modal) modal.classList.remove('active');
    stopCamera();

    const m = document.getElementById('manualStatus');
    const c = document.getElementById('cameraStatus');
    if (m) m.textContent = '';
    if (c) c.textContent = '';
}

function switchScanTab(tab) {
    const tabManual = document.getElementById('tabManual');
    const tabCamera = document.getElementById('tabCamera');
    const panelManual = document.getElementById('panelManual');
    const panelCamera = document.getElementById('panelCamera');

    if (tab === 'camera') {
        if (tabManual) tabManual.classList.remove('active');
        if (tabCamera) tabCamera.classList.add('active');
        if (panelManual) panelManual.classList.remove('active');
        if (panelCamera) panelCamera.classList.add('active');
    } else {
        if (tabCamera) tabCamera.classList.remove('active');
        if (tabManual) tabManual.classList.add('active');
        if (panelCamera) panelCamera.classList.remove('active');
        if (panelManual) panelManual.classList.add('active');
        stopCamera();
        const input = document.getElementById('barcodeEntryInput');
        setTimeout(function () { if (input) input.focus(); }, 100);
    }
}

function submitBarcodeEntry() {
    const input = document.getElementById('barcodeEntryInput');
    const statusLine = document.getElementById('manualStatus');
    if (!input) return;

    const barcode = input.value.trim();
    if (!barcode) {
        input.classList.add('error');
        if (statusLine) {
            statusLine.textContent = 'Please enter a barcode';
            statusLine.className = 'scan-status-line error';
        }
        return;
    }

    lookupBarcode(barcode, {
        onSuccess: function () {
            input.value = '';
            input.classList.remove('error');
            if (statusLine) {
                statusLine.textContent = 'Ready for next scan...';
                statusLine.className = 'scan-status-line success';
            }
            input.focus();
        },
        statusEl: statusLine
    });
}


/* ============================================
   BARCODE LOOKUP
   ============================================ */

function lookupBarcode(barcode, options) {
    options = options || {};
    const statusEl = options.statusEl || null;
    const onSuccess = options.onSuccess || null;

    if (statusEl) {
        statusEl.textContent = 'Looking up...';
        statusEl.className = 'scan-status-line';
    }

    fetch('/api/v1/products/barcode/' + encodeURIComponent(barcode), {
        credentials: 'same-origin'
    })
    .then(function (response) {
        return response.json().catch(function () { return {}; })
            .then(function (data) {
                if (!response.ok || !data.success) {
                    throw new Error(data.message || ('No product found for: ' + barcode));
                }
                return data.data;
            });
    })
    .then(function (product) {
        if (_posNum(product.stock_quantity) <= 0) {
            if (statusEl) {
                statusEl.textContent = '⚠️ "' + product.name + '" is out of stock';
                statusEl.className = 'scan-status-line error';
            }
            showToast('"' + product.name + '" is out of stock', 'warning');
            return;
        }
        _doAddToCart(product);
        showToast('✅ ' + product.name + ' added', 'success');
        if (statusEl) {
            statusEl.textContent = '✅ ' + product.name + ' — Added to cart';
            statusEl.className = 'scan-status-line success';
        }
        if (typeof onSuccess === 'function') onSuccess();
    })
    .catch(function (err) {
        console.error('[SCAN] Lookup failed:', err);
        showToast('❌ ' + err.message, 'error');
        if (statusEl) {
            statusEl.textContent = '❌ ' + err.message;
            statusEl.className = 'scan-status-line error';
        }
    });
}


/* ============================================
   CAMERA
   ============================================ */

function _cameraIsAvailable() {
    const isSecure = window.isSecureContext;
    const isLocalhost =
        location.hostname === 'localhost' ||
        location.hostname === '127.0.0.1' ||
        location.hostname === '::1';
    return isSecure || isLocalhost;
}

async function startCamera() {
    const video = document.getElementById('cameraVideo');
    const placeholder = document.getElementById('cameraPlaceholder');
    const crosshair = document.getElementById('cameraCrosshair');
    const startBtn = document.getElementById('cameraStartBtn');
    const stopBtn = document.getElementById('cameraStopBtn');
    const statusEl = document.getElementById('cameraStatus');

    if (cameraStream) return;

    if (!_cameraIsAvailable()) {
        if (statusEl) {
            statusEl.innerHTML =
                '❌ Camera requires a secure connection.<br>' +
                '<span style="font-size:0.75rem;">Open this POS on the store PC at ' +
                '<strong>http://127.0.0.1:5000/admin/pos</strong> ' +
                'to use the camera, or use a USB scanner.</span>';
            statusEl.className = 'scan-status-line error';
        }
        return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (statusEl) {
            statusEl.textContent = '❌ Your browser does not support camera access.';
            statusEl.className = 'scan-status-line error';
        }
        return;
    }

    if (statusEl) {
        statusEl.textContent = 'Requesting camera access...';
        statusEl.className = 'scan-status-line';
    }

    try {
        const constraints = {
            video: {
                facingMode: { ideal: 'environment' },
                width: { ideal: 1280 },
                height: { ideal: 720 }
            }
        };
        cameraStream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = cameraStream;
        await video.play();

        if (placeholder) placeholder.style.display = 'none';
        if (crosshair) crosshair.style.display = 'block';
        if (startBtn) startBtn.style.display = 'none';
        if (stopBtn) stopBtn.style.display = 'inline-flex';

        if (statusEl) {
            statusEl.textContent = 'Camera active — point at a barcode';
            statusEl.className = 'scan-status-line';
        }

        startDecoding();
    } catch (err) {
        console.error('[CAMERA] Failed:', err);
        if (statusEl) {
            let msg = 'Could not access camera.';
            if (err.name === 'NotAllowedError') {
                msg = 'Camera permission denied. Allow camera access and try again.';
            } else if (err.name === 'NotFoundError') {
                msg = 'No camera found on this device.';
            } else if (err.name === 'NotReadableError') {
                msg = 'Camera is in use by another app.';
            }
            statusEl.textContent = '❌ ' + msg;
            statusEl.className = 'scan-status-line error';
        }
        showToast('Camera access failed', 'error');
    }
}

function stopCamera() {
    const video = document.getElementById('cameraVideo');
    const placeholder = document.getElementById('cameraPlaceholder');
    const crosshair = document.getElementById('cameraCrosshair');
    const startBtn = document.getElementById('cameraStartBtn');
    const stopBtn = document.getElementById('cameraStopBtn');

    if (scanInterval) { clearInterval(scanInterval); scanInterval = null; }
    if (zxingReader) {
        try { zxingReader.reset(); } catch (e) {}
        zxingReader = null;
    }
    if (cameraStream) {
        cameraStream.getTracks().forEach(function (t) { t.stop(); });
        cameraStream = null;
    }

    if (video) video.srcObject = null;
    if (placeholder) placeholder.style.display = 'flex';
    if (crosshair) crosshair.style.display = 'none';
    if (startBtn) startBtn.style.display = 'inline-flex';
    if (stopBtn) stopBtn.style.display = 'none';
}

function startDecoding() {
    const video = document.getElementById('cameraVideo');
    const statusEl = document.getElementById('cameraStatus');

    if ('BarcodeDetector' in window) {
        let detector;
        try {
            detector = new BarcodeDetector({
                formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e',
                          'code_128', 'code_39', 'codabar', 'itf', 'qr_code']
            });
        } catch (e) {
            console.warn('[CAMERA] BarcodeDetector init failed:', e);
            detector = null;
        }

        if (detector) {
            scanInterval = setInterval(async function () {
                if (!cameraStream || !video.videoWidth) return;
                try {
                    const codes = await detector.detect(video);
                    if (codes && codes.length > 0) {
                        handleCameraScan(codes[0].rawValue, statusEl);
                    }
                } catch (e) { /* silent */ }
            }, 400);
            return;
        }
    }

    if (typeof ZXing !== 'undefined') {
        try {
            zxingReader = new ZXing.BrowserMultiFormatReader();
            zxingReader.decodeFromVideoElement(video, function (result) {
                if (result) handleCameraScan(result.getText(), statusEl);
            });
            return;
        } catch (e) {
            console.warn('[ZXING] Init failed:', e);
        }
    }

    if (statusEl) {
        statusEl.textContent =
            '⚠️ Your browser cannot decode barcodes from camera. ' +
            'Use manual entry or update your browser.';
        statusEl.className = 'scan-status-line error';
    }
}

function handleCameraScan(code, statusEl) {
    if (!code) return;
    const now = Date.now();
    if (code === lastScannedCode && (now - lastScannedAt) < 2000) return;
    lastScannedCode = code;
    lastScannedAt = now;

    if (statusEl) {
        statusEl.textContent = 'Scanned: ' + code;
        statusEl.className = 'scan-status-line success';
    }
    if (navigator.vibrate) navigator.vibrate(80);
    lookupBarcode(code, { statusEl: statusEl });
}


/* ============================================
   CART
   ============================================ */

function addToPosCart(productId) {
    const product = posProductsMap.get(productId);
    if (!product) return;
    if (product.is_active === false) return;
    if (_posNum(product.stock_quantity) <= 0) return;
    _doAddToCart(product);
}

function _doAddToCart(product) {
    const stock = _posNum(product.stock_quantity);
    if (stock <= 0) return;

    const existing = posCart.find(function (item) { return item.id === product.id; });
    if (existing) {
        if (existing.quantity >= stock) return;
        existing.quantity += 1;
    } else {
        posCart.push({
            id: product.id,
            name: product.name,
            price: _posNum(product.selling_price),
            quantity: 1,
            maxStock: stock
        });
    }

    renderPosCart();
}

function renderPosCart() {
    const container = document.getElementById('posCartItems');
    const itemCount = document.getElementById('cartItemCount');
    if (!container) return;

    if (posCart.length === 0) {
        container.innerHTML = `
            <div class="empty-cart">
                <i class="fas fa-cart-plus"></i>
                <p>Add items to start order</p>
            </div>
        `;
        if (itemCount) itemCount.textContent = '0 items';
        updatePosTotals();
        return;
    }

    const renderedRows = container.querySelectorAll('.pos-cart-item');
    const needsFullRebuild = renderedRows.length !== posCart.length;

    if (needsFullRebuild) {
        const fragment = document.createDocumentFragment();
        posCart.forEach(function (item, index) {
            const row = document.createElement('div');
            row.className = 'pos-cart-item';
            row.dataset.index = index;
            row.innerHTML =
                '<div class="item-info">' +
                    '<div class="item-name">' + escapeHtml(_posStr(item.name)) + '</div>' +
                    '<div class="item-price">₱' + item.price.toFixed(2) +
                        ' × ' + item.quantity + '</div>' +
                '</div>' +
                '<div class="item-actions">' +
                    '<button class="qty-btn" data-action="dec"><i class="fas fa-minus"></i></button>' +
                    '<span class="item-qty">' + item.quantity + '</span>' +
                    '<button class="qty-btn" data-action="inc" ' +
                        (item.quantity >= item.maxStock ? 'disabled' : '') +
                    '><i class="fas fa-plus"></i></button>' +
                    '<button class="remove-btn" data-action="remove"><i class="fas fa-times"></i></button>' +
                '</div>' +
                '<div class="item-total">₱' +
                    (item.price * item.quantity).toFixed(2) + '</div>';
            fragment.appendChild(row);
        });
        container.innerHTML = '';
        container.appendChild(fragment);

        if (!container._delegationAttached) {
            container.addEventListener('click', handleCartClick);
            container._delegationAttached = true;
        }
    } else {
        posCart.forEach(function (item, index) {
            const row = container.querySelector('[data-index="' + index + '"]');
            if (!row) return;
            const priceEl = row.querySelector('.item-price');
            const qtyEl = row.querySelector('.item-qty');
            const totalEl = row.querySelector('.item-total');
            if (priceEl) priceEl.textContent = '₱' + item.price.toFixed(2) +
                ' × ' + item.quantity;
            if (qtyEl) qtyEl.textContent = item.quantity;
            if (totalEl) totalEl.textContent = '₱' +
                (item.price * item.quantity).toFixed(2);
            const incBtn = row.querySelector('[data-action="inc"]');
            if (incBtn) incBtn.disabled = item.quantity >= item.maxStock;
        });
    }

    const totalItems = posCart.reduce(function (sum, item) {
        return sum + item.quantity;
    }, 0);
    if (itemCount) itemCount.textContent = totalItems + ' items';
    updatePosTotals();
}

function handleCartClick(event) {
    const btn = event.target.closest('button[data-action]');
    if (!btn) return;
    const row = btn.closest('.pos-cart-item');
    if (!row) return;
    const index = parseInt(row.dataset.index, 10);
    const action = btn.dataset.action;

    if (action === 'inc') updatePosCartItem(index, 1);
    else if (action === 'dec') updatePosCartItem(index, -1);
    else if (action === 'remove') removePosCartItem(index);
}

function updatePosCartItem(index, change) {
    if (index < 0 || index >= posCart.length) return;
    const newQty = posCart[index].quantity + change;
    if (newQty < 1) {
        posCart.splice(index, 1);
    } else {
        if (newQty > posCart[index].maxStock) return;
        posCart[index].quantity = newQty;
    }
    renderPosCart();
}

function removePosCartItem(index) {
    posCart.splice(index, 1);
    renderPosCart();
}

function clearPosCart() {
    if (posCart.length === 0) return;
    if (!confirm('Clear all items from cart?')) return;
    posCart = [];
    renderPosCart();
}

function updatePosTotals() {
    const subtotal = posCart.reduce(function (sum, item) {
        return sum + (item.price * item.quantity);
    }, 0);
    const subEl = document.getElementById('posSubtotal');
    const discEl = document.getElementById('posDiscount');
    const totEl = document.getElementById('posTotal');
    if (subEl) subEl.textContent = '₱' + subtotal.toFixed(2);
    if (discEl) discEl.textContent = '₱0.00';
    if (totEl) totEl.textContent = '₱' + subtotal.toFixed(2);
}


/* ============================================
   PAYMENT MODAL
   ============================================ */

function openPaymentModal() {
    if (posCart.length === 0) {
        showToast('Cart is empty', 'warning');
        return;
    }

    currentPaymentTotal = posCart.reduce(function (sum, item) {
        return sum + (item.price * item.quantity);
    }, 0);

    const totalEl = document.getElementById('paymentTotal');
    const qrHint = document.getElementById('qrAmountHint');
    if (totalEl) totalEl.textContent = '₱' + currentPaymentTotal.toFixed(2);
    if (qrHint) qrHint.textContent = '₱' + currentPaymentTotal.toFixed(2);

    const cn = document.getElementById('customerName');
    if (cn) cn.value = '';

    const subBtn = document.getElementById('submitPaymentBtn');
    if (subBtn) {
        subBtn.disabled = false;
        subBtn.innerHTML = '✅ Confirm Payment';
    }

    const ca = document.getElementById('cashAmount');
    if (ca) ca.value = currentPaymentTotal.toFixed(2);
    const cc = document.getElementById('cashChange');
    if (cc) {
        cc.value = '₱0.00';
        cc.style.color = '#2d6a4f';
    }
    const ga = document.getElementById('gcashAmount');
    if (ga) ga.value = currentPaymentTotal.toFixed(2);
    const gc = document.getElementById('gcashChange');
    if (gc) {
        gc.value = '₱0.00';
        gc.style.color = '#2d6a4f';
    }
    const gr = document.getElementById('gcashRef');
    if (gr) gr.value = '';

    selectPaymentMethod('cash');

    const modal = document.getElementById('paymentModal');
    if (modal) modal.classList.add('active');
    setTimeout(function () { if (ca) ca.focus(); }, 50);
}

function closePaymentModal() {
    const modal = document.getElementById('paymentModal');
    if (modal) modal.classList.remove('active');
}

function selectPaymentMethod(method) {
    currentPaymentMethod = method;

    const cashBtn = document.getElementById('pmCashBtn');
    const gcashBtn = document.getElementById('pmGcashBtn');
    if (cashBtn) cashBtn.classList.toggle('active', method === 'cash');
    if (gcashBtn) gcashBtn.classList.toggle('active', method === 'gcash');

    const cs = document.getElementById('cashSection');
    const gs = document.getElementById('gcashSection');
    if (cs) cs.style.display = (method === 'cash') ? 'block' : 'none';
    if (gs) gs.classList.toggle('active', method === 'gcash');

    if (method === 'gcash') {
        loadGcashQr();
    }

    setTimeout(function () {
        if (method === 'cash') {
            const ca = document.getElementById('cashAmount');
            if (ca) ca.focus();
        } else {
            const gr = document.getElementById('gcashRef');
            if (gr) gr.focus();
        }
    }, 100);
}

function calculateChange() {
    const amount = parseFloat((document.getElementById('cashAmount') || {}).value) || 0;
    const change = amount - currentPaymentTotal;
    const changeEl = document.getElementById('cashChange');
    const submitBtn = document.getElementById('submitPaymentBtn');
    if (!changeEl || !submitBtn) return;

    if (change < 0) {
        changeEl.value = '⚠️ Insufficient: ₱' + Math.abs(change).toFixed(2);
        changeEl.style.color = '#dc3545';
        submitBtn.disabled = true;
    } else {
        changeEl.value = '₱' + change.toFixed(2);
        changeEl.style.color = '#2d6a4f';
        submitBtn.disabled = false;
    }
}

function calculateGcashChange() {
    const amount = parseFloat((document.getElementById('gcashAmount') || {}).value) || 0;
    const change = amount - currentPaymentTotal;
    const changeEl = document.getElementById('gcashChange');
    const submitBtn = document.getElementById('submitPaymentBtn');
    if (!changeEl || !submitBtn) return;

    if (change < 0) {
        changeEl.value = '⚠️ Insufficient: ₱' + Math.abs(change).toFixed(2);
        changeEl.style.color = '#dc3545';
        submitBtn.disabled = true;
    } else {
        changeEl.value = '₱' + change.toFixed(2);
        changeEl.style.color = '#2d6a4f';
        submitBtn.disabled = false;
    }
}

function validateRefInput(input) {
    if (!input) return;
    input.value = input.value.replace(/\D/g, '').slice(0, 3);
}


/* ============================================
   GCASH QR
   ============================================ */

function _setQrPlaceholder(iconClass, message, isError) {
    const placeholder = document.getElementById('gcashQrPlaceholder');
    if (!placeholder) return;
    placeholder.classList.toggle('qr-error', !!isError);
    placeholder.innerHTML = '<i class="' + iconClass + '"></i><p>' +
        message + '</p>';
    placeholder.style.display = 'flex';
}

function loadGcashQr(forceReload) {
    const img = document.getElementById('gcashQrImage');
    const placeholder = document.getElementById('gcashQrPlaceholder');
    if (!img || !placeholder) return;

    if (!forceReload && _gcashQrLoadedFor && img.src && img.style.display === 'block') {
        return;
    }

    img.style.display = 'none';
    _setQrPlaceholder('fas fa-spinner fa-spin', 'Loading QR code...', false);

    fetch('/api/v1/settings/gcash-qr', { credentials: 'same-origin' })
        .then(function (r) {
            if (r.status === 401 || r.status === 422) {
                throw new Error('Not logged in. Please refresh and log in again.');
            }
            if (!r.ok) throw new Error('Server returned HTTP ' + r.status);
            return r.json();
        })
        .then(function (data) {
            const qrUrl =
                (data && data.data && data.data.qr_image_url) ||
                (data && data.data && data.data.image_url) ||
                (data && data.qr_image_url) ||
                (data && data.image_url) ||
                null;
            const hasQr = (data && data.data && data.data.has_qr) || !!qrUrl;

            if (!qrUrl || !hasQr) {
                _setQrPlaceholder(
                    'fas fa-qrcode',
                    'No QR uploaded. Ask the owner to upload one in Settings.',
                    false
                );
                return;
            }

            _gcashQrLoadedFor = qrUrl;

            const testImg = new Image();
            testImg.onload = function () {
                img.src = qrUrl;
                img.style.display = 'block';
                placeholder.style.display = 'none';
            };
            testImg.onerror = function () {
                _setQrPlaceholder(
                    'fas fa-exclamation-triangle',
                    'QR file missing on server. The database points to:<br>' +
                    '<code style="font-size:0.65rem;word-break:break-all;">' +
                    escapeHtml(qrUrl) + '</code>',
                    true
                );
                console.error('[POS] QR image failed to load:', qrUrl);
            };
            testImg.src = qrUrl;
        })
        .catch(function (err) {
            console.error('[POS] QR fetch failed:', err);
            _setQrPlaceholder(
                'fas fa-exclamation-triangle',
                'Failed to load QR: ' + escapeHtml(err.message),
                true
            );
        });
}


/* ============================================
   SUBMIT PAYMENT
   ============================================ */

function submitPayment() {
    let amount, reference;

    if (currentPaymentMethod === 'cash') {
        amount = parseFloat((document.getElementById('cashAmount') || {}).value) || 0;
        reference = null;
        if (amount < currentPaymentTotal) {
            showToast('Insufficient cash payment', 'error');
            return;
        }
    } else if (currentPaymentMethod === 'gcash') {
        amount = parseFloat((document.getElementById('gcashAmount') || {}).value) || 0;
        reference = ((document.getElementById('gcashRef') || {}).value || '').trim();
        if (amount < currentPaymentTotal) {
            showToast('Insufficient GCash amount', 'error');
            return;
        }
        if (!reference || reference.length !== 3) {
            showToast('Please enter the last 3 digits of the GCash reference', 'error');
            const gr = document.getElementById('gcashRef');
            if (gr) gr.focus();
            return;
        }
    } else {
        return;
    }

    const cn = document.getElementById('customerName');
    const customerName = cn ? (cn.value.trim() || null) : null;

    const saleData = {
        items: posCart.map(function (item) {
            return {
                product_id: item.id,
                quantity: item.quantity,
                selling_price: item.price
            };
        }),
        payment_method: currentPaymentMethod,
        payment_amount: amount,
        discount: 0,
        customer_name: customerName
    };
    if (reference) saleData.payment_reference = reference;

    const btn = document.getElementById('submitPaymentBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '⏳ Processing...';
    }

    fetch('/api/v1/sales', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': getCsrfToken() || ''
        },
        body: JSON.stringify(saleData)
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data && data.success) {
            closePaymentModal();
            const refNote = currentPaymentMethod === 'gcash'
                ? ' (Ref ***' + reference + ')' : '';
            showToast(
                '✅ Sale complete! ' + data.data.sale.invoice_number + refNote,
                'success'
            );
            posCart = [];
            renderPosCart();
            loadPosProducts(true);
        } else {
            showToast((data && data.message) || 'Sale failed', 'error');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '✅ Confirm Payment';
            }
        }
    })
    .catch(function (err) {
        console.error('[POS] Payment error:', err);
        showToast('Network error', 'error');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '✅ Confirm Payment';
        }
    });
}


/* ============================================
   INIT
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('posSearch');
    if (searchInput) {
        let debounceTimer;
        searchInput.addEventListener('input', function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(function () {
                posSearchQuery = searchInput.value;
                const clearBtn = document.getElementById('posSearchClear');
                if (clearBtn) clearBtn.classList.toggle('visible', posSearchQuery.length > 0);
                renderFilteredProducts();
            }, 150);
        });
        searchInput.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') clearPosSearch();
        });
    }

    const refreshBtn = document.getElementById('refreshProductsBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function () {
            loadPosProducts(false);
        });
    }

    const scanBtn = document.getElementById('scanBarcodeBtn');
    if (scanBtn) scanBtn.addEventListener('click', openBarcodeEntry);

    const modalInput = document.getElementById('barcodeEntryInput');
    if (modalInput) {
        modalInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                submitBarcodeEntry();
            } else if (e.key === 'Escape') {
                closeBarcodeEntry();
            }
        });
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'F2') {
            e.preventDefault();
            openBarcodeEntry();
        }
        if (e.ctrlKey && e.key === 'k') {
            e.preventDefault();
            const s = document.getElementById('posSearch');
            if (s) { s.focus(); s.select(); }
        }
    });

    window.addEventListener('beforeunload', stopCamera);

    loadPosProducts(false);
    startAutoRefresh();
});
