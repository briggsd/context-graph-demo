"""Optional HTTP Basic Auth for all FastAPI routes.

Set BASIC_AUTH_USER + BASIC_AUTH_PASSWORD environment variables to enable.
If either var is unset, auth is disabled (local dev / trusted network).
"""
from __future__ import annotations

import os
import secrets

from fastapi import Depends, HTTPException, status
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
