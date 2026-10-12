"""
Sales endpoint tests.

Covers:
  - Cash sale (creation, stock decrement, change calculation)
  - GCash sale (reference validation)
  - Listing
  - Void (stock restoration, double-void prevention)
  - Inventory adjustment logging
"""


# ═══════════
# CASH SALES
# ═══════════
class TestCreateSaleCash:

    def test_create_sale_cash_success(self, client, cashier_headers, sample_product):

        real_price = float(sample_product['selling_price'])
        resp = client.post('/api/v1/sales', headers=cashier_headers, json={
            'items': [{
                'product_id': sample_product['id'],
                'quantity': 2,
                'selling_price': 80.0  # bogus, ignored
            }],
            'payment_method': 'cash',
            'payment_amount': 200.0,
            'discount': 0,
            'customer_name': 'Test Customer'
        })
        assert resp.status_code == 201, resp.get_json()
        sale = resp.get_json()['data']['sale']

        expected_total = real_price * 2
        expected_change = 200.0 - expected_total

        assert sale['final_amount'] == expected_total
        assert sale['payment_method'] == 'cash'
        assert sale['change_amount'] == expected_change
        assert sale['items'][0]['quantity'] == 2
        assert float(sale['items'][0]['selling_price']) == real_price

    def test_create_sale_insufficient_payment(self, client, cashier_headers,
                                                sample_product):
        resp = client.post('/api/v1/sales', headers=cashier_headers, json={
            'items': [{
                'product_id': sample_product['id'],
                'quantity': 5,
                'selling_price': 80.0
            }],
            'payment_method': 'cash',
            'payment_amount': 100.0,
            'discount': 0
        })
        assert resp.status_code == 400

    def test_create_sale_insufficient_stock(self, client, cashier_headers,
                                              sample_product):
        resp = client.post('/api/v1/sales', headers=cashier_headers, json={
            'items': [{
                'product_id': sample_product['id'],
                'quantity': 99999,
                'selling_price': 80.0
            }],
            'payment_method': 'cash',
            'payment_amount': 9999999.0,
            'discount': 0
        })
        assert resp.status_code == 400

    def test_create_sale_reduces_stock(self, client, db, cashier_headers,
                                         sample_product):
        initial = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?",
            (sample_product['id'],)
        ).fetchone()['stock_quantity']

        resp = client.post('/api/v1/sales', headers=cashier_headers, json={
            'items': [{
                'product_id': sample_product['id'],
                'quantity': 3,
                'selling_price': 80.0
            }],
            'payment_method': 'cash',
            'payment_amount': 240.0,
            'discount': 0
        })
        assert resp.status_code == 201

        after = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?",
            (sample_product['id'],)
        ).fetchone()['stock_quantity']
        assert after == initial - 3

    def test_sale_records_inventory_adjustment(self, client, db,
                                                 cashier_headers,
                                                 sample_product):
        """
        Sales must record a row in inventory_adjustments so the
        stock history is complete.
        """
        before = db.execute(
            "SELECT COUNT(*) AS n FROM inventory_adjustments "
            "WHERE product_id = ?",
            (sample_product['id'],)
        ).fetchone()['n']

        resp = client.post('/api/v1/sales', headers=cashier_headers, json={
            'items': [{
                'product_id': sample_product['id'],
                'quantity': 1,
                'selling_price': 80.0
            }],
            'payment_method': 'cash',
            'payment_amount': 100.0,
            'discount': 0
        })
        assert resp.status_code == 201

        after = db.execute(
            "SELECT COUNT(*) AS n FROM inventory_adjustments "
            "WHERE product_id = ?",
            (sample_product['id'],)
        ).fetchone()['n']
        assert after == before + 1


# ═════════════
# GCASH SALES
# ════════════

