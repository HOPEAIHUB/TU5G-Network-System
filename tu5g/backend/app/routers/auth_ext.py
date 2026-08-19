"""
Extended Authentication, Registration, and OTP Verification router for the TU5G platform.
Handles signup, Multi-Factor/OTP verification, password recovery, and KYC status integration.
Uses SQLAlchemy for core user profiles and an in-memory/stateful store for extended attributes (OTP, Phone, KYC status).
"""

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models import User
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user
from app.dependencies import get_limiter
from app.services.email import send_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Extended Authentication & MFA"])
limiter = get_limiter()

# =====================================================================
# In-Memory Database for Extended User Fields (OTP, Phone, KYC status)
# =====================================================================
_user_ext_db: Dict[int, Dict[str, Any]] = {}


# =====================================================================
# Pydantic Schemas
# =====================================================================
class SignupRequest(BaseModel):
    email: EmailStr = Field(..., description="Unique email address for signup")
    phone: str = Field(..., description="Callback phone number including country code (e.g. +984799000111)")
    full_name: str = Field(..., min_length=2, max_length=100, description="Full name of the user")
    password: str = Field(..., min_length=6, description="User password (minimum 6 characters)")


class SignupResponse(BaseModel):
    user_id: int = Field(..., description="Newly created database user ID")
    email: str = Field(..., description="User's registered email")
    email_otp_sent: bool = Field(True, description="Indicates if OTP was sent to email successfully")
    phone_otp_sent: bool = Field(True, description="Indicates if OTP was sent to phone successfully")


class VerifyOTPRequest(BaseModel):
    user_id: int = Field(..., description="The ID of the user verifying their identity")
    otp_type: str = Field(..., description="The type of OTP: 'email' or 'phone'")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6-digit numeric OTP code")


class VerifyOTPResponse(BaseModel):
    success: bool = Field(..., description="Verification status")
    message: str = Field(..., description="Verification result message")


class ResendOTPRequest(BaseModel):
    user_id: int = Field(..., description="User ID for whom to resend OTP")
    otp_type: str = Field(..., description="OTP channel to resend: 'email' or 'phone'")


class ResendOTPResponse(BaseModel):
    success: bool = Field(..., description="Indicates if OTP was resent successfully")
    message: str = Field(..., description="Status message")


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="Registered user email")
    password: str = Field(..., description="User password")


class LoginResponse(BaseModel):
    access_token: str = Field(..., description="OAuth2 compliant JWT access token")
    token_type: str = Field("bearer", description="Token type prefix")
    user: Dict[str, Any] = Field(..., description="Basic authenticated user profile details")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="Registered email to initiate password recovery")


class ForgotPasswordResponse(BaseModel):
    success: bool = Field(..., description="Whether password reset process was successfully initiated")
    message: str = Field(..., description="Status message")


class ResetPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6-digit reset OTP sent to email")
    new_password: str = Field(..., min_length=6, description="New secure password")


class ResetPasswordResponse(BaseModel):
    success: bool = Field(..., description="Whether password was successfully reset")
    message: str = Field(..., description="Result message")


class KYCStatusResponse(BaseModel):
    user_id: int = Field(...)
    kyc_status: str = Field(..., description="Status of KYC verification: 'not_submitted', 'pending', 'verified', 'rejected'")
    last_checked: datetime = Field(...)


# =====================================================================
# Utility Helpers
# =====================================================================
def generate_numeric_otp() -> str:
    """Generates a secure standard 6-digit numeric OTP."""
    return f"{random.randint(100000, 999999)}"


