/**
 * settings.js — Settings page for owners.
 *
 * Depends on api-client.js.
 *
 * All API calls go through `API.*` helpers so URLs stay in sync
 * with the backend. No raw fetch() calls — this avoids the URL
 * mismatch bug that caused the QR 404s.
 */

let _setUsers = [];
let _setSelectedQrFile = null;


/* ============================================
   INIT
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
    loadSettings();
    loadUsers();
    loadGcashQr();
});


/* ============================================
   LOAD SETTINGS
   ============================================ */

function loadSettings() {
    API.admin.settings.get()
        .then(function (data) {
            if (!data || !data.success) return;
            const settings = (data.data && data.data.settings) || [];
            settings.forEach(function (s) {
                const el = document.getElementById(s.key);
                if (el) el.value = s.value;
            });
        })
        .catch(function (err) {
            console.error('[settings] load:', err);
        });
}


/* ============================================
   UPDATE SETTINGS
   ============================================ */

function updateSettings(event) {
    event.preventDefault();

    const get = function (id) {
        const el = document.getElementById(id);
        return el ? el.value : '';
    };

    const settings = {
        store_name: get('storeName'),
        store_address: get('storeAddress'),
        store_phone: get('storePhone'),
        store_email: get('storeEmail'),
        tax_rate: get('taxRate'),
        low_stock_threshold: get('lowStockThreshold'),
        receipt_footer: get('receiptFooter')
    };

    showLoading('Saving settings...');

    API.admin.settings.update(settings)
        .then(function (data) {
            hideLoading();
            if (data && data.success) {
                showToast('Settings saved successfully!', 'success');

                // Reload store info so the navbar and footer update
                // immediately. Without this, users must refresh the
                // page to see the new store name.
                if (typeof window.loadStoreInfo === 'function') {
                    window.loadStoreInfo();
                }
            } else {
                showToast((data && data.message) || 'Failed to save settings', 'error');
            }
        })
        .catch(function (err) {
            hideLoading();
            console.error('[settings] save:', err);
            showToast('Failed to save settings', 'error');
        });
}


/* ============================================
   LOAD USERS
   ============================================ */

function loadUsers() {
    fetch('/api/v1/auth/users?per_page=200', {
        credentials: 'same-origin'
    })
    .then(function (r) {
        if (r.status === 403) {
            showToast('You do not have permission to manage users', 'error');
            const select = document.getElementById('userSelect');
            if (select) select.innerHTML = '<option value="">Permission denied</option>';
            return null;
        }
        return r.json();
    })
    .then(function (data) {
        if (!data || !data.success) return;
        _setUsers = (data.data && data.data.items) || [];
        const select = document.getElementById('userSelect');
        if (!select) return;
        select.innerHTML = '<option value="">Select a user...</option>';
        _setUsers.forEach(function (u) {
            const opt = document.createElement('option');
            opt.value = u.id;
            opt.textContent = u.username + ' (' + (u.full_name || '') + ') - ' + u.role;
            select.appendChild(opt);
        });
    })
    .catch(function (err) {
        console.error('[settings] users:', err);
    });
}


/* ============================================
   GCASH QR
   ============================================ */

function loadGcashQr() {
    API.admin.settings.getGcashQr()
        .then(function (data) {
            const preview = document.getElementById('gcashQrPreview');
            if (!preview) return;

            const qrUrl = (data && data.success && data.data)
                ? (data.data.qr_image_url || data.data.image_url)
                : null;

            if (qrUrl) {
                preview.innerHTML =
                    '<img src="' + escapeHtml(qrUrl) +
                    '" alt="GCash QR Code">' +
                    '<p class="qr-placeholder-text" style="margin-top:10px;color:#198754;">' +
                    '<i class="fas fa-check-circle"></i> QR code uploaded</p>';
            } else {
                preview.innerHTML =
                    '<i class="fas fa-qrcode qr-placeholder-icon"></i>' +
                    '<p class="qr-placeholder-text">No QR uploaded</p>';
            }
        })
        .catch(function (err) {
            console.error('[settings] QR load:', err);
            const preview = document.getElementById('gcashQrPreview');
            if (preview) {
                preview.innerHTML =
                    '<i class="fas fa-qrcode qr-placeholder-icon"></i>' +
                    '<p class="qr-placeholder-text">No QR uploaded</p>';
            }
        });
}

