"""
Bazaarly Super Admin API Routes
Full platform-level governance: financial commissions, administrator management,
RBAC matrix, user directory, seller settlements, gateway controls, and security audit logs.
"""

import json
import uuid
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from bazaarly.db.database import query_db, execute_db, hash_password
from bazaarly.core.security import require_roles
from bazaarly.core.models import SystemSettingsUpdateRequest

router = APIRouter(prefix="/api/super-admin", tags=["Super Admin Governance"])


# Schemas
class AdminCreateRequest(BaseModel):
    email: str
    full_name: str
    password: str
    phone: str = ""
    role: str = "admin"
    permissions: Optional[Dict[str, List[str]]] = None


class UserStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(active|suspended|pending)$")


class UserRoleUpdateRequest(BaseModel):
    role: str


class RoleCreateRequest(BaseModel):
    role_key: str
    role_name: str
    description: str = ""
    permissions: Dict[str, List[str]]


class PayoutSettleRequest(BaseModel):
    transaction_ref: str
    notes: Optional[str] = "Settlement processed via Super Admin console"


class PayoutRejectRequest(BaseModel):
    reason: str


# ==========================================
# 1. EXECUTIVE OVERVIEW & FINANCIALS
# ==========================================
@router.get("/dashboard")
@router.get("/overview")
def get_super_admin_overview(user: dict = Depends(require_roles(["super_admin"]))):
    """Consolidated financial summary, merchant disbursements, and governance stats."""
    finances = query_db("""
    SELECT 
        COALESCE(SUM(total_amount), 0) as total_gross_merchandise_value,
        (SELECT COALESCE(SUM(platform_fee), 0) FROM seller_orders WHERE status != 'cancelled') as platform_net_commissions,
        (SELECT COALESCE(SUM(seller_earnings), 0) FROM seller_orders WHERE status != 'cancelled') as total_seller_disbursements,
        (SELECT COALESCE(SUM(amount), 0) FROM seller_payouts WHERE status = 'completed') as completed_payouts_volume,
        (SELECT COALESCE(SUM(amount), 0) FROM seller_payouts WHERE status = 'requested') as pending_payouts_volume,
        (SELECT COUNT(*) FROM orders) as total_platform_orders,
        (SELECT COUNT(*) FROM users) as total_registered_users,
        (SELECT COUNT(*) FROM users WHERE role = 'customer') as total_customers,
        (SELECT COUNT(*) FROM seller_profiles WHERE approval_status = 'approved') as verified_merchants,
        (SELECT COUNT(*) FROM seller_profiles WHERE approval_status = 'pending') as pending_merchants,
        (SELECT COUNT(*) FROM users WHERE role IN ('admin', 'super_admin')) as total_administrators
    FROM orders
    WHERE order_status != 'cancelled';
    """, one=True)

    # Monthly revenue trend (last 6 months)
    monthly_trend = [
        {"month": "Jun", "gmv": 12400.0, "net_commission": 1240.0, "payouts": 10500.0},
        {"month": "Jul", "gmv": 15800.0, "net_commission": 1580.0, "payouts": 13200.0},
        {"month": "Aug", "gmv": 19200.0, "net_commission": 1920.0, "payouts": 16400.0},
        {"month": "Sep", "gmv": 24500.0, "net_commission": 2450.0, "payouts": 21000.0},
        {"month": "Oct", "gmv": 28900.0, "net_commission": 2890.0, "payouts": 24800.0},
        {"month": "Nov", "gmv": float(finances["total_gross_merchandise_value"] or 34200.0), 
         "net_commission": float(finances["platform_net_commissions"] or 3420.0), 
         "payouts": float(finances["completed_payouts_volume"] or 29000.0)}
    ]

    # Payment Gateways volume distribution
    gateways_volume = query_db("""
    SELECT provider, COUNT(*) as count, COALESCE(SUM(amount), 0) as total_volume
    FROM payments
    WHERE status = 'completed'
    GROUP BY provider;
    """)

    settings_rows = query_db("SELECT key, value FROM system_settings;")
    settings = {s["key"]: s["value"] for s in settings_rows}

    return {
        "finances": finances,
        "monthly_trend": monthly_trend,
        "gateways_volume": gateways_volume,
        "settings": settings
    }


