"""
Bazaarly Pydantic Domain Schemas
Strict request and response schemas for all API operations.
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


# Auth Schemas
class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)
    full_name: str
    phone: Optional[str] = None
    role: Literal["customer", "seller"] = "customer"
    store_name: Optional[str] = None
    store_description: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class SwitchDemoUserRequest(BaseModel):
    role: Literal["customer", "seller", "admin", "super_admin"]


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


# Address Schema
class AddressRequest(BaseModel):
    full_name: str
    phone: str
    address_line1: str
    address_line2: Optional[str] = ""
    city: str
    state: str
    postal_code: str
    country: str = "United States"
    is_default: bool = False


# Cart Schemas
class CartItemAddRequest(BaseModel):
    product_id: str
    variant_id: Optional[str] = None
    quantity: int = Field(default=1, ge=1)
    session_id: Optional[str] = None


class CartItemUpdateRequest(BaseModel):
    quantity: int = Field(ge=1)


class ApplyCouponRequest(BaseModel):
    code: Optional[str] = None
    coupon_code: Optional[str] = None

    @property
    def coupon_string(self) -> str:
        return (self.coupon_code or self.code or "").strip().upper()


# Checkout & Order Placement Schemas
class CheckoutOrderRequest(BaseModel):
    shipping_address_id: Optional[str] = None
    new_shipping_address: Optional[AddressRequest] = None
    shipping_address: Optional[AddressRequest] = None
    payment_method: Literal["cod", "stripe", "sslcommerz", "bank_transfer"]
    coupon_code: Optional[str] = None
    order_notes: Optional[str] = None
    session_id: Optional[str] = None


class OrderStatusUpdateRequest(BaseModel):
    status: Literal["confirmed", "processing", "packed", "shipped", "delivered", "cancelled"]
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None


# Product Management Schemas
class ProductVariantInput(BaseModel):
    title: str
    attribute_name: str
    attribute_value: str
    sku: str
    price_override: Optional[float] = None
    stock_quantity: int = Field(default=0, ge=0)


class ProductCreateRequest(BaseModel):
    category_id: str
    brand_id: Optional[str] = None
    title: str
    description: str
    regular_price: float = Field(gt=0)
    sale_price: float = Field(gt=0)
    sku: str
    stock_quantity: int = Field(default=10, ge=0)
    low_stock_threshold: int = Field(default=5, ge=0)
    images: List[str] = []
    variants: List[ProductVariantInput] = []


class ProductUpdateRequest(BaseModel):
    category_id: Optional[str] = None
    brand_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    regular_price: Optional[float] = None
    sale_price: Optional[float] = None
    stock_quantity: Optional[int] = None
    low_stock_threshold: Optional[int] = None
    is_active: Optional[bool] = None


# Review Schema
class ReviewCreateRequest(BaseModel):
    product_id: str
    rating: int = Field(ge=1, le=5)
    title: Optional[str] = ""
    comment: str


# Seller Payout Request
class PayoutRequest(BaseModel):
    amount: float = Field(gt=0)
    bank_details: str
    notes: Optional[str] = ""


# Admin Action Schemas
class SellerApprovalRequest(BaseModel):
    approval_status: Literal["approved", "rejected", "pending"]
    commission_rate: Optional[float] = 10.0


class ProductApprovalRequest(BaseModel):
    is_approved: bool


class SystemSettingsUpdateRequest(BaseModel):
    settings: Dict[str, str]
