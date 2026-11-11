"""
Bazaarly Centralized Inventory & Stock Allocation Engine
Guarantees atomic stock reservation, prevents overselling, and handles automatic replenishment on cancellation.
"""

from typing import List, Dict, Any, Tuple
from bazaarly.db.database import get_db_connection


class InventoryManager:
    """Manages transactional inventory deductions and reservations."""

    @staticmethod
    def validate_and_deduct_stock(items: List[Dict[str, Any]], conn) -> List[Dict[str, Any]]:
        """
        Atomically checks and decrements product / variant inventory within an existing transaction.
        Raises ValueError if any item does not have sufficient stock.
        """
        cursor = conn.cursor()
        deducted_records = []

        for item in items:
            p_id = item["product_id"]
            v_id = item.get("variant_id")
            qty = int(item["quantity"])

            if v_id:
                # Variant inventory
                cursor.execute("SELECT id, title, stock_quantity FROM product_variants WHERE id = ?;", (v_id,))
                variant = cursor.fetchone()
                if not variant:
                    raise ValueError(f"Selected product variant {v_id} was not found.")
                if variant["stock_quantity"] < qty:
                    raise ValueError(f"Insufficient stock for variant '{variant['title']}'. Requested {qty}, available: {variant['stock_quantity']}.")
                
                # Deduct variant stock
                cursor.execute("""
                UPDATE product_variants
                SET stock_quantity = stock_quantity - ?
                WHERE id = ?;
                """, (qty, v_id))
            else:
                # Base product inventory
                cursor.execute("SELECT id, title, stock_quantity FROM products WHERE id = ?;", (p_id,))
                product = cursor.fetchone()
                if not product:
                    raise ValueError(f"Product {p_id} was not found.")
                if product["stock_quantity"] < qty:
                    raise ValueError(f"Insufficient stock for '{product['title']}'. Requested {qty}, available: {product['stock_quantity']}.")
                
                # Deduct product stock
                cursor.execute("""
                UPDATE products
                SET stock_quantity = stock_quantity - ?
                WHERE id = ?;
                """, (qty, p_id))

            deducted_records.append({
                "product_id": p_id,
                "variant_id": v_id,
                "quantity": qty
            })

        return deducted_records

    @staticmethod
    def restore_stock_for_order(order_id: str):
        """Replenishes inventory when an order is cancelled or refunded."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT product_id, variant_id, quantity FROM order_items WHERE order_id = ?;", (order_id,))
            items = cursor.fetchall()
            for it in items:
                qty = it["quantity"]
                if it["variant_id"]:
                    cursor.execute("""
                    UPDATE product_variants
                    SET stock_quantity = stock_quantity + ?
                    WHERE id = ?;
                    """, (qty, it["variant_id"]))
                else:
                    cursor.execute("""
                    UPDATE products
                    SET stock_quantity = stock_quantity + ?
                    WHERE id = ?;
                    """, (qty, it["product_id"]))
