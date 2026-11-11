"""
Bazaarly Product Catalog & Customer Review Routes
"""

import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from bazaarly.db.database import query_db, execute_db
from bazaarly.core.security import get_current_user, get_current_user_optional
from bazaarly.core.models import ReviewCreateRequest

router = APIRouter(prefix="/api", tags=["Catalog"])


@router.get("/categories")
@router.get("/catalog/categories")
def get_categories():
    """Returns active product categories."""
    return query_db("SELECT * FROM categories WHERE is_active = 1 ORDER BY display_order ASC;")


@router.get("/brands")
@router.get("/catalog/brands")
def get_brands():
    """Returns active brands."""
    return query_db("SELECT * FROM brands WHERE is_active = 1 ORDER BY name ASC;")


@router.get("/products")
@router.get("/catalog/products")
def list_products(
    q: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    category_slug: Optional[str] = None,
    brand: Optional[str] = None,
    seller_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock_only: bool = False,
    in_stock: Optional[bool] = None,
    sort: str = "featured",
    limit: int = 50,
    offset: int = 0
):
    """
    Searches, filters, and sorts approved active products.
    """
    query_term = search if search is not None else q
    category_filter = category_slug if category_slug is not None else category
    stock_filter = in_stock if in_stock is not None else in_stock_only

    conditions = ["p.is_approved = 1", "p.is_active = 1"]
    args = []

    if query_term and query_term.strip():
        term = f"%{query_term.strip()}%"
        conditions.append("(p.title LIKE ? OR p.description LIKE ? OR p.sku LIKE ?)")
        args.extend([term, term, term])

    if category_filter:
        conditions.append("(c.slug = ? OR c.id = ?)")
        args.extend([category_filter, category_filter])

    if brand:
        conditions.append("(b.slug = ? OR b.id = ?)")
        args.extend([brand, brand])

    if seller_id:
        conditions.append("p.seller_id = ?")
        args.append(seller_id)

    if min_price is not None:
        conditions.append("p.sale_price >= ?")
        args.append(min_price)

    if max_price is not None:
        conditions.append("p.sale_price <= ?")
        args.append(max_price)

    if stock_filter:
        conditions.append("p.stock_quantity > 0")

    where_clause = " WHERE " + " AND ".join(conditions)

    # Sorting
    sort_sql = "p.created_at DESC"
    if sort == "price_asc":
        sort_sql = "p.sale_price ASC"
    elif sort == "price_desc":
        sort_sql = "p.sale_price DESC"
    elif sort == "rating_desc":
        sort_sql = "p.rating_avg DESC"
    elif sort == "title_asc":
        sort_sql = "p.title ASC"

    sql = f"""
    SELECT 
        p.*,
        c.name as category_name,
        c.slug as category_slug,
        b.name as brand_name,
        s.store_name,
        s.slug as seller_slug,
        s.rating_avg as seller_rating,
        (SELECT image_url FROM product_images WHERE product_id = p.id AND is_primary = 1 LIMIT 1) as primary_image
    FROM products p
    JOIN categories c ON p.category_id = c.id
    LEFT JOIN brands b ON p.brand_id = b.id
    JOIN seller_profiles s ON p.seller_id = s.id
    {where_clause}
    ORDER BY {sort_sql}
    LIMIT ? OFFSET ?;
    """
    args.extend([limit, offset])

    items = query_db(sql, tuple(args))
    
    # Calculate discount percentage
    for item in items:
        if item["regular_price"] > item["sale_price"]:
            item["discount_percent"] = round(((item["regular_price"] - item["sale_price"]) / item["regular_price"]) * 100)
        else:
            item["discount_percent"] = 0

    return items


@router.get("/products/{product_id}")
@router.get("/catalog/products/{product_id}")
def get_product_details(product_id: str):
    """Returns complete product profile with image gallery, variants, and seller info."""
    product = query_db("""
    SELECT 
        p.*,
        c.name as category_name,
        c.slug as category_slug,
        b.name as brand_name,
        s.store_name,
        s.slug as seller_slug,
        s.logo_url as seller_logo,
        s.rating_avg as seller_rating,
        s.address as seller_address
    FROM products p
    JOIN categories c ON p.category_id = c.id
    LEFT JOIN brands b ON p.brand_id = b.id
    JOIN seller_profiles s ON p.seller_id = s.id
    WHERE (p.id = ? OR p.slug = ?) AND p.is_approved = 1 AND p.is_active = 1;
    """, (product_id, product_id), one=True)

    if not product:
        raise HTTPException(status_code=404, detail="Product not found or currently unavailable.")

    # Attached images
    images = query_db("""
    SELECT id, image_url, is_primary, display_order 
    FROM product_images 
    WHERE product_id = ? 
    ORDER BY is_primary DESC, display_order ASC;
    """, (product["id"],))

    # Attached variants
    variants = query_db("""
    SELECT id, sku, title, attribute_name, attribute_value, price_override, stock_quantity
    FROM product_variants
    WHERE product_id = ?
    ORDER BY title ASC;
    """, (product["id"],))

    # Recent reviews
    reviews = query_db("""
    SELECT r.*, u.full_name as author_name
    FROM reviews r
    JOIN users u ON r.user_id = u.id
    WHERE r.product_id = ?
    ORDER BY r.created_at DESC;
    """, (product["id"],))

    product["images"] = images
    product["variants"] = variants
    product["reviews"] = reviews
    product["discount_percent"] = round(((product["regular_price"] - product["sale_price"]) / product["regular_price"]) * 100) if product["regular_price"] > product["sale_price"] else 0

    # Related items in same category
    related = query_db("""
    SELECT p.id, p.title, p.slug, p.sale_price, p.regular_price, p.rating_avg,
           (SELECT image_url FROM product_images WHERE product_id = p.id AND is_primary = 1 LIMIT 1) as primary_image
    FROM products p
    WHERE p.category_id = ? AND p.id != ? AND p.is_approved = 1 AND p.is_active = 1
    LIMIT 4;
    """, (product["category_id"], product["id"]))
    product["related_products"] = related

    return product


@router.post("/reviews")
@router.post("/products/{product_id}/reviews")
@router.post("/catalog/products/{product_id}/reviews")
def create_product_review(req: ReviewCreateRequest, product_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Allows authenticated customers to review a product."""
    target_product_id = product_id or req.product_id
    product = query_db("SELECT id, title FROM products WHERE id = ?;", (target_product_id,), one=True)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    rev_id = f"rev-{uuid.uuid4().hex[:8]}"
    execute_db("""
    INSERT INTO reviews (id, product_id, user_id, rating, title, comment, is_verified_purchase)
    VALUES (?, ?, ?, ?, ?, ?, 1);
    """, (rev_id, target_product_id, user["id"], req.rating, req.title, req.comment))

    # Recalculate average rating & reviews count
    stats = query_db("""
    SELECT AVG(rating) as avg_rating, COUNT(*) as cnt
    FROM reviews
    WHERE product_id = ?;
    """, (target_product_id,), one=True)

    execute_db("""
    UPDATE products
    SET rating_avg = ROUND(?, 1), reviews_count = ?
    WHERE id = ?;
    """, (stats["avg_rating"], stats["cnt"], target_product_id))

    return {"success": True, "message": "Review submitted successfully.", "review_id": rev_id}
