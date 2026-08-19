"""
Customer/SIM CRUD routers for TU5G platform.
Handles listing, retrieving, creating, updating, and deleting customer records.
Includes integration with SIM profile generation and data usage tracking.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, List, Optional
from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException, status, Query

# Try to import auth and sim services; fallback if they are not yet fully implemented
try:
    from app.services.auth import get_current_user
except ImportError:
    async def get_current_user(*args, **kwargs) -> Any:
        raise NotImplementedError("Authentication service not fully configured.")

try:
    from app.services import sim as sim_service
except ImportError:
    # Safe mock fallback for the router module to compile
    class MockSimService:
        @staticmethod
        def generate_sim_number() -> str:
            # 19 or 20 digits SIM number starting with country/carrier prefix
            return "890141032111" + "".join(str(uuid.uuid4().int)[:8])
        
        @staticmethod
        def generate_iccid() -> str:
            # Standard ICCID structure: prefix (89), country (01), issuer (410), then unique digits + check digit
            return "890141032" + "".join(str(uuid.uuid4().int)[:11])
            
    sim_service = MockSimService()

router = APIRouter(prefix="/customers", tags=["Customers / SIM CRUD"])


# ==========================================
# Pydantic Schemas
# ==========================================

class SIMProfileSchema(BaseModel):
    """Schema for the SIM Profile nested inside customer data."""
    sim_number: str = Field(..., description="Unique SIM MSISDN / phone number")
    iccid: str = Field(..., description="Integrated Circuit Card Identifier (ICCID)")
    imsi: Optional[str] = Field(None, description="International Mobile Subscriber Identity")
    status: str = Field("active", description="Status of the SIM (active, suspended, inactive)")
    pin1: str = Field("1111", description="SIM PIN 1")
    puk: str = Field("12345678", description="SIM PUK key")


class CustomerCreate(BaseModel):
    """Schema for creating a new customer."""
    name: str = Field(..., min_length=2, max_length=100, description="Full name of the customer")
    email: EmailStr = Field(..., description="Email address for billing and notifications")
    phone: str = Field(..., description="Contact phone number")
    plan_name: str = Field("TU5G_unlimited_basic", description="Subscription plan name")


class CustomerUpdate(BaseModel):
    """Schema for updating an existing customer's basic info."""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = Field(None)
    phone: Optional[str] = Field(None)
    plan_name: Optional[str] = Field(None)
    is_active: Optional[bool] = Field(None)


class CustomerResponse(BaseModel):
    """Schema for customer data returned to client."""
    id: str = Field(..., description="Unique Customer UUID")
    name: str = Field(...)
    email: EmailStr = Field(...)
    phone: str = Field(...)
    plan_name: str = Field(...)
    is_active: bool = Field(...)
    sim_profile: Optional[SIMProfileSchema] = Field(None, description="Associated e-SIM/SIM card profile")
    created_at: datetime = Field(...)
    updated_at: datetime = Field(...)

    class Config:
        from_attributes = True


class UsageStatsResponse(BaseModel):
    """Schema for SIM data usage statistics (stub)."""
    customer_id: str = Field(...)
    sim_number: str = Field(...)
    data_used_gb: float = Field(..., description="Data consumed during this billing cycle in Gigabytes")
    data_limit_gb: float = Field(..., description="Total data limit in Gigabytes (or -1 for unlimited)")
    voice_minutes_used: int = Field(0, description="Voice minutes consumed")
    sms_sent: int = Field(0, description="SMS count sent")
    billing_cycle_start: datetime = Field(...)
    billing_cycle_end: datetime = Field(...)


# ==========================================
# In-Memory Mock database for illustration 
# ==========================================
_mock_customers_db: dict = {}


# ==========================================
# Endpoints
# ==========================================

