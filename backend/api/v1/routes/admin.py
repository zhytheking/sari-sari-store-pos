"""
Admin routes: stock management, product images, settings, GCash QR,
user password management.

Upload paths:
    Source mode:  <project>/frontend/web/static/assets/{products,qrcodes}/
    Frozen mode:  %LOCALAPPDATA%/SariSariPOS/uploads/{products,qrcodes}/
    The frozen path is used because _MEIPASS is a temp folder that
    gets recreated on every launch, and Program Files is read-only.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import bcrypt
import os
import sys
import uuid
from pathlib import Path

from database.connection import get_db, transaction
from utils.decorators import role_required, audit_log
from utils.logger import get_logger
from utils.validators import validate_password_strength
from utils.responses import (
    success_response,
    bad_request,
    not_found,
    server_error,
)

admin_bp = Blueprint('admin', __name__)
logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024

ALLOWED_SETTINGS_KEYS = {
    'store_name', 'store_address', 'store_phone', 'store_email',
    'tax_rate', 'currency_symbol', 'low_stock_threshold',
    'receipt_footer', 'enable_gcash', 'enable_bank_transfer',
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _static_upload_root():
    """
    Return the folder where uploaded images live.

    Frozen:  %LOCALAPPDATA%/SariSariPOS/uploads/
    Source:  <project>/frontend/web/static/assets/

    The frozen location is persistent across rebuilds and always
    writable — it never hits Program Files or _MEIPASS.
    """
    if getattr(sys, 'frozen', False):
        local = os.getenv("LOCALAPPDATA")
        if local:
            base = Path(local) / "SariSariPOS" / "uploads"
        else:
            base = (Path.home() / "AppData" / "Local"
                    / "SariSariPOS" / "uploads")
    else:
        base = (Path(__file__).resolve().parents[3]
                / "frontend" / "web" / "static" / "assets")

    base.mkdir(parents=True, exist_ok=True)
    return base


def _products_upload_folder():
    folder = _static_upload_root() / "products"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def _qrcodes_upload_folder():
    folder = _static_upload_root() / "qrcodes"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def ensure_settings_table(cursor, db):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _record_audit(**kwargs):
    """Wrapper that never raises."""
    try:
        from backend.api.v1.routes.audit import record_audit
        record_audit(**kwargs)
    except Exception as e:
        logger.warning(f"Audit write failed: {e}")


# ============================================
# STOCK MANAGEMENT
# ============================================

@admin_bp.route('/stock/add', methods=['POST'])
@jwt_required()
@role_required(['owner'])
@audit_log('ADD_STOCK')
def add_stock():
    try:
        data = request.get_json() or {}
        user_id = get_jwt_identity()
        product_id = data.get('product_id')
        quantity = data.get('quantity')
        reason = data.get('reason', 'Manual stock addition')
        note = data.get('note')

        if not product_id:
            return bad_request('Product ID is required', code='missing_product')
        if not quantity or quantity <= 0:
            return bad_request('Quantity must be greater than 0', code='invalid_quantity')

        old_quantity = new_quantity = product_name = None

        with transaction() as db:
            cursor = db.cursor()
            cursor.execute(
                "SELECT id, name, stock_quantity FROM products WHERE id = ? AND is_active = 1",
                (product_id,)
            )
            product = cursor.fetchone()
            if not product:
                raise ValueError("Product not found")
            product_name = product[1]
            old_quantity = product[2]
            new_quantity = old_quantity + quantity

            cursor.execute(
                "UPDATE products SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_quantity, product_id)
            )
            cursor.execute(
                """INSERT INTO inventory_adjustments
                   (product_id, user_id, old_quantity, new_quantity,
                    adjustment_type, reason, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (product_id, user_id, old_quantity, new_quantity, 'add', reason, note)
            )

        _record_audit(
            action='STOCK_ADD',
            category='stock',
            user_id=user_id,
            details=f"Added {quantity} to '{product_name}' ({old_quantity} → {new_quantity})",
            target_type='product',
            target_id=product_id,
            result='success',
            metadata={
                'quantity': quantity,
                'reason': reason,
                'note': note,
            },
            ip_address=request.remote_addr,
        )

        logger.info(f"Stock added to {product_name}: +{quantity} by user {user_id}")
        return success_response(
            data={
                'product_id': product_id, 'product_name': product_name,
                'old_quantity': old_quantity, 'added_quantity': quantity,
                'new_quantity': new_quantity, 'reason': reason, 'note': note,
            },
            message=f'Added {quantity} stock to {product_name}',
        )
    except ValueError as e:
        return not_found(str(e), code='product_not_found')
    except Exception as e:
        logger.error(f"Add stock error: {e}", exc_info=True)
        return server_error(str(e), code='add_stock_failed')


