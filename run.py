"""
Bazaarly Application Entry Point
Starts the FastAPI server with Uvicorn.
"""

import sys
import io
import argparse
import uvicorn

# Windows console encoding safeguard
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(description="Start Bazaarly Multi-Vendor eCommerce Platform Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8005, help="Port to listen on (default: 8005)")
    parser.add_argument("--reload", action="store_true", help="Enable live auto-reloading")
    args = parser.parse_args()

    print(f"================================================================")
    print(f"  🛒 Starting Bazaarly Multi-Vendor Platform on port {args.port}")
    print(f"  👉 Customer Storefront: http://localhost:{args.port}/")
    print(f"  📖 Interactive Swagger: http://localhost:{args.port}/docs")
    print(f"================================================================")

    uvicorn.run("bazaarly.api.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
