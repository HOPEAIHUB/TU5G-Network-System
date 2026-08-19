from typing import List, Optional, Any, Dict
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete, update, and_

# Import Database Models
from app.models import (
    User, Customer, VirtualCell, HolographicSession, ChatMessage, TelemetryRecord,
    KYCRecord, OTPRecord, PaymentTransaction, Wallet, VPA, HmailAccount,
    HmailMessage, GovernanceApplication, ESIMReservation, AuditLog
)

# Import Pydantic Schemas
from app.schemas import (
    UserCreate, UserUpdate, CustomerCreate, CustomerUpdate,
    VirtualCellCreate, VirtualCellUpdate, HolographicSessionCreate, ChatMessageCreate, TelemetryData,
    KYCRecordCreate, KYCRecordUpdate, OTPRecordCreate, PaymentTransactionCreate,
    WalletCreate, WalletUpdate, VPACreate, HmailAccountCreate, HmailMessageCreate,
    GovernanceApplicationCreate, GovernanceApplicationUpdate, ESIMReservationCreate, AuditLogCreate
)

# Import Password hashing helpers from auth to prevent duplication
from app.auth import get_password_hash, verify_password


# ==========================================
# 1. USER CRUD
# ==========================================

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Retrieve a user by their unique email address."""
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    return result.scalars().first()

async def get_user(db: AsyncSession, user_id: int) -> Optional[User]:
    """Retrieve a user by their database ID."""
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    return result.scalars().first()

async def create_user(db: AsyncSession, user: UserCreate) -> User:
    """
    Create a new user in the database with a securely-hashed password, 
    and automatically initialize their digital wallet and VPA address.
    """
    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        phone_number=user.phone_number,
        hashed_password=hashed_password,
        full_name=user.full_name,
        role=user.role or "user"
    )
    db.add(db_user)
    await db.flush()  # Populates db_user.id for downstream relations

    # Initialize associated wallet
    db_wallet = Wallet(user_id=db_user.id, balance=0.0, currency="USD")
    db.add(db_wallet)

    # Initialize associated Virtual Payment Address (VPA) using email prefix
    email_prefix = user.email.split("@")[0]
    db_vpa = VPA(user_id=db_user.id, vpa_address=f"{email_prefix}@tu5g", is_active=True)
    db.add(db_vpa)

    await db.commit()
    await db.refresh(db_user)
    return db_user

async def update_user(db: AsyncSession, user_id: int, user_update: UserUpdate) -> Optional[User]:
    """Update general user details."""
    db_user = await get_user(db, user_id)
    if not db_user:
        return None
    
    update_data = user_update.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        update_data["hashed_password"] = get_password_hash(update_data["password"])
        del update_data["password"]

    for key, value in update_data.items():
        setattr(db_user, key, value)

    await db.commit()
    await db.refresh(db_user)
    return db_user

async def update_user_role(db: AsyncSession, user_id: int, role: str) -> Optional[User]:
    """Explicitly update a user's organizational or system role."""
    db_user = await get_user(db, user_id)
    if not db_user:
        return None
    db_user.role = role
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def update_user_status(db: AsyncSession, user_id: int, is_active: bool) -> Optional[User]:
    """Toggle a user's active system access state."""
    db_user = await get_user(db, user_id)
    if not db_user:
        return None
    db_user.is_active = is_active
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """Authenticate a user by verifying their email and password."""
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ==========================================
# 2. CUSTOMER / SIM CRUD
# ==========================================

async def get_customer(db: AsyncSession, customer_id: int) -> Optional[Customer]:
    """Retrieve a customer's profile by database ID."""
    query = select(Customer).where(Customer.id == customer_id)
    result = await db.execute(query)
    return result.scalars().first()

async def get_customers(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Customer]:
    """Paginate and list registered telecom customers."""
    query = select(Customer).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())

async def create_customer(db: AsyncSession, customer: CustomerCreate) -> Customer:
    """Onboard/provision a new customer profile."""
    db_customer = Customer(**customer.model_dump())
    db.add(db_customer)
    await db.commit()
    await db.refresh(db_customer)
    return db_customer

