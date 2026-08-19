from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

# Instantiate the declarative base class
Base = declarative_base()


class User(Base):
    """
    User entity representative of administrators and platform customers.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone_number = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, default="customer", nullable=False)  # Allowed values: 'admin', 'customer'
    is_active = Column(Boolean, default=True, nullable=False)
    kyc_status = Column(String, default="not_submitted", nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    phone_verified = Column(Boolean, default=False, nullable=False)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    sessions = relationship("HolographicSession", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")


class Customer(Base):
    """
    Customer telecom and SIM provisioning profile data.
    """
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    sim_number = Column(String, nullable=False)
    iccid = Column(String, unique=True, index=True, nullable=False)
    country_code = Column(String, nullable=False)
    status = Column(String, default="inactive", nullable=False, index=True)  # Allowed: 'active', 'inactive', 'suspended'
    data_plan = Column(String, nullable=False)
    phone_number = Column(String, nullable=True, index=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class VirtualCell(Base):
    """
    Virtual Cell tower network metadata and configuration.
    """
    __tablename__ = "virtual_cells"

    id = Column(Integer, primary_key=True, index=True)
    cell_id = Column(String, unique=True, index=True, nullable=False)
    mcc = Column(Integer, nullable=False)  # Mobile Country Code
    mnc = Column(Integer, nullable=False)  # Mobile Network Code
    rsrp = Column(Integer, nullable=False)  # Reference Signal Received Power
    rtt = Column(Integer, nullable=False)  # Round Trip Time
    users = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    telemetry_records = relationship("TelemetryRecord", back_populates="cell", cascade="all, delete-orphan")


class HolographicSession(Base):
    """
    Details of interactive 3D holographic streaming/companion sessions.
    """
    __tablename__ = "holographic_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_name = Column(String, nullable=False)
    status = Column(String, default="inactive", nullable=False, index=True)  # e.g., 'active', 'inactive'
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="sessions")


class ChatMessage(Base):
    """
    Persistent log of AI character companion chats.
    """
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False)  # e.g., 'user', 'assistant'
    content = Column(Text, nullable=False)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="messages")


class TelemetryRecord(Base):
    """
    Time-series network quality telemetry associated with virtual cells.
    """
    __tablename__ = "telemetry_records"

    id = Column(Integer, primary_key=True, index=True)
    cell_id = Column(String, ForeignKey("virtual_cells.cell_id", ondelete="CASCADE"), nullable=False, index=True)
    rsrp = Column(Integer, nullable=False)
    rtt = Column(Integer, nullable=False)
    users = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    cell = relationship("VirtualCell", back_populates="telemetry_records")


class KYCRecord(Base):
    """
    KYC submission details for users on the TU5G platform.
    """
    __tablename__ = "kyc_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name = Column(String, nullable=False)
    id_type = Column(String, nullable=False)
    id_number = Column(String, nullable=False)
    address = Column(Text, nullable=False)
    document_urls = Column(Text, nullable=False)  # JSON-encoded array or text
    status = Column(String, default="pending", nullable=False, index=True)  # pending, verified, rejected
    admin_notes = Column(Text, nullable=True, default="")
    notes = Column(Text, nullable=True, default="")
    admin_id = Column(Integer, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# Alias for compatibility with services that use KYCSubmission
KYCSubmission = KYCRecord


class OTPRecord(Base):
    """
    One-Time Password (OTP) records for authentication & verification.
    """
    __tablename__ = "otp_records"

    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String, nullable=False, index=True)  # Email or Phone
    otp_code = Column(String, nullable=False)
    otp_type = Column(String, nullable=False)  # 'email', 'phone'
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class PaymentTransaction(Base):
    """
    Transaction records for P2P transfers and fiat-on-ramp on the TU5G platform.
    """
    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String, nullable=False)  # 'fiat_onramp', 'transfer', 'payment', 'refund'
    amount = Column(Float, nullable=False)
    currency = Column(String, default="USD", nullable=False)
    description = Column(String, nullable=False)
    vpa_from = Column(String, nullable=True)
    vpa_to = Column(String, nullable=True)
    source_vpa = Column(String, nullable=True)
    recipient_vpa = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    status = Column(String, default="pending", nullable=False, index=True)  # pending, completed, failed
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


# Alias for compatibility with services that use Transaction
Transaction = PaymentTransaction


class Wallet(Base):
    """
    User digital wallet on the TU5G platform (fiat, VPA).
    """
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    balance = Column(Float, default=0.0, nullable=False)
    currency = Column(String, default="USD", nullable=False)
    vpa = Column(String, unique=True, index=True, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class VPA(Base):
    """
    Virtual Payment Address mapping for users.
    """
    __tablename__ = "vpas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    vpa_address = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HmailAccount(Base):
    """
    HMAIL (Hope Mail) account representation.
    """
    __tablename__ = "hmail_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    email_address = Column(String, unique=True, index=True, nullable=False)  # username@tu5g.online
    status = Column(String, default="pending", nullable=False)  # activated, pending
    is_active = Column(Boolean, default=True, nullable=False)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HmailMessage(Base):
    """
    HMAIL (Hope Mail) persistent message storage.
    """
    __tablename__ = "hmail_messages"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("hmail_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    from_email = Column(String, nullable=False)
    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class GovernanceApplication(Base):
    """
    Formal organization membership requests on the TU5G platform.
    """
    __tablename__ = "governance_applications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String, nullable=False)
    organization_name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    proof_url = Column(String, nullable=True)
    status = Column(String, default="pending", nullable=False, index=True)  # pending, approved, rejected
    admin_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ESIMReservation(Base):
    """
    Holds or reservations for specific eSIM numbers.
    """
    __tablename__ = "esim_reservations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class AuditLog(Base):
    """
    Security trace audit log.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    action = Column(String, nullable=False)
    resource = Column(String, nullable=False)
    ip_address = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class ESim(Base):
    """
    E-SIM provisioning profile data.
    """
    __tablename__ = "esims"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    sim_number = Column(String, unique=True, index=True, nullable=False)
    iccid = Column(String, unique=True, index=True, nullable=False)
    country_code = Column(String, default="+984", nullable=False)
    category = Column(String, default="free", nullable=False)  # 'free', 'premium', 'vanity'
    status = Column(String, default="provisioned", nullable=False, index=True)  # 'provisioned', 'active', 'deactivated', 'suspended'
    plan_id = Column(String, default="free_3months", nullable=False)
    lpa_string = Column(String, nullable=True)
    qr_code_base64 = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_date = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
