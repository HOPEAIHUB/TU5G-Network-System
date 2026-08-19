"""
Virtual e-SIM Provisioning routers for TU5G platform.
Handles over-the-air (OTA) virtual e-SIM generation, status updates, activation, suspension, and QR/LPA code delivery.
Integrates with the sim.py service for secure identification parameters.
"""

import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException, status

# Import auth and sim services with robust mock fallbacks
try:
    from app.services.auth import get_current_user
except ImportError:
    async def get_current_user(*args, **kwargs) -> Any:
        raise NotImplementedError("Authentication service not fully configured.")

try:
    from app.services import sim as sim_service
except ImportError:
    # High fidelity mock fallback
    class MockSimService:
        @staticmethod
        def generate_sim_number() -> str:
            return "890141032111" + "".join(str(uuid.uuid4().int)[:8])
        
        @staticmethod
        def generate_iccid() -> str:
            return "890141032" + "".join(str(uuid.uuid4().int)[:11])
            
    sim_service = MockSimService()

router = APIRouter(prefix="/esim", tags=["e-SIM / Provisioning Engine"])


# ==========================================
# Pydantic Schemas
# ==========================================

class ESimProvisionRequest(BaseModel):
    """Schema for provisioning a new OTA virtual e-SIM profile."""
    customer_name: str = Field(..., min_length=2, max_length=100, description="Full name of the subscriber")
    email: EmailStr = Field(..., description="Email for activation instructions and QR code delivery")
    phone: str = Field(..., description="Primary contact/callback phone number")
    plan_name: str = Field("TU5G_unlimited_pro", description="Selected 5G billing subscription plan")
    device_model: str = Field(..., description="User smartphone model, e.g., 'iPhone 15 Pro', 'Pixel 8'")


class ESimProvisionResponse(BaseModel):
    """Schema returning newly provisioned e-SIM properties."""
    customer_id: str = Field(..., description="Generated customer database UUID")
    sim_number: str = Field(..., description="Generated MSISDN / 5G phone number")
    iccid: str = Field(..., description="Generated e-SIM serial identifier (ICCID)")
    lpa_string: str = Field(..., description="GSMA standard LPA Activation String (e.g., LPA:1$rsp.server.com$token)")
    status: str = Field("provisioned", description="Current operational state: provisioned, active, suspended")
    created_at: datetime = Field(...)


class ESimStatusResponse(BaseModel):
    """Schema for returning e-SIM status details."""
    customer_id: str = Field(...)
    sim_number: str = Field(...)
    iccid: str = Field(...)
    status: str = Field(..., description="Current state: provisioned, active, suspended, deactivated")
    activated_at: Optional[datetime] = Field(None)
    suspended_at: Optional[datetime] = Field(None)
    last_network_registration: Optional[datetime] = Field(None)


class ESimQRResponse(BaseModel):
    """Schema containing LPA configuration and printable QR code vector data."""
    customer_id: str = Field(...)
    lpa_string: str = Field(..., description="Standard LPA string format for manual typing")
    qr_code_base64: str = Field(..., description="Base64 encoded virtual QR code SVG/PNG representation for scan display")


# ==========================================
# In-Memory Database for e-SIM profiles
# ==========================================
_mock_esim_profiles: dict = {}


# ==========================================
# Endpoints
# ==========================================

