"""
Bazaarly Admin Portal API Routes
Operational management: seller verification, product approvals, order disputes, and financial reporting.
"""

import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from bazaarly.db.database import query_db, execute_db
from bazaarly.core.security import require_roles
from bazaarly.core.models import SellerApprovalRequest, ProductApprovalRequest
from bazaarly.core.payments import PaymentGatewayManager

router = APIRouter(prefix="/api/admin", tags=["Admin Portal"])


@router.get("/dashboard")
def get_admin_dashboard(user: dict = Depends(require_roles(["admin", "super_admin"]))):
    """Returns platform-wide operational KPIs and revenue analytics."""
    # 1. Total Metrics
    totals = query_db("""
    SELECT 
        COALESCE(SUM(total_amount), 0) as gross_merchandise_value,
        COALESCE(SUM(platform_fee), 0) as platform_commission_revenue,
        (SELECT COUNT(*) FROM orders) as total_orders,
        (SELECT COUNT(*) FROM users WHERE role = 'customer') as total_customers,
        (SELECT COUNT(*) FROM seller_profiles WHERE approval_status = 'approved') as active_sellers,
        (SELECT COUNT(*) FROM seller_profiles WHERE approval_status = 'pending') as pending_seller_approvals,
        (SELECT COUNT(*) FROM products WHERE is_approved = 0) as pending_product_approvals
    FROM orders o
    LEFT JOIN (SELECT order_id, SUM(platform_fee) as platform_fee FROM seller_orders GROUP BY order_id) so ON o.id = so.order_id
    WHERE o.order_status != 'cancelled';
    """, one=True)

    # 2. Recent Platform Transactions
    recent_orders = query_db("""
    SELECT o.id, o.order_number, o.total_amount, o.payment_method, o.payment_status, o.order_status, o.created_at,
           u.full_name as customer_name, u.email as customer_email
    FROM orders o
    JOIN users u ON o.customer_id = u.id
    ORDER BY o.created_at DESC
    LIMIT 6;
    """)

    # 3. Pending Sellers
    pending_sellers = query_db("""
    SELECT sp.*, u.email as user_email, u.full_name as contact_name
    FROM seller_profiles sp
    JOIN users u ON sp.user_id = u.id
    WHERE sp.approval_status = 'pending'
    ORDER BY sp.created_at ASC;
    """)

    # 4. Top Performing Sellers
    top_sellers = query_db("""
    SELECT sp.id, sp.store_name, sp.rating_avg, sp.commission_rate,
           COALESCE(SUM(so.subtotal), 0) as gross_volume,
           COALESCE(SUM(so.platform_fee), 0) as earned_fees
    FROM seller_profiles sp
    LEFT JOIN seller_orders so ON sp.id = so.seller_id AND so.status != 'cancelled'
    WHERE sp.approval_status = 'approved'
    GROUP BY sp.id
    ORDER BY gross_volume DESC
    LIMIT 5;
    """)

    return {
        "kpis": totals,
        "recent_orders": recent_orders,
        "pending_sellers": pending_sellers,
        "top_sellers": top_sellers
    }


@router.get("/sellers")
def list_all_sellers(user: dict = Depends(require_roles(["admin", "super_admin"]))):
    """Retrieves all seller applicants and active vendor stores."""
    return query_db("""
    SELECT sp.*, u.email as user_email, u.full_name as contact_person, u.phone as contact_phone
    FROM seller_profiles sp
    JOIN users u ON sp.user_id = u.id
    ORDER BY sp.created_at DESC;
    """)


@router.put("/sellers/{seller_id}/approval")
def update_seller_approval(seller_id: str, req: SellerApprovalRequest, user: dict = Depends(require_roles(["admin", "super_admin"]))):
    """Approves or rejects a vendor application and sets custom commission rate."""
    seller = query_db("SELECT * FROM seller_profiles WHERE id = ?;", (seller_id,), one=True)
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found.")

    execute_db("""
    UPDATE seller_profiles 
    SET approval_status = ?, commission_rate = COALESCE(?, commission_rate)
    WHERE id = ?;
    """, (req.approval_status, req.commission_rate, seller_id))

    return {"success": True, "message": f"Seller application marked as {req.approval_status}."}


