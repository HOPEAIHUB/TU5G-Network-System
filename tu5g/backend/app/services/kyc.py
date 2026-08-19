"""
KYC Verification Service for the TU5G platform.
Manages customer identity submissions, document uploads to MinIO,
admin reviews (verification/rejection), and status retrieval.
Supports dual DB storage (SQLAlchemy AsyncSession) and clean In-Memory fallback.
"""

import json
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import KYCSubmission
from app.services.storage import upload_file as minio_upload_file

logger = logging.getLogger(__name__)

# ==========================================
# Enums and In-Memory Storage Fallback
# ==========================================

class KYCStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    NOT_SUBMITTED = "not_submitted"


# Structure: { kyc_id: dict_record }
_mock_kyc_db: Dict[str, Dict[str, Any]] = {}


# ==========================================
# Storage Helpers
# ==========================================

def upload_kyc_document(user_id: str, file_path: str, original_filename: str) -> str:
    """
    Helper to upload KYC documents to MinIO storage bucket.
    Saves files under the 'kyc-documents' bucket with path '{user_id}/{uuid}_{filename}'.

    Args:
        user_id (str): ID of the user submitting the document.
        file_path (str): Path of the local file to upload.
        original_filename (str): Original name of the document file.

    Returns:
        str: Presigned secure URL to view/download the document, valid for 7 days.
    """
    bucket_name = "kyc-documents"
    unique_id = uuid.uuid4().hex
    # Clean up filename a bit
    safe_filename = original_filename.replace(" ", "_")
    object_name = f"{user_id}/{unique_id}_{safe_filename}"
    
    logger.info(f"Uploading KYC document '{original_filename}' for user '{user_id}' to MinIO...")
    try:
        url = minio_upload_file(bucket_name, object_name, file_path)
        logger.info(f"KYC document uploaded successfully. Presigned URL generated: {url}")
        return url
    except Exception as e:
        logger.error(f"Failed to upload KYC document to MinIO: {e}")
        raise RuntimeError(f"KYC Document upload failed: {str(e)}")


# ==========================================
# Core KYC Service Functions
# ==========================================