async def update_customer(db: AsyncSession, customer_id: int, customer: CustomerUpdate) -> Optional[Customer]:
    """Update existing details of a customer profile."""
    db_customer = await get_customer(db, customer_id)
    if not db_customer:
        return None
    
    update_data = customer.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_customer, key, value)
        
    await db.commit()
    await db.refresh(db_customer)
    return db_customer

async def delete_customer(db: AsyncSession, customer_id: int) -> bool:
    """Delete a customer profile by ID."""
    db_customer = await get_customer(db, customer_id)
    if not db_customer:
        return False
    await db.delete(db_customer)
    await db.commit()
    return True


# ==========================================
# 3. KYC CRUD
# ==========================================

async def get_kyc_record(db: AsyncSession, kyc_id: int) -> Optional[KYCRecord]:
    """Retrieve a specific KYC record."""
    query = select(KYCRecord).where(KYCRecord.id == kyc_id)
    result = await db.execute(query)
    return result.scalars().first()

async def get_kyc_records(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[KYCRecord]:
    """Retrieve all KYC application records with pagination."""
    query = select(KYCRecord).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())

async def get_kyc_records_by_user(db: AsyncSession, user_id: int) -> List[KYCRecord]:
    """Retrieve all KYC submissions made by a user."""
    query = select(KYCRecord).where(KYCRecord.user_id == user_id)
    result = await db.execute(query)
    return list(result.scalars().all())

async def create_kyc_record(db: AsyncSession, user_id: int, kyc_data: KYCRecordCreate) -> KYCRecord:
    """Submit a new KYC verification request."""
    db_kyc = KYCRecord(
        user_id=user_id,
        full_name=kyc_data.full_name,
        id_type=kyc_data.id_type,
        id_number=kyc_data.id_number,
        address=kyc_data.address,
        document_urls=kyc_data.document_urls,
        status="pending"
    )
    db.add(db_kyc)
    
    # Update user's kyc_status to pending as well
    user = await get_user(db, user_id)
    if user:
        user.kyc_status = "pending"
        
    await db.commit()
    await db.refresh(db_kyc)
    return db_kyc

async def update_kyc_status(db: AsyncSession, kyc_id: int, status_update: KYCRecordUpdate, admin_id: int) -> Optional[KYCRecord]:
    """Approve or reject a KYC submission."""
    db_kyc = await get_kyc_record(db, kyc_id)
    if not db_kyc:
        return None
    
    db_kyc.status = status_update.status
    db_kyc.admin_notes = status_update.admin_notes
    db_kyc.admin_id = admin_id
    db_kyc.verified_at = datetime.now(timezone.utc)
    
    # Cascade verification status back to the User model
    user = await get_user(db, db_kyc.user_id)
    if user:
        user.kyc_status = status_update.status
        
    await db.commit()
    await db.refresh(db_kyc)
    return db_kyc


# ==========================================
# 4. OTP CRUD
# ==========================================

async def create_otp_record(db: AsyncSession, otp_data: OTPRecordCreate, otp_code: str) -> OTPRecord:
    """Persist a newly generated validation passcode."""
    from datetime import timedelta
    # Expire in 10 minutes
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db_otp = OTPRecord(
        identifier=otp_data.identifier,
        otp_code=otp_code,
        otp_type=otp_data.otp_type,
        expires_at=expires_at,
        used=False
    )
    db.add(db_otp)
    await db.commit()
    await db.refresh(db_otp)
    return db_otp

