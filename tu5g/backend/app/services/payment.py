"""
Payment Service for the TU5G platform.
Implements HOPE PAY (fiat on-ramp via add_funds) and UPS PAY (VPA peer-to-peer transfers).
Supports virtual payment addresses (VPA), transaction history, payment sessions, and
wallet balances. Dual-mode support: SQLAlchemy async DB or local in-memory fallback.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import Wallet, Transaction

logger = logging.getLogger(__name__)

# ==========================================
# In-Memory Backup Databases
# ==========================================
# Keys are user_id (str)
_mock_wallets: Dict[str, Dict[str, Any]] = {}
# Stores list of dict transaction objects
_mock_transactions: List[Dict[str, Any]] = []
# Stores pending payment sessions
_mock_payment_sessions: Dict[str, Dict[str, Any]] = {}


# ==========================================
# Core Payment Service Functions
# ==========================================

async def create_vpa(
    user_id: str,
    preferred_name: Optional[str] = None,
    db: Optional[AsyncSession] = None
) -> str:
    """
    Creates or updates a Virtual Payment Address (VPA) like `username@upspay` for a user.

    Args:
        user_id (str): Unique identifier of the wallet owner.
        preferred_name (str, optional): Preferred prefix. Defaults to 'user_{user_id}' if None.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        str: The created VPA string.

    Raises:
        ValueError: If the VPA is already in use by another user.
    """
    prefix = preferred_name.strip().lower() if preferred_name else f"user_{user_id}"
    vpa = f"{prefix}@upspay"

    # 1. Check uniqueness across other users
    if db:
        try:
            # Check if this VPA is already assigned to a different user
            query = select(Wallet).where(Wallet.vpa == vpa, Wallet.user_id != str(user_id))
            result = await db.execute(query)
            existing = result.scalars().first()
            if existing:
                raise ValueError(f"VPA '{vpa}' is already registered by another user.")

            # Get or create the user's wallet
            query_my_wallet = select(Wallet).where(Wallet.user_id == str(user_id))
            result_my_wallet = await db.execute(query_my_wallet)
            wallet = result_my_wallet.scalars().first()

            if wallet:
                wallet.vpa = vpa
                wallet.updated_date = datetime.utcnow()
            else:
                wallet = Wallet(
                    id=str(uuid.uuid4()),
                    user_id=str(user_id),
                    balance=0.0,
                    vpa=vpa,
                    created_date=datetime.utcnow(),
                    updated_date=datetime.utcnow()
                )
                db.add(wallet)
            
            await db.flush()
            logger.info(f"VPA '{vpa}' successfully created for user '{user_id}' (DB)")
            return vpa

        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"Database error creating VPA: {e}. Falling back to in-memory store.")
            await db.rollback()

    # In-memory fallback
    user_id_str = str(user_id)
    # Check if VPA exists for another user in-memory
    for other_uid, w in _mock_wallets.items():
        if other_uid != user_id_str and w.get("vpa") == vpa:
            raise ValueError(f"VPA '{vpa}' is already registered by another user.")

    # Get or create in-memory wallet
    if user_id_str not in _mock_wallets:
        _mock_wallets[user_id_str] = {
            "id": str(uuid.uuid4()),
            "user_id": user_id_str,
            "balance": 0.0,
            "vpa": vpa,
            "created_date": datetime.utcnow(),
            "updated_date": datetime.utcnow()
        }
    else:
        _mock_wallets[user_id_str]["vpa"] = vpa
        _mock_wallets[user_id_str]["updated_date"] = datetime.utcnow()

    logger.info(f"VPA '{vpa}' successfully created for user '{user_id}' (Memory)")
    return vpa


async def get_vpa(user_id: str, db: Optional[AsyncSession] = None) -> Optional[str]:
    """
    Retrieves the VPA for a specific user.

    Args:
        user_id (str): User identifier.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Optional[str]: VPA address if exists, otherwise None.
    """
    if db:
        try:
            query = select(Wallet).where(Wallet.user_id == str(user_id))
            result = await db.execute(query)
            wallet = result.scalars().first()
            return wallet.vpa if wallet else None
        except Exception as e:
            logger.warning(f"Database error getting VPA: {e}. Falling back to in-memory.")

    # In-memory fallback
    wallet = _mock_wallets.get(str(user_id))
    return wallet.get("vpa") if wallet else None


async def get_wallet_balance(user_id: str, db: Optional[AsyncSession] = None) -> float:
    """
    Retrieves the current wallet balance for a user.
    Creates a wallet with 0.0 balance if it doesn't already exist.

    Args:
        user_id (str): User identifier.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        float: Balance rounded to 2 decimal places.
    """
    user_id_str = str(user_id)
    if db:
        try:
            query = select(Wallet).where(Wallet.user_id == user_id_str)
            result = await db.execute(query)
            wallet = result.scalars().first()
            if wallet:
                return round(float(wallet.balance), 2)
            else:
                # Create wallet on the fly with 0 balance
                wallet = Wallet(
                    id=str(uuid.uuid4()),
                    user_id=user_id_str,
                    balance=0.0,
                    vpa=None,
                    created_date=datetime.utcnow(),
                    updated_date=datetime.utcnow()
                )
                db.add(wallet)
                await db.flush()
                return 0.0
        except Exception as e:
            logger.warning(f"Database error reading wallet balance: {e}. Using in-memory fallback.")
            await db.rollback()

    # In-memory fallback
    if user_id_str not in _mock_wallets:
        _mock_wallets[user_id_str] = {
            "id": str(uuid.uuid4()),
            "user_id": user_id_str,
            "balance": 0.0,
            "vpa": None,
            "created_date": datetime.utcnow(),
            "updated_date": datetime.utcnow()
        }
    return round(float(_mock_wallets[user_id_str]["balance"]), 2)


async def add_funds(
    user_id: str,
    amount: float,
    source: str,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    HOPE PAY: Simulates a fiat on-ramp by adding money to a user's wallet.
    Increases the balance and records a transaction.

    Args:
        user_id (str): User receiving the funds.
        amount (float): Value to credit.
        source (str): Source description (e.g. 'Credit Card', 'Bank Transfer').
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Dict containing the resulting transaction details and updated balance.
    """
    if amount <= 0:
        raise ValueError("On-ramp amount must be greater than zero.")
    
    clean_amount = round(float(amount), 2)
    tx_id = str(uuid.uuid4())
    user_id_str = str(user_id)
    now = datetime.utcnow()

    tx_data = {
        "id": tx_id,
        "user_id": user_id_str,
        "amount": clean_amount,
        "currency": "USD",
        "description": f"Hope Pay Fiat On-Ramp via {source}",
        "type": "fiat_onramp",
        "status": "success",
        "source_vpa": None,
        "recipient_vpa": None,
        "created_date": now,
    }

    if db:
        try:
            # Check or create wallet
            query = select(Wallet).where(Wallet.user_id == user_id_str)
            result = await db.execute(query)
            wallet = result.scalars().first()

            if not wallet:
                wallet = Wallet(
                    id=str(uuid.uuid4()),
                    user_id=user_id_str,
                    balance=0.0,
                    vpa=None,
                    created_date=now,
                    updated_date=now
                )
                db.add(wallet)

            wallet.balance = round(wallet.balance + clean_amount, 2)
            wallet.updated_date = now

            db_tx = Transaction(
                id=tx_id,
                user_id=user_id_str,
                amount=clean_amount,
                currency="USD",
                description=tx_data["description"],
                type="fiat_onramp",
                status="success",
                source_vpa=None,
                recipient_vpa=None,
                created_date=now
            )
            db.add(db_tx)
            await db.flush()

            logger.info(f"HOPE PAY: Credited ${clean_amount} to user '{user_id_str}' via '{source}' (DB)")
            return {
                "transaction_id": tx_id,
                "user_id": user_id_str,
                "amount": clean_amount,
                "balance": wallet.balance,
                "status": "success",
                "description": tx_data["description"],
                "created_at": now
            }
        except Exception as e:
            logger.warning(f"Database error in add_funds: {e}. Falling back to in-memory.")
            await db.rollback()

    # In-memory fallback
    if user_id_str not in _mock_wallets:
        _mock_wallets[user_id_str] = {
            "id": str(uuid.uuid4()),
            "user_id": user_id_str,
            "balance": 0.0,
            "vpa": None,
            "created_date": now,
            "updated_date": now
        }
    
    wallet_rec = _mock_wallets[user_id_str]
    wallet_rec["balance"] = round(wallet_rec["balance"] + clean_amount, 2)
    wallet_rec["updated_date"] = now
    
    _mock_transactions.append(tx_data)
    
    logger.info(f"HOPE PAY: Credited ${clean_amount} to user '{user_id_str}' via '{source}' (Memory)")
    return {
        "transaction_id": tx_id,
        "user_id": user_id_str,
        "amount": clean_amount,
        "balance": wallet_rec["balance"],
        "status": "success",
        "description": tx_data["description"],
        "created_at": now
    }


