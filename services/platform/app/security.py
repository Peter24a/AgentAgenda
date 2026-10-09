import base64
import hashlib
import hmac
import secrets
from collections import defaultdict, deque
from time import monotonic


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Use a password of at least 12 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(derived).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt" or (int(n), int(r), int(p)) != (16384, 8, 1):
            return False
        result = hashlib.scrypt(password.encode(), salt=base64.urlsafe_b64decode(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(result, base64.urlsafe_b64decode(expected))
    except (ValueError, TypeError):
        return False


class RateLimiter:
    """Bounded in-process guard; deployment runs one worker, with Cloudflare protection upstream."""
    def __init__(self, limit: int = 10, window: int = 300):
        self.limit, self.window = limit, window
        self.entries: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = monotonic()
        if len(self.entries) > 10000:
            self.entries = defaultdict(deque, {k: v for k, v in self.entries.items() if v and v[-1] > now - self.window})
            if len(self.entries) > 10000 and key not in self.entries:
                return False
        entries = self.entries[key]
        while entries and entries[0] < now - self.window:
            entries.popleft()
        if len(entries) >= self.limit:
            return False
        entries.append(now)
        return True
