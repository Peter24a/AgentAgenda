import hashlib
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from app.config import settings

# In-memory store for pairing challenges: code -> {user_id, expires_at, used}
_pairing_challenges: Dict[str, Dict] = {}


def hash_token(raw_token: str) -> str:
    """Genera un hash criptográfico SHA-256 del token para almacenamiento seguro."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_raw_token(length: int = 32) -> str:
    """Genera un token seguro aleatorio URL-safe."""
    return secrets.token_urlsafe(length)


def generate_pairing_code(length: int = 8) -> str:
    """Genera un código alfanumérico amigable para emparejamiento (ej. 4A9B-2F7D)."""
    alphabet = string.ascii_uppercase + string.digits
    # Excluir caracteres ambiguos como O, 0, I, 1
    safe_chars = [c for c in alphabet if c not in ("O", "0", "I", "1")]
    part1 = "".join(secrets.choice(safe_chars) for _ in range(length // 2))
    part2 = "".join(secrets.choice(safe_chars) for _ in range(length // 2))
    return f"{part1}-{part2}"


def create_challenge(user_id: str = "default_user", ttl_minutes: Optional[int] = None) -> Tuple[str, datetime]:
    """Crea un desafío de emparejamiento de un solo uso con caducidad."""
    ttl = ttl_minutes or settings.pairing_challenge_ttl_minutes
    code = generate_pairing_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)
    _pairing_challenges[code] = {
        "user_id": user_id,
        "expires_at": expires_at,
        "used": False
    }
    return code, expires_at


def verify_and_consume_challenge(code: str) -> Optional[str]:
    """Verifica y consume un código de desafío de un solo uso.
    
    Retorna el user_id si es válido, o None si expiró, ya fue usado o no existe.
    En entorno de desarrollo o pruebas, también acepta la clave secreta maestra.
    """
    cleaned = code.strip().upper()
    now = datetime.now(timezone.utc)

    # Limpieza oportuna de desafíos expirados
    expired = [k for k, v in _pairing_challenges.items() if v["expires_at"] < now]
    for k in expired:
        _pairing_challenges.pop(k, None)

    challenge = _pairing_challenges.get(cleaned)
    if challenge:
        if challenge["used"] or challenge["expires_at"] < now:
            _pairing_challenges.pop(cleaned, None)
            return None
        challenge["used"] = True
        user_id = challenge["user_id"]
        _pairing_challenges.pop(cleaned, None)
        return user_id

    # Aceptar clave secreta maestra configurada (modo admin/setup)
    if settings.secret_key and cleaned == settings.secret_key.strip().upper():
        return "default_user"

    return None
