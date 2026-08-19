"""
Payments and Wallet Management Router for the TU5G platform (Hope Pay & UPS Pay).
Enables Virtual Payment Address (VPA) registration, peer-to-peer (P2P) transfers,
wallet fund management, checkout session handling, and administrative audits.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Hope Pay & UPS Pay Systems"])

# =====================================================================
# In-Memory Database for Payment Profiles, Sessions & Transactions
# =====================================================================
# Schema: user_id -> { "vpa": str, "balance": float, "transactions": list }
_payment_profiles: Dict[int, Dict[str, Any]] = {}

# Schema: session_id -> session_details
_checkout_sessions: Dict[str, Dict[str, Any]] = {}


# =====================================================================
# Pydantic Schemas
# =====================================================================
class CreateVPARequest(BaseModel):
    desired_username: str = Field(..., min_length=3, max_length=50, description="Preferred VPA name (e.g. 'alice')")
    provider: str = Field("hopepay", description="Payment gateway: 'hopepay' or 'upspay'")


class VPAResponse(BaseModel):
    user_id: int = Field(...)
    vpa: str = Field(..., description="Virtual Payment Address (e.g. 'alice@hopepay')")
    provider: str = Field(...)
    created_at: datetime = Field(...)


class WalletResponse(BaseModel):
    user_id: int = Field(...)
    vpa: Optional[str] = Field(None, description="Registered VPA if configured")
    balance: float = Field(..., description="Current spendable cash balance in USD")
    currency: str = Field("USD", description="Wallet pricing base currency")


class AddFundsRequest(BaseModel):
    amount: float = Field(..., gt=0.0, description="Amount in USD to add")
    source: str = Field(..., description="Funding source description, e.g. 'visa_credit', 'apple_pay'")


class AddFundsResponse(BaseModel):
    user_id: int = Field(...)
    previous_balance: float = Field(...)
    new_balance: float = Field(...)
    transaction_id: str = Field(...)
    status: str = Field("success")


class CreateSessionRequest(BaseModel):
    amount: float = Field(..., gt=0.0, description="Transaction total amount in USD")
    description: str = Field(..., description="Item or subscription detail being paid for")


class CreateSessionResponse(BaseModel):
    session_id: str = Field(...)
    amount: float = Field(...)
    description: str = Field(...)
    status: str = Field("pending", description="Session state: pending, completed, expired")
    expires_at: datetime = Field(...)


class SessionStatusResponse(BaseModel):
    session_id: str = Field(...)
    amount: float = Field(...)
    description: str = Field(...)
    status: str = Field(...)
    completed_at: Optional[datetime] = None


class TransferRequest(BaseModel):
    to_vpa: str = Field(..., description="Recipient's VPA, e.g. 'bob@hopepay'")
    amount: float = Field(..., gt=0.0, description="P2P Transfer amount in USD")
    description: Optional[str] = Field("P2P Wallet Transfer", description="Optional comment or purpose")


class TransferResponse(BaseModel):
    transaction_id: str = Field(...)
    sender_vpa: str = Field(...)
    recipient_vpa: str = Field(...)
    amount: float = Field(...)
    description: str = Field(...)
    status: str = Field("completed")
    timestamp: datetime = Field(...)


class TransactionRecord(BaseModel):
    transaction_id: str = Field(...)
    type: str = Field(..., description="Type: 'deposit', 'withdrawal', 'p2p_send', 'p2p_receive', 'purchase'")
    amount: float = Field(...)
    vpa: Optional[str] = None
    description: str = Field(...)
    timestamp: datetime = Field(...)


# =====================================================================
# Helper to Initialize Profile if missing
# =====================================================================
def get_or_create_payment_profile(user_id: int) -> Dict[str, Any]:
    """Ensures a payment wallet profile exists for the user with an initial $100 balance."""
    if user_id not in _payment_profiles:
        _payment_profiles[user_id] = {
            "user_id": user_id,
            "vpa": None,
            "provider": None,
            "balance": 100.00,  # Generous default balance for sandbox testing
            "transactions": [],
            "created_at": datetime.now(timezone.utc)
        }
    return _payment_profiles[user_id]


# =====================================================================
# Endpoints
# =====================================================================
@router.post("/create-vpa", response_model=VPAResponse, status_code=status.HTTP_201_CREATED)
async def create_vpa(
    request_in: CreateVPARequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Create a secure Virtual Payment Address (VPA) for Hope Pay or UPS Pay.
    Protected: Requires valid Bearer Token.
    """
    user_id = current_user["id"]
    profile = get_or_create_payment_profile(user_id)
    
    if profile["vpa"] is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You already have a configured VPA on the platform: {profile['vpa']}"
        )

    clean_username = request_in.desired_username.strip().lower()
    provider = request_in.provider.strip().lower()

    if provider not in ("hopepay", "upspay"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid provider. Choose either 'hopepay' or 'upspay'."
        )

    vpa_address = f"{clean_username}@{provider}"

    # Verify global uniqueness of VPA
    for other_p in _payment_profiles.values():
        if other_p.get("vpa") == vpa_address:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The Virtual Payment Address '{vpa_address}' is already registered by another customer."
            )

    # Save VPA Details
    profile["vpa"] = vpa_address
    profile["provider"] = provider
    _payment_profiles[user_id] = profile

    logger.info(f"VPA '{vpa_address}' successfully configured for user {user_id}")
    return {
        "user_id": user_id,
        "vpa": vpa_address,
        "provider": provider,
        "created_at": datetime.now(timezone.utc)
    }


@router.get("/vpa", response_model=VPAResponse, status_code=status.HTTP_200_OK)
async def get_user_vpa(current_user: Dict[str, Any] = Depends(get_current_user)) -> Any:
    """
    Get current logged-in user's Virtual Payment Address.
    Protected: Requires valid Bearer Token.
    """
    user_id = current_user["id"]
    profile = get_or_create_payment_profile(user_id)

    if profile["vpa"] is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You do not have a registered Virtual Payment Address on this profile."
        )

    return {
        "user_id": user_id,
        "vpa": profile["vpa"],
        "provider": profile["provider"],
        "created_at": profile["created_at"]
    }


@router.get("/wallet", response_model=WalletResponse, status_code=status.HTTP_200_OK)
async def get_wallet_balance(current_user: Dict[str, Any] = Depends(get_current_user)) -> Any:
    """
    Get current customer balance and registered VPA.
    Protected: Requires valid Bearer Token.
    """
    user_id = current_user["id"]
    profile = get_or_create_payment_profile(user_id)

    return {
        "user_id": user_id,
        "vpa": profile["vpa"],
        "balance": profile["balance"],
        "currency": "USD"
    }


@router.post("/add-funds", response_model=AddFundsResponse, status_code=status.HTTP_200_OK)
async def add_funds_to_wallet(
    request_in: AddFundsRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Deposit funds into the customer's secure platform wallet.
    Protected: Requires valid Bearer Token.
    """
    user_id = current_user["id"]
    profile = get_or_create_payment_profile(user_id)

    previous_balance = profile["balance"]
    amount = request_in.amount
    new_balance = previous_balance + amount

    transaction_id = f"TXN-DEP-{uuid.uuid4().hex[:12].upper()}"
    now = datetime.now(timezone.utc)

    # Record transaction
    record = {
        "transaction_id": transaction_id,
        "type": "deposit",
        "amount": amount,
        "vpa": profile["vpa"],
        "description": f"Funded wallet via {request_in.source}",
        "timestamp": now
    }

    profile["balance"] = new_balance
    profile["transactions"].append(record)
    _payment_profiles[user_id] = profile

    logger.info(f"Deposited ${amount} into user {user_id} wallet. New balance: ${new_balance}")
    return {
        "user_id": user_id,
        "previous_balance": previous_balance,
        "new_balance": new_balance,
        "transaction_id": transaction_id,
        "status": "success"
    }


@router.post("/create-session", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_session(
    request_in: CreateSessionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Initialize a secure checkout payment session for e-SIM or standard items.
    Protected: Requires valid Bearer Token.
    """
    session_id = f"PAY-SES-{uuid.uuid4().hex[:12].upper()}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    session_data = {
        "session_id": session_id,
        "user_id": current_user["id"],
        "amount": request_in.amount,
        "description": request_in.description,
        "status": "pending",
        "expires_at": expires_at,
        "completed_at": None
    }

    _checkout_sessions[session_id] = session_data
    
    logger.info(f"Payment session {session_id} created for ${request_in.amount}")
    return session_data


