"""
Tests that verify transaction atomicity.

These are the most important tests in the suite. If any fail,
data corruption is possible in production.

Every test here exercises one of:
  - A successful multi-step write (sale + items + stock decrement).
  - A failed multi-step write (should roll back completely).
  - Concurrency (two writers racing).
  - Stock restoration on void.
"""
import threading
import time

import pytest


# ═══════════════════════════════════════════════════════════
# HAPPY PATH
# ═══════════════════════════════════════════════════════════

class TestSaleTransactionSuccess:
    """A valid sale writes sale + items + stock decrement."""

    def test_sale_creates_row_and_decrements_stock(
        self, client, db, cashier_headers, sample_product
    ):
        pid = sample_product["id"]
        initial_stock = sample_product["stock_quantity"]

        resp = client.post(
            "/api/v1/sales",
            headers=cashier_headers,
            json={
                "items": [
                    {
                        "product_id": pid,
                        "quantity": 3,
                        "selling_price": 75.00,
                    }
                ],
                "payment_method": "cash",
                "payment_amount": 300.00,
                "discount": 0,
            },
        )
        assert resp.status_code == 201, resp.get_json()
        sale_id = resp.get_json()["data"]["sale"]["id"]

        # Sale row exists
        row = db.execute(
            "SELECT * FROM sales WHERE id = ?", (sale_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "completed"

        # Sale item row exists
        items = db.execute(
            "SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)
        ).fetchall()
        assert len(items) == 1
        assert items[0]["quantity"] == 3

        # Stock decremented exactly
        stock = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?", (pid,)
        ).fetchone()["stock_quantity"]
        assert stock == initial_stock - 3


# ═══════════════════════════════════════════════════════════
# ROLLBACK
# ═══════════════════════════════════════════════════════════

class TestSaleTransactionRollback:
    """
    A sale that fails partway through must leave NO trace:
    no sales row, no sale_items rows, no stock change.
    """

    def test_insufficient_stock_leaves_no_trace(
        self, client, db, cashier_headers, sample_product
    ):
        pid = sample_product["id"]
        initial_stock = sample_product["stock_quantity"]

        # Count sales before
        sales_before = db.execute(
            "SELECT COUNT(*) AS n FROM sales"
        ).fetchone()["n"]
        items_before = db.execute(
            "SELECT COUNT(*) AS n FROM sale_items"
        ).fetchone()["n"]

        # Try to sell more than exists
        resp = client.post(
            "/api/v1/sales",
            headers=cashier_headers,
            json={
                "items": [
                    {
                        "product_id": pid,
                        "quantity": initial_stock + 1,
                        "selling_price": 75.00,
                    }
                ],
                "payment_method": "cash",
                "payment_amount": 999999.00,
                "discount": 0,
            },
        )
        assert resp.status_code == 400

        # No new sale row
        sales_after = db.execute(
            "SELECT COUNT(*) AS n FROM sales"
        ).fetchone()["n"]
        items_after = db.execute(
            "SELECT COUNT(*) AS n FROM sale_items"
        ).fetchone()["n"]
        assert sales_after == sales_before, "Phantom sale row created"
        assert items_after == items_before, "Phantom sale_item row created"

        # Stock unchanged
        stock = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?", (pid,)
        ).fetchone()["stock_quantity"]
        assert stock == initial_stock, "Stock changed on failed sale"

    def test_nonexistent_product_rolls_back_prior_items(
        self, client, db, cashier_headers, sample_product
    ):
        """
        Two items in the cart. First is valid, second references a
        product that doesn't exist. The whole sale must roll back —
        including the first item's would-be stock decrement.
        """
        pid = sample_product["id"]
        initial_stock = sample_product["stock_quantity"]

        resp = client.post(
            "/api/v1/sales",
            headers=cashier_headers,
            json={
                "items": [
                    {
                        "product_id": pid,
                        "quantity": 2,
                        "selling_price": 75.00,
                    },
                    {
                        "product_id": 999999,
                        "quantity": 1,
                        "selling_price": 10.00,
                    },
                ],
                "payment_method": "cash",
                "payment_amount": 500.00,
                "discount": 0,
            },
        )
        assert resp.status_code == 400

        # Stock unchanged despite the valid first item
        stock = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?", (pid,)
        ).fetchone()["stock_quantity"]
        assert stock == initial_stock

    def test_insufficient_payment_rolls_back(
        self, client, db, cashier_headers, sample_product
    ):
        pid = sample_product["id"]
        initial_stock = sample_product["stock_quantity"]

        resp = client.post(
            "/api/v1/sales",
            headers=cashier_headers,
            json={
                "items": [
                    {
                        "product_id": pid,
                        "quantity": 2,
                        "selling_price": 75.00,
                    }
                ],
                "payment_method": "cash",
                "payment_amount": 1.00,
                "discount": 0,
            },
        )
        assert resp.status_code == 400

        stock = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?", (pid,)
        ).fetchone()["stock_quantity"]
        assert stock == initial_stock


# ═══════════════════════════════════════════════════════════
# VOID
# ═══════════════════════════════════════════════════════════

