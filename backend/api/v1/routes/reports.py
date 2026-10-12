import csv
import io
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, send_file, Response
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.connection import get_db
from utils.decorators import role_required, audit_log
from utils.logger import get_logger

reports_bp = Blueprint('reports', __name__)
logger = get_logger(__name__)


# ═════════════
# SALES REPORT
# ═════════════

@reports_bp.route('/sales', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_sales_report():
    #Generate sales report with optional user filter
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        group_by = request.args.get('group_by', 'day')
        format_type = request.args.get('format', 'json')
        user_id = request.args.get('user_id', type=int)

        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')

        db = get_db()
        cursor = db.cursor()

        group_clause = {
            'day': "DATE(created_at)",
            'week': "strftime('%Y-%W', created_at)",
            'month': "strftime('%Y-%m', created_at)",
            'year': "strftime('%Y', created_at)"
        }.get(group_by, "DATE(created_at)")

        user_clause = ""
        user_params = []
        if user_id is not None:
            user_clause = " AND user_id = ?"
            user_params = [user_id]

        #Period breakdown
        cursor.execute(
            f"""SELECT {group_clause} as period, COUNT(*) as sales_count,
                      SUM(final_amount) as revenue,
                      SUM(discount_amount) as discounts,
                      SUM(tax_amount) as taxes,
                      COUNT(DISTINCT user_id) as cashiers
               FROM sales
               WHERE DATE(created_at) BETWEEN ? AND ?
                     AND status = 'completed'{user_clause}
               GROUP BY period
               ORDER BY period ASC""",
            [start_date, end_date] + user_params
        )
        period_data = cursor.fetchall()

        #Totals
        cursor.execute(
            f"""SELECT COUNT(*) as total_sales,
                      SUM(final_amount) as total_revenue,
                      SUM(discount_amount) as total_discounts,
                      SUM(tax_amount) as total_taxes,
                      AVG(final_amount) as average_sale
               FROM sales
               WHERE DATE(created_at) BETWEEN ? AND ?
                     AND status = 'completed'{user_clause}""",
            [start_date, end_date] + user_params
        )
        totals = cursor.fetchone()

        #Top products
        top_user_clause = ""
        if user_id is not None:
            top_user_clause = " AND s.user_id = ?"
        cursor.execute(
            f"""SELECT p.name, SUM(si.quantity) as quantity_sold,
                      SUM(si.subtotal) as revenue
               FROM sale_items si
               JOIN products p ON si.product_id = p.id
               JOIN sales s ON si.sale_id = s.id
               WHERE DATE(s.created_at) BETWEEN ? AND ?
                     AND s.status = 'completed'{top_user_clause}
               GROUP BY p.id, p.name
               ORDER BY revenue DESC
               LIMIT 5""",
            [start_date, end_date] + user_params
        )
        top_products = cursor.fetchall()

        #Payment method breakdown
        cursor.execute(
            f"""SELECT payment_method, COUNT(*) as count,
                      SUM(final_amount) as total
               FROM sales
               WHERE DATE(created_at) BETWEEN ? AND ?
                     AND status = 'completed'{user_clause}
               GROUP BY payment_method""",
            [start_date, end_date] + user_params
        )
        payment_methods = cursor.fetchall()

        #Resolve user label
        user_label = "All Users"
        if user_id is not None:
            cursor.execute(
                "SELECT username, full_name FROM users WHERE id = ?",
                (user_id,)
            )
            urow = cursor.fetchone()
            if urow:
                user_label = f"{urow[1]} ({urow[0]})"
            else:
                user_label = f"User ID {user_id}"

        report_data = {
            'summary': {
                'start_date': start_date,
                'end_date': end_date,
                'user_filter': user_label,
                'user_id': user_id,
                'total_sales': totals[0] or 0,
                'total_revenue': float(totals[1]) if totals[1] else 0,
                'total_discounts': float(totals[2]) if totals[2] else 0,
                'total_taxes': float(totals[3]) if totals[3] else 0,
                'average_sale': float(totals[4]) if totals[4] else 0
            },
            'period_data': [
                {
                    'period': p[0],
                    'sales_count': p[1],
                    'revenue': float(p[2]) if p[2] else 0,
                    'discounts': float(p[3]) if p[3] else 0,
                    'taxes': float(p[4]) if p[4] else 0,
                    'cashiers': p[5]
                } for p in period_data
            ],
            'daily_data': [
                {
                    'date': p[0],
                    'sales_count': p[1],
                    'revenue': float(p[2]) if p[2] else 0,
                    'discounts': float(p[3]) if p[3] else 0,
                    'taxes': float(p[4]) if p[4] else 0,
                    'cashiers': p[5]
                } for p in period_data
            ],
            'top_products': [
                {
                    'name': p[0],
                    'quantity_sold': p[1],
                    'revenue': float(p[2]) if p[2] else 0
                } for p in top_products
            ],
            'payment_methods': [
                {
                    'method': p[0],
                    'count': p[1],
                    'total': float(p[2]) if p[2] else 0
                } for p in payment_methods
            ]
        }

        if format_type == 'csv':
            return export_report_csv(report_data)

        return jsonify({'success': True, 'data': report_data}), 200

    except Exception as e:
        logger.error(f"Sales report error: {e}", exc_info=True)
        return jsonify({'error': 'report_failed', 'message': str(e)}), 500


def export_report_csv(report_data):
    #Export report data as CSV
    try:
        output = io.StringIO()
        writer = csv.writer(output)

        summary = report_data.get('summary', {})

        writer.writerow(['SALES REPORT'])
        writer.writerow(['Start Date:', summary.get('start_date', '')])
        writer.writerow(['End Date:', summary.get('end_date', '')])
        writer.writerow(['User Filter:', summary.get('user_filter', 'All Users')])
        writer.writerow(['Total Sales:', summary.get('total_sales', 0)])
        writer.writerow(['Total Revenue:', summary.get('total_revenue', 0)])
        writer.writerow(['Total Discounts:', summary.get('total_discounts', 0)])
        writer.writerow(['Total Taxes:', summary.get('total_taxes', 0)])
        writer.writerow(['Average Sale:', summary.get('average_sale', 0)])
        writer.writerow([])

        writer.writerow(['Period Data'])
        writer.writerow(['Period', 'Sales Count', 'Revenue',
                         'Discounts', 'Taxes', 'Cashiers'])
        for row in report_data.get('period_data', []):
            writer.writerow([
                row.get('period'),
                row.get('sales_count'),
                row.get('revenue'),
                row.get('discounts'),
                row.get('taxes'),
                row.get('cashiers')
            ])
        writer.writerow([])

        writer.writerow(['Top Products'])
        writer.writerow(['Product Name', 'Quantity Sold', 'Revenue'])
        for row in report_data.get('top_products', []):
            writer.writerow([
                row.get('name'),
                row.get('quantity_sold'),
                row.get('revenue')
            ])
        writer.writerow([])

        writer.writerow(['Payment Methods'])
        writer.writerow(['Method', 'Count', 'Total'])
        for row in report_data.get('payment_methods', []):
            writer.writerow([
                row.get('method'),
                row.get('count'),
                row.get('total')
            ])

        output.seek(0)

        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=(
                f'sales_report_{datetime.now().strftime("%Y%m%d")}.csv'
            )
        )
    except Exception as e:
        logger.error(f"CSV export error: {e}", exc_info=True)
        return jsonify({'error': 'export_failed', 'message': str(e)}), 500


