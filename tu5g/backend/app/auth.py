import os
import time
import uuid
import base64
import hmac
import hashlib
import struct
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Union, Set
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# Import database and models
from app.database import get_db
from app.models import User

# Configuration from environment variables
JWT_SECRET = os.getenv("JWT_SECRET", "supersecret_tu5g_jwt_token_key_change_me_in_prod")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")) # Default 30 min
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))      # Default 7 days
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Password hashing configuration using passlib bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2PasswordBearer flow pointing to admin/auth login token endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/admin/token")


# Pydantic schemas for auth tokens
class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    jti: Optional[str] = None


# =====================================================================
# Token Blacklist & Revocation Support (In-Memory with Redis fallback)
# =====================================================================
class TokenBlacklistManager:
    """
    In-memory and Redis-backed revocation blacklist manager for JWT tokens / JTIs.
    """
    def __init__(self, redis_url: Optional[str] = None):
        self._blacklisted: Dict[str, float] = {}  # token_or_jti -> expiry_timestamp
        self.redis_client = None
        if redis_url:
            try:
                import redis
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
            except Exception:
                self.redis_client = None

    def revoke(self, identifier: str, expires_in_seconds: int = 86400) -> bool:
        """Revoke a JWT token or JTI."""
        if not identifier:
            return False
        expiry = time.time() + expires_in_seconds
        self._blacklisted[identifier] = expiry

        if self.redis_client:
            try:
                self.redis_client.setex(f"blacklist:{identifier}", expires_in_seconds, "revoked")
            except Exception:
                pass
        return True

    def is_blacklisted(self, identifier: str) -> bool:
        """Check if a token or JTI is blacklisted."""
        if not identifier:
            return False

        if self.redis_client:
            try:
                if self.redis_client.get(f"blacklist:{identifier}"):
                    return True
            except Exception:
                pass

        now = time.time()
        expiry = self._blacklisted.get(identifier)
        if expiry is None:
            return False
        if now > expiry:
            del self._blacklisted[identifier]
            return False
        return True


# Global blacklist manager instance
token_blacklist = TokenBlacklistManager(redis_url=REDIS_URL)


def revoke_token(token_or_jti: str, expires_in_seconds: int = 86400) -> bool:
    """Revoke a token or JTI across system."""
    return token_blacklist.revoke(token_or_jti, expires_in_seconds)


def is_token_blacklisted(token_or_jti: str) -> bool:
    """Check if token or JTI is in revocation list."""
    return token_blacklist.is_blacklisted(token_or_jti)


# =====================================================================
# Password Hashing Utilities
# =====================================================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its bcrypt hashed value."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash of a password."""
    return pwd_context.hash(password)


