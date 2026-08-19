"""
E-SIM Store & Number Selection Router for the TU5G platform.
Handles browsing phone numbers, reservations, plan subscription, e-SIM provisioning, 
lifecycle management (activation, suspension), and application for premium number benefits.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.services import sim as sim_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/esim-store", tags=["e-SIM Store & Provisioning Engine"])

# =====================================================================
# Mock Store Databases (Phone Numbers, Plans, Profiles, Reservations)
# =====================================================================
_available_numbers: Dict[str, Dict[str, Any]] = {
    "+984799000111": {"number": "+984799000111", "category": "platinum", "price": 300.00, "status": "available"},
    "+984799000777": {"number": "+984799000777", "category": "royal", "price": 1000.00, "status": "available"},
    "+984799111222": {"number": "+984799111222", "category": "gold", "price": 50.00, "status": "available"},
    "+984799555666": {"number": "+984799555666", "category": "premium", "price": 150.00, "status": "available"},
    "+984799222333": {"number": "+984799222333", "category": "standard", "price": 0.00, "status": "available"},
    "+984799333444": {"number": "+984799333444", "category": "standard", "price": 0.00, "status": "available"},
    "+984799444555": {"number": "+984799444555", "category": "standard", "price": 0.00, "status": "available"},
}

_data_plans: List[Dict[str, Any]] = [
    {
        "plan_id": "tu5g_core",
        "name": "TU5G Core Plan",
        "data_limit": "10 GB",
        "speed": "5G standard (100 Mbps)",
        "price": 15.00,
        "validity_days": 30
    },
    {
        "plan_id": "tu5g_unlimited_pro",
        "name": "TU5G Unlimited Pro",
        "data_limit": "Unlimited",
        "speed": "5G Ultra Wideband (1 Gbps)",
        "price": 45.00,
        "validity_days": 30
    },
    {
        "plan_id": "tu5g_holo_elite",
        "name": "TU5G Holographic Elite",
        "data_limit": "Unlimited + Dedicated Holo-Stream Bandwidth",
        "speed": "Next-Gen Quantum Core Speed (2.5 Gbps)",
        "price": 85.00,
        "validity_days": 30
    }
]

# Schema: number -> {"user_id": int, "expires_at": datetime}
_number_reservations: Dict[str, Dict[str, Any]] = {}

# Schema: customer_id -> esim_profile_dict
_esim_store_profiles: Dict[str, Dict[str, Any]] = {}

# Schema: user_id -> free_premium_application_dict
_free_premium_applications: Dict[int, Dict[str, Any]] = {}


# =====================================================================
# Pydantic Schemas
# =====================================================================
class NumberDetail(BaseModel):
    number: str = Field(..., description="Phone number")
    category: str = Field(..., description="Category: 'standard', 'gold', 'premium', 'platinum', 'royal'")
    price: float = Field(..., description="Cost of the number in USD")
    status: str = Field(..., description="Availability status: 'available', 'reserved', 'sold'")


class NumberListResponse(BaseModel):
    numbers: List[NumberDetail] = Field(...)
    total_count: int = Field(...)
    page: int = Field(...)
    per_page: int = Field(...)


class ReserveNumberResponse(BaseModel):
    number: str = Field(...)
    reserved_by: int = Field(...)
    expires_at: datetime = Field(..., description="MFA verification cooldown deadline")
    message: str = Field(...)


class ESimProvisionRequest(BaseModel):
    number: str = Field(..., description="The reserved or standard phone number to provision")
    plan_id: str = Field(..., description="The selected data plan identifier")
    user_id: int = Field(..., description="The user associated with the profile")


class ESimProvisionResponse(BaseModel):
    customer_id: str = Field(..., description="Generated e-SIM subscriber ID")
    sim_number: str = Field(..., description="Assigned phone number")
    iccid: str = Field(..., description="Generated standard ICCID")
    lpa_string: str = Field(..., description="GSMA standard LPA activation configuration")
    status: str = Field("provisioned", description="Provisioned eSIM operational state")
    created_at: datetime = Field(...)


class DataPlanResponse(BaseModel):
    plan_id: str = Field(...)
    name: str = Field(...)
    data_limit: str = Field(...)
    speed: str = Field(...)
    price: float = Field(...)
    validity_days: int = Field(...)


class ESimStatusResponse(BaseModel):
    customer_id: str = Field(...)
    sim_number: str = Field(...)
    iccid: str = Field(...)
    status: str = Field(..., description="State: provisioned, active, suspended, deactivated")
    activated_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    last_network_registration: Optional[datetime] = None


class ESimQRResponse(BaseModel):
    customer_id: str = Field(...)
    lpa_string: str = Field(..., description="Standard LPA registration string")
    qr_code_base64: str = Field(..., description="Scannable base64 image containing the profile definition")


class FreePremiumRequest(BaseModel):
    category: str = Field(..., description="Desired number tier, e.g. gold, premium, platinum")
    reason: str = Field(..., min_length=10, description="Detailed reason for applying for a free premium number")


class FreePremiumResponse(BaseModel):
    application_id: str = Field(...)
    user_id: int = Field(...)
    category: str = Field(...)
    reason: str = Field(...)
    status: str = Field("pending", description="Status: 'pending', 'approved', 'rejected'")
    submitted_at: datetime = Field(...)


# =====================================================================
# Business Logic (Mocking esim_store.provision_esim as requested)
# =====================================================================
def provision_esim_profile(number: str, plan_id: str, user_id: int) -> Dict[str, Any]:
    """
    Core function mapping to esim_store.provision_esim logic.
    Creates and stores eSIM profile parameters.
    """
    customer_id = f"SUB-{uuid.uuid4().hex[:12].upper()}"
    
    # Generate mock ICCID if sim service fails, else use standard format
    try:
        iccid = sim_service.generate_iccid()
    except Exception:
        iccid = f"89984" + "".join(str(uuid.uuid4().int)[:15])

    matching_id = f"TU5G-{uuid.uuid4().hex[:12].upper()}"
    lpa_string = f"LPA:1$rsp.tu5g.com${matching_id}"
    
    profile = {
        "customer_id": customer_id,
        "user_id": user_id,
        "sim_number": number,
        "iccid": iccid,
        "plan_id": plan_id,
        "lpa_string": lpa_string,
        "status": "provisioned",
        "created_at": datetime.now(timezone.utc),
        "activated_at": None,
        "suspended_at": None,
        "last_network_registration": None
    }
    
    _esim_store_profiles[customer_id] = profile
    return profile


# =====================================================================
# Endpoints
# =====================================================================
@router.get("/numbers", response_model=NumberListResponse, status_code=status.HTTP_200_OK)
async def list_available_numbers(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100)
) -> Any:
    """
    List and filter available eSIM cellular numbers on the TU5G platform.
    Can filter by category (standard, premium, etc.) and search numbers with match.
    """
    filtered = []
    now = datetime.now(timezone.utc)
    
    # Cleanup expired reservations first
    for num, res in list(_number_reservations.items()):
        if now > res["expires_at"]:
            _number_reservations.pop(num, None)
            if num in _available_numbers:
                _available_numbers[num]["status"] = "available"

    for num_data in _available_numbers.values():
        num_str = num_data["number"]
        # Check active reservations
        is_reserved = num_str in _number_reservations
        status_val = "reserved" if is_reserved else num_data["status"]
        
        # Match filters
        if category and num_data["category"].lower() != category.lower():
            continue
        if search and search not in num_str:
            continue
            
        filtered.append({
            "number": num_str,
            "category": num_data["category"],
            "price": num_data["price"],
            "status": status_val
        })

    # Pagination
    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_items = filtered[start:end]

    return {
        "numbers": paginated_items,
        "total_count": total,
        "page": page,
        "per_page": per_page
    }


@router.get("/numbers/{number}", response_model=NumberDetail, status_code=status.HTTP_200_OK)
async def get_number_details(number: str) -> Any:
    """
    Retrieve classification metadata, category, price, and operational status of a specific number.
    """
    # Clean up first
    if number in _number_reservations:
        if datetime.now(timezone.utc) > _number_reservations[number]["expires_at"]:
            _number_reservations.pop(number, None)
            if number in _available_numbers:
                _available_numbers[number]["status"] = "available"

    if number not in _available_numbers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The cellular number '{number}' is not managed on our virtual network routing profile."
        )

    num_data = _available_numbers[number]
    status_val = "reserved" if number in _number_reservations else num_data["status"]
    
    return {
        "number": num_data["number"],
        "category": num_data["category"],
        "price": num_data["price"],
        "status": status_val
    }


@router.post("/numbers/{number}/reserve", response_model=ReserveNumberResponse, status_code=status.HTTP_200_OK)
async def reserve_number(
    number: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Temporarily reserve an available number for the current user.
    Reservations expire after a 10-minute TTL (Time To Live).
    Protected: Requires valid Bearer Token.
    """
    user_id = current_user["id"]
    
    if number not in _available_numbers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The requested cellular number '{number}' is not available."
        )

    num_data = _available_numbers[number]
    
    # Check current status
    if num_data["status"] == "sold":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This cellular number has already been purchased and activated."
        )

    # Check reservation
    if number in _number_reservations:
        res = _number_reservations[number]
        if datetime.now(timezone.utc) <= res["expires_at"]:
            if res["user_id"] == user_id:
                return {
                    "number": number,
                    "reserved_by": user_id,
                    "expires_at": res["expires_at"],
                    "message": "You already hold an active reservation for this number."
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This cellular number is currently reserved by another subscriber."
                )

    # Create new reservation
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    _number_reservations[number] = {
        "user_id": user_id,
        "expires_at": expires_at
    }
    
    logger.info(f"Number {number} reserved for user {user_id} until {expires_at}")
    return {
        "number": number,
        "reserved_by": user_id,
        "expires_at": expires_at,
        "message": f"Success: Cellular number reserved. You have 10 minutes to complete checkout."
    }


