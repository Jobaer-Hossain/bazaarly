"""
Bazaarly Authentication & RBAC Security Module
JWT-compatible token signing, password verification, and role-based access decorators.
"""

import hmac
import hashlib
import base64
import json
import time
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bazaarly.db.database import query_db, hash_password

SECRET_KEY = "bazaarly_jwt_production_master_secret_key_2026"
security_scheme = HTTPBearer(auto_error=False)


def create_access_token(user_id: str, email: str, role: str, expires_in_seconds: int = 86400 * 7) -> str:
    """Creates a signed JWT-compatible token with HMAC-SHA256 signature."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": int(time.time()) + expires_in_seconds,
        "iat": int(time.time())
    }
    encoded_header = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(
        SECRET_KEY.encode(),
        f"{encoded_header}.{encoded_payload}".encode(),
        hashlib.sha256
    ).digest()
    encoded_sig = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{encoded_header}.{encoded_payload}.{encoded_sig}"


def decode_access_token(token: str) -> Dict[str, Any]:
    """Validates and decodes the signed token payload."""
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token structure")
        
        encoded_header, encoded_payload, encoded_sig = parts
        
        # Verify signature
        expected_sig = hmac.new(
            SECRET_KEY.encode(),
            f"{encoded_header}.{encoded_payload}".encode(),
            hashlib.sha256
        ).digest()
        
        # Pad base64 for decoding
        rem = len(encoded_sig) % 4
        padded_sig = encoded_sig + ("=" * (4 - rem) if rem else "")
        if not hmac.compare_digest(base64.urlsafe_b64decode(padded_sig.encode()), expected_sig):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")
        
        # Decode payload
        rem_p = len(encoded_payload) % 4
        padded_payload = encoded_payload + ("=" * (4 - rem_p) if rem_p else "")
        payload = json.loads(base64.urlsafe_b64decode(padded_payload.encode()).decode())
        
        # Check expiry
        if payload.get("exp", 0) < time.time():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
            
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication error: {str(e)}")


def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)) -> Optional[Dict[str, Any]]:
    """Retrieves authenticated user record if bearer token is present, otherwise returns None."""
    if not credentials or not credentials.credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        user = query_db("SELECT id, email, full_name, phone, role, status FROM users WHERE id = ?", (payload["sub"],), one=True)
        if not user or user["status"] != "active":
            return None
        
        # If seller, also attach seller_profile
        if user["role"] == "seller":
            seller = query_db("SELECT * FROM seller_profiles WHERE user_id = ?", (user["id"],), one=True)
            user["seller_profile"] = seller
            
        return user
    except Exception:
        return None


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)) -> Dict[str, Any]:
    """Strict dependency requiring authenticated user."""
    user = get_current_user_optional(credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(allowed_roles: List[str]):
    """Role-based access control dependency factory."""
    def role_checker(user: Dict[str, Any] = Depends(get_current_user)):
        user_role = user.get("role")
        # Super admin has global bypass capability
        if user_role == "super_admin":
            return user
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of roles: {', '.join(allowed_roles)}"
            )
        return user
    return role_checker
