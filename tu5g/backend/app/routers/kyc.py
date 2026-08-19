"""
KYC (Know Your Customer) Verification Router for the TU5G platform.
Handles KYC document submissions, status checking, and administrative approval/rejection pipelines.
Integrates with the extended authentication state in auth_ext.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.routers.auth_ext import _user_ext_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kyc", tags=["KYC Verification Engine"])

# =====================================================================
# In-Memory Database for KYC Applications
# =====================================================================
_kyc_applications_db: Dict[str, Dict[str, Any]] = {}


# =====================================================================
# Pydantic Schemas
# =====================================================================
class KYCSubmitRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100, description="Legal full name matching ID document")
    id_type: str = Field(..., description="Type of document, e.g., 'passport', 'national_id', 'drivers_license'")
    id_number: str = Field(..., min_length=4, max_length=50, description="Unique number/code of the submitted ID")
    address: str = Field(..., min_length=5, description="Residential or billing address")
    document_url: str = Field(..., description="Secure object URL or base64 data representing the uploaded ID document")


class KYCSubmitResponse(BaseModel):
    kyc_id: str = Field(..., description="Generated KYC application tracking reference ID")
    status: str = Field("pending", description="Current application status: pending, approved, rejected")
    submitted_at: datetime = Field(...)


class KYCStatusResponse(BaseModel):
    user_id: int = Field(...)
    kyc_status: str = Field(...)
    application_id: Optional[str] = Field(None, description="Current application ID if exists")
    rejection_reason: Optional[str] = Field(None, description="Reason for rejection, if applicable")
    updated_at: datetime = Field(...)


class KYCApplicationDetail(BaseModel):
    kyc_id: str = Field(...)
    user_id: int = Field(...)
    full_name: str = Field(...)
    id_type: str = Field(...)
    id_number: str = Field(...)
    address: str = Field(...)
    document_url: str = Field(...)
    status: str = Field(...)
    rejection_reason: Optional[str] = None
    submitted_at: datetime = Field(...)
    reviewed_at: Optional[datetime] = None


class KYCVerifyRequest(BaseModel):
    status: str = Field(..., description="Approval status: 'approved' or 'rejected'")
    rejection_reason: Optional[str] = Field(None, description="Mandatory if status is 'rejected'")


class KYCVerifyResponse(BaseModel):
    kyc_id: str = Field(...)
    status: str = Field(...)
    message: str = Field(...)
    reviewed_at: datetime = Field(...)


# =====================================================================
# Utility Helpers
# =====================================================================
def verify_admin_role(user: Dict[str, Any]) -> None:
    """Helper to enforce admin or super_admin permissions."""
    role = user.get("role")
    if role not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: This operation requires administrative privileges."
        )


# =====================================================================
# Endpoints
# =====================================================================
@router.post("/submit", response_model=KYCSubmitResponse, status_code=status.HTTP_201_CREATED)
async def submit_kyc(
    request_in: KYCSubmitRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Submit legally required KYC credentials.
    Sets user KYC status to 'pending' and registers application for administrative review.
    Protected: Requires valid Bearer Token.
    """
    user_id = current_user["id"]
    
    # Check if there's already a pending or verified application
    for app in _kyc_applications_db.values():
        if app["user_id"] == user_id and app["status"] in ("pending", "approved"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You already have a KYC application in state '{app['status']}'."
            )

    kyc_id = f"KYC-{uuid.uuid4().hex[:12].upper()}"
    now = datetime.now(timezone.utc)
    
    # Store KYC application details
    _kyc_applications_db[kyc_id] = {
        "kyc_id": kyc_id,
        "user_id": user_id,
        "full_name": request_in.full_name,
        "id_type": request_in.id_type,
        "id_number": request_in.id_number,
        "address": request_in.address,
        "document_url": request_in.document_url,
        "status": "pending",
        "rejection_reason": None,
        "submitted_at": now,
        "reviewed_at": None
    }

    # Update state in extended auth db
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
    
    _user_ext_db[user_id]["kyc_status"] = "pending"

    logger.info(f"KYC application {kyc_id} submitted by user {user_id}")
    return {
        "kyc_id": kyc_id,
        "status": "pending",
        "submitted_at": now
    }


