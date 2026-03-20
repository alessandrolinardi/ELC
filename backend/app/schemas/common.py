"""Shared API response schemas."""
from typing import Generic, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel, Generic[T]):
    ok: bool
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None


def success_response(data) -> dict:
    return {"ok": True, "data": data}


def error_response(code: str, message: str, status_code: int = 400) -> tuple[dict, int]:
    return {"ok": False, "error": {"code": code, "message": message}}, status_code
