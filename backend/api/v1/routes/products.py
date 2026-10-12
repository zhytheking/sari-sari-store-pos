"""
Product management routes.

Audit:
    Product create/update/delete/reactivate all write to audit_logs.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import ValidationError
import random
import sqlite3

from database.connection import get_db, transaction
from api.v1.schemas.product import (
    ProductCreateSchema,
    ProductUpdateSchema,
    CategoryCreateSchema,
)
from utils.validators import validate_input
from utils.decorators import role_required
from utils.logger import get_logger

products_bp = Blueprint('products', __name__)
logger = get_logger(__name__)


def _record_audit(**kwargs):
    """Wrapper that never raises."""
    try:
        from backend.api.v1.routes.audit import record_audit
        record_audit(**kwargs)
    except Exception as e:
        logger.warning(f"Audit write failed: {e}")


# ============================================
# PUBLIC LISTING
# ============================================

@products_bp.route('', methods=['GET'])
@products_bp.route('/', methods=['GET'])
def list_products():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        category = request.args.get('category')
        search = request.args.get('search')
        min_price = request.args.get('min_price', type=float)
        max_price = request.args.get('max_price', type=float)
        low_stock = request.args.get('low_stock',
                                     type=lambda v: v.lower() == 'true',
                                     default=False)
        stock_type = request.args.get('stock_type')

        active_arg = request.args.get('active')
        active_filter = True
        if active_arg is not None:
            if active_arg.lower() == 'all':
                active_filter = None
            else:
                active_filter = active_arg.lower() == 'true'

        db = get_db()
        cursor = db.cursor()

        cursor.execute("SELECT name, icon, color FROM stock_types")
        stock_type_map = {row['name']: {'icon': row['icon'], 'color': row['color']}
                          for row in cursor.fetchall()}
        if not stock_type_map:
            stock_type_map = {
                'regular': {'icon': 'fas fa-box', 'color': '#2d6a4f'},
                'premium': {'icon': 'fas fa-crown', 'color': '#ffb703'},
                'discount': {'icon': 'fas fa-tag', 'color': '#dc3545'},
                'new_arrival': {'icon': 'fas fa-star', 'color': '#0d6efd'},
                'limited': {'icon': 'fas fa-clock', 'color': '#6f42c1'},
            }

        conditions = []
        params = []
        if active_filter is not None:
            conditions.append("p.is_active = ?")
            params.append(1 if active_filter else 0)
        if category:
            conditions.append("c.name = ?")
            params.append(category)
        if stock_type:
            conditions.append("p.stock_type = ?")
            params.append(stock_type)
        if search:
            conditions.append(
                "(p.name LIKE ? OR p.barcode LIKE ? OR p.description LIKE ?)"
            )
            s = f"%{search}%"
            params.extend([s, s, s])
        if min_price is not None:
            conditions.append("p.selling_price >= ?")
            params.append(min_price)
        if max_price is not None:
            conditions.append("p.selling_price <= ?")
            params.append(max_price)
        if low_stock:
            conditions.append("p.stock_quantity <= p.min_stock_level")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""SELECT p.id, p.name, p.description, p.barcode,
                           p.category_id, c.name as category_name,
                           p.purchase_price, p.selling_price,
                           p.stock_quantity, p.min_stock_level,
                           p.unit, p.tax_rate, p.is_active,
                           p.stock_type, p.product_image,
                           p.created_at, p.updated_at
                    FROM products p
                    LEFT JOIN categories c ON p.category_id = c.id
                    {where_clause}
                    ORDER BY p.name ASC
                    LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, (page - 1) * per_page])
        rows = cursor.fetchall()

        items = []
        for row in rows:
            p = dict(row)
            st = p['stock_type'] or 'regular'
            info = stock_type_map.get(st, {'icon': 'fas fa-box', 'color': '#2d6a4f'})
            items.append({
                'id': p['id'], 'name': p['name'], 'description': p['description'],
                'barcode': p['barcode'], 'category_id': p['category_id'],
                'category_name': p['category_name'],
                'purchase_price': float(p['purchase_price'] or 0),
                'selling_price': float(p['selling_price'] or 0),
                'stock_quantity': p['stock_quantity'],
                'min_stock_level': p['min_stock_level'], 'unit': p['unit'],
                'tax_rate': float(p['tax_rate'] or 0),
                'is_active': bool(p['is_active']),
                'stock_type': st, 'stock_icon': info['icon'],
                'stock_color': info['color'],
                'stock_label': st.replace('_', ' ').title(),
                'product_image': p['product_image'],
                'is_low_stock': p['stock_quantity'] <= p['min_stock_level'],
                'created_at': p['created_at'], 'updated_at': p['updated_at'],
            })

        count_query = f"""SELECT COUNT(*) FROM products p
                          LEFT JOIN categories c ON p.category_id = c.id
                          {where_clause}"""
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        return jsonify({'success': True, 'data': {
            'items': items,
            'pagination': {'page': page, 'per_page': per_page, 'total': total,
                           'pages': (total + per_page - 1) // per_page},
        }}), 200
    except Exception as e:
        logger.error(f"List products error: {e}", exc_info=True)
        return jsonify({'error': 'list_products_failed', 'message': str(e)}), 500


@products_bp.route('/<int:product_id>', methods=['GET'])
def get_product(product_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT p.id, p.name, p.description, p.barcode,
                      p.category_id, c.name as category_name,
                      p.purchase_price, p.selling_price,
                      p.stock_quantity, p.min_stock_level,
                      p.unit, p.tax_rate, p.is_active,
                      p.stock_type, p.product_image,
                      p.created_at, p.updated_at
               FROM products p
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE p.id = ?""",
            (product_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'product_not_found',
                            'message': 'Product not found'}), 404

        p = dict(row)
        st = p['stock_type'] or 'regular'
        cursor.execute("SELECT icon, color FROM stock_types WHERE name = ?", (st,))
        info = cursor.fetchone()
        icon = info['icon'] if info else 'fas fa-box'
        color = info['color'] if info else '#2d6a4f'

        return jsonify({'success': True, 'data': {
            'id': p['id'], 'name': p['name'], 'description': p['description'],
            'barcode': p['barcode'], 'category_id': p['category_id'],
            'category_name': p['category_name'],
            'purchase_price': float(p['purchase_price'] or 0),
            'selling_price': float(p['selling_price'] or 0),
            'stock_quantity': p['stock_quantity'],
            'min_stock_level': p['min_stock_level'], 'unit': p['unit'],
            'tax_rate': float(p['tax_rate'] or 0),
            'is_active': bool(p['is_active']),
            'stock_type': st, 'stock_icon': icon, 'stock_color': color,
            'stock_label': st.replace('_', ' ').title(),
            'product_image': p['product_image'],
            'is_low_stock': p['stock_quantity'] <= p['min_stock_level'],
            'created_at': p['created_at'], 'updated_at': p['updated_at'],
        }}), 200
    except Exception as e:
        logger.error(f"Get product error: {e}", exc_info=True)
        return jsonify({'error': 'get_product_failed', 'message': str(e)}), 500


