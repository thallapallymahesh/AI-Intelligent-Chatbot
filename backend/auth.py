"""Supabase Auth session verification for protected API routes."""

from dataclasses import dataclass
import hmac
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend import supabase_store

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None = None
    name: str | None = None


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    local_token = os.getenv("LOCAL_DEV_TOKEN", "")
    if os.getenv("LOCAL_DEV_AUTH", "false").lower() == "true" and local_token:
        if hmac.compare_digest(credentials.credentials, local_token):
            return AuthenticatedUser(id="local-development-user", name="Local developer")
        raise HTTPException(status_code=401, detail="Your local session is invalid.")
    if not supabase_store.configured():
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    try:
        identity = supabase_store.verify_access_token(credentials.credentials)
    except supabase_store.AuthenticationError as error:
        raise HTTPException(status_code=401, detail="Your session is invalid or expired.") from error
    except supabase_store.SupabaseError as error:
        raise HTTPException(status_code=503, detail="Authentication service is unavailable.") from error

    metadata = identity.get("user_metadata") or {}
    return AuthenticatedUser(
        id=identity["id"],
        email=identity.get("email"),
        name=metadata.get("name"),
    )