async def verify_otp_record(db: AsyncSession, identifier: str, otp_code: str) -> bool:
    """Validate a given passcode and mark it as consumed."""
    query = select(OTPRecord).where(
        and_(
            OTPRecord.identifier == identifier,
            OTPRecord.otp_code == otp_code,
            OTPRecord.used == False,
            OTPRecord.expires_at > datetime.now(timezone.utc)
        )
    )
    result = await db.execute(query)
    db_otp = result.scalars().first()
    if not db_otp:
        return False
    
    # Mark OTP as used
    db_otp.used = True
    
    # Additionally update verification state on matching user
    query_user = select(User).where(and_(User.email == identifier))
    res_user = await db.execute(query_user)
    user_by_email = res_user.scalars().first()
    if user_by_email:
        if db_otp.otp_type == "email":
            user_by_email.email_verified = True
        elif db_otp.otp_type == "phone":
            user_by_email.phone_verified = True
    else:
        query_user_phone = select(User).where(and_(User.phone_number == identifier))
        res_user_phone = await db.execute(query_user_phone)
        user_by_phone = res_user_phone.scalars().first()
        if user_by_phone:
            if db_otp.otp_type == "email":
                user_by_phone.email_verified = True
            elif db_otp.otp_type == "phone":
                user_by_phone.phone_verified = True

    await db.commit()
    return True


# ==========================================
# 5. PAYMENT / WALLET / VPA CRUD
# ==========================================

async def create_payment_transaction(db: AsyncSession, user_id: int, tx_data: PaymentTransactionCreate) -> PaymentTransaction:
    """Log and execute a payment transaction, adjusting in-app wallet balances accordingly."""
    db_tx = PaymentTransaction(
        user_id=user_id,
        type=tx_data.type,
        amount=tx_data.amount,
        currency=tx_data.currency or "USD",
        description=tx_data.description,
        vpa_from=tx_data.vpa_from,
        vpa_to=tx_data.vpa_to,
        session_id=tx_data.session_id,
        status="completed"  # Simulating synchronous instant settlement
    )
    db.add(db_tx)

    # Perform balance transfer adjust
    if tx_data.type == "add_funds" or tx_data.type == "refund":
        await update_wallet_balance(db, user_id, tx_data.amount)
    elif tx_data.type == "payment":
        await update_wallet_balance(db, user_id, -tx_data.amount)
    elif tx_data.type == "transfer":
        # Subtract from source
        await update_wallet_balance(db, user_id, -tx_data.amount)
        # Find recipient by VPA
        if tx_data.vpa_to:
            recipient_vpa = await get_vpa_by_address(db, tx_data.vpa_to)
            if recipient_vpa:
                await update_wallet_balance(db, recipient_vpa.user_id, tx_data.amount)
                # Create duplicate transaction record for the recipient as an incoming transfer
                rx_tx = PaymentTransaction(
                    user_id=recipient_vpa.user_id,
                    type="transfer",
                    amount=tx_data.amount,
                    currency=tx_data.currency or "USD",
                    description=f"Transfer from {tx_data.vpa_from or 'Unknown VPA'}",
                    vpa_from=tx_data.vpa_from,
                    vpa_to=tx_data.vpa_to,
                    session_id=tx_data.session_id,
                    status="completed"
                )
                db.add(rx_tx)

    await db.commit()
    await db.refresh(db_tx)
    return db_tx

async def get_payment_transaction(db: AsyncSession, tx_id: int) -> Optional[PaymentTransaction]:
    """Retrieve transaction record details."""
    query = select(PaymentTransaction).where(PaymentTransaction.id == tx_id)
    result = await db.execute(query)
    return result.scalars().first()

async def get_payment_transactions_by_user(db: AsyncSession, user_id: int, skip: int = 0, limit: int = 50) -> List[PaymentTransaction]:
    """Retrieve transaction history for a user."""
    query = select(PaymentTransaction).where(PaymentTransaction.user_id == user_id).order_by(PaymentTransaction.created_date.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())

async def get_wallet_by_user(db: AsyncSession, user_id: int) -> Optional[Wallet]:
    """Fetch wallet details associated with a user."""
    query = select(Wallet).where(Wallet.user_id == user_id)
    result = await db.execute(query)
    db_wallet = result.scalars().first()
    if not db_wallet:
        # Lazy initialization fallback
        db_wallet = Wallet(user_id=user_id, balance=0.0, currency="USD")
        db.add(db_wallet)
        await db.commit()
        await db.refresh(db_wallet)
    return db_wallet

