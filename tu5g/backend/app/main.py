import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import database components
from app.database import engine
from app.models import Base

# Import production middleware components
from app.middleware import (
    RequestIDMiddleware,
    SecureHeadersMiddleware,
    RateLimitMiddleware,
    AuditLoggingMiddleware
)

# Import all required routers (original and extended)
from app.routers import (
    admin, customers, router as general_router, esim, ai_characters, chat, holo, telemetry,
    auth_ext, kyc, esim_store, payments, hmail, governance, super_admin
)

# Initialize slowapi rate limiter instance
limiter = Limiter(key_func=get_remote_address, default_limits=["10/second"])

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Asynchronous lifespan manager for FastAPI.
    Handles startup events (like database table creation) and clean shutdown.
    """
    # Startup: Initialize DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Clean shutdown operations can go here if needed


# Initialize FastAPI application
app = FastAPI(
    title="TU5G Backend Service",
    description="Production-ready FastAPI backend for the TU5G platform with HAABS security.",
    version="1.0.0",
    lifespan=lifespan
)

# Set rate limiter in app state and add standard handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Allowed origins defined via ALLOWED_ORIGINS env var (comma-separated list)
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost,http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8000")
origins = [origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()]

# Register Production HAABS Middlewares
# 1. Request ID Middleware (outermost: assigns/forwards unique request ID)
app.add_middleware(RequestIDMiddleware)

# 2. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Secure Headers Middleware (HAABS compliance: CSP, HSTS, X-Frame-Options, etc.)
app.add_middleware(SecureHeadersMiddleware)

# 4. Sliding Window Rate Limiting Middleware (IP-based, route-specific for /auth, /esim, /ai)
app.add_middleware(RateLimitMiddleware)

# 5. Audit Logging Middleware (structured JSON logging for all requests & responses)
app.add_middleware(AuditLoggingMiddleware)

# Serve static files and templates for the frontend
base_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.abspath(os.path.join(base_dir, "..", "..", "frontend", "static"))
templates_dir = os.path.abspath(os.path.join(base_dir, "..", "..", "frontend", "templates"))

# Mount static files (served at /static)
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize Jinja2 Templates
if not os.path.exists(templates_dir):
    os.makedirs(templates_dir, exist_ok=True)
templates = Jinja2Templates(directory=templates_dir)

# Initialize and instrument Prometheus metrics at /metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Include all required API routers (original and extended)
app.include_router(admin.router)
app.include_router(customers.router)
app.include_router(general_router.router)
app.include_router(esim.router)
app.include_router(ai_characters.router)
app.include_router(chat.router)
app.include_router(holo.router)
app.include_router(telemetry.router)

# Mount the 7 extended routers
app.include_router(auth_ext.router)
app.include_router(kyc.router)
app.include_router(esim_store.router)
app.include_router(payments.router)
app.include_router(hmail.router)
app.include_router(governance.router)
app.include_router(super_admin.router)

@app.get("/health", tags=["health"])
@limiter.limit("10/second")
async def health_check(request: Request):
    """
    Liveness and readiness probe.
    Decorated with rate-limiting (10 req/s) to prevent DDoS attacks on health probes.
    """
    return {
        "status": "healthy",
        "database": "connected",
        "version": "1.0.0"
    }

@app.get("/", tags=["root"])
async def root_index(request: Request):
    """
    Render index HTML or return JSON fallback.
    """
    index_file = os.path.join(templates_dir, "index.html")
    if os.path.exists(index_file):
        return templates.TemplateResponse("index.html", {"request": request})
    return {"message": "Welcome to TU5G FastAPI Backend Service. Please check /docs for the API reference."}
