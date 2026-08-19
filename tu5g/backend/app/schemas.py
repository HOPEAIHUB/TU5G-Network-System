from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, EmailStr

# ==========================================
# 1. AUTHENTICATION & USER SCHEMAS
# ==========================================

class Token(BaseModel):
    """Schema representing JWT access tokens."""
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """Decoded token payload information."""
    email: Optional[str] = None
    role: Optional[str] = None


class UserCreate(BaseModel):
    """Schema for creating a new user account."""
    email: EmailStr = Field(..., description="Unique user email address")
    phone_number: Optional[str] = Field(None, description="Optional user phone number")
    password: str = Field(..., min_length=6, description="Minimum 6 character password")
    full_name: str = Field(..., min_length=2, max_length=100, description="User's real or display name")
    role: Optional[str] = Field("user", description="User role ('user', 'admin', 'super_admin')")


class UserUpdate(BaseModel):
    """Schema for updating user details."""
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6)
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    email_verified: Optional[bool] = None
    phone_verified: Optional[bool] = None
    kyc_status: Optional[str] = None


class UserResponse(BaseModel):
    """Schema representing public or authenticated user profiles."""
    id: int
    email: EmailStr
    phone_number: Optional[str] = None
    full_name: str
    role: str
    is_active: bool
    email_verified: bool
    phone_verified: bool
    kyc_status: str
    created_date: datetime
    updated_date: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 2. CUSTOMER / SIM PROFILE SCHEMAS
# ==========================================

class CustomerCreate(BaseModel):
    """Schema for onboarding a new telecom customer sim profile."""
    user_id: int = Field(..., description="The user owning this customer SIM profile")
    sim_number: str = Field(..., description="Physical or digital SIM identifier")
    iccid: str = Field(..., description="Integrated Circuit Card Identifier")
    country_code: str = Field(..., description="ISO Country Code")
    phone_number: Optional[str] = Field(None, description="Assigned phone number if applicable")
    status: Optional[str] = Field("inactive", description="SIM Status: 'active', 'inactive', 'suspended'")
    plan_type: Optional[str] = Field("free", description="Subscribed plan: 'free', 'premium', 'ultra', 'business', 'vanity'")
    plan_expires: Optional[datetime] = Field(None, description="Plan expiration timestamp")
    data_allowance_gb: Optional[float] = Field(0.0, description="Total data allowance in GB")
    data_used_gb: Optional[float] = Field(0.0, description="Data used so far in GB")


class CustomerUpdate(BaseModel):
    """Schema for updating an existing customer sim profile."""
    sim_number: Optional[str] = None
    iccid: Optional[str] = None
    country_code: Optional[str] = None
    phone_number: Optional[str] = None
    status: Optional[str] = None
    plan_type: Optional[str] = None
    plan_expires: Optional[datetime] = None
    data_allowance_gb: Optional[float] = None
    data_used_gb: Optional[float] = None


class CustomerResponse(BaseModel):
    """Schema representing full telecom customer profile details."""
    id: int
    user_id: int
    sim_number: str
    iccid: str
    country_code: str
    phone_number: Optional[str] = None
    status: str
    plan_type: str
    plan_expires: Optional[datetime] = None
    data_allowance_gb: float
    data_used_gb: float
    created_date: datetime
    updated_date: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. VIRTUAL CELL NETWORK SCHEMAS
# ==========================================

class VirtualCellCreate(BaseModel):
    """Schema for creating/onboarding a new virtual cell transmitter."""
    cell_id: str = Field(..., description="Unique cell identifier")
    mcc: int = Field(..., description="Mobile Country Code")
    mnc: int = Field(..., description="Mobile Network Code")
    rsrp: int = Field(..., description="Reference Signal Received Power in dBm")
    rtt: int = Field(..., description="Round-trip latency in milliseconds")
    users: Optional[int] = Field(0, description="Count of connected clients")
    is_active: Optional[bool] = Field(True, description="Cell availability status")


class VirtualCellUpdate(BaseModel):
    """Schema for updating a virtual cell transmitter."""
    mcc: Optional[int] = None
    mnc: Optional[int] = None
    rsrp: Optional[int] = None
    rtt: Optional[int] = None
    users: Optional[int] = None
    is_active: Optional[bool] = None


class VirtualCellResponse(BaseModel):
    """Detailed Virtual Cell state response."""
    id: int
    cell_id: str
    mcc: int
    mnc: int
    rsrp: int
    rtt: int
    users: int
    is_active: bool
    created_date: datetime
    updated_date: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. HOLOGRAPHIC SESSION SCHEMAS
# ==========================================

class HolographicSessionCreate(BaseModel):
    """Schema for initializing a holographic stream."""
    session_name: str = Field(..., description="Human-readable session or stream descriptor")
    status: Optional[str] = Field("inactive", description="Initial status of holographic stream")


