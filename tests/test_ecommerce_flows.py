"""
Bazaarly Multi-Vendor Automated Test Suite
Validates authentication, catalog, cart, multi-vendor order splitting, atomic stock reservation, and payment gateways.
"""

import unittest
from fastapi.testclient import TestClient
from bazaarly.api.server import app
from bazaarly.db.database import init_schema, seed_data, query_db


class TestBazaarlyEcommercePlatform(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_schema()
        seed_data()
        cls.client = TestClient(app)

    def test_01_api_health(self):
        """Validates basic health endpoint."""
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")

    def test_02_auth_login_and_roles(self):
        """Tests login for Customer, Seller, Admin, and Super Admin."""
        # 1. Customer login
        res = self.client.post("/api/auth/login", json={
            "email": "john.doe@example.com",
            "password": "password123"
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn("access_token", res.json())
        self.assertEqual(res.json()["user"]["role"], "customer")

        # 2. Seller login
        res_sel = self.client.post("/api/auth/login", json={
            "email": "techstore@bazaarly.com",
            "password": "password123"
        })
        self.assertEqual(res_sel.status_code, 200)
        self.assertEqual(res_sel.json()["user"]["role"], "seller")
        self.assertIsNotNone(res_sel.json()["user"]["seller_profile"])

        # 3. Super Admin login
        res_sa = self.client.post("/api/auth/login", json={
            "email": "superadmin@bazaarly.com",
            "password": "password123"
        })
        self.assertEqual(res_sa.status_code, 200)
        self.assertEqual(res_sa.json()["user"]["role"], "super_admin")

    def test_03_catalog_browsing_and_filtering(self):
        """Tests product listing, category filtering, search, and sorting."""
        # 1. List all products
        res = self.client.get("/api/products")
        self.assertEqual(res.status_code, 200)
        products = res.json()
        self.assertGreaterEqual(len(products), 5)

        # 2. Filter by category
        res_cat = self.client.get("/api/products?category=electronics")
        self.assertEqual(res_cat.status_code, 200)
        for p in res_cat.json():
            self.assertEqual(p["category_slug"], "electronics")

        # 3. Search term
        res_search = self.client.get("/api/products?q=Sony")
        self.assertEqual(res_search.status_code, 200)
        self.assertTrue(any("Sony" in p["title"] for p in res_search.json()))

        # 4. Product details
        first_id = products[0]["id"]
        res_detail = self.client.get(f"/api/products/{first_id}")
        self.assertEqual(res_detail.status_code, 200)
        detail = res_detail.json()
        self.assertIn("images", detail)
        self.assertIn("variants", detail)
        self.assertIn("reviews", detail)

    def test_04_cart_and_coupon_operations(self):
        """Tests adding items to cart, stock limits, and coupon recalculation."""
        # Login customer
        auth_res = self.client.post("/api/auth/login", json={
            "email": "jane.smith@example.com",
            "password": "password123"
        }).json()
        token = auth_res["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Clear cart first
        self.client.delete("/api/cart", headers=headers)

        # Add Sony Headphones to cart
        add_res = self.client.post("/api/cart/items", json={
            "product_id": "prd-sony-wh1000xm5",
            "quantity": 1
        }, headers=headers)
        self.assertEqual(add_res.status_code, 200)

        # Get cart
        cart_res = self.client.get("/api/cart", headers=headers)
        self.assertEqual(cart_res.status_code, 200)
        cart = cart_res.json()
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 1)

        # Apply valid coupon
        coupon_res = self.client.get("/api/cart?coupon=WELCOME10", headers=headers)
        self.assertEqual(coupon_res.status_code, 200)
        cart_with_coupon = coupon_res.json()
        self.assertGreater(cart_with_coupon["discount_amount"], 0)
        self.assertIsNotNone(cart_with_coupon["applied_coupon"])

    def test_05_multi_vendor_checkout_and_order_splitting(self):
        """Tests complete checkout with items from multiple distinct sellers and checks suborder separation."""
        auth_res = self.client.post("/api/auth/login", json={
            "email": "john.doe@example.com",
            "password": "password123"
        }).json()
        token = auth_res["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Clear cart
        self.client.delete("/api/cart", headers=headers)

        # Add item from Nexus Tech (Sony Headphones)
        self.client.post("/api/cart/items", json={
            "product_id": "prd-sony-wh1000xm5",
            "quantity": 1
        }, headers=headers)

        # Add item from Urban Weave (Nike Sneakers)
        self.client.post("/api/cart/items", json={
            "product_id": "prd-nike-air-max-plus",
            "quantity": 1
        }, headers=headers)

        # Record initial stock
        initial_stock_sony = query_db("SELECT stock_quantity FROM products WHERE id = 'prd-sony-wh1000xm5';", one=True)["stock_quantity"]

        # Place Order via Stripe Simulator
        checkout_res = self.client.post("/api/checkout", json={
            "payment_method": "stripe",
            "coupon_code": "WELCOME10",
            "order_notes": "Unit test multi-vendor order"
        }, headers=headers)
        self.assertEqual(checkout_res.status_code, 200)
        order_info = checkout_res.json()
        order_id = order_info["order_id"]
        self.assertTrue(order_info["success"])

        # Verify stock was atomically deducted
        updated_stock_sony = query_db("SELECT stock_quantity FROM products WHERE id = 'prd-sony-wh1000xm5';", one=True)["stock_quantity"]
        self.assertEqual(updated_stock_sony, initial_stock_sony - 1)

        # Verify parent order and split suborders
        order_details = self.client.get(f"/api/orders/{order_id}", headers=headers).json()
        self.assertEqual(len(order_details["suborders"]), 2)
        sellers_in_order = {s["seller_id"] for s in order_details["suborders"]}
        self.assertIn("sel-nexus-tech", sellers_in_order)
        self.assertIn("sel-urban-weave", sellers_in_order)
        self.assertEqual(order_details["payment_status"], "paid")

    def test_06_seller_dashboard_and_fulfillment(self):
        """Tests seller portal suborder view and shipment status progression."""
        auth_res = self.client.post("/api/auth/login", json={
            "email": "techstore@bazaarly.com",
            "password": "password123"
        }).json()
        token = auth_res["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Dashboard metrics
        dash = self.client.get("/api/seller/dashboard", headers=headers).json()
        self.assertIn("kpis", dash)
        self.assertGreater(dash["kpis"]["total_revenue"], 0)

        # List suborders
        suborders = self.client.get("/api/seller/orders", headers=headers).json()
        self.assertGreater(len(suborders), 0)
        first_sub_id = suborders[0]["id"]

        # Update suborder status to packed then shipped
        update_res = self.client.put(f"/api/seller/orders/{first_sub_id}/status", json={
            "status": "shipped",
            "tracking_number": "TRK-EXP-992211",
            "carrier": "DHL Express"
        }, headers=headers)
        self.assertEqual(update_res.status_code, 200)

        # Verify update persisted
        updated_sub = query_db("SELECT status, tracking_number FROM seller_orders WHERE id = ?;", (first_sub_id,), one=True)
        self.assertEqual(updated_sub["status"], "shipped")
        self.assertEqual(updated_sub["tracking_number"], "TRK-EXP-992211")

    def test_07_admin_seller_approval_and_reporting(self):
        """Tests operations admin approving pending seller and generating CSV report."""
        auth_res = self.client.post("/api/auth/login", json={
            "email": "admin@bazaarly.com",
            "password": "password123"
        }).json()
        token = auth_res["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Admin dashboard
        dash = self.client.get("/api/admin/dashboard", headers=headers).json()
        self.assertIn("kpis", dash)

        # 2. Approve pending seller GadgetVerse
        appr_res = self.client.put("/api/admin/sellers/sel-gadget-verse/approval", json={
            "approval_status": "approved",
            "commission_rate": 8.5
        }, headers=headers)
        self.assertEqual(appr_res.status_code, 200)
        seller = query_db("SELECT approval_status, commission_rate FROM seller_profiles WHERE id = 'sel-gadget-verse';", one=True)
        self.assertEqual(seller["approval_status"], "approved")
        self.assertEqual(seller["commission_rate"], 8.5)

        # 3. CSV Report generation
        csv_res = self.client.get("/api/admin/reports/csv", headers=headers)
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn("Order Number,Date,Customer", csv_res.text)

    def test_08_super_admin_governance(self):
        """Tests super admin settings update and audit log recording."""
        auth_res = self.client.post("/api/auth/login", json={
            "email": "superadmin@bazaarly.com",
            "password": "password123"
        }).json()
        token = auth_res["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Update system commission and tax
        res = self.client.put("/api/super-admin/settings", json={
            "settings": {
                "platform_commission_percent": "12.5",
                "tax_percent": "6.0"
            }
        }, headers=headers)
        self.assertEqual(res.status_code, 200)

        # Verify audit log was recorded
        audit = query_db("SELECT * FROM audit_logs WHERE action = 'update_system_settings' ORDER BY created_at DESC LIMIT 1;", one=True)
        self.assertIsNotNone(audit)
        self.assertIn("12.5", audit["metadata_json"])


if __name__ == "__main__":
    unittest.main()
