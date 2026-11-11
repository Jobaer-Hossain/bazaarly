"""
Bazaarly Database Layer
Thread-safe SQLite engine with WAL mode, foreign keys, schema migrations, and rich seed data.
"""

import sqlite3
import json
import os
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager

DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "bazaarly.db"


def hash_password(password: str) -> str:
    """Computes a SHA-256 hash with salt for secure credential storage."""
    salt = "bazaarly_secure_salt_2026"
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


@contextmanager
def get_db_connection():
    """Context manager for SQLite connections with row factories and foreign keys enabled."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_db(query: str, args: Tuple = (), one: bool = False) -> Any:
    """Executes a read query and returns dictionary rows."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, args)
        rows = cursor.fetchall()
        if not rows:
            return None if one else []
        results = [dict(r) for r in rows]
        return results[0] if one else results


def execute_db(query: str, args: Tuple = ()) -> int:
    """Executes an INSERT, UPDATE, or DELETE query and returns the lastrowid."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, args)
        return cursor.lastrowid or cursor.rowcount


def init_schema():
    """Initializes all normalized relational tables if they do not exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Users Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT,
            role TEXT NOT NULL CHECK(role IN ('customer', 'seller', 'admin', 'super_admin')),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'suspended', 'pending')),
            is_verified INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 2. Seller Profiles Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS seller_profiles (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            store_name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            store_description TEXT,
            logo_url TEXT,
            banner_url TEXT,
            business_email TEXT,
            phone TEXT,
            address TEXT,
            tax_id TEXT,
            bank_name TEXT,
            bank_account TEXT,
            approval_status TEXT NOT NULL DEFAULT 'pending' CHECK(approval_status IN ('pending', 'approved', 'rejected')),
            commission_rate REAL NOT NULL DEFAULT 10.0,
            rating_avg REAL NOT NULL DEFAULT 5.0,
            total_sales REAL NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """)

        # 3. Customer Profiles Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_profiles (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            loyalty_points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """)

        # 4. Addresses Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS addresses (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address_line1 TEXT NOT NULL,
            address_line2 TEXT,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            postal_code TEXT NOT NULL,
            country TEXT NOT NULL DEFAULT 'Bangladesh',
            is_default INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """)

        # 5. Categories Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            image_url TEXT,
            display_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        );
        """)

        # 6. Brands Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS brands (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            logo_url TEXT,
            is_active INTEGER DEFAULT 1
        );
        """)

        # 7. Products Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            seller_id TEXT NOT NULL,
            category_id TEXT NOT NULL,
            brand_id TEXT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL,
            regular_price REAL NOT NULL,
            sale_price REAL NOT NULL,
            sku TEXT UNIQUE NOT NULL,
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            low_stock_threshold INTEGER NOT NULL DEFAULT 5,
            is_approved INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            rating_avg REAL NOT NULL DEFAULT 0.0,
            reviews_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES seller_profiles (id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories (id),
            FOREIGN KEY (brand_id) REFERENCES brands (id)
        );
        """)

        # 8. Product Images Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_images (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            image_url TEXT NOT NULL,
            is_primary INTEGER DEFAULT 0,
            display_order INTEGER DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        );
        """)

        # 9. Product Variants Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_variants (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            sku TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            attribute_name TEXT NOT NULL,
            attribute_value TEXT NOT NULL,
            price_override REAL,
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        );
        """)

        # 10. Carts Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS carts (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE,
            session_id TEXT UNIQUE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """)

        # 11. Cart Items Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart_items (
            id TEXT PRIMARY KEY,
            cart_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            variant_id TEXT,
            quantity INTEGER NOT NULL DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cart_id) REFERENCES carts (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE,
            FOREIGN KEY (variant_id) REFERENCES product_variants (id) ON DELETE CASCADE
        );
        """)

        # 12. Wishlists Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS wishlists (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, product_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        );
        """)

        # 13. Coupons Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS coupons (
            id TEXT PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            discount_type TEXT NOT NULL CHECK(discount_type IN ('percentage', 'fixed')),
            discount_value REAL NOT NULL,
            min_spend REAL NOT NULL DEFAULT 0.0,
            max_discount REAL,
            usage_limit INTEGER DEFAULT 1000,
            times_used INTEGER DEFAULT 0,
            expires_at TIMESTAMP,
            is_active INTEGER DEFAULT 1
        );
        """)

        # 14. Parent Orders Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            order_number TEXT UNIQUE NOT NULL,
            customer_id TEXT NOT NULL,
            shipping_address_json TEXT NOT NULL,
            subtotal REAL NOT NULL,
            shipping_cost REAL NOT NULL,
            tax_amount REAL NOT NULL,
            discount_amount REAL NOT NULL DEFAULT 0.0,
            total_amount REAL NOT NULL,
            coupon_code TEXT,
            payment_method TEXT NOT NULL CHECK(payment_method IN ('cod', 'stripe', 'sslcommerz', 'bank_transfer')),
            payment_status TEXT NOT NULL DEFAULT 'pending' CHECK(payment_status IN ('pending', 'paid', 'failed', 'refunded')),
            order_status TEXT NOT NULL DEFAULT 'confirmed' CHECK(order_status IN ('pending_payment', 'confirmed', 'processing', 'packed', 'shipped', 'delivered', 'cancelled', 'refunded')),
            tracking_number TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES users (id)
        );
        """)

        # 15. Seller Suborders Table (for Multi-Vendor separation)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS seller_orders (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            seller_id TEXT NOT NULL,
            suborder_number TEXT UNIQUE NOT NULL,
            subtotal REAL NOT NULL,
            shipping_cost REAL NOT NULL DEFAULT 0.0,
            seller_earnings REAL NOT NULL,
            platform_fee REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed', 'processing', 'packed', 'shipped', 'delivered', 'cancelled')),
            tracking_number TEXT,
            carrier TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
            FOREIGN KEY (seller_id) REFERENCES seller_profiles (id)
        );
        """)

        # 16. Order Items Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id TEXT PRIMARY KEY,
            seller_order_id TEXT NOT NULL,
            order_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            variant_id TEXT,
            product_title TEXT NOT NULL,
            variant_title TEXT,
            unit_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            total_price REAL NOT NULL,
            FOREIGN KEY (seller_order_id) REFERENCES seller_orders (id) ON DELETE CASCADE,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id)
        );
        """)

        # 17. Payment Records Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            transaction_ref TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            status TEXT NOT NULL CHECK(status IN ('initiated', 'completed', 'failed', 'refunded')),
            raw_response TEXT,
            idempotency_key TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
        );
        """)

        # 18. Product Reviews Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            title TEXT,
            comment TEXT NOT NULL,
            is_verified_purchase INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        """)

        # 19. Seller Payouts Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS seller_payouts (
            id TEXT PRIMARY KEY,
            seller_id TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'requested' CHECK(status IN ('requested', 'approved', 'rejected', 'completed')),
            bank_details TEXT,
            notes TEXT,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES seller_profiles (id)
        );
        """)

        # 20. Audit Logs Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 21. Platform System Settings Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Indexes for fast querying
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_seller ON products (seller_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products (category_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders (customer_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seller_orders_seller ON seller_orders (seller_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items (order_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews (product_id);")


def seed_data():
    """Populates seed data with all 4 roles, categories, brands, products, variants, and settings."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Check if already seeded
        cursor.execute("SELECT COUNT(*) as cnt FROM users;")
        if cursor.fetchone()["cnt"] > 0:
            return

        print("Seeding Bazaarly eCommerce database...")

        # System Settings
        settings = [
            ("site_name", "Bazaarly"),
            ("support_email", "support@bazaarly.com"),
            ("currency_symbol", "$"),
            ("currency_code", "USD"),
            ("platform_commission_percent", "10.0"),
            ("tax_percent", "5.0"),
            ("flat_shipping_rate", "5.00"),
            ("free_shipping_threshold", "100.00"),
            ("allow_guest_checkout", "true")
        ]
        cursor.executemany("INSERT INTO system_settings (key, value) VALUES (?, ?);", settings)

        # Users & Demo Accounts
        demo_users = [
            ("usr-superadmin", "superadmin@bazaarly.com", hash_password("password123"), "Platform Executive (Super Admin)", "+15550000001", "super_admin", "active"),
            ("usr-admin", "admin@bazaarly.com", hash_password("password123"), "Operations Lead (Admin)", "+15550000002", "admin", "active"),
            ("usr-seller-tech", "techstore@bazaarly.com", hash_password("password123"), "Marcus Vance (Nexus Tech)", "+15550000003", "seller", "active"),
            ("usr-seller-fashion", "fashionhub@bazaarly.com", hash_password("password123"), "Elena Rostova (Urban Weave)", "+15550000004", "seller", "active"),
            ("usr-seller-pending", "gadgetverse@bazaarly.com", hash_password("password123"), "Arif Chowdhury (GadgetVerse)", "+8801700000001", "seller", "pending"),
            ("usr-customer-john", "john.doe@example.com", hash_password("password123"), "Johnathan Doe", "+15551234567", "customer", "active"),
            ("usr-customer-jane", "jane.smith@example.com", hash_password("password123"), "Jane Smith", "+15559876543", "customer", "active"),
        ]
        cursor.executemany("""
        INSERT INTO users (id, email, password_hash, full_name, phone, role, status)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, demo_users)

        # Seller Profiles
        seller_profiles = [
            ("sel-nexus-tech", "usr-seller-tech", "Nexus Electronics", "nexus-electronics", "Official distributor of high-fidelity audio, computing, and smart accessories.", "https://images.unsplash.com/photo-1550009158-9ebf69173e03?auto=format&fit=crop&w=120&q=80", "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80", "sales@nexustech.io", "+15550000003", "42 Silicon Blvd, Austin, TX", "TX-998822", "Chase Bank", "9876543210", "approved", 10.0, 4.9, 14250.0),
            ("sel-urban-weave", "usr-seller-fashion", "Urban Weave Atelier", "urban-weave", "Contemporary sustainable apparel, premium denim, and minimalist footwear.", "https://images.unsplash.com/photo-1544441893-675973e31985?auto=format&fit=crop&w=120&q=80", "https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=crop&w=1200&q=80", "hello@urbanweave.co", "+15550000004", "180 Mercer St, New York, NY", "NY-445511", "Bank of America", "1234567890", "approved", 12.0, 4.8, 8920.0),
            ("sel-gadget-verse", "usr-seller-pending", "GadgetVerse Labs", "gadgetverse", "Experimental consumer electronics and robotics kits.", "https://images.unsplash.com/photo-1531297484001-80022131f5a1?auto=format&fit=crop&w=120&q=80", "https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=1200&q=80", "contact@gadgetverse.bd", "+8801700000001", "Gulshan-2, Dhaka, Bangladesh", "BD-778899", "BRAC Bank", "5544332211", "pending", 10.0, 5.0, 0.0),
        ]
        cursor.executemany("""
        INSERT INTO seller_profiles (id, user_id, store_name, slug, store_description, logo_url, banner_url, business_email, phone, address, tax_id, bank_name, bank_account, approval_status, commission_rate, rating_avg, total_sales)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, seller_profiles)

        # Customer Addresses
        addresses = [
            ("addr-john-default", "usr-customer-john", "Johnathan Doe", "+15551234567", "742 Evergreen Terrace", "Apt 4B", "Springfield", "OR", "97477", "United States", 1),
            ("addr-jane-default", "usr-customer-jane", "Jane Smith", "+15559876543", "100 Broadway Ave", "Suite 200", "New York", "NY", "10005", "United States", 1)
        ]
        cursor.executemany("""
        INSERT INTO addresses (id, user_id, full_name, phone, address_line1, address_line2, city, state, postal_code, country, is_default)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, addresses)

        # Categories
        categories = [
            ("cat-electronics", "Electronics & Audio", "electronics", "Laptops, high-res audio, mobile devices and accessories.", "https://images.unsplash.com/photo-1498049794561-7780e7231661?auto=format&fit=crop&w=600&q=80", 1),
            ("cat-fashion", "Fashion & Apparel", "fashion", "Minimalist streetwear, premium jackets, footwear and accessories.", "https://images.unsplash.com/photo-1445205170230-053b83016050?auto=format&fit=crop&w=600&q=80", 2),
            ("cat-home", "Home & Lifestyle", "home-lifestyle", "Ergonomic workspace furniture, ambient lighting, and kitchenware.", "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=600&q=80", 3),
            ("cat-sports", "Sports & Fitness", "sports-fitness", "Activewear, performance gear, and health tracking devices.", "https://images.unsplash.com/photo-1517838277536-f5f99be501cd?auto=format&fit=crop&w=600&q=80", 4),
        ]
        cursor.executemany("""
        INSERT INTO categories (id, name, slug, description, image_url, display_order)
        VALUES (?, ?, ?, ?, ?, ?);
        """, categories)

        # Brands
        brands = [
            ("br-sony", "Sony", "sony", "https://images.unsplash.com/photo-1546868871-7041f2a55e12?auto=format&fit=crop&w=120&q=80"),
            ("br-apple", "Apple", "apple", "https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?auto=format&fit=crop&w=120&q=80"),
            ("br-nike", "Nike", "nike", "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=120&q=80"),
            ("br-levis", "Levi's", "levis", "https://images.unsplash.com/photo-1582552938357-32b906df40cb?auto=format&fit=crop&w=120&q=80"),
            ("br-dyson", "Dyson", "dyson", "https://images.unsplash.com/photo-1558317374-067fb5f30001?auto=format&fit=crop&w=120&q=80"),
        ]
        cursor.executemany("""
        INSERT INTO brands (id, name, slug, logo_url)
        VALUES (?, ?, ?, ?);
        """, brands)

        # Products
        products = [
            ("prd-sony-wh1000xm5", "sel-nexus-tech", "cat-electronics", "br-sony", "Sony WH-1000XM5 Wireless Noise-Cancelling Headphones", "sony-wh-1000xm5-headphones", "Industry-leading noise cancelation with two processors and 8 microphones. Magnificent sound quality engineered to perfection with the new Integrated Processor V1. Up to 30-hour battery life.", 399.99, 348.00, "SNY-WH-XM5-BLK", 24, 4, 1, 1, 4.9, 18),
            ("prd-apple-macbook-air", "sel-nexus-tech", "cat-electronics", "br-apple", "Apple MacBook Air 15-inch M3 Chip (16GB RAM, 512GB SSD)", "apple-macbook-air-15-m3", "Strikingly thin and fast. The M3 chip brings even greater capabilities to the ultraportable 15-inch MacBook Air. With up to 18 hours of battery life and a stunning Liquid Retina display.", 1499.00, 1379.00, "APL-MBA15-M3", 12, 2, 1, 1, 4.8, 14),
            ("prd-apple-watch-ultra", "sel-nexus-tech", "cat-electronics", "br-apple", "Apple Watch Ultra 2 GPS + Cellular 49mm Titanium", "apple-watch-ultra-2", "The most rugged and capable Apple Watch. Powered by the S9 SiP. An exceptionally bright display. Precision dual-frequency GPS. Up to 36 hours of battery life.", 799.00, 749.00, "APL-WAT-ULT2", 8, 2, 1, 1, 4.9, 9),
            ("prd-sony-a7iv", "sel-nexus-tech", "cat-electronics", "br-sony", "Sony Alpha 7 IV Full-frame Mirrorless Interchangeable Lens Camera", "sony-alpha-7-iv", "33MP full-frame Exmor R back-illuminated CMOS sensor. 8x more powerful, next-gen BIONZ XR image processing engine. Up to 10fps continuous shooting.", 2499.00, 2299.00, "SNY-A7M4-BODY", 5, 1, 1, 1, 4.9, 6),
            ("prd-nike-air-max-plus", "sel-urban-weave", "cat-fashion", "br-nike", "Nike Air Max Plus Drift Performance Sneakers", "nike-air-max-plus-drift", "Give your attitude an edge in the Air Max Plus Drift. A flame-caged upper pairs with airy mesh, while Max Air units deliver tuned stability and unbelievable cushioning.", 185.00, 149.99, "NKE-AMP-DRIFT", 45, 5, 1, 1, 4.7, 26),
            ("prd-levis-vintage-jacket", "sel-urban-weave", "cat-fashion", "br-levis", "Levi's Vintage Trucker Denim Jacket - Heavy Stonewash", "levis-vintage-trucker-jacket", "A timeless silhouette crafted from 100% premium heavyweight cotton denim. Classic point collar, button placket, button-flap chest pockets and side welt pockets.", 128.00, 98.00, "LEV-TRK-JKT", 30, 4, 1, 1, 4.8, 19),
            ("prd-urban-wool-overcoat", "sel-urban-weave", "cat-fashion", None, "Urban Weave Minimalist Double-Breasted Wool Overcoat", "urban-weave-wool-overcoat", "Tailored from Italian recycled wool blend with peak lapels and structured shoulders. The epitome of modern refined outerwear for cooler seasons.", 295.00, 245.00, "URB-OVC-WHT", 15, 3, 1, 1, 4.9, 11),
            ("prd-dyson-v15-detect", "sel-nexus-tech", "cat-home", "br-dyson", "Dyson V15 Detect Cordless Vacuum Cleaner", "dyson-v15-detect-vacuum", "Dyson's most powerful, intelligent cordless vacuum. Laser reveals microscopic dust. Scientifically proves a deep clean on the LCD screen.", 749.99, 649.00, "DYS-V15-DET", 10, 2, 1, 1, 4.8, 15),
            ("prd-nike-dri-fit-hoodie", "sel-urban-weave", "cat-sports", "br-nike", "Nike Dri-FIT Tech Fleece Full-Zip Lightweight Hoodie", "nike-tech-fleece-hoodie", "Smooth on both sides, Tech Fleece delivers impressive warmth and an elevated look without adding excess weight or bulk.", 130.00, 110.00, "NKE-TF-HOOD", 50, 8, 1, 1, 4.6, 32),
            ("prd-ergonomic-desk-lamp", "sel-nexus-tech", "cat-home", None, "Aura Lumina Smart Ambient Desk Lamp with Wireless Charger", "aura-lumina-smart-lamp", "Full spectrum 98 CRI illumination with integrated 15W Qi fast wireless charging base, automated circadian sync, and touch dimming slider.", 89.00, 69.00, "AUR-LUM-LMP", 40, 6, 1, 1, 4.7, 14),
        ]
        cursor.executemany("""
        INSERT INTO products (id, seller_id, category_id, brand_id, title, slug, description, regular_price, sale_price, sku, stock_quantity, low_stock_threshold, is_approved, is_active, rating_avg, reviews_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, products)

        # Product Images
        images = [
            ("img-wh1-1", "prd-sony-wh1000xm5", "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=800&q=80", 1, 1),
            ("img-wh1-2", "prd-sony-wh1000xm5", "https://images.unsplash.com/photo-1484704849700-f032a568e944?auto=format&fit=crop&w=800&q=80", 0, 2),
            ("img-mba-1", "prd-apple-macbook-air", "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=800&q=80", 1, 1),
            ("img-wat-1", "prd-apple-watch-ultra", "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=800&q=80", 1, 1),
            ("img-a74-1", "prd-sony-a7iv", "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=800&q=80", 1, 1),
            ("img-nke-1", "prd-nike-air-max-plus", "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=80", 1, 1),
            ("img-lev-1", "prd-levis-vintage-jacket", "https://images.unsplash.com/photo-1576995853123-5a10305d93c0?auto=format&fit=crop&w=800&q=80", 1, 1),
            ("img-ovc-1", "prd-urban-wool-overcoat", "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?auto=format&fit=crop&w=800&q=80", 1, 1),
            ("img-dys-1", "prd-dyson-v15-detect", "https://images.unsplash.com/photo-1558317374-067fb5f30001?auto=format&fit=crop&w=800&q=80", 1, 1),
            ("img-tfh-1", "prd-nike-dri-fit-hoodie", "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?auto=format&fit=crop&w=800&q=80", 1, 1),
            ("img-lmp-1", "prd-ergonomic-desk-lamp", "https://images.unsplash.com/photo-1507473885765-e6ed057f782c?auto=format&fit=crop&w=800&q=80", 1, 1),
        ]
        cursor.executemany("""
        INSERT INTO product_images (id, product_id, image_url, is_primary, display_order)
        VALUES (?, ?, ?, ?, ?);
        """, images)

        # Product Variants (Color, Size, Finish)
        variants = [
            ("var-xm5-blk", "prd-sony-wh1000xm5", "SNY-XM5-BLK", "Black Edition", "Color", "Midnight Black", 348.00, 14),
            ("var-xm5-slv", "prd-sony-wh1000xm5", "SNY-XM5-SLV", "Platinum Silver", "Color", "Platinum Silver", 348.00, 10),
            ("var-nke-9", "prd-nike-air-max-plus", "NKE-AMP-09", "Size US 9.0", "Shoe Size", "US 9.0", 149.99, 15),
            ("var-nke-10", "prd-nike-air-max-plus", "NKE-AMP-10", "Size US 10.0", "Shoe Size", "US 10.0", 149.99, 20),
            ("var-nke-11", "prd-nike-air-max-plus", "NKE-AMP-11", "Size US 11.0", "Shoe Size", "US 11.0", 149.99, 10),
            ("var-lev-m", "prd-levis-vintage-jacket", "LEV-JKT-M", "Medium Size", "Size", "Medium (M)", 98.00, 12),
            ("var-lev-l", "prd-levis-vintage-jacket", "LEV-JKT-L", "Large Size", "Size", "Large (L)", 98.00, 18),
        ]
        cursor.executemany("""
        INSERT INTO product_variants (id, product_id, sku, title, attribute_name, attribute_value, price_override, stock_quantity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, variants)

        # Coupons
        coupons = [
            ("cpn-welcome", "WELCOME10", "percentage", 10.0, 50.0, 30.0, 500, 12, "2027-12-31 23:59:59", 1),
            ("cpn-bazaar", "BAZAAR50", "fixed", 50.0, 200.0, 50.0, 200, 5, "2027-12-31 23:59:59", 1),
        ]
        cursor.executemany("""
        INSERT INTO coupons (id, code, discount_type, discount_value, min_spend, max_discount, usage_limit, times_used, expires_at, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, coupons)

        # Sample Reviews
        sample_reviews = [
            ("rev-1", "prd-sony-wh1000xm5", "usr-customer-john", 5, "Unbelievable Noise Cancellation", "The best over-ear headphones I've ever owned. Battery life easily lasts my entire work week.", 1),
            ("rev-2", "prd-sony-wh1000xm5", "usr-customer-jane", 5, "Crystal Clear Calls", "Microphone quality on Zoom calls is crisp, and the earcups are super lightweight.", 1),
            ("rev-3", "prd-nike-air-max-plus", "usr-customer-john", 4, "Great comfort, true to size", "Stylish silhouette and very responsive sole support for all-day walking.", 1),
            ("rev-4", "prd-apple-macbook-air", "usr-customer-jane", 5, "The ultimate daily laptop", "M3 handles full-stack dev and multitasking with zero fan noise. Display is gorgeous.", 1),
        ]
        cursor.executemany("""
        INSERT INTO reviews (id, product_id, user_id, rating, title, comment, is_verified_purchase)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, sample_reviews)

        # Initial Completed Order for Demo analytics
        sample_address_json = json.dumps({
            "full_name": "Johnathan Doe",
            "phone": "+15551234567",
            "address_line1": "742 Evergreen Terrace",
            "city": "Springfield",
            "state": "OR",
            "postal_code": "97477",
            "country": "United States"
        })
        cursor.execute("""
        INSERT INTO orders (id, order_number, customer_id, shipping_address_json, subtotal, shipping_cost, tax_amount, discount_amount, total_amount, coupon_code, payment_method, payment_status, order_status, tracking_number)
        VALUES ('ord-demo-001', 'ORD-2026-9041', 'usr-customer-john', ?, 497.99, 0.0, 24.90, 49.80, 473.09, 'WELCOME10', 'stripe', 'paid', 'delivered', 'BZ-TRK-771100');
        """, (sample_address_json,))

        cursor.execute("""
        INSERT INTO seller_orders (id, order_id, seller_id, suborder_number, subtotal, shipping_cost, seller_earnings, platform_fee, status, tracking_number, carrier)
        VALUES ('subord-001-nexus', 'ord-demo-001', 'sel-nexus-tech', 'SUB-2026-9041-A', 348.00, 0.0, 313.20, 34.80, 'delivered', 'FEDEX-998811', 'FedEx Express');
        """)

        cursor.execute("""
        INSERT INTO seller_orders (id, order_id, seller_id, suborder_number, subtotal, shipping_cost, seller_earnings, platform_fee, status, tracking_number, carrier)
        VALUES ('subord-001-urban', 'ord-demo-001', 'sel-urban-weave', 'SUB-2026-9041-B', 149.99, 0.0, 131.99, 18.00, 'delivered', 'UPS-443322', 'UPS Ground');
        """)

        cursor.execute("""
        INSERT INTO order_items (id, seller_order_id, order_id, product_id, variant_id, product_title, variant_title, unit_price, quantity, total_price)
        VALUES ('item-001', 'subord-001-nexus', 'ord-demo-001', 'prd-sony-wh1000xm5', 'var-xm5-blk', 'Sony WH-1000XM5 Wireless Noise-Cancelling Headphones', 'Midnight Black', 348.00, 1, 348.00);
        """)

        cursor.execute("""
        INSERT INTO order_items (id, seller_order_id, order_id, product_id, variant_id, product_title, variant_title, unit_price, quantity, total_price)
        VALUES ('item-002', 'subord-001-urban', 'ord-demo-001', 'prd-nike-air-max-plus', 'var-nke-10', 'Nike Air Max Plus Drift Performance Sneakers', 'US 10.0', 149.99, 1, 149.99);
        """)

        cursor.execute("""
        INSERT INTO payments (id, order_id, provider, transaction_ref, amount, currency, status, idempotency_key)
        VALUES ('pay-001', 'ord-demo-001', 'stripe', 'ch_3N82hF2eZvKYlo2C194827', 473.09, 'USD', 'completed', 'idemp_ord_demo_001');
        """)

        print("Database schema created and populated successfully with multi-vendor fixtures.")
