"""
Storage Service Module.
Provides helper methods for interacting with MinIO/S3-compatible storage.
"""

import os
import logging
import tempfile
from datetime import timedelta
from typing import List
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


def init_minio_client() -> Minio:
    """
    Initializes and returns a MinIO client instance.

    Loads the following environment variables:
    - MINIO_ENDPOINT (e.g., 'play.min.io' or 'localhost:9000')
    - MINIO_ACCESS_KEY
    - MINIO_SECRET_KEY
    - MINIO_SECURE ('true' or 'false', default 'true')

    Returns:
        Minio: Configured MinIO Client.

    Raises:
        ValueError: If connection variables are incomplete.
    """
    endpoint = os.getenv("MINIO_ENDPOINT")
    access_key = os.getenv("MINIO_ACCESS_KEY")
    secret_key = os.getenv("MINIO_SECRET_KEY")
    secure_str = os.getenv("MINIO_SECURE", "true").lower()
    secure = secure_str in ("true", "1", "yes")

    if not endpoint or not access_key or not secret_key:
        raise ValueError(
            "MinIO configuration is incomplete. "
            "Please check MINIO_ENDPOINT, MINIO_ACCESS_KEY, and MINIO_SECRET_KEY environment variables."
        )

    try:
        client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        return client
    except Exception as e:
        logger.error(f"Failed to initialize MinIO client: {e}")
        raise


def create_bucket_if_not_exists(bucket: str) -> None:
    """
    Checks if a bucket exists, and creates it if it does not.

    Args:
        bucket (str): The name of the bucket to find or create.

    Raises:
        S3Error: If bucket operations fail.
    """
    client = init_minio_client()
    try:
        found = client.bucket_exists(bucket)
        if not found:
            client.make_bucket(bucket)
            logger.info(f"Bucket '{bucket}' was created successfully.")
        else:
            logger.debug(f"Bucket '{bucket}' already exists.")
    except S3Error as e:
        logger.error(f"S3Error checking/creating bucket '{bucket}': {e}")
        raise


def upload_file(bucket: str, object_name: str, file_path: str) -> str:
    """
    Uploads a local file to MinIO, ensuring the bucket exists, and returns
    a secure presigned URL to access the uploaded file.

    Args:
        bucket (str): The target bucket name.
        object_name (str): The destination key/object path in the bucket.
        file_path (str): The local system file path to upload.

    Returns:
        str: A secure, signed download/view URL for the uploaded object,
             valid for 7 days.

    Raises:
        S3Error: If upload operations fail.
    """
    client = init_minio_client()
    create_bucket_if_not_exists(bucket)

    try:
        client.fput_object(bucket, object_name, file_path)
        logger.info(f"Successfully uploaded '{file_path}' as '{object_name}' in bucket '{bucket}'")

        # Generate a presigned URL valid for 7 days (the maximum allowed by standard AWS S3 / MinIO)
        url = client.presigned_get_object(
            bucket_name=bucket,
            object_name=object_name,
            expires=timedelta(days=7),
        )
        return url
    except S3Error as e:
        logger.error(f"Failed to upload '{file_path}' to '{bucket}/{object_name}': {e}")
        raise


def download_file(bucket: str, object_name: str) -> str:
    """
    Downloads an object from MinIO to the local system temp directory.

    Args:
        bucket (str): The source bucket name.
        object_name (str): The object name/key in the bucket.

    Returns:
        str: The path to the downloaded local temporary file.

    Raises:
        S3Error: If downloading fails.
    """
    client = init_minio_client()
    
    # Generate a temporary path based on the system temp directory and the object's clean name
    clean_name = object_name.replace("/", "_")
    temp_dir = tempfile.gettempdir()
    local_file_path = os.path.join(temp_dir, clean_name)

    try:
        client.fget_object(bucket, object_name, local_file_path)
        logger.info(f"Successfully downloaded '{bucket}/{object_name}' to '{local_file_path}'")
        return local_file_path
    except S3Error as e:
        logger.error(f"Failed to download object '{bucket}/{object_name}': {e}")
        raise


def list_files(bucket: str) -> List[str]:
    """
    Lists the keys of all objects stored in a given bucket.

    Args:
        bucket (str): The bucket name.

    Returns:
        List[str]: A list of object names/keys in the bucket.
    """
    client = init_minio_client()
    try:
        if not client.bucket_exists(bucket):
            logger.warning(f"Bucket '{bucket}' does not exist.")
            return []

        objects = client.list_objects(bucket, recursive=True)
        return [obj.object_name for obj in objects]
    except S3Error as e:
        logger.error(f"Failed to list objects in bucket '{bucket}': {e}")
        raise
