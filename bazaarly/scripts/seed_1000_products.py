"""
Bazaarly 1,000 Products Category-Wise Seed Generator
Generates and populates 1,000 realistic, production-ready products distributed
across the 4 core categories (Electronics, Fashion, Home & Living, Sports & Fitness),
complete with primary images, realistic SKUs, inventory levels, ratings, and variants.
"""

import sys
import random
import sqlite3
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "bazaarly.db"

# High-resolution Unsplash images curated by category
IMAGES_BY_CATEGORY = {
    "cat-electronics": [
        "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1546868871-7041f2a55e12?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1583394838336-acd977736f90?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1572569511254-d8f925fe2cbb?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1512499617640-c74ae3a79d37?auto=format&fit=crop&w=600&q=80"
    ],
    "cat-fashion": [
        "https://images.unsplash.com/photo-1523381294911-8d3cead13475?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1551028719-00167b16eac5?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1576995853123-5a10305d93c0?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1509631179647-0177331693ae?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1434389677669-e08b4cac3105?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&w=600&q=80"
    ],
    "cat-home": [
        "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1558317374-067fb5f30001?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1583847268964-b28dc8f51f92?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1507473885765-e6ed057f782c?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1519710164239-da123dc03ef4?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1524758631624-e2822e304c36?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1517705008128-361805f42e86?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=600&q=80"
    ],
    "cat-sports": [
        "https://images.unsplash.com/photo-1517838277536-f5f99be501cd?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1584735935682-2f2b69dff9d2?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1518611012118-696072aa579a?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1526506118085-60ce8714f8c5?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1574680096145-d05b474e2155?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1598971861713-54ad16a7e72e?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1576678927484-cc907957088c?auto=format&fit=crop&w=600&q=80"
    ]
}

# Vocabulary for generating titles
ADJECTIVES = [
    "Ultra-Thin", "Pro Wireless", "Signature Series", "Ergonomic", "Titanium",
    "Precision", "Eco-Friendly", "Performance", "Studio Edition", "Acoustic",
    "Smart", "Compact", "Modular", "Heavy-Duty", "Seamless", "Aerodynamic",
    "Thermal", "Breathable", "Water-Resistant", "Next-Gen", "Carbon Fiber"
]

NOUNS_BY_CAT = {
    "cat-electronics": [
        "ANC Wireless Earbuds", "Mechanical RGB Keyboard", "OLED Portable Monitor", "Fast Charging Dock",
        "Noise-Isolating Headphones", "Smart Fitness Tracker", "Bluetooth Soundbar", "Studio USB Microphone",
        "High-Speed Hub Adapter", "Wireless Gaming Mouse", "Ultra HD Web Camera", "MagSafe Power Bank",
        "Smart Ambient Speaker", "Thunderbolt Docking Station", "Surround Sound DAC", "Wireless Trackpad"
    ],
    "cat-fashion": [
        "Heavyweight Cotton T-Shirt", "Slim-Fit Denim Jeans", "Waterproof Bomber Jacket", "Minimalist Canvas Sneakers",
        "Merino Wool Sweater", "Structured Cargo Trousers", "Cashmere Scarf", "Classic Leather Belt",
        "Windbreaker Shell Parka", "Tailored Linen Blazer", "Athletic Fleece Hoodie", "Chelsea Ankle Boots",
        "Vintage Denim Trucker", "Oversized Flannel Shirt", "Waterproof Commuter Trench", "Corduroy Overshirt"
    ],
    "cat-home": [
        "Memory Foam Office Chair", "Minimalist Oak Desk Lamp", "Ultrasonic Cool-Mist Humidifier", "Handcrafted Ceramic Mug Set",
        "Stainless Steel Electric Kettle", "Aroma Essential Oil Diffuser", "Bamboo Bedding Sheet Set", "Cast Iron Skillet Pan",
        "Modular Storage Bookcase", "Smart LED Lightstrip", "Ergonomic Laptop Stand", "Nordic Wool Throw Blanket",
        "Double-Wall Glass Tumbler", "Non-Stick Wok Cookware", "Air Purifier HEPA Filter", "Floating Walnut Wall Shelf"
    ],
    "cat-sports": [
        "Compression Running Tights", "Adjustable Dumbbell Set", "Non-Slip Yoga Exercise Mat", "Thermal Insulated Hydration Flask",
        "Cross-Training Grip Gloves", "Hydration Vest Backpack", "Speed Jump Rope with Bearings", "Deep Tissue Foam Roller",
        "Resistance Workout Bands", "Trail Running Trail Shoes", "Sweat-Wicking Muscle Tank", "Smart GPS Sport Watch",
        "Ankle Support Running Socks", "Boxing Training Wraps", "High-Impact Sports Bra", "Multi-Grip Pull-Up Bar"
    ]
}

