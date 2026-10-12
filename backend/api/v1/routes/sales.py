"""
Sales and POS routes.

Notable change:
    create_sale now records a row in `inventory_adjustments` for
    each product sold. This makes the stock history complete.

Audit:
    Every sale and void writes to audit_logs.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from marshmallow import ValidationError
from datetime import datetime, timedelta

from database.connection import get_db, transaction
from api.v1.schemas.sale import SaleCreateSchema
from utils.validators import validate_input
from utils.decorators import role_required, audit_log
from utils.helpers import generate_invoice_number
from utils.logger import get_logger

sales_bp = Blueprint('sales', __name__)
logger = get_logger(__name__)

DEFAULT_CUSTOMER = None


def _record_audit(**kwargs):
    try:
        from backend.api.v1.routes.audit import record_audit
        record_audit(**kwargs)
    except Exception as e:
        logger.warning(f"Audit write failed: {e}")


# ============================================
# CREATE SALE
# ============================================

@sales_bp.route('', methods=['POST'])
@sales_bp.route('/', methods=['POST'])
@jwt_required()
@validate_input(SaleCreateSchema)
def create_sale():
    try:
        data = request.validated_data
        user_id = get_jwt_identity()
        invoice_number = generate_invoice_number()
        total_amount = 0
        discount = float(data.get('discount', 0))
        validated_items = []

        with transaction() as db:
            cursor = db.cursor()

            for item in data['items']:
                cursor.execute(
                    """SELECT id, name, selling_price, stock_quantity
                       FROM products WHERE id = ? AND is_active = 1""",
                    (item['product_id'],))
                product = cursor.fetchone()
                if not product:
                    raise ValueError(
                        f"Product with ID {item['product_id']} not found")

                if product['stock_quantity'] < item['quantity']:
                    raise ValueError(
                        f"Insufficient stock for {product['name']}. "
                        f"Available: {product['stock_quantity']}")

                server_price = float(product['selling_price'])
                line_total = item['quantity'] * server_price
                total_amount += line_total

                validated_items.append({
                    'product_id': product['id'],
                    'product_name': product['name'],
                    'quantity': item['quantity'],
                    'selling_price': server_price,
                    'subtotal': line_total,
                    'old_stock': product['stock_quantity'],
                    'new_stock': product['stock_quantity'] - item['quantity'],
                })

            final_amount = total_amount - discount
            if final_amount < 0:
                raise ValueError("Discount cannot exceed total")
            if float(data['payment_amount']) < final_amount:
                raise ValueError(
                    f"Insufficient payment. Amount due: "
                    f"₱{final_amount:.2f}")
            change = float(data['payment_amount']) - final_amount

            cursor.execute(
                """INSERT INTO sales
                   (invoice_number, customer_name, user_id, total_amount,
                    discount_amount, tax_amount, final_amount,
                    payment_method, payment_amount, change_amount,
                    payment_reference, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (invoice_number, data.get('customer_name'), user_id,
                 total_amount, discount, 0, final_amount,
                 data['payment_method'], float(data['payment_amount']),
                 change, data.get('payment_reference'),
                 data.get('notes')))
            sale_id = cursor.lastrowid

            for item in validated_items:
                cursor.execute(
                    """INSERT INTO sale_items
                       (sale_id, product_id, quantity, selling_price,
                        subtotal)
                       VALUES (?, ?, ?, ?, ?)""",
                    (sale_id, item['product_id'], item['quantity'],
                     item['selling_price'], item['subtotal']))

                cursor.execute(
                    """UPDATE products
                       SET stock_quantity = ?,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (item['new_stock'], item['product_id']))

                cursor.execute(
                    """INSERT INTO inventory_adjustments
                       (product_id, user_id, old_quantity, new_quantity,
                        adjustment_type, reason, note)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (item['product_id'], user_id,
                     item['old_stock'], item['new_stock'],
                     'subtract',
                     f'Sale {invoice_number}',
                     f'Qty sold: {item["quantity"]}'))

        _record_audit(
            action='SALE_CREATE',
            category='sale',
            user_id=user_id,
            details=f"Sale {invoice_number} — ₱{final_amount:.2f} ({data['payment_method']})",
            target_type='sale',
            target_id=sale_id,
            result='success',
            metadata={
                'invoice_number': invoice_number,
                'final_amount': final_amount,
                'payment_method': data['payment_method'],
                'item_count': len(validated_items),
            },
            ip_address=request.remote_addr,
        )

        logger.info(f"Sale {invoice_number} completed by user {user_id}")

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT s.id, s.invoice_number, s.customer_name, s.user_id,
                      u.username, s.total_amount, s.discount_amount,
                      s.tax_amount, s.final_amount, s.payment_method,
                      s.payment_amount, s.change_amount,
                      s.payment_reference, s.status, s.notes, s.created_at
               FROM sales s JOIN users u ON s.user_id = u.id
               WHERE s.id = ?""", (sale_id,))
        sale = dict(cursor.fetchone())

        cursor.execute(
            """SELECT si.id, si.product_id, p.name, si.quantity,
                      si.selling_price, si.subtotal
               FROM sale_items si JOIN products p ON si.product_id = p.id
               WHERE si.sale_id = ?""", (sale_id,))
        items = [dict(r) for r in cursor.fetchall()]

        receipt_data = {
            'invoice_number': sale['invoice_number'],
            'date': sale['created_at'],
            'customer': sale['customer_name'] or DEFAULT_CUSTOMER,
            'items': [
                {'name': i['name'], 'quantity': i['quantity'],
                 'price': float(i['selling_price']),
                 'subtotal': float(i['subtotal'])}
                for i in items],
            'subtotal': float(sale['total_amount']),
            'discount': float(sale['discount_amount']),
            'tax': float(sale['tax_amount'] or 0),
            'total': float(sale['final_amount']),
            'payment_method': sale['payment_method'],
            'payment_amount': float(sale['payment_amount']),
            'change': float(sale['change_amount']),
            'payment_reference': sale['payment_reference'],
            'cashier': sale['username'],
        }

        return jsonify({
            'success': True,
            'message': 'Sale completed successfully',
            'data': {
                'sale': {
                    'id': sale['id'],
                    'invoice_number': sale['invoice_number'],
                    'customer_name': sale['customer_name'],
                    'user_id': sale['user_id'],
                    'username': sale['username'],
                    'total_amount': float(sale['total_amount']),
                    'discount_amount': float(sale['discount_amount']),
                    'tax_amount': float(sale['tax_amount'] or 0),
                    'final_amount': float(sale['final_amount']),
                    'payment_method': sale['payment_method'],
                    'payment_amount': float(sale['payment_amount']),
                    'change_amount': float(sale['change_amount']),
                    'payment_reference': sale['payment_reference'],
                    'status': sale['status'],
                    'notes': sale['notes'],
                    'created_at': sale['created_at'],
                    'items': [
                        {'id': i['id'], 'product_id': i['product_id'],
                         'product_name': i['name'],
                         'quantity': i['quantity'],
                         'selling_price': float(i['selling_price']),
                         'subtotal': float(i['subtotal'])}
                        for i in items],
                },
                'receipt': receipt_data,
            }
        }), 201

    except ValueError as e:
        logger.warning(f"Sale rejected: {e}")
        return jsonify({'error': 'sale_error', 'message': str(e)}), 400
    except ValidationError as e:
        return jsonify({'error': 'validation_error',
                        'message': 'Invalid input data',
                        'details': e.messages}), 400
    except Exception as e:
        logger.error(f"Sale failed: {e}", exc_info=True)
        return jsonify({'error': 'sale_failed', 'message': str(e)}), 500


# ============================================
# LIST SALES
# ============================================

@sales_bp.route('', methods=['GET'])
@sales_bp.route('/', methods=['GET'])
@jwt_required()
def list_sales():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        user_id = request.args.get('user_id', type=int)
        payment_method = request.args.get('payment_method')
        include_items = (
            request.args.get('include_items', '').lower() == 'true')

        db = get_db()
        cursor = db.cursor()

        conditions = ["s.status = 'completed'"]
        params = []

        if start_date:
            conditions.append("DATE(s.created_at) >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(s.created_at) <= ?")
            params.append(end_date)
        if user_id:
            conditions.append("s.user_id = ?")
            params.append(user_id)
        if payment_method:
            conditions.append("s.payment_method = ?")
            params.append(payment_method)

        where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT s.id, s.invoice_number, s.customer_name, s.user_id,
                   u.username, s.total_amount, s.discount_amount,
                   s.tax_amount, s.final_amount, s.payment_method,
                   s.payment_amount, s.change_amount,
                   s.payment_reference, s.status, s.notes, s.created_at,
                   COALESCE(SUM(si.quantity), 0) AS total_items
            FROM sales s
            JOIN users u ON s.user_id = u.id
            LEFT JOIN sale_items si ON si.sale_id = s.id
            {where_clause}
            GROUP BY s.id
            ORDER BY s.created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(
            query, params + [per_page, (page - 1) * per_page])
        sales = [dict(r) for r in cursor.fetchall()]

        items_by_sale = {}
        if include_items and sales:
            sale_ids = [s['id'] for s in sales]
            placeholders = ','.join('?' * len(sale_ids))
            cursor.execute(
                f"""SELECT si.sale_id, si.id, si.product_id, p.name,
                           si.quantity, si.selling_price, si.subtotal
                    FROM sale_items si
                    JOIN products p ON si.product_id = p.id
                    WHERE si.sale_id IN ({placeholders})""",
                sale_ids)
            for row in cursor.fetchall():
                items_by_sale.setdefault(row['sale_id'], []).append({
                    'id': row['id'],
                    'product_id': row['product_id'],
                    'product_name': row['name'],
                    'quantity': row['quantity'],
                    'selling_price': float(row['selling_price']),
                    'subtotal': float(row['subtotal']),
                })

        count_query = f"SELECT COUNT(*) FROM sales s {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(MAX(id), 0) FROM sales")
        latest_sale_id = cursor.fetchone()[0]

        result_items = []
        for s in sales:
            entry = {
                'id': s['id'],
                'invoice_number': s['invoice_number'],
                'customer_name': s['customer_name'],
                'user_id': s['user_id'],
                'username': s['username'],
                'total_amount': float(s['total_amount']),
                'discount_amount': float(s['discount_amount']),
                'tax_amount': float(s['tax_amount'] or 0),
                'final_amount': float(s['final_amount']),
                'payment_method': s['payment_method'],
                'payment_amount': float(s['payment_amount']),
                'change_amount': float(s['change_amount']),
                'payment_reference': s['payment_reference'],
                'status': s['status'],
                'notes': s['notes'],
                'created_at': s['created_at'],
                'total_items': s['total_items'],
            }
            if include_items:
                entry['items'] = items_by_sale.get(s['id'], [])
            result_items.append(entry)

        return jsonify({
            'success': True,
            'data': {
                'items': result_items,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'pages': (total + per_page - 1) // per_page,
                },
                'latest_sale_id': latest_sale_id,
            }
        }), 200
    except Exception as e:
        logger.error(f"List sales error: {e}", exc_info=True)
        return jsonify({'error': 'list_sales_failed',
                        'message': str(e)}), 500


# ============================================
# MY SALES
# ============================================

@sales_bp.route('/my-sales', methods=['GET'])
@jwt_required()
def get_my_sales():
    try:
        user_id = get_jwt_identity()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        payment_method = request.args.get('payment_method')

        db = get_db()
        cursor = db.cursor()
        conditions = ["s.user_id = ?", "s.status = 'completed'"]
        params = [user_id]

        if start_date:
            conditions.append("DATE(s.created_at) >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(s.created_at) <= ?")
            params.append(end_date)
        if payment_method:
            conditions.append("s.payment_method = ?")
            params.append(payment_method)

        where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT s.id, s.invoice_number, s.customer_name, s.user_id,
                   u.username, s.total_amount, s.discount_amount,
                   s.tax_amount, s.final_amount, s.payment_method,
                   s.payment_amount, s.change_amount,
                   s.payment_reference, s.status, s.notes, s.created_at,
                   COALESCE(SUM(si.quantity), 0) AS total_items
            FROM sales s
            JOIN users u ON s.user_id = u.id
            LEFT JOIN sale_items si ON si.sale_id = s.id
            {where_clause}
            GROUP BY s.id
            ORDER BY s.created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(
            query, params + [per_page, (page - 1) * per_page])
        sales = [dict(r) for r in cursor.fetchall()]

        count_query = f"SELECT COUNT(*) FROM sales s {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        summary_conditions = ["user_id = ?", "status = 'completed'"]
        summary_params = [user_id]
        if start_date:
            summary_conditions.append("DATE(created_at) >= ?")
            summary_params.append(start_date)
        if end_date:
            summary_conditions.append("DATE(created_at) <= ?")
            summary_params.append(end_date)
        summary_where = "WHERE " + " AND ".join(summary_conditions)

        cursor.execute(
            f"""SELECT COUNT(*) AS total_transactions,
                       COALESCE(SUM(final_amount), 0) AS total_revenue,
                       COALESCE(SUM(discount_amount), 0) AS total_discounts,
                       COALESCE(AVG(final_amount), 0) AS average_sale
                FROM sales {summary_where}""", summary_params)
        summary = dict(cursor.fetchone())

        cursor.execute(
            """SELECT COUNT(*) AS count,
                      COALESCE(SUM(final_amount), 0) AS revenue
               FROM sales WHERE user_id = ? AND status = 'completed'
                 AND DATE(created_at) = DATE('now')""", (user_id,))
        today = dict(cursor.fetchone())

        cursor.execute(
            """SELECT COUNT(*) AS count,
                      COALESCE(SUM(final_amount), 0) AS revenue
               FROM sales WHERE user_id = ? AND status = 'completed'
                 AND created_at >= DATE('now', '-7 days')""", (user_id,))
        week = dict(cursor.fetchone())

        cursor.execute(
            """SELECT COALESCE(MAX(id), 0) FROM sales
               WHERE user_id = ? AND status = 'completed'""", (user_id,))
        latest_sale_id = cursor.fetchone()[0]

        return jsonify({
            'success': True,
            'data': {
                'items': [
                    {'id': s['id'],
                     'invoice_number': s['invoice_number'],
                     'customer_name': s['customer_name'],
                     'user_id': s['user_id'],
                     'username': s['username'],
                     'total_amount': float(s['total_amount']),
                     'discount_amount': float(s['discount_amount']),
                     'tax_amount': float(s['tax_amount'] or 0),
                     'final_amount': float(s['final_amount']),
                     'payment_method': s['payment_method'],
                     'payment_amount': float(s['payment_amount']),
                     'change_amount': float(s['change_amount']),
                     'payment_reference': s['payment_reference'],
                     'status': s['status'],
                     'notes': s['notes'],
                     'created_at': s['created_at'],
                     'total_items': s['total_items']}
                    for s in sales],
                'pagination': {
                    'page': page, 'per_page': per_page,
                    'total': total,
                    'pages': (total + per_page - 1) // per_page},
                'summary': {
                    'total_transactions': summary['total_transactions'],
                    'total_revenue': float(summary['total_revenue']),
                    'total_discounts': float(summary['total_discounts']),
                    'average_sale': float(summary['average_sale']),
                },
                'today': {
                    'count': today['count'],
                    'revenue': float(today['revenue'])},
                'week': {
                    'count': week['count'],
                    'revenue': float(week['revenue'])},
                'latest_sale_id': latest_sale_id,
            }
        }), 200
    except Exception as e:
        logger.error(f"Get my sales error: {e}", exc_info=True)
        return jsonify({'error': 'get_my_sales_failed',
                        'message': str(e)}), 500


# ============================================
# ALL SALES (OWNER)
# ============================================

@sales_bp.route('/all-sales', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_all_sales():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        payment_method = request.args.get('payment_method')
        cashier_id = request.args.get('cashier_id', type=int)

        db = get_db()
        cursor = db.cursor()
        conditions = ["s.status = 'completed'"]
        params = []

        if start_date:
            conditions.append("DATE(s.created_at) >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(s.created_at) <= ?")
            params.append(end_date)
        if payment_method:
            conditions.append("s.payment_method = ?")
            params.append(payment_method)
        if cashier_id:
            conditions.append("s.user_id = ?")
            params.append(cashier_id)

        where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT s.id, s.invoice_number, s.customer_name, s.user_id,
                   u.username, u.full_name AS cashier_name,
                   s.total_amount, s.discount_amount, s.tax_amount,
                   s.final_amount, s.payment_method, s.payment_amount,
                   s.change_amount, s.payment_reference,
                   s.status, s.notes, s.created_at,
                   COALESCE(SUM(si.quantity), 0) AS total_items
            FROM sales s
            JOIN users u ON s.user_id = u.id
            LEFT JOIN sale_items si ON si.sale_id = s.id
            {where_clause}
            GROUP BY s.id
            ORDER BY s.created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(
            query, params + [per_page, (page - 1) * per_page])
        sales = [dict(r) for r in cursor.fetchall()]

        count_query = f"SELECT COUNT(*) FROM sales s {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        summary_conditions = ["status = 'completed'"]
        summary_params = []
        if start_date:
            summary_conditions.append("DATE(created_at) >= ?")
            summary_params.append(start_date)
        if end_date:
            summary_conditions.append("DATE(created_at) <= ?")
            summary_params.append(end_date)
        if payment_method:
            summary_conditions.append("payment_method = ?")
            summary_params.append(payment_method)
        if cashier_id:
            summary_conditions.append("user_id = ?")
            summary_params.append(cashier_id)
        summary_where = "WHERE " + " AND ".join(summary_conditions)

        cursor.execute(
            f"""SELECT COUNT(*) AS total_transactions,
                       COALESCE(SUM(final_amount), 0) AS total_revenue,
                       COALESCE(SUM(discount_amount), 0) AS total_discounts,
                       COALESCE(AVG(final_amount), 0) AS average_sale
                FROM sales {summary_where}""", summary_params)
        summary = dict(cursor.fetchone())

        breakdown_conditions = ["s.status = 'completed'"]
        breakdown_params = []
        if start_date:
            breakdown_conditions.append("DATE(s.created_at) >= ?")
            breakdown_params.append(start_date)
        if end_date:
            breakdown_conditions.append("DATE(s.created_at) <= ?")
            breakdown_params.append(end_date)
        breakdown_where = "WHERE " + " AND ".join(breakdown_conditions)

        cursor.execute(
            f"""SELECT u.id AS user_id, u.username, u.full_name, u.role,
                       COUNT(s.id) AS sale_count,
                       COALESCE(SUM(s.final_amount), 0) AS total_revenue,
                       COALESCE(AVG(s.final_amount), 0) AS average_sale
                FROM sales s JOIN users u ON s.user_id = u.id
                {breakdown_where}
                GROUP BY u.id, u.username, u.full_name, u.role
                ORDER BY total_revenue DESC""", breakdown_params)
        cashier_breakdown = [
            {'user_id': r['user_id'], 'username': r['username'],
             'full_name': r['full_name'], 'role': r['role'],
             'sale_count': r['sale_count'],
             'total_revenue': float(r['total_revenue']),
             'average_sale': float(r['average_sale'])}
            for r in cursor.fetchall()]

        pay_conditions = ["status = 'completed'"]
        pay_params = []
        if start_date:
            pay_conditions.append("DATE(created_at) >= ?")
            pay_params.append(start_date)
        if end_date:
            pay_conditions.append("DATE(created_at) <= ?")
            pay_params.append(end_date)
        if cashier_id:
            pay_conditions.append("user_id = ?")
            pay_params.append(cashier_id)
        pay_where = "WHERE " + " AND ".join(pay_conditions)

        cursor.execute(
            f"""SELECT payment_method, COUNT(*) AS count,
                       COALESCE(SUM(final_amount), 0) AS total
                FROM sales {pay_where}
                GROUP BY payment_method""", pay_params)
        payment_breakdown = [
            {'method': r['payment_method'], 'count': r['count'],
             'total': float(r['total'])}
            for r in cursor.fetchall()]

        cursor.execute(
            """SELECT id, username, full_name, role FROM users
               WHERE role IN ('owner', 'cashier') AND is_active = 1
               ORDER BY full_name ASC""")
        cashiers = [{'id': r['id'], 'username': r['username'],
                     'full_name': r['full_name'], 'role': r['role']}
                    for r in cursor.fetchall()]

        cursor.execute("SELECT COALESCE(MAX(id), 0) FROM sales")
        latest_sale_id = cursor.fetchone()[0]

        return jsonify({
            'success': True,
            'data': {
                'items': [
                    {'id': s['id'],
                     'invoice_number': s['invoice_number'],
                     'customer_name': s['customer_name'],
                     'user_id': s['user_id'],
                     'username': s['username'],
                     'cashier_name': s['cashier_name'],
                     'total_amount': float(s['total_amount']),
                     'discount_amount': float(s['discount_amount']),
                     'tax_amount': float(s['tax_amount'] or 0),
                     'final_amount': float(s['final_amount']),
                     'payment_method': s['payment_method'],
                     'payment_amount': float(s['payment_amount']),
                     'change_amount': float(s['change_amount']),
                     'payment_reference': s['payment_reference'],
                     'status': s['status'],
                     'notes': s['notes'],
                     'created_at': s['created_at'],
                     'total_items': s['total_items']}
                    for s in sales],
                'pagination': {
                    'page': page, 'per_page': per_page,
                    'total': total,
                    'pages': (total + per_page - 1) // per_page},
                'summary': {
                    'total_transactions': summary['total_transactions'],
                    'total_revenue': float(summary['total_revenue']),
                    'total_discounts': float(summary['total_discounts']),
                    'average_sale': float(summary['average_sale']),
                },
                'cashier_breakdown': cashier_breakdown,
                'payment_breakdown': payment_breakdown,
                'cashiers': cashiers,
                'latest_sale_id': latest_sale_id,
            }
        }), 200
    except Exception as e:
        logger.error(f"Get all sales error: {e}", exc_info=True)
        return jsonify({'error': 'get_all_sales_failed',
                        'message': str(e)}), 500


# ============================================
# GET SINGLE SALE
# ============================================

@sales_bp.route('/<int:sale_id>', methods=['GET'])
@jwt_required()
def get_sale(sale_id):
    try:
        current_user_id = get_jwt_identity()
        claims = get_jwt()
        user_role = claims.get('role', 'cashier')

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT s.id, s.invoice_number, s.customer_name, s.user_id,
                      u.username, s.total_amount, s.discount_amount,
                      s.tax_amount, s.final_amount, s.payment_method,
                      s.payment_amount, s.change_amount,
                      s.payment_reference, s.status, s.notes, s.created_at
               FROM sales s JOIN users u ON s.user_id = u.id
               WHERE s.id = ?""", (sale_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'sale_not_found',
                            'message': 'Sale not found'}), 404
        sale = dict(row)

        if (user_role != 'owner'
                and str(sale['user_id']) != str(current_user_id)):
            logger.warning(
                f"User {current_user_id} ({user_role}) tried to view "
                f"sale {sale_id} owned by user {sale['user_id']}")
            return jsonify({'error': 'forbidden',
                            'message':
                            'You can only view your own sales'}), 403

        cursor.execute(
            """SELECT si.id, si.product_id, p.name, si.quantity,
                      si.selling_price, si.subtotal
               FROM sale_items si JOIN products p ON si.product_id = p.id
               WHERE si.sale_id = ?""", (sale_id,))
        items = [dict(r) for r in cursor.fetchall()]

        return jsonify({
            'success': True,
            'data': {
                'id': sale['id'],
                'invoice_number': sale['invoice_number'],
                'customer_name': sale['customer_name'],
                'user_id': sale['user_id'],
                'username': sale['username'],
                'total_amount': float(sale['total_amount']),
                'discount_amount': float(sale['discount_amount']),
                'tax_amount': float(sale['tax_amount'] or 0),
                'final_amount': float(sale['final_amount']),
                'payment_method': sale['payment_method'],
                'payment_amount': float(sale['payment_amount']),
                'change_amount': float(sale['change_amount']),
                'payment_reference': sale['payment_reference'],
                'status': sale['status'],
                'notes': sale['notes'],
                'created_at': sale['created_at'],
                'items': [
                    {'id': i['id'], 'product_id': i['product_id'],
                     'product_name': i['name'],
                     'quantity': i['quantity'],
                     'selling_price': float(i['selling_price']),
                     'subtotal': float(i['subtotal'])}
                    for i in items],
            }
        }), 200
    except Exception as e:
        logger.error(f"Get sale error: {e}", exc_info=True)
        return jsonify({'error': 'get_sale_failed',
                        'message': str(e)}), 500


