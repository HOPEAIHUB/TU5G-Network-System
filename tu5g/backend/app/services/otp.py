"""
OTP Verification Service for the TU5G platform.
Handles generation, secure storage (Redis / Memory), transmission (Email / SMS stub),
constant-time verification, and rate-limiting.
"""

import os
import random
import secrets
import time
import logging
import uuid
from typing import Dict, Tuple, List, Optional
from email.message import EmailMessage

import aiosmtplib

# Setup logger
logger = logging.getLogger(__name__)

# Fallback Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = None

try:
    import redis
    # Using a sync connection but we can wrap operations in async execution or run directly.
    # Note: For asyncio in python, redis has an async client, but for general compatibility,
    # we can use redis.Redis and handle exceptions.
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    # Ping to check if actually reachable
    redis_client.ping()
    logger.info(f"Successfully connected to Redis at {REDIS_URL}")
except Exception as e:
    logger.warning(
        f"Redis connection failed or 'redis' package not installed. "
        f"Using thread-safe in-memory fallback store. Error: {e}"
    )
    redis_client = None

# ==========================================
# In-Memory Backup Storage (Thread-Safe Simulation)
# ==========================================
# Structure: { identifier: (otp_code, expiration_timestamp) }
_otp_store: Dict[str, Tuple[str, float]] = {}

# Structure: { identifier: [request_timestamps] }
_rate_limit_store: Dict[str, List[float]] = {}


def _cleanup_expired_in_memory() -> None:
    """Helper to remove expired entries from the in-memory fallback stores."""
    now = time.time()
    
    # Cleanup expired OTP codes
    expired_otps = [k for k, v in _otp_store.items() if v[1] < now]
    for k in expired_otps:
        _otp_store.pop(k, None)
        
    # Cleanup rate limit records older than 5 minutes (300 seconds)
    for k, ts_list in list(_rate_limit_store.items()):
        valid_ts = [t for t in ts_list if t > now - 300]
        if not valid_ts:
            _rate_limit_store.pop(k, None)
        else:
            _rate_limit_store[k] = valid_ts


# ==========================================
# Core OTP Services
# ==========================================

def generate_otp(length: int = 6) -> str:
    """
    Generates a cryptographically secure random numeric OTP.

    Args:
        length (int): Length of the OTP (default: 6).

    Returns:
        str: Numeric OTP string.
    """
    if length <= 0:
        raise ValueError("OTP length must be a positive integer.")
    
    # Use secrets for cryptographic randomness
    digits = [str(secrets.randbelow(10)) for _ in range(length)]
    return "".join(digits)


async def send_otp_email(email_address: str, otp: str) -> bool:
    """
    Sends the OTP via email asynchronously using aiosmtplib.
    Loads SMTP configurations from environment variables.

    Args:
        email_address (str): Target recipient email.
        otp (str): Generated OTP to send.

    Returns:
        bool: True if email sent successfully, False otherwise.
    """
    smtp_host = os.getenv("SMTP_HOST", "localhost")
    smtp_port_str = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if not smtp_user or not smtp_password:
        logger.error("SMTP credentials (SMTP_USER, SMTP_PASSWORD) are not configured in environment.")
        return False

    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        logger.error(f"Invalid SMTP_PORT: '{smtp_port_str}'. Defaulting to 587.")
        smtp_port = 587

    # Build the EmailMessage
    message = EmailMessage()
    message["From"] = smtp_user
    message["To"] = email_address
    message["Subject"] = "Your TU5G Verification Code"
    
    body_text = (
        f"Hello,\n\n"
        f"Your verification code for TU5G platform is: {otp}\n\n"
        f"This code is valid for 5 minutes (300 seconds). "
        f"If you did not request this code, please ignore this email.\n\n"
        f"Best regards,\n"
        f"TU5G Security Team"
    )
    message.set_content(body_text)

    # Standard security detection based on port
    use_tls = smtp_port == 465
    start_tls = smtp_port == 587 or smtp_port == 25

    try:
        logger.info(f"Connecting to SMTP {smtp_host}:{smtp_port} to send OTP...")
        await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user,
            password=smtp_password,
            use_tls=use_tls,
            start_tls=start_tls,
            timeout=10,
        )
        logger.info(f"OTP successfully sent to email: {email_address}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email to {email_address} via aiosmtplib: {e}")
        return False


async def send_otp_sms(phone: str, otp: str) -> bool:
    """
    Sends the OTP via SMS. Currently a stub that logs to console.

    Args:
        phone (str): Recipient phone number (e.g. +984799000123).
        otp (str): OTP string.

    Returns:
        bool: True (simulating successful gateway request).
    """
    logger.info("==============================================")
    logger.info(f"SMS GATEWAY STUB [SEND OTP]")
    logger.info(f"To: {phone}")
    logger.info(f"Message: Your TU5G verification code is {otp}. Valid for 5 minutes.")
    logger.info("TODO: Integrate with Twilio, Infobip, or local carrier SMS API.")
    logger.info("==============================================")
    return True


