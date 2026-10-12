
#Tests for the reports endpoints.

class TestSalesReport:
    #Tests for GET /api/v1/reports/sales

    def test_report_requires_owner(self, client, cashier_headers):
        resp = client.get(
            '/api/v1/reports/sales',
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_report_empty_range_returns_zero_totals(self, client, owner_headers):
        resp = client.get(
            '/api/v1/reports/sales'
            '?start_date=2000-01-01&end_date=2000-01-31',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['summary']['total_sales'] == 0
        assert data['summary']['total_revenue'] == 0
        assert data['period_data'] == []

    def test_report_with_data(self, client, owner_headers, cashier_headers, sample_product):
        
        real_price = float(sample_product['selling_price'])

        # Create a sale — client-sent price is ignored by the server
        sale_resp = client.post(
            '/api/v1/sales',
            headers=cashier_headers,
            json={
                'items': [
                    {
                        'product_id': sample_product['id'],
                        'quantity': 1,
                        'selling_price': 80.0,      # bogus, ignored
                    }
                ],
                'payment_method': 'cash',
                'payment_amount': 80.0,
                'discount': 0,
            },
        )
        assert sale_resp.status_code == 201

        resp = client.get(
            '/api/v1/reports/sales',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['summary']['total_sales'] >= 1
        assert data['summary']['total_revenue'] >= real_price


class TestInventoryReport:
    #Tests for GET /api/v1/reports/inventory

    def test_inventory_report_returns_items(self, client, owner_headers, sample_product):
        resp = client.get(
            '/api/v1/reports/inventory',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'items' in data
        assert 'summary' in data
        assert data['summary']['total_products'] >= 1

    def test_inventory_report_requires_owner(self, client, cashier_headers):
        resp = client.get(
            '/api/v1/reports/inventory',
            headers=cashier_headers,
        )
        assert resp.status_code == 403


class TestAnalytics:
    #Tests for GET /api/v1/reports/analytics.

    def test_analytics_returns_expected_shape(self, client, owner_headers):
        resp = client.get(
            '/api/v1/reports/analytics',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'today' in data
        assert 'week' in data
        assert 'month' in data
        assert 'inventory' in data
        assert 'recent_sales' in data