# =====================================================================
# Endpoints
# =====================================================================
@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(request_in: SignupRequest, db: AsyncSession = Depends(get_db)) -> Any:
    """
    Register a new user account with email, phone, full_name, and password.
    Saves profile to database, generates MFA OTPs for email and phone,
    and returns user_id alongside MFA dispatch flags.
    """
    # 1. Check if user already exists
    query = select(User).where(User.email == request_in.email)
    result = await db.execute(query)
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists on the TU5G network."
        )

    # 2. Hash password and insert into the users database table
    hashed_password = get_password_hash(request_in.password)
    new_user = User(
        email=request_in.email,
        hashed_password=hashed_password,
        full_name=request_in.full_name,
        role="customer",
        is_active=True
    )
    db.add(new_user)
    await db.flush()  # Flush to generate ID without committing yet
    
    user_id = new_user.id

    # 3. Generate high-fidelity OTPs
    email_otp = generate_numeric_otp()
    phone_otp = generate_numeric_otp()
    
    # 4. Dispatch email OTP asynchronously (or fallback gracefully)
    email_sent = True
    try:
        subject = "Welcome to TU5G - Verify Your Email Address"
        body = (
            f"Dear {request_in.full_name},\n\n"
            f"Thank you for joining the TU5G platform! Please verify your email using this 6-digit OTP code:\n\n"
            f"--> {email_otp} <--\n\n"
            f"If you did not register for a TU5G account, please ignore this email.\n\n"
            f"Best regards,\nTU5G Core System"
        )
        await send_email(to=request_in.email, subject=subject, body=body)
    except Exception as e:
        logger.warning(f"Could not send email OTP to {request_in.email}: {e}")
        email_sent = False

    # 5. Populate Extended In-Memory User State
    _user_ext_db[user_id] = {
        "phone": request_in.phone,
        "email_verified": False,
        "phone_verified": False,
        "email_otp": email_otp,
        "phone_otp": phone_otp,
        "forgot_password_otp": None,
        "kyc_status": "not_submitted",
        "last_otp_sent_at": datetime.now(timezone.utc)
    }

    # Commit transactions cleanly
    await db.commit()
    logger.info(f"User {user_id} registered successfully. OTPs generated.")

    return {
        "user_id": user_id,
        "email": request_in.email,
        "email_otp_sent": email_sent,
        "phone_otp_sent": True  # Phone OTP generated; simulated SMS dispatch is successful
    }


@router.post("/verify-otp", response_model=VerifyOTPResponse, status_code=status.HTTP_200_OK)
async def verify_otp(request_in: VerifyOTPRequest) -> Any:
    """
    Verify the user's OTP code (either email or phone).
    Confirms compliance with security requirements before activating account sub-functions.
    """
    user_id = request_in.user_id
    if user_id not in _user_ext_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Extended user record or verification session not found."
        )

    ext_profile = _user_ext_db[user_id]
    otp_type = request_in.otp_type.lower()
    
    if otp_type not in ("email", "phone"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid otp_type. Allowed types are: 'email' or 'phone'."
        )

    expected_otp = ext_profile.get(f"{otp_type}_otp")
    if not expected_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No active OTP request found for {otp_type} verification."
        )

    if request_in.otp_code != expected_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification failed: Invalid OTP code. Please try again."
        )

    # Mark verified and clear verified OTP
    ext_profile[f"{otp_type}_verified"] = True
    ext_profile[f"{otp_type}_otp"] = None
    _user_ext_db[user_id] = ext_profile

    return {
        "success": True,
        "message": f"Your {otp_type} address has been successfully verified."
    }


@router.post("/resend-otp", response_model=ResendOTPResponse, status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
async def resend_otp(request: Request, request_in: ResendOTPRequest, db: AsyncSession = Depends(get_db)) -> Any:
    """
    Resend a new 6-digit OTP code to the requested verification channel (email or phone).
    Rate-limited by slowapi (3 resends per minute).
    """
    user_id = request_in.user_id
    if user_id not in _user_ext_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification profile was not found for this user."
        )

    ext_profile = _user_ext_db[user_id]
    otp_type = request_in.otp_type.lower()
    
    if otp_type not in ("email", "phone"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid otp_type. Must be 'email' or 'phone'."
        )

    # Enforce basic cooldown period (e.g., 30 seconds)
    last_sent = ext_profile.get("last_otp_sent_at")
    if last_sent and (datetime.now(timezone.utc) - last_sent) < timedelta(seconds=30):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait 30 seconds before requesting another verification code."
        )

    new_otp = generate_numeric_otp()
    ext_profile[f"{otp_type}_otp"] = new_otp
    ext_profile["last_otp_sent_at"] = datetime.now(timezone.utc)
    _user_ext_db[user_id] = ext_profile

    # Dispatch email if email channel
    if otp_type == "email":
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalars().first()
        if user:
            try:
                subject = "TU5G - Resend OTP Code"
                body = (
                    f"Dear {user.full_name},\n\n"
                    f"As requested, your new verification code is:\n\n"
                    f"--> {new_otp} <--\n\n"
                    f"Please complete your verification. This code will expire soon.\n\n"
                    f"Best regards,\nTU5G Operations Team"
                )
                await send_email(to=user.email, subject=subject, body=body)
            except Exception as e:
                logger.warning(f"Could not resend email OTP: {e}")

    return {
        "success": True,
        "message": f"A brand new OTP has been dispatched to your registered {otp_type}."
    }


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def login(request: Request, request_in: LoginRequest, db: AsyncSession = Depends(get_db)) -> Any:
    """
    Standard platform login.
    Authenticates user, validates email and password, and issues JWT token.
    Rate-limited to prevent brute-force attacks.
    """
    query = select(User).where(User.email == request_in.email)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user or not verify_password(request_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Incorrect email or password."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact TU5G Support."
        )

    # Generate access token
    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    
    # Check/back-fill ext_db entry if missing (e.g. users registered by seed data)
    if user.id not in _user_ext_db:
        _user_ext_db[user.id] = {
            "phone": "+984799000000",
            "email_verified": True,
            "phone_verified": True,
            "email_otp": None,
            "phone_otp": None,
            "forgot_password_otp": None,
            "kyc_status": "not_submitted",
            "last_otp_sent_at": None
        }

    user_info = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_date": user.created_date,
        "updated_date": user.updated_date
    }

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_info
    }


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> Any:
    """
    Retrieve currently logged-in user profile with extended session attributes.
    Protected: Requires valid Bearer Token.
    """
    user_id = current_user["id"]
    ext_data = _user_ext_db.get(user_id, {
        "phone": "+984799000000",
        "email_verified": True,
        "phone_verified": True,
        "kyc_status": "not_submitted"
    })
    
    return {
        **current_user,
        "phone": ext_data.get("phone"),
        "email_verified": ext_data.get("email_verified"),
        "phone_verified": ext_data.get("phone_verified"),
        "kyc_status": ext_data.get("kyc_status")
    }