async def update_wallet_balance(db: AsyncSession, user_id: int, amount_change: float) -> Optional[Wallet]:
    """Add or subtract absolute amount values on user's digital balance."""
    wallet = await get_wallet_by_user(db, user_id)
    if not wallet:
        return None
    wallet.balance += amount_change
    await db.flush()
    return wallet

async def create_vpa(db: AsyncSession, user_id: int, vpa_data: VPACreate) -> VPA:
    """Register a new Virtual Payment Address handle for a user."""
    db_vpa = VPA(
        user_id=user_id,
        vpa_address=vpa_data.vpa_address,
        is_active=True
    )
    db.add(db_vpa)
    await db.commit()
    await db.refresh(db_vpa)
    return db_vpa

async def get_vpa_by_user(db: AsyncSession, user_id: int) -> Optional[VPA]:
    """Fetch VPA mapping for a user."""
    query = select(VPA).where(VPA.user_id == user_id)
    result = await db.execute(query)
    return result.scalars().first()

async def get_vpa_by_address(db: AsyncSession, vpa_address: str) -> Optional[VPA]:
    """Resolve user mapping by Virtual Payment Address."""
    query = select(VPA).where(VPA.vpa_address == vpa_address)
    result = await db.execute(query)
    return result.scalars().first()


# ==========================================
# 6. HMAIL CRUD
# ==========================================

async def create_hmail_account(db: AsyncSession, user_id: int, account_data: HmailAccountCreate) -> HmailAccount:
    """Provision a new internal mail profile."""
    email_addr = account_data.email_address or f"{account_data.username}@hmail.tu5g"
    db_account = HmailAccount(
        user_id=user_id,
        username=account_data.username,
        email_address=email_addr,
        is_active=True
    )
    db.add(db_account)
    await db.commit()
    await db.refresh(db_account)
    return db_account

async def get_hmail_account_by_user(db: AsyncSession, user_id: int) -> Optional[HmailAccount]:
    """Fetch hmail details for a user."""
    query = select(HmailAccount).where(HmailAccount.user_id == user_id)
    result = await db.execute(query)
    return result.scalars().first()

async def get_hmail_account_by_address(db: AsyncSession, email_address: str) -> Optional[HmailAccount]:
    """Retrieve hmail details by its unique handle address."""
    query = select(HmailAccount).where(HmailAccount.email_address == email_address)
    result = await db.execute(query)
    return result.scalars().first()

async def create_hmail_message(db: AsyncSession, account_id: int, from_email: str, msg_data: HmailMessageCreate) -> HmailMessage:
    """Draft and persist an internal email transaction."""
    db_msg = HmailMessage(
        account_id=account_id,
        from_email=from_email,
        to_email=msg_data.to_email,
        subject=msg_data.subject,
        body=msg_data.body,
        is_read=False
    )
    db.add(db_msg)

    # Deliver to matching internal inbox as well, if recipient exists on platform
    recipient_account = await get_hmail_account_by_address(db, msg_data.to_email)
    if recipient_account:
        db_recipient_msg = HmailMessage(
            account_id=recipient_account.id,
            from_email=from_email,
            to_email=msg_data.to_email,
            subject=msg_data.subject,
            body=msg_data.body,
            is_read=False
        )
        db.add(db_recipient_msg)

    await db.commit()
    await db.refresh(db_msg)
    return db_msg

async def get_hmail_messages_by_account(db: AsyncSession, account_id: int, is_read: Optional[bool] = None) -> List[HmailMessage]:
    """Retrieve incoming and outgoing secure mail messages."""
    if is_read is not None:
        query = select(HmailMessage).where(and_(HmailMessage.account_id == account_id, HmailMessage.is_read == is_read)).order_by(HmailMessage.created_date.desc())
    else:
        query = select(HmailMessage).where(HmailMessage.account_id == account_id).order_by(HmailMessage.created_date.desc())
    
    result = await db.execute(query)
    return list(result.scalars().all())


# ==========================================
# 7. GOVERNANCE CRUD
# ==========================================

