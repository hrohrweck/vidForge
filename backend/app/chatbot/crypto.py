import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

VERSION_BYTE = b"\x01"


def _derive_key() -> bytes:
    settings = get_settings()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=VERSION_BYTE,
        info=b"vidforge-mcp-credentials-v1",
    )
    raw_key = hkdf.derive(settings.secret_key.encode())
    return base64.urlsafe_b64encode(raw_key)


_KEY = None


def _get_fernet() -> Fernet:
    global _KEY
    if _KEY is None:
        _KEY = Fernet(_derive_key())
    return _KEY


def encrypt_credentials(plaintext: str) -> bytes:
    fernet = _get_fernet()
    ciphertext = fernet.encrypt(plaintext.encode())
    return VERSION_BYTE + ciphertext


def decrypt_credentials(ciphertext: bytes) -> str:
    if not ciphertext.startswith(VERSION_BYTE):
        raise ValueError("Unsupported credential version")
    fernet = _get_fernet()
    return fernet.decrypt(ciphertext[len(VERSION_BYTE) :]).decode()