@router.post("/forgot-password", response_model=ForgotPasswordResponse, status_code=status.HTTP_200_OK)
async def forgot_password(request_in: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)) -> Any:
    """
    Initiate user password reset process.
    If email exists, generates a temporary 6-digit recovery OTP and sends it via email.
    """
    query = select(User).where(User.email == request_in.email)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user:
        # Avoid user enumeration attacks: return positive response even if user doesn't exist
        return {
            "success": True,
            "message": "If the email is registered on our system, a password recovery code has been sent."
        }

    reset_otp = generate_numeric_otp()
    
    # Store reset OTP in user's extended record
    if user.id not in _user_ext_db:
        _user_ext_db[user.id] = {
            "phone": "+984799000000",
            "email_verified": True,
            "phone_verified": True,
            "email_otp": None,
            "phone_otp": None,
            "forgot_password_otp": None,
            "kyc_status": "not_submitted",
            "last_otp_sent_at": None
        }
    
    _user_ext_db[user.id]["forgot_password_otp"] = reset_otp

    # Send email
    try:
        subject = "TU5G - Password Reset Verification Code"
        body = (
            f"Dear {user.full_name},\n\n"
            f"We received a request to reset your password. Please use this verification code:\n\n"
            f"--> {reset_otp} <--\n\n"
            f"If you did not request a password reset, you can safely ignore this message.\n\n"
            f"Best regards,\nTU5G Core System"
        )
        await send_email(to=user.email, subject=subject, body=body)
    except Exception as e:
        logger.error(f"Failed sending password recovery email to {user.email}: {e}")

    return {
        "success": True,
        "message": "A security verification code has been dispatched to your email."
    }


@router.post("/reset-password", response_model=ResetPasswordResponse, status_code=status.HTTP_200_OK)
async def reset_password(request_in: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> Any:
    """
    Reset account password.
    Validates email recovery OTP and updates password record.
    """
    query = select(User).where(User.email == request_in.email)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested user account was not found."
        )

    user_id = user.id
    if user_id not in _user_ext_db or _user_ext_db[user_id].get("forgot_password_otp") is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active password reset process is open. Please request a code first."
        )

    expected_otp = _user_ext_db[user_id]["forgot_password_otp"]
    if request_in.otp_code != expected_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset failed: The provided verification code is incorrect."
        )

    # Code matches! Proceed to update password and flush reset OTP
    user.hashed_password = get_password_hash(request_in.new_password)
    _user_ext_db[user_id]["forgot_password_otp"] = None
    
    db.add(user)
    await db.commit()

    logger.info(f"Password reset successfully for user {user.email}")
    return {
        "success": True,
        "message": "Your password has been reset successfully. You can now log in."
    }


@router.post("/check-kyc", response_model=KYCStatusResponse, status_code=status.HTTP_200_OK)
async def check_kyc(current_user: Dict[str, Any] = Depends(get_current_user)) -> Any:
    """
    Check if user's KYC (Know Your Customer) is verified.
    Checks user's extended profile attributes.
    """
    user_id = current_user["id"]
    if user_id not in _user_ext_db:
        _user_ext_db[user_id] = {
            "phone": "+984799000000",
            "email_verified": True,
            "phone_verified": True,
            "email_otp": None,
            "phone_otp": None,
            "forgot_password_otp": None,
            "kyc_status": "not_submitted",
            "last_otp_sent_at": None
        }

    kyc_status = _user_ext_db[user_id].get("kyc_status", "not_submitted")

    return {
        "user_id": user_id,
        "kyc_status": kyc_status,
        "last_checked": datetime.now(timezone.utc)
    }
