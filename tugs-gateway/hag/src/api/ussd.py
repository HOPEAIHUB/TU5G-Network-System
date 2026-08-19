"""
USSD OTP API — Handle USSD-based OTP verification.
USSD code format: *984*79*OTP#
"""

import os
import logging
from fastapi import APIRouter, Request
from pydantic import BaseModel

from security.haabs_security import haabs_rate_limit
from redis_client import RedisClient

router = APIRouter()
logger = logging.getLogger(__name__)

class UssdSessionRequest(BaseModel):
    phone: str
    session_id: str

class UssdVerifyRequest(BaseModel):
    phone: str
    session_id: str
    ussd_input: str  # The OTP entered via USSD

@router.post("/session")
@haabs_rate_limit(max_requests=5, window=3600)
async def start_ussd_session(req: UssdSessionRequest, request: Request):
    """Start a USSD session for OTP delivery."""
    redis: RedisClient = request.app.state.redis
    
    # Generate 6-digit OTP
    import random
    otp_code = str(random.randint(100000, 999999))
    
    # Store OTP in Redis with 5-min TTL
    key = f"otp:ussd:{req.phone}"
    await redis.setex(key, 300, otp_code)
    
    # Store session
    session_key = f"ussd:session:{req.session_id}"
    await redis.setex(session_key, 300, req.phone)
    
    logger.info(f"USSD OTP session started for {req.phone}")
    
    return {
        "session_id": req.session_id,
        "message": "Dial *984*79*<OTP># to verify",
        "expires_in": 300,
    }

@router.post("/verify")
async def verify_ussd(req: UssdVerifyRequest, request: Request):
    """Verify USSD OTP response."""
    redis: RedisClient = request.app.state.redis
    
    # Get stored OTP
    key = f"otp:ussd:{req.phone}"
    stored_otp = await redis.get(key)
    
    if not stored_otp:
        return {"success": False, "message": "OTP expired or not found"}
    
    # Verify session
    session_key = f"ussd:session:{req.session_id}"
    session_phone = await redis.get(session_key)
    
    if not session_phone or session_phone != req.phone:
        return {"success": False, "message": "Invalid or expired session"}
    
    # Extract OTP from USSD input (format: *984*79*OTP#)
    ussd_input = req.ussd_input.strip()
    if ussd_input.startswith("*984*79*") and ussd_input.endswith("#"):
        entered_otp = ussd_input[8:-1]
    else:
        entered_otp = ussd_input
    
    if entered_otp == stored_otp:
        # Delete used OTP and session
        await redis.delete(key)
        await redis.delete(session_key)
        logger.info(f"USSD OTP verified for {req.phone}")
        return {"success": True, "message": "OTP verified successfully"}
    else:
        return {"success": False, "message": "Invalid OTP"}