@router.get("/customers")
def list_customers(user: dict = Depends(require_roles(["admin", "super_admin"]))):
    """Lists registered customer accounts with aggregate order history."""
    return query_db("""
    SELECT 
        u.id, u.email, u.full_name, u.phone, u.status, u.created_at,
        COUNT(o.id) as orders_count,
        COALESCE(SUM(o.total_amount), 0) as total_spend
    FROM users u
    LEFT JOIN orders o ON u.id = o.customer_id AND o.order_status != 'cancelled'
    WHERE u.role = 'customer'
    GROUP BY u.id
    ORDER BY u.created_at DESC;
    """)


@router.put("/customers/{customer_id}/status")
def update_customer_status(customer_id: str, status: str, user: dict = Depends(require_roles(["admin", "super_admin"]))):
    """Suspends or restores a customer account."""
    if status not in ["active", "suspended"]:
        raise HTTPException(status_code=400, detail="Invalid status value.")
    execute_db("UPDATE users SET status = ? WHERE id = ? AND role = 'customer';", (status, customer_id))
    return {"success": True, "message": f"Customer status updated to {status}."}


@router.get("/products")
def list_all_products(user: dict = Depends(require_roles(["admin", "super_admin"]))):
    """Lists all products across all vendors for moderation."""
    return query_db("""
    SELECT p.*, s.store_name, c.name as category_name
    FROM products p
    JOIN seller_profiles s ON p.seller_id = s.id
    JOIN categories c ON p.category_id = c.id
    ORDER BY p.created_at DESC;
    """)


@router.put("/products/{product_id}/approval")
def toggle_product_approval(product_id: str, req: ProductApprovalRequest, user: dict = Depends(require_roles(["admin", "super_admin"]))):
    """Approves or unapproves a product listing."""
    execute_db("UPDATE products SET is_approved = ? WHERE id = ?;", (1 if req.is_approved else 0, product_id))
    return {"success": True, "message": f"Product approval set to {req.is_approved}."}


@router.get("/orders")
def list_all_orders(user: dict = Depends(require_roles(["admin", "super_admin"]))):
    """Lists all orders placed on the platform."""
    orders = query_db("""
    SELECT o.*, u.full_name as customer_name, u.email as customer_email
    FROM orders o
    JOIN users u ON o.customer_id = u.id
    ORDER BY o.created_at DESC;
    """)
    for o in orders:
        o["suborders_count"] = query_db("SELECT COUNT(*) as cnt FROM seller_orders WHERE order_id = ?;", (o["id"],), one=True)["cnt"]
    return orders


@router.post("/orders/{order_id}/refund")
def process_admin_refund(order_id: str, reason: str = "Administrative refund", user: dict = Depends(require_roles(["admin", "super_admin"]))):
    """Issues an administrative refund for a disputed order."""
    return PaymentGatewayManager.process_refund(order_id, reason=reason)


@router.get("/reports/csv", response_class=PlainTextResponse)
def export_sales_report_csv(user: dict = Depends(require_roles(["admin", "super_admin"]))):
    """Generates and streams a CSV export of all platform sales and commissions."""
    orders = query_db("""
    SELECT 
        o.order_number, o.created_at, u.full_name as customer,
        o.total_amount, o.payment_method, o.payment_status, o.order_status,
        so.suborder_number, sp.store_name, so.subtotal as item_total, so.platform_fee, so.seller_earnings
    FROM orders o
    JOIN users u ON o.customer_id = u.id
    JOIN seller_orders so ON o.id = so.order_id
    JOIN seller_profiles sp ON so.seller_id = sp.id
    ORDER BY o.created_at DESC;
    """)

    lines = ["Order Number,Date,Customer,Total Amount,Payment Method,Payment Status,Order Status,Suborder,Seller Store,Suborder Subtotal,Platform Commission,Seller Payout"]
    for r in orders:
        lines.append(f'"{r["order_number"]}","{r["created_at"]}","{r["customer"]}",{r["total_amount"]},"{r["payment_method"]}","{r["payment_status"]}","{r["order_status"]}","{r["suborder_number"]}","{r["store_name"]}",{r["item_total"]},{r["platform_fee"]},{r["seller_earnings"]}')
    
    return "\n".join(lines)
