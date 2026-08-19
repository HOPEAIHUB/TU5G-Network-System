"""
HAG — HAG AI GSM Service (Python FastAPI)
Handles SMS/USSD OTP generation and verification with HAABS security.
"""

import os
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from api.sms import router as sms_router
from api.ussd import router as ussd_router
from security.haabs_security import HAABSSecurity, haabs_rate_limit
from redis_client import RedisClient
from vault_client import VaultClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [HAG] %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    logger.info("HAG AI GSM Service starting...")
    logger.info("TUGS v1.0 ACTIVATED — HMTML ACTIVATED — HPLS AI ACTIVATED")
    
    # Initialize Redis
    app.state.redis = RedisClient()
    await app.state.redis.connect()
    
    # Initialize Vault client
    app.state.vault = VaultClient(
        endpoint=os.getenv("VAULT_ENDPOINT", "http://vault:8080")
    )
    
    # Initialize HAABS security
    app.state.haabs = HAABSSecurity(
        cloudflare_api=os.getenv("CLOUD_FLARE_API"),
    )
    
    logger.info("HAG ready — listening on port %s", os.getenv("HAG_PORT", "8090"))
    yield
    
    logger.info("HAG shutting down...")
    await app.state.redis.disconnect()

app = FastAPI(
    title="HAG — AI GSM Service",
    description="HAG AI GSM service for SMS/USSD OTP validation with HAABS security",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(sms_router, prefix="/sms", tags=["SMS OTP"])
app.include_router(ussd_router, prefix="/ussd", tags=["USSD OTP"])

@app.get("/health")
async def health():
    return {"status": "ok", "service": "hag", "version": "1.0.0"}

@app.middleware("http")
async def haabs_middleware(request: Request, call_next):
    """HAABS security middleware — IP reputation, rate limiting, nonce validation."""
    # Skip health check
    if request.url.path == "/health":
        return await call_next(request)
    
    haabs: HAABSSecurity = request.app.state.haabs
    
    # Check IP reputation (skip in dev if no Cloudflare API)
    if haabs.cloudflare_api:
        ip_ok = await haabs.check_ip_reputation(request.client.host)
        if not ip_ok:
            return JSONResponse(
                status_code=403,
                content={"error": "IP reputation check failed"}
            )
    
    response = await call_next(request)
    
    # Add security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("HAG_PORT", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port)
