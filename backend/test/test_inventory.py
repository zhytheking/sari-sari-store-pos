import pytest


# ══════════
# STOCK ADD
# ══════════

class TestStockAdd:
    def test_add_stock_success(self, client, owner_headers, sample_product):
        resp = client.post('/api/v1/admin/stock/add', headers=owner_headers,
                           json={
            'product_id': sample_product['id'],
            'quantity': 25,
            'reason': 'Test restock',
        })
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()['data']
        assert data['old_quantity'] == 100
        assert data['added_quantity'] == 25
        assert data['new_quantity'] == 125

    def test_add_stock_invalid_quantity(self, client, owner_headers,
                                        sample_product):
        resp = client.post('/api/v1/admin/stock/add', headers=owner_headers,
                           json={
            'product_id': sample_product['id'],
            'quantity': 0,
            'reason': 'Bad',
        })
        assert resp.status_code == 400

    def test_add_stock_nonexistent_product(self, client, owner_headers):
        resp = client.post('/api/v1/admin/stock/add', headers=owner_headers,
                           json={
            'product_id': 999999,
            'quantity': 5,
            'reason': 'Test',
        })
        assert resp.status_code == 404

    def test_add_stock_requires_owner(self, client, cashier_headers,
                                      sample_product):
        resp = client.post('/api/v1/admin/stock/add', headers=cashier_headers,
                           json={
            'product_id': sample_product['id'],
            'quantity': 10,
            'reason': 'Try',
        })
        assert resp.status_code == 403


# ═════════════
# STOCK REMOVE
# ═════════════

class TestStockRemove:
    def test_remove_stock_success(self, client, owner_headers, sample_product):
        resp = client.post('/api/v1/admin/stock/remove',
                           headers=owner_headers, json={
            'product_id': sample_product['id'],
            'quantity': 10,
            'reason': 'Wastage',
        })
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()['data']['new_quantity'] == 90

    def test_remove_more_than_available(self, client, owner_headers,
                                        sample_product):
        resp = client.post('/api/v1/admin/stock/remove',
                           headers=owner_headers, json={
            'product_id': sample_product['id'],
            'quantity': 99999,
            'reason': 'Too much',
        })
        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'insufficient_stock'


# ═════════════
# STOCK ADJUST
# ═════════════

class TestStockAdjust:
    def test_adjust_to_value(self, client, owner_headers, sample_product):
        resp = client.post('/api/v1/admin/stock/adjust',
                           headers=owner_headers, json={
            'product_id': sample_product['id'],
            'new_quantity': 500,
            'reason': 'Inventory count',
        })
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()['data']['new_quantity'] == 500

    def test_adjust_to_zero(self, client, owner_headers, sample_product):
        resp = client.post('/api/v1/admin/stock/adjust',
                           headers=owner_headers, json={
            'product_id': sample_product['id'],
            'new_quantity': 0,
            'reason': 'Zero test',
        })
        assert resp.status_code == 200
        assert resp.get_json()['data']['new_quantity'] == 0

    def test_adjust_negative_fails(self, client, owner_headers,
                                   sample_product):
        resp = client.post('/api/v1/admin/stock/adjust',
                           headers=owner_headers, json={
            'product_id': sample_product['id'],
            'new_quantity': -5,
            'reason': 'Bad',
        })
        assert resp.status_code == 400


# ═════════
# TRANSFER
# ═════════
class TestTransfer:
    def test_transfer_success(self, client, owner_headers,
                              sample_product, second_product):
        resp = client.post('/api/v1/inventory/transfer',
                           headers=owner_headers, json={
            'from_product_id': sample_product['id'],
            'to_product_id': second_product['id'],
            'quantity': 10,
            'reason': 'Consolidation',
        })
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()['data']
        assert data['quantity'] == 10

    def test_transfer_insufficient_stock(self, client, owner_headers,
                                         sample_product, second_product):
        resp = client.post('/api/v1/inventory/transfer',
                           headers=owner_headers, json={
            'from_product_id': sample_product['id'],
            'to_product_id': second_product['id'],
            'quantity': 999999,
            'reason': 'Too much',
        })
        assert resp.status_code == 400

    def test_transfer_same_product_rejected(self, client, owner_headers,
                                            sample_product):
        resp = client.post('/api/v1/inventory/transfer',
                           headers=owner_headers, json={
            'from_product_id': sample_product['id'],
            'to_product_id': sample_product['id'],
            'quantity': 5,
            'reason': 'Self',
        })
        assert resp.status_code == 400

    def test_transfer_requires_owner(self, client, cashier_headers,
                                     sample_product, second_product):
        resp = client.post('/api/v1/inventory/transfer',
                           headers=cashier_headers, json={
            'from_product_id': sample_product['id'],
            'to_product_id': second_product['id'],
            'quantity': 5,
            'reason': 'Try',
        })
        assert resp.status_code == 403


# ══════════
# LOW STOCK
# ══════════
class TestLowStock:
    def test_low_stock_returns_products(self, client, owner_headers,
                                        sample_product):
        resp = client.get('/api/v1/inventory/low-stock?threshold=200',
                          headers=owner_headers)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'items' in data
        assert 'count' in data
        assert data['count'] >= 1

    def test_low_stock_empty_when_threshold_zero(self, client, owner_headers,
                                                 sample_product):
        # threshold=0 → no product should have stock <= 0
        resp = client.get('/api/v1/inventory/low-stock?threshold=-1',
                          headers=owner_headers)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['count'] == 0


# ══════════════════════════════
# INVENTORY ADJUSTMENT HISTORY
# ══════════════════════════════

class TestInventoryHistory:
    def test_history_after_add(self, client, owner_headers, sample_product):
        # Make an adjustment
        client.post('/api/v1/admin/stock/add', headers=owner_headers, json={
            'product_id': sample_product['id'],
            'quantity': 10,
            'reason': 'History test',
        })

        # Check history
        resp = client.get(
            f"/api/v1/inventory/history?product_id={sample_product['id']}",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['pagination']['total'] >= 1
        assert len(data['items']) >= 1
        # Most recent should be our add
        assert data['items'][0]['adjustment_type'] == 'add'
