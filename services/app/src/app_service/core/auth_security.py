import hashlib
import hmac
import secrets
import bcrypt

BCRYPT_ROUNDS = 12
SESSION_TOKEN_BYTES = 32
BCRYPT_MAX_PASSWORD_BYTES = 72

def normalize_username(username: str) -> str:
    return username.strip().casefold()


def _encode_password(password: str) -> bytes:
    if not password:
        raise ValueError("密码不能为空")
    
    encoded = password.encode("utf-8")

    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError("密码的 UTF-8 编码不能超过 72 字节")

    return encoded


def hash_password(password: str) -> str:
    password_bytes = _encode_password(password)
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    password_hash = bcrypt.hashpw(password_bytes, salt)
    return password_hash.decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        password_bytes = _encode_password(password)
        hash_bytes = password_hash.encode("ascii")
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except (TypeError, ValueError, UnicodeError):
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_token(token: str) -> str:
    if not token:
        raise ValueError("令牌不能为空")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, expected_hash: str) -> bool:
    if not token or not expected_hash:
        return False

    actual_hash = hash_token(token)
    return hmac.compare_digest(actual_hash, expected_hash)