@router.post("/provision", response_model=ESimProvisionResponse, status_code=status.HTTP_201_CREATED)
async def provision_esim_store(
    request_in: ESimProvisionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Provision a brand new e-SIM with the requested cellular number and selected data plan.
    Fulfills reservations and sets status.
    Protected: Requires valid Bearer Token.
    """
    number = request_in.number
    plan_id = request_in.plan_id
    user_id = request_in.user_id

    # Verify authorization (user must match current user or user must be admin)
    if user_id != current_user["id"] and current_user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: You cannot provision services for other user IDs."
        )

    # Ensure plan is valid
    plan_exists = any(p["plan_id"] == plan_id for p in _data_plans)
    if not plan_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Data plan '{plan_id}' does not exist."
        )

    # Verify number availability and reservation constraints
    if number in _number_reservations:
        res = _number_reservations[number]
        if datetime.now(timezone.utc) <= res["expires_at"] and res["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This phone number is reserved by another user."
            )
        # Clear reservation
        _number_reservations.pop(number, None)

    if number in _available_numbers:
        if _available_numbers[number]["status"] == "sold":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This phone number has already been provisioned and sold."
            )
        _available_numbers[number]["status"] = "sold"

    # Provision eSIM via business logic function
    profile = provision_esim_profile(number=number, plan_id=plan_id, user_id=user_id)
    
    logger.info(f"e-SIM provisioned successfully for user {user_id}: ICCID={profile['iccid']}")
    return profile


@router.get("/plans", response_model=List[DataPlanResponse], status_code=status.HTTP_200_OK)
async def list_data_plans() -> Any:
    """
    List all high-fidelity 5G cellular billing subscriptions and data plans.
    """
    return _data_plans


@router.get("/status/{customer_id}", response_model=ESimStatusResponse, status_code=status.HTTP_200_OK)
async def get_store_esim_status(
    customer_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Get activation, network registry, and status payload of a provisioned eSIM profile.
    Protected: Requires valid credentials.
    """
    if customer_id not in _esim_store_profiles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"e-SIM profile for customer reference {customer_id} does not exist."
        )

    profile = _esim_store_profiles[customer_id]
    
    # Auth authorization boundary
    if profile["user_id"] != current_user["id"] and current_user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: You are not authorized to view this subscriber profile."
        )

    return profile


