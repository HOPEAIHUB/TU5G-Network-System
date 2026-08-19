"""
TU5G Services Package.
This package contains service wrappers and engines for the TU5G backend application,
including LLM generation, email communication, storage helpers, telemetry ingestion,
SIM card utilities, and core virtual network engine.
"""

from app.services.email import send_email, fetch_unread_emails
from app.services.kyc import upload_kyc_document, submit_kyc, verify_kyc, get_kyc_status, get_pending_kycs
from app.services.llm import chat_completion
from app.services.network_engine import (
    VirtualCell as VirtualCellEngine, create_cell, get_cell, update_cell,
    delete_cell, list_cells, simulate_load
)
from app.services.otp import (
    generate_otp, send_otp_email, send_otp_sms, verify_otp, store_otp,
    get_stored_otp, invalidate_otp, check_and_increment_rate_limit
)
from app.services.payment import (
    create_vpa, get_vpa, get_wallet_balance, add_funds, process_payment,
    create_payment_session, verify_payment, get_transaction_history
)
from app.services.sim import generate_sim_number, generate_iccid
from app.services.storage import init_minio_client, create_bucket_if_not_exists, upload_file, download_file, list_files
from app.services.telemetry import (
    TelemetryBuffer, ConnectionManager, ingest_telemetry, get_latest_telemetry,
    get_telemetry_history, init_mqtt_client
)
