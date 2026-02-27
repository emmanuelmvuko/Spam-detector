from cryptography.fernet import Fernet


def _fernet(key: str) -> Fernet:
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(token: str, key: str) -> str:
    if token is None:
        return None
    return _fernet(key).encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(token_enc: str, key: str) -> str:
    if not token_enc:
        return None
    return _fernet(key).decrypt(token_enc.encode("utf-8")).decode("utf-8")