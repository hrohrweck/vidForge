"""Tests for credential encryption/decryption."""

import pytest
from cryptography.fernet import Fernet

from app.chatbot.crypto import decrypt_credentials, encrypt_credentials


class TestEncryptDecryptRoundTrip:
    """Round-trip encryption/decryption preserves plaintext."""

    def test_encrypt_decrypt_returns_original(self):
        plaintext = "sk-abc123xyz"
        ciphertext = encrypt_credentials(plaintext)
        decrypted = decrypt_credentials(ciphertext)
        assert decrypted == plaintext

    def test_encrypt_returns_bytes(self):
        plaintext = "sk-abc123xyz"
        ciphertext = encrypt_credentials(plaintext)
        assert isinstance(ciphertext, bytes)

    def test_ciphertext_starts_with_version_byte(self):
        plaintext = "sk-abc123xyz"
        ciphertext = encrypt_credentials(plaintext)
        assert ciphertext[0] == 0x01

    def test_different_plaintexts_produce_different_ciphertexts(self):
        ct1 = encrypt_credentials("secret1")
        ct2 = encrypt_credentials("secret2")
        assert ct1 != ct2

    def test_same_plaintext_different_ciphertexts(self):
        """Fernet uses random IV, so same plaintext encrypts differently each time."""
        ct1 = encrypt_credentials("same-secret")
        ct2 = encrypt_credentials("same-secret")
        assert ct1 != ct2


class TestDecryptWithWrongKey:
    """Decryption fails with wrong key."""

    def test_decrypt_wrong_key_raises(self):
        plaintext = "sk-abc123xyz"
        ciphertext = encrypt_credentials(plaintext)

        wrong_fernet = Fernet(Fernet.generate_key())

        with pytest.raises(Exception):  # noqa: B017
            wrong_fernet.decrypt(ciphertext[1:])


class TestKeyRotationSafety:
    """Version byte prefix enables future key rotation."""

    def test_ciphertext_can_be_decrypted_by_new_key_derived_from_same_secret(self):
        """Same secret_key should always derive the same encryption key."""
        plaintext = "sk-rotate-test"
        ct1 = encrypt_credentials(plaintext)

        # Decrypt with same key (same secret_key)
        decrypted = decrypt_credentials(ct1)
        assert decrypted == plaintext

    def test_ciphertext_with_wrong_version_byte_fails(self):
        """Ciphertexts must start with 0x01 for v1."""
        plaintext = "sk-test"
        ciphertext = encrypt_credentials(plaintext)

        # Tamper with version byte
        tampered = bytes([0x02]) + ciphertext[1:]

        with pytest.raises(Exception):  # noqa: B017
            decrypt_credentials(tampered)

    def test_truncated_ciphertext_fails(self):
        """Truncated ciphertext should fail gracefully."""
        plaintext = "sk-test"
        ciphertext = encrypt_credentials(plaintext)

        with pytest.raises(Exception):  # noqa: B017
            decrypt_credentials(ciphertext[:10])

    def test_corrupted_ciphertext_fails(self):
        """Corrupted ciphertext should fail gracefully."""
        plaintext = "sk-test"
        ciphertext = encrypt_credentials(plaintext)

        # Flip some bits in the middle
        corrupted = bytearray(ciphertext)
        corrupted[20] ^= 0xFF
        with pytest.raises(Exception):  # noqa: B017
            decrypt_credentials(bytes(corrupted))