@router.post("/activate/{customer_id}", response_model=ESimStatusResponse, status_code=status.HTTP_200_OK)
async def activate_store_esim(
    customer_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Remotely activate an OTA provisioned e-SIM profile on the Next-Gen TU5G Core.
    Protected: Requires valid credentials.
    """
    if customer_id not in _esim_store_profiles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"e-SIM profile for customer reference {customer_id} was not found."
        )

    profile = _esim_store_profiles[customer_id]
    
    if profile["user_id"] != current_user["id"] and current_user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Unauthorized activation."
        )

    if profile["status"] == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The requested e-SIM is already active."
        )

    profile["status"] = "active"
    profile["activated_at"] = datetime.now(timezone.utc)
    profile["last_network_registration"] = datetime.now(timezone.utc)
    
    _esim_store_profiles[customer_id] = profile
    return profile


@router.post("/suspend/{customer_id}", response_model=ESimStatusResponse, status_code=status.HTTP_200_OK)
async def suspend_store_esim(
    customer_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Temporarily block network traffic and suspend billing services for an e-SIM.
    Protected: Requires valid credentials.
    """
    if customer_id not in _esim_store_profiles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"e-SIM profile for customer reference {customer_id} was not found."
        )

    profile = _esim_store_profiles[customer_id]
    
    if profile["user_id"] != current_user["id"] and current_user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Unauthorized suspension."
        )

    if profile["status"] == "suspended":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This e-SIM is already suspended."
        )

    profile["status"] = "suspended"
    profile["suspended_at"] = datetime.now(timezone.utc)
    
    _esim_store_profiles[customer_id] = profile
    return profile