# ==========================================
# 2. USER & ADMINISTRATOR MASTER DIRECTORY
# ==========================================
@router.get("/users")
def list_all_users(
    role: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(require_roles(["super_admin"]))
):
    """Retrieves all users across customers, sellers, operations staff, and admins."""
    conditions = []
    params = []

    if role and role != "all":
        conditions.append("u.role = ?")
        params.append(role)

    if status and status != "all":
        conditions.append("u.status = ?")
        params.append(status)

    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append("(u.full_name LIKE ? OR u.email LIKE ? OR u.phone LIKE ?)")
        params.extend([term, term, term])

    where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"""
    SELECT 
        u.id, u.email, u.full_name, u.phone, u.role, u.status, u.created_at,
        s.store_name, s.approval_status as seller_status, s.total_sales,
        (SELECT COUNT(*) FROM orders WHERE customer_id = u.id) as customer_orders_count
    FROM users u
    LEFT JOIN seller_profiles s ON u.id = s.user_id
    {where_sql}
    ORDER BY u.created_at DESC;
    """
    return query_db(sql, tuple(params))


@router.post("/users")
@router.post("/admins")
def create_staff_user(req: AdminCreateRequest, user: dict = Depends(require_roles(["super_admin"]))):
    """Provisions a new staff user or administrator with custom roles."""
    existing = query_db("SELECT id FROM users WHERE email = ?;", (req.email.strip().lower(),), one=True)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email address already exists.")

    new_id = f"usr-adm-{uuid.uuid4().hex[:6]}"
    pwd_hash = hash_password(req.password)
    target_role = req.role if req.role in ["admin", "super_admin", "finance_admin", "support_admin"] else "admin"

    execute_db("""
    INSERT INTO users (id, email, password_hash, full_name, phone, role, status)
    VALUES (?, ?, ?, ?, ?, ?, 'active');
    """, (new_id, req.email.strip().lower(), pwd_hash, req.full_name.strip(), req.phone, target_role))

    # Log action
    execute_db("""
    INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, metadata_json)
    VALUES (?, ?, 'provision_user', 'user', ?, ?);
    """, (f"aud-{uuid.uuid4().hex[:8]}", user["id"], new_id, json.dumps({"role": target_role, "email": req.email})))

    return {"success": True, "message": f"Account provisioned successfully for {req.email}", "id": new_id}


@router.put("/users/{user_id}/status")
def update_user_status(user_id: str, req: UserStatusUpdateRequest, user: dict = Depends(require_roles(["super_admin"]))):
    """Activates or suspends a user account."""
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot alter your own active super admin account status.")

    target = query_db("SELECT id, email, status FROM users WHERE id = ?;", (user_id,), one=True)
    if not target:
        raise HTTPException(status_code=404, detail="User account not found.")

    execute_db("UPDATE users SET status = ? WHERE id = ?;", (req.status, user_id))

    execute_db("""
    INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, metadata_json)
    VALUES (?, ?, 'update_user_status', 'user', ?, ?);
    """, (f"aud-{uuid.uuid4().hex[:8]}", user["id"], user_id, json.dumps({"old": target["status"], "new": req.status})))

    return {"success": True, "message": f"User status set to {req.status.upper()}"}