class TestCreateSaleGCash:

    def test_gcash_with_reference(self, client, cashier_headers, sample_product):
        resp = client.post('/api/v1/sales', headers=cashier_headers, json={
            'items': [{
                'product_id': sample_product['id'],
                'quantity': 1,
                'selling_price': 80.0
            }],
            'payment_method': 'gcash',
            'payment_amount': 80.0,
            'payment_reference': '123',
            'discount': 0
        })
        assert resp.status_code == 201, resp.get_json()
        sale = resp.get_json()['data']['sale']
        assert sale['payment_method'] == 'gcash'
        assert sale['payment_reference'] == '123'

    def test_gcash_missing_reference(self, client, cashier_headers,
                                       sample_product):
        resp = client.post('/api/v1/sales', headers=cashier_headers, json={
            'items': [{
                'product_id': sample_product['id'],
                'quantity': 1,
                'selling_price': 80.0
            }],
            'payment_method': 'gcash',
            'payment_amount': 80.0,
            'discount': 0
        })
        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'validation_error'

    def test_gcash_bad_reference(self, client, cashier_headers, sample_product):
        resp = client.post('/api/v1/sales', headers=cashier_headers, json={
            'items': [{
                'product_id': sample_product['id'],
                'quantity': 1,
                'selling_price': 80.0
            }],
            'payment_method': 'gcash',
            'payment_amount': 80.0,
            'payment_reference': 'ABCD',
            'discount': 0
        })
        assert resp.status_code == 400


# ════════════
# LIST SALES
# ════════════

class TestListSales:

    def test_list_sales_requires_auth(self, client):
        resp = client.get('/api/v1/sales')
        assert resp.status_code == 401

    def test_list_sales_returns_paginated(self, client, cashier_headers):
        resp = client.get('/api/v1/sales?per_page=5',
                          headers=cashier_headers)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'items' in data
        assert 'pagination' in data


# ══════════
# VOID SALE
# ══════════

class TestVoidSale:

    def test_void_restores_stock(self, client, db, owner_headers,
                                   cashier_headers, sample_product):
        initial = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?",
            (sample_product['id'],)
        ).fetchone()['stock_quantity']

        # Make a sale
        resp = client.post('/api/v1/sales', headers=cashier_headers, json={
            'items': [{
                'product_id': sample_product['id'],
                'quantity': 5,
                'selling_price': 80.0
            }],
            'payment_method': 'cash',
            'payment_amount': 500.0,
            'discount': 0
        })
        assert resp.status_code == 201
        sale_id = resp.get_json()['data']['sale']['id']

        # Stock went down
        mid = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?",
            (sample_product['id'],)
        ).fetchone()['stock_quantity']
        assert mid == initial - 5

        # Void it
        resp = client.post(f'/api/v1/sales/{sale_id}/void',
                           headers=owner_headers,
                           json={'reason': 'test void'})
        assert resp.status_code == 200

        # Stock restored
        after = db.execute(
            "SELECT stock_quantity FROM products WHERE id = ?",
            (sample_product['id'],)
        ).fetchone()['stock_quantity']
        assert after == initial

        # Marked as voided
        status = db.execute(
            "SELECT status FROM sales WHERE id = ?", (sale_id,)
        ).fetchone()['status']
        assert status == 'voided'

    def test_double_void_rejected(self, client, owner_headers,
                                    cashier_headers, sample_product):
        resp = client.post('/api/v1/sales', headers=cashier_headers, json={
            'items': [{
                'product_id': sample_product['id'],
                'quantity': 1,
                'selling_price': 80.0
            }],
            'payment_method': 'cash',
            'payment_amount': 100.0,
            'discount': 0
        })
        sale_id = resp.get_json()['data']['sale']['id']

        r1 = client.post(f'/api/v1/sales/{sale_id}/void',
                         headers=owner_headers, json={'reason': 'first'})
        assert r1.status_code == 200

        r2 = client.post(f'/api/v1/sales/{sale_id}/void',
                         headers=owner_headers, json={'reason': 'second'})
        assert r2.status_code == 400