"""
Product CRUD and category tests.

Covers:
  - Listing (public)
  - Getting by id / barcode
  - Search
  - Create / update / delete (owner-only)
  - Category CRUD
"""

# ════════════════
# PUBLIC LISTING
# ════════════════

class TestProductListing:

    def test_list_products_public(self, client, sample_product):
        resp = client.get('/api/v1/products')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'items' in data['data']
        assert len(data['data']['items']) >= 1

    def test_get_product_by_id(self, client, sample_product):
        pid = sample_product['id']
        resp = client.get(f'/api/v1/products/{pid}')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['id'] == pid
        assert data['name'] == sample_product['name']

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get('/api/v1/products/999999')
        assert resp.status_code == 404

    def test_get_by_barcode(self, client, sample_product):
        barcode = sample_product['barcode']
        resp = client.get(f'/api/v1/products/barcode/{barcode}')
        assert resp.status_code == 200
        assert resp.get_json()['data']['barcode'] == barcode

    def test_search(self, client, sample_product):
        resp = client.get('/api/v1/products/search?q=Test')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['data']) >= 1


# ═════════
# CREATE
# ═════════

    def test_owner_can_create(self, client, owner_headers):
        resp = client.post('/api/v1/products', headers=owner_headers, json={
            'name': 'New Product',
            'barcode': '9999000011112',
            'purchase_price': 10.00,
            'selling_price': 20.00,
            'stock_quantity': 50,
            'min_stock_level': 5,
            'unit': 'pc',
            'tax_rate': 0
        })
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()['data']
        assert data['name'] == 'New Product'
        assert float(data['selling_price']) == 20.00

    def test_cashier_forbidden(self, client, cashier_headers):
        resp = client.post('/api/v1/products', headers=cashier_headers, json={
            'name': 'Blocked',
            'purchase_price': 10,
            'selling_price': 20
        })
        assert resp.status_code == 403

    def test_anonymous_unauthorized(self, client):
        resp = client.post('/api/v1/products', json={
            'name': 'Anon',
            'purchase_price': 10,
            'selling_price': 20
        })
        assert resp.status_code == 401

    def test_selling_below_purchase_rejected(self, client, owner_headers):
        resp = client.post('/api/v1/products', headers=owner_headers, json={
            'name': 'Bad Price',
            'purchase_price': 100.00,
            'selling_price': 50.00,
            'stock_quantity': 10,
            'min_stock_level': 5
        })
        assert resp.status_code == 400

    def test_duplicate_barcode_rejected(self, client, owner_headers, sample_product):
        resp = client.post('/api/v1/products', headers=owner_headers, json={
            'name': 'Dup Barcode',
            'barcode': sample_product['barcode'],
            'purchase_price': 10,
            'selling_price': 20
        })
        assert resp.status_code == 409
        assert resp.get_json()['error'] == 'barcode_exists'

    def test_category_id_validated(self, client, owner_headers):
        resp = client.post('/api/v1/products', headers=owner_headers, json={
            'name': 'Bad Category',
            'category_id': 999999,
            'purchase_price': 10,
            'selling_price': 20
        })
        assert resp.status_code == 404
        assert resp.get_json()['error'] == 'category_not_found'


# ═════════
# UPDATE
# ═════════

class TestUpdateProduct:

    def test_update_name(self, client, owner_headers, sample_product):
        pid = sample_product['id']
        resp = client.put(f'/api/v1/products/{pid}',
                          headers=owner_headers,
                          json={'name': 'Renamed Product'})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()['data']['name'] == 'Renamed Product'

    def test_update_category_to_invalid_id_rejected(self, client, owner_headers,
                                                       sample_product):
        pid = sample_product['id']
        resp = client.put(f'/api/v1/products/{pid}',
                          headers=owner_headers,
                          json={'category_id': 999999})
        assert resp.status_code == 404
        assert resp.get_json()['error'] == 'category_not_found'

    def test_update_duplicate_barcode_rejected(self, client, owner_headers,
                                                 sample_product, second_product):
        pid = sample_product['id']
        resp = client.put(f'/api/v1/products/{pid}',
                          headers=owner_headers,
                          json={'barcode': second_product['barcode']})
        assert resp.status_code == 409

    def test_update_nonexistent_product(self, client, owner_headers):
        resp = client.put('/api/v1/products/999999',
                          headers=owner_headers,
                          json={'name': 'Ghost'})
        assert resp.status_code == 404


# ═════════
# DELETE
# ═════════

class TestDeleteProduct:

    def test_owner_soft_delete(self, client, owner_headers, sample_product):
        pid = sample_product['id']
        resp = client.delete(f'/api/v1/products/{pid}',
                             headers=owner_headers)
        assert resp.status_code == 200

        # Product must not appear in the active list
        listing = client.get('/api/v1/products')
        ids = [p['id'] for p in listing.get_json()['data']['items']]
        assert pid not in ids

    def test_delete_nonexistent_returns_404(self, client, owner_headers):
        resp = client.delete('/api/v1/products/999999',
                             headers=owner_headers)
        assert resp.status_code == 404


# ═════════════
# CATEGORIES
# ═════════════

class TestCategories:

    def test_list_categories_public(self, client):
        resp = client.get('/api/v1/products/categories')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert isinstance(data['data'], list)

    def test_create_category_as_owner(self, client, owner_headers):
        resp = client.post('/api/v1/products/categories',
                           headers=owner_headers,
                           json={
                               'name': 'TestCat',
                               'description': 'Test category'
                           })
        assert resp.status_code == 201
        assert resp.get_json()['data']['name'] == 'TestCat'

    def test_create_duplicate_category_rejected(self, client, owner_headers):
        client.post('/api/v1/products/categories',
                    headers=owner_headers,
                    json={'name': 'DupCat'})
        resp = client.post('/api/v1/products/categories',
                           headers=owner_headers,
                           json={'name': 'DupCat'})
        assert resp.status_code == 409
        assert resp.get_json()['error'] == 'category_exists'

    def test_delete_in_use_category_rejected(self, client, owner_headers,
                                               sample_product):
        cats = client.get('/api/v1/products/categories').get_json()['data']
        used = [c for c in cats if c.get('product_count', 0) > 0]
        if not used:
            return  # skip if no categories in use
        cat_id = used[0]['id']

        resp = client.delete(f'/api/v1/products/categories/{cat_id}',
                             headers=owner_headers)
        assert resp.status_code == 409
        assert resp.get_json()['error'] == 'category_in_use'
