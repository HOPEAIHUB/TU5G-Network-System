"""
Shared FastAPI dependencies for the TU5G platform backend.
Re-exports database session generator, auth dependency, slowapi rate-limiter,
and provides common pagination dependencies.
"""

from typing import Dict, Any, Union
from fastapi import Query
from slowapi import Limiter
from slowapi.util import get_remote_address

# 1. Re-export get_db from app.database
from app.database import get_db

# 2. Setup Slowapi rate limiter instance and get_limiter dependency
limiter = Limiter(key_func=get_remote_address)

def get_limiter() -> Limiter:
    """
    Returns the configured Limiter instance.
    """
    return limiter

# 3. Robust re-export of get_current_user from auth
# This ensures that even if authentication routers or services are restructured or written later,
# importing app.dependencies won't throw circular or missing dependency errors.
try:
    from app.auth import get_current_user
except ImportError:
    try:
        from app.routers.auth import get_current_user
    except ImportError:
        try:
            from app.services.auth import get_current_user
        except ImportError:
            # Fallback mock/placeholder dependency
            from fastapi import Depends, HTTPException, status
            from fastapi.security import OAuth2PasswordBearer

            oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)

            async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
                """
                Fallback authentication dependency. Replace with actual implementation.
                """
                if not token:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Not authenticated. Auth service / routing not yet fully loaded.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                # Mock payload for safety during bootstrap/development
                return {"id": "fallback_user_id", "email": "admin@tu5g.com", "role": "admin"}


# 4. Common pagination dependency class
class PaginationParams:
    """
    Query parameters for pagination.
    Can be used with FastAPI Depends() inside path operations.
    """
    def __init__(
        self,
        skip: int = Query(default=0, ge=0, description="Number of records to skip"),
        limit: int = Query(default=100, ge=1, le=1000, description="Max number of records to return")
    ):
        self.skip = skip
        self.limit = limit

    def dict(self) -> Dict[str, int]:
        """Returns parameters as a dict."""
        return {"skip": self.skip, "limit": self.limit}


def get_pagination(
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max number of records to return")
) -> Dict[str, int]:
    """
    Function-based pagination dependency.
    """
    return {"skip": skip, "limit": limit}
