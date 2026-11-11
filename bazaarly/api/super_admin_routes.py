"""
Bazaarly Super Admin API Routes
Platform-level governance: financial commissions, administrator management, audit logs, and global settings.
"""

import uuid
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from bazaarly.db.database import query_db, execute_db, hash_password
from bazaarly.core.security import require_roles
from bazaarly.core.models import SystemSettingsUpdateRequest

router = APIRouter(prefix="/api/super-admin", tags=["Super Admin Portal"])


class AdminCreateRequest(BaseModel):
    email: str
    full_name: str
    password: str
    phone: str = ""


@router.get("/dashboard")
def get_super_admin_dashboard(user: dict = Depends(require_roles(["super_admin"]))):
    """Platform-level financial and governance health check."""
    finances = query_db("""
    SELECT 
        COALESCE(SUM(total_amount), 0) as total_gross_merchandise_value,
        (SELECT COALESCE(SUM(platform_fee), 0) FROM seller_orders WHERE status != 'cancelled') as platform_net_commissions,
        (SELECT COALESCE(SUM(seller_earnings), 0) FROM seller_orders WHERE status != 'cancelled') as total_seller_disbursements,
        (SELECT COUNT(*) FROM orders) as total_platform_orders,
        (SELECT COUNT(*) FROM users WHERE role = 'admin') as total_staff_admins,
        (SELECT COUNT(*) FROM seller_profiles WHERE approval_status = 'approved') as verified_merchants
    FROM orders
    WHERE order_status != 'cancelled';
    """, one=True)

    settings = {s["key"]: s["value"] for s in query_db("SELECT key, value FROM system_settings;")}
    audit_logs = query_db("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 10;")

    return {
        "finances": finances,
        "settings": settings,
        "recent_audit_logs": audit_logs
    }


@router.get("/admins")
def list_administrators(user: dict = Depends(require_roles(["super_admin"]))):
    """Lists staff admin and super admin accounts."""
    return query_db("SELECT id, email, full_name, phone, role, status, created_at FROM users WHERE role IN ('admin', 'super_admin') ORDER BY created_at DESC;")


@router.post("/admins")
def create_administrator(req: AdminCreateRequest, user: dict = Depends(require_roles(["super_admin"]))):
    """Provisions a new platform administrator."""
    existing = query_db("SELECT id FROM users WHERE email = ?;", (req.email,), one=True)
    if existing:
        raise HTTPException(status_code=400, detail="Account with this email already exists.")

    new_id = f"usr-adm-{uuid.uuid4().hex[:6]}"
    pwd_hash = hash_password(req.password)

    execute_db("""
    INSERT INTO users (id, email, password_hash, full_name, phone, role, status)
    VALUES (?, ?, ?, ?, ?, 'admin', 'active');
    """, (new_id, req.email, pwd_hash, req.full_name, req.phone))

    return {"success": True, "message": "Administrator account provisioned.", "id": new_id}


@router.get("/settings")
def get_system_settings(user: dict = Depends(require_roles(["super_admin"]))):
    """Returns platform configuration settings."""
    rows = query_db("SELECT key, value, updated_at FROM system_settings;")
    return {r["key"]: r["value"] for r in rows}


@router.put("/settings")
def update_system_settings(req: SystemSettingsUpdateRequest, user: dict = Depends(require_roles(["super_admin"]))):
    """Updates platform commission, tax rates, shipping policies, and website settings."""
    for key, value in req.settings.items():
        execute_db("""
        INSERT INTO system_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
        """, (key, str(value)))

    # Record audit log
    execute_db("""
    INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, metadata_json)
    VALUES (?, ?, 'update_system_settings', 'settings', 'global', ?);
    """, (f"aud-{uuid.uuid4().hex[:8]}", user["id"], str(req.settings)))

    return {"success": True, "message": "Platform system settings updated successfully."}


@router.get("/audit-logs")
def get_audit_logs(user: dict = Depends(require_roles(["super_admin"]))):
    """Fetches system audit trail."""
    return query_db("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 50;")
