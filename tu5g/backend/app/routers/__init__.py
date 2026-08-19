"""
TU5G Router Package.
This package contains all the FastAPI routers for the TU5G backend application,
including customer management, network telemetry, eSIM provisioning, AI companions,
internal Hmail, governance, compliance, and administration.
"""

from app.routers import (
    admin, customers, router, esim, ai_characters, chat, holo, telemetry,
    auth_ext, kyc, esim_store, payments, hmail, governance, super_admin
)
