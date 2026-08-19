import hashlib
import hmac
import json
import logging
import time
import secrets
import functools
import httpx
from typing import Optional, Dict, Any, Callable
from fastapi import HTTPException, Request, Depends, status
from jose import jwt, JWTError

from src.config import settings
from src.redis_client import redis_client
from src.vault_client import vault_client

logger = logging.getLogger("hag.security")


# ==========================================
# 1. Audit Logging to Immutable Ledger
# ==========================================
class ImmutableAuditLedger:

    def __init__(self):
        self._chain: list[dict] = []
        self._genesis_block()

    def _genesis_block(self):
        genesis = {
            "index": 0,
            "timestamp": time.time(),
            "event": "GENESIS",
            "data": {"message": "HAABS Immutable Audit Ledger Initialized"},
            "prev_hash": "0" * 64,
        }
        genesis["hash"] = self._compute_hash(genesis)
        self._chain.append(genesis)

    def _compute_hash(self, block: dict) -> str:
        block_string = json.dumps(
            {
                "index": block["index"],
                "timestamp": block["timestamp"],
                "event": block["event"],
                "data": block["data"],
                "prev_hash": block["prev_hash"],
            },
            sort_keys=True,
        )
        return hashlib.sha256(block_string.encode("utf-8")).hexdigest()

    def log_event(self, event: str, data: dict[str, Any]) -> dict:
        prev_block = self._chain[-1]
        new_block = {
            "index": len(self._chain),
            "timestamp": time.time(),
            "event": event,
            "data": data,
            "prev_hash": prev_block["hash"],
        }
        new_block["hash"] = self._compute_hash(new_block)
        self._chain.append(new_block)
        logger.info("Audit Ledger Block #%d created [%s]: %s", new_block["index"], event, new_block["hash"])
        return new_block

    def verify_integrity(self) -> bool:
        for i in range(1, len(self._chain)):
            curr = self._chain[i]
            prev = self._chain[i - 1]
            if curr["prev_hash"] != prev["hash"]:
                logger.error("Audit ledger broken link at block %d", i)
                return False
            if curr["hash"] != self._compute_hash(curr):
                logger.error("Audit ledger hash mismatch at block %d", i)
                return False
        return True

    def get_logs(self, limit: int = 50) -> list[dict]:
        return self._chain[-limit:]


audit_ledger = ImmutableAuditLedger()


# ==========================================
# 2. Rate Limiting Decorator & Helper
# ==========================================
async def enforce_rate_limit(
    identifier: str, limit: int = 5, window_seconds: int = 3600
):
    """Enforce rate limit (default 5 requests/hour per identifier)."""
    rate_key = f"rate:{identifier}"
    allowed, count = await redis_client.check_rate_limit(
        rate_key, limit=limit, window=window_seconds
    )
    if not allowed:
        audit_ledger.log_event(
            "RATE_LIMIT_EXCEEDED",
            {"identifier": identifier, "limit": limit, "count": count},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {limit} requests per hour.",
        )
    return count


def rate_limited(limit: int = 5, window_seconds: int = 3600, key_param: str = "phone"):
    """Decorator to rate limit functions by phone parameter or identifier."""

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            identifier = kwargs.get(key_param)
            if not identifier and args:
                # Inspect positional args or dict
                if isinstance(args[0], str):
                    identifier = args[0]
                elif hasattr(args[0], key_param):
                    identifier = getattr(args[0], key_param)
                elif isinstance(args[0], dict) and key_param in args[0]:
                    identifier = args[0][key_param]

            if not identifier:
                identifier = "default_anon"

            await enforce_rate_limit(identifier, limit=limit, window_seconds=window_seconds)
            return await func(*args, **kwargs)

        return wrapper

    return decorator


# ==========================================
# 3. IP Reputation Check via Cloudflare API
# ==========================================
async def check_ip_reputation(client_ip: str) -> dict[str, Any]:
    """Check IP reputation using Cloudflare API if CLOUD_FLARE_API is configured."""
    api_token = settings.CLOUD_FLARE_API
    if not api_token:
        logger.debug("Cloudflare API token not configured. IP reputation skipped.")
        return {"allowed": True, "score": 0, "reason": "Cloudflare API token not configured"}

    # Cloudflare IP threat score / intel query
    try:
        url = f"https://api.cloudflare.com/client/v4/ips?ip={client_ip}"
        headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("result", {})
                threat_score = result.get("threat_score", 0)
                if threat_score > 50:
                    audit_ledger.log_event("HIGH_RISK_IP_BLOCKED", {"ip": client_ip, "threat_score": threat_score})
                    return {"allowed": False, "score": threat_score, "reason": "High risk threat score"}
                return {"allowed": True, "score": threat_score, "reason": "Clean IP reputation"}
    except Exception as e:
        logger.warning("Cloudflare IP reputation check failed: %s", e)

    return {"allowed": True, "score": 0, "reason": "Reputation service default pass"}


# ==========================================
# 4. Nonce Generation and Validation
# ==========================================
def generate_nonce() -> str:
    """Generate cryptographically secure one-time nonce."""
    prefix = hex(int(time.time()))[2:]
    random_part = secrets.token_hex(16)
    return f"{prefix}-{random_part}"


async def validate_and_consume_nonce(nonce: str, ttl: int = 300) -> bool:
    """Validate and consume a one-time nonce. Returns True if valid & unused."""
    if not nonce or len(nonce) < 10:
        return False
    # Check if nonce is already stored/used
    consumed = await redis_client.consume_nonce(nonce)
    if consumed:
        return False  # Already used!
    
    # Store nonce so subsequent attempts fail
    await redis_client.store_nonce(nonce, ttl=ttl)
    audit_ledger.log_event("NONCE_VALIDATED", {"nonce": nonce})
    return True


# ==========================================
# 5. JWT Verification Helper
# ==========================================
def verify_jwt_token(token: str) -> dict[str, Any]:
    """Verify JWT token using active public key from Vault/settings."""
    public_key = vault_client.get_public_key()
    try:
        # Try decoding with RS256 using public key
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[settings.JWT_ALGORITHM, "RS256", "HS256"],
            options={"verify_aud": False},
        )
        return payload
    except JWTError as e:
        # Fallback check if symmetric or direct key
        if settings.JWT_PRIVATE_KEY:
            try:
                payload = jwt.decode(
                    token,
                    settings.JWT_PRIVATE_KEY,
                    algorithms=["HS256"],
                    options={"verify_aud": False},
                )
                return payload
            except JWTError:
                pass
        audit_ledger.log_event("JWT_VERIFICATION_FAILED", {"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired JWT token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ==========================================
# 6. Request Signing & Verification
# ==========================================
def sign_request(payload: str | bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for request payload."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_request_signature(
    payload: str | bytes,
    signature: str,
    secret: str,
    timestamp: Optional[str] = None,
    max_age_seconds: int = 300,
) -> bool:
    """Verify request HMAC signature and check timestamp for replay attack prevention."""
    if timestamp:
        try:
            ts = float(timestamp)
            if abs(time.time() - ts) > max_age_seconds:
                audit_ledger.log_event("SIGNATURE_REPLAY_ATTEMPT", {"timestamp": timestamp})
                return False
        except ValueError:
            return False

    expected_sig = sign_request(payload, secret)
    valid = hmac.compare_digest(expected_sig, signature)
    if not valid:
        audit_ledger.log_event("INVALID_SIGNATURE", {"received_sig": signature})
    return valid
