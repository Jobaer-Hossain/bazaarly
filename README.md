# Bazaarly

A multi-vendor eCommerce marketplace platform built with FastAPI, SQLite, and vanilla modern JavaScript.

## Features

- **Storefront & Catalog:** Product browsing with category filters, variant selection (size, color, storage), search, and pagination.
- **Cart & Checkout:** Server-calculated pricing, coupon discounts, shipping rules, and multi-step checkout.
- **Multi-Vendor Orders:** Atomic stock reservation, automated splitting of customer orders into individual merchant suborders, and per-vendor order fulfillment.
- **Role-Based Portals:**
  - **Customer:** Product browsing, persistent cart, order tracking, printable invoices, and reviews.
  - **Seller:** Store catalog management, SKU and inventory control, suborder fulfillment, and revenue analytics.
  - **Admin:** Merchant approvals, catalog moderation, dispute resolution, and sales reporting.
  - **Super Admin:** Commission configurations, platform policy settings, and staff administrator management.
- **Payment Drivers:** Interface supporting Card (Stripe), Cash on Delivery, Net Banking, and Bank Transfer.

## Getting Started

### Prerequisites

- Python 3.10+
- pip

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Jobaer-Hossain/bazaarly.git
   cd bazaarly
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

Start the local server:
```bash
python run.py --port 8005
```

Once running:
- **Web App:** http://localhost:8005/
- **API Documentation:** http://localhost:8005/docs
- **Health Check:** http://localhost:8005/api/status

### Test Accounts

The database comes pre-seeded with accounts for testing different roles:

| Role | Email | Password |
| :--- | :--- | :--- |
| Customer | `john.doe@example.com` | `password123` |
| Seller | `techstore@bazaarly.com` | `password123` |
| Admin | `admin@bazaarly.com` | `password123` |
| Super Admin | `superadmin@bazaarly.com` | `password123` |

## Running Tests

Run the automated test suite with unittest:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Project Structure

```
bazaarly/
├── bazaarly/
│   ├── api/
│   │   ├── admin_routes.py         # Merchant approvals, disputes, CSV export
│   │   ├── auth_routes.py          # Authentication, token generation, user roles
│   │   ├── cart_routes.py          # Cart operations, pricing calculations, coupons
│   │   ├── catalog_routes.py       # Products search, categories, reviews
│   │   ├── order_routes.py         # Checkout, order splitting, fulfillment
│   │   ├── seller_routes.py        # Merchant inventory, orders, revenue
│   │   ├── super_admin_routes.py   # Global settings, staff accounts, audit logs
│   │   └── server.py               # FastAPI application setup and routing
│   ├── core/
│   │   ├── inventory.py            # Stock allocation and replenishment logic
│   │   ├── models.py               # Domain schemas and validation models
│   │   ├── payments.py             # Payment gateway abstractions
│   │   └── security.py             # JWT token handling and RBAC helpers
│   ├── db/
│   │   └── database.py             # Database connection, schemas, and initial seed
│   └── web/
│       └── static/
│           ├── app.js              # Frontend application logic
│           ├── index.html          # Single-page interface
│           └── styles.css          # Styles and print layouts
├── data/
│   └── bazaarly.db                 # SQLite database
├── tests/
│   └── test_ecommerce_flows.py     # End-to-end flow tests
├── requirements.txt
├── run.py
└── README.md
```

## License

MIT