# ============================================
# GET RECEIPT
# ============================================

@sales_bp.route('/<int:sale_id>/receipt', methods=['GET'])
@jwt_required()
def get_receipt(sale_id):
    try:
        current_user_id = get_jwt_identity()
        claims = get_jwt()
        user_role = claims.get('role', 'cashier')

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT s.id, s.invoice_number, s.customer_name,
                      s.created_at, s.user_id, u.full_name AS cashier,
                      s.total_amount, s.discount_amount, s.tax_amount,
                      s.final_amount, s.payment_method, s.payment_amount,
                      s.change_amount, s.payment_reference
               FROM sales s JOIN users u ON s.user_id = u.id
               WHERE s.id = ? AND s.status = 'completed'""", (sale_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'sale_not_found',
                            'message': 'Sale not found'}), 404
        sale = dict(row)

        if (user_role != 'owner'
                and str(sale['user_id']) != str(current_user_id)):
            return jsonify({'error': 'forbidden',
                            'message':
                            'You can only view your own receipts'}), 403

        cursor.execute(
            """SELECT p.name, si.quantity, si.selling_price, si.subtotal
               FROM sale_items si JOIN products p ON si.product_id = p.id
               WHERE si.sale_id = ?""", (sale_id,))
        items = [dict(r) for r in cursor.fetchall()]

        return jsonify({
            'success': True,
            'data': {
                'invoice_number': sale['invoice_number'],
                'date': sale['created_at'],
                'customer': sale['customer_name'] or DEFAULT_CUSTOMER,
                'items': [
                    {'name': i['name'], 'quantity': i['quantity'],
                     'price': float(i['selling_price']),
                     'subtotal': float(i['subtotal'])}
                    for i in items],
                'subtotal': float(sale['total_amount']),
                'discount': float(sale['discount_amount']),
                'tax': float(sale['tax_amount'] or 0),
                'total': float(sale['final_amount']),
                'payment_method': sale['payment_method'],
                'payment_amount': float(sale['payment_amount']),
                'change': float(sale['change_amount']),
                'payment_reference': sale['payment_reference'],
                'cashier': sale['cashier'],
            }
        }), 200
    except Exception as e:
        logger.error(f"Get receipt error: {e}", exc_info=True)
        return jsonify({'error': 'get_receipt_failed',
                        'message': str(e)}), 500


# ============================================
# VOID SALE
# ============================================

@sales_bp.route('/<int:sale_id>/void', methods=['POST'])
@jwt_required()
@role_required(['owner'])
def void_sale(sale_id):
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        reason = data.get('reason', 'Voided by admin')
        invoice_number = None

        with transaction() as db:
            cursor = db.cursor()
            cursor.execute(
                """SELECT id, status, invoice_number FROM sales
                   WHERE id = ? AND status = 'completed'""", (sale_id,))
            sale = cursor.fetchone()
            if not sale:
                raise ValueError("Sale not found or already voided")
            invoice_number = sale['invoice_number']

            cursor.execute(
                "SELECT product_id, quantity FROM sale_items "
                "WHERE sale_id = ?", (sale_id,))
            items_to_restore = cursor.fetchall()

            for item in items_to_restore:
                cursor.execute(
                    "SELECT stock_quantity FROM products WHERE id = ?",
                    (item['product_id'],))
                current = cursor.fetchone()
                if current:
                    old_stock = current['stock_quantity']
                    new_stock = old_stock + item['quantity']
                    cursor.execute(
                        """UPDATE products
                           SET stock_quantity = ?,
                               updated_at = CURRENT_TIMESTAMP
                           WHERE id = ?""",
                        (new_stock, item['product_id']))

                    cursor.execute(
                        """INSERT INTO inventory_adjustments
                           (product_id, user_id, old_quantity,
                            new_quantity, adjustment_type, reason, note)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (item['product_id'], user_id,
                         old_stock, new_stock,
                         'add',
                         f'Void of {invoice_number}',
                         f'Restored qty: {item["quantity"]}'))

            cursor.execute(
                """UPDATE sales SET status = 'voided', voided_by = ?,
                   voided_at = CURRENT_TIMESTAMP, void_reason = ?,
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (user_id, reason, sale_id))

        _record_audit(
            action='SALE_VOID',
            category='sale',
            user_id=user_id,
            details=f"Sale {invoice_number} voided — reason: {reason}",
            target_type='sale',
            target_id=sale_id,
            result='success',
            metadata={'reason': reason},
            ip_address=request.remote_addr,
        )

        logger.info(f"Sale {invoice_number} voided by user {user_id}")
        return jsonify({'success': True,
                        'message': 'Sale voided successfully'}), 200
    except ValueError as e:
        return jsonify({'error': 'void_error', 'message': str(e)}), 400
    except Exception as e:
        logger.error(f"Void failed: {e}", exc_info=True)
        return jsonify({'error': 'void_failed', 'message': str(e)}), 500


# ============================================
# STATS
# ============================================

@sales_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_sales_stats():
    try:
        period = request.args.get('period', 'today')
        db = get_db()
        cursor = db.cursor()

        if period == 'today':
            cursor.execute(
                """SELECT COUNT(*), COALESCE(SUM(final_amount), 0),
                          COALESCE(SUM(discount_amount), 0)
                   FROM sales WHERE DATE(created_at) = DATE('now')
                     AND status = 'completed'""")
        elif period == 'week':
            cursor.execute(
                """SELECT COUNT(*), COALESCE(SUM(final_amount), 0),
                          COALESCE(SUM(discount_amount), 0)
                   FROM sales
                   WHERE created_at >= DATE('now', '-7 days')
                     AND status = 'completed'""")
        elif period == 'month':
            cursor.execute(
                """SELECT COUNT(*), COALESCE(SUM(final_amount), 0),
                          COALESCE(SUM(discount_amount), 0)
                   FROM sales
                   WHERE created_at >= DATE('now', '-30 days')
                     AND status = 'completed'""")
        elif period == 'year':
            cursor.execute(
                """SELECT COUNT(*), COALESCE(SUM(final_amount), 0),
                          COALESCE(SUM(discount_amount), 0)
                   FROM sales
                   WHERE created_at >= DATE('now', '-365 days')
                     AND status = 'completed'""")
        else:
            return jsonify({'error': 'invalid_period',
                            'message': 'Invalid period'}), 400

        row = cursor.fetchone()
        total_sales = row[0] or 0
        total_revenue = float(row[1]) if row[1] else 0
        total_discount = float(row[2]) if row[2] else 0
        average_sale = (total_revenue / total_sales
                        if total_sales > 0 else 0)

        return jsonify({
            'success': True,
            'data': {
                'period': period,
                'total_sales': total_sales,
                'total_revenue': total_revenue,
                'total_discount': total_discount,
                'average_sale': average_sale,
            }
        }), 200
    except Exception as e:
        logger.error(f"Get stats error: {e}", exc_info=True)
        return jsonify({'error': 'get_stats_failed',
                        'message': str(e)}), 500


@sales_bp.route('/stats/detailed', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_detailed_stats():
    try:
        db = get_db()
        cursor = db.cursor()
        now = datetime.now()
        today_start = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ).strftime('%Y-%m-%d %H:%M:%S')
        week_start = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        month_start = (now - timedelta(days=30)).strftime('%Y-%m-%d')

        cursor.execute(
            """SELECT COUNT(*), COALESCE(SUM(final_amount), 0),
                      COALESCE(SUM(discount_amount), 0)
               FROM sales WHERE created_at >= ?
                 AND status = 'completed'""", (today_start,))
        today = cursor.fetchone()

        cursor.execute(
            """SELECT COUNT(*), COALESCE(SUM(final_amount), 0),
                      COALESCE(SUM(discount_amount), 0)
               FROM sales WHERE DATE(created_at) >= ?
                 AND status = 'completed'""", (week_start,))
        week = cursor.fetchone()

        cursor.execute(
            """SELECT COUNT(*), COALESCE(SUM(final_amount), 0),
                      COALESCE(SUM(discount_amount), 0)
               FROM sales WHERE DATE(created_at) >= ?
                 AND status = 'completed'""", (month_start,))
        month = cursor.fetchone()

        cursor.execute(
            """SELECT payment_method, COUNT(*),
                      COALESCE(SUM(final_amount), 0)
               FROM sales WHERE status = 'completed'
               GROUP BY payment_method""")
        payment_methods = cursor.fetchall()

        return jsonify({
            'success': True,
            'data': {
                'today': {
                    'sales_count': today[0] or 0,
                    'revenue': float(today[1]),
                    'discount': float(today[2])},
                'week': {
                    'sales_count': week[0] or 0,
                    'revenue': float(week[1]),
                    'discount': float(week[2])},
                'month': {
                    'sales_count': month[0] or 0,
                    'revenue': float(month[1]),
                    'discount': float(month[2])},
                'payment_methods': [
                    {'method': pm[0], 'count': pm[1],
                     'total': float(pm[2])}
                    for pm in payment_methods],
            }
        }), 200
    except Exception as e:
        logger.error(f"Get detailed stats error: {e}", exc_info=True)
        return jsonify({'error': 'get_detailed_stats_failed',
                        'message': str(e)}), 500
