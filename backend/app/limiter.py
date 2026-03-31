"""Shared rate-limiter instance used by all routers and main app."""
from slowapi import Limiter
from starlette.requests import Request


def _get_real_ip(request: Request) -> str:
    """Return the real client IP, reading X-Forwarded-For when behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_real_ip)
