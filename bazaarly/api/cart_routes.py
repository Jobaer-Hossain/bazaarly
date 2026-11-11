"""
Bazaarly Shopping Cart & Wishlist API Routes
Server-side price recalculation and atomic stock checks. Never trusts client totals.
"""

import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Header
from bazaarly.db.database import query_db, execute_db, get_db_connection
from bazaarly.core.security import get_current_user_optional, get_current_user
from bazaarly.core.models import CartItemAddRequest, CartItemUpdateRequest, ApplyCouponRequest

router = APIRouter(prefix="/api", tags=["Shopping Cart"])


def get_or_create_cart(user: Optional[dict], session_id: Optional[str]) -> str:
    """Finds or creates a cart ID based on user_id or guest session_id."""
    cart_id = None
    if user:
        cart = query_db("SELECT id FROM carts WHERE user_id = ?;", (user["id"],), one=True)
        if cart:
            return cart["id"]
        # If guest session had items, claim it
        if session_id:
            guest_cart = query_db("SELECT id FROM carts WHERE session_id = ? AND user_id IS NULL;", (session_id,), one=True)
            if guest_cart:
                execute_db("UPDATE carts SET user_id = ?, session_id = NULL WHERE id = ?;", (user["id"], guest_cart["id"]))
                return guest_cart["id"]
        cart_id = f"crt-{uuid.uuid4().hex[:8]}"
        execute_db("INSERT INTO carts (id, user_id) VALUES (?, ?);", (cart_id, user["id"]))
        return cart_id
    else:
        s_id = session_id or f"guest-{uuid.uuid4().hex[:12]}"
        cart = query_db("SELECT id FROM carts WHERE session_id = ?;", (s_id,), one=True)
        if cart:
            return cart["id"]
        cart_id = f"crt-{uuid.uuid4().hex[:8]}"
        execute_db("INSERT INTO carts (id, session_id) VALUES (?, ?);", (cart_id, s_id))
        return cart_id