@admin_bp.route('/stock/remove', methods=['POST'])
@jwt_required()
@role_required(['owner'])
@audit_log('REMOVE_STOCK')
def remove_stock():
    try:
        data = request.get_json() or {}
        user_id = get_jwt_identity()
        product_id = data.get('product_id')
        quantity = data.get('quantity')
        reason = data.get('reason', 'Manual stock removal')
        note = data.get('note')

        if not product_id:
            return bad_request('Product ID is required', code='missing_product')
        if not quantity or quantity <= 0:
            return bad_request('Quantity must be greater than 0', code='invalid_quantity')

        old_quantity = new_quantity = product_name = None

        with transaction() as db:
            cursor = db.cursor()
            cursor.execute(
                "SELECT id, name, stock_quantity FROM products WHERE id = ? AND is_active = 1",
                (product_id,)
            )
            product = cursor.fetchone()
            if not product:
                raise ValueError("Product not found")
            product_name = product[1]
            old_quantity = product[2]
            if old_quantity < quantity:
                raise ValueError(f'Only {old_quantity} units available')
            new_quantity = old_quantity - quantity

            cursor.execute(
                "UPDATE products SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_quantity, product_id)
            )
            cursor.execute(
                """INSERT INTO inventory_adjustments
                   (product_id, user_id, old_quantity, new_quantity,
                    adjustment_type, reason, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (product_id, user_id, old_quantity, new_quantity, 'subtract', reason, note)
            )

        _record_audit(
            action='STOCK_REMOVE',
            category='stock',
            user_id=user_id,
            details=f"Removed {quantity} from '{product_name}' ({old_quantity} → {new_quantity})",
            target_type='product',
            target_id=product_id,
            result='success',
            metadata={
                'quantity': quantity,
                'reason': reason,
                'note': note,
            },
            ip_address=request.remote_addr,
        )

        logger.info(f"Stock removed from {product_name}: -{quantity} by user {user_id}")
        return success_response(
            data={
                'product_id': product_id, 'product_name': product_name,
                'old_quantity': old_quantity, 'removed_quantity': quantity,
                'new_quantity': new_quantity, 'reason': reason, 'note': note,
            },
            message=f'Removed {quantity} stock from {product_name}',
        )
    except ValueError as e:
        msg = str(e)
        if 'not found' in msg.lower():
            return not_found(msg, code='product_not_found')
        return bad_request(msg, code='insufficient_stock')
    except Exception as e:
        logger.error(f"Remove stock error: {e}", exc_info=True)
        return server_error(str(e), code='remove_stock_failed')


@admin_bp.route('/stock/adjust', methods=['POST'])
@jwt_required()
@role_required(['owner'])
@audit_log('ADJUST_STOCK')
def adjust_stock():
    try:
        data = request.get_json() or {}
        user_id = get_jwt_identity()
        product_id = data.get('product_id')
        new_quantity = data.get('new_quantity')
        reason = data.get('reason', 'Manual stock adjustment')
        note = data.get('note')

        if not product_id:
            return bad_request('Product ID is required', code='missing_product')
        if new_quantity is None or new_quantity < 0:
            return bad_request('Quantity must be 0 or greater', code='invalid_quantity')

        old_quantity = product_name = None

        with transaction() as db:
            cursor = db.cursor()
            cursor.execute(
                "SELECT id, name, stock_quantity FROM products WHERE id = ? AND is_active = 1",
                (product_id,)
            )
            product = cursor.fetchone()
            if not product:
                raise ValueError("Product not found")
            product_name = product[1]
            old_quantity = product[2]

            cursor.execute(
                "UPDATE products SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_quantity, product_id)
            )
            cursor.execute(
                """INSERT INTO inventory_adjustments
                   (product_id, user_id, old_quantity, new_quantity,
                    adjustment_type, reason, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (product_id, user_id, old_quantity, new_quantity, 'set', reason, note)
            )

        _record_audit(
            action='STOCK_ADJUST',
            category='stock',
            user_id=user_id,
            details=f"Adjusted '{product_name}' ({old_quantity} → {new_quantity})",
            target_type='product',
            target_id=product_id,
            result='success',
            metadata={
                'old_quantity': old_quantity,
                'new_quantity': new_quantity,
                'reason': reason,
                'note': note,
            },
            ip_address=request.remote_addr,
        )

        logger.info(f"Stock adjusted for {product_name}: {old_quantity} -> {new_quantity} by user {user_id}")
        return success_response(
            data={
                'product_id': product_id, 'product_name': product_name,
                'old_quantity': old_quantity, 'new_quantity': new_quantity,
                'change': new_quantity - old_quantity, 'reason': reason, 'note': note,
            },
            message=f'Stock adjusted for {product_name}',
        )
    except ValueError as e:
        return not_found(str(e), code='product_not_found')
    except Exception as e:
        logger.error(f"Adjust stock error: {e}", exc_info=True)
        return server_error(str(e), code='adjust_stock_failed')


# ============================================
# PRODUCT IMAGE MANAGEMENT
# ============================================

@admin_bp.route('/product/<int:product_id>/image', methods=['POST'])
@jwt_required()
@role_required(['owner'])
@audit_log('UPLOAD_PRODUCT_IMAGE')
def upload_product_image(product_id):
    try:
        user_id = get_jwt_identity()
        if 'image' not in request.files:
            return bad_request('No image file provided', code='no_file')
        file = request.files['image']
        if file.filename == '':
            return bad_request('No file selected', code='empty_file')
        if not allowed_file(file.filename):
            return bad_request(
                f'File type not allowed. Allowed: {", ".join(ALLOWED_EXTENSIONS)}',
                code='invalid_file_type',
            )
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > MAX_FILE_SIZE:
            return bad_request(
                f'File size exceeds {MAX_FILE_SIZE // (1024 * 1024)}MB limit',
                code='file_too_large',
            )

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name FROM products WHERE id = ? AND is_active = 1",
            (product_id,)
        )
        product = cursor.fetchone()
        if not product:
            return not_found('Product not found', code='product_not_found')

        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"product_{product_id}_{uuid.uuid4().hex[:8]}.{ext}"
        upload_folder = _products_upload_folder()
        file_path = os.path.join(upload_folder, filename)
        image_path = f"/static/assets/products/{filename}"

        file.save(file_path)
        try:
            with transaction() as tdb:
                tdb.cursor().execute(
                    "UPDATE products SET product_image = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (image_path, product_id)
                )
        except Exception:
            try:
                os.remove(file_path)
            except Exception:
                pass
            raise

        _record_audit(
            action='PRODUCT_IMAGE_UPLOAD',
            category='product',
            user_id=user_id,
            details=f"Uploaded image for '{product[1]}' ({image_path})",
            target_type='product',
            target_id=product_id,
            result='success',
            metadata={'image_path': image_path},
            ip_address=request.remote_addr,
        )

        logger.info(f"Image uploaded for product {product[1]} by user {user_id}")
        return success_response(
            data={'product_id': product_id, 'product_name': product[1],
                  'image_url': image_path, 'filename': filename},
            message='Product image uploaded successfully',
        )
    except Exception as e:
        logger.error(f"Upload image error: {e}", exc_info=True)
        return server_error(str(e), code='upload_failed')