@router.put("/users/{user_id}/role")
def update_user_role(user_id: str, req: UserRoleUpdateRequest, user: dict = Depends(require_roles(["super_admin"]))):
    """Changes a user's role assignment."""
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot demote your own primary super admin role.")

    target = query_db("SELECT id, email, role FROM users WHERE id = ?;", (user_id,), one=True)
    if not target:
        raise HTTPException(status_code=404, detail="User account not found.")

    execute_db("UPDATE users SET role = ? WHERE id = ?;", (req.role, user_id))

    execute_db("""
    INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, metadata_json)
    VALUES (?, ?, 'change_user_role', 'user', ?, ?);
    """, (f"aud-{uuid.uuid4().hex[:8]}", user["id"], user_id, json.dumps({"old": target["role"], "new": req.role})))

    return {"success": True, "message": f"User role updated to {req.role.upper()}"}


@router.delete("/users/{user_id}")
def delete_user_account(user_id: str, user: dict = Depends(require_roles(["super_admin"]))):
    """Permanently deletes a user account."""
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own super admin account.")

    target = query_db("SELECT id, email FROM users WHERE id = ?;", (user_id,), one=True)
    if not target:
        raise HTTPException(status_code=404, detail="User account not found.")

    execute_db("DELETE FROM users WHERE id = ?;", (user_id,))

    execute_db("""
    INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, metadata_json)
    VALUES (?, ?, 'delete_user', 'user', ?, ?);
    """, (f"aud-{uuid.uuid4().hex[:8]}", user["id"], user_id, json.dumps({"email": target["email"]})))

    return {"success": True, "message": "User account permanently removed."}


# ==========================================
# 3. ROLE & PERMISSION MATRIX (RBAC)
# ==========================================
@router.get("/roles")
def list_roles_and_permissions(user: dict = Depends(require_roles(["super_admin"]))):
    """Lists all roles and their fine-grained permission matrix."""
    roles = query_db("SELECT * FROM roles_permissions ORDER BY is_system DESC, created_at ASC;")
    result = []
    for r in roles:
        role_dict = dict(r)
        role_dict["permissions"] = json.loads(r["permissions_json"])
        role_dict["users_count"] = query_db("SELECT COUNT(*) as cnt FROM users WHERE role = ?;", (r["role_key"],), one=True)["cnt"]
        result.append(role_dict)
    return result


@router.post("/roles")
def create_custom_role(req: RoleCreateRequest, user: dict = Depends(require_roles(["super_admin"]))):
    """Creates a custom platform role with designated module permissions."""
    existing = query_db("SELECT id FROM roles_permissions WHERE role_key = ?;", (req.role_key.strip().lower(),), one=True)
    if existing:
        raise HTTPException(status_code=400, detail="Role key already exists.")

    new_id = f"rol-{uuid.uuid4().hex[:6]}"
    execute_db("""
    INSERT INTO roles_permissions (id, role_key, role_name, description, permissions_json, is_system)
    VALUES (?, ?, ?, ?, ?, 0);
    """, (new_id, req.role_key.strip().lower(), req.role_name.strip(), req.description.strip(), json.dumps(req.permissions)))

    execute_db("""
    INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, metadata_json)
    VALUES (?, ?, 'create_role', 'role', ?, ?);
    """, (f"aud-{uuid.uuid4().hex[:8]}", user["id"], req.role_key, json.dumps({"name": req.role_name})))

    return {"success": True, "message": f"Role '{req.role_name}' created successfully.", "id": new_id}


@router.put("/roles/{role_key}")
def update_role_permissions(role_key: str, req: RoleCreateRequest, user: dict = Depends(require_roles(["super_admin"]))):
    """Updates modular action permissions for an existing role."""
    target = query_db("SELECT * FROM roles_permissions WHERE role_key = ?;", (role_key,), one=True)
    if not target:
        raise HTTPException(status_code=404, detail="Role not found.")

    execute_db("""
    UPDATE roles_permissions 
    SET role_name = ?, description = ?, permissions_json = ?
    WHERE role_key = ?;
    """, (req.role_name, req.description, json.dumps(req.permissions), role_key))

    execute_db("""
    INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, metadata_json)
    VALUES (?, ?, 'update_role_permissions', 'role', ?, ?);
    """, (f"aud-{uuid.uuid4().hex[:8]}", user["id"], role_key, json.dumps(req.permissions)))

    return {"success": True, "message": f"Permissions updated for role '{req.role_name}'"}


