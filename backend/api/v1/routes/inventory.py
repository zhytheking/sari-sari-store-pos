from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import ValidationError

from database.connection import get_db
from api.v1.schemas.product import StockTransferSchema
from utils.validators import validate_input
from utils.decorators import role_required
from utils.logger import get_logger

inventory_bp = Blueprint('inventory', __name__)
logger = get_logger(__name__)


# ════════════════
# TRANSFER STOCK
# ════════════════

@inventory_bp.route('/transfer', methods=['POST'])
@jwt_required()
@role_required(['owner'])
@validate_input(StockTransferSchema)
def transfer_stock():
    """
    Transfer stock between products.
    The service owns the transaction. If any step fails, nothing
    is written. Business errors raise ValueError, which we turn
    into a 400 response.
    """
    try:
        data = request.validated_data
        user_id = get_jwt_identity()

        from core.services.inventory_service import InventoryService

        service = InventoryService()
        result = service.transfer_stock(
            from_product_id=data['from_product_id'],
            to_product_id=data['to_product_id'],
            quantity=data['quantity'],
            reason=data['reason'],
            note=data.get('note'),
            user_id=user_id,
        )

        logger.info(
            f"Stock transfer: {result['from_product']} → "
            f"{result['to_product']} (qty {data['quantity']}) "
            f"by user {user_id}"
        )

        return jsonify({
            'success': True,
            'message': 'Stock transferred successfully',
            'data': result,
        }), 200

    except ValidationError as e:
        return jsonify({
            'error': 'validation_error',
            'message': 'Invalid input data',
            'details': e.messages,
        }), 400
    except ValueError as e:
        return jsonify({
            'error': 'transfer_error',
            'message': str(e),
        }), 400
    except Exception as e:
        logger.error(f"Transfer failed: {e}", exc_info=True)
        return jsonify({
            'error': 'transfer_failed',
            'message': str(e),
        }), 500


# ═════════
# HISTORY
# ═════════

@inventory_bp.route('/history', methods=['GET'])
@jwt_required()
def get_inventory_history():
    #Get inventory adjustment history with filters
    try:
        product_id = request.args.get('product_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        db = get_db()
        cursor = db.cursor()

        conditions = []
        params = []

        if product_id:
            conditions.append("ia.product_id = ?")
            params.append(product_id)
        if start_date:
            conditions.append("DATE(ia.created_at) >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(ia.created_at) <= ?")
            params.append(end_date)

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""SELECT ia.id, ia.product_id, p.name as product_name,
                           ia.user_id, u.username,
                           ia.old_quantity, ia.new_quantity,
                           ia.adjustment_type, ia.reason, ia.note, ia.created_at
                    FROM inventory_adjustments ia
                    JOIN products p ON ia.product_id = p.id
                    JOIN users u ON ia.user_id = u.id
                    {where_clause}
                    ORDER BY ia.created_at DESC
                    LIMIT ? OFFSET ?"""

        cursor.execute(query, params + [per_page, (page - 1) * per_page])
        rows = cursor.fetchall()

        count_query = f"""SELECT COUNT(*)
                          FROM inventory_adjustments ia
                          {where_clause}"""
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        return jsonify({
            'success': True,
            'data': {
                'items': [
                    {
                        'id': r['id'],
                        'product_id': r['product_id'],
                        'product_name': r['product_name'],
                        'user_id': r['user_id'],
                        'username': r['username'],
                        'old_quantity': r['old_quantity'],
                        'new_quantity': r['new_quantity'],
                        'change': r['new_quantity'] - r['old_quantity'],
                        'adjustment_type': r['adjustment_type'],
                        'reason': r['reason'],
                        'note': r['note'],
                        'created_at': r['created_at'],
                    }
                    for r in rows
                ],
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'pages': (total + per_page - 1) // per_page,
                }
            }
        }), 200

    except Exception as e:
        logger.error(f"Get history error: {e}", exc_info=True)
        return jsonify({'error': 'get_history_failed', 'message': str(e)}), 500


# ══════════
# LOW STOCK
# ══════════

@inventory_bp.route('/low-stock', methods=['GET'])
@jwt_required()
def get_low_stock_products():
    #Get products with low stock
    try:
        threshold = request.args.get('threshold', 10, type=int)

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT id, name, stock_quantity, min_stock_level, unit
               FROM products
               WHERE is_active = 1 AND stock_quantity <= ?
               ORDER BY stock_quantity ASC""",
            (threshold,)
        )
        rows = cursor.fetchall()

        return jsonify({
            'success': True,
            'data': {
                'items': [
                    {
                        'id': r['id'],
                        'name': r['name'],
                        'stock_quantity': r['stock_quantity'],
                        'min_stock_level': r['min_stock_level'],
                        'unit': r['unit'],
                    }
                    for r in rows
                ],
                'count': len(rows),
            }
        }), 200

    except Exception as e:
        logger.error(f"Get low stock error: {e}", exc_info=True)
        return jsonify({'error': 'get_low_stock_failed', 'message': str(e)}), 500


