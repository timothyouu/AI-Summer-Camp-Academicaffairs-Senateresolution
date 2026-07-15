from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from .models import LoginRequest, LoginResponse


router = APIRouter(prefix="/api", tags=["authentication"])

DEMO_ACCOUNTS: dict[str, tuple[str, str, str]] = {
    "reviewer@campus.edu": ("demo123", "reviewer", "Jennifer D."),
    "employee@campus.edu": ("demo123", "employee", "Alex B."),
}


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    account = DEMO_ACCOUNTS.get(payload.email.lower().strip())
    if account is None or account[0] != payload.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid demo credentials")
    return LoginResponse(role=account[1], name=account[2])
