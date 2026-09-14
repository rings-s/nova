"""Password hashing.

Uses `hashlib.scrypt` from the standard library. scrypt is memory-hard, so a
GPU or ASIC attacker gains far less than against a fast hash like SHA-256 —
and it needs no third-party dependency, which matters for a local-first
deployment.

Parameters follow current interactive-login guidance: n=2^15, r=8, p=1
(~32 MB per hash). Raise `n` as hardware improves; the cost parameters are
stored in the hash string, so old hashes keep verifying and are transparently
upgraded on next login via `needs_rehash`.

If bcrypt/argon2 is added later, `verify_password` can dispatch on the prefix
without invalidating a single stored password.
"""

import hmac
import secrets
from base64 import b64decode, b64encode
from hashlib import scrypt

_ALGORITHM = "scrypt"
_N = 2**15
_R = 8
_P = 1
_DKLEN = 64
_SALT_BYTES = 16

# scrypt needs maxmem >= roughly 128 * n * r; the default is too small for n=2^15.
_MAXMEM = 128 * _N * _R * 2


def hash_password(password: str) -> str:
    """Returns `scrypt$n$r$p$salt$hash`, self-describing so parameters can change."""
    if not password:
        raise ValueError("Password must not be empty.")

    salt = secrets.token_bytes(_SALT_BYTES)
    derived = scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM)
    return "$".join(
        [
            _ALGORITHM,
            str(_N),
            str(_R),
            str(_P),
            b64encode(salt).decode(),
            b64encode(derived).decode(),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification. Returns False rather than raising on junk."""
    try:
        algorithm, n_str, r_str, p_str, salt_b64, hash_b64 = stored.split("$")
        if algorithm != _ALGORITHM:
            return False
        n, r, p = int(n_str), int(r_str), int(p_str)
        salt = b64decode(salt_b64)
        expected = b64decode(hash_b64)
    except (ValueError, TypeError):
        return False

    candidate = scrypt(
        password.encode(),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=len(expected),
        maxmem=128 * n * r * 2,
    )
    return hmac.compare_digest(candidate, expected)


def needs_rehash(stored: str) -> bool:
    """True when a stored hash uses weaker parameters than the current policy."""
    try:
        algorithm, n_str, r_str, p_str, _, _ = stored.split("$")
    except ValueError:
        return True
    return (algorithm, int(n_str), int(r_str), int(p_str)) != (_ALGORITHM, _N, _R, _P)