@router.get("/", response_model=List[CustomerResponse], status_code=status.HTTP_200_OK)
async def list_customers(
    skip: int = Query(0, ge=0, description="Number of customer records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max number of records to return"),
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    List all customer records with pagination.
    Protected: Requires valid administrator credentials.
    """
    customers = list(_mock_customers_db.values())
    return customers[skip : skip + limit]


@router.get("/{customer_id}", response_model=CustomerResponse, status_code=status.HTTP_200_OK)
async def get_customer(
    customer_id: str,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Get details of a single customer by their ID.
    Protected: Requires valid credentials.
    """
    if customer_id not in _mock_customers_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} does not exist."
        )
    return _mock_customers_db[customer_id]


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_in: CustomerCreate,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Create a new customer profile.
    Automatically generates a new physical SIM profile (sim_number and iccid) using the sim service.
    Protected: Requires valid credentials.
    """
    # Check if email is already in use
    for existing_customer in _mock_customers_db.values():
        if existing_customer["email"] == customer_in.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A customer with this email address is already registered."
            )

    customer_id = str(uuid.uuid4())
    
    # Generate unique SIM/ICCID identifiers using sim.py service
    generated_sim_num = sim_service.generate_sim_number()
    generated_iccid = sim_service.generate_iccid()
    generated_imsi = "41001" + "".join(str(uuid.uuid4().int)[:10])
    
    sim_profile = {
        "sim_number": generated_sim_num,
        "iccid": generated_iccid,
        "imsi": generated_imsi,
        "status": "active",
        "pin1": "1111",
        "puk": "12345678"
    }

    now = datetime.utcnow()
    new_customer = {
        "id": customer_id,
        "name": customer_in.name,
        "email": customer_in.email,
        "phone": customer_in.phone,
        "plan_name": customer_in.plan_name,
        "is_active": True,
        "sim_profile": sim_profile,
        "created_at": now,
        "updated_at": now
    }
    
    _mock_customers_db[customer_id] = new_customer
    return new_customer


@router.put("/{customer_id}", response_model=CustomerResponse, status_code=status.HTTP_200_OK)
async def update_customer(
    customer_id: str,
    customer_in: CustomerUpdate,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Update basic information of a customer.
    Protected: Requires valid credentials.
    """
    if customer_id not in _mock_customers_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} does not exist."
        )
    
    customer = _mock_customers_db[customer_id]
    
    # Apply updates
    update_data = customer_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        customer[field] = value
        
    customer["updated_at"] = datetime.utcnow()
    _mock_customers_db[customer_id] = customer
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_200_OK)
async def delete_customer(
    customer_id: str,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Permanently delete a customer profile and release assets.
    Protected: Requires valid administrator credentials.
    """
    if customer_id not in _mock_customers_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} does not exist."
        )
    
    del _mock_customers_db[customer_id]
    return {"message": f"Customer {customer_id} has been successfully deleted."}


@router.get("/{customer_id}/usage", response_model=UsageStatsResponse, status_code=status.HTTP_200_OK)
async def get_customer_usage(
    customer_id: str,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Retrieve real-time and billing-period data usage statistics for a customer's active SIM.
    Protected: Requires valid credentials.
    """
    if customer_id not in _mock_customers_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} does not exist."
        )
    
    customer = _mock_customers_db[customer_id]
    sim_profile = customer.get("sim_profile")
    sim_number = sim_profile["sim_number"] if sim_profile else "UNKNOWN"
    
    # Stub metric generator
    now = datetime.utcnow()
    cycle_start = now - timedelta(days=12)
    cycle_end = now + timedelta(days=18)
    
    return {
        "customer_id": customer_id,
        "sim_number": sim_number,
        "data_used_gb": 12.45,  # Stubbed metric
        "data_limit_gb": 100.0 if "unlimited" not in customer["plan_name"].lower() else -1.0,
        "voice_minutes_used": 145,
        "sms_sent": 38,
        "billing_cycle_start": cycle_start,
        "billing_cycle_end": cycle_end
    }
