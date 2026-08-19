"""
HMAIL (Hope Mail) Service for the TU5G platform.
Handles mailbox account creation under the tu5g.online domain, verification status checks,
KYC-based activation gates, and secure incoming/outgoing email delivery.
Supports internal tu5g.online delivery, external SMTP forwarding, and automated support forwarding
from support@tu5g.online to tu5g.online@gmail.com.
Supports dual DB storage (SQLAlchemy AsyncSession) and in-memory fallback.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import HmailAccount, HmailMessage
from app.services.email import send_email as external_smtp_send_email

logger = logging.getLogger(__name__)

# ==========================================
# Constant Configurations
# ==========================================
HMAIL_DOMAIN = "tu5g.online"
SUPPORT_EMAIL = f"support@{HMAIL_DOMAIN}"
GMAIL_FORWARD = "tu5g.online@gmail.com"


# ==========================================
# In-Memory Backup Databases
# ==========================================
# Structure: { user_id: account_dict_record }
_mock_hmail_accounts: Dict[str, Dict[str, Any]] = {}

# Structure: List of message dict records
_mock_hmail_messages: List[Dict[str, Any]] = []


# ==========================================
# Core HMAIL Service Functions
# ==========================================

async def create_hmail_account(
    user_id: str,
    username: str,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Creates a new HMAIL account username@tu5g.online for a user in 'pending' status.

    Args:
        user_id (str): Unique identifier of the user.
        username (str): Desired email mailbox name prefix.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Created hmail account record.

    Raises:
        ValueError: If username contains invalid characters or is already registered.
    """
    user_id_str = str(user_id)
    username_clean = username.strip().lower()

    # Validate username formatting
    if not username_clean.isalnum() and "_" not in username_clean and "." not in username_clean:
        raise ValueError("Username can only contain alphanumeric characters, underscores, and dots.")

    email_address = f"{username_clean}@{HMAIL_DOMAIN}"
    account_id = str(uuid.uuid4())
    now = datetime.utcnow()

    account_data = {
        "id": account_id,
        "user_id": user_id_str,
        "username": username_clean,
        "email_address": email_address,
        "status": "pending",  # Pending KYC verification
        "created_date": now,
        "updated_date": now
    }

    if db:
        try:
            # Check if email is already taken in DB
            query_taken = select(HmailAccount).where(HmailAccount.email_address == email_address)
            res_taken = await db.execute(query_taken)
            if res_taken.scalars().first():
                raise ValueError(f"Email address '{email_address}' is already registered.")

            # Check if user already has an account
            query_user = select(HmailAccount).where(HmailAccount.user_id == user_id_str)
            res_user = await db.execute(query_user)
            if res_user.scalars().first():
                raise ValueError("User is already registered with an existing HMAIL account.")

            # Create DB account record
            db_account = HmailAccount(
                id=account_id,
                user_id=user_id_str,
                username=username_clean,
                email_address=email_address,
                status="pending",
                created_date=now,
                updated_date=now
            )
            db.add(db_account)
            await db.flush()

            logger.info(f"HMAIL Account '{email_address}' created successfully in DB (Pending KYC).")
            return {
                "id": db_account.id,
                "user_id": db_account.user_id,
                "username": db_account.username,
                "email_address": db_account.email_address,
                "status": db_account.status,
                "created_at": db_account.created_date,
                "updated_at": db_account.updated_date
            }

        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"Database error creating HMAIL account: {e}. Falling back to in-memory.")
            await db.rollback()

    # In-memory fallback
    # Check email uniqueness in memory
    for acc in _mock_hmail_accounts.values():
        if acc["email_address"] == email_address:
            raise ValueError(f"Email address '{email_address}' is already registered.")
        if acc["user_id"] == user_id_str:
            raise ValueError("User already has an in-memory HMAIL account.")

    _mock_hmail_accounts[user_id_str] = account_data
    logger.info(f"HMAIL Account '{email_address}' created successfully in memory (Pending KYC).")
    return {
        "id": account_id,
        "user_id": user_id_str,
        "username": username_clean,
        "email_address": email_address,
        "status": "pending",
        "created_at": now,
        "updated_at": now
    }