@router.get("/cart")
def get_cart_contents(
    session_id: Optional[str] = None,
    coupon: Optional[str] = None,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Returns verified cart items with live stock status and recalculated server-side totals.
    """
    cart_id = get_or_create_cart(user, session_id)

    raw_items = query_db("""
    SELECT 
        ci.id as item_id,
        ci.quantity,
        p.id as product_id,
        p.title as product_title,
        p.sale_price as base_sale_price,
        p.stock_quantity as product_stock,
        p.sku as product_sku,
        s.id as seller_id,
        s.store_name,
        pv.id as variant_id,
        pv.title as variant_title,
        pv.attribute_name,
        pv.attribute_value,
        pv.price_override,
        pv.stock_quantity as variant_stock,
        (SELECT image_url FROM product_images WHERE product_id = p.id AND is_primary = 1 LIMIT 1) as primary_image
    FROM cart_items ci
    JOIN products p ON ci.product_id = p.id
    JOIN seller_profiles s ON p.seller_id = s.id
    LEFT JOIN product_variants pv ON ci.variant_id = pv.id
    WHERE ci.cart_id = ?;
    """, (cart_id,))

    items = []
    subtotal = 0.0

    for r in raw_items:
        # Use variant price if overridden, otherwise base sale price
        effective_unit_price = r["price_override"] if r["price_override"] is not None else r["base_sale_price"]
        available_stock = r["variant_stock"] if r["variant_id"] else r["product_stock"]
        item_total = round(effective_unit_price * r["quantity"], 2)
        subtotal += item_total

        items.append({
            "item_id": r["item_id"],
            "product_id": r["product_id"],
            "product_title": r["product_title"],
            "variant_id": r["variant_id"],
            "variant_title": r["variant_title"],
            "attribute_name": r["attribute_name"],
            "attribute_value": r["attribute_value"],
            "seller_id": r["seller_id"],
            "store_name": r["store_name"],
            "unit_price": effective_unit_price,
            "quantity": r["quantity"],
            "total_price": item_total,
            "available_stock": available_stock,
            "is_out_of_stock": available_stock < r["quantity"],
            "primary_image": r["primary_image"]
        })

    # Calculations
    tax_rate = 0.05  # 5% tax
    tax_amount = round(subtotal * tax_rate, 2)
    shipping_rate = 5.00 if (subtotal < 100.00 and subtotal > 0) else 0.00

    # Coupon validation
    discount_amount = 0.0
    applied_coupon = None
    if coupon and coupon.strip():
        cpn = query_db("""
        SELECT * FROM coupons 
        WHERE code = ? AND is_active = 1 AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP);
        """, (coupon.strip().upper(),), one=True)

        if cpn and subtotal >= cpn["min_spend"]:
            if cpn["discount_type"] == "percentage":
                discount_amount = round((subtotal * cpn["discount_value"]) / 100.0, 2)
                if cpn["max_discount"]:
                    discount_amount = min(discount_amount, cpn["max_discount"])
            else:
                discount_amount = min(cpn["discount_value"], subtotal)
            applied_coupon = {
                "code": cpn["code"],
                "discount_type": cpn["discount_type"],
                "discount_value": cpn["discount_value"],
                "savings": discount_amount
            }

    grand_total = max(0.0, round(subtotal + tax_amount + shipping_rate - discount_amount, 2))

    return {
        "cart_id": cart_id,
        "items": items,
        "items_count": sum(i["quantity"] for i in items),
        "subtotal": round(subtotal, 2),
        "tax_amount": tax_amount,
        "shipping_cost": shipping_rate,
        "discount_amount": discount_amount,
        "applied_coupon": applied_coupon,
        "grand_total": grand_total
    }


@router.post("/cart/coupon")
def apply_cart_coupon(
    req: ApplyCouponRequest,
    session_id: Optional[str] = None,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    """Validates coupon and returns updated calculation."""
    code = req.coupon_string
    if not code:
        raise HTTPException(status_code=400, detail="Coupon code is required.")
    cpn = query_db("""
    SELECT * FROM coupons 
    WHERE code = ? AND is_active = 1 AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP);
    """, (code,), one=True)
    if not cpn:
        raise HTTPException(status_code=400, detail="Coupon code is invalid or has expired.")

    # Return full recalculated cart with this coupon
    return get_cart_contents(session_id=session_id, coupon=code, user=user)


@router.post("/cart/items")
def add_item_to_cart(
    req: CartItemAddRequest,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    """Adds a product or variant to the cart with stock verification."""
    cart_id = get_or_create_cart(user, req.session_id)

    # Validate stock
    if req.variant_id:
        variant = query_db("SELECT id, title, stock_quantity FROM product_variants WHERE id = ?;", (req.variant_id,), one=True)
        if not variant:
            raise HTTPException(status_code=404, detail="Product variant not found.")
        if variant["stock_quantity"] < req.quantity:
            raise HTTPException(status_code=400, detail=f"Only {variant['stock_quantity']} units available in stock.")
    else:
        product = query_db("SELECT id, title, stock_quantity FROM products WHERE id = ?;", (req.product_id,), one=True)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found.")
        if product["stock_quantity"] < req.quantity:
            raise HTTPException(status_code=400, detail=f"Only {product['stock_quantity']} units available in stock.")

    # Check if item is already in cart
    existing = query_db("""
    SELECT id, quantity FROM cart_items 
    WHERE cart_id = ? AND product_id = ? AND (variant_id = ? OR (variant_id IS NULL AND ? IS NULL));
    """, (cart_id, req.product_id, req.variant_id, req.variant_id), one=True)

    if existing:
        new_qty = existing["quantity"] + req.quantity
        execute_db("UPDATE cart_items SET quantity = ? WHERE id = ?;", (new_qty, existing["id"]))
    else:
        item_id = f"ci-{uuid.uuid4().hex[:8]}"
        execute_db("""
        INSERT INTO cart_items (id, cart_id, product_id, variant_id, quantity)
        VALUES (?, ?, ?, ?, ?);
        """, (item_id, cart_id, req.product_id, req.variant_id, req.quantity))

    return {"success": True, "message": "Item added to cart successfully."}


@router.put("/cart/items/{item_id}")
def update_cart_item_quantity(
    item_id: str,
    req: CartItemUpdateRequest,
    session_id: Optional[str] = None,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    """Updates quantity of an existing cart item after verifying available stock."""
    item = query_db("SELECT * FROM cart_items WHERE id = ?;", (item_id,), one=True)
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found.")

    # Validate stock
    if item["variant_id"]:
        variant = query_db("SELECT stock_quantity FROM product_variants WHERE id = ?;", (item["variant_id"],), one=True)
        if variant and variant["stock_quantity"] < req.quantity:
            raise HTTPException(status_code=400, detail=f"Only {variant['stock_quantity']} units available.")
    else:
        product = query_db("SELECT stock_quantity FROM products WHERE id = ?;", (item["product_id"],), one=True)
        if product and product["stock_quantity"] < req.quantity:
            raise HTTPException(status_code=400, detail=f"Only {product['stock_quantity']} units available.")

    execute_db("UPDATE cart_items SET quantity = ? WHERE id = ?;", (req.quantity, item_id))
    return {"success": True, "message": "Cart updated."}


@router.delete("/cart/items/{item_id}")
def remove_cart_item(item_id: str):
    """Removes a single item from the cart."""
    execute_db("DELETE FROM cart_items WHERE id = ?;", (item_id,))
    return {"success": True, "message": "Item removed from cart."}


@router.delete("/cart")
def clear_cart(
    session_id: Optional[str] = None,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    """Clears all items in current user or session cart."""
    cart_id = get_or_create_cart(user, session_id)
    execute_db("DELETE FROM cart_items WHERE cart_id = ?;", (cart_id,))
    return {"success": True, "message": "Cart cleared."}


# Wishlist Endpoints
@router.get("/wishlist")
def get_user_wishlist(user: dict = Depends(get_current_user)):
    """Retrieves authenticated customer wishlist items."""
    return query_db("""
    SELECT 
        w.id as wishlist_id,
        w.created_at as saved_at,
        p.*,
        (SELECT image_url FROM product_images WHERE product_id = p.id AND is_primary = 1 LIMIT 1) as primary_image
    FROM wishlists w
    JOIN products p ON w.product_id = p.id
    WHERE w.user_id = ?
    ORDER BY w.created_at DESC;
    """, (user["id"],))


@router.post("/wishlist/{product_id}")
def toggle_wishlist_product(product_id: str, user: dict = Depends(get_current_user)):
    """Toggles product in/out of customer's wishlist."""
    existing = query_db("SELECT id FROM wishlists WHERE user_id = ? AND product_id = ?;", (user["id"], product_id), one=True)
    if existing:
        execute_db("DELETE FROM wishlists WHERE id = ?;", (existing["id"],))
        return {"saved": False, "message": "Removed from wishlist."}
    else:
        w_id = f"wsh-{uuid.uuid4().hex[:8]}"
        execute_db("INSERT INTO wishlists (id, user_id, product_id) VALUES (?, ?, ?);", (w_id, user["id"], product_id))
        return {"saved": True, "message": "Saved to wishlist."}
