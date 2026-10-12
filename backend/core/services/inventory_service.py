from typing import Optional, Tuple, List, Dict

from backend.database.connection import get_db, transaction


class InventoryService:
    #Inventory management service

    def adjust_stock(
        self,
        product_id: int,
        quantity: int,
        adjustment_type: str,
        reason: str,
        note: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict:
        """
        Adjust product stock.
        adjustment_type:
          - 'add'      : increment stock by `quantity`
          - 'subtract' : decrement stock by `quantity`
          - 'set'      : set stock to `quantity` (absolute)
        """
        if adjustment_type not in ('add', 'subtract', 'set'):
            raise ValueError(f"Invalid adjustment type: {adjustment_type}")

        if adjustment_type == 'set' and quantity < 0:
            raise ValueError("Stock quantity cannot be negative")

        if adjustment_type in ('add', 'subtract') and quantity <= 0:
            raise ValueError("Quantity must be greater than 0")

        product_name = None
        old_quantity = None
        new_quantity = None

        with transaction() as db:
            cursor = db.cursor()

            cursor.execute(
                "SELECT id, name, stock_quantity FROM products WHERE id = ?",
                (product_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Product with ID {product_id} not found")

            product_name = row['name']
            old_quantity = row['stock_quantity']

            if adjustment_type == 'add':
                new_quantity = old_quantity + quantity
            elif adjustment_type == 'subtract':
                if old_quantity < quantity:
                    raise ValueError(
                        f"Insufficient stock. Available: {old_quantity}, "
                        f"requested: {quantity}"
                    )
                new_quantity = old_quantity - quantity
            else:
                new_quantity = quantity

            cursor.execute(
                """UPDATE products
                   SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (new_quantity, product_id),
            )

            cursor.execute(
                """INSERT INTO inventory_adjustments
                   (product_id, user_id, old_quantity, new_quantity,
                    adjustment_type, reason, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    product_id,
                    user_id,
                    old_quantity,
                    new_quantity,
                    adjustment_type,
                    reason,
                    note,
                ),
            )

        return {
            'product_id': product_id,
            'product_name': product_name,
            'old_quantity': old_quantity,
            'new_quantity': new_quantity,
            'change': new_quantity - old_quantity,
            'adjustment_type': adjustment_type,
            'current_stock': new_quantity,
        }

    def transfer_stock(
        self,
        from_product_id: int,
        to_product_id: int,
        quantity: int,
        reason: str,
        note: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict:
        #Transfer stock between products atomically
        if quantity <= 0:
            raise ValueError("Transfer quantity must be greater than 0")

        if from_product_id == to_product_id:
            raise ValueError("Source and target products must be different")

        from_name = None
        to_name = None
        from_new_stock = None
        to_new_stock = None

        with transaction() as db:
            cursor = db.cursor()

            cursor.execute(
                "SELECT id, name, stock_quantity, is_active "
                "FROM products WHERE id = ?",
                (from_product_id,),
            )
            from_row = cursor.fetchone()
            if not from_row:
                raise ValueError(
                    f"Source product with ID {from_product_id} not found"
                )
            if not from_row['is_active']:
                raise ValueError(
                    f"Source product '{from_row['name']}' is inactive"
                )

            cursor.execute(
                "SELECT id, name, stock_quantity, is_active "
                "FROM products WHERE id = ?",
                (to_product_id,),
            )
            to_row = cursor.fetchone()
            if not to_row:
                raise ValueError(
                    f"Target product with ID {to_product_id} not found"
                )
            if not to_row['is_active']:
                raise ValueError(
                    f"Target product '{to_row['name']}' is inactive"
                )

            from_name = from_row['name']
            to_name = to_row['name']

            if from_row['stock_quantity'] < quantity:
                raise ValueError(
                    f"Insufficient stock in {from_name}. "
                    f"Available: {from_row['stock_quantity']}"
                )

            from_new_stock = from_row['stock_quantity'] - quantity
            to_new_stock = to_row['stock_quantity'] + quantity

            cursor.execute(
                """UPDATE products
                   SET stock_quantity = stock_quantity - ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (quantity, from_product_id),
            )
            cursor.execute(
                """UPDATE products
                   SET stock_quantity = stock_quantity + ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (quantity, to_product_id),
            )

            cursor.execute(
                """INSERT INTO stock_transfers
                   (from_product_id, to_product_id, user_id, quantity,
                    reason, note)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (from_product_id, to_product_id, user_id, quantity,
                 reason, note),
            )

        return {
            'from_product': from_name,
            'to_product': to_name,
            'quantity': quantity,
            'from_product_stock': from_new_stock,
            'to_product_stock': to_new_stock,
        }

    def get_adjustment_history(
        self,
        product_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[Dict], int]:
        #Get inventory adjustment history
        db = get_db()
        cursor = db.cursor()

        conditions = []
        params: List = []

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
                           ia.adjustment_type, ia.reason, ia.note,
                           ia.created_at
                    FROM inventory_adjustments ia
                    JOIN products p ON ia.product_id = p.id
                    JOIN users u ON ia.user_id = u.id
                    {where_clause}
                    ORDER BY ia.created_at DESC
                    LIMIT ? OFFSET ?"""

        query_params = params + [per_page, (page - 1) * per_page]
        cursor.execute(query, query_params)
        rows = cursor.fetchall()

        adjustments = [
            {
                'id': row['id'],
                'product_id': row['product_id'],
                'product_name': row['product_name'],
                'user_id': row['user_id'],
                'username': row['username'],
                'old_quantity': row['old_quantity'],
                'new_quantity': row['new_quantity'],
                'change': row['new_quantity'] - row['old_quantity'],
                'adjustment_type': row['adjustment_type'],
                'reason': row['reason'],
                'note': row['note'],
                'created_at': row['created_at'],
            }
            for row in rows
        ]

        count_query = (
            f"SELECT COUNT(*) FROM inventory_adjustments ia {where_clause}"
        )
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        return adjustments, total

    def get_product_stock_info(self, product_id: int) -> Dict:
        #Get stock information for a product
        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            """SELECT id, name, stock_quantity, min_stock_level,
                      purchase_price
               FROM products WHERE id = ? AND is_active = 1""",
            (product_id,),
        )
        product = cursor.fetchone()
        if not product:
            raise ValueError(f"Product with ID {product_id} not found")

        cursor.execute(
            """SELECT id, old_quantity, new_quantity, adjustment_type,
                      reason, created_at
               FROM inventory_adjustments
               WHERE product_id = ?
               ORDER BY created_at DESC
               LIMIT 10""",
            (product_id,),
        )
        rows = cursor.fetchall()

        adjustments = [
            {
                'id': row['id'],
                'old_quantity': row['old_quantity'],
                'new_quantity': row['new_quantity'],
                'change': row['new_quantity'] - row['old_quantity'],
                'adjustment_type': row['adjustment_type'],
                'reason': row['reason'],
                'created_at': row['created_at'],
            }
            for row in rows
        ]

        stock = product['stock_quantity']
        min_stock = product['min_stock_level']
        purchase = float(product['purchase_price'] or 0)

        return {
            'product_id': product['id'],
            'product_name': product['name'],
            'current_stock': stock,
            'min_stock_level': min_stock,
            'is_low_stock': stock <= min_stock,
            'total_value': stock * purchase,
            'recent_adjustments': adjustments,
        }

    def get_inventory_summary(self) -> Dict:
        #Get inventory summary report
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
            "SELECT SUM(stock_quantity * purchase_price) "
            "FROM products WHERE is_active = 1"
        )
        total_value = cursor.fetchone()[0] or 0

        cursor.execute(
            """SELECT c.name, COUNT(p.id) as product_count,
                      SUM(p.stock_quantity * p.purchase_price) as total_value
               FROM categories c
               LEFT JOIN products p
                 ON c.id = p.category_id AND p.is_active = 1
               GROUP BY c.id
               HAVING product_count > 0"""
        )
        rows = cursor.fetchall()

        categories = [
            {
                'category': row['name'],
                'product_count': row['product_count'],
                'total_value': float(row['total_value']) if row['total_value'] else 0,
            }
            for row in rows
        ]

        return {
            'total_products': total_products,
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'total_inventory_value': float(total_value) if total_value else 0,
            'categories': categories,
        }