BRANDS_BY_CAT = {
    "cat-electronics": [("br-sony", "Sony"), ("br-apple", "Apple"), ("br-samsung", "Samsung"), ("br-anker", "Anker"), ("br-logitech", "Logitech")],
    "cat-fashion": [("br-nike", "Nike"), ("br-levis", "Levi's"), ("br-zara", "Zara"), ("br-patagonia", "Patagonia"), ("br-urban", "Urban Weave")],
    "cat-home": [("br-dyson", "Dyson"), ("br-ikea", "IKEA"), ("br-kitchenaid", "KitchenAid"), ("br-philips", "Philips"), ("br-muji", "MUJI")],
    "cat-sports": [("br-nike", "Nike"), ("br-adidas", "Adidas"), ("br-under-armour", "Under Armour"), ("br-puma", "Puma"), ("br-garmin", "Garmin")]
}

SELLERS = ["sel-nexus-tech", "sel-urban-weave"]


def generate_and_insert():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Ensure Brands exist
    all_brands = [
        ("br-sony", "Sony", "sony", "https://images.unsplash.com/photo-1546868871-7041f2a55e12?auto=format&fit=crop&w=120&q=80"),
        ("br-apple", "Apple", "apple", "https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?auto=format&fit=crop&w=120&q=80"),
        ("br-nike", "Nike", "nike", "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=120&q=80"),
        ("br-levis", "Levi's", "levis", "https://images.unsplash.com/photo-1582552938357-32b906df40cb?auto=format&fit=crop&w=120&q=80"),
        ("br-dyson", "Dyson", "dyson", "https://images.unsplash.com/photo-1558317374-067fb5f30001?auto=format&fit=crop&w=120&q=80"),
        ("br-samsung", "Samsung", "samsung", "https://images.unsplash.com/photo-1610945265064-0e34e5519bbf?auto=format&fit=crop&w=120&q=80"),
        ("br-anker", "Anker", "anker", "https://images.unsplash.com/photo-1583394838336-acd977736f90?auto=format&fit=crop&w=120&q=80"),
        ("br-logitech", "Logitech", "logitech", "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?auto=format&fit=crop&w=120&q=80"),
        ("br-adidas", "Adidas", "adidas", "https://images.unsplash.com/photo-1518002171953-a080ee817e1f?auto=format&fit=crop&w=120&q=80"),
        ("br-under-armour", "Under Armour", "under-armour", "https://images.unsplash.com/photo-1517838277536-f5f99be501cd?auto=format&fit=crop&w=120&q=80"),
        ("br-ikea", "IKEA", "ikea", "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=120&q=80"),
        ("br-kitchenaid", "KitchenAid", "kitchenaid", "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?auto=format&fit=crop&w=120&q=80"),
        ("br-zara", "Zara", "zara", "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=120&q=80"),
        ("br-patagonia", "Patagonia", "patagonia", "https://images.unsplash.com/photo-1434389677669-e08b4cac3105?auto=format&fit=crop&w=120&q=80"),
        ("br-urban", "Urban Weave", "urban-weave", "https://images.unsplash.com/photo-1544441893-675973e31985?auto=format&fit=crop&w=120&q=80"),
        ("br-philips", "Philips", "philips", "https://images.unsplash.com/photo-1507473885765-e6ed057f782c?auto=format&fit=crop&w=120&q=80"),
        ("br-muji", "MUJI", "muji", "https://images.unsplash.com/photo-1519710164239-da123dc03ef4?auto=format&fit=crop&w=120&q=80"),
        ("br-puma", "Puma", "puma", "https://images.unsplash.com/photo-1584735935682-2f2b69dff9d2?auto=format&fit=crop&w=120&q=80"),
        ("br-garmin", "Garmin", "garmin", "https://images.unsplash.com/photo-1576678927484-cc907957088c?auto=format&fit=crop&w=120&q=80")
    ]
    cursor.executemany("INSERT OR IGNORE INTO brands (id, name, slug, logo_url) VALUES (?, ?, ?, ?);", all_brands)

    categories = ["cat-electronics", "cat-fashion", "cat-home", "cat-sports"]
    products_per_cat = 250  # 4 * 250 = 1000 products!

    print(f"Generating {len(categories) * products_per_cat} products category-wise...")

    product_rows = []
    image_rows = []
    variant_rows = []

    sku_counter = 1000

    for cat_id in categories:
        brand_list = BRANDS_BY_CAT[cat_id]
        noun_list = NOUNS_BY_CAT[cat_id]
        image_pool = IMAGES_BY_CATEGORY[cat_id]

        for i in range(1, products_per_cat + 1):
            sku_counter += 1
            prod_id = f"prd-gen-{cat_id[:5]}-{i:04d}"
            
            # Select attributes
            brand_id, brand_name = random.choice(brand_list)
            seller_id = "sel-nexus-tech" if cat_id in ["cat-electronics", "cat-home"] else "sel-urban-weave"
            
            adj = random.choice(ADJECTIVES)
            noun = random.choice(noun_list)
            model_num = f"{random.choice(['X', 'Pro', 'Max', 'Ultra', 'S', 'Plus'])}-{random.randint(10, 990)}"
            title = f"{brand_name} {adj} {noun} ({model_num})"
            slug = f"{brand_name.lower()}-{adj.lower()}-{noun.lower().replace(' ', '-')}-{sku_counter}"

            # Pricing
            base_price = round(random.uniform(25.0, 750.0), 2)
            has_discount = random.random() < 0.65
            discount_pct = random.choice([10, 15, 20, 25, 30, 40]) if has_discount else 0
            sale_price = round(base_price * (1.0 - (discount_pct / 100.0)), 2) if has_discount else base_price

            sku = f"BZ-{cat_id[4:6].upper()}-{sku_counter}"
            stock_qty = random.randint(8, 120)
            low_stock_threshold = random.randint(3, 8)
            rating_avg = round(random.uniform(4.2, 5.0), 1)
            reviews_count = random.randint(1, 45)

            desc = f"Engineered for high performance and durability. The {title} combines premium materials with ergonomic modern aesthetics. Includes official manufacturer warranty and guaranteed merchant direct dispatch."

            product_rows.append((
                prod_id, seller_id, cat_id, brand_id, title, slug, desc,
                base_price, sale_price, sku, stock_qty, low_stock_threshold,
                1, 1, rating_avg, reviews_count
            ))

            # Primary image
            img_url = random.choice(image_pool)
            image_rows.append((f"img-{prod_id}-0", prod_id, img_url, 1, 0))

            # Add variants for 40% of items (e.g. storage or size)
            if random.random() < 0.40:
                if cat_id == "cat-fashion":
                    sizes = ["Small", "Medium", "Large", "XL"]
                    for s_idx, s in enumerate(sizes):
                        variant_rows.append((
                            f"var-{prod_id}-{s_idx}",
                            prod_id,
                            f"{sku}-SZ-{s[0]}",
                            f"{title} - Size {s}",
                            "Size",
                            s,
                            sale_price,
                            random.randint(5, 30)
                        ))
                elif cat_id == "cat-electronics":
                    specs = ["128GB Storage", "256GB Storage", "512GB Storage"]
                    for sp_idx, sp in enumerate(specs):
                        variant_rows.append((
                            f"var-{prod_id}-{sp_idx}",
                            prod_id,
                            f"{sku}-SP-{sp[:3]}",
                            f"{title} ({sp})",
                            "Configuration",
                            sp,
                            round(sale_price + (sp_idx * 50.0), 2),
                            random.randint(4, 25)
                        ))
                elif cat_id in ["cat-home", "cat-sports"]:
                    colors = ["Matte Black", "Graphite Gray", "Alpine White"]
                    for c_idx, c in enumerate(colors):
                        variant_rows.append((
                            f"var-{prod_id}-{c_idx}",
                            prod_id,
                            f"{sku}-COL-{c[:3]}",
                            f"{title} - {c}",
                            "Color",
                            c,
                            sale_price,
                            random.randint(6, 20)
                        ))

    # Batch Insert
    print(f"Writing {len(product_rows)} products into SQLite...")
    cursor.executemany("""
    INSERT OR REPLACE INTO products (
        id, seller_id, category_id, brand_id, title, slug, description,
        regular_price, sale_price, sku, stock_quantity, low_stock_threshold,
        is_approved, is_active, rating_avg, reviews_count
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, product_rows)

    print(f"Writing {len(image_rows)} product images...")
    cursor.executemany("""
    INSERT OR REPLACE INTO product_images (id, product_id, image_url, is_primary, display_order)
    VALUES (?, ?, ?, ?, ?);
    """, image_rows)

    print(f"Writing {len(variant_rows)} product variants...")
    cursor.executemany("""
    INSERT OR REPLACE INTO product_variants (
        id, product_id, sku, title, attribute_name, attribute_value, price_override, stock_quantity
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, variant_rows)

    conn.commit()

    # Verify counts
    cursor.execute("SELECT category_id, COUNT(*) as cnt FROM products GROUP BY category_id;")
    cat_counts = cursor.fetchall()
    print("Category Breakdown:")
    for cat_id, cnt in cat_counts:
        print(f"  - {cat_id}: {cnt} items")

    cursor.execute("SELECT COUNT(*) as total FROM products;")
    total = cursor.fetchone()[0]
    print(f"\nTotal verified products in catalog: {total}")

    conn.close()


if __name__ == "__main__":
    generate_and_insert()
