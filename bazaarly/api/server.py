"""
Bazaarly Core Server Application
FastAPI REST API and SPA Static Dashboard Server.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from bazaarly.db.database import init_schema, seed_data
from bazaarly.api import (
    auth_routes,
    catalog_routes,
    cart_routes,
    order_routes,
    seller_routes,
    admin_routes,
    super_admin_routes,
)

app = FastAPI(
    title="Bazaarly Multi-Vendor eCommerce Platform API",
    description="Enterprise Multi-Vendor eCommerce Backend with Role-Based Portals, Multi-Gateway Payments, and Centralized Inventory Control.",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup Hook
@app.on_event("startup")
def on_startup():
    init_schema()
    seed_data()

# Include Feature Routers
app.include_router(auth_routes.router)
app.include_router(catalog_routes.router)
app.include_router(cart_routes.router)
app.include_router(order_routes.router)
app.include_router(seller_routes.router)
app.include_router(admin_routes.router)
app.include_router(super_admin_routes.router)


@app.api_route("/api/status", methods=["GET", "HEAD"])
def api_status():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "platform": "Bazaarly Multi-Vendor eCommerce",
        "engine": "FastAPI + SQLite WAL",
        "roles_supported": ["customer", "seller", "admin", "super_admin"]
    }


# Static Files & SPA Route
STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.api_route("/", methods=["GET", "HEAD"])
    def serve_frontend_index():
        return FileResponse(str(STATIC_DIR / "index.html"))