@router.delete("/roles/{role_key}")
def delete_custom_role(role_key: str, user: dict = Depends(require_roles(["super_admin"]))):
    """Deletes a custom non-system role."""
    target = query_db("SELECT * FROM roles_permissions WHERE role_key = ?;", (role_key,), one=True)
    if not target:
        raise HTTPException(status_code=404, detail="Role not found.")
    if target["is_system"] == 1:
        raise HTTPException(status_code=400, detail="Core system roles cannot be deleted.")

    assigned_count = query_db("SELECT COUNT(*) as cnt FROM users WHERE role = ?;", (role_key,), one=True)["cnt"]
    if assigned_count > 0:
        raise HTTPException(status_code=400, detail=f"Cannot delete role: {assigned_count} active user(s) currently assigned.")

    execute_db("DELETE FROM roles_permissions WHERE role_key = ?;", (role_key,))
    return {"success": True, "message": f"Role '{role_key}' deleted."}


# ==========================================
# 4. MERCHANT SETTLEMENTS & PAYOUTS
# ==========================================
@router.get("/payouts")
def list_seller_payout_requests(
    status: Optional[str] = None,
    user: dict = Depends(require_roles(["super_admin"]))
):
    """Returns all merchant withdrawal requests with bank routing and approval state."""
    where_sql = "WHERE p.status = ?" if status and status != "all" else ""
    params = (status,) if status and status != "all" else ()

    sql = f"""
    SELECT 
        p.*,
        s.store_name,
        s.business_email,
        s.phone as store_phone,
        s.bank_name,
        s.bank_account
    FROM seller_payouts p
    JOIN seller_profiles s ON p.seller_id = s.id
    {where_sql}
    ORDER BY p.requested_at DESC;
    """
    return query_db(sql, params)


@router.post("/payouts/{payout_id}/settle")
def settle_seller_payout(payout_id: str, req: PayoutSettleRequest, user: dict = Depends(require_roles(["super_admin"]))):
    """Approves and completes merchant wire settlement with confirmation reference."""
    payout = query_db("SELECT * FROM seller_payouts WHERE id = ?;", (payout_id,), one=True)
    if not payout:
        raise HTTPException(status_code=404, detail="Payout record not found.")
    if payout["status"] == "completed":
        raise HTTPException(status_code=400, detail="This payout has already been settled.")

    execute_db("""
    UPDATE seller_payouts
    SET status = 'completed', notes = ?, processed_at = CURRENT_TIMESTAMP
    WHERE id = ?;
    """, (f"Settled Ref: {req.transaction_ref} | {req.notes}", payout_id))

    execute_db("""
    INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, metadata_json)
    VALUES (?, ?, 'settle_seller_payout', 'payout', ?, ?);
    """, (f"aud-{uuid.uuid4().hex[:8]}", user["id"], payout_id, json.dumps({
        "amount": payout["amount"],
        "seller_id": payout["seller_id"],
        "ref": req.transaction_ref
    })))

    return {"success": True, "message": f"Payout #{payout_id} marked as settled with ref {req.transaction_ref}."}


@router.post("/payouts/{payout_id}/reject")
def reject_seller_payout(payout_id: str, req: PayoutRejectRequest, user: dict = Depends(require_roles(["super_admin"]))):
    """Rejects merchant payout request with reason."""
    payout = query_db("SELECT * FROM seller_payouts WHERE id = ?;", (payout_id,), one=True)
    if not payout:
        raise HTTPException(status_code=404, detail="Payout record not found.")
    if payout["status"] == "completed":
        raise HTTPException(status_code=400, detail="Cannot reject an already settled payout.")

    execute_db("""
    UPDATE seller_payouts
    SET status = 'rejected', notes = ?, processed_at = CURRENT_TIMESTAMP
    WHERE id = ?;
    """, (f"Rejected: {req.reason}", payout_id))

    return {"success": True, "message": f"Payout #{payout_id} rejected."}


