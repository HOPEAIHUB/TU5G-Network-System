"""
Custom middlewares for the TU5G platform backend.
Includes HAABS (HMTML Advanced Authentication & Banking Security) compliant implementations:
- RequestIDMiddleware: Correlates requests by generating/forwarding X-Request-ID headers.
- SecureHeadersMiddleware: Enhances API security with standard HAABS headers (CSP, HSTS, X-Frame-Options, etc.).
- RateLimitMiddleware: In-memory sliding window IP-based rate limiting with route-specific limits.
- AuditLoggingMiddleware: Performs structured JSON logging of HTTP requests with IP, duration, and user tracking.
"""

import json
import logging
import time
import uuid
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

# Initialize logger for audit logging
logger = logging.getLogger("tu5g.audit")
logger.setLevel(logging.INFO)

# Ensure console handler is attached if logger doesn't have handlers
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def get_client_ip(request: Request) -> str:
    """
    Extracts client IP address from request headers or socket details.
    Supports X-Forwarded-For when operating behind reverse proxies (NGINX).
    """
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that generates and injects a unique X-Request-ID for every incoming HTTP request.
    If the request already provides an X-Request-ID header, it is reused to support tracing.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
            
        # Store the request_id in request state for downstream middlewares & routers
        request.state.request_id = request_id
        
        # Proceed with request pipeline
        response = await call_next(request)
        
        # Return the request ID in the response headers
        response.headers["X-Request-ID"] = request_id
        return response


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware adding industry-standard security headers to all responses to protect the backend.
    Enforces HAABS security compliance.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        # Clickjacking mitigation
        response.headers["X-Frame-Options"] = "DENY"
        
        # MIME sniffing mitigation
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # XSS protection header
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # HTTP Strict Transport Security (HSTS) - 1 year with subdomains
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy (CSP)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:;"
        )
        
        # Permissions Policy for browser hardware features
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), "
            "accelerometer=(), gyroscope=(), magnetometer=(), fullscreen=(self)"
        )
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    In-memory IP-based rate limiting middleware using a sliding window algorithm.
    Enforces specialized rate limits for sensitive endpoint prefixes:
    - /auth/* -> 5 requests/second
    - /esim/* -> 10 requests/second
    - /ai/*   -> 3 requests/second
    - Default -> 20 requests/second (configurable)
    """
    def __init__(self, app, default_rate: int = 20):
        super().__init__(app)
        self.default_rate = default_rate
        # Specialized path prefix limits: (prefix, max_requests_per_second)
        self.route_limits: List[Tuple[str, int]] = [
            ("/auth", 5),
            ("/esim", 10),
            ("/ai", 3),
        ]
        # Memory structure: key ("ip:prefix") -> list of timestamps (floats)
        self.history: Dict[str, List[float]] = defaultdict(list)
        self.last_cleanup: float = time.time()

    def _get_route_limit(self, path: str) -> Tuple[str, int]:
        """Matches path against route prefixes or returns default rate."""
        for prefix, limit in self.route_limits:
            if path.startswith(prefix):
                return prefix, limit
        return "default", self.default_rate

    def _cleanup_stale_entries(self, now: float):
        """Periodically purges timestamps older than sliding window to prevent memory leaks."""
        if now - self.last_cleanup > 60.0:
            cutoff = now - 1.0
            stale_keys = []
            for key, timestamps in list(self.history.items()):
                active = [t for t in timestamps if t > cutoff]
                if active:
                    self.history[key] = active
                else:
                    stale_keys.append(key)
            for k in stale_keys:
                self.history.pop(k, None)
            self.last_cleanup = now

    async def dispatch(self, request: Request, call_next) -> Response:
        now = time.time()
        self._cleanup_stale_entries(now)

        client_ip = get_client_ip(request)
        path = request.url.path
        prefix, limit = self._get_route_limit(path)

        key = f"{client_ip}:{prefix}"
        window_start = now - 1.0

        # Filter timestamps within 1-second window
        active_timestamps = [t for t in self.history[key] if t > window_start]
        self.history[key] = active_timestamps

        if len(active_timestamps) >= limit:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Maximum {limit} requests per second allowed for prefix '{prefix}'."
                },
                headers={
                    "Retry-After": "1",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": "1"
                }
            )

        self.history[key].append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - len(self.history[key])))
        return response


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured JSON logging of all incoming requests and outgoing responses.
    Tracks duration, endpoint, method, status, client IP, request_id, and authenticated user_id if present.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        
        method = request.method
        path = request.url.path
        client_ip = get_client_ip(request)
        request_id = getattr(request.state, "request_id", "unknown")
        
        response = await call_next(request)
        
        duration = time.time() - start_time
        status_code = response.status_code
        
        # Extract user_id from request state (set by authentication dependencies or middlewares)
        user_id = None
        if hasattr(request.state, "user_id") and request.state.user_id:
            user_id = request.state.user_id
        elif hasattr(request.state, "user") and request.state.user:
            user = request.state.user
            if isinstance(user, dict):
                user_id = user.get("id") or user.get("sub") or user.get("email")
            elif hasattr(user, "id"):
                user_id = getattr(user, "id")
                
        # Structured JSON log representation
        log_data = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration * 1000, 2),
            "ip": client_ip,
            "user_id": user_id or "anonymous"
        }
        
        # Write to structured log
        logger.info(json.dumps(log_data))
        
        return response


# Backward-compatibility alias
AuditLogMiddleware = AuditLoggingMiddleware
