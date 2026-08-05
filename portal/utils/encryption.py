"""
Encryption utilities for secure token storage.

Uses Fernet symmetric encryption from cryptography library.
Keys are derived from the Django SECRET_KEY.
"""

import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _get_fernet_key():
    """Derive a Fernet key from Django's SECRET_KEY."""
    # Use SHA-256 to get a 32-byte key, then base64 encode for Fernet
    secret = settings.SECRET_KEY.encode()
    key = hashlib.sha256(secret).digest()
    return base64.urlsafe_b64encode(key)


# Module-level cipher instance
_cipher = Fernet(_get_fernet_key())


def encrypt_text(plaintext):
    """
    Encrypt a plaintext string.

    Returns base64-encoded ciphertext, or empty string if input is empty/None.
    """
    if not plaintext:
        return ""
    return _cipher.encrypt(plaintext.encode()).decode()


def decrypt_text(ciphertext):
    """
    Decrypt a base64-encoded ciphertext string.

    Returns the plaintext, or empty string if input is empty/None or decryption fails.
    """
    if not ciphertext:
        return ""
    try:
        return _cipher.decrypt(ciphertext.encode()).decode()
    except Exception:
        # If decryption fails (e.g., key changed), return empty string
        # This prevents crashes but means the token is lost
        return ""