def verify_otp(stored_otp: str, provided_otp: str) -> bool:
    """
    Constant-time comparison to prevent timing attacks on OTP verification.

    Args:
        stored_otp (str): The valid OTP stored in cache/database.
        provided_otp (str): The OTP provided by the user.

    Returns:
        bool: True if they match, False otherwise.
    """
    if not stored_otp or not provided_otp:
        return False
    return secrets.compare_digest(stored_otp.strip(), provided_otp.strip())


async def store_otp(identifier: str, otp: str, ttl_seconds: int = 300) -> None:
    """
    Stores an OTP for a given identifier (email or phone) with a time-to-live.
    Supports Redis and falls back to in-memory dict.

    Args:
        identifier (str): User identifier (email / phone).
        otp (str): Generated OTP code.
        ttl_seconds (int): Time-to-live in seconds (default: 300).
    """
    if redis_client:
        try:
            redis_client.set(f"otp:{identifier}", otp, ex=ttl_seconds)
            logger.debug(f"Stored OTP in Redis for '{identifier}' with TTL {ttl_seconds}s")
            return
        except Exception as e:
            logger.error(f"Redis write error: {e}. Falling back to in-memory dict.")

    # In-memory fallback
    _cleanup_expired_in_memory()
    expiry = time.time() + ttl_seconds
    _otp_store[identifier] = (otp, expiry)
    logger.debug(f"Stored OTP in memory fallback for '{identifier}' with TTL {ttl_seconds}s")


async def get_stored_otp(identifier: str) -> Optional[str]:
    """
    Retrieves the stored OTP for an identifier.
    Supports Redis and falls back to in-memory dict.

    Args:
        identifier (str): User identifier (email / phone).

    Returns:
        Optional[str]: Stored OTP if exists and is not expired, else None.
    """
    if redis_client:
        try:
            val = redis_client.get(f"otp:{identifier}")
            return val
        except Exception as e:
            logger.error(f"Redis read error: {e}. Falling back to in-memory dict.")

    # In-memory fallback
    _cleanup_expired_in_memory()
    val = _otp_store.get(identifier)
    if val:
        otp_code, expiry = val
        if expiry > time.time():
            return otp_code
        else:
            _otp_store.pop(identifier, None)  # Clean expired on-the-fly
    return None


async def invalidate_otp(identifier: str) -> None:
    """
    Deletes the OTP for an identifier (e.g. after successful verification).

    Args:
        identifier (str): User identifier.
    """
    if redis_client:
        try:
            redis_client.delete(f"otp:{identifier}")
            logger.debug(f"Invalidated OTP in Redis for '{identifier}'")
            return
        except Exception as e:
            logger.error(f"Redis delete error: {e}. Falling back to in-memory dict.")

    # In-memory fallback
    _otp_store.pop(identifier, None)
    logger.debug(f"Invalidated OTP in memory fallback for '{identifier}'")


async def check_and_increment_rate_limit(identifier: str) -> bool:
    """
    Rate limiter: Checks if the identifier has exceeded the limit of 
    max 3 OTP requests in 5 minutes. If within limit, records the request.

    Args:
        identifier (str): User identifier (email / phone).

    Returns:
        bool: True if request is allowed, False if rate-limited.
    """
    now = time.time()
    five_min_ago = now - 300

    if redis_client:
        try:
            key = f"rate_limit:{identifier}"
            pipe = redis_client.pipeline()
            # Remove any elements older than 5 minutes
            pipe.zremrangebyscore(key, 0, five_min_ago)
            # Count elements remaining
            pipe.zcard(key)
            results = pipe.execute()
            current_requests = results[1]

            if current_requests >= 3:
                logger.warning(f"Rate limit exceeded for OTP request on identifier '{identifier}' (Redis)")
                return False

            # Add new request and set key expiry to 5 minutes
            # Using combination of current time and UUID to ensure uniqueness of member
            member = f"{now}:{uuid.uuid4()}"
            pipe = redis_client.pipeline()
            pipe.zadd(key, {member: now})
            pipe.expire(key, 300)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Redis rate limiting error: {e}. Falling back to in-memory rate limiting.")

    # In-memory fallback rate limiting
    _cleanup_expired_in_memory()
    ts_list = _rate_limit_store.get(identifier, [])
    # Filter list for timestamps in the last 5 minutes
    ts_list = [t for t in ts_list if t > five_min_ago]

    if len(ts_list) >= 3:
        logger.warning(f"Rate limit exceeded for OTP request on identifier '{identifier}' (Memory)")
        return False

    ts_list.append(now)
    _rate_limit_store[identifier] = ts_list
    return True