async def get_hmail_status(user_id: str, db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """
    Fetches the activation status of a user's HMAIL account.

    Args:
        user_id (str): User identifier.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Status information dictionary.
    """
    user_id_str = str(user_id)

    if db:
        try:
            query = select(HmailAccount).where(HmailAccount.user_id == user_id_str)
            res = await db.execute(query)
            db_account = res.scalars().first()
            if db_account:
                return {
                    "user_id": db_account.user_id,
                    "username": db_account.username,
                    "email_address": db_account.email_address,
                    "status": db_account.status,
                    "created_at": db_account.created_date
                }
        except Exception as e:
            logger.warning(f"Database error fetching HMAIL status: {e}. Falling back to in-memory.")

    # In-memory fallback
    acc = _mock_hmail_accounts.get(user_id_str)
    if acc:
        return {
            "user_id": acc["user_id"],
            "username": acc["username"],
            "email_address": acc["email_address"],
            "status": acc["status"],
            "created_at": acc["created_date"]
        }

    return {
        "user_id": user_id_str,
        "username": None,
        "email_address": None,
        "status": "not_created",
        "created_at": None
    }


async def activate_hmail(
    user_id: str,
    kyc_verified: bool,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Activates a pending HMAIL account. Gated by verified user KYC status.

    Args:
        user_id (str): User identifier.
        kyc_verified (bool): Verification status indicator.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Updated account status.

    Raises:
        ValueError: If KYC is not verified or HMAIL account doesn't exist.
    """
    if not kyc_verified:
        raise ValueError("Access Denied: HMAIL mailboxes can only be activated for KYC-verified users.")

    user_id_str = str(user_id)
    now = datetime.utcnow()

    if db:
        try:
            query = select(HmailAccount).where(HmailAccount.user_id == user_id_str)
            res = await db.execute(query)
            db_account = res.scalars().first()

            if not db_account:
                raise ValueError("HMAIL account mailbox profile does not exist.")

            db_account.status = "activated"
            db_account.updated_date = now
            await db.flush()

            logger.info(f"HMAIL Account '{db_account.email_address}' activated successfully via DB.")
            return {
                "user_id": db_account.user_id,
                "email_address": db_account.email_address,
                "status": "activated",
                "activated_at": now
            }
        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"Database error activating HMAIL mailbox: {e}. Falling back to in-memory.")
            await db.rollback()

    # In-memory fallback
    if user_id_str not in _mock_hmail_accounts:
        raise ValueError("HMAIL account mailbox profile does not exist.")

    acc = _mock_hmail_accounts[user_id_str]
    acc["status"] = "activated"
    acc["updated_date"] = now

    logger.info(f"HMAIL Account '{acc['email_address']}' activated successfully via in-memory.")
    return {
        "user_id": user_id_str,
        "email_address": acc["email_address"],
        "status": "activated",
        "activated_at": now
    }


async def send_hmail(
    from_user: str,
    to_email: str,
    subject: str,
    body: str,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Sends an email from a TU5G HMAIL mailbox.
    Supports internal routing to other tu5g.online addresses,
    external delivery via outbound SMTP client, and automated Gmail forwarding for support.

    Args:
        from_user (str): Sender's user_id or username prefix.
        to_email (str): Target recipient email address.
        subject (str): Email subject.
        body (str): Email message content.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Record of the sent message.
    """
    # 1. Look up and verify sender account
    sender_account = None
    sender_user_id = str(from_user)
    
    if db:
        try:
            # Query by user_id or username
            query = select(HmailAccount).where(
                (HmailAccount.user_id == sender_user_id) | 
                (HmailAccount.username == sender_user_id.lower())
            )
            res = await db.execute(query)
            sender_account = res.scalars().first()
        except Exception as e:
            logger.warning(f"Database error finding sender: {e}")

    if not sender_account:
        # Fallback search in memory
        for acc in _mock_hmail_accounts.values():
            if acc["user_id"] == sender_user_id or acc["username"] == sender_user_id.lower():
                sender_account = acc
                break

    if not sender_account:
        raise ValueError(f"Sender HMAIL account profile '{from_user}' not found.")

    sender_email = sender_account["email_address"] if isinstance(sender_account, dict) else sender_account.email_address
    sender_status = sender_account["status"] if isinstance(sender_account, dict) else sender_account.status
    sender_uid = sender_account["user_id"] if isinstance(sender_account, dict) else sender_account.user_id

    if sender_status != "activated":
        raise ValueError(f"HMAIL sender mailbox '{sender_email}' is not activated. (Status: {sender_status})")

    to_email_clean = to_email.strip().lower()
    msg_id = str(uuid.uuid4())
    now = datetime.utcnow()

    msg_data = {
        "id": msg_id,
        "from_email": sender_email,
        "to_email": to_email_clean,
        "subject": subject,
        "body": body,
        "is_read": False,
        "created_date": now
    }

    # 2. Delivery mechanics
    delivery_status = "delivered"
    
    if to_email_clean.endswith(f"@{HMAIL_DOMAIN}"):
        # INTERNAL TU5G ROUTING
        recipient_account = None
        
        # Check DB
        if db:
            try:
                query_rec = select(HmailAccount).where(HmailAccount.email_address == to_email_clean)
                res_rec = await db.execute(query_rec)
                recipient_account = res_rec.scalars().first()
            except Exception as e:
                logger.warning(f"Database lookup of recipient failed: {e}")

        # Check in-memory
        if not recipient_account:
            for acc in _mock_hmail_accounts.values():
                if acc["email_address"] == to_email_clean:
                    recipient_account = acc
                    break

        if not recipient_account:
            logger.warning(f"Internal delivery bounce: Recipient mailbox '{to_email_clean}' not found.")
            delivery_status = "bounced"
        else:
            rec_uid = recipient_account["user_id"] if isinstance(recipient_account, dict) else recipient_account.user_id
            
            # Save incoming message for the recipient
            if db:
                try:
                    db_msg = HmailMessage(
                        id=msg_id,
                        user_id=rec_uid,
                        from_email=sender_email,
                        to_email=to_email_clean,
                        subject=subject,
                        body=body,
                        is_read=False,
                        created_date=now
                    )
                    db.add(db_msg)
                    await db.flush()
                except Exception as e:
                    logger.warning(f"Failed to write DB incoming message: {e}")
                    await db.rollback()
                    # fallback to list
                    _mock_hmail_messages.append({**msg_data, "user_id": rec_uid})
            else:
                _mock_hmail_messages.append({**msg_data, "user_id": rec_uid})

        # Special Support Routing: forward to GMAIL_FORWARD
        if to_email_clean == SUPPORT_EMAIL:
            logger.info(f"HMAIL: Support email detected. Forwarding from '{sender_email}' to Gmail: '{GMAIL_FORWARD}'...")
            try:
                forward_subject = f"[Forwarded Support] {subject}"
                forward_body = f"Original Sender: {sender_email}\n\n{body}"
                await external_smtp_send_email(GMAIL_FORWARD, forward_subject, forward_body)
                logger.info(f"HMAIL Support email successfully forwarded to '{GMAIL_FORWARD}'.")
            except Exception as e:
                logger.error(f"Support email forwarding to Gmail failed: {e}")

    else:
        # EXTERNAL ROUTING via Outbound SMTP client
        logger.info(f"HMAIL: External recipient detected. Transmitting via SMTP to '{to_email_clean}'...")
        try:
            await external_smtp_send_email(to_email_clean, subject, body)
            delivery_status = "transmitted"
            logger.info("Outbound external SMTP mail dispatched successfully.")
        except Exception as e:
            logger.error(f"External SMTP transmission failed: {e}")
            delivery_status = "failed"

    # Save outgoing message record for the sender
    if db:
        try:
            db_sent_msg = HmailMessage(
                id=str(uuid.uuid4()),  # unique outgoing record
                user_id=sender_uid,
                from_email=sender_email,
                to_email=to_email_clean,
                subject=subject,
                body=body,
                is_read=True,  # Sender's copy is obviously read
                created_date=now
            )
            db.add(db_sent_msg)
            await db.flush()
        except Exception as e:
            logger.warning(f"Failed to record outgoing DB copy: {e}")
            await db.rollback()
            _mock_hmail_messages.append({**msg_data, "user_id": sender_uid, "is_read": True})
    else:
        _mock_hmail_messages.append({**msg_data, "user_id": sender_uid, "is_read": True})

    return {
        "message_id": msg_id,
        "from": sender_email,
        "to": to_email_clean,
        "subject": subject,
        "status": delivery_status,
        "sent_at": now
    }


async def receive_hmail(
    user_id: str,
    limit: int = 20,
    db: Optional[AsyncSession] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves incoming emails received in the user's HMAIL inbox.

    Args:
        user_id (str): User recipient identifier.
        limit (int): Maximum messages to pull. Defaults to 20.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        List[Dict[str, Any]]: List of email messages.
    """
    user_id_str = str(user_id)

    # 1. Fetch user's email address
    user_email = None
    if db:
        try:
            query = select(HmailAccount).where(HmailAccount.user_id == user_id_str)
            res = await db.execute(query)
            acc = res.scalars().first()
            if acc:
                user_email = acc.email_address
        except Exception as e:
            logger.warning(f"Database error fetching mailbox details: {e}")

    if not user_email:
        acc = _mock_hmail_accounts.get(user_id_str)
        if acc:
            user_email = acc["email_address"]

    if not user_email:
        # User doesn't even have a mailbox created
        return []

    # 2. Fetch messages delivered to this user's mailbox address
    if db:
        try:
            query_msg = (
                select(HmailMessage)
                .where(HmailMessage.to_email == user_email)
                .order_by(HmailMessage.created_date.desc())
                .limit(limit)
            )
            res_msg = await db.execute(query_msg)
            db_messages = res_msg.scalars().all()
            
            # Auto-mark retrieved messages as read for inbox convenience
            for m in db_messages:
                m.is_read = True
            await db.flush()

            return [
                {
                    "message_id": m.id,
                    "from": m.from_email,
                    "to": m.to_email,
                    "subject": m.subject,
                    "body": m.body,
                    "is_read": m.is_read,
                    "received_at": m.created_date
                }
                for m in db_messages
            ]
        except Exception as e:
            logger.warning(f"Database error fetching HMAIL messages: {e}. Using in-memory fallback.")

    # In-memory fallback
    incoming_mails = []
    for m in _mock_hmail_messages:
        # Match messages destined for user's mailbox
        if m["to_email"] == user_email:
            m["is_read"] = True  # Auto mark as read
            incoming_mails.append({
                "message_id": m["id"],
                "from": m["from_email"],
                "to": m["to_email"],
                "subject": m["subject"],
                "body": m["body"],
                "is_read": True,
                "received_at": m["created_date"]
            })

    # Sort descending received_at
    incoming_mails.sort(key=lambda x: x["received_at"], reverse=True)
    return incoming_mails[:limit]
