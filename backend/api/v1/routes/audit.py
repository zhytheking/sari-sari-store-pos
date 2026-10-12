"""
Audit log routes.

Read-only endpoints for owners to inspect the audit trail.
Writes happen via the `audit_log` decorator in utils/decorators.py
and via direct insert calls in login/logout flows.
"""
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from database.connection import get_db
from utils.decorators import role_required
from utils.logger import get_logger

audit_bp = Blueprint('audit', __name__)
logger = get_logger(__name__)


# ════════════════════════════════════════════════════════════
# LIST LOGS
# ════════════════════════════════════════════════════════════

@audit_bp.route('/logs', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def list_logs():
    """
    List audit log entries with pagination and filters.

    Query params:
        page, per_page       pagination (default 20 per page)
        category             auth | sale | stock | product | user | settings | system
        action               e.g. LOGIN, SALE_CREATE
        user_id              filter by the acting user
        result               success | failure
        start_date           YYYY-MM-DD
        end_date             YYYY-MM-DD
        search               matches in action, details, username
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 200)
        category = request.args.get('category')
        action = request.args.get('action')
        user_id = request.args.get('user_id', type=int)
        result = request.args.get('result')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search')

        db = get_db()
        cursor = db.cursor()

        conditions = []
        params = []

        if category:
            conditions.append("a.category = ?")
            params.append(category)
        if action:
            conditions.append("a.action = ?")
            params.append(action)
        if user_id is not None:
            conditions.append("a.user_id = ?")
            params.append(user_id)
        if result:
            conditions.append("a.result = ?")
            params.append(result)
        if start_date:
            conditions.append("DATE(a.timestamp) >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(a.timestamp) <= ?")
            params.append(end_date)
        if search:
            conditions.append(
                "(a.action LIKE ? OR a.details LIKE ? OR u.username LIKE ?)"
            )
            s = f"%{search}%"
            params.extend([s, s, s])

        where_clause = (
            "WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""
            SELECT a.id, a.user_id, u.username, u.full_name, u.role,
                   a.action, a.category, a.details,
                   a.target_type, a.target_id, a.result, a.metadata,
                   a.ip_address, a.timestamp
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            {where_clause}
            ORDER BY a.timestamp DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, params + [per_page, (page - 1) * per_page])
        rows = cursor.fetchall()

        count_query = f"""
            SELECT COUNT(*) FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            {where_clause}
        """
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        items = []
        for r in rows:
            items.append({
                'id': r['id'],
                'user_id': r['user_id'],
                'username': r['username'] or 'System',
                'full_name': r['full_name'] or '—',
                'role': r['role'] or 'system',
                'action': r['action'],
                'category': r['category'] or 'system',
                'details': r['details'],
                'target_type': r['target_type'],
                'target_id': r['target_id'],
                'result': r['result'] or 'success',
                'metadata': r['metadata'],
                'ip_address': r['ip_address'],
                'timestamp': r['timestamp'],
            })

        return jsonify({
            'success': True,
            'data': {
                'items': items,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'pages': (total + per_page - 1) // per_page,
                }
            }
        }), 200

    except Exception as e:
        logger.error(f"List audit logs error: {e}", exc_info=True)
        return jsonify({
            'error': 'list_logs_failed',
            'message': str(e),
        }), 500


# ════════════════════════════════════════════════════════════
# SINGLE LOG ENTRY
# ════════════════════════════════════════════════════════════

@audit_bp.route('/logs/<int:log_id>', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_log(log_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT a.id, a.user_id, u.username, u.full_name, u.role,
                   a.action, a.category, a.details,
                   a.target_type, a.target_id, a.result, a.metadata,
                   a.ip_address, a.timestamp
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            WHERE a.id = ?
            """,
            (log_id,)
        )
        r = cursor.fetchone()
        if not r:
            return jsonify({
                'error': 'log_not_found',
                'message': 'Audit log entry not found',
            }), 404

        return jsonify({
            'success': True,
            'data': {
                'id': r['id'],
                'user_id': r['user_id'],
                'username': r['username'] or 'System',
                'full_name': r['full_name'] or '—',
                'role': r['role'] or 'system',
                'action': r['action'],
                'category': r['category'] or 'system',
                'details': r['details'],
                'target_type': r['target_type'],
                'target_id': r['target_id'],
                'result': r['result'] or 'success',
                'metadata': r['metadata'],
                'ip_address': r['ip_address'],
                'timestamp': r['timestamp'],
            }
        }), 200

    except Exception as e:
        logger.error(f"Get audit log error: {e}", exc_info=True)
        return jsonify({
            'error': 'get_log_failed',
            'message': str(e),
        }), 500


# ════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════

@audit_bp.route('/summary', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_summary():
    """Return counts by category for the last 24h, 7d, 30d."""
    try:
        db = get_db()
        cursor = db.cursor()

        now = datetime.now()
        day_ago = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        month_ago = (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

        def _count_since(since_str):
            cursor.execute(
                """SELECT category, COUNT(*) as n
                   FROM audit_logs
                   WHERE timestamp >= ?
                   GROUP BY category""",
                (since_str,)
            )
            return {r['category'] or 'system': r['n'] for r in cursor.fetchall()}

        day = _count_since(day_ago)
        week = _count_since(week_ago)
        month = _count_since(month_ago)

        # Totals
        cursor.execute("SELECT COUNT(*) FROM audit_logs")
        grand_total = cursor.fetchone()[0]

        # Recent failure count (last 24h)
        cursor.execute(
            """SELECT COUNT(*) FROM audit_logs
               WHERE timestamp >= ? AND result = 'failure'""",
            (day_ago,)
        )
        failures_24h = cursor.fetchone()[0]

        return jsonify({
            'success': True,
            'data': {
                'grand_total': grand_total,
                'failures_last_24h': failures_24h,
                'last_24h': day,
                'last_7d': week,
                'last_30d': month,
            }
        }), 200

    except Exception as e:
        logger.error(f"Audit summary error: {e}", exc_info=True)
        return jsonify({
            'error': 'summary_failed',
            'message': str(e),
        }), 500


# ════════════════════════════════════════════════════════════
# HELPER — record a log entry manually
# ════════════════════════════════════════════════════════════
#
# Not a route. Used by other modules (e.g. auth.login) when the
# decorator is not applicable.

def record_audit(
    action: str,
    category: str = 'system',
    user_id=None,
    details: str = None,
    target_type: str = None,
    target_id: int = None,
    result: str = 'success',
    metadata: dict = None,
    ip_address: str = None,
):
    """
    Insert an audit log row directly.

    This never raises. If the insert fails, it logs a warning and
    continues. The caller is not interrupted.
    """
    import json

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO audit_logs
                (user_id, action, category, details,
                 target_type, target_id, result, metadata, ip_address,
                 timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                user_id,
                action,
                category,
                details,
                target_type,
                target_id,
                result,
                json.dumps(metadata) if metadata else None,
                ip_address,
            )
        )
        db.commit()
    except Exception as e:
        logger.warning(f"record_audit failed: {e}")


# Alias for older code paths
record = record_audit  