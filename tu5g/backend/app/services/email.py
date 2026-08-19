"""
Email Service Module.
Provides asynchronous email clients for sending emails (via SMTP)
and reading unread emails (via IMAP) using aiosmtplib and aioimaplib.
"""

import os
import logging
import email
from email.message import EmailMessage
from email.policy import default
from typing import List, Dict, Any, Optional

import aiosmtplib
import aioimaplib

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, body: str) -> None:
    """
    Sends an email asynchronously via SMTP.

    Args:
        to (str): Recipient email address.
        subject (str): Subject line of the email.
        body (str): Plain-text body of the email.

    Raises:
        ValueError: If SMTP environment variables are missing.
        Exception: If SMTP transmission fails.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port_str = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if not smtp_host or not smtp_user or not smtp_password:
        raise ValueError(
            "SMTP configuration is incomplete. "
            "Please check SMTP_HOST, SMTP_USER, and SMTP_PASSWORD environment variables."
        )

    try:
        smtp_port = int(smtp_port_str)
    except ValueError as e:
        raise ValueError(f"Invalid SMTP_PORT: {smtp_port_str}") from e

    # Create message
    message = EmailMessage()
    message["From"] = smtp_user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    # Determine security parameters based on standard port configurations
    use_tls = smtp_port == 465
    start_tls = smtp_port == 587 or smtp_port == 25

    try:
        logger.info(f"Connecting to SMTP server {smtp_host}:{smtp_port}...")
        await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user,
            password=smtp_password,
            use_tls=use_tls,
            start_tls=start_tls,
        )
        logger.info(f"Email successfully sent to {to}")
    except Exception as e:
        logger.error(f"SMTP error while sending email to {to}: {e}")
        raise


async def fetch_unread_emails(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetches unread emails asynchronously via IMAP.

    Args:
        limit (int): The maximum number of unread emails to retrieve (newest first).

    Returns:
        List[Dict[str, Any]]: A list of structured dicts, each containing:
            - id: IMAP message ID
            - subject: Email subject
            - sender: From email address
            - body: Plain-text or fallback HTML body
            - date: Date received

    Raises:
        ValueError: If IMAP environment variables are missing.
        Exception: If IMAP retrieval fails.
    """
    imap_host = os.getenv("IMAP_HOST")
    imap_port_str = os.getenv("IMAP_PORT", "993")
    
    # Fallback to SMTP_USER/SMTP_PASSWORD if IMAP specific ones are not defined
    imap_user = os.getenv("IMAP_USER", os.getenv("SMTP_USER"))
    imap_password = os.getenv("IMAP_PASSWORD", os.getenv("SMTP_PASSWORD"))

    if not imap_host or not imap_user or not imap_password:
        raise ValueError(
            "IMAP configuration is incomplete. "
            "Please check IMAP_HOST, IMAP_USER, and IMAP_PASSWORD environment variables."
        )

    try:
        imap_port = int(imap_port_str)
    except ValueError as e:
        raise ValueError(f"Invalid IMAP_PORT: {imap_port_str}") from e

    logger.info(f"Connecting to IMAP server {imap_host}:{imap_port}...")
    client = aioimaplib.IMAP4_SSL(host=imap_host, port=imap_port)
    await client.wait_hello_from_server()

    try:
        # Perform login and select INBOX
        await client.login(imap_user, imap_password)
        await client.select("INBOX")

        # Search for unread/unseen messages
        status, data = await client.search("UNSEEN")
        if status != "OK":
            logger.warning(f"Failed to search unseen messages: status={status}")
            return []

        # Parse message IDs from response
        # The result of search is usually a space-separated sequence of bytes inside a list
        msg_ids = data[0].split()
        if not msg_ids:
            logger.info("No unread messages found.")
            return []

        # Grab latest unread messages up to the limit
        msg_ids = msg_ids[::-1][:limit]
        unread_emails = []

        for msg_id in msg_ids:
            msg_id_str = msg_id.decode()
            # Fetch raw RFC822 full message bytes
            fetch_status, fetch_data = await client.fetch(msg_id_str, "RFC822")
            if fetch_status != "OK":
                logger.error(f"Failed to fetch email with ID {msg_id_str}")
                continue

            # Identify the actual email body bytes inside IMAP fetch data structure
            message_bytes = b""
            if len(fetch_data) >= 3:
                # Standard aioimaplib format: [metadata, rfc822_content_bytes, closing_parenthesis]
                message_bytes = fetch_data[1]
            else:
                # Fallback to identify the largest bytes segment representing the body
                parts = [p for p in fetch_data if isinstance(p, bytes)]
                if parts:
                    message_bytes = max(parts, key=len)

            if not message_bytes:
                logger.warning(f"No email bytes found for message ID {msg_id_str}")
                continue

            # Parse MIME email message
            msg = email.message_from_bytes(message_bytes, policy=default)
            subject = msg.get("Subject", "")
            sender = msg.get("From", "")
            date = msg.get("Date", "")

            # Extract body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))
                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        body_part = part.get_payload(decode=True)
                        if body_part:
                            body = body_part.decode(errors="replace")
                            break
                # Fallback to HTML if no text/plain body was found
                if not body:
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition", ""))
                        if content_type == "text/html" and "attachment" not in content_disposition:
                            body_part = part.get_payload(decode=True)
                            if body_part:
                                body = body_part.decode(errors="replace")
                                break
            else:
                body_part = msg.get_payload(decode=True)
                if body_part:
                    body = body_part.decode(errors="replace")

            unread_emails.append({
                "id": msg_id_str,
                "subject": subject,
                "sender": sender,
                "body": body.strip(),
                "date": date,
            })

        return unread_emails

    except Exception as e:
        logger.error(f"IMAP retrieval failed: {e}")
        raise
    finally:
        # Cleanly log out of the IMAP connection
        try:
            await client.logout()
            logger.info("IMAP logout complete.")
        except Exception:
            pass