class TestVoidTransaction:
    """A void restores stock exactly and marks the sale voided."""

    def test_void_restores_stock(
        self, client, db, owner_headers, cashier_headers, sample_product
    ):
        pid = sample_product["id"]
        initial_stock = sample_product["stock_quantity"]

        # Make a sale
        resp = client.post(
            "/api/v1/sales",
            headers=cashier_headers,
            json={
                "items": [
                    {
                        "product_id": pid,
                        "quantity": 5,
                        "selling_price": 75.00,
                    }
                ],
                "payment_method": "cash",
                "payment_amount": 500.00,
                "discount": 0,
            },
        )
        assert resp.status_code == 201
        sale_id = resp.get_json()["data"]["sale"]["id"]

        # Confirm stock went down
        stock_after_sale = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?", (pid,)
        ).fetchone()["stock_quantity"]
        assert stock_after_sale == initial_stock - 5

        # Void it
        resp = client.post(
            f"/api/v1/sales/{sale_id}/void",
            headers=owner_headers,
            json={"reason": "test void"},
        )
        assert resp.status_code == 200, resp.get_json()

        # Stock restored exactly
        stock_after_void = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?", (pid,)
        ).fetchone()["stock_quantity"]
        assert stock_after_void == initial_stock, (
            f"Expected {initial_stock}, got {stock_after_void}"
        )

        # Sale marked voided
        status = db.execute(
            "SELECT status FROM sales WHERE id = ?", (sale_id,)
        ).fetchone()["status"]
        assert status == "voided"

    def test_double_void_is_rejected(
        self, client, owner_headers, cashier_headers, sample_product
    ):
        pid = sample_product["id"]

        resp = client.post(
            "/api/v1/sales",
            headers=cashier_headers,
            json={
                "items": [
                    {"product_id": pid, "quantity": 1, "selling_price": 75.00}
                ],
                "payment_method": "cash",
                "payment_amount": 100.00,
                "discount": 0,
            },
        )
        sale_id = resp.get_json()["data"]["sale"]["id"]

        resp = client.post(
            f"/api/v1/sales/{sale_id}/void",
            headers=owner_headers,
            json={"reason": "first"},
        )
        assert resp.status_code == 200

        resp = client.post(
            f"/api/v1/sales/{sale_id}/void",
            headers=owner_headers,
            json={"reason": "second"},
        )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════
# STOCK ADJUST
# ═══════════════════════════════════════════════════════════

class TestStockAdjustTransaction:
    """Stock add/remove/adjust each record an inventory_adjustments row."""

    def test_add_stock_records_adjustment(
        self, client, db, owner_headers, sample_product
    ):
        pid = sample_product["id"]
        initial_stock = sample_product["stock_quantity"]

        before = db.execute(
            "SELECT COUNT(*) AS n FROM inventory_adjustments "
            "WHERE product_id = ?",
            (pid,),
        ).fetchone()["n"]

        resp = client.post(
            "/api/v1/admin/stock/add",
            headers=owner_headers,
            json={
                "product_id": pid,
                "quantity": 20,
                "reason": "test restock",
            },
        )
        assert resp.status_code == 200, resp.get_json()

        after = db.execute(
            "SELECT COUNT(*) AS n FROM inventory_adjustments "
            "WHERE product_id = ?",
            (pid,),
        ).fetchone()["n"]
        assert after == before + 1

        # Stock went up by exactly 20
        stock = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?", (pid,)
        ).fetchone()["stock_quantity"]
        assert stock == initial_stock + 20

    def test_remove_more_than_available_leaves_no_trace(
        self, client, db, owner_headers, sample_product
    ):
        pid = sample_product["id"]
        initial_stock = sample_product["stock_quantity"]

        before = db.execute(
            "SELECT COUNT(*) AS n FROM inventory_adjustments "
            "WHERE product_id = ?",
            (pid,),
        ).fetchone()["n"]

        resp = client.post(
            "/api/v1/admin/stock/remove",
            headers=owner_headers,
            json={
                "product_id": pid,
                "quantity": initial_stock + 100,
                "reason": "too much",
            },
        )
        assert resp.status_code == 400

        # No adjustment row recorded
        after = db.execute(
            "SELECT COUNT(*) AS n FROM inventory_adjustments "
            "WHERE product_id = ?",
            (pid,),
        ).fetchone()["n"]
        assert after == before

        # Stock unchanged
        stock = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?", (pid,)
        ).fetchone()["stock_quantity"]
        assert stock == initial_stock


# ═══════════════════════════════════════════════════════════
# CONCURRENCY
# ═══════════════════════════════════════════════════════════

class TestConcurrentSales:
    """
    Two sales racing on the same product must not oversell.
    This is the test that proves the transaction() context manager
    actually serializes writes.
    """

    def test_concurrent_sales_dont_oversell(
        self, app, client, db, cashier_headers, sample_product
    ):
        pid = sample_product["id"]

        # Set stock to a small number so the race is easy to trigger
        with app.app_context():
            from database.connection import transaction
            with transaction() as tdb:
                tdb.cursor().execute(
                    "UPDATE products SET stock_quantity = 10 WHERE id = ?",
                    (pid,),
                )

        initial_stock = 10
        results = []
        errors = []

        def make_sale(quantity):
            try:
                c = app.test_client()
                resp = c.post(
                    "/api/v1/sales",
                    headers=cashier_headers,
                    json={
                        "items": [
                            {
                                "product_id": pid,
                                "quantity": quantity,
                                "selling_price": 75.00,
                            }
                        ],
                        "payment_method": "cash",
                        "payment_amount": 9999.00,
                        "discount": 0,
                    },
                )
                results.append(resp.status_code)
            except Exception as e:
                errors.append(str(e))

        # Fire 5 concurrent sales of 3 units each = 15 total
        # requested, 10 available. At most 3 should succeed.
        threads = [
            threading.Thread(target=make_sale, args=(3,))
            for _ in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"

        # Count successes
        successes = sum(1 for s in results if s == 201)
        assert successes <= 3, (
            f"Oversold: {successes} sales succeeded out of 10 units "
            f"(each sale is 3 units)"
        )

        # Final stock must never be negative
        stock = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?", (pid,)
        ).fetchone()["stock_quantity"]
        assert stock >= 0, f"Stock went negative: {stock}"
        assert stock == initial_stock - (successes * 3), (
            f"Stock {stock} does not match successes {successes}"
        )