# ============================================
# OWNER CREATE
# ============================================

@products_bp.route('', methods=['POST'])
@products_bp.route('/', methods=['POST'])
@jwt_required()
@role_required(['owner'])
@validate_input(ProductCreateSchema)
def create_product():
    try:
        data = request.validated_data
        user_id = get_jwt_identity()
        product_id = None

        with transaction() as db:
            cursor = db.cursor()

            if data.get('barcode'):
                cursor.execute("SELECT id FROM products WHERE barcode = ?",
                               (data['barcode'],))
                if cursor.fetchone():
                    raise ValueError("Barcode already exists")

            if data.get('category_id'):
                cursor.execute("SELECT id FROM categories WHERE id = ?",
                               (data['category_id'],))
                if not cursor.fetchone():
                    raise ValueError("Category not found")

            cursor.execute(
                """INSERT INTO products
                   (name, description, barcode, category_id, purchase_price,
                    selling_price, stock_quantity, min_stock_level, unit,
                    tax_rate, stock_type, product_image)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (data['name'], data.get('description'), data.get('barcode'),
                 data.get('category_id'), float(data['purchase_price']),
                 float(data['selling_price']), data.get('stock_quantity', 0),
                 data.get('min_stock_level', 10), data.get('unit', 'pc'),
                 float(data.get('tax_rate', 0)),
                 data.get('stock_type', 'regular'),
                 data.get('product_image')))
            product_id = cursor.lastrowid

        _record_audit(
            action='PRODUCT_CREATE',
            category='product',
            user_id=user_id,
            details=f"Created product '{data['name']}' (id={product_id})",
            target_type='product',
            target_id=product_id,
            result='success',
            metadata={
                'name': data['name'],
                'selling_price': float(data['selling_price']),
                'stock_quantity': data.get('stock_quantity', 0),
            },
            ip_address=request.remote_addr,
        )

        logger.info(f"Product created: {data['name']} (id={product_id}) by user {user_id}")

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT p.id, p.name, p.description, p.barcode,
                      p.category_id, c.name as category_name,
                      p.purchase_price, p.selling_price,
                      p.stock_quantity, p.min_stock_level,
                      p.unit, p.tax_rate, p.is_active,
                      p.stock_type, p.product_image,
                      p.created_at, p.updated_at
               FROM products p
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE p.id = ?""",
            (product_id,))
        p = dict(cursor.fetchone())

        return jsonify({'success': True, 'message': 'Product created successfully',
                        'data': {
            'id': p['id'], 'name': p['name'], 'description': p['description'],
            'barcode': p['barcode'], 'category_id': p['category_id'],
            'category_name': p['category_name'],
            'purchase_price': float(p['purchase_price'] or 0),
            'selling_price': float(p['selling_price'] or 0),
            'stock_quantity': p['stock_quantity'],
            'min_stock_level': p['min_stock_level'], 'unit': p['unit'],
            'tax_rate': float(p['tax_rate'] or 0),
            'is_active': bool(p['is_active']),
            'stock_type': p['stock_type'] or 'regular',
            'product_image': p['product_image'],
            'is_low_stock': p['stock_quantity'] <= p['min_stock_level'],
            'created_at': p['created_at'], 'updated_at': p['updated_at'],
        }}), 201

    except ValidationError as e:
        return jsonify({'error': 'validation_error',
                        'message': 'Invalid input data',
                        'details': e.messages}), 400
    except ValueError as e:
        msg = str(e)
        if 'barcode' in msg.lower():
            return jsonify({'error': 'barcode_exists', 'message': msg}), 409
        if 'category' in msg.lower():
            return jsonify({'error': 'category_not_found', 'message': msg}), 404
        return jsonify({'error': 'create_product_failed', 'message': msg}), 400
    except Exception as e:
        logger.error(f"Create product error: {e}", exc_info=True)
        return jsonify({'error': 'create_product_failed', 'message': str(e)}), 500


