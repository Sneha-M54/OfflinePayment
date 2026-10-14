import os
import base64
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

BANK_KEY_FILE = os.environ.get("BANK_KEY_FILE", "./bank_private.pem")


def load_or_create_bank_key() -> Ed25519PrivateKey:
    if os.path.exists(BANK_KEY_FILE):
        with open(BANK_KEY_FILE, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    os.makedirs(os.path.dirname(BANK_KEY_FILE), exist_ok=True)
    with open(BANK_KEY_FILE, "wb") as f:
        f.write(pem)
    return key


def bank_public_key_b64(key: Ed25519PrivateKey) -> str:
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(pub).decode()


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sign_bank(key: Ed25519PrivateKey, obj: dict) -> str:
    return base64.b64encode(key.sign(_canonical(obj))).decode()


def verify_public(pub_b64: str, obj: dict, sig_b64: str) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
        pub.verify(base64.b64decode(sig_b64), _canonical(obj))
        return True
    except Exception:
        return False