class HolographicSessionResponse(BaseModel):
    """Holographic stream metadata response."""
    id: int
    user_id: int
    session_name: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 5. CHAT / AI COMPANION SCHEMAS
# ==========================================

class ChatMessageCreate(BaseModel):
    """Schema for submitting a message to an AI companion."""
    role: str = Field(..., description="Role of the sender: e.g., 'user', 'assistant', 'system'")
    content: str = Field(..., description="Body of the message")


class ChatMessageResponse(BaseModel):
    """Schema representing a stored chat session message."""
    id: int
    user_id: int
    role: str
    content: str
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 6. TELEMETRY SCHEMAS
# ==========================================

class TelemetryData(BaseModel):
    """Schema representing live connection telemetry packet."""
    cell_id: str = Field(..., description="Cell tower transmitting telemetry")
    rsrp: int = Field(..., description="RSRP network power")
    rtt: int = Field(..., description="RTT communication latency")
    users: int = Field(..., description="Total cell occupants")


class TelemetryResponse(BaseModel):
    """Stored persistent telemetry record details."""
    id: int
    cell_id: str
    rsrp: int
    rtt: int
    users: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 7. KYC SCHEMAS
# ==========================================

class KYCRecordCreate(BaseModel):
    """Schema for submitting KYC verification."""
    full_name: str = Field(..., description="Full legal name of the user")
    id_type: str = Field(..., description="ID Type: e.g. passport, national_id, drivers_license")
    id_number: str = Field(..., description="Identification Document Number")
    address: str = Field(..., description="Legal physical address")
    document_urls: Optional[List[str]] = Field(None, description="S3 or private storage URLs of uploaded identity files")


class KYCRecordUpdate(BaseModel):
    """Schema for updating/reviewing a KYC application."""
    status: str = Field(..., description="Compliance status: 'verified' or 'rejected'")
    admin_notes: Optional[str] = Field(None, description="Optional compliance evaluation details")


class KYCRecordResponse(BaseModel):
    """Full KYC application details and evaluation."""
    id: int
    user_id: int
    full_name: str
    id_type: str
    id_number: str
    address: str
    document_urls: Optional[List[str]] = None
    status: str
    admin_id: Optional[int] = None
    admin_notes: Optional[str] = None
    submitted_at: datetime
    verified_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 8. OTP SCHEMAS
# ==========================================

class OTPRecordCreate(BaseModel):
    """Request schema for generating and sending a new verification OTP."""
    identifier: str = Field(..., description="Target email or phone number for OTP delivery")
    otp_type: str = Field(..., description="Verification medium: 'email' or 'phone'")


class OTPVerifyRequest(BaseModel):
    """Request schema for validating an OTP verification code."""
    identifier: str = Field(..., description="The target email or phone number matching the OTP request")
    otp_code: str = Field(..., description="The one-time passcode to verify")


class OTPRecordResponse(BaseModel):
    """Schema representing generated or verified OTP status."""
    id: int
    identifier: str
    otp_type: str
    expires_at: datetime
    used: bool
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 9. PAYMENT / WALLET / VPA SCHEMAS
# ==========================================

class PaymentTransactionCreate(BaseModel):
    """Schema to log or trigger a payment transaction."""
    type: str = Field(..., description="Transaction type: 'add_funds', 'payment', 'transfer', 'refund'")
    amount: float = Field(..., gt=0.0, description="Amount in transaction currency")
    currency: Optional[str] = Field("USD", description="Currency string (e.g. 'USD')")
    description: Optional[str] = Field(None, description="Optional text description")
    vpa_from: Optional[str] = Field(None, description="Source VPA if applicable")
    vpa_to: Optional[str] = Field(None, description="Target VPA if applicable")
    session_id: Optional[str] = Field(None, description="Payment gateway transaction/session ID")


class PaymentTransactionResponse(BaseModel):
    """Transaction audit ledger record."""
    id: int
    user_id: int
    type: str
    amount: float
    currency: str
    status: str
    description: Optional[str] = None
    vpa_from: Optional[str] = None
    vpa_to: Optional[str] = None
    session_id: Optional[str] = None
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


class WalletCreate(BaseModel):
    """Initialize a digital wallet."""
    user_id: int
    balance: Optional[float] = Field(0.0, ge=0.0)
    currency: Optional[str] = Field("USD")


class WalletUpdate(BaseModel):
    """Directly adjust wallet balance."""
    balance: float = Field(..., ge=0.0, description="New absolute balance of the wallet")


class WalletResponse(BaseModel):
    """In-app digital balance and currency storage."""
    id: int
    user_id: int
    balance: float
    currency: str
    created_date: datetime
    updated_date: datetime

    model_config = ConfigDict(from_attributes=True)


class VPACreate(BaseModel):
    """Map a virtual payment address."""
    vpa_address: str = Field(..., min_length=3, max_length=50, description="VPA handle, e.g., username@tu5g")


