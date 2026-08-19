"""
E-SIM Number Selection & Provisioning Store Service for the TU5G platform.
Handles available phone number listing and categorization, reservations, e-SIM provisioning
including standard LPA-format QR code generation, activation, suspension, plan management,
and free premium eligibility evaluation under the TU5G AI governance rules.
Supports dual-mode database storage (SQLAlchemy AsyncSession) and in-memory fallback.
"""

import time
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import Customer
from app.services.sim import generate_iccid, COUNTRY_CODE, SIM_RANGE_START, SIM_RANGE_END

logger = logging.getLogger(__name__)

# ==========================================
# In-Memory Fallback Databases
# ==========================================
# Mock Customer DB. Key is customer_id as integer or string
_mock_customer_db: Dict[str, Dict[str, Any]] = {}

# Active number reservations: { number: (user_id, expiration_timestamp) }
_reservations: Dict[str, tuple] = {}

# Free premium application records: { app_id: application_dict }
_free_premium_applications: Dict[str, Dict[str, Any]] = {}


# ==========================================
# Deterministic Number Categorizer and Generator
# ==========================================

def categorize_number(number: str) -> str:
    """
    Categorizes a phone number based on its digit patterns.
    - 'vanity': ends with 3 or more repeating digits, or 777/000.
    - 'premium': ends with 2 repeating digits, or contains simple sequential patterns like '123' or '799' at the end.
    - 'free': random assortment of digits.

    Args:
        number (str): The phone number (e.g. +984799000123).

    Returns:
        str: 'free', 'premium', or 'vanity'.
    """
    clean_num = number.replace(COUNTRY_CODE, "")
    last_four = clean_num[-4:]
    last_three = clean_num[-3:]
    last_two = clean_num[-2:]

    # Vanity checks
    if len(set(last_three)) == 1 or last_three in ("000", "777", "999") or len(set(last_four)) == 1:
        return "vanity"
    # Premium checks
    elif len(set(last_two)) == 1 or "123" in clean_num or last_three == "799" or last_four.startswith("79"):
        return "premium"
    # Free
    return "free"


def get_number_price(number: str) -> float:
    """
    Returns the price of the number based on its category in USD.
    - free: $0.00
    - premium: $100.00
    - vanity: $500.00

    Args:
        number (str): The phone number.

    Returns:
        float: Price in USD.
    """
    category = categorize_number(number)
    if category == "premium":
        return 100.00
    elif category == "vanity":
        return 500.00
    return 0.00


def _generate_deterministic_store_numbers() -> List[str]:
    """
    Generates a deterministic pool of available numbers in the +984 799 range
    to simulate a live inventory pool without bloating memory.
    
    Returns:
        List[str]: A stable pool of ~300 well-formed phone numbers.
    """
    pool = []
    # Use a fixed stride to generate various patterns across the range
    for offset in range(12000, 999999, 3137):
        num_str = f"{COUNTRY_CODE}{SIM_RANGE_START + offset}"
        pool.append(num_str)
    return pool


# ==========================================
# Core eSIM Store Services
# ==========================================

def list_available_numbers(
    category: Optional[str] = None,
    page: int = 1,
    per_page: int = 20
) -> Dict[str, Any]:
    """
    Provides a paginated list of available phone numbers in the store,
    optionally filtered by category ('free', 'premium', 'vanity').

    Args:
        category (str, optional): Category filter. Defaults to None.
        page (int): Page index starting at 1. Defaults to 1.
        per_page (int): Page size. Defaults to 20.

    Returns:
        Dict[str, Any]: Paginated payload with list of numbers, total count, pages.
    """
    raw_pool = _generate_deterministic_store_numbers()
    now = time.time()
    
    # Filter out numbers that have active, unexpired reservations
    available_pool = []
    for num in raw_pool:
        is_reserved = False
        if num in _reservations:
            res_user, expiry = _reservations[num]
            if expiry > now:
                is_reserved = True
            else:
                _reservations.pop(num, None)  # expired reservation cleanup
        
        if not is_reserved:
            available_pool.append(num)

    # Filter by category if requested
    if category:
        target_cat = category.strip().lower()
        filtered_pool = [n for num in available_pool if (n := {"number": num, "category": categorize_number(num), "price": get_number_price(num)})["category"] == target_cat]
    else:
        filtered_pool = [{"number": num, "category": categorize_number(num), "price": get_number_price(num)} for num in available_pool]

    # Calculate pagination boundaries
    total_count = len(filtered_pool)
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_items = filtered_pool[start_idx:end_idx]

    return {
        "numbers": paginated_items,
        "total_count": total_count,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages
    }