@router.get("/session/{session_id}", response_model=SessionStatusResponse, status_code=status.HTTP_200_OK)
async def check_payment_status(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Check current checkout payment session completion status.
    Protected: Requires valid Bearer Token.
    """
    if session_id not in _checkout_sessions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The checkout session referenced does not exist on our payment server."
        )

    session = _checkout_sessions[session_id]
    
    # Boundary check
    if session["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: This billing session does not belong to you."
        )

    # Check expiry
    if session["status"] == "pending" and datetime.now(timezone.utc) > session["expires_at"]:
        session["status"] = "expired"
        _checkout_sessions[session_id] = session

    return session


@router.post("/transfer", response_model=TransferResponse, status_code=status.HTTP_200_OK)
async def transfer_funds(
    request_in: TransferRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Peer-to-Peer (P2P) transfer of funds from current wallet to another subscriber's VPA.
    Protected: Requires valid Bearer Token.
    """
    sender_id = current_user["id"]
    sender_profile = get_or_create_payment_profile(sender_id)

    # Verify sender has VPA
    if sender_profile["vpa"] is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must register a VPA on your profile before initiating transfers."
        )

    amount = request_in.amount
    to_vpa = request_in.to_vpa.strip().lower()

    if sender_profile["vpa"].lower() == to_vpa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer Error: You cannot transfer funds to your own wallet address."
        )

    # Check balance
    if sender_profile["balance"] < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient balance. Please deposit funds into your wallet."
        )

    # Locate recipient
    recipient_profile = None
    recipient_id = None
    for uid, prof in _payment_profiles.items():
        if prof.get("vpa") and prof["vpa"].lower() == to_vpa:
            recipient_profile = prof
            recipient_id = uid
            break

    if not recipient_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The recipient VPA '{to_vpa}' was not found. Please verify the address."
        )

    # Perform P2P transfer
    transaction_id = f"TXN-P2P-{uuid.uuid4().hex[:12].upper()}"
    now = datetime.now(timezone.utc)

    # Deduct sender
    sender_profile["balance"] -= amount
    sender_record = {
        "transaction_id": transaction_id,
        "type": "p2p_send",
        "amount": amount,
        "vpa": to_vpa,
        "description": f"Transferred to {to_vpa}: {request_in.description}",
        "timestamp": now
    }
    sender_profile["transactions"].append(sender_record)
    _payment_profiles[sender_id] = sender_profile

    # Credit recipient
    recipient_profile["balance"] += amount
    recipient_record = {
        "transaction_id": transaction_id,
        "type": "p2p_receive",
        "amount": amount,
        "vpa": sender_profile["vpa"],
        "description": f"Received from {sender_profile['vpa']}: {request_in.description}",
        "timestamp": now
    }
    recipient_profile["transactions"].append(recipient_record)
    _payment_profiles[recipient_id] = recipient_profile

    logger.info(f"P2P Transfer of ${amount} completed from {sender_profile['vpa']} to {to_vpa}")
    return {
        "transaction_id": transaction_id,
        "sender_vpa": sender_profile["vpa"],
        "recipient_vpa": to_vpa,
        "amount": amount,
        "description": request_in.description,
        "status": "completed",
        "timestamp": now
    }


@router.get("/history", response_model=List[TransactionRecord], status_code=status.HTTP_200_OK)
async def get_transaction_history(current_user: Dict[str, Any] = Depends(get_current_user)) -> Any:
    """
    Get full wallet deposit, withdrawal, and transfer history for the current user.
    Protected: Requires valid Bearer Token.
    """
    user_id = current_user["id"]
    profile = get_or_create_payment_profile(user_id)
    return profile["transactions"]


@router.get("/admin/all", response_model=List[Dict[str, Any]], status_code=status.HTTP_200_OK)
async def get_all_transactions_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Any:
    """
    Retrieve all payment transactions across all users.
    Protected: Requires Super Admin credentials.
    """
    role = current_user.get("role")
    if role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: This telemetry audit operation requires 'super_admin' clearance."
        )

    all_txs = []
    for uid, profile in _payment_profiles.items():
        for txn in profile.get("transactions", []):
            txn_with_user = txn.copy()
            txn_with_user["user_id"] = uid
            txn_with_user["user_vpa"] = profile.get("vpa")
            all_txs.append(txn_with_user)
            
    # Sort by newest first
    all_txs.sort(key=lambda x: x["timestamp"], reverse=True)
    return all_txs
