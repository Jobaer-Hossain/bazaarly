"""
Bazaarly Multi-Vendor Order Placement & Fulfillment Routes
Atomic inventory reservation, transactional suborder splitting, and multi-gateway processing.
"""

import uuid
import json
import time
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from bazaarly.db.database import get_db_connection, query_db, execute_db
from bazaarly.core.security import get_current_user
from bazaarly.core.models import CheckoutOrderRequest, AddressRequest
from bazaarly.core.payments import PaymentGatewayManager
from bazaarly.core.inventory import InventoryManager

router = APIRouter(prefix="/api", tags=["Orders & Checkout"])


@router.get("/addresses")
def get_user_addresses(user: dict = Depends(get_current_user)):
    """Retrieves customer saved shipping addresses."""
    return query_db("SELECT * FROM addresses WHERE user_id = ? ORDER BY is_default DESC, created_at DESC;", (user["id"],))


@router.post("/addresses")
def save_new_address(req: AddressRequest, user: dict = Depends(get_current_user)):
    """Saves a new shipping address to the customer address book."""
    addr_id = f"addr-{uuid.uuid4().hex[:8]}"
    if req.is_default:
        execute_db("UPDATE addresses SET is_default = 0 WHERE user_id = ?;", (user["id"],))

    execute_db("""
    INSERT INTO addresses (id, user_id, full_name, phone, address_line1, address_line2, city, state, postal_code, country, is_default)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (addr_id, user["id"], req.full_name, req.phone, req.address_line1, req.address_line2, req.city, req.state, req.postal_code, req.country, 1 if req.is_default else 0))

    return query_db("SELECT * FROM addresses WHERE id = ?;", (addr_id,), one=True)


@router.post("/checkout")
def process_checkout(req: CheckoutOrderRequest, user: dict = Depends(get_current_user)):
    """
    Executes the complete multi-vendor transactional order workflow:
    1. Validate and resolve shipping address.
    2. Recalculate cart items, pricing, discounts, and taxes on server.
    3. Atomically verify and deduct inventory for each vendor item.
    4. Create parent Order record.
    5. Split items by vendor and create isolated Seller Suborders with commission calculation.
    6. Process payment via the requested gateway (COD, Stripe, SSLCommerz, Bank Transfer).
    7. Clear customer cart.
    """
    # 1. Resolve Shipping Address
    shipping_address = None
    resolved_new_addr = req.new_shipping_address or req.shipping_address
    if req.shipping_address_id:
        addr = query_db("SELECT * FROM addresses WHERE id = ? AND user_id = ?;", (req.shipping_address_id, user["id"]), one=True)
        if addr:
            shipping_address = dict(addr)
    elif resolved_new_addr:
        new_addr_id = f"addr-{uuid.uuid4().hex[:8]}"
        execute_db("""
        INSERT INTO addresses (id, user_id, full_name, phone, address_line1, address_line2, city, state, postal_code, country, is_default)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
        """, (new_addr_id, user["id"], resolved_new_addr.full_name, resolved_new_addr.phone,
              resolved_new_addr.address_line1, resolved_new_addr.address_line2,
              resolved_new_addr.city, resolved_new_addr.state,
              resolved_new_addr.postal_code, resolved_new_addr.country))
        shipping_address = resolved_new_addr.model_dump()

    if not shipping_address:
        # Fallback to default address
        default_addr = query_db("SELECT * FROM addresses WHERE user_id = ? ORDER BY is_default DESC LIMIT 1;", (user["id"],), one=True)
        if default_addr:
            shipping_address = dict(default_addr)
        else:
            raise HTTPException(status_code=400, detail="Shipping address is required to proceed with checkout.")

    # 2. Retrieve Cart Items
    cart = query_db("SELECT id FROM carts WHERE user_id = ?;", (user["id"],), one=True)
    if not cart:
        raise HTTPException(status_code=400, detail="Your shopping cart is empty.")

    cart_items = query_db("""
    SELECT 
        ci.id as item_id,
        ci.quantity,
        ci.variant_id,
        ci.product_id,
        p.title as product_title,
        p.sale_price as base_sale_price,
        p.seller_id,
        s.commission_rate,
        s.store_name,
        pv.title as variant_title,
        pv.price_override
    FROM cart_items ci
    JOIN products p ON ci.product_id = p.id
    JOIN seller_profiles s ON p.seller_id = s.id
    LEFT JOIN product_variants pv ON ci.variant_id = pv.id
    WHERE ci.cart_id = ?;
    """, (cart["id"],))

    if not cart_items:
        raise HTTPException(status_code=400, detail="No products found in your cart.")

    # 3. Calculate server totals and group by seller
    seller_groups: Dict[str, List[Dict[str, Any]]] = {}
    subtotal = 0.0

    for item in cart_items:
        unit_price = item["price_override"] if item["price_override"] is not None else item["base_sale_price"]
        item_total = round(unit_price * item["quantity"], 2)
        subtotal += item_total

        seller_id = item["seller_id"]
        if seller_id not in seller_groups:
            seller_groups[seller_id] = {
                "commission_rate": item["commission_rate"] or 10.0,
                "store_name": item["store_name"],
                "items": [],
                "subtotal": 0.0
            }
        seller_groups[seller_id]["items"].append({
            "product_id": item["product_id"],
            "variant_id": item["variant_id"],
            "product_title": item["product_title"],
            "variant_title": item["variant_title"],
            "unit_price": unit_price,
            "quantity": item["quantity"],
            "total_price": item_total
        })
        seller_groups[seller_id]["subtotal"] += item_total

    # Tax & Shipping
    tax_amount = round(subtotal * 0.05, 2)
    shipping_cost = 5.00 if (subtotal < 100.00 and subtotal > 0) else 0.00

    # Coupon Discount
    discount_amount = 0.0
    if req.coupon_code:
        cpn = query_db("""
        SELECT * FROM coupons 
        WHERE code = ? AND is_active = 1 AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP);
        """, (req.coupon_code.strip().upper(),), one=True)
        if cpn and subtotal >= cpn["min_spend"]:
            if cpn["discount_type"] == "percentage":
                discount_amount = round((subtotal * cpn["discount_value"]) / 100.0, 2)
                if cpn["max_discount"]:
                    discount_amount = min(discount_amount, cpn["max_discount"])
            else:
                discount_amount = min(cpn["discount_value"], subtotal)
            execute_db("UPDATE coupons SET times_used = times_used + 1 WHERE id = ?;", (cpn["id"],))

    grand_total = max(0.0, round(subtotal + tax_amount + shipping_cost - discount_amount, 2))

    # 4. Transactional Order Creation with Atomic Stock Deduction
    order_id = f"ord-{uuid.uuid4().hex[:8]}"
    order_number = f"ORD-{int(time.time())}-{uuid.uuid4().hex[:4].upper()}"
    tracking_number = f"BZ-TRK-{uuid.uuid4().hex[:8].upper()}"

    with get_db_connection() as conn:
        # Atomic stock check and deduction
        InventoryManager.validate_and_deduct_stock(cart_items, conn)

        cursor = conn.cursor()
        # Insert Parent Order
        cursor.execute("""
        INSERT INTO orders (id, order_number, customer_id, shipping_address_json, subtotal, shipping_cost, tax_amount, discount_amount, total_amount, coupon_code, payment_method, payment_status, order_status, tracking_number, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'confirmed', ?, ?);
        """, (order_id, order_number, user["id"], json.dumps(shipping_address), subtotal, shipping_cost, tax_amount, discount_amount, grand_total, req.coupon_code, req.payment_method, tracking_number, req.order_notes or ""))

        # Insert Seller Suborders & Order Items
        suborder_idx = 1
        for s_id, s_data in seller_groups.items():
            sub_id = f"subord-{uuid.uuid4().hex[:8]}"
            sub_num = f"{order_number}-{chr(64 + suborder_idx)}"
            suborder_idx += 1

            sub_subtotal = s_data["subtotal"]
            platform_fee = round((sub_subtotal * s_data["commission_rate"]) / 100.0, 2)
            seller_earnings = round(sub_subtotal - platform_fee, 2)

            cursor.execute("""
            INSERT INTO seller_orders (id, order_id, seller_id, suborder_number, subtotal, seller_earnings, platform_fee, status, tracking_number, carrier)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, 'Standard Courier');
            """, (sub_id, order_id, s_id, sub_num, sub_subtotal, seller_earnings, platform_fee, f"TRK-{uuid.uuid4().hex[:6].upper()}"))

            # Items for this seller
            for it in s_data["items"]:
                it_id = f"item-{uuid.uuid4().hex[:8]}"
                cursor.execute("""
                INSERT INTO order_items (id, seller_order_id, order_id, product_id, variant_id, product_title, variant_title, unit_price, quantity, total_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (it_id, sub_id, order_id, it["product_id"], it["variant_id"], it["product_title"], it["variant_title"], it["unit_price"], it["quantity"], it["total_price"]))

            # Update seller total sales
            cursor.execute("UPDATE seller_profiles SET total_sales = total_sales + ? WHERE id = ?;", (seller_earnings, s_id))

        # Clear cart
        cursor.execute("DELETE FROM cart_items WHERE cart_id = ?;", (cart["id"],))

    # 5. Process Payment via Gateway Provider
    payment_res = PaymentGatewayManager.process_payment(
        order_id=order_id,
        method=req.payment_method,
        amount=grand_total
    )

    return {
        "success": True,
        "order_id": order_id,
        "order_number": order_number,
        "tracking_number": tracking_number,
        "grand_total": grand_total,
        "payment": payment_res,
        "shipping_address": shipping_address,
        "message": "Order created and confirmed successfully."
    }


