import secrets
import logging
import grpc
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from src.redis_client import redis_client
from src.security.haabs_security import (
    enforce_rate_limit,
    audit_ledger,
)
from src.proto import hag_pb2, hag_pb2_grpc

logger = logging.getLogger("hag.api.sms")

sms_router = APIRouter(prefix="/sms", tags=["SMS OTP"])


# Request / Response Schemas
class SmsOtpSendRequest(BaseModel):
    phone: str = Field(..., description="Target phone number in international E.164 format or digits", example="+1234567890")


class SmsOtpSendResponse(BaseModel):
    success: bool
    message: str
    otp: Optional[str] = Field(None, description="Returned OTP code (in production sent via SMS provider)")


class SmsOtpVerifyRequest(BaseModel):
    phone: str = Field(..., description="Phone number associated with OTP", example="+1234567890")
    code: str = Field(..., description="6-digit OTP code to verify", example="123456")


class SmsOtpVerifyResponse(BaseModel):
    success: bool
    message: str


def generate_6digit_otp() -> str:
    """Generate cryptographically secure 6-digit numeric OTP."""
    return f"{secrets.randbelow(1000000):06d}"


@sms_router.post(
    "/otp/send",
    response_model=SmsOtpSendResponse,
    summary="Send SMS OTP",
    description="Generates a 6-digit OTP, stores it in Redis with a 5-minute TTL, and rate limits to 5 requests per hour per phone.",
)
async def send_sms_otp(payload: SmsOtpSendRequest):
    phone = payload.phone.strip()
    if not phone or len(phone) < 5:
        raise HTTPException(status_code=400, detail="Invalid phone number format.")

    # Rate limiting: 5 OTP requests/hour per phone number
    await enforce_rate_limit(f"phone:{phone}", limit=5, window_seconds=3600)

    # Generate 6-digit OTP
    otp_code = generate_6digit_otp()

    # Store in Redis (key: otp:phone, TTL: 300 seconds)
    stored = await redis_client.set_otp(phone, otp_code, ttl=300)
    if not stored:
        logger.error("Failed to store OTP in Redis for phone %s", phone)
        raise HTTPException(status_code=500, detail="Failed to generate OTP. Internal storage error.")

    audit_ledger.log_event("SMS_OTP_SENT", {"phone": phone})
    logger.info("SMS OTP sent to %s", phone)

    return SmsOtpSendResponse(
        success=True,
        message="OTP sent successfully via SMS",
        otp=otp_code,
    )


@sms_router.post(
    "/otp/verify",
    response_model=SmsOtpVerifyResponse,
    summary="Verify SMS OTP",
    description="Checks Redis for stored 6-digit OTP. On successful match, deletes the key and returns success.",
)
async def verify_sms_otp(payload: SmsOtpVerifyRequest):
    phone = payload.phone.strip()
    code = payload.code.strip()

    if not phone or not code:
        raise HTTPException(status_code=400, detail="Phone and code are required.")

    cached_otp = await redis_client.get_otp(phone)
    if cached_otp and cached_otp == code:
        # Delete on success
        await redis_client.delete_otp(phone)
        audit_ledger.log_event("SMS_OTP_VERIFIED_SUCCESS", {"phone": phone})
        logger.info("SMS OTP verified successfully for %s", phone)
        return SmsOtpVerifyResponse(
            success=True,
            message="OTP verified successfully",
        )

    audit_ledger.log_event("SMS_OTP_VERIFIED_FAILED", {"phone": phone, "submitted_code": code})
    logger.warning("SMS OTP verification failed for %s", phone)
    return SmsOtpVerifyResponse(
        success=False,
        message="Invalid or expired OTP code",
    )


# ==========================================
# gRPC Service Implementation
# ==========================================
class HagOtpGrpcServicer(hag_pb2_grpc.HagOtpServiceServicer):

    async def SendOtp(self, request, context):
        phone = request.phone.strip()
        if not phone:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Phone number is required")
            return hag_pb2.SendOtpResponse(success=False, message="Phone number is required")

        try:
            # Enforce rate limit (5 req/hour)
            await enforce_rate_limit(f"phone:{phone}", limit=5, window_seconds=3600)
        except HTTPException as e:
            context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
            context.set_details(e.detail)
            return hag_pb2.SendOtpResponse(success=False, message=e.detail)

        otp_code = generate_6digit_otp()
        stored = await redis_client.set_otp(phone, otp_code, ttl=300)
        if not stored:
            context.set_code(grpc.StatusCode.INTERNAL)
            return hag_pb2.SendOtpResponse(success=False, message="Storage error")

        audit_ledger.log_event("GRPC_SMS_OTP_SENT", {"phone": phone})
        return hag_pb2.SendOtpResponse(
            success=True,
            message="OTP sent successfully via gRPC",
            otp=otp_code,
        )

    async def VerifyOtp(self, request, context):
        phone = request.phone.strip()
        code = request.code.strip()

        if not phone or not code:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            return hag_pb2.VerifyOtpResponse(success=False, message="Phone and code are required")

        cached_otp = await redis_client.get_otp(phone)
        if cached_otp and cached_otp == code:
            await redis_client.delete_otp(phone)
            audit_ledger.log_event("GRPC_SMS_OTP_VERIFIED_SUCCESS", {"phone": phone})
            return hag_pb2.VerifyOtpResponse(success=True, message="OTP verified successfully")

        audit_ledger.log_event("GRPC_SMS_OTP_VERIFIED_FAILED", {"phone": phone})
        return hag_pb2.VerifyOtpResponse(success=False, message="Invalid or expired OTP code")