def reserve_number(number: str, user_id: str, ttl_seconds: int = 600) -> bool:
    """
    Places a temporary hold/reservation on a phone number.
    Ensures that other users cannot purchase/provision it within the reservation window.

    Args:
        number (str): Phone number to reserve.
        user_id (str): ID of the reserving user.
        ttl_seconds (int): Reservation lifetime in seconds. Defaults to 600 (10 mins).

    Returns:
        bool: True if reservation succeeded, False if already reserved by someone else.
    """
    now = time.time()
    user_id_str = str(user_id)

    # Check existing reservations
    if number in _reservations:
        res_user, expiry = _reservations[number]
        if expiry > now and res_user != user_id_str:
            logger.warning(f"Number '{number}' is already reserved by user '{res_user}' until {expiry}")
            return False

    # Create/Renew reservation
    expiration = now + ttl_seconds
    _reservations[number] = (user_id_str, expiration)
    logger.info(f"Number '{number}' reserved for user '{user_id_str}' for {ttl_seconds} seconds.")
    return True


async def provision_esim(
    user_id: str,
    number: str,
    plan: str = "free_3months",
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Simulates a full e-SIM provisioning flow.
    Generates a unique ICCID, creates an e-SIM telecom profile, creates
    QR activation code in standard LPA format, and saves the customer profile.

    LPA (Local Profile Assistant) format: LPA:1$SM-DP+ Address$Activation Code

    Args:
        user_id (str): Owning customer user identifier.
        number (str): The chosen e-SIM phone number (MSISDN).
        plan (str): Telecom plan name (e.g. 'free_3months', 'premium_10gb').
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Detailed e-SIM profile data.
    """
    user_id_str = str(user_id)
    iccid = generate_iccid()
    now = datetime.utcnow()

    # Generate standard LPA QR Activation payload
    smdpp_address = "rsp.tu5g.online"
    activation_token = f"LS-PROV-{uuid.uuid4().hex[:12].upper()}"
    lpa_qr_data = f"LPA:1${smdpp_address}${activation_token}"

    sim_profile_data = {
        "iccid": iccid,
        "phone_number": number,
        "sim_number": number,
        "country_code": COUNTRY_CODE,
        "status": "inactive",  # initial status till activated
        "data_plan": plan,
        "lpa_activation_code": lpa_qr_data,
        "smdpp_address": smdpp_address,
        "pin1": "1111",
        "puk": "12345678",
        "provisioned_at": now
    }

    if db:
        try:
            # Check if this number is already active
            query = select(Customer).where(Customer.sim_number == number)
            res = await db.execute(query)
            existing = res.scalars().first()
            if existing:
                raise ValueError(f"Phone number '{number}' is already provisioned to an active subscription.")

            # Create SQLAlchemy Customer profile
            db_customer = Customer(
                sim_number=number,
                iccid=iccid,
                country_code=COUNTRY_CODE,
                status="inactive",
                data_plan=plan,
                phone_number=number,
                created_date=now,
                updated_date=now
            )
            db.add(db_customer)
            await db.flush()

            # Release hold reservation if held
            _reservations.pop(number, None)

            logger.info(f"E-SIM '{number}' successfully provisioned in DB for user '{user_id_str}'")
            return {
                "customer_id": db_customer.id,
                **sim_profile_data
            }
        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"Database error during eSIM provisioning: {e}. Falling back to in-memory.")
            await db.rollback()

    # In-memory fallback
    # Verify number uniqueness in memory
    for c in _mock_customer_db.values():
        if c.get("sim_number") == number:
            raise ValueError(f"Phone number '{number}' is already provisioned in memory.")

    customer_id = str(uuid.uuid4().int)[:6]  # numeric looking id
    customer_record = {
        "id": customer_id,
        "user_id": user_id_str,
        "sim_number": number,
        "iccid": iccid,
        "country_code": COUNTRY_CODE,
        "status": "inactive",
        "data_plan": plan,
        "phone_number": number,
        "lpa_activation_code": lpa_qr_data,
        "smdpp_address": smdpp_address,
        "pin1": "1111",
        "puk": "12345678",
        "created_date": now,
        "updated_date": now
    }
    _mock_customer_db[customer_id] = customer_record
    
    # Release hold
    _reservations.pop(number, None)

    logger.info(f"E-SIM '{number}' successfully provisioned in memory for user '{user_id_str}'")
    return {
        "customer_id": customer_id,
        **sim_profile_data
    }


async def activate_esim(customer_id: str, db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """
    Activates a provisioned e-SIM subscription.

    Args:
        customer_id (str): Customer / subscription ID.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Updated eSIM status and profile.
    """
    now = datetime.utcnow()
    
    if db:
        try:
            # Query the customer (Integer key in DB or try casting)
            try:
                cust_id_val = int(customer_id)
            except ValueError:
                cust_id_val = -1

            query = select(Customer).where(Customer.id == cust_id_val)
            res = await db.execute(query)
            db_customer = res.scalars().first()

            if db_customer:
                db_customer.status = "active"
                db_customer.updated_date = now
                await db.flush()
                logger.info(f"E-SIM customer ID '{customer_id}' activated in DB.")
                return {
                    "customer_id": db_customer.id,
                    "sim_number": db_customer.sim_number,
                    "iccid": db_customer.iccid,
                    "status": "active",
                    "data_plan": db_customer.data_plan,
                    "updated_at": now
                }
        except Exception as e:
            logger.warning(f"Database error activating eSIM: {e}. Falling back to in-memory.")
            await db.rollback()

    # In-memory fallback
    cust_id_str = str(customer_id)
    if cust_id_str not in _mock_customer_db:
        raise ValueError(f"Subscription profile with ID '{customer_id}' not found.")

    record = _mock_customer_db[cust_id_str]
    record["status"] = "active"
    record["updated_date"] = now
    
    logger.info(f"E-SIM customer ID '{customer_id}' activated in memory.")
    return {
        "customer_id": customer_id,
        "sim_number": record["sim_number"],
        "iccid": record["iccid"],
        "status": "active",
        "data_plan": record["data_plan"],
        "updated_at": now
    }


async def suspend_esim(customer_id: str, db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """
    Temporarily suspends an active e-SIM line.

    Args:
        customer_id (str): Customer / subscription ID.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Updated eSIM status.
    """
    now = datetime.utcnow()
    
    if db:
        try:
            try:
                cust_id_val = int(customer_id)
            except ValueError:
                cust_id_val = -1

            query = select(Customer).where(Customer.id == cust_id_val)
            res = await db.execute(query)
            db_customer = res.scalars().first()

            if db_customer:
                db_customer.status = "suspended"
                db_customer.updated_date = now
                await db.flush()
                logger.info(f"E-SIM customer ID '{customer_id}' suspended in DB.")
                return {
                    "customer_id": db_customer.id,
                    "sim_number": db_customer.sim_number,
                    "status": "suspended",
                    "updated_at": now
                }
        except Exception as e:
            logger.warning(f"Database error suspending eSIM: {e}. Falling back to in-memory.")
            await db.rollback()

    # In-memory fallback
    cust_id_str = str(customer_id)
    if cust_id_str not in _mock_customer_db:
        raise ValueError(f"Subscription profile with ID '{customer_id}' not found.")

    record = _mock_customer_db[cust_id_str]
    record["status"] = "suspended"
    record["updated_date"] = now
    
    logger.info(f"E-SIM customer ID '{customer_id}' suspended in memory.")
    return {
        "customer_id": customer_id,
        "sim_number": record["sim_number"],
        "status": "suspended",
        "updated_at": now
    }


async def get_esim_status(customer_id: str, db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """
    Fetches the details and network status of an eSIM.

    Args:
        customer_id (str): Customer / subscription ID.
        db (AsyncSession, optional): SQLAlchemy async session.

    Returns:
        Dict[str, Any]: Status payload.
    """
    if db:
        try:
            try:
                cust_id_val = int(customer_id)
            except ValueError:
                cust_id_val = -1

            query = select(Customer).where(Customer.id == cust_id_val)
            res = await db.execute(query)
            db_customer = res.scalars().first()

            if db_customer:
                return {
                    "customer_id": db_customer.id,
                    "sim_number": db_customer.sim_number,
                    "iccid": db_customer.iccid,
                    "country_code": db_customer.country_code,
                    "status": db_customer.status,
                    "data_plan": db_customer.data_plan,
                    "data_remaining_gb": 4.12 if "free" in db_customer.data_plan else 8.54, # Mock remaining
                    "updated_at": db_customer.updated_date
                }
        except Exception as e:
            logger.warning(f"Database error getting eSIM status: {e}. Falling back to in-memory.")

    # In-memory fallback
    cust_id_str = str(customer_id)
    if cust_id_str not in _mock_customer_db:
        raise ValueError(f"Subscription profile with ID '{customer_id}' not found.")

    record = _mock_customer_db[cust_id_str]
    return {
        "customer_id": customer_id,
        "sim_number": record["sim_number"],
        "iccid": record["iccid"],
        "country_code": record["country_code"],
        "status": record["status"],
        "data_plan": record["data_plan"],
        "data_remaining_gb": 4.12 if "free" in record["data_plan"] else 8.54,
        "updated_at": record["updated_date"]
    }


def get_plans() -> List[Dict[str, Any]]:
    """
    Retrieves list of available cellular data plans.

    Returns:
        List[Dict[str, Any]]: Available plans and descriptions.
    """
    return [
        {
            "plan_id": "free_3months",
            "name": "Free Starter Plan",
            "description": "3 months, 5GB high-speed data/month. No setup cost.",
            "data_limit_gb": 5.0,
            "validity_months": 3,
            "price_usd": 0.00
        },
        {
            "plan_id": "premium_10gb",
            "name": "Premium Plan",
            "description": "10GB high-speed data/month with roll-over.",
            "data_limit_gb": 10.0,
            "validity_months": 1,
            "price_usd": 9.99
        },
        {
            "plan_id": "ultra_unlimited",
            "name": "Ultra Unlimited",
            "description": "Unlimited cellular data without throttling.",
            "data_limit_gb": -1.0,  # Unlimited
            "validity_months": 1,
            "price_usd": 29.99
        },
        {
            "plan_id": "business_100gb",
            "name": "Business Pro Plan",
            "description": "100GB corporate data pool, multi-SIM sharing enabled.",
            "data_limit_gb": 100.0,
            "validity_months": 1,
            "price_usd": 49.99
        }
    ]


# ==========================================
# AI Governance & Free Premium Program Services
# ==========================================

def check_eligibility_free_premium(user_id: str) -> Dict[str, Any]:
    """
    Evaluates a user's eligibility for receiving a free Premium/Vanity number under
    the TU5G digital sovereignty AI governance rules.
    Covers community developers, students, researchers, charities, and religious orgs.

    Args:
        user_id (str): User identifier.

    Returns:
        Dict[str, Any]: Eligibility evaluation report.
    """
    user_id_str = str(user_id)
    
    # Evaluate previously approved/pending applications
    previous_app = None
    for app in _free_premium_applications.values():
        if app["user_id"] == user_id_str:
            previous_app = app
            break

    if previous_app:
        return {
            "user_id": user_id_str,
            "eligible": False,
            "status": "already_applied",
            "reason": f"An application is already registered (Status: {previous_app['status']}).",
            "allowed_categories": [],
            "governance_rule_reference": "TU5G-SOV-2026-RULE4"
        }

    # Standard eligibility rules
    # Users are pre-eligible and can apply. This method provides the available categories and conditions.
    return {
        "user_id": user_id_str,
        "eligible": True,
        "status": "ready",
        "reason": "Qualified for Digital Sovereignty Premium Program. Verification documents required upon application.",
        "allowed_categories": [
            "community_developer",
            "student",
            "charity",
            "religious_org",
            "academic_research"
        ],
        "governance_rule_reference": "TU5G-SOV-2026-RULE1"
    }


def apply_free_premium(user_id: str, category: str, reason: str) -> Dict[str, Any]:
    """
    Submits an application for a free premium cellular number.
    Uses community support evaluation. Auto-approves clear benevolent categories
    (e.g., charity, community_developer) with structured AI-governance commentary.

    Args:
        user_id (str): User identifier.
        category (str): Allowed category (e.g. 'student', 'charity').
        reason (str): Benevolence justification statement.

    Returns:
        Dict[str, Any]: Created application details.
    """
    user_id_str = str(user_id)
    category_clean = category.strip().lower()

    valid_categories = ["community_developer", "student", "charity", "religious_org", "academic_research"]
    if category_clean not in valid_categories:
        raise ValueError(f"Invalid category. Must be one of: {', '.join(valid_categories)}")

    if not reason or len(reason.strip()) < 15:
        raise ValueError("Please provide a substantial justification reason (minimum 15 characters).")

    app_id = f"fp_app_{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow()

    # Rule engine evaluation for automatic approval
    auto_approve = False
    governance_comment = ""
    
    if category_clean in ("charity", "community_developer"):
        auto_approve = True
        governance_comment = (
            f"AI Governance Engine: Automatically approved under code TU5G-SOV-2026-RULE2. "
            f"Developer/Charity applications are pre-cleared to foster rapid ecosystem growth."
        )
    else:
        governance_comment = (
            f"AI Governance Engine: Submitted for standard peer review. Under standard student/academic "
            f"governance clauses, proof of enrollment or researcher credentials will be reviewed within 24 hours."
        )

    app_record = {
        "application_id": app_id,
        "user_id": user_id_str,
        "category": category_clean,
        "justification": reason,
        "status": "approved" if auto_approve else "pending",
        "governance_comment": governance_comment,
        "submitted_at": now,
        "reviewed_at": now if auto_approve else None
    }

    # Store application
    _free_premium_applications[app_id] = app_record
    
    logger.info(f"Free premium number application '{app_id}' submitted for user '{user_id_str}' (Status: {app_record['status']})")
    return app_record
