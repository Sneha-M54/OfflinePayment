import os
import time
import tempfile
import base64
import json

import pytest
from fastapi.testclient import TestClient

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["BANK_KEY_FILE"] = os.path.join(tempfile.mkdtemp(), "bank.pem")
os.environ["ALLOW_DEMO_RESET"] = "1"

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from app import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, u, p):
    return client.post("/api/login", json={"username": u, "password": p}).json()


def _sign(priv, obj):
    canon = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return base64.b64encode(priv.sign(canon)).decode()


def _setup_payer(client, uid):
    priv = Ed25519PrivateKey.generate()
    pub = base64.b64encode(
        priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ).decode()
    headers = {"X-User": uid}

    dev_r = client.post("/api/devices", json={"public_key": pub}, headers=headers)
    assert dev_r.status_code == 200, f"device failed: {dev_r.status_code} {dev_r.text}"
    device_id = dev_r.json()["device_id"]

    r = client.post("/api/reserve", json={"amount": 1000}, headers=headers)
    assert r.status_code == 200, f"reserve failed: {r.status_code} {r.text}"
    rid = r.json()["reserve_id"]

    r = client.post(
        "/api/certificates",
        json={"reserve_id": rid, "device_id": device_id},
        headers=headers,
    )
    assert r.status_code == 200, f"cert failed: {r.status_code} {r.text}"
    cert_id = r.json()["certificate_id"]
    return priv, cert_id, headers


def test_normal_payment_settles(client):
    _login(client, "alice", "alice123")
    priv, cert_id, headers = _setup_payer(client, "u_alice")
    now = int(time.time())
    payload = {
        "certificate_id": cert_id,
        "payer_id": "u_alice",
        "payee_id": "u_merchant",
        "amount": 100,
        "nonce": "n1",
        "counter": 1,
        "issued_at": now,
        "expires_at": now + 3600,
    }
    sig = _sign(priv, payload)
    r = client.post("/api/sync/token", json={**payload, "signature": sig}, headers=headers)
    assert r.json().get("status") == "settled", f"HTTP {r.status_code} body={r.text}"


def test_replay_rejected(client):
    priv, cert_id, headers = _setup_payer(client, "u_alice")
    now = int(time.time())
    payload = {
        "certificate_id": cert_id,
        "payer_id": "u_alice",
        "payee_id": "u_merchant",
        "amount": 10,
        "nonce": "n_dup",
        "counter": 99,
        "issued_at": now,
        "expires_at": now + 3600,
    }
    sig = _sign(priv, payload)
    r1 = client.post("/api/sync/token", json={**payload, "signature": sig}, headers=headers)
    r2 = client.post("/api/sync/token", json={**payload, "signature": sig}, headers=headers)
    assert r1.json().get("status") == "settled", f"HTTP {r1.status_code} body={r1.text}"
    assert r2.json().get("status") == "already_settled", f"HTTP {r2.status_code} body={r2.text}"


def test_double_spend_flagged(client):
    priv, cert_id, headers = _setup_payer(client, "u_alice")
    now = int(time.time())
    base = {
        "certificate_id": cert_id,
        "payer_id": "u_alice",
        "payee_id": "u_merchant",
        "amount": 100,
        "issued_at": now,
        "expires_at": now + 3600,
    }
    a = {**base, "nonce": "na", "counter": 500}
    sig_a = _sign(priv, a)
    r = client.post("/api/sync/token", json={**a, "signature": sig_a}, headers=headers)
    assert r.json().get("status") == "settled", f"HTTP {r.status_code} body={r.text}"

    b = {**base, "nonce": "nb", "counter": 500, "payee_id": "u_bob"}
    sig_b = _sign(priv, b)
    r = client.post("/api/sync/token", json={**b, "signature": sig_b}, headers=headers)
    body = r.json()
    assert body.get("status") == "flagged", f"HTTP {r.status_code} body={r.text}"
    assert "counter_reuse" in body.get("flag_reason", "")


def test_idempotent_ten_uploads(client):
    priv, cert_id, headers = _setup_payer(client, "u_alice")
    now = int(time.time())
    payload = {
        "certificate_id": cert_id,
        "payer_id": "u_alice",
        "payee_id": "u_merchant",
        "amount": 50,
        "nonce": "idem",
        "counter": 777,
        "issued_at": now,
        "expires_at": now + 3600,
    }
    sig = _sign(priv, payload)
    statuses = []
    for _ in range(10):
        r = client.post("/api/sync/token", json={**payload, "signature": sig}, headers=headers)
        statuses.append(r.json().get("status"))
    assert statuses.count("settled") == 1, f"statuses={statuses}"
    assert statuses.count("already_settled") == 9, f"statuses={statuses}"