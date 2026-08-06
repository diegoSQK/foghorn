"""Auth endpoints + FastAPI dependencies (multi-user, August 2026).

The model is invite-link-as-credential: an admin creates a user, which mints a
token; the URL ``/join/<token>`` both claims the account (first open) and
signs in on any later open. Sessions ride an HttpOnly cookie with rolling
expiry (see ``repo/sessions.py``). ``Secure`` on the cookie is opt-in via
``FOGHORN_SECURE_COOKIES=1`` because the Tailscale fleet deployment serves
plain HTTP, where a Secure cookie would never be stored.

Dependencies exported for other routers:

- ``optional_user`` — the session's ``User`` or ``None``; never raises.
- ``require_user`` — 401 without a valid session.
- ``require_admin`` — 401 anonymous / 403 non-admin.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from foghorn.models import User
from foghorn.repo import db
from foghorn.repo import sessions as sessions_repo
from foghorn.repo import users as users_repo

router = APIRouter()

SESSION_COOKIE = "foghorn_session"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=sessions_repo.SESSION_TTL_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("FOGHORN_SECURE_COOKIES") == "1",
        path="/",
    )


def optional_user(request: Request) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    conn = db.connect()
    try:
        return sessions_repo.resolve(conn, token)
    finally:
        conn.close()


def require_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="sign-in required")
    return user


def require_admin(user: Annotated[User, Depends(require_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    return user


class MeView(BaseModel):
    id: int
    display_name: str
    email: str | None
    is_admin: bool


def _me(user: User) -> MeView:
    assert user.id is not None
    return MeView(
        id=user.id,
        display_name=user.display_name,
        email=user.email,
        is_admin=user.is_admin,
    )


class InviteInfoView(BaseModel):
    """What the /join page needs to render before the visitor commits."""

    display_name: str
    claimed: bool


class ClaimBody(BaseModel):
    token: str
    display_name: str | None = None
    email: str | None = None


@router.get("/api/auth/invite/{token}", response_model=InviteInfoView)
def invite_info(token: str) -> InviteInfoView:
    conn = db.connect()
    try:
        user = users_repo.get_by_invite_token(conn, token)
    finally:
        conn.close()
    if user is None or user.disabled:
        raise HTTPException(status_code=404, detail="unknown invite")
    return InviteInfoView(display_name=user.display_name, claimed=user.claimed_at is not None)


@router.post("/api/auth/claim", response_model=MeView)
def claim(body: ClaimBody, response: Response) -> MeView:
    """Open an invite link: claim the account on first use, sign in on any
    use. Always mints a fresh session (multiple devices coexist fine)."""
    conn = db.connect()
    try:
        user = users_repo.get_by_invite_token(conn, body.token)
        if user is None or user.disabled:
            raise HTTPException(status_code=404, detail="unknown invite")
        assert user.id is not None
        user = users_repo.claim(
            conn, user.id, display_name=body.display_name, email=body.email
        )
        assert user.id is not None
        token = sessions_repo.create(conn, user.id)
    finally:
        conn.close()
    _set_session_cookie(response, token)
    return _me(user)


@router.get("/api/auth/me", response_model=MeView)
def me(user: Annotated[User, Depends(require_user)]) -> MeView:
    return _me(user)


@router.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        conn = db.connect()
        try:
            sessions_repo.delete(conn, token)
        finally:
            conn.close()
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# ---- Admin user management ------------------------------------------------


class UserAdminView(BaseModel):
    id: int
    display_name: str
    email: str | None
    is_admin: bool
    disabled: bool
    created_at: str
    claimed_at: str | None
    # Path form so the UI can prefix whatever origin it was served from.
    invite_path: str


def _admin_view(user: User) -> UserAdminView:
    assert user.id is not None
    return UserAdminView(
        id=user.id,
        display_name=user.display_name,
        email=user.email,
        is_admin=user.is_admin,
        disabled=user.disabled,
        created_at=user.created_at,
        claimed_at=user.claimed_at,
        invite_path=f"/join/{user.invite_token}",
    )


class UserCreate(BaseModel):
    display_name: str
    is_admin: bool = False


class DisabledUpdate(BaseModel):
    disabled: bool


@router.get("/api/auth/users", response_model=list[UserAdminView])
def list_users(_admin: Annotated[User, Depends(require_admin)]) -> list[UserAdminView]:
    conn = db.connect()
    try:
        return [_admin_view(u) for u in users_repo.list_all(conn)]
    finally:
        conn.close()


@router.post("/api/auth/users", response_model=UserAdminView, status_code=201)
def create_user(
    body: UserCreate, _admin: Annotated[User, Depends(require_admin)]
) -> UserAdminView:
    display_name = body.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="display_name required")
    conn = db.connect()
    try:
        return _admin_view(
            users_repo.create_invite(conn, display_name, is_admin=body.is_admin)
        )
    finally:
        conn.close()


@router.post("/api/auth/users/{user_id}/regenerate", response_model=UserAdminView)
def regenerate_invite(
    user_id: int, _admin: Annotated[User, Depends(require_admin)]
) -> UserAdminView:
    conn = db.connect()
    try:
        if users_repo.get_by_id(conn, user_id) is None:
            raise HTTPException(status_code=404, detail="unknown user")
        return _admin_view(users_repo.regenerate_token(conn, user_id))
    finally:
        conn.close()


@router.put("/api/auth/users/{user_id}/disabled", response_model=UserAdminView)
def set_user_disabled(
    user_id: int, body: DisabledUpdate, admin: Annotated[User, Depends(require_admin)]
) -> UserAdminView:
    if body.disabled and user_id == admin.id:
        # An admin locking themself out is never what anyone meant.
        raise HTTPException(status_code=422, detail="cannot disable yourself")
    conn = db.connect()
    try:
        if users_repo.get_by_id(conn, user_id) is None:
            raise HTTPException(status_code=404, detail="unknown user")
        return _admin_view(users_repo.set_disabled(conn, user_id, body.disabled))
    finally:
        conn.close()