async def create_governance_application(db: AsyncSession, user_id: int, app_data: GovernanceApplicationCreate) -> GovernanceApplication:
    """Submit a formal organization membership request."""
    db_app = GovernanceApplication(
        user_id=user_id,
        category=app_data.category,
        organization_name=app_data.organization_name,
        description=app_data.description,
        proof_url=app_data.proof_url,
        status="pending"
    )
    db.add(db_app)
    await db.commit()
    await db.refresh(db_app)
    return db_app

async def get_governance_application(db: AsyncSession, app_id: int) -> Optional[GovernanceApplication]:
    """Fetch details for a specific governance application."""
    query = select(GovernanceApplication).where(GovernanceApplication.id == app_id)
    result = await db.execute(query)
    return result.scalars().first()

async def get_governance_applications(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[GovernanceApplication]:
    """List membership applications with pagination."""
    query = select(GovernanceApplication).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())

async def update_governance_status(db: AsyncSession, app_id: int, status_update: GovernanceApplicationUpdate) -> Optional[GovernanceApplication]:
    """Approve or reject a governance organization membership request."""
    db_app = await get_governance_application(db, app_id)
    if not db_app:
        return None
    db_app.status = status_update.status
    db_app.admin_notes = status_update.admin_notes
    db_app.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(db_app)
    return db_app


# ==========================================
# 8. AUDIT LOG CRUD
# ==========================================

async def create_audit_log(db: AsyncSession, log_data: AuditLogCreate) -> AuditLog:
    """Create a security trace trace audit record."""
    db_log = AuditLog(
        user_id=log_data.user_id,
        action=log_data.action,
        resource=log_data.resource,
        ip_address=log_data.ip_address,
        details=log_data.details
    )
    db.add(db_log)
    await db.commit()
    await db.refresh(db_log)
    return db_log

async def get_audit_logs(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[AuditLog]:
    """List complete administrative trace logs with pagination."""
    query = select(AuditLog).order_by(AuditLog.created_date.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


# ==========================================
# 9. VIRTUAL CELL CRUD
# ==========================================

async def get_virtual_cell(db: AsyncSession, cell_id: str) -> Optional[VirtualCell]:
    """Retrieve a virtual cell's metadata by its network ID."""
    query = select(VirtualCell).where(VirtualCell.cell_id == cell_id)
    result = await db.execute(query)
    return result.scalars().first()

async def get_virtual_cells(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[VirtualCell]:
    """Retrieve virtual cells with pagination."""
    query = select(VirtualCell).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())

async def create_virtual_cell(db: AsyncSession, cell: VirtualCellCreate) -> VirtualCell:
    """Provision a new virtual cell transmitter."""
    db_cell = VirtualCell(**cell.model_dump())
    db.add(db_cell)
    await db.commit()
    await db.refresh(db_cell)
    return db_cell

async def update_virtual_cell(db: AsyncSession, cell_id: str, cell: VirtualCellUpdate) -> Optional[VirtualCell]:
    """Update performance telemetry or details of an existing virtual cell."""
    db_cell = await get_virtual_cell(db, cell_id)
    if not db_cell:
        return None
    
    update_data = cell.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_cell, key, value)
        
    await db.commit()
    await db.refresh(db_cell)
    return db_cell

async def delete_virtual_cell(db: AsyncSession, cell_id: str) -> bool:
    """Delete/de-provision a virtual cell from the network registry."""
    db_cell = await get_virtual_cell(db, cell_id)
    if not db_cell:
        return False
    await db.delete(db_cell)
    await db.commit()
    return True


# ==========================================
# 10. HOLOGRAPHIC SESSION CRUD
# ==========================================

async def get_holographic_session(db: AsyncSession, session_id: int) -> Optional[HolographicSession]:
    """Retrieve details for a specific holographic companion streaming session."""
    query = select(HolographicSession).where(HolographicSession.id == session_id)
    result = await db.execute(query)
    return result.scalars().first()

async def get_holographic_sessions_by_user(
    db: AsyncSession, user_id: int, skip: int = 0, limit: int = 100
) -> List[HolographicSession]:
    """Fetch all holographic sessions associated with a specific user."""
    query = select(HolographicSession).where(HolographicSession.user_id == user_id).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())