# ═══════════════════════════
# PRODUCT PERFORMANCE REPORT
# ═══════════════════════════

@reports_bp.route('/products', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_product_report():
    #Generate product performance report
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        top_n = request.args.get('top_n', 10, type=int)
        user_id = request.args.get('user_id', type=int)

        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')

        db = get_db()
        cursor = db.cursor()

        user_clause = ""
        user_params = []
        if user_id is not None:
            user_clause = " AND s.user_id = ?"
            user_params = [user_id]

        cursor.execute(
            f"""SELECT p.id, p.name, p.category_id, c.name as category_name,
                      SUM(si.quantity) as total_quantity,
                      SUM(si.subtotal) as total_revenue,
                      AVG(si.selling_price) as avg_price,
                      COUNT(DISTINCT si.sale_id) as times_sold
               FROM sale_items si
               JOIN products p ON si.product_id = p.id
               LEFT JOIN categories c ON p.category_id = c.id
               JOIN sales s ON si.sale_id = s.id
               WHERE DATE(s.created_at) BETWEEN ? AND ?
                     AND s.status = 'completed'{user_clause}
               GROUP BY p.id, p.name, p.category_id, c.name
               ORDER BY total_revenue DESC
               LIMIT ?""",
            [start_date, end_date] + user_params + [top_n]
        )
        products = cursor.fetchall()

        cursor.execute(
            f"""SELECT c.name, COUNT(DISTINCT si.product_id) as products_sold,
                      SUM(si.quantity) as total_quantity,
                      SUM(si.subtotal) as total_revenue
               FROM sale_items si
               JOIN products p ON si.product_id = p.id
               LEFT JOIN categories c ON p.category_id = c.id
               JOIN sales s ON si.sale_id = s.id
               WHERE DATE(s.created_at) BETWEEN ? AND ?
                     AND s.status = 'completed'{user_clause}
               GROUP BY c.name
               ORDER BY total_revenue DESC""",
            [start_date, end_date] + user_params
        )
        categories = cursor.fetchall()

        cursor.execute(
            f"""SELECT COUNT(DISTINCT p.id)
               FROM sale_items si
               JOIN products p ON si.product_id = p.id
               JOIN sales s ON si.sale_id = s.id
               WHERE DATE(s.created_at) BETWEEN ? AND ?
                     AND s.status = 'completed'{user_clause}""",
            [start_date, end_date] + user_params
        )
        total_products = cursor.fetchone()[0]

        return jsonify({
            'success': True,
            'data': {
                'start_date': start_date,
                'end_date': end_date,
                'total_products_sold': total_products,
                'top_products': [
                    {
                        'id': p[0],
                        'name': p[1],
                        'category_id': p[2],
                        'category_name': p[3],
                        'quantity_sold': p[4],
                        'revenue': float(p[5]) if p[5] else 0,
                        'average_price': float(p[6]) if p[6] else 0,
                        'times_sold': p[7]
                    } for p in products
                ],
                'category_performance': [
                    {
                        'category': c[0] or 'Uncategorized',
                        'products_sold': c[1],
                        'total_quantity': c[2],
                        'total_revenue': float(c[3]) if c[3] else 0
                    } for c in categories
                ]
            }
        }), 200

    except Exception as e:
        logger.error(f"Product report error: {e}", exc_info=True)
        return jsonify({'error': 'report_failed', 'message': str(e)}), 500


# ══════════════════
# INVENTORY REPORT
# ══════════════════

@reports_bp.route('/inventory', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_inventory_report():
    #Generate inventory report
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            """SELECT p.id, p.name, p.stock_quantity, p.min_stock_level,
                      p.unit, p.purchase_price, p.selling_price,
                      c.name as category_name,
                      CASE WHEN p.stock_quantity <= p.min_stock_level
                                AND p.stock_quantity > 0
                           THEN 'Low Stock'
                           WHEN p.stock_quantity = 0
                           THEN 'Out of Stock'
                           ELSE 'In Stock' END as status,
                      p.stock_type
               FROM products p
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE p.is_active = 1
               ORDER BY p.stock_quantity ASC"""
        )
        products = cursor.fetchall()

        cursor.execute(
            """SELECT c.name,
                      SUM(p.stock_quantity * p.purchase_price) as total_value,
                      COUNT(p.id) as product_count
               FROM products p
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE p.is_active = 1
               GROUP BY c.name
               ORDER BY total_value DESC"""
        )
        category_values = cursor.fetchall()

        cursor.execute(
            """SELECT stock_type, COUNT(*) as count,
                      SUM(stock_quantity) as total_stock
               FROM products
               WHERE is_active = 1
               GROUP BY stock_type"""
        )
        stock_types = cursor.fetchall()

        return jsonify({
            'success': True,
            'data': {
                'items': [
                    {
                        'id': p[0],
                        'name': p[1],
                        'stock_quantity': p[2],
                        'min_stock_level': p[3],
                        'unit': p[4],
                        'purchase_price': float(p[5]) if p[5] else 0,
                        'selling_price': float(p[6]) if p[6] else 0,
                        'category': p[7],
                        'status': p[8],
                        'stock_type': p[9] or 'regular'
                    } for p in products
                ],
                'summary': {
                    'total_products': len(products),
                    'low_stock_count': sum(
                        1 for p in products if p[8] == 'Low Stock'),
                    'out_of_stock_count': sum(
                        1 for p in products if p[8] == 'Out of Stock'),
                    'total_inventory_value': sum(
                        (p[5] or 0) * (p[2] or 0) for p in products)
                },
                'category_breakdown': [
                    {
                        'category': c[0] or 'Uncategorized',
                        'total_value': float(c[1]) if c[1] else 0,
                        'product_count': c[2]
                    } for c in category_values
                ],
                'stock_type_breakdown': [
                    {
                        'stock_type': st[0] or 'regular',
                        'count': st[1],
                        'total_stock': st[2]
                    } for st in stock_types
                ]
            }
        }), 200

    except Exception as e:
        logger.error(f"Inventory report error: {e}", exc_info=True)
        return jsonify({'error': 'report_failed', 'message': str(e)}), 500


# ═══════════════
# DAILY SUMMARY
# ═══════════════

@reports_bp.route('/daily', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_daily_summary():
    #Get daily sales summary.
    try:
        date = request.args.get('date')
        user_id = request.args.get('user_id', type=int)
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')

        db = get_db()
        cursor = db.cursor()

        user_clause = ""
        user_params = []
        if user_id is not None:
            user_clause = " AND user_id = ?"
            user_params = [user_id]

        cursor.execute(
            f"""SELECT COUNT(*) as total_sales,
                      SUM(final_amount) as revenue,
                      SUM(discount_amount) as discounts,
                      SUM(tax_amount) as taxes,
                      AVG(final_amount) as average_sale
               FROM sales
               WHERE DATE(created_at) = ?
                     AND status = 'completed'{user_clause}""",
            [date] + user_params
        )
        summary = cursor.fetchone()

        cursor.execute(
            f"""SELECT strftime('%H', created_at) as hour,
                      COUNT(*) as sales_count,
                      SUM(final_amount) as revenue
               FROM sales
               WHERE DATE(created_at) = ?
                     AND status = 'completed'{user_clause}
               GROUP BY hour
               ORDER BY hour ASC""",
            [date] + user_params
        )
        hourly = cursor.fetchall()

        top_user_clause = ""
        if user_id is not None:
            top_user_clause = " AND s.user_id = ?"
        cursor.execute(
            f"""SELECT p.name, SUM(si.quantity) as quantity,
                      SUM(si.subtotal) as revenue
               FROM sale_items si
               JOIN products p ON si.product_id = p.id
               JOIN sales s ON si.sale_id = s.id
               WHERE DATE(s.created_at) = ?
                     AND s.status = 'completed'{top_user_clause}
               GROUP BY p.id, p.name
               ORDER BY revenue DESC
               LIMIT 5""",
            [date] + user_params
        )
        top_products = cursor.fetchall()

        cursor.execute(
            f"""SELECT payment_method, COUNT(*) as count,
                      SUM(final_amount) as total
               FROM sales
               WHERE DATE(created_at) = ?
                     AND status = 'completed'{user_clause}
               GROUP BY payment_method""",
            [date] + user_params
        )
        payment_methods = cursor.fetchall()

        cursor.execute(
            f"""SELECT u.full_name, COUNT(*) as sales_count,
                      SUM(s.final_amount) as total_revenue
               FROM sales s
               JOIN users u ON s.user_id = u.id
               WHERE DATE(s.created_at) = ?
                     AND s.status = 'completed'{user_clause}
               GROUP BY u.id, u.full_name
               ORDER BY total_revenue DESC""",
            [date] + user_params
        )
        cashiers = cursor.fetchall()

        return jsonify({
            'success': True,
            'data': {
                'date': date,
                'total_sales': summary[0] or 0,
                'total_revenue': float(summary[1]) if summary[1] else 0,
                'total_discounts': float(summary[2]) if summary[2] else 0,
                'total_taxes': float(summary[3]) if summary[3] else 0,
                'average_sale': float(summary[4]) if summary[4] else 0,
                'hourly_breakdown': [
                    {
                        'hour': h[0],
                        'sales_count': h[1],
                        'revenue': float(h[2]) if h[2] else 0
                    } for h in hourly
                ],
                'top_products': [
                    {
                        'name': p[0],
                        'quantity': p[1],
                        'revenue': float(p[2]) if p[2] else 0
                    } for p in top_products
                ],
                'payment_methods': [
                    {
                        'method': p[0],
                        'count': p[1],
                        'total': float(p[2]) if p[2] else 0
                    } for p in payment_methods
                ],
                'cashier_performance': [
                    {
                        'cashier': c[0],
                        'sales_count': c[1],
                        'total_revenue': float(c[2]) if c[2] else 0
                    } for c in cashiers
                ]
            }
        }), 200

    except Exception as e:
        logger.error(f"Daily summary error: {e}", exc_info=True)
        return jsonify({'error': 'get_daily_summary_failed',
                        'message': str(e)}), 500


# ══════════════════════
# PROFIT / LOSS REPORT
# ══════════════════════

@reports_bp.route('/profit', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_profit_report():
    #Generate profit/loss report
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        user_id = request.args.get('user_id', type=int)

        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')

        db = get_db()
        cursor = db.cursor()

        user_clause = ""
        user_params = []
        if user_id is not None:
            user_clause = " AND user_id = ?"
            user_params = [user_id]

        cursor.execute(
            f"""SELECT COUNT(*), SUM(final_amount),
                      SUM(discount_amount), SUM(tax_amount)
               FROM sales
               WHERE DATE(created_at) BETWEEN ? AND ?
                     AND status = 'completed'{user_clause}""",
            [start_date, end_date] + user_params
        )
        row = cursor.fetchone()

        total_revenue = float(row[1]) if row[1] else 0
        total_discount = float(row[2]) if row[2] else 0
        total_tax = float(row[3]) if row[3] else 0

        cost_user_clause = ""
        if user_id is not None:
            cost_user_clause = " AND s.user_id = ?"
        cursor.execute(
            f"""SELECT SUM(si.quantity * p.purchase_price)
               FROM sale_items si
               JOIN products p ON si.product_id = p.id
               JOIN sales s ON si.sale_id = s.id
               WHERE DATE(s.created_at) BETWEEN ? AND ?
                     AND s.status = 'completed'{cost_user_clause}""",
            [start_date, end_date] + user_params
        )
        cost_row = cursor.fetchone()
        total_cost = float(cost_row[0]) if cost_row[0] else 0

        gross_profit = total_revenue - total_cost
        net_profit = gross_profit - total_discount - total_tax
        profit_margin = (
            (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
        )
        net_margin = (
            (net_profit / total_revenue * 100) if total_revenue > 0 else 0
        )

        return jsonify({
            'success': True,
            'data': {
                'start_date': start_date,
                'end_date': end_date,
                'summary': {
                    'total_sales': row[0] or 0,
                    'total_revenue': total_revenue,
                    'total_discount': total_discount,
                    'total_tax': total_tax,
                    'total_cost': total_cost,
                    'gross_profit': gross_profit,
                    'net_profit': net_profit,
                    'profit_margin': profit_margin,
                    'net_margin': net_margin
                }
            }
        }), 200

    except Exception as e:
        logger.error(f"Profit report error: {e}", exc_info=True)
        return jsonify({'error': 'report_failed', 'message': str(e)}), 500


# ═════════════════════
# ANALYTICS DASHBOARD
# ═════════════════════

@reports_bp.route('/analytics', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_analytics():
    #Get business analytics dashboard data
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
            """SELECT COUNT(*), SUM(final_amount),
                      SUM(discount_amount)
               FROM sales
               WHERE created_at >= ? AND status = 'completed'""",
            (today_start,)
        )
        today = cursor.fetchone()

        cursor.execute(
            """SELECT COUNT(*), SUM(final_amount),
                      SUM(discount_amount)
               FROM sales
               WHERE DATE(created_at) >= ? AND status = 'completed'""",
            (week_start,)
        )
        week = cursor.fetchone()

        cursor.execute(
            """SELECT COUNT(*), SUM(final_amount),
                      SUM(discount_amount)
               FROM sales
               WHERE DATE(created_at) >= ? AND status = 'completed'""",
            (month_start,)
        )
        month = cursor.fetchone()

        cursor.execute(
            """SELECT COUNT(*) FROM products
               WHERE is_active = 1
                     AND stock_quantity <= min_stock_level"""
        )
        low_stock = cursor.fetchone()[0]

        cursor.execute(
            """SELECT COUNT(*) FROM products
               WHERE is_active = 1 AND stock_quantity = 0"""
        )
        out_of_stock = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM products WHERE is_active = 1"
        )
        total_products = cursor.fetchone()[0]

        cursor.execute(
            """SELECT s.invoice_number, s.customer_name,
                      s.final_amount, s.created_at,
                      u.full_name as cashier
               FROM sales s
               JOIN users u ON s.user_id = u.id
               WHERE s.status = 'completed'
               ORDER BY s.created_at DESC
               LIMIT 5"""
        )
        recent_sales = cursor.fetchall()

        cursor.execute(
            """SELECT COUNT(*), SUM(final_amount)
               FROM sales
               WHERE DATE(created_at) BETWEEN
                     DATE('now', '-60 days') AND DATE('now', '-30 days')
                     AND status = 'completed'"""
        )
        previous_month = cursor.fetchone()

        return jsonify({
            'success': True,
            'data': {
                'today': {
                    'sales_count': today[0] or 0,
                    'revenue': float(today[1]) if today[1] else 0,
                    'discount': float(today[2]) if today[2] else 0
                },
                'week': {
                    'sales_count': week[0] or 0,
                    'revenue': float(week[1]) if week[1] else 0,
                    'discount': float(week[2]) if week[2] else 0
                },
                'month': {
                    'sales_count': month[0] or 0,
                    'revenue': float(month[1]) if month[1] else 0,
                    'discount': float(month[2]) if month[2] else 0
                },
                'inventory': {
                    'total_products': total_products,
                    'low_stock_products': low_stock,
                    'out_of_stock_products': out_of_stock
                },
                'growth': {
                    'sales_growth': (
                        ((month[0] or 0) - (previous_month[0] or 0))
                        / (previous_month[0] or 1) * 100
                    ),
                    'revenue_growth': (
                        ((month[1] or 0) - (previous_month[1] or 0))
                        / (previous_month[1] or 1) * 100
                    )
                },
                'recent_sales': [
                    {
                        'invoice': rs[0],
                        'customer': rs[1] or 'Walk-in',
                        'amount': float(rs[2]) if rs[2] else 0,
                        'date': rs[3],
                        'cashier': rs[4]
                    } for rs in recent_sales
                ]
            }
        }), 200

    except Exception as e:
        logger.error(f"Analytics error: {e}", exc_info=True)
        return jsonify({'error': 'get_analytics_failed',
                        'message': str(e)}), 500


# ═══════════════════════════════
# CSV EXPORT — ALL SALES (owner)
# ═══════════════════════════════

@reports_bp.route('/export/all-sales', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def export_all_sales_csv():
    #Export all sales as CSV. Query params mirror /sales/all-sales
    try:
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

        cursor.execute(
            f"""
            SELECT s.id, s.invoice_number, s.created_at,
                   s.customer_name, s.user_id, u.username,
                   u.full_name AS cashier_name,
                   COALESCE(SUM(si.quantity), 0) AS total_items,
                   s.payment_method, s.payment_reference,
                   s.total_amount, s.discount_amount,
                   s.tax_amount, s.final_amount
            FROM sales s
            JOIN users u ON s.user_id = u.id
            LEFT JOIN sale_items si ON si.sale_id = s.id
            {where_clause}
            GROUP BY s.id
            ORDER BY s.created_at DESC
            """,
            params
        )
        rows = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            'Invoice', 'Date', 'Cashier', 'Customer',
            'Items', 'Payment Method', 'GCash Ref',
            'Subtotal', 'Discount', 'Tax', 'Total'
        ])

        grand_total = 0.0
        for r in rows:
            final_amount = float(r['final_amount'] or 0)
            grand_total += final_amount

            writer.writerow([
                r['invoice_number'] or '',
                r['created_at'] or '',
                r['cashier_name'] or r['username'] or '',
                r['customer_name'] or 'Walk-in',
                int(r['total_items'] or 0),
                (r['payment_method'] or '').upper(),
                r['payment_reference'] or '',
                f"{float(r['total_amount'] or 0):.2f}",
                f"{float(r['discount_amount'] or 0):.2f}",
                f"{float(r['tax_amount'] or 0):.2f}",
                f"{final_amount:.2f}",
            ])

        writer.writerow([])
        writer.writerow(['TOTAL', '', '', '', '', '', '', '', '', '',
                         f"{grand_total:.2f}"])

        csv_data = output.getvalue()
        output.close()

        start_label = start_date or 'all'
        end_label = end_date or 'all'
        filename = f"all_sales_{start_label}_to_{end_label}.csv"

        return Response(
            csv_data,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Cache-Control': 'no-store',
            }
        )
    except Exception as e:
        logger.error(f"Export all sales CSV error: {e}", exc_info=True)
        return jsonify({'error': 'export_failed', 'message': str(e)}), 500


# ════════════════════════════════
# CSV EXPORT — MY SALES (cashier)
# ════════════════════════════════

@reports_bp.route('/export/my-sales', methods=['GET'])
@jwt_required()
def export_my_sales_csv():
    #Export the current user's sales as CSV
    try:
        user_id = get_jwt_identity()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        payment_method = request.args.get('payment_method')

        db = get_db()
        cursor = db.cursor()

        conditions = ["s.status = 'completed'", "s.user_id = ?"]
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

        cursor.execute(
            f"""
            SELECT s.id, s.invoice_number, s.created_at,
                   s.customer_name,
                   COALESCE(SUM(si.quantity), 0) AS total_items,
                   s.payment_method, s.payment_reference,
                   s.total_amount, s.discount_amount,
                   s.tax_amount, s.final_amount
            FROM sales s
            LEFT JOIN sale_items si ON si.sale_id = s.id
            {where_clause}
            GROUP BY s.id
            ORDER BY s.created_at DESC
            """,
            params
        )
        rows = cursor.fetchall()

        cursor.execute(
            "SELECT username, full_name FROM users WHERE id = ?",
            (user_id,)
        )
        urow = cursor.fetchone()
        cashier_label = ''
        if urow:
            cashier_label = urow['full_name'] or urow['username'] or ''

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([f"Cashier: {cashier_label}"])
        writer.writerow([])
        writer.writerow([
            'Invoice', 'Date', 'Customer', 'Items',
            'Payment Method', 'GCash Ref',
            'Subtotal', 'Discount', 'Tax', 'Total'
        ])

        grand_total = 0.0
        for r in rows:
            final_amount = float(r['final_amount'] or 0)
            grand_total += final_amount

            writer.writerow([
                r['invoice_number'] or '',
                r['created_at'] or '',
                r['customer_name'] or 'Walk-in',
                int(r['total_items'] or 0),
                (r['payment_method'] or '').upper(),
                r['payment_reference'] or '',
                f"{float(r['total_amount'] or 0):.2f}",
                f"{float(r['discount_amount'] or 0):.2f}",
                f"{float(r['tax_amount'] or 0):.2f}",
                f"{final_amount:.2f}",
            ])

        writer.writerow([])
        writer.writerow(['TOTAL', '', '', '', '', '', '', '', '',
                         f"{grand_total:.2f}"])

        csv_data = output.getvalue()
        output.close()

        start_label = start_date or 'all'
        end_label = end_date or 'all'
        filename = f"my_sales_{start_label}_to_{end_label}.csv"

        return Response(
            csv_data,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Cache-Control': 'no-store',
            }
        )
    except Exception as e:
        logger.error(f"Export my sales CSV error: {e}", exc_info=True)
        return jsonify({'error': 'export_failed', 'message': str(e)}), 500