@admin_bp.route('/product/<int:product_id>/image', methods=['DELETE'])
@jwt_required()
@role_required(['owner'])
@audit_log('REMOVE_PRODUCT_IMAGE')
def remove_product_image(product_id):
    try:
        user_id = get_jwt_identity()
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, product_image FROM products WHERE id = ? AND is_active = 1",
            (product_id,)
        )
        product = cursor.fetchone()
        if not product:
            return not_found('Product not found', code='product_not_found')
        if not product[2]:
            return not_found('Product has no image', code='no_image')

        old_image_path = product[2]
        with transaction() as tdb:
            tdb.cursor().execute(
                "UPDATE products SET product_image = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (product_id,)
            )
        try:
            image_filename = old_image_path.split('/')[-1]
            file_path = os.path.join(_products_upload_folder(), image_filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.warning(f"Could not delete image file: {e}")

        _record_audit(
            action='PRODUCT_IMAGE_REMOVE',
            category='product',
            user_id=user_id,
            details=f"Removed image from '{product[1]}'",
            target_type='product',
            target_id=product_id,
            result='success',
            ip_address=request.remote_addr,
        )

        logger.info(f"Image removed for product {product[1]} by user {user_id}")
        return success_response(
            data={'product_id': product_id, 'product_name': product[1]},
            message='Product image removed successfully',
        )
    except Exception as e:
        logger.error(f"Remove image error: {e}", exc_info=True)
        return server_error(str(e), code='remove_failed')


# ============================================
# BULK STOCK
# ============================================

@admin_bp.route('/stock/bulk-add', methods=['POST'])
@jwt_required()
@role_required(['owner'])
@audit_log('BULK_ADD_STOCK')
def bulk_add_stock():
    try:
        data = request.get_json() or {}
        user_id = get_jwt_identity()
        items = data.get('items', [])
        reason = data.get('reason', 'Bulk stock addition')
        note = data.get('note')

        if not items:
            return bad_request('No items provided', code='no_items')

        results = []
        with transaction() as db:
            cursor = db.cursor()
            for idx, item in enumerate(items):
                product_id = item.get('product_id')
                quantity = item.get('quantity', 0)
                if not product_id or quantity <= 0:
                    raise ValueError(f"Item {idx + 1}: product_id and positive quantity required")
                cursor.execute(
                    "SELECT id, name, stock_quantity FROM products WHERE id = ? AND is_active = 1",
                    (product_id,)
                )
                product = cursor.fetchone()
                if not product:
                    raise ValueError(f"Item {idx + 1}: product {product_id} not found")
                old_quantity = product[2]
                new_quantity = old_quantity + quantity
                cursor.execute(
                    "UPDATE products SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (new_quantity, product_id)
                )
                cursor.execute(
                    """INSERT INTO inventory_adjustments
                       (product_id, user_id, old_quantity, new_quantity,
                        adjustment_type, reason, note)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (product_id, user_id, old_quantity, new_quantity, 'add', reason, note)
                )
                results.append({
                    'product_id': product_id, 'product_name': product[1],
                    'old_quantity': old_quantity, 'added_quantity': quantity,
                    'new_quantity': new_quantity,
                })

        _record_audit(
            action='STOCK_BULK_ADD',
            category='stock',
            user_id=user_id,
            details=f"Bulk-added stock to {len(results)} products",
            result='success',
            metadata={
                'count': len(results),
                'reason': reason,
                'items': [r['product_id'] for r in results],
            },
            ip_address=request.remote_addr,
        )

        logger.info(f"Bulk stock added: {len(results)} products by user {user_id}")
        return success_response(
            data={'successful': results, 'errors': [], 'total_processed': len(results)},
            message=f'Added stock to {len(results)} products',
        )
    except ValueError as e:
        logger.warning(f"Bulk add rejected: {e}")
        return bad_request(
            str(e), code='bulk_add_failed',
            details={'successful': [], 'errors': [str(e)], 'total_processed': 0},
        )
    except Exception as e:
        logger.error(f"Bulk add stock error: {e}", exc_info=True)
        return server_error(str(e), code='bulk_add_failed')


@admin_bp.route('/stock/history', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_stock_history():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        product_id = request.args.get('product_id', type=int)
        adjustment_type = request.args.get('adjustment_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        db = get_db()
        cursor = db.cursor()

        query = """SELECT ia.id, ia.product_id, p.name as product_name,
                          ia.user_id, u.username,
                          ia.old_quantity, ia.new_quantity,
                          ia.adjustment_type, ia.reason, ia.note, ia.created_at
                   FROM inventory_adjustments ia
                   JOIN products p ON ia.product_id = p.id
                   JOIN users u ON ia.user_id = u.id"""
        params = []
        conditions = []

        if product_id:
            conditions.append("ia.product_id = ?"); params.append(product_id)
        if adjustment_type:
            conditions.append("ia.adjustment_type = ?"); params.append(adjustment_type)
        if start_date:
            conditions.append("DATE(ia.created_at) >= ?"); params.append(start_date)
        if end_date:
            conditions.append("DATE(ia.created_at) <= ?"); params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY ia.created_at DESC LIMIT ? OFFSET ?"
        params.extend([per_page, (page - 1) * per_page])
        cursor.execute(query, params)
        adjustments = cursor.fetchall()

        count_query = "SELECT COUNT(*) FROM inventory_adjustments ia"
        count_params = []
        if conditions:
            count_query += " WHERE " + " AND ".join(conditions)
            count_params = params[:-2]
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()[0]

        return success_response(data={
            'items': [
                {
                    'id': a[0], 'product_id': a[1], 'product_name': a[2],
                    'user_id': a[3], 'username': a[4],
                    'old_quantity': a[5], 'new_quantity': a[6],
                    'change': a[6] - a[5], 'adjustment_type': a[7],
                    'reason': a[8], 'note': a[9], 'created_at': a[10],
                } for a in adjustments
            ],
            'pagination': {
                'page': page, 'per_page': per_page, 'total': total,
                'pages': (total + per_page - 1) // per_page,
            }
        })
    except Exception as e:
        logger.error(f"Get stock history error: {e}", exc_info=True)
        return server_error(str(e), code='get_history_failed')


# ============================================
# USER MANAGEMENT
# ============================================

@admin_bp.route('/users/<int:user_id>/change-password', methods=['POST'])
@jwt_required()
@role_required(['owner'])
@audit_log('ADMIN_CHANGE_PASSWORD')
def admin_change_user_password(user_id):
    try:
        data = request.get_json() or {}
        admin_id = get_jwt_identity()
        new_password = data.get('new_password')

        if not new_password:
            return bad_request('New password is required', code='missing_password')
        try:
            validate_password_strength(new_password)
        except ValueError as e:
            return bad_request(str(e), code='validation_error')

        if str(user_id) == str(admin_id):
            return bad_request(
                'Use the profile settings to change your own password',
                code='cannot_change_own_password',
            )

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return not_found('User not found', code='user_not_found')

        password_hash = bcrypt.hashpw(
            new_password.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')

        with transaction() as tdb:
            tdb.cursor().execute(
                """UPDATE users
                   SET password_hash = ?,
                       password_changed_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (password_hash, user_id)
            )

        _record_audit(
            action='PASSWORD_RESET',
            category='user',
            user_id=admin_id,
            details=f"Admin reset password for '{user[1]}'",
            target_type='user',
            target_id=user_id,
            result='success',
            metadata={'username': user[1]},
            ip_address=request.remote_addr,
        )

        logger.info(f"Password changed for user {user[1]} by admin {admin_id}")
        return success_response(message=f'Password changed successfully for {user[1]}')
    except Exception as e:
        logger.error(f"Change password error: {e}", exc_info=True)
        return server_error(str(e), code='change_password_failed')


@admin_bp.route('/profile/change-password', methods=['POST'])
@jwt_required()
@audit_log('CHANGE_OWN_PASSWORD')
def change_own_password():
    try:
        data = request.get_json() or {}
        user_id = get_jwt_identity()
        old_password = data.get('old_password')
        new_password = data.get('new_password')

        if not old_password or not new_password:
            return bad_request(
                'Both old and new passwords are required',
                code='missing_fields',
            )
        try:
            validate_password_strength(new_password)
        except ValueError as e:
            return bad_request(str(e), code='validation_error')

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT username, password_hash FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return not_found('User not found', code='user_not_found')

        if not bcrypt.checkpw(old_password.encode('utf-8'), user[1].encode('utf-8')):
            return bad_request('Current password is incorrect', code='incorrect_password')

        password_hash = bcrypt.hashpw(
            new_password.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')

        with transaction() as tdb:
            tdb.cursor().execute(
                """UPDATE users
                   SET password_hash = ?,
                       password_changed_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (password_hash, user_id)
            )

        _record_audit(
            action='PASSWORD_CHANGE_SELF',
            category='auth',
            user_id=user_id,
            details=f"User '{user[0]}' changed their own password",
            target_type='user',
            target_id=user_id,
            result='success',
            ip_address=request.remote_addr,
        )

        logger.info(f"Password changed for user {user[0]} (self)")
        return success_response(message='Password changed successfully')
    except Exception as e:
        logger.error(f"Change own password error: {e}", exc_info=True)
        return server_error(str(e), code='change_password_failed')


# ============================================
# SETTINGS
# ============================================

@admin_bp.route('/settings', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_settings():
    try:
        db = get_db()
        cursor = db.cursor()
        ensure_settings_table(cursor, db)
        cursor.execute(
            "SELECT key, value, description, updated_at FROM system_settings ORDER BY key"
        )
        settings = cursor.fetchall()

        if not settings:
            default_settings = {
                'store_name': 'Saliga Sari-Sari Store',
                'store_address': '123 Main Street, City',
                'store_phone': '0912-345-6789',
                'store_email': 'info@longganigga-store.com',
                'tax_rate': '12.0',
                'currency_symbol': '₱',
                'low_stock_threshold': '10',
                'receipt_footer': 'Thank you for your purchase!',
                'enable_gcash': 'true',
                'enable_bank_transfer': 'false',
            }
            with transaction() as tdb:
                tcursor = tdb.cursor()
                ensure_settings_table(tcursor, tdb)
                for key, value in default_settings.items():
                    tcursor.execute(
                        "INSERT INTO system_settings (key, value, description) VALUES (?, ?, ?)",
                        (key, value, f'Default {key.replace("_", " ").title()}')
                    )
            cursor.execute(
                "SELECT key, value, description, updated_at FROM system_settings ORDER BY key"
            )
            settings = cursor.fetchall()

        return success_response(data={
            'settings': [
                {'key': s[0], 'value': s[1], 'description': s[2], 'updated_at': s[3]}
                for s in settings
            ]
        })
    except Exception as e:
        logger.error(f"Get settings error: {e}", exc_info=True)
        return server_error(str(e), code='get_settings_failed')


@admin_bp.route('/settings', methods=['PUT'])
@jwt_required()
@role_required(['owner'])
@audit_log('UPDATE_SETTINGS')
def update_settings():
    try:
        data = request.get_json() or {}
        user_id = get_jwt_identity()
        settings = data.get('settings', {})
        if not settings:
            return bad_request('No settings provided', code='no_settings')

        updated, skipped = [], []
        with transaction() as db:
            cursor = db.cursor()
            ensure_settings_table(cursor, db)
            for key, value in settings.items():
                if key not in ALLOWED_SETTINGS_KEYS:
                    skipped.append(key); continue
                cursor.execute(
                    """INSERT INTO system_settings (key, value, updated_at)
                       VALUES (?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(key) DO UPDATE SET
                           value = excluded.value,
                           updated_at = CURRENT_TIMESTAMP""",
                    (key, str(value) if value is not None else '')
                )
                updated.append(key)

        _record_audit(
            action='SETTINGS_UPDATE',
            category='settings',
            user_id=user_id,
            details=f"Updated {len(updated)} settings: {', '.join(updated)}",
            result='success',
            metadata={
                'updated': updated,
                'skipped': skipped,
            },
            ip_address=request.remote_addr,
        )

        logger.info(f"Settings updated by user {user_id}: {', '.join(updated)} (skipped: {', '.join(skipped) or 'none'})")
        return success_response(
            data={'updated': updated, 'skipped': skipped},
            message=f'Updated {len(updated)} settings',
        )
    except Exception as e:
        logger.error(f"Update settings error: {e}", exc_info=True)
        return server_error(str(e), code='update_settings_failed')


# ============================================
# GCASH QR
# ============================================

@admin_bp.route('/settings/gcash-qr', methods=['POST'])
@jwt_required()
@role_required(['owner'])
@audit_log('UPLOAD_GCASH_QR')
def upload_gcash_qr():
    try:
        user_id = get_jwt_identity()
        file = request.files.get('image') or request.files.get('qr_image')
        if not file:
            return bad_request('No image file provided', code='no_file')
        if file.filename == '':
            return bad_request('No file selected', code='empty_file')
        if not allowed_file(file.filename):
            return bad_request(
                f'File type not allowed. Allowed: {", ".join(ALLOWED_EXTENSIONS)}',
                code='invalid_file_type',
            )
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > MAX_FILE_SIZE:
            return bad_request(
                f'File size exceeds {MAX_FILE_SIZE // (1024 * 1024)}MB limit',
                code='file_too_large',
            )

        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"gcash_qr_{uuid.uuid4().hex[:8]}.{ext}"
        upload_folder = _qrcodes_upload_folder()
        file_path = os.path.join(upload_folder, filename)
        image_path = f"/static/assets/qrcodes/{filename}"

        db = get_db()
        cursor = db.cursor()
        ensure_settings_table(cursor, db)
        cursor.execute("SELECT value FROM system_settings WHERE key = 'gcash_qr_url'")
        old_row = cursor.fetchone()
        old_qr_url = old_row[0] if old_row and old_row[0] else None

        file.save(file_path)
        try:
            with transaction() as tdb:
                tcursor = tdb.cursor()
                ensure_settings_table(tcursor, tdb)
                tcursor.execute(
                    """INSERT INTO system_settings (key, value, updated_at)
                       VALUES ('gcash_qr_url', ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(key) DO UPDATE SET
                           value = excluded.value,
                           updated_at = CURRENT_TIMESTAMP""",
                    (image_path,)
                )
        except Exception:
            try:
                os.remove(file_path)
            except Exception:
                pass
            raise

        if old_qr_url:
            try:
                old_filename = old_qr_url.split('/')[-1]
                old_file_path = os.path.join(upload_folder, old_filename)
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)
            except Exception as e:
                logger.warning(f"Could not delete old QR: {e}")

        _record_audit(
            action='GCASH_QR_UPLOAD',
            category='settings',
            user_id=user_id,
            details=f"Uploaded GCash QR ({image_path})",
            result='success',
            metadata={'image_path': image_path},
            ip_address=request.remote_addr,
        )

        logger.info(f"GCash QR uploaded by user {user_id}: {image_path}")
        return success_response(
            data={'qr_image_url': image_path, 'image_url': image_path, 'filename': filename},
            message='GCash QR uploaded successfully',
        )
    except Exception as e:
        logger.error(f"Upload GCash QR error: {e}", exc_info=True)
        return server_error(str(e), code='upload_failed')


@admin_bp.route('/settings/gcash-qr', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_gcash_qr():
    try:
        db = get_db()
        cursor = db.cursor()
        ensure_settings_table(cursor, db)
        cursor.execute("SELECT value FROM system_settings WHERE key = 'gcash_qr_url'")
        row = cursor.fetchone()
        image_url = row[0] if row and row[0] else ''
        return success_response(data={'qr_image_url': image_url, 'image_url': image_url})
    except Exception as e:
        logger.error(f"Get GCash QR error: {e}", exc_info=True)
        return server_error(str(e), code='get_qr_failed')


@admin_bp.route('/settings/gcash-qr', methods=['DELETE'])
@jwt_required()
@role_required(['owner'])
@audit_log('REMOVE_GCASH_QR')
def remove_gcash_qr():
    try:
        user_id = get_jwt_identity()
        db = get_db()
        cursor = db.cursor()
        ensure_settings_table(cursor, db)
        cursor.execute("SELECT value FROM system_settings WHERE key = 'gcash_qr_url'")
        row = cursor.fetchone()
        image_url = row[0] if row and row[0] else None
        if not image_url:
            return not_found('No QR code to remove', code='no_qr')

        with transaction() as tdb:
            tcursor = tdb.cursor()
            ensure_settings_table(tcursor, tdb)
            tcursor.execute(
                """INSERT INTO system_settings (key, value, updated_at)
                   VALUES ('gcash_qr_url', '', CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       updated_at = CURRENT_TIMESTAMP"""
            )

        try:
            filename = image_url.split('/')[-1]
            file_path = os.path.join(_qrcodes_upload_folder(), filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Deleted QR file: {file_path}")
        except Exception as e:
            logger.warning(f"Could not delete QR file: {e}")

        _record_audit(
            action='GCASH_QR_REMOVE',
            category='settings',
            user_id=user_id,
            details=f"Removed GCash QR ({image_url})",
            result='success',
            ip_address=request.remote_addr,
        )

        logger.info(f"GCash QR removed by user {user_id}")
        return success_response(message='GCash QR removed successfully')
    except Exception as e:
        logger.error(f"Remove GCash QR error: {e}", exc_info=True)
        return server_error(str(e), code='remove_failed')


# ============================================
# STOCK SUMMARY
# ============================================

@admin_bp.route('/stock/summary', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_stock_summary():
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1")
        total_products = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(stock_quantity * purchase_price) FROM products WHERE is_active = 1")
        total_value = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1 AND stock_quantity <= min_stock_level")
        low_stock = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1 AND stock_quantity = 0")
        out_of_stock = cursor.fetchone()[0]
        cursor.execute(
            """SELECT ia.id, p.name, ia.old_quantity, ia.new_quantity,
                      ia.adjustment_type, ia.reason, ia.created_at, u.username
               FROM inventory_adjustments ia
               JOIN products p ON ia.product_id = p.id
               JOIN users u ON ia.user_id = u.id
               ORDER BY ia.created_at DESC LIMIT 10"""
        )
        recent = cursor.fetchall()

        return success_response(data={
            'summary': {
                'total_products': total_products,
                'total_inventory_value': float(total_value) if total_value else 0,
                'low_stock_count': low_stock,
                'out_of_stock_count': out_of_stock,
            },
            'recent_adjustments': [
                {
                    'id': r[0], 'product_name': r[1],
                    'old_quantity': r[2], 'new_quantity': r[3],
                    'adjustment_type': r[4], 'reason': r[5],
                    'created_at': r[6], 'username': r[7],
                } for r in recent
            ]
        })
    except Exception as e:
        logger.error(f"Get stock summary error: {e}", exc_info=True)
        return server_error(str(e), code='get_summary_failed')
