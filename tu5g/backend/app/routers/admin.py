"""
Admin routers for TU5G platform.
Handles authentication, token generation, profile retrieval, and user creation.
"""

from datetime import timedelta
from typing import Any, Optional
from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

# Attempt to import services; fallback to mock implementations if they do not exist yet
try:
    from app.services.auth import (
        get_current_user,
        authenticate_user,
        create_access_token,
    )
except ImportError:
    # Fallback/mock signatures to guarantee file compiles independently
    async def get_current_user(*args, **kwargs) -> Any:
        raise NotImplementedError("Authentication service not fully configured.")

    async def authenticate_user(*args, **kwargs) -> Any:
        raise NotImplementedError("Authentication service not fully configured.")

    def create_access_token(*args, **kwargs) -> str:
        raise NotImplementedError("Authentication service not fully configured.")

router = APIRouter(prefix="/admin", tags=["Admin / Authentication"])


# ==========================================
# Pydantic Schemas
# ==========================================

class Token(BaseModel):
    """Schema for OAuth2 access token response."""
    access_token: str = Field(..., description="The JWT access token")
    token_type: str = Field("bearer", description="The token type")


class UserCreate(BaseModel):
    """Schema for creating a new user (admin only)."""
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=8, description="User's password (min 8 chars)")
    role: str = Field("user", description="User role, e.g., 'admin' or 'user'")


class UserResponse(BaseModel):
    """Schema for returning user information."""
    id: str = Field(..., description="Unique identifier for the user")
    username: str = Field(..., description="User's username")
    email: EmailStr = Field(..., description="User's email address")
    role: str = Field(..., description="User's assigned role")
    is_active: bool = Field(True, description="Whether the user is currently active")

    class Config:
        from_attributes = True


# ==========================================
# Endpoints
# ==========================================

@router.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Any:
    """
    OAuth2 compatible token login.
    Takes username and password in the request body (form-encoded) and returns a JWT token.
    """
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate access token (standard expiry is typically 30-60 minutes)
    access_token_expires = timedelta(minutes=60)
    access_token = create_access_token(
        data={"sub": user.username, "role": getattr(user, "role", "user")},
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/token", response_model=Token, status_code=status.HTTP_200_OK)
async def token_alternative(form_data: OAuth2PasswordRequestForm = Depends()) -> Any:
    """
    Alternative OAuth2 token endpoint.
    Often required by automated tools or integrations looking specifically for /admin/token.
    """
    return await login(form_data)


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_me(current_user: Any = Depends(get_current_user)) -> Any:
    """
    Get current logged-in admin or user information.
    Protected endpoint requiring a valid Bearer JWT.
    """
    return current_user


@router.post("/create-user", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate, 
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Create a new user.
    Restricted to admin users only.
    """
    # Verify that the current user has the admin role
    user_role = getattr(current_user, "role", None)
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation restricted to administrative accounts only.",
        )
    
    # In a real environment, we would invoke the user creation crud logic here:
    # e.g., from app.crud.user import create_db_user
    # db_user = await create_db_user(db, user_in)
    # Since this is a router interface, we can raise a simulated success or delegate to crud.
    
    # Mocking successful user creation for router testing
    import uuid
    mocked_user = {
        "id": str(uuid.uuid4()),
        "username": user_in.username,
        "email": user_in.email,
        "role": user_in.role,
        "is_active": True
    }
    return mocked_user