function onQrFileChange(input) {
    const file = input.files && input.files[0];
    const filenameEl = document.getElementById('gcashQrFilename');
    const uploadBtn = document.getElementById('uploadQrBtn');

    if (!file) {
        _setSelectedQrFile = null;
        if (filenameEl) filenameEl.textContent = '';
        if (uploadBtn) uploadBtn.disabled = true;
        return;
    }

    if (file.size > 2 * 1024 * 1024) {
        showToast('Image must be under 2 MB', 'error');
        input.value = '';
        _setSelectedQrFile = null;
        if (filenameEl) filenameEl.textContent = '';
        if (uploadBtn) uploadBtn.disabled = true;
        return;
    }

    const allowed = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'];
    if (allowed.indexOf(file.type) === -1) {
        showToast('Only PNG, JPG, or WEBP allowed', 'error');
        input.value = '';
        _setSelectedQrFile = null;
        if (filenameEl) filenameEl.textContent = '';
        if (uploadBtn) uploadBtn.disabled = true;
        return;
    }

    _setSelectedQrFile = file;
    if (filenameEl) {
        filenameEl.innerHTML = '<i class="fas fa-file-image"></i> ' +
            escapeHtml(file.name) + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
    }
    if (uploadBtn) uploadBtn.disabled = false;
}

function uploadGcashQr() {
    if (!_setSelectedQrFile) {
        showToast('Please select an image first', 'warning');
        return;
    }

    const formData = new FormData();
    // Backend's upload handler reads `request.files.get('image')`
    // first, falling back to 'qr_image'. Use 'image' for clarity.
    formData.append('image', _setSelectedQrFile);

    const uploadBtn = document.getElementById('uploadQrBtn');
    if (uploadBtn) {
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading...';
    }

    showLoading('Uploading QR code...');

    API.admin.settings.uploadGcashQr(formData)
        .then(function (data) {
            hideLoading();
            if (uploadBtn) {
                uploadBtn.disabled = false;
                uploadBtn.innerHTML = '<i class="fas fa-upload"></i> Upload QR';
            }
            if (data && data.success) {
                showToast('✅ GCash QR uploaded successfully!', 'success');
                const fileInput = document.getElementById('gcashQrFile');
                if (fileInput) fileInput.value = '';
                const fn = document.getElementById('gcashQrFilename');
                if (fn) fn.textContent = '';
                _setSelectedQrFile = null;
                if (uploadBtn) uploadBtn.disabled = true;
                loadGcashQr();
            } else {
                showToast((data && data.message) || 'Upload failed', 'error');
            }
        })
        .catch(function (err) {
            hideLoading();
            if (uploadBtn) {
                uploadBtn.disabled = false;
                uploadBtn.innerHTML = '<i class="fas fa-upload"></i> Upload QR';
            }
            console.error('[settings] QR upload:', err);
            showToast('Upload failed: ' + (err.message || err), 'error');
        });
}

function removeGcashQr() {
    if (!confirm('Remove the GCash QR code?')) return;

    showLoading('Removing QR code...');

    API.admin.settings.removeGcashQr()
        .then(function (data) {
            hideLoading();
            if (data && data.success) {
                showToast('GCash QR removed', 'success');
                loadGcashQr();
            } else {
                showToast((data && data.message) || 'Remove failed', 'error');
            }
        })
        .catch(function (err) {
            hideLoading();
            console.error('[settings] QR remove:', err);
            showToast('Remove failed: ' + (err.message || err), 'error');
        });
}


/* ============================================
   PASSWORD VALIDATION
   ============================================ */

function validatePasswordStrength(prefix) {
    const pw = ((document.getElementById(prefix + 'NewPassword') || {}).value) || '';
    const setClass = function (id, ok) {
        const el = document.getElementById(id);
        if (el) el.className = ok ? 'valid' : 'invalid';
    };
    setClass(prefix + 'Length', pw.length >= 8);
    setClass(prefix + 'Uppercase', /[A-Z]/.test(pw));
    setClass(prefix + 'Lowercase', /[a-z]/.test(pw));
    setClass(prefix + 'Number', /[0-9]/.test(pw));
    validatePasswordMatch(prefix);
}