async def process_payment(
    vpa: str,
    amount: float,
    recipient_vpa: str,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    UPS PAY: Performs a direct peer-to-peer VPA funds transfer.
    Deducts balance from sender VPA and credits recipient VPA.

    Args:
        vpa (str): Sender's VPA (e.g. sender@upspay).
        amount (float): Transfer value.
        recipient_vpa (str): Recipient's VPA (e.g. recipient@upspay).
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Dict with transaction status and reference ID.

    Raises:
        ValueError: If sender/recipient VPA is invalid, or if sender has insufficient funds.
    """
    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")
    
    clean_amount = round(float(amount), 2)
    tx_id = str(uuid.uuid4())
    now = datetime.utcnow()

    if db:
        try:
            # 1. Fetch sender's wallet
            query_sender = select(Wallet).where(Wallet.vpa == vpa)
            res_sender = await db.execute(query_sender)
            sender_wallet = res_sender.scalars().first()
            if not sender_wallet:
                raise ValueError(f"Sender VPA '{vpa}' not found.")

            # 2. Fetch recipient's wallet
            query_recipient = select(Wallet).where(Wallet.vpa == recipient_vpa)
            res_recipient = await db.execute(query_recipient)
            recipient_wallet = res_recipient.scalars().first()
            if not recipient_wallet:
                raise ValueError(f"Recipient VPA '{recipient_vpa}' not found.")

            if sender_wallet.user_id == recipient_wallet.user_id:
                raise ValueError("Self-transfers between the same VPA wallet owner are not permitted.")

            # 3. Balance verification
            if sender_wallet.balance < clean_amount:
                raise ValueError(f"Insufficient funds in sender wallet. Required: ${clean_amount}, Current: ${sender_wallet.balance}")

            # 4. Perform atomic transfer
            sender_wallet.balance = round(sender_wallet.balance - clean_amount, 2)
            recipient_wallet.balance = round(recipient_wallet.balance + clean_amount, 2)
            sender_wallet.updated_date = now
            recipient_wallet.updated_date = now

            # 5. Create transactions records (debit and credit)
            desc = f"UPS Pay VPA P2P Transfer from {vpa} to {recipient_vpa}"
            db_tx_sender = Transaction(
                id=tx_id,
                user_id=sender_wallet.user_id,
                amount=-clean_amount,
                currency="USD",
                description=desc,
                type="vpa_transfer",
                status="success",
                source_vpa=vpa,
                recipient_vpa=recipient_vpa,
                created_date=now
            )
            db_tx_recipient = Transaction(
                id=str(uuid.uuid4()),  # separate tx ID for recipient history
                user_id=recipient_wallet.user_id,
                amount=clean_amount,
                currency="USD",
                description=desc,
                type="vpa_transfer",
                status="success",
                source_vpa=vpa,
                recipient_vpa=recipient_vpa,
                created_date=now
            )
            db.add(db_tx_sender)
            db.add(db_tx_recipient)
            await db.flush()

            logger.info(f"UPS PAY: ${clean_amount} transfered from '{vpa}' to '{recipient_vpa}' (DB)")
            return {
                "transaction_id": tx_id,
                "status": "success",
                "amount": clean_amount,
                "sender_vpa": vpa,
                "recipient_vpa": recipient_vpa,
                "description": desc,
                "created_at": now
            }

        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"Database error during VPA transfer: {e}. Falling back to in-memory.")
            await db.rollback()

    # In-memory fallback
    # Find wallets
    sender_wallet = None
    recipient_wallet = None

    for w in _mock_wallets.values():
        if w.get("vpa") == vpa:
            sender_wallet = w
        if w.get("vpa") == recipient_vpa:
            recipient_wallet = w

    if not sender_wallet:
        raise ValueError(f"Sender VPA '{vpa}' not found.")
    if not recipient_wallet:
        raise ValueError(f"Recipient VPA '{recipient_vpa}' not found.")
    if sender_wallet["user_id"] == recipient_wallet["user_id"]:
        raise ValueError("Self-transfers between the same VPA wallet owner are not permitted.")

    if sender_wallet["balance"] < clean_amount:
        raise ValueError(f"Insufficient funds. Balance: ${sender_wallet['balance']}")

    sender_wallet["balance"] = round(sender_wallet["balance"] - clean_amount, 2)
    recipient_wallet["balance"] = round(recipient_wallet["balance"] + clean_amount, 2)
    sender_wallet["updated_date"] = now
    recipient_wallet["updated_date"] = now

    desc = f"UPS Pay VPA P2P Transfer from {vpa} to {recipient_vpa}"
    tx_sender = {
        "id": tx_id,
        "user_id": sender_wallet["user_id"],
        "amount": -clean_amount,
        "currency": "USD",
        "description": desc,
        "type": "vpa_transfer",
        "status": "success",
        "source_vpa": vpa,
        "recipient_vpa": recipient_vpa,
        "created_date": now,
    }
    tx_recipient = {
        "id": str(uuid.uuid4()),
        "user_id": recipient_wallet["user_id"],
        "amount": clean_amount,
        "currency": "USD",
        "description": desc,
        "type": "vpa_transfer",
        "status": "success",
        "source_vpa": vpa,
        "recipient_vpa": recipient_vpa,
        "created_date": now,
    }

    _mock_transactions.append(tx_sender)
    _mock_transactions.append(tx_recipient)

    logger.info(f"UPS PAY: ${clean_amount} transfered from '{vpa}' to '{recipient_vpa}' (Memory)")
    return {
        "transaction_id": tx_id,
        "status": "success",
        "amount": clean_amount,
        "sender_vpa": vpa,
        "recipient_vpa": recipient_vpa,
        "description": desc,
        "created_at": now
    }


async def create_payment_session(
    user_id: str,
    amount: float,
    currency: str,
    description: str,
    vpa: Optional[str] = None,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Creates a temporary payment session (e.g., for purchasing premium numbers).

    Args:
        user_id (str): Purchasing user identifier.
        amount (float): Purchase price.
        currency (str): Price currency (e.g. 'USD').
        description (str): Reason/Description of purchase.
        vpa (str, optional): Target VPA associated with session. Defaults to None.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Dict containing the created session details.
    """
    session_id = f"pay_sess_{uuid.uuid4().hex}"
    clean_amount = round(float(amount), 2)
    user_id_str = str(user_id)
    now = datetime.utcnow()

    session_data = {
        "session_id": session_id,
        "user_id": user_id_str,
        "amount": clean_amount,
        "currency": currency.upper(),
        "description": description,
        "vpa": vpa,
        "status": "pending",
        "created_at": now,
        "checkout_url": f"https://pay.tu5g.online/checkout/{session_id}"
    }

    # Save payment session
    _mock_payment_sessions[session_id] = session_data

    # Optional: We can create a pending Transaction in the DB for audit trails
    if db:
        try:
            db_tx = Transaction(
                id=session_id,  # using session_id as the pending transaction ID
                user_id=user_id_str,
                amount=-clean_amount,
                currency=currency.upper(),
                description=description,
                type="payment",
                status="pending",
                source_vpa=vpa,
                recipient_vpa=None,
                created_date=now
            )
            db.add(db_tx)
            await db.flush()
            logger.info(f"Payment session '{session_id}' created and recorded as pending in DB.")
        except Exception as e:
            logger.warning(f"Failed to record pending session in database: {e}. Kept in-memory only.")
            await db.rollback()

    logger.info(f"Payment session '{session_id}' successfully created for user '{user_id_str}' of ${clean_amount}")
    return session_data


async def verify_payment(
    payment_id: str,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Verifies the status of a payment session. If the session exists and is pending,
    attempts to perform the wallet deduction automatically, validating the payment.

    Args:
        payment_id (str): Payment session ID or transaction reference.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Verification status dict.
    """
    now = datetime.utcnow()

    # Locate the session
    session = _mock_payment_sessions.get(payment_id)
    if not session:
        # Fallback to checking the database transaction directly
        if db:
            try:
                query = select(Transaction).where(Transaction.id == payment_id)
                res = await db.execute(query)
                tx = res.scalars().first()
                if tx:
                    return {
                        "payment_id": payment_id,
                        "status": tx.status,
                        "amount": float(tx.amount),
                        "currency": tx.currency,
                        "description": tx.description,
                        "verified_at": now
                    }
            except Exception as e:
                logger.error(f"Database lookup for transaction {payment_id} failed: {e}")
        
        return {
            "payment_id": payment_id,
            "status": "not_found",
            "message": "Payment session or transaction reference not found.",
            "verified_at": now
        }

    # If already processed
    if session["status"] != "pending":
        return {
            "payment_id": payment_id,
            "status": session["status"],
            "amount": session["amount"],
            "currency": session["currency"],
            "description": session["description"],
            "verified_at": now
        }

    # If pending, attempt to process automatically by debiting the user's wallet balance
    user_id = session["user_id"]
    amount = session["amount"]
    
    try:
        current_balance = await get_wallet_balance(user_id, db=db)
        if current_balance < amount:
            session["status"] = "failed"
            logger.warning(f"Payment session '{payment_id}' verification failed: Insufficient wallet balance.")
            
            if db:
                try:
                    # Update pending transaction status in DB
                    query = select(Transaction).where(Transaction.id == payment_id)
                    res = await db.execute(query)
                    tx = res.scalars().first()
                    if tx:
                        tx.status = "failed"
                        await db.flush()
                except Exception:
                    await db.rollback()

            return {
                "payment_id": payment_id,
                "status": "failed",
                "error": "Insufficient wallet balance",
                "verified_at": now
            }

        # Deduct wallet funds
        if db:
            try:
                query = select(Wallet).where(Wallet.user_id == str(user_id))
                res = await db.execute(query)
                wallet = res.scalars().first()
                if wallet:
                    wallet.balance = round(wallet.balance - amount, 2)
                    wallet.updated_date = now

                    # Update transaction status
                    query_tx = select(Transaction).where(Transaction.id == payment_id)
                    res_tx = await db.execute(query_tx)
                    tx = res_tx.scalars().first()
                    if tx:
                        tx.status = "success"
                    else:
                        db_tx = Transaction(
                            id=payment_id,
                            user_id=str(user_id),
                            amount=-amount,
                            currency=session["currency"],
                            description=session["description"],
                            type="payment",
                            status="success",
                            source_vpa=session["vpa"],
                            recipient_vpa=None,
                            created_date=now
                        )
                        db.add(db_tx)
                    await db.flush()
            except Exception as e:
                logger.warning(f"Database deduction failed: {e}. Falling back to in-memory.")
                await db.rollback()
                # Perform in-memory deduction instead
                wallet_rec = _mock_wallets[str(user_id)]
                wallet_rec["balance"] = round(wallet_rec["balance"] - amount, 2)
        else:
            wallet_rec = _mock_wallets[str(user_id)]
            wallet_rec["balance"] = round(wallet_rec["balance"] - amount, 2)

        # Update in-memory session status
        session["status"] = "success"
        
        # Record successful transaction in fallback list
        tx_item = {
            "id": payment_id,
            "user_id": str(user_id),
            "amount": -amount,
            "currency": session["currency"],
            "description": session["description"],
            "type": "payment",
            "status": "success",
            "source_vpa": session["vpa"],
            "recipient_vpa": None,
            "created_date": now,
        }
        _mock_transactions.append(tx_item)

        logger.info(f"Payment session '{payment_id}' verified and processed successfully.")
        return {
            "payment_id": payment_id,
            "status": "success",
            "amount": amount,
            "currency": session["currency"],
            "description": session["description"],
            "verified_at": now
        }

    except Exception as e:
        logger.error(f"Error verifying/processing payment session '{payment_id}': {e}")
        return {
            "payment_id": payment_id,
            "status": "error",
            "message": f"Verification error: {str(e)}",
            "verified_at": now
        }


async def get_transaction_history(
    user_id: str,
    limit: int = 50,
    db: Optional[AsyncSession] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves the transaction history for a user, sorted newest first.

    Args:
        user_id (str): User identifier.
        limit (int): Max transactions to return (default: 50).
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        List[Dict[str, Any]]: List of transactions.
    """
    user_id_str = str(user_id)
    if db:
        try:
            query = (
                select(Transaction)
                .where(Transaction.user_id == user_id_str)
                .order_by(Transaction.created_date.desc())
                .limit(limit)
            )
            result = await db.execute(query)
            txs = result.scalars().all()
            return [
                {
                    "id": item.id,
                    "user_id": item.user_id,
                    "amount": round(float(item.amount), 2),
                    "currency": item.currency,
                    "description": item.description,
                    "type": item.type,
                    "status": item.status,
                    "source_vpa": item.source_vpa,
                    "recipient_vpa": item.recipient_vpa,
                    "created_at": item.created_date
                }
                for item in txs
            ]
        except Exception as e:
            logger.warning(f"Database error reading transaction history: {e}. Using in-memory fallback.")

    # In-memory fallback
    user_txs = [t for t in _mock_transactions if t["user_id"] == user_id_str]
    # Sort by created date descending
    user_txs.sort(key=lambda x: x["created_date"], reverse=True)
    return user_txs[:limit]