# ============================================
# OWNER UPDATE — validates category FK
# ============================================

@products_bp.route('/<int:product_id>', methods=['PUT'])
@jwt_required()
@role_required(['owner'])
@validate_input(ProductUpdateSchema)
def update_product(product_id):
    try:
        data = request.validated_data
        user_id = get_jwt_identity()

        with transaction() as db:
            cursor = db.cursor()

            cursor.execute("SELECT id FROM products WHERE id = ?", (product_id,))
            if not cursor.fetchone():
                raise ValueError("Product not found")

            # ── FK validation for category_id ──
            if data.get('category_id') is not None:
                cursor.execute("SELECT id FROM categories WHERE id = ?",
                               (data['category_id'],))
                if not cursor.fetchone():
                    raise ValueError("Category not found")

            if data.get('barcode'):
                cursor.execute(
                    "SELECT id FROM products WHERE barcode = ? AND id != ?",
                    (data['barcode'], product_id))
                if cursor.fetchone():
                    raise ValueError("Barcode already exists")

            allowed = [
                'name', 'description', 'barcode', 'category_id',
                'purchase_price', 'selling_price', 'min_stock_level',
                'unit', 'tax_rate', 'is_active', 'stock_type', 'product_image',
            ]

            updates = []
            params = []
            for field in allowed:
                if field in data and data[field] is not None:
                    updates.append(f"{field} = ?")
                    params.append(data[field])

            if not updates:
                raise ValueError("No fields to update")

            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(product_id)

            cursor.execute(
                f"UPDATE products SET {', '.join(updates)} WHERE id = ?", params)

        _record_audit(
            action='PRODUCT_UPDATE',
            category='product',
            user_id=user_id,
            details=f"Updated product id={product_id}",
            target_type='product',
            target_id=product_id,
            result='success',
            metadata={'fields': list(data.keys())},
            ip_address=request.remote_addr,
        )

        logger.info(f"Product updated: {product_id} by user {user_id}")

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT p.id, p.name, p.description, p.barcode,
                      p.category_id, c.name as category_name,
                      p.purchase_price, p.selling_price,
                      p.stock_quantity, p.min_stock_level,
                      p.unit, p.tax_rate, p.is_active,
                      p.stock_type, p.product_image,
                      p.created_at, p.updated_at
               FROM products p
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE p.id = ?""",
            (product_id,))
        p = dict(cursor.fetchone())

        return jsonify({'success': True, 'message': 'Product updated successfully',
                        'data': {
            'id': p['id'], 'name': p['name'], 'description': p['description'],
            'barcode': p['barcode'], 'category_id': p['category_id'],
            'category_name': p['category_name'],
            'purchase_price': float(p['purchase_price'] or 0),
            'selling_price': float(p['selling_price'] or 0),
            'stock_quantity': p['stock_quantity'],
            'min_stock_level': p['min_stock_level'], 'unit': p['unit'],
            'tax_rate': float(p['tax_rate'] or 0),
            'is_active': bool(p['is_active']),
            'stock_type': p['stock_type'] or 'regular',
            'product_image': p['product_image'],
            'is_low_stock': p['stock_quantity'] <= p['min_stock_level'],
            'created_at': p['created_at'], 'updated_at': p['updated_at'],
        }}), 200

    except ValidationError as e:
        return jsonify({'error': 'validation_error',
                        'message': 'Invalid input data',
                        'details': e.messages}), 400
    except ValueError as e:
        msg = str(e)
        if 'not found' in msg.lower() and 'category' in msg.lower():
            return jsonify({'error': 'category_not_found', 'message': msg}), 404
        if 'not found' in msg.lower():
            return jsonify({'error': 'product_not_found', 'message': msg}), 404
        if 'barcode' in msg.lower():
            return jsonify({'error': 'barcode_exists', 'message': msg}), 409
        if 'no fields' in msg.lower():
            return jsonify({'error': 'no_updates', 'message': msg}), 400
        return jsonify({'error': 'update_product_failed', 'message': msg}), 400
    except Exception as e:
        logger.error(f"Update product error: {e}", exc_info=True)
        return jsonify({'error': 'update_product_failed', 'message': str(e)}), 500


# ============================================
# DELETE / REACTIVATE
# ============================================

@products_bp.route('/<int:product_id>', methods=['DELETE'])
@jwt_required()
@role_required(['owner'])
def delete_product(product_id):
    try:
        user_id = get_jwt_identity()
        product_name = None
        with transaction() as db:
            cursor = db.cursor()
            cursor.execute("SELECT name FROM products WHERE id = ?", (product_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Product not found")
            product_name = row['name']
            cursor.execute(
                "UPDATE products SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (product_id,))

        _record_audit(
            action='PRODUCT_DELETE',
            category='product',
            user_id=user_id,
            details=f"Soft-deleted product '{product_name}' (id={product_id})",
            target_type='product',
            target_id=product_id,
            result='success',
            ip_address=request.remote_addr,
        )

        logger.info(f"Product deleted (soft): {product_name} by user {user_id}")
        return jsonify({'success': True, 'message': 'Product deleted successfully'}), 200
    except ValueError as e:
        return jsonify({'error': 'product_not_found', 'message': str(e)}), 404
    except Exception as e:
        logger.error(f"Delete product error: {e}", exc_info=True)
        return jsonify({'error': 'delete_product_failed', 'message': str(e)}), 500


@products_bp.route('/<int:product_id>/reactivate', methods=['POST'])
@jwt_required()
@role_required(['owner'])
def reactivate_product(product_id):
    try:
        user_id = get_jwt_identity()
        product_name = None
        with transaction() as db:
            cursor = db.cursor()
            cursor.execute("SELECT name, is_active FROM products WHERE id = ?",
                           (product_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Product not found")
            product_name = row['name']
            cursor.execute(
                "UPDATE products SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (product_id,))

        _record_audit(
            action='PRODUCT_REACTIVATE',
            category='product',
            user_id=user_id,
            details=f"Reactivated product '{product_name}' (id={product_id})",
            target_type='product',
            target_id=product_id,
            result='success',
            ip_address=request.remote_addr,
        )

        logger.info(f"Product reactivated: {product_name} by user {user_id}")
        return jsonify({'success': True,
                        'message': f"Product '{product_name}' reactivated"}), 200
    except ValueError as e:
        return jsonify({'error': 'product_not_found', 'message': str(e)}), 404
    except Exception as e:
        logger.error(f"Reactivate product error: {e}", exc_info=True)
        return jsonify({'error': 'reactivate_failed', 'message': str(e)}), 500


# ============================================
# SEARCH / BARCODE
# ============================================

@products_bp.route('/search', methods=['GET'])
def search_products():
    try:
        query = request.args.get('q', '')
        limit = request.args.get('limit', 10, type=int)
        if not query:
            return jsonify({'error': 'missing_query',
                            'message': 'Search query is required'}), 400
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT p.id, p.name, p.description, p.barcode,
                      p.category_id, c.name as category_name,
                      p.purchase_price, p.selling_price,
                      p.stock_quantity, p.min_stock_level,
                      p.unit, p.tax_rate, p.is_active,
                      p.stock_type, p.product_image
               FROM products p
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE p.is_active = 1
                 AND (p.name LIKE ? OR p.barcode LIKE ?)
               LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit))
        rows = cursor.fetchall()
        return jsonify({'success': True, 'data': [
            {'id': r['id'], 'name': r['name'], 'description': r['description'],
             'barcode': r['barcode'], 'category_id': r['category_id'],
             'category_name': r['category_name'],
             'purchase_price': float(r['purchase_price'] or 0),
             'selling_price': float(r['selling_price'] or 0),
             'stock_quantity': r['stock_quantity'],
             'min_stock_level': r['min_stock_level'], 'unit': r['unit'],
             'tax_rate': float(r['tax_rate'] or 0),
             'is_active': bool(r['is_active']),
             'stock_type': r['stock_type'] or 'regular',
             'product_image': r['product_image'],
             'is_low_stock': r['stock_quantity'] <= r['min_stock_level']}
            for r in rows
        ]}), 200
    except Exception as e:
        logger.error(f"Search products error: {e}", exc_info=True)
        return jsonify({'error': 'search_failed', 'message': str(e)}), 500


@products_bp.route('/barcode/<barcode>', methods=['GET'])
def get_product_by_barcode(barcode):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT p.id, p.name, p.description, p.barcode,
                      p.category_id, c.name as category_name,
                      p.purchase_price, p.selling_price,
                      p.stock_quantity, p.min_stock_level,
                      p.unit, p.tax_rate, p.is_active,
                      p.stock_type, p.product_image
               FROM products p
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE p.barcode = ? AND p.is_active = 1""",
            (barcode,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'product_not_found',
                            'message': 'Product not found'}), 404
        r = dict(row)
        return jsonify({'success': True, 'data': {
            'id': r['id'], 'name': r['name'], 'description': r['description'],
            'barcode': r['barcode'], 'category_id': r['category_id'],
            'category_name': r['category_name'],
            'purchase_price': float(r['purchase_price'] or 0),
            'selling_price': float(r['selling_price'] or 0),
            'stock_quantity': r['stock_quantity'],
            'min_stock_level': r['min_stock_level'], 'unit': r['unit'],
            'tax_rate': float(r['tax_rate'] or 0),
            'is_active': bool(r['is_active']),
            'stock_type': r['stock_type'] or 'regular',
            'product_image': r['product_image'],
            'is_low_stock': r['stock_quantity'] <= r['min_stock_level'],
        }}), 200
    except Exception as e:
        logger.error(f"Get by barcode error: {e}", exc_info=True)
        return jsonify({'error': 'get_product_failed', 'message': str(e)}), 500