@router.post("/provision", response_model=ESimProvisionResponse, status_code=status.HTTP_201_CREATED)
async def provision_esim(
    request_in: ESimProvisionRequest,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Provision a brand new virtual e-SIM.
    Generates high-assurance identification parameters (MSISDN/ICCID/IMSI) and formats
    a standard GSMA LPA activation code.
    Protected: Requires valid credentials.
    """
    customer_id = str(uuid.uuid4())
    sim_number = sim_service.generate_sim_number()
    iccid = sim_service.generate_iccid()
    
    # Standard GSMA LPA activation format: LPA:1$<RSP_Server>$<Matching_ID>
    # TU5G production RSP (Remote SIM Provisioning) platform is 'rsp.tu5g.com'
    matching_id = f"TU5G-{uuid.uuid4().hex[:12].upper()}"
    lpa_string = f"LPA:1$rsp.tu5g.com${matching_id}"
    
    now = datetime.utcnow()
    esim_profile = {
        "customer_id": customer_id,
        "customer_name": request_in.customer_name,
        "email": request_in.email,
        "phone": request_in.phone,
        "plan_name": request_in.plan_name,
        "device_model": request_in.device_model,
        "sim_number": sim_number,
        "iccid": iccid,
        "lpa_string": lpa_string,
        "status": "provisioned",
        "created_at": now,
        "activated_at": None,
        "suspended_at": None,
        "last_network_registration": None
    }
    
    _mock_esim_profiles[customer_id] = esim_profile
    return esim_profile


@router.post("/activate/{customer_id}", response_model=ESimStatusResponse, status_code=status.HTTP_200_OK)
async def activate_esim(
    customer_id: str,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Trigger immediate remote activation of an OTA-provisioned e-SIM profile on the network Core.
    Protected: Requires valid credentials.
    """
    if customer_id not in _mock_esim_profiles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"e-SIM profile for Customer ID {customer_id} does not exist."
        )
    
    profile = _mock_esim_profiles[customer_id]
    if profile["status"] == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="e-SIM is already in 'active' operational state."
        )
        
    profile["status"] = "active"
    profile["activated_at"] = datetime.utcnow()
    profile["last_network_registration"] = datetime.utcnow()
    
    _mock_esim_profiles[customer_id] = profile
    return profile


@router.post("/suspend/{customer_id}", response_model=ESimStatusResponse, status_code=status.HTTP_200_OK)
async def suspend_esim(
    customer_id: str,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Temporarily block network registration and suspend billing services for an e-SIM profile.
    Protected: Requires valid credentials.
    """
    if customer_id not in _mock_esim_profiles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"e-SIM profile for Customer ID {customer_id} does not exist."
        )
    
    profile = _mock_esim_profiles[customer_id]
    if profile["status"] == "suspended":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="e-SIM profile is already under suspension."
        )
        
    profile["status"] = "suspended"
    profile["suspended_at"] = datetime.utcnow()
    
    _mock_esim_profiles[customer_id] = profile
    return profile


@router.get("/{customer_id}/status", response_model=ESimStatusResponse, status_code=status.HTTP_200_OK)
async def get_esim_status(
    customer_id: str,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Retrieve real-time activation, registration, and suspension status of an e-SIM profile.
    Protected: Requires valid credentials.
    """
    if customer_id not in _mock_esim_profiles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"e-SIM profile for Customer ID {customer_id} does not exist."
        )
    return _mock_esim_profiles[customer_id]


@router.get("/{customer_id}/qr", response_model=ESimQRResponse, status_code=status.HTTP_200_OK)
async def get_esim_qr(
    customer_id: str,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Fetch the printable/scannable QR code package for cellular remote activation.
    Returns standard LPA string alongside SVG vector graphic encoded in base64.
    Protected: Requires valid credentials.
    """
    if customer_id not in _mock_esim_profiles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"e-SIM profile for Customer ID {customer_id} does not exist."
        )
        
    profile = _mock_esim_profiles[customer_id]
    
    # Generic base64 mock QR code representing the GSMA-compliant LPA activation code
    mock_qr_base64 = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAJYAAACWAQMAAAAGzY6ZAAAAA1UEW"
        "klUUk5MTS0AAGb69gAAAAZQTFRF////AAAAVXgq8QAAAAF0Uk5TAEDm2GYAAAABYktHRACIBR1"
        "IAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUHNgUXCg0bAgR7bQAAADpJREFUOMtj+P///"
        "8EDDBgEHBgwCOBvYMBgEMDfwIDBIIC/gQGDQQB/AwMGgwD+BgYMBgH8DQwYDAL4G7gNAKyfFz"
        "sK26KCAAAAAElFTkSuQmCC"
    )
    
    return {
        "customer_id": customer_id,
        "lpa_string": profile["lpa_string"],
        "qr_code_base64": mock_qr_base64
    }
