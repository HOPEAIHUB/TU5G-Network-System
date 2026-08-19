"""
Custom exceptions and FastAPI exception handlers for the TU5G platform backend.
Defines domain-specific errors and a standard method to register handlers in FastAPI.
"""

from typing import Any, Dict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class TU5GException(Exception):
    """
    Base exception class for all TU5G-specific platform errors.
    Standardizes error status codes and optional structured error details.
    """
    def __init__(self, message: str, status_code: int = 500, details: Dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class CustomerNotFound(TU5GException):
    """
    Raised when a requested customer record cannot be found in the system.
    """
    def __init__(self, message: str = "Customer not found", details: Dict[str, Any] | None = None):
        super().__init__(message=message, status_code=404, details=details)


class CellNotFound(TU5GException):
    """
    Raised when a target cellular site or cell transmitter cannot be found.
    """
    def __init__(self, message: str = "Cell or transmitter not found", details: Dict[str, Any] | None = None):
        super().__init__(message=message, status_code=404, details=details)


class SessionNotFound(TU5GException):
    """
    Raised when a required subscriber data session, auth session, or user session cannot be found.
    """
    def __init__(self, message: str = "Session not found", details: Dict[str, Any] | None = None):
        super().__init__(message=message, status_code=404, details=details)


class SimProvisioningError(TU5GException):
    """
    Raised when SIM provisioning operations fail on HSS/UDM or external carrier APIs.
    """
    def __init__(self, message: str = "SIM card provisioning failed", details: Dict[str, Any] | None = None):
        super().__init__(message=message, status_code=400, details=details)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Registers custom exception handlers with a FastAPI application instance.
    Standardizes the error JSON responses returned to client applications.
    """
    
    @app.exception_handler(TU5GException)
    async def tu5g_exception_handler(request: Request, exc: TU5GException) -> JSONResponse:
        """
        Catches all custom exceptions deriving from TU5GException and returns
        a consistent JSON error structure.
        """
        # Ensure request_id is included in the error response for debugging purposes
        request_id = getattr(request.state, "request_id", None)
        
        error_response = {
            "success": False,
            "error_code": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details,
        }
        
        if request_id:
            error_response["request_id"] = request_id
            
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response
        )