async def submit_kyc(
    user_id: str,
    full_name: str,
    id_type: str,
    id_number: str,
    address: str,
    document_urls: List[str],
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Submits a new KYC application.
    Saves details in the database or falls back to in-memory dictionary.

    Args:
        user_id (str): Unique user identifier.
        full_name (str): Customer's full name.
        id_type (str): Identity document type (e.g., 'Passport', 'National ID', 'Drivers License').
        id_number (str): Unique document identification number.
        address (str): Customer's residential address.
        document_urls (List[str]): Uploaded document presigned URLs.
        db (AsyncSession, optional): SQLAlchemy async database session.

    Returns:
        Dict[str, Any]: Dict containing the created KYC submission.
    """
    kyc_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    # Standardised dict structure
    kyc_data = {
        "id": kyc_id,
        "user_id": str(user_id),
        "full_name": full_name,
        "id_type": id_type,
        "id_number": id_number,
        "address": address,
        "document_urls": document_urls,
        "status": KYCStatus.PENDING.value,
        "admin_id": None,
        "notes": "",
        "created_date": now,
        "updated_date": now,
    }

    if db:
        try:
            db_submission = KYCSubmission(
                id=kyc_id,
                user_id=str(user_id),
                full_name=full_name,
                id_type=id_type,
                id_number=id_number,
                address=address,
                document_urls=json.dumps(document_urls),
                status=KYCStatus.PENDING.value,
                admin_id=None,
                notes="",
                created_date=now,
                updated_date=now
            )
            db.add(db_submission)
            await db.flush()  # Flush to catch constraints without full commit
            logger.info(f"KYC Submission saved to DB for user '{user_id}' with ID '{kyc_id}'")
            
            # Formulate the response dict from DB object
            return {
                "id": db_submission.id,
                "user_id": db_submission.user_id,
                "full_name": db_submission.full_name,
                "id_type": db_submission.id_type,
                "id_number": db_submission.id_number,
                "address": db_submission.address,
                "document_urls": json.loads(db_submission.document_urls),
                "status": db_submission.status,
                "admin_id": db_submission.admin_id,
                "notes": db_submission.notes,
                "created_date": db_submission.created_date,
                "updated_date": db_submission.updated_date,
            }
        except Exception as e:
            logger.warning(f"Database error writing KYC submission: {e}. Falling back to in-memory store.")
            await db.rollback()

    # In-Memory fallback
    _mock_kyc_db[kyc_id] = kyc_data
    logger.info(f"KYC Submission saved in-memory for user '{user_id}' with ID '{kyc_id}'")
    return kyc_data


async def verify_kyc(
    kyc_id: str,
    admin_id: str,
    approved: bool,
    notes: str = "",
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Approves or rejects a KYC submission.
    Performed by an administrator.

    Args:
        kyc_id (str): The KYC submission ID to review.
        admin_id (str): ID of the reviewing admin.
        approved (bool): True to verify, False to reject.
        notes (str): Reviewer's feedback notes (default: "").
        db (AsyncSession, optional): SQLAlchemy async database session.

    Returns:
        Dict[str, Any]: The updated KYC record dict.

    Raises:
        ValueError: If the kyc_id does not exist.
    """
    new_status = KYCStatus.VERIFIED.value if approved else KYCStatus.REJECTED.value
    now = datetime.utcnow()

    if db:
        try:
            result = await db.execute(select(KYCSubmission).where(KYCSubmission.id == kyc_id))
            db_submission = result.scalars().first()
            if db_submission:
                db_submission.status = new_status
                db_submission.admin_id = str(admin_id)
                db_submission.notes = notes
                db_submission.updated_date = now
                await db.flush()
                
                logger.info(f"KYC {kyc_id} updated in DB by Admin '{admin_id}' to status '{new_status}'")
                return {
                    "id": db_submission.id,
                    "user_id": db_submission.user_id,
                    "full_name": db_submission.full_name,
                    "id_type": db_submission.id_type,
                    "id_number": db_submission.id_number,
                    "address": db_submission.address,
                    "document_urls": json.loads(db_submission.document_urls),
                    "status": db_submission.status,
                    "admin_id": db_submission.admin_id,
                    "notes": db_submission.notes,
                    "created_date": db_submission.created_date,
                    "updated_date": db_submission.updated_date,
                }
        except Exception as e:
            logger.warning(f"Database error verifying KYC: {e}. Attempting in-memory fallback lookups.")
            await db.rollback()

    # In-Memory fallback
    if kyc_id not in _mock_kyc_db:
        raise ValueError(f"KYC submission with ID '{kyc_id}' not found.")
    
    record = _mock_kyc_db[kyc_id]
    record["status"] = new_status
    record["admin_id"] = str(admin_id)
    record["notes"] = notes
    record["updated_date"] = now
    
    logger.info(f"KYC {kyc_id} updated in-memory by Admin '{admin_id}' to status '{new_status}'")
    return record


async def get_kyc_status(user_id: str, db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """
    Retrieves the latest KYC submission details and overall status for a user.

    Args:
        user_id (str): Unique user identifier.
        db (AsyncSession, optional): SQLAlchemy async database session.

    Returns:
        Dict[str, Any]: Dict containing user's current status and details.
    """
    user_id_str = str(user_id)

    if db:
        try:
            # Query latest record for the user based on created_date descending
            query = (
                select(KYCSubmission)
                .where(KYCSubmission.user_id == user_id_str)
                .order_by(KYCSubmission.created_date.desc())
            )
            result = await db.execute(query)
            db_submission = result.scalars().first()
            if db_submission:
                return {
                    "user_id": db_submission.user_id,
                    "status": db_submission.status,
                    "kyc_id": db_submission.id,
                    "notes": db_submission.notes,
                    "updated_at": db_submission.updated_date,
                    "full_name": db_submission.full_name,
                    "document_urls": json.loads(db_submission.document_urls)
                }
        except Exception as e:
            logger.warning(f"Database error getting KYC status: {e}. Checking in-memory.")

    # In-Memory fallback (find latest by created_date)
    user_submissions = [v for v in _mock_kyc_db.values() if v["user_id"] == user_id_str]
    if user_submissions:
        # Sort in-memory list by created_date desc
        user_submissions.sort(key=lambda x: x["created_date"], reverse=True)
        latest = user_submissions[0]
        return {
            "user_id": latest["user_id"],
            "status": latest["status"],
            "kyc_id": latest["id"],
            "notes": latest["notes"],
            "updated_at": latest["updated_date"],
            "full_name": latest["full_name"],
            "document_urls": latest["document_urls"]
        }

    # No record exists
    return {
        "user_id": user_id_str,
        "status": KYCStatus.NOT_SUBMITTED.value,
        "kyc_id": None,
        "notes": None,
        "updated_at": None,
        "full_name": None,
        "document_urls": []
    }


async def get_pending_kycs(db: Optional[AsyncSession] = None) -> List[Dict[str, Any]]:
    """
    Retrieves all pending KYC submissions. Handy for the Admin Panel.

    Args:
        db (AsyncSession, optional): SQLAlchemy async database session.

    Returns:
        List[Dict[str, Any]]: A list of pending KYC records.
    """
    if db:
        try:
            query = select(KYCSubmission).where(KYCSubmission.status == KYCStatus.PENDING.value)
            result = await db.execute(query)
            db_list = result.scalars().all()
            return [
                {
                    "id": item.id,
                    "user_id": item.user_id,
                    "full_name": item.full_name,
                    "id_type": item.id_type,
                    "id_number": item.id_number,
                    "address": item.address,
                    "document_urls": json.loads(item.document_urls),
                    "status": item.status,
                    "admin_id": item.admin_id,
                    "notes": item.notes,
                    "created_date": item.created_date,
                    "updated_date": item.updated_date,
                }
                for item in db_list
            ]
        except Exception as e:
            logger.warning(f"Database error getting pending KYCs: {e}. Returning in-memory records.")

    # In-Memory fallback
    pending_records = [v for v in _mock_kyc_db.values() if v["status"] == KYCStatus.PENDING.value]
    # Sort by created date (oldest first, so admins see long-waiting applications)
    pending_records.sort(key=lambda x: x["created_date"])
    return pending_records
