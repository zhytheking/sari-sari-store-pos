from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from database.connection import get_db
from utils.logger import get_logger

settings_bp = Blueprint('settings', __name__)
logger = get_logger(__name__)


#Defaults used if the settings table is empty
DEFAULT_STORE_INFO = {
    'store_name': 'Saliga Sari-Sari Store',
    'store_address': '123 Main Street, City',
    'store_phone': '0936-104-2845',
    'store_email': 'email@gmail.com',
    'tax_rate': '12.0',
    'currency_symbol': '₱',
    'low_stock_threshold': '10',
    'receipt_footer': 'Thank you for your purchase!',
}


def _ensure_settings_table(cursor, db):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()


def _read_settings():
    db = get_db()
    cursor = db.cursor()
    _ensure_settings_table(cursor, db)

    cursor.execute("SELECT key, value FROM system_settings")
    rows = cursor.fetchall()

    settings = {}
    for row in rows:
        settings[row['key']] = row['value']

    for key, default in DEFAULT_STORE_INFO.items():
        settings.setdefault(key, default)

    return settings


@settings_bp.route('/public', methods=['GET'])
@jwt_required()
def get_public_settings():
    """
    Get store info for any authenticated user.

    Used by:
      - Web navbar/footer
      - POS header
      - Receipt generation
      - GUI Settings tab
    """
    try:
        s = _read_settings()

        return jsonify({
            'success': True,
            'data': {
                'store_name':          s['store_name'],
                'store_address':       s['store_address'],
                'store_phone':         s['store_phone'],
                'store_email':         s['store_email'],
                'tax_rate':            s['tax_rate'],
                'currency_symbol':     s['currency_symbol'],
                'low_stock_threshold': s['low_stock_threshold'],
                'receipt_footer':      s['receipt_footer'],
            }
        }), 200

    except Exception as e:
        logger.error(f"Get public settings error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'get_settings_failed',
            'message': str(e),
        }), 500


@settings_bp.route('/public-no-auth', methods=['GET'])
def get_public_settings_no_auth():
    #Public endpoint used by the GUI login screen.
    #Returns only the store name — nothing sensitive.
   
    try:
        s = _read_settings()

        return jsonify({
            'success': True,
            'data': {
                'store_name': s['store_name'],
            }
        }), 200

    except Exception as e:
        logger.error(f"Get no-auth settings error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'get_settings_failed',
            'message': str(e),
        }), 500


@settings_bp.route('/gcash-qr', methods=['GET'])
@jwt_required()
def get_gcash_qr():
    #Get the GCash QR image path. Any logged-in user can read it
    try:
        db = get_db()
        cursor = db.cursor()
        _ensure_settings_table(cursor, db)

        cursor.execute(
            "SELECT value FROM system_settings WHERE key = 'gcash_qr_url'"
        )
        row = cursor.fetchone()

        image_url = row['value'] if row and row['value'] else None

        return jsonify({
            'success': True,
            'data': {
                'image_url': image_url,
                'qr_image_url': image_url,
                'has_qr': bool(image_url),
            }
        }), 200

    except Exception as e:
        logger.error(f"Get GCash QR error: {e}", exc_info=True)
        return jsonify({'error': 'get_gcash_qr_failed', 'message': str(e)}), 500
