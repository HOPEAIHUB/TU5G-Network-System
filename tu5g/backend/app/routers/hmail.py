from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_user
from app import crud
from app.schemas import HmailAccountCreate, HmailAccountResponse, HmailMessageCreate, HmailMessageResponse

router = APIRouter(prefix="/hmail", tags=["H-Mail Service"])

@router.post("/account", response_model=HmailAccountResponse, status_code=status.HTTP_201_CREATED)
async def register_hmail_account(
    account_in: HmailAccountCreate,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Register a new Hmail messaging account for the current user."""
    # Check if user already has an account
    existing = await crud.get_hmail_account_by_user(db, current_user["id"])
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hmail account already exists for this user."
        )
    return await crud.create_hmail_account(db, current_user["id"], account_in)

@router.get("/account", response_model=HmailAccountResponse)
async def get_current_hmail_account(
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch the active Hmail account configuration for the current user."""
    account = await crud.get_hmail_account_by_user(db, current_user["id"])
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Hmail account registered for this user."
        )
    return account

@router.post("/messages", response_model=HmailMessageResponse, status_code=status.HTTP_201_CREATED)
async def send_hmail(
    message_in: HmailMessageCreate,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a secure internal holographic email."""
    account = await crud.get_hmail_account_by_user(db, current_user["id"])
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A registered Hmail account is required to send messages."
        )
    return await crud.create_hmail_message(db, account.id, account.email_address, message_in)

@router.get("/messages", response_model=List[HmailMessageResponse])
async def list_hmail_messages(
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all messages delivered to the user's active Hmail inbox."""
    account = await crud.get_hmail_account_by_user(db, current_user["id"])
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A registered Hmail account is required to access messages."
        )
    return await crud.get_hmail_messages_by_account(db, account.id)
