import hashlib
import secrets

import bcrypt


def hash_password(plain_password: str) -> str:
    """Hash a plain password using bcrypt."""
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    try:
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except ValueError:
        return False


def generate_secure_token(nbytes: int = 32) -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Hash a token using SHA-256."""
    token_bytes = token.encode("utf-8")
    hashed = hashlib.sha256(token_bytes).hexdigest()
    return hashed


# Legacy compatibility alias used by tests and older imports.
hash_token_ = hash_token


def generate_totp_secret() -> str:
    """Generate a random secret for TOTP (Time-based One-Time Password)."""
    import base64

    random_bytes = secrets.token_bytes(20)  # 160 bits
    return base64.b32encode(random_bytes).decode("utf-8")


def generate_recovery_codes(count: int = 10) -> list[str]:
    """
    Generate human-typeable, single-use MFA recovery codes.

    Codes are drawn from an alphabet that excludes visually ambiguous
    characters (0/O, 1/I/L) to reduce transcription errors, and are
    formatted as two 5-character groups separated by a hyphen (e.g.
    "7K9XJ-4RTQZ") purely for readability.

    SECURITY: callers must hash each code with hash_token() (after
    normalize_recovery_code()) before persisting it — see
    MFAService.confirm(). The raw values returned here are shown to the
    user exactly once and are never stored or logged.
    """
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def normalize_recovery_code(code: str) -> str:
    """
    Normalize a user-submitted recovery code before hashing/comparison.

    Strips surrounding whitespace, uppercases, and removes hyphens/
    internal spaces, so "7k9xj-4rtqz", "7K9XJ4RTQZ", and " 7K9XJ-4RTQZ "
    all hash to the same value. Applied identically at generation time
    (before hashing for storage) and at verification time (before
    hashing the value the user typed) so the two never drift apart.
    """
    return code.strip().upper().replace("-", "").replace(" ", "")


def constant_time_compare(val1: str, val2: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    import hmac

    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))


# Legacy compatibility alias used by tests and older imports.
constants_time_compare = constant_time_compare
