"""
SIM Card Utility Module.
Provides helper functions for generating country-specific SIM card numbers and ICCIDs.
"""

import random

COUNTRY_CODE: str = "+984"
SIM_RANGE_START: int = 799_000_000
SIM_RANGE_END: int = 799_999_999


def generate_sim_number() -> str:
    """
    Generates a random unique SIM number with the specified country code prefix.
    Range is between 799,000,000 and 799,999,999.
    
    Returns:
        str: E.g., "+984799513524"
    """
    number = random.randint(SIM_RANGE_START, SIM_RANGE_END)
    return f"{COUNTRY_CODE}{number}"


def generate_iccid() -> str:
    """
    Generates a standard 20-digit ICCID starting with 89, country-specific prefix.
    
    Formatting:
    - '89' (2 digits) - Telecom Industry Identifier.
    - '984' (3 digits) - Country code without the '+' prefix.
    - Random 15 digits to complete the standard 20-digit length.

    Returns:
        str: 20-digit ICCID string.
    """
    clean_cc = COUNTRY_CODE.replace("+", "")
    prefix = f"89{clean_cc}"
    # 20 total digits, prefix takes 5 digits, so we need 15 random digits.
    # range: 10^14 (100,000,000,000,000) to 10^15 - 1 (999,999,999,999,999)
    random_part = random.randint(10**14, 10**15 - 1)
    return f"{prefix}{random_part}"
