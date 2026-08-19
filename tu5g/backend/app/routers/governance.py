from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_user
from app import crud
from app.schemas import GovernanceApplicationCreate, GovernanceApplicationUpdate, GovernanceApplicationResponse

router = APIRouter(prefix="/governance", tags=["Platform Governance"])

@router.post("/applications", response_model=GovernanceApplicationResponse, status_code=status.HTTP_201_CREATED)
async def submit_application(
    app_in: GovernanceApplicationCreate,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit a formal governance membership or cellular node application."""
    return await crud.create_governance_application(db, current_user["id"], app_in)

@router.get("/applications", response_model=List[GovernanceApplicationResponse])
async def list_applications(
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List applications. Regular users see their own; admin/super_admin see all."""
    if current_user["role"] in ["admin", "super_admin"]:
        return await crud.get_governance_applications(db)
    else:
        # Filter own
        apps = await crud.get_governance_applications(db)
        return [a for a in apps if a.user_id == current_user["id"]]

@router.get("/applications/{app_id}", response_model=GovernanceApplicationResponse)
async def get_application_details(
    app_id: int,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve detailed metadata for a specific governance application."""
    application = await crud.get_governance_application(db, app_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Governance application not found."
        )
    if application.user_id != current_user["id"] and current_user["role"] not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view this application."
        )
    return application

@router.put("/applications/{app_id}", response_model=GovernanceApplicationResponse)
async def review_application(
    app_id: int,
    update_in: GovernanceApplicationUpdate,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Review, approve, or reject an organization governance application."""
    if current_user["role"] not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges are required to review applications."
        )
    application = await crud.get_governance_application(db, app_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Governance application not found."
        )
    return await crud.update_governance_status(db, app_id, update_in)