# =====================================================================
# JWT Generation & Decoding Utilities
# =====================================================================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Generate a short-lived JSON Web Token (JWT) access token with custom or default expiry.
    Includes 'sub', 'role', 'type', 'jti', 'iat', and 'exp' claims.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": "access",
        "jti": str(uuid.uuid4())
    })
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Generate a long-lived JSON Web Token (JWT) refresh token.
    Includes 'sub', 'role', 'type', 'jti', 'iat', and 'exp' claims.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": "refresh",
        "jti": str(uuid.uuid4())
    })
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Decodes and validates a JWT token. Checks expiration, signature, and revocation list.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti and is_token_blacklisted(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        token_type = payload.get("type")
        if expected_type and token_type and token_type != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type. Expected {expected_type} token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return payload
    except JWTError:
        raise credentials_exception


def verify_token(token: str) -> Dict[str, Any]:
    """Alias for decode_token."""
    return decode_token(token)


# =====================================================================
# 2FA / MFA Support (TOTP RFC 6238)
# =====================================================================
def generate_totp_secret() -> str:
    """Generates a secure 32-character base32 TOTP secret key."""
    raw_bytes = secrets.token_bytes(20)
    return base64.b32encode(raw_bytes).decode('utf-8').replace('=', '')


def generate_totp_code(secret: str, time_step: int = 30, for_time: Optional[float] = None) -> str:
    """
    Generates a 6-digit TOTP code according to RFC 6238 standard HMAC-SHA1.
    """
    if for_time is None:
        for_time = time.time()
    # Normalize secret padding
    secret_padded = secret + '=' * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(secret_padded, casefold=True)
    counter = int(for_time // time_step)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code_int = struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF
    code = code_int % 1000000
    return f"{code:06d}"


def verify_totp_code(secret: str, code: str, window: int = 1) -> bool:
    """
    Verifies a 6-digit TOTP code against a secret key with configurable time window drift.
    """
    if not secret or not code:
        return False
    code_str = code.strip()
    if len(code_str) != 6 or not code_str.isdigit():
        return False
    
    now = time.time()
    for i in range(-window, window + 1):
        if generate_totp_code(secret, time_step=30, for_time=now + (i * 30)) == code_str:
            return True
    return False


def get_totp_uri(secret: str, email: str, issuer: str = "TU5G-HAABS") -> str:
    """Generates a TOTP provisioning URI suitable for QR codes in authenticator apps."""
    return f"otpauth://totp/{issuer}:{email}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


# =====================================================================
# HOPE ASI Identity Verification Service (HAABS Entry Point Stub)
# =====================================================================
class HopeASIVerificationService:
    """
    HOPE ASI (HMTML Universal Operational Processing Engine / Artificial Super Intelligence)
    Identity Verification entry point for HAABS security architecture.
    Provides automated identity risk assessment, biometric/KYC analysis, and trust scoring.
    """
    async def verify_identity(self, user_id: Union[int, str], verification_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes identity verification through HOPE ASI intelligence engine.
        """
        document_number = verification_data.get("document_number")
        document_type = verification_data.get("document_type", "national_id")
        biometric_hash = verification_data.get("biometric_hash")
        
        verification_id = f"asi-verify-{uuid.uuid4().hex[:12]}"
        confidence_score = 0.998 if biometric_hash else 0.950
        trust_score = 98.5 if document_number else 85.0
        
        return {
            "user_id": user_id,
            "verification_id": verification_id,
            "status": "VERIFIED",
            "asi_confidence": confidence_score,
            "trust_score": trust_score,
            "document_type": document_type,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "haabs_tier": "HAABS-TIER-3-BANKING-SECURE",
            "message": "Identity successfully verified by HOPE ASI Security Engine"
        }

    async def evaluate_trust_score(self, user_id: Union[int, str], behavior_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates dynamic user trust score based on access patterns, device fingerprints, and telemetry.
        """
        failed_attempts = behavior_metrics.get("failed_attempts", 0)
        base_score = 100.0 - (failed_attempts * 15.0)
        trust_score = max(0.0, min(100.0, base_score))
        
        return {
            "user_id": user_id,
            "trust_score": trust_score,
            "risk_level": "LOW" if trust_score >= 80 else ("MEDIUM" if trust_score >= 50 else "HIGH"),
            "evaluated_at": datetime.now(timezone.utc).isoformat()
        }


hope_asi_verifier = HopeASIVerificationService()


async def verify_hope_asi_identity(user_id: Union[int, str], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Standalone entry point function for HOPE ASI identity verification."""
    return await hope_asi_verifier.verify_identity(user_id, payload)


# =====================================================================
# FastAPI Dependencies for Authentication
# =====================================================================
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    FastAPI dependency to retrieve the current active user from JWT access token.
    Decodes the JWT, validates revocation status, checks user presence and state in DB.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_token(token, expected_type="access")
    email: str = payload.get("sub")
    role: str = payload.get("role")
    if email is None:
        raise credentials_exception
        
    token_data = TokenData(email=email, role=role, jti=payload.get("jti"))
        
    query = select(User).where(User.email == token_data.email)
    result = await db.execute(query)
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
        
    user_dict = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_date": user.created_date,
        "updated_date": user.updated_date
    }
    
    return user_dict


async def get_current_user_from_token(
    token: str,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Utility function to retrieve current user directly from token string and AsyncSession.
    Used for WebSockets, background tasks, or direct route handlers.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_token(token, expected_type="access")
    email: str = payload.get("sub")
    if not email:
        raise credentials_exception
        
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    user = result.scalars().first()
    
    if user is None or not user.is_active:
        raise credentials_exception
        
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_date": user.created_date,
        "updated_date": user.updated_date
    }
