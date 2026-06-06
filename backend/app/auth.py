"""Auth dependencies for FastAPI routes.

BasicAuth (BASIC_AUTH_USER + BASIC_AUTH_PASSWORD):
  Browser-facing auth for the web UI layer.

API key (BACKEND_API_KEY):
  Header-based check for all /api/* routes — requires X-Api-Key header.
  The frontend includes this via NEXT_PUBLIC_BACKEND_API_KEY env var.
  Stops casual scanning of the public backend URL without adding CORS pain.

Both are opt-in: if env vars are unset, the check is skipped (local dev).
"""
from __future__ import annotations

import os
import secrets

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic(auto_error=False)

_USER = os.environ.get("BASIC_AUTH_USER", "")
_PASS = os.environ.get("BASIC_AUTH_PASSWORD", "")
_ENABLED = bool(_USER and _PASS)


def require_auth(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    """FastAPI dependency — inject via app-level middleware or per-router."""
    if not _ENABLED:
        return  # auth disabled — local dev or trusted network

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    # constant-time comparison to prevent timing attacks
    user_ok = secrets.compare_digest(credentials.username.encode(), _USER.encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), _PASS.encode())

    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


# ── API key auth ─────────────────────────────────────────────────────────────

_API_KEY = os.environ.get("BACKEND_API_KEY", "")
_API_KEY_ENABLED = bool(_API_KEY)


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-Api-Key")) -> None:
    """Require X-Api-Key header on all /api/* routes when BACKEND_API_KEY is set."""
    if not _API_KEY_ENABLED:
        return

    if x_api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Api-Key header required")

    if not secrets.compare_digest(x_api_key.encode(), _API_KEY.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