function validatePasswordMatch(prefix) {
    const pw = ((document.getElementById(prefix + 'NewPassword') || {}).value) || '';
    const cf = ((document.getElementById(prefix + 'ConfirmPassword') || {}).value) || '';
    const el = document.getElementById(prefix + 'Match');
    if (!el) return;
    if (cf.length > 0) {
        el.className = pw === cf ? 'valid' : 'invalid';
    } else {
        el.className = '';
    }
}


/* ============================================
   CHANGE OWN PASSWORD
   ============================================ */

function changeOwnPassword(event) {
    event.preventDefault();

    const get = function (id) {
        const el = document.getElementById(id);
        return el ? el.value : '';
    };

    const oldPassword = get('ownOldPassword');
    const newPassword = get('ownNewPassword');
    const confirmPassword = get('ownConfirmPassword');

    if (newPassword !== confirmPassword) {
        showToast('Passwords do not match', 'error');
        return;
    }
    if (newPassword.length < 8 ||
        !/[A-Z]/.test(newPassword) ||
        !/[a-z]/.test(newPassword) ||
        !/[0-9]/.test(newPassword)) {
        showToast('Password does not meet requirements', 'error');
        return;
    }
    if (!confirm('Are you sure you want to change your password?')) return;

    showLoading('Changing password...');

    API.admin.profile.changePassword(oldPassword, newPassword)
        .then(function (data) {
            hideLoading();
            if (data && data.success) {
                showToast('Password changed successfully!', 'success');
                const form = document.getElementById('changeOwnPasswordForm');
                if (form) form.reset();
                ['ownLength', 'ownUppercase', 'ownLowercase', 'ownNumber', 'ownMatch']
                    .forEach(function (id) {
                        const el = document.getElementById(id);
                        if (el) el.className = '';
                    });
            } else {
                showToast((data && data.message) || 'Failed to change password', 'error');
            }
        })
        .catch(function (err) {
            hideLoading();
            console.error('[settings] own password:', err);
            showToast('Failed to change password', 'error');
        });
}


/* ============================================
   CHANGE USER PASSWORD (ADMIN)
   ============================================ */

function changeUserPassword(event) {
    event.preventDefault();

    const get = function (id) {
        const el = document.getElementById(id);
        return el ? el.value : '';
    };

    const userId = get('userSelect');
    const newPassword = get('userNewPassword');
    const confirmPassword = get('userConfirmPassword');

    if (!userId) {
        showToast('Please select a user', 'error');
        return;
    }
    if (newPassword !== confirmPassword) {
        showToast('Passwords do not match', 'error');
        return;
    }
    if (newPassword.length < 8 ||
        !/[A-Z]/.test(newPassword) ||
        !/[a-z]/.test(newPassword) ||
        !/[0-9]/.test(newPassword)) {
        showToast('Password does not meet requirements', 'error');
        return;
    }

    const user = _setUsers.find(function (u) {
        return u.id === parseInt(userId, 10);
    });
    if (!confirm('Reset password for "' + ((user && user.username) || userId) + '"?')) return;

    showLoading('Resetting password...');

    API.admin.users.changePassword(parseInt(userId, 10), newPassword)
        .then(function (data) {
            hideLoading();
            if (data && data.success) {
                showToast(data.message || 'Password reset successfully', 'success');
                const form = document.getElementById('changeUserPasswordForm');
                if (form) form.reset();
                ['userLength', 'userUppercase', 'userLowercase', 'userNumber', 'userMatch']
                    .forEach(function (id) {
                        const el = document.getElementById(id);
                        if (el) el.className = '';
                    });
            } else {
                showToast((data && data.message) || 'Failed to reset password', 'error');
            }
        })
        .catch(function (err) {
            hideLoading();
            console.error('[settings] user password:', err);
            showToast('Failed to reset password', 'error');
        });
}