@router.get("/status", response_model=KYCStatusResponse, status_code=status.HTTP_200_OK)
async def get_kyc_status(current_user: Dict[str, Any] = Depends(get_current_user)) -> Any:
    """
    Retrieve current customer's KYC verification status.
    Protected: Requires valid Bearer Token.
    """
    user_id = current_user["id"]
    
    # Retrieve extended state
    ext_state = _user_ext_db.get(user_id, {
        "kyc_status": "not_submitted"
    })
    kyc_status = ext_state.get("kyc_status", "not_submitted")

    # Find matching application
    application_id = None
    rejection_reason = None
    for app_id, app in _kyc_applications_db.items():
        if app["user_id"] == user_id:
            application_id = app_id
            rejection_reason = app.get("rejection_reason")
            # Return newest matched
            break

    return {
        "user_id": user_id,
        "kyc_status": kyc_status,
        "application_id": application_id,
        "rejection_reason": rejection_reason,
        "updated_at": datetime.now(timezone.utc)
    }


@router.get("/pending", response_model=List[KYCApplicationDetail], status_code=status.HTTP_200_OK)
async def get_pending_kyc_applications(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    List all KYC verification applications with 'pending' status.
    Protected: Requires administrative credentials.
    """
    verify_admin_role(current_user)

    pending_apps = []
    for app in _kyc_applications_db.values():
        if app["status"] == "pending":
            pending_apps.append(app)
            
    return pending_apps


@router.post("/{kyc_id}/verify", response_model=KYCVerifyResponse, status_code=status.HTTP_200_OK)
async def verify_kyc_application(
    kyc_id: str,
    request_in: KYCVerifyRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Approve or reject a submitted KYC application.
    Updates extended user KYC status accordingly.
    Protected: Requires administrative credentials.
    """
    verify_admin_role(current_user)

    if kyc_id not in _kyc_applications_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"KYC Application with ID {kyc_id} was not found."
        )

    app = _kyc_applications_db[kyc_id]
    if app["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"KYC Application is already in a completed '{app['status']}' state."
        )

    action_status = request_in.status.lower()
    if action_status not in ("approved", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status parameter. Must be 'approved' or 'rejected'."
        )

    if action_status == "rejected" and not request_in.rejection_reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A rejection reason must be provided when rejecting a KYC application."
        )

    now = datetime.now(timezone.utc)
    app["status"] = action_status
    app["rejection_reason"] = request_in.rejection_reason if action_status == "rejected" else None
    app["reviewed_at"] = now
    
    _kyc_applications_db[kyc_id] = app

    # Propagate verification to extended auth db
    user_id = app["user_id"]
    target_status = "verified" if action_status == "approved" else "rejected"
    if user_id in _user_ext_db:
        _user_ext_db[user_id]["kyc_status"] = target_status
    else:
        _user_ext_db[user_id] = {
            "phone": "+984799000000",
            "email_verified": True,
            "phone_verified": True,
            "email_otp": None,
            "phone_otp": None,
            "forgot_password_otp": None,
            "kyc_status": target_status,
            "last_otp_sent_at": None
        }

    logger.info(f"KYC Application {kyc_id} reviewed and {action_status} by admin {current_user['id']}")
    return {
        "kyc_id": kyc_id,
        "status": action_status,
        "message": f"The KYC application has been successfully {action_status}.",
        "reviewed_at": now
    }


@router.get("/{kyc_id}", response_model=KYCApplicationDetail, status_code=status.HTTP_200_OK)
async def get_kyc_application_detail(
    kyc_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Retrieve full details of a specific KYC application.
    Protected: Requires administrative credentials.
    """
    verify_admin_role(current_user)

    if kyc_id not in _kyc_applications_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"KYC Application with ID {kyc_id} was not found."
        )

    return _kyc_applications_db[kyc_id]