async def create_holographic_session(
    db: AsyncSession, user_id: int, session: HolographicSessionCreate
) -> HolographicSession:
    """Initialize a brand-new user holographic streaming session."""
    db_session = HolographicSession(user_id=user_id, **session.model_dump())
    db.add(db_session)
    await db.commit()
    await db.refresh(db_session)
    return db_session

async def update_holographic_session_status(
    db: AsyncSession, session_id: int, status: str, ended_at=None
) -> Optional[HolographicSession]:
    """Update status (active/inactive) and record end time for holographic sessions."""
    db_session = await get_holographic_session(db, session_id)
    if not db_session:
        return None
    
    db_session.status = status
    if ended_at:
        db_session.ended_at = ended_at
        
    await db.commit()
    await db.refresh(db_session)
    return db_session


# ==========================================
# 11. CHAT MESSAGE CRUD
# ==========================================

async def create_chat_message(db: AsyncSession, user_id: int, message: ChatMessageCreate) -> ChatMessage:
    """Save an AI character companion chat message."""
    db_message = ChatMessage(user_id=user_id, **message.model_dump())
    db.add(db_message)
    await db.commit()
    await db.refresh(db_message)
    return db_message

async def get_chat_messages_by_user(db: AsyncSession, user_id: int, limit: int = 50) -> List[ChatMessage]:
    """Retrieve recent companion chat dialogue history chronologically."""
    query = select(ChatMessage).where(ChatMessage.user_id == user_id).order_by(ChatMessage.created_date.desc()).limit(limit)
    result = await db.execute(query)
    return list(reversed(result.scalars().all()))


# ==========================================
# 12. TELEMETRY RECORD CRUD
# ==========================================

async def create_telemetry_record(db: AsyncSession, telemetry: TelemetryData) -> TelemetryRecord:
    """Save network-performance metrics associated with a virtual cell."""
    db_telemetry = TelemetryRecord(**telemetry.model_dump())
    db.add(db_telemetry)
    await db.commit()
    await db.refresh(db_telemetry)
    return db_telemetry

async def get_telemetry_records(db: AsyncSession, cell_id: str, limit: int = 100) -> List[TelemetryRecord]:
    """Retrieve a list of connection quality recordings for a virtual cell."""
    query = select(TelemetryRecord).where(TelemetryRecord.cell_id == cell_id).order_by(TelemetryRecord.timestamp.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


# ==========================================
# 13. ESIM RESERVATION CRUD
# ==========================================

async def create_esim_reservation(db: AsyncSession, user_id: int, reservation_data: ESIMReservationCreate) -> ESIMReservation:
    """Create a hold or reservation for a specific eSIM or number."""
    db_res = ESIMReservation(
        user_id=user_id,
        number=reservation_data.number,
        expires_at=reservation_data.expires_at,
        is_active=True
    )
    db.add(db_res)
    await db.commit()
    await db.refresh(db_res)
    return db_res

async def get_esim_reservation(db: AsyncSession, reservation_id: int) -> Optional[ESIMReservation]:
    """Retrieve details for a specific reservation."""
    query = select(ESIMReservation).where(ESIMReservation.id == reservation_id)
    result = await db.execute(query)
    return result.scalars().first()

async def get_esim_reservations_by_user(db: AsyncSession, user_id: int) -> List[ESIMReservation]:
    """List all reservations made by a user."""
    query = select(ESIMReservation).where(and_(ESIMReservation.user_id == user_id, ESIMReservation.is_active == True))
    result = await db.execute(query)
    return list(result.scalars().all())

async def update_esim_reservation_status(db: AsyncSession, reservation_id: int, is_active: bool) -> Optional[ESIMReservation]:
    """Deactivate or update eSIM reservation status."""
    db_res = await get_esim_reservation(db, reservation_id)
    if not db_res:
        return None
    db_res.is_active = is_active
    await db.commit()
    await db.refresh(db_res)
    return db_res