class VPAResponse(BaseModel):
    """Virtual Payment Address registration details."""
    id: int
    user_id: int
    vpa_address: str
    is_active: bool
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 10. HMAIL SCHEMAS
# ==========================================

class HmailAccountCreate(BaseModel):
    """Create a new internal holographic mail account."""
    username: str = Field(..., min_length=3, max_length=30, description="Desired hmail handle (e.g., alice)")
    email_address: Optional[str] = Field(None, description="Full hmail address, auto-generated if omitted (e.g. alice@hmail.tu5g)")


class HmailAccountResponse(BaseModel):
    """Hmail Account registration."""
    id: int
    user_id: int
    username: str
    email_address: str
    is_active: bool
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


class HmailMessageCreate(BaseModel):
    """Send an internal Hmail message."""
    to_email: str = Field(..., description="Recipient hmail address")
    subject: str = Field(..., max_length=150, description="Subject of the email")
    body: str = Field(..., description="Message body or holographic data packet content")


class HmailMessageResponse(BaseModel):
    """A single stored Hmail message."""
    id: int
    account_id: int
    from_email: str
    to_email: str
    subject: str
    body: str
    is_read: bool
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 11. GOVERNANCE SCHEMAS
# ==========================================

class GovernanceApplicationCreate(BaseModel):
    """Request to become a validated platform node or governance member."""
    category: str = Field(..., description="e.g. academic, corporate, telecom_node")
    organization_name: str = Field(..., description="Official legal name of organizing body")
    description: str = Field(..., description="Justification and explanation of platform involvement")
    proof_url: Optional[str] = Field(None, description="External verification links or proof files")


class GovernanceApplicationUpdate(BaseModel):
    """Evaluate or review a governance membership application."""
    status: str = Field(..., description="Application state: 'approved' or 'rejected'")
    admin_notes: Optional[str] = Field(None, description="Internal verification team review comments")


class GovernanceApplicationResponse(BaseModel):
    """A recorded governance application status."""
    id: int
    user_id: int
    category: str
    organization_name: str
    description: str
    proof_url: Optional[str] = None
    status: str
    admin_notes: Optional[str] = None
    created_date: datetime
    reviewed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 12. ESIM RESERVATION SCHEMAS
# ==========================================

class ESIMReservationCreate(BaseModel):
    """Hold a specific number/eSIM profile in the store."""
    number: str = Field(..., description="The phone number or eSIM ICCID to reserve")
    expires_at: datetime = Field(..., description="Hold expiration timestamp")


class ESIMReservationResponse(BaseModel):
    """eSIM reserve hold receipt."""
    id: int
    number: str
    user_id: int
    expires_at: datetime
    is_active: bool
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 13. AUDIT LOG SCHEMAS
# ==========================================

class AuditLogCreate(BaseModel):
    """Log an explicit platform administration trace record."""
    user_id: Optional[int] = None
    action: str = Field(..., description="Categorized system action performed")
    resource: str = Field(..., description="Affected platform entity or endpoint")
    ip_address: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class AuditLogResponse(BaseModel):
    """Compliance trace Audit record."""
    id: int
    user_id: Optional[int] = None
    action: str
    resource: str
    ip_address: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 14. AI BOT & COPILOT SCHEMAS
# ==========================================

class ChatRequest(BaseModel):
    """Schema for querying any AI Character / Copilot Bot."""
    prompt: str = Field(..., min_length=1, max_length=4000, description="Your query or instruction to the AI")
    conversation_id: Optional[str] = Field(None, description="Optional conversation session ID for multi-turn history")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=1.0, description="Creativity/sampling temperature of the model response")


class ChatResponse(BaseModel):
    """Schema for AI Bot response output."""
    answer: str = Field(..., description="The generated textual answer from the AI bot")
    bot_name: str = Field(..., description="The name of the answering assistant")
    conversation_id: str = Field(..., description="The conversation session ID")
    system_prompt: Optional[str] = Field(None, description="The system guidelines used by this assistant")
    response: Optional[str] = Field(None, description="Alias for answer for backwards compatibility")
    tokens_used: Optional[int] = Field(150, description="Estimated or actual token usage count")


# Aliases for backwards compatibility with existing router definitions
AIChatRequest = ChatRequest
AIChatResponse = ChatResponse


class BotInfo(BaseModel):
    """Metadata for an available AI bot assistant."""
    id: str = Field(..., description="Unique identifier/slug for the bot")
    name: str = Field(..., description="Display name of the AI bot")
    endpoint: str = Field(..., description="API endpoint path for the bot")
    description: str = Field(..., description="Summary of the bot capabilities and domain expertise")


class BotListResponse(BaseModel):
    """List of available AI bot assistants."""
    bots: List[BotInfo] = Field(..., description="List of registered AI bot assistants")
