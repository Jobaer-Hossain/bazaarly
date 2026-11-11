"""
Bazaarly Authentication API Routes
"""

import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from bazaarly.db.database import query_db, execute_db, hash_password
from bazaarly.core.security import create_access_token, get_current_user
from bazaarly.core.models import RegisterRequest, LoginRequest, SwitchDemoUserRequest, AuthResponse

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthResponse)
def register_user(req: RegisterRequest):
    """Registers a new customer or seller account."""
    existing = query_db("SELECT id FROM users WHERE email = ?;", (req.email,), one=True)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user_id = f"usr-{uuid.uuid4().hex[:8]}"
    pwd_hash = hash_password(req.password)

    # Status: customers active immediately; sellers pending approval unless auto-approved
    seller_status = "pending" if req.role == "seller" else "active"

    execute_db("""
    INSERT INTO users (id, email, password_hash, full_name, phone, role, status)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (user_id, req.email, pwd_hash, req.full_name, req.phone, req.role, "active"))

    if req.role == "seller":
        seller_id = f"sel-{uuid.uuid4().hex[:8]}"
        store_slug = (req.store_name or req.full_name).lower().replace(" ", "-") + f"-{uuid.uuid4().hex[:4]}"
        execute_db("""
        INSERT INTO seller_profiles (id, user_id, store_name, slug, store_description, business_email, phone, approval_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (seller_id, user_id, req.store_name or f"{req.full_name}'s Store", store_slug, req.store_description, req.email, req.phone, seller_status))
    else:
        execute_db("""
        INSERT INTO customer_profiles (id, user_id)
        VALUES (?, ?);
        """, (f"cust-{uuid.uuid4().hex[:8]}", user_id))

    token = create_access_token(user_id, req.email, req.role)
    user_data = query_db("SELECT id, email, full_name, phone, role, status FROM users WHERE id = ?;", (user_id,), one=True)
    
    return AuthResponse(access_token=token, user=user_data)


@router.post("/login", response_model=AuthResponse)
def login_user(req: LoginRequest):
    """Authenticates credentials and issues a signed JWT token."""
    pwd_hash = hash_password(req.password)
    user = query_db("""
    SELECT id, email, full_name, phone, role, status
    FROM users
    WHERE email = ? AND password_hash = ?;
    """, (req.email, pwd_hash), one=True)

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    if user["status"] == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account has been suspended by administration.")

    token = create_access_token(user["id"], user["email"], user["role"])
    
    # Attach seller details if seller
    if user["role"] == "seller":
        seller = query_db("SELECT * FROM seller_profiles WHERE user_id = ?;", (user["id"],), one=True)
        user["seller_profile"] = seller

    return AuthResponse(access_token=token, user=user)


@router.get("/me")
def get_current_user_profile(user: dict = Depends(get_current_user)):
    """Returns the authenticated user profile and seller details if applicable."""
    if user["role"] == "seller":
        seller = query_db("SELECT * FROM seller_profiles WHERE user_id = ?;", (user["id"],), one=True)
        user["seller_profile"] = seller
    return user


@router.get("/demo-users")
def get_demo_users():
    """Lists the pre-configured role test accounts for quick evaluation."""
    return [
        {"role": "customer", "email": "john.doe@example.com", "name": "Johnathan Doe (Customer)"},
        {"role": "seller", "email": "techstore@bazaarly.com", "name": "Marcus Vance (Nexus Tech Store)"},
        {"role": "admin", "email": "admin@bazaarly.com", "name": "Operations Lead (Admin)"},
        {"role": "super_admin", "email": "superadmin@bazaarly.com", "name": "Platform Executive (Super Admin)"},
    ]


@router.post("/switch-demo", response_model=AuthResponse)
def switch_demo_user(req: Optional[SwitchDemoUserRequest] = None, role: Optional[str] = None):
    """Seamlessly switches active session to a designated role demo account."""
    target_role = (req.role if req else None) or role or "customer"
    role_email_map = {
        "customer": "john.doe@example.com",
        "seller": "techstore@bazaarly.com",
        "admin": "admin@bazaarly.com",
        "super_admin": "superadmin@bazaarly.com",
    }
    if target_role not in role_email_map:
        raise HTTPException(status_code=400, detail=f"Unsupported demo role: {target_role}")

    target_email = role_email_map[target_role]
    user = query_db("SELECT id, email, full_name, phone, role, status FROM users WHERE email = ?;", (target_email,), one=True)
    if not user:
        raise HTTPException(status_code=404, detail="Demo user not found.")

    token = create_access_token(user["id"], user["email"], user["role"])
    if user["role"] == "seller":
        user["seller_profile"] = query_db("SELECT * FROM seller_profiles WHERE user_id = ?;", (user["id"],), one=True)

    return AuthResponse(access_token=token, user=user)