@router.get("/orders")
def get_customer_orders(user: dict = Depends(get_current_user)):
    """Retrieves order history for the authenticated customer."""
    orders = query_db("""
    SELECT o.*,
           (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as total_items
    FROM orders o
    WHERE o.customer_id = ?
    ORDER BY o.created_at DESC;
    """, (user["id"],))

    for o in orders:
        o["shipping_address"] = json.loads(o["shipping_address_json"])
        o["suborders"] = query_db("""
        SELECT so.*, sp.store_name
        FROM seller_orders so
        JOIN seller_profiles sp ON so.seller_id = sp.id
        WHERE so.order_id = ?;
        """, (o["id"],))

    return orders


@router.get("/orders/{order_id}")
def get_order_details(order_id: str, user: dict = Depends(get_current_user)):
    """Returns full order details including line items, suborders, and tracking timeline."""
    order = query_db("""
    SELECT o.*, u.full_name as customer_name, u.email as customer_email
    FROM orders o
    JOIN users u ON o.customer_id = u.id
    WHERE o.id = ? OR o.order_number = ?;
    """, (order_id, order_id), one=True)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    # Authorization check: only customer owner, associated sellers, or admin can view
    if user["role"] == "customer" and order["customer_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized access to order.")

    order["shipping_address"] = json.loads(order["shipping_address_json"])
    order["items"] = query_db("""
    SELECT oi.*, p.slug as product_slug,
           (SELECT image_url FROM product_images WHERE product_id = oi.product_id AND is_primary = 1 LIMIT 1) as primary_image
    FROM order_items oi
    JOIN products p ON oi.product_id = p.id
    WHERE oi.order_id = ?;
    """, (order["id"],))

    order["suborders"] = query_db("""
    SELECT so.*, sp.store_name, sp.slug as store_slug
    FROM seller_orders so
    JOIN seller_profiles sp ON so.seller_id = sp.id
    WHERE so.order_id = ?;
    """, (order["id"],))

    order["payment"] = query_db("SELECT * FROM payments WHERE order_id = ? ORDER BY created_at DESC LIMIT 1;", (order["id"],), one=True)

    return order


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, user: dict = Depends(get_current_user)):
    """Cancels eligible orders and automatically replenishes inventory."""
    order = query_db("SELECT * FROM orders WHERE id = ?;", (order_id,), one=True)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    if user["role"] == "customer" and order["customer_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized.")

    if order["order_status"] in ["shipped", "delivered", "cancelled"]:
        raise HTTPException(status_code=400, detail=f"Order cannot be cancelled in '{order['order_status']}' status.")

    execute_db("UPDATE orders SET order_status = 'cancelled' WHERE id = ?;", (order_id,))
    execute_db("UPDATE seller_orders SET status = 'cancelled' WHERE order_id = ?;", (order_id,))

    # Replenish stock
    InventoryManager.restore_stock_for_order(order_id)

    # If paid, refund
    if order["payment_status"] == "paid":
        PaymentGatewayManager.process_refund(order_id, reason="Customer cancelled before dispatch")

    return {"success": True, "message": "Order cancelled and inventory restored."}