# ══════════════
# PRODUCT STOCK
# ══════════════

@inventory_bp.route('/<int:product_id>/stock', methods=['GET'])
@jwt_required()
def get_product_stock(product_id):
    #Get current stock and recent history for a product
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            """SELECT id, name, stock_quantity, min_stock_level, purchase_price
               FROM products WHERE id = ? AND is_active = 1""",
            (product_id,)
        )
        product = cursor.fetchone()
        if not product:
            return jsonify({
                'error': 'product_not_found',
                'message': 'Product not found'
            }), 404

        cursor.execute(
            """SELECT id, old_quantity, new_quantity, adjustment_type,
                      reason, created_at
               FROM inventory_adjustments
               WHERE product_id = ?
               ORDER BY created_at DESC LIMIT 10""",
            (product_id,)
        )
        adjustments = cursor.fetchall()

        return jsonify({
            'success': True,
            'data': {
                'product_id': product['id'],
                'product_name': product['name'],
                'current_stock': product['stock_quantity'],
                'min_stock_level': product['min_stock_level'],
                'is_low_stock': product['stock_quantity'] <= product['min_stock_level'],
                'total_value': (product['stock_quantity']
                                * float(product['purchase_price'] or 0)),
                'recent_adjustments': [
                    {
                        'id': a['id'],
                        'old_quantity': a['old_quantity'],
                        'new_quantity': a['new_quantity'],
                        'change': a['new_quantity'] - a['old_quantity'],
                        'adjustment_type': a['adjustment_type'],
                        'reason': a['reason'],
                        'created_at': a['created_at'],
                    }
                    for a in adjustments
                ]
            }
        }), 200

    except Exception as e:
        logger.error(f"Get product stock error: {e}", exc_info=True)
        return jsonify({'error': 'get_stock_failed', 'message': str(e)}), 500


# ═════════
# SUMMARY
# ═════════

@inventory_bp.route('/summary', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_inventory_summary():
    #Get inventory summary report
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1")
        total_products = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM products "
            "WHERE is_active = 1 AND stock_quantity <= min_stock_level"
        )
        low_stock_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM products "
            "WHERE is_active = 1 AND stock_quantity = 0"
        )
        out_of_stock_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COALESCE(SUM(stock_quantity * purchase_price), 0) "
            "FROM products WHERE is_active = 1"
        )
        total_value = cursor.fetchone()[0] or 0

        cursor.execute(
            """SELECT c.name, COUNT(p.id) as product_count,
                      COALESCE(SUM(p.stock_quantity * p.purchase_price), 0) as total_value
               FROM categories c
               LEFT JOIN products p ON c.id = p.category_id AND p.is_active = 1
               GROUP BY c.id
               HAVING product_count > 0"""
        )
        categories = cursor.fetchall()

        return jsonify({
            'success': True,
            'data': {
                'total_products': total_products,
                'low_stock_count': low_stock_count,
                'out_of_stock_count': out_of_stock_count,
                'total_inventory_value': float(total_value),
                'categories': [
                    {
                        'category': c['name'],
                        'product_count': c['product_count'],
                        'total_value': float(c['total_value']),
                    }
                    for c in categories
                ],
            }
        }), 200

    except Exception as e:
        logger.error(f"Get summary error: {e}", exc_info=True)
        return jsonify({'error': 'get_summary_failed', 'message': str(e)}), 500


# ═══════════
# DASHBOARD
# ═══════════

@inventory_bp.route('/dashboard', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_inventory_dashboard():
    #Get inventory dashboard data with alerts
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM products "
            "WHERE is_active = 1 AND stock_quantity <= min_stock_level"
        )
        low_stock_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM products "
            "WHERE is_active = 1 AND stock_quantity = 0"
        )
        out_of_stock_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1")
        total_products = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COALESCE(SUM(stock_quantity * purchase_price), 0) "
            "FROM products WHERE is_active = 1"
        )
        total_value = cursor.fetchone()[0] or 0

        cursor.execute(
            """SELECT id, name, stock_quantity, min_stock_level
               FROM products
               WHERE is_active = 1 AND stock_quantity <= min_stock_level
               ORDER BY stock_quantity ASC
               LIMIT 5"""
        )
        low_stock_products = cursor.fetchall()

        return jsonify({
            'success': True,
            'data': {
                'summary': {
                    'total_products': total_products,
                    'low_stock_count': low_stock_count,
                    'out_of_stock_count': out_of_stock_count,
                    'total_inventory_value': float(total_value),
                },
                'alerts': {
                    'low_stock': [
                        {
                            'id': p['id'],
                            'name': p['name'],
                            'stock_quantity': p['stock_quantity'],
                            'min_stock_level': p['min_stock_level'],
                        }
                        for p in low_stock_products
                    ],
                },
            }
        }), 200

    except Exception as e:
        logger.error(f"Get dashboard error: {e}", exc_info=True)
        return jsonify({'error': 'get_dashboard_failed', 'message': str(e)}), 500