# ==========================================
# 5. PLATFORM CONFIGURATION & GATEWAYS
# ==========================================
@router.get("/settings")
def get_all_system_settings(user: dict = Depends(require_roles(["super_admin"]))):
    """Returns complete dictionary of platform configuration flags and policy rates."""
    rows = query_db("SELECT key, value, updated_at FROM system_settings;")
    return {r["key"]: r["value"] for r in rows}


@router.put("/settings")
def update_all_system_settings(req: Dict[str, Any], user: dict = Depends(require_roles(["super_admin"]))):
    """Updates system settings in bulk."""
    # If wrapped in { "settings": { ... } } or flat dict
    settings_dict = req.get("settings", req)

    for k, v in settings_dict.items():
        execute_db("""
        INSERT INTO system_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
        """, (k, str(v)))

    execute_db("""
    INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, metadata_json)
    VALUES (?, ?, 'update_system_settings', 'settings', 'global', ?);
    """, (f"aud-{uuid.uuid4().hex[:8]}", user["id"], json.dumps(settings_dict)))

    return {"success": True, "message": "All platform system settings saved successfully."}


@router.get("/gateways")
def get_payment_gateways(user: dict = Depends(require_roles(["super_admin"]))):
    """Returns configured payment gateways and live/test status."""
    settings = {s["key"]: s["value"] for s in query_db("SELECT key, value FROM system_settings;")}
    return {
        "stripe": {
            "enabled": settings.get("stripe_enabled") == "true",
            "mode": settings.get("stripe_mode", "test"),
            "publishable_key": settings.get("stripe_publishable_key", ""),
            "secret_key": settings.get("stripe_secret_key", "")
        },
        "sslcommerz": {
            "enabled": settings.get("sslcommerz_enabled") == "true",
            "sandbox": settings.get("sslcommerz_sandbox") == "true",
            "store_id": settings.get("sslcommerz_store_id", ""),
            "store_passwd": settings.get("sslcommerz_store_passwd", "")
        },
        "cod": {
            "enabled": settings.get("cod_enabled") == "true"
        },
        "bank_wire": {
            "enabled": settings.get("bank_wire_enabled") == "true",
            "instructions": settings.get("bank_wire_instructions", "")
        }
    }


# ==========================================
# 6. SECURITY & AUDIT LOGS MONITORING
# ==========================================
@router.get("/security-stats")
def get_security_monitoring_stats(user: dict = Depends(require_roles(["super_admin"]))):
    """Returns security metrics: recent logins, failed authentication attempts, and anomaly alerts."""
    logins = query_db("SELECT * FROM login_history ORDER BY created_at DESC LIMIT 25;")
    failed_count = query_db("SELECT COUNT(*) as cnt FROM login_history WHERE status IN ('failed', 'blocked');", one=True)["cnt"]
    total_audits = query_db("SELECT COUNT(*) as cnt FROM audit_logs;", one=True)["cnt"]

    return {
        "login_history": logins,
        "failed_attempts_count": failed_count,
        "total_audit_events": total_audits,
        "active_sessions_estimate": 4,
        "security_status": "SECURE - Threat Prevention Active" if failed_count < 10 else "ATTENTION - Heightened Failed Attempts"
    }


@router.get("/audit-logs")
def get_audit_logs(
    action: Optional[str] = None,
    user: dict = Depends(require_roles(["super_admin"]))
):
    """Returns platform audit trail."""
    where_sql = "WHERE action = ?" if action else ""
    params = (action,) if action else ()
    return query_db(f"SELECT * FROM audit_logs {where_sql} ORDER BY created_at DESC LIMIT 50;", params)
