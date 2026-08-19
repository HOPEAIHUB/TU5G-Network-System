from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_user
from app import crud
from app.schemas import UserResponse, AuditLogResponse

router = APIRouter(prefix="/super-admin", tags=["Super Admin Operations"])

def require_super_admin(current_user: Any = Depends(get_current_user)):
    """Enforce that the caller must possess the super_admin system role."""
    if current_user["role"] != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super administrative privileges are required to perform this action."
        )
    return current_user

@router.get("/audit-logs", response_model=List[AuditLogResponse])
async def view_audit_logs(
    current_user: Any = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve all compliance and security audit logs."""
    return await crud.get_audit_logs(db)

@router.put("/users/{user_id}/role", response_model=UserResponse)
async def modify_user_role(
    user_id: int,
    role: str,
    current_user: Any = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    """Directly modify system access roles for any platform user."""
    if role not in ["user", "admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Must be 'user', 'admin', or 'super_admin'."
        )
    updated_user = await crud.update_user_role(db, user_id, role)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    return updated_user

@router.put("/users/{user_id}/status", response_model=UserResponse)
async def toggle_user_status(
    user_id: int,
    is_active: bool,
    current_user: Any = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate or activate user accounts for compliance purposes."""
    updated_user = await crud.update_user_status(db, user_id, is_active)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    return updated_user