@router.get("/qr/{customer_id}", response_model=ESimQRResponse, status_code=status.HTTP_200_OK)
async def get_store_esim_qr(
    customer_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Retrieve printable/scannable QR and activation metadata vectors.
    Protected: Requires valid credentials.
    """
    if customer_id not in _esim_store_profiles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"e-SIM profile for customer reference {customer_id} was not found."
        )

    profile = _esim_store_profiles[customer_id]
    
    if profile["user_id"] != current_user["id"] and current_user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Unauthorized QR payload request."
        )

    # Standard scannable mock image representation
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


@router.post("/free-premium/apply", response_model=FreePremiumResponse, status_code=status.HTTP_201_CREATED)
async def apply_for_free_premium_number(
    request_in: FreePremiumRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Apply for a free premium category number (gold, premium, platinum) with supportive justification.
    Protected: Requires valid Bearer Token.
    """
    user_id = current_user["id"]
    category = request_in.category.lower()

    if category not in ("gold", "premium", "platinum"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category. Applications are only evaluated for gold, premium, and platinum tiers."
        )

    # Allow one active application at a time
    if user_id in _free_premium_applications:
        app = _free_premium_applications[user_id]
        if app["status"] == "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already have an active premium number application pending review."
            )

    application_id = f"APP-{uuid.uuid4().hex[:12].upper()}"
    now = datetime.now(timezone.utc)

    application_data = {
        "application_id": application_id,
        "user_id": user_id,
        "category": category,
        "reason": request_in.reason,
        "status": "pending",
        "submitted_at": now
    }

    _free_premium_applications[user_id] = application_data
    
    logger.info(f"Free premium application {application_id} registered for user {user_id}")
    return application_data


@router.get("/free-premium/status", response_model=FreePremiumResponse, status_code=status.HTTP_200_OK)
async def check_free_premium_status(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Check current user's free premium number application evaluation status.
    Protected: Requires valid Bearer Token.
    """
    user_id = current_user["id"]
    
    if user_id not in _free_premium_applications:
        raise HTTPException(
            status_code=status.HTTP_444_NOT_RESPONSE if hasattr(status, "HTTP_444_NOT_RESPONSE") else 404,
            detail="You have not submitted any applications for a free premium number."
        )

    return _free_premium_applications[user_id]
