"""
Utility functions for the TU5G platform backend.
Provides helpers for QR code generation, telemetry parsing, phone number validation,
ICCID verification (using the Luhn algorithm), pagination, timestamp generation, and security masking.
"""

from datetime import datetime, timezone
import io
import re
from typing import Any, Iterable, List

# Try importing qrcode for eSIM QR code generation.
# Handles cases where the qrcode library has not yet been added to requirements.txt.
try:
    import qrcode
except ImportError:
    qrcode = None


def generate_qr_code(data: str) -> bytes:
    """
    Generates a high-quality PNG QR code image as bytes for the provided string data.
    Commonly used for eSIM profiles or authentication tokens.
    """
    if qrcode is None:
        raise ImportError(
            "The 'qrcode' library is not installed in the environment. "
            "Please ensure 'qrcode' is added to requirements.txt and installed."
        )
        
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    return img_byte_arr.getvalue()


def format_phone_number(phone: str, default_country_code: str = "+94") -> str:
    """
    Formats a raw phone number into standard international E.164 format.
    E.g., "0771234567" with default "+94" -> "+94771234567"
    """
    if not phone:
        return ""
        
    # Strip any non-digit/non-plus characters
    cleaned = re.sub(r"[^\d+]", "", phone)
    
    if cleaned.startswith("+"):
        return cleaned
        
    # Remove leading local trunk prefix (usually '0') and prepend default country code
    if cleaned.startswith("0"):
        cleaned = cleaned[1:]
        
    # Prepend '+' if not present after country code prepending
    if default_country_code.startswith("+"):
        return f"{default_country_code}{cleaned}"
    else:
        return f"+{default_country_code}{cleaned}"


def validate_iccid(iccid: str) -> bool:
    """
    Validates a SIM card's ICCID (Integrated Circuit Card Identifier)
    using length checks (typically 19-20 digits) and the Luhn checksum algorithm.
    """
    if not iccid:
        return False
        
    # Clean whitespace or delimiters
    cleaned = re.sub(r"\D", "", iccid)
    
    if len(cleaned) not in [19, 20]:
        return False
        
    # Validate with Luhn algorithm
    total = 0
    reverse_digits = cleaned[::-1]
    for i, digit_char in enumerate(reverse_digits):
        val = int(digit_char)
        if i % 2 == 1:
            val *= 2
            if val > 9:
                val -= 9
        total += val
        
    return total % 10 == 0


def paginate_results(items: Iterable[Any], skip: int = 0, limit: int = 100) -> List[Any]:
    """
    Slices and paginates any in-memory list or iterable safely.
    """
    if not items:
        return []
    
    start = max(0, skip)
    end = start + max(1, limit)
    
    # Cast to list for slicing support
    return list(items)[start:end]


def timestamp_now() -> str:
    """
    Returns the current UTC time formatted in standard ISO-8601 with timezone suffix (Z).
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mask_sensitive_data(data: str, mask_char: str = "*") -> str:
    """
    Masks highly sensitive parameters (e.g. ICCID, IMSI, Auth Tokens, Credit Cards)
    by leaving only the first 4 and last 4 characters visible, replacing the rest with mask_char.
    """
    if not data:
        return ""
        
    length = len(data)
    if length <= 8:
        return mask_char * length
        
    visible_prefix = data[:4]
    visible_suffix = data[-4:]
    masked_part = mask_char * (length - 8)
    
    return f"{visible_prefix}{masked_part}{visible_suffix}"
