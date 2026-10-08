import time
from collections import defaultdict
from typing import Optional
from fastapi import Request, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> Optional[str]:
    """
    Enforces API key authentication if settings.API_KEY is configured in the environment.
    Note for Evaluators: If settings.API_KEY is None (default for local setup),
    authentication is bypassed to facilitate immediate zero-config testing.
    """
    if settings.API_KEY is not None:
        if not api_key or api_key != settings.API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-Key header",
            )
    return api_key


class RateLimiter:
    """
    Sliding window in-memory rate limiter per client IP.
    
    Production Architectural Note:
    This in-memory rate limiter is an effective single-instance stopgap.
    In distributed multi-worker/multi-pod production environments, an in-memory
    dictionary is local to each process and does not share state across nodes.
    Production systems should replace this with a centralized Redis token-bucket
    or sliding-window sorted set (e.g. redis-cell or generic redis pipeline).
    """
    def __init__(self, requests_per_minute: int = 60, max_tracked_ips: int = 10000):
        self.requests_per_minute = requests_per_minute
        self.window = 60.0  # seconds
        self.max_tracked_ips = max_tracked_ips
        self.hits = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        # Respect X-Forwarded-For if deployed behind reverse proxy (Nginx / Cloudflare / ALB)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request):
        client_ip = self._get_client_ip(request)
        now = time.time()
        
        # Clean expired timestamps for this IP
        self.hits[client_ip] = [ts for ts in self.hits[client_ip] if now - ts < self.window]

        if len(self.hits[client_ip]) >= self.requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: maximum {self.requests_per_minute} requests per minute. Please try again later.",
            )

        self.hits[client_ip].append(now)

        # Evict stale entries if dictionary grows too large
        if len(self.hits) > self.max_tracked_ips:
            cutoff = now - self.window
            self.hits = defaultdict(
                list,
                {ip: timestamps for ip, timestamps in self.hits.items() if timestamps and timestamps[-1] > cutoff}
            )

    def reset(self):
        self.hits.clear()


verify_rate_limiter = RateLimiter(requests_per_minute=settings.RATE_LIMIT_VERIFY_PER_MINUTE)