# ============================================
# BARCODE GENERATION — EAN-13 with check digit
# ============================================

@products_bp.route('/<int:product_id>/generate-barcode', methods=['POST'])
@jwt_required()
@role_required(['owner'])
def generate_barcode(product_id):
    """
    Generate a unique 13-digit EAN-13 barcode for a product.
    """
    try:
        product_name = None
        barcode = None
        MAX_ATTEMPTS = 10

        for attempt in range(MAX_ATTEMPTS):
            try:
                with transaction() as db:
                    cursor = db.cursor()
                    cursor.execute(
                        "SELECT id, name, barcode FROM products WHERE id = ? AND is_active = 1",
                        (product_id,))
                    row = cursor.fetchone()
                    if not row:
                        raise ValueError("Product not found")
                    product_name = row['name']

                    candidate = None
                    for _ in range(50):
                        body = [random.randint(0, 9) for _ in range(12)]
                        if body[0] == 0:
                            body[0] = 1

                        odd_sum = sum(body[i] for i in range(0, 12, 2))
                        even_sum = sum(body[i] for i in range(1, 12, 2))
                        check = (10 - ((odd_sum + even_sum * 3) % 10)) % 10

                        digits = ''.join(str(d) for d in body) + str(check)

                        cursor.execute(
                            "SELECT id FROM products WHERE barcode = ?",
                            (digits,))
                        if not cursor.fetchone():
                            candidate = digits
                            break

                    if candidate is None:
                        raise RuntimeError("Could not generate unique barcode")

                    cursor.execute(
                        "UPDATE products SET barcode = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (candidate, product_id))
                    barcode = candidate
                break
            except sqlite3.IntegrityError:
                if attempt == MAX_ATTEMPTS - 1:
                    raise
                logger.warning(f"Barcode collision on attempt {attempt + 1}, retrying")
                continue

        _record_audit(
            action='PRODUCT_BARCODE_GENERATE',
            category='product',
            user_id=get_jwt_identity(),
            details=f"Generated barcode {barcode} for '{product_name}'",
            target_type='product',
            target_id=product_id,
            result='success',
            metadata={'barcode': barcode},
            ip_address=request.remote_addr,
        )

        logger.info(f"Barcode generated for product {product_name}: {barcode}")
        return jsonify({'success': True, 'message': 'Barcode generated successfully',
                        'data': {'product_id': product_id,
                                 'product_name': product_name,
                                 'barcode': barcode}}), 200
    except ValueError as e:
        return jsonify({'error': 'product_not_found', 'message': str(e)}), 404
    except Exception as e:
        logger.error(f"Generate barcode error: {e}", exc_info=True)
        return jsonify({'error': 'generate_barcode_failed', 'message': str(e)}), 500


# ============================================
# CATEGORIES
# ============================================

@products_bp.route('/categories', methods=['GET'])
def list_categories():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT c.id, c.name, c.description,
                      c.created_at, c.updated_at,
                      (SELECT COUNT(*) FROM products
                       WHERE category_id = c.id AND is_active = 1) as product_count
               FROM categories c
               ORDER BY c.name ASC""")
        rows = cursor.fetchall()
        return jsonify({'success': True, 'data': [
            {'id': r['id'], 'name': r['name'], 'description': r['description'],
             'product_count': r['product_count'],
             'created_at': r['created_at'], 'updated_at': r['updated_at']}
            for r in rows
        ]}), 200
    except Exception as e:
        logger.error(f"List categories error: {e}", exc_info=True)
        return jsonify({'error': 'list_categories_failed', 'message': str(e)}), 500


@products_bp.route('/categories', methods=['POST'])
@jwt_required()
@role_required(['owner'])
@validate_input(CategoryCreateSchema)
def create_category():
    try:
        data = request.validated_data
        user_id = get_jwt_identity()
        category_id = None
        with transaction() as db:
            cursor = db.cursor()
            cursor.execute("SELECT id FROM categories WHERE name = ?",
                           (data['name'],))
            if cursor.fetchone():
                raise ValueError(f"Category '{data['name']}' already exists")
            cursor.execute(
                "INSERT INTO categories (name, description) VALUES (?, ?)",
                (data['name'], data.get('description')))
            category_id = cursor.lastrowid

        _record_audit(
            action='CATEGORY_CREATE',
            category='product',
            user_id=user_id,
            details=f"Created category '{data['name']}' (id={category_id})",
            target_type='category',
            target_id=category_id,
            result='success',
            metadata={'name': data['name']},
            ip_address=request.remote_addr,
        )

        return jsonify({'success': True, 'message': 'Category created successfully',
                        'data': {'id': category_id, 'name': data['name'],
                                 'description': data.get('description')}}), 201
    except ValueError as e:
        return jsonify({'error': 'category_exists', 'message': str(e)}), 409
    except Exception as e:
        logger.error(f"Create category error: {e}", exc_info=True)
        return jsonify({'error': 'create_category_failed', 'message': str(e)}), 500


@products_bp.route('/categories/<int:category_id>', methods=['DELETE'])
@jwt_required()
@role_required(['owner'])
def delete_category(category_id):
    try:
        user_id = get_jwt_identity()
        category_name = None
        with transaction() as db:
            cursor = db.cursor()
            cursor.execute("SELECT name FROM categories WHERE id = ?",
                           (category_id,))
            category = cursor.fetchone()
            if not category:
                raise ValueError("Category not found")
            category_name = category['name']
            cursor.execute("SELECT COUNT(*) FROM products WHERE category_id = ?",
                           (category_id,))
            count = cursor.fetchone()[0]
            if count > 0:
                raise ValueError(f"Cannot delete category - it has {count} products")
            cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))

        _record_audit(
            action='CATEGORY_DELETE',
            category='product',
            user_id=user_id,
            details=f"Deleted category '{category_name}' (id={category_id})",
            target_type='category',
            target_id=category_id,
            result='success',
            metadata={'name': category_name},
            ip_address=request.remote_addr,
        )

        return jsonify({'success': True,
                        'message': 'Category deleted successfully'}), 200
    except ValueError as e:
        msg = str(e)
        if 'not found' in msg.lower():
            return jsonify({'error': 'category_not_found', 'message': msg}), 404
        if 'cannot delete' in msg.lower():
            return jsonify({'error': 'category_in_use', 'message': msg}), 409
        return jsonify({'error': 'delete_category_failed', 'message': msg}), 400
    except Exception as e:
        logger.error(f"Delete category error: {e}", exc_info=True)
        return jsonify({'error': 'delete_category_failed', 'message': str(e)}), 500


# ============================================
# STOCK TYPES
# ============================================

@products_bp.route('/stock-types', methods=['GET'])
def get_stock_types():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, name, icon, color, description FROM stock_types ORDER BY id")
        rows = cursor.fetchall()
        return jsonify({'success': True, 'data': [
            {'id': r['id'], 'name': r['name'], 'icon': r['icon'],
             'color': r['color'], 'description': r['description']}
            for r in rows
        ]}), 200
    except Exception as e:
        logger.error(f"Get stock types error: {e}", exc_info=True)
        return jsonify({'error': 'get_stock_types_failed', 'message': str(e)}), 500


@products_bp.route('/stock-types', methods=['POST'])
@jwt_required()
@role_required(['owner'])
def create_stock_type():
    try:
        data = request.get_json() or {}
        user_id = get_jwt_identity()
        name = data.get('name')
        if not name:
            return jsonify({'error': 'missing_name',
                            'message': 'Name is required'}), 400
        name = name.lower().replace(' ', '_')
        stock_type_id = None
        with transaction() as db:
            cursor = db.cursor()
            cursor.execute("SELECT id FROM stock_types WHERE name = ?", (name,))
            if cursor.fetchone():
                raise ValueError("Stock type already exists")
            cursor.execute(
                "INSERT INTO stock_types (name, icon, color, description) VALUES (?, ?, ?, ?)",
                (name, data.get('icon'), data.get('color'), data.get('description')))
            stock_type_id = cursor.lastrowid

        _record_audit(
            action='STOCK_TYPE_CREATE',
            category='product',
            user_id=user_id,
            details=f"Created stock type '{name}' (id={stock_type_id})",
            target_type='stock_type',
            target_id=stock_type_id,
            result='success',
            metadata={'name': name},
            ip_address=request.remote_addr,
        )

        return jsonify({'success': True, 'message': 'Stock type created successfully',
                        'data': {'id': stock_type_id, 'name': name,
                                 'icon': data.get('icon'), 'color': data.get('color'),
                                 'description': data.get('description')}}), 201
    except ValueError as e:
        return jsonify({'error': 'exists', 'message': str(e)}), 409
    except Exception as e:
        logger.error(f"Create stock type error: {e}", exc_info=True)
        return jsonify({'error': 'create_stock_type_failed', 'message': str(e)}), 500


@products_bp.route('/stock-types/<int:stock_type_id>', methods=['DELETE'])
@jwt_required()
@role_required(['owner'])
def delete_stock_type(stock_type_id):
    try:
        user_id = get_jwt_identity()
        stock_type_name = None
        with transaction() as db:
            cursor = db.cursor()
            cursor.execute("SELECT name FROM stock_types WHERE id = ?",
                           (stock_type_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Stock type not found")
            stock_type_name = row['name']
            cursor.execute("SELECT COUNT(*) FROM products WHERE stock_type = ?",
                           (stock_type_name,))
            count = cursor.fetchone()[0]
            if count > 0:
                raise ValueError(f"Cannot delete stock type - used by {count} products")
            cursor.execute("DELETE FROM stock_types WHERE id = ?", (stock_type_id,))

        _record_audit(
            action='STOCK_TYPE_DELETE',
            category='product',
            user_id=user_id,
            details=f"Deleted stock type '{stock_type_name}' (id={stock_type_id})",
            target_type='stock_type',
            target_id=stock_type_id,
            result='success',
            metadata={'name': stock_type_name},
            ip_address=request.remote_addr,
        )

        return jsonify({'success': True,
                        'message': 'Stock type deleted successfully'}), 200
    except ValueError as e:
        msg = str(e)
        if 'not found' in msg.lower():
            return jsonify({'error': 'stock_type_not_found', 'message': msg}), 404
        if 'cannot delete' in msg.lower():
            return jsonify({'error': 'stock_type_in_use', 'message': msg}), 409
        return jsonify({'error': 'delete_stock_type_failed', 'message': msg}), 400
    except Exception as e:
        logger.error(f"Delete stock type error: {e}", exc_info=True)
        return jsonify({'error': 'delete_stock_type_failed', 'message': str(e)}), 500
