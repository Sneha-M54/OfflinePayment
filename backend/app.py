import os
import time
import uuid

from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import init_db, tx
from crypto import (
    load_or_create_bank_key,
    bank_public_key_b64,
    sign_bank,
    verify_public,
)
from auth import require_user, require_role
from risk import limits_for

ALLOW_DEMO_RESET = os.environ.get("ALLOW_DEMO_RESET", "0") == "1"
FRONTEND_ORIGINS = [
    o.strip() for o in os.environ.get("FRONTEND_ORIGINS", "*").split(",") if o.strip()
]

BANK_KEY = load_or_create_bank_key()


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------
SEED = [
    ("u_alice", "alice", "alice123", "customer"),
    ("u_bob", "bob", "bob123", "customer"),
    ("u_merchant", "merchant", "shop123", "merchant"),
    ("u_analyst", "analyst", "analyst123", "analyst"),
]


def _seed_users():
    now = int(time.time())
    with tx() as conn:
        for uid, uname, pw, role in SEED:
            conn.execute(
                "INSERT OR IGNORE INTO users(id, username, password, role, created_at) "
                "VALUES (?,?,?,?,?)",
                (uid, uname, pw, role, now - 90 * 86400),
            )
        for uid in ("u_alice", "u_bob"):
            has = conn.execute(
                "SELECT 1 FROM ledger WHERE user_id=? LIMIT 1", (uid,)
            ).fetchone()
            if not has:
                conn.execute(
                    "INSERT INTO ledger(user_id, delta, reason, ref, created_at) "
                    "VALUES (?,?,?,?,?)",
                    (uid, 100000, "seed", None, now),
                )


def _balance(conn, user_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(delta),0) AS s FROM ledger WHERE user_id=?", (user_id,)
    ).fetchone()
    return row["s"]


def _reserved(conn, user_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS s FROM reserves WHERE user_id=?", (user_id,)
    ).fetchone()
    return row["s"]


# ---------------------------------------------------------------------------
# Lifespan + app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _seed_users()
    yield


app = FastAPI(title="OfflinePay API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class LoginIn(BaseModel):
    username: str
    password: str


class DeviceIn(BaseModel):
    public_key: str


class ReserveIn(BaseModel):
    amount: int = Field(gt=0)


class CertIn(BaseModel):
    reserve_id: str
    device_id: str | None = None


class TokenIn(BaseModel):
    certificate_id: str
    payee_id: str
    amount: int = Field(gt=0)
    nonce: str
    counter: int = Field(ge=1)
    issued_at: int
    expires_at: int
    signature: str
    payer_id: str


class DisputeIn(BaseModel):
    token_id: str
    reason: str


class DecisionIn(BaseModel):
    dispute_id: str
    decision: str


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/bank-public-key")
def bank_public_key():
    return {"public_key": bank_public_key_b64(BANK_KEY)}


@app.post("/api/demo/reset")
def demo_reset():
    if not ALLOW_DEMO_RESET:
        raise HTTPException(status_code=403, detail="demo reset disabled")
    import db as _db

    if os.path.exists(_db.DB_PATH):
        os.remove(_db.DB_PATH)
    init_db()
    _seed_users()
    return {"status": "reset"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.post("/api/login")
def login(body: LoginIn):
    with tx() as conn:
        row = conn.execute(
            "SELECT id, role FROM users WHERE username=? AND password=?",
            (body.username, body.password),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return {"user_id": row["id"], "role": row["role"]}


@app.post("/api/devices")
def register_device(body: DeviceIn, user_id: str = Depends(require_user)):
    device_id = "dev_" + uuid.uuid4().hex[:12]
    with tx() as conn:
        conn.execute(
            "INSERT INTO devices(id, user_id, public_key, created_at) VALUES (?,?,?,?)",
            (device_id, user_id, body.public_key, int(time.time())),
        )
    return {"device_id": device_id}


# ---------------------------------------------------------------------------
# Wallet / ledger
# ---------------------------------------------------------------------------
@app.get("/api/wallet")
def wallet(user_id: str = Depends(require_user)):
    with tx() as conn:
        bal = _balance(conn, user_id)
        res = _reserved(conn, user_id)
        tier, per_pay, max_res = limits_for(conn, user_id)
        cert = conn.execute(
            "SELECT id, amount, per_payment_limit, expires_at FROM certificates "
            "WHERE user_id=? AND revoked=0 ORDER BY issued_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    return {
        "user_id": user_id,
        "balance": bal,
        "reserved": res,
        "available": bal - res,
        "tier": tier,
        "per_payment_limit": per_pay,
        "max_reserve": max_res,
        "certificate": dict(cert) if cert else None,
    }


@app.post("/api/reserve")
def add_reserve(body: ReserveIn, user_id: str = Depends(require_user)):
    with tx() as conn:
        bal = _balance(conn, user_id)
        res = _reserved(conn, user_id)
        tier, per_pay, max_res = limits_for(conn, user_id)
        if body.amount > max_res:
            raise HTTPException(400, f"exceeds tier '{tier}' reserve cap {max_res}")
        if res + body.amount > bal:
            raise HTTPException(400, "insufficient available balance")

        rid = "res_" + uuid.uuid4().hex[:12]
        now = int(time.time())
        conn.execute(
            "INSERT INTO reserves(id, user_id, amount, created_at) VALUES (?,?,?,?)",
            (rid, user_id, body.amount, now),
        )
        conn.execute(
            "INSERT INTO ledger(user_id, delta, reason, ref, created_at) "
            "VALUES (?,?,?,?,?)",
            (user_id, 0, "reserve_lock", rid, now),
        )
    return {"reserve_id": rid, "amount": body.amount}


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------
@app.post("/api/certificates")
def issue_certificate(body: CertIn, user_id: str = Depends(require_user)):
    with tx() as conn:
        res = conn.execute(
            "SELECT id, amount FROM reserves WHERE id=? AND user_id=?",
            (body.reserve_id, user_id),
        ).fetchone()
        if res is None:
            raise HTTPException(404, "reserve not found")

        if body.device_id:
            dev = conn.execute(
                "SELECT id, public_key FROM devices WHERE id=? AND user_id=?",
                (body.device_id, user_id),
            ).fetchone()
        else:
            dev = conn.execute(
                "SELECT id, public_key FROM devices WHERE user_id=? "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        if dev is None:
            raise HTTPException(400, "register a device first")

        tier, per_pay, _ = limits_for(conn, user_id)
        now = int(time.time())
        expires = now + 24 * 3600

        cert_id = "cert_" + uuid.uuid4().hex[:12]
        payload = {
            "certificate_id": cert_id,
            "device_public_key": dev["public_key"],
            "reserve_amount": res["amount"],
            "per_payment_limit": per_pay,
            "expires_at": expires,
            "tier": tier,
        }
        sig = sign_bank(BANK_KEY, payload)
        conn.execute(
            "INSERT INTO certificates(id, user_id, device_id, reserve_id, amount, "
            "per_payment_limit, issued_at, expires_at, signature) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                cert_id,
                user_id,
                dev["id"],
                res["id"],
                res["amount"],
                per_pay,
                now,
                expires,
                sig,
            ),
        )
    return {"certificate_id": cert_id, "payload": payload, "signature": sig}


# ---------------------------------------------------------------------------
# Sync / settle
# ---------------------------------------------------------------------------
@app.post("/api/sync/token")
def sync_token(body: TokenIn, user_id: str = Depends(require_user)):
    """
    Idempotent: uploading the same token N times yields exactly one settlement.
    Double-spend: unique (payer_id, counter) index flags reuse.
    """
    with tx() as conn:
        cert = conn.execute(
            "SELECT * FROM certificates WHERE id=?", (body.certificate_id,)
        ).fetchone()
        if cert is None:
            raise HTTPException(404, "certificate not found")

        dev = conn.execute(
            "SELECT public_key FROM devices WHERE id=?", (cert["device_id"],)
        ).fetchone()

        token_payload = {
            "certificate_id": body.certificate_id,
            "payer_id": body.payer_id,
            "payee_id": body.payee_id,
            "amount": body.amount,
            "nonce": body.nonce,
            "counter": body.counter,
            "issued_at": body.issued_at,
            "expires_at": body.expires_at,
        }
        if not verify_public(dev["public_key"], token_payload, body.signature):
            raise HTTPException(400, "invalid device signature")

        token_id = "tok_" + uuid.uuid4().hex[:12]

        existing = conn.execute(
            "SELECT * FROM tokens WHERE nonce=?", (body.nonce,)
        ).fetchone()
        if existing:
            return {
                "status": "already_settled",
                "token_id": existing["id"],
                "settled": bool(existing["settled"]),
                "flagged": bool(existing["flagged"]),
            }

        # Replay / counter reuse. The unique index on (payer_id, counter) is
        # the real guard; we check explicitly to return a clear reason and
        # avoid inserting a colliding row.
        counter_row = conn.execute(
            "SELECT id FROM tokens WHERE payer_id=? AND counter=?",
            (body.payer_id, body.counter),
        ).fetchone()
        if counter_row is not None:
            conn.execute(
                "UPDATE users SET flags = flags + 1 WHERE id=?",
                (body.payer_id,),
            )
            return {
                "status": "flagged",
                "token_id": counter_row["id"],
                "flag_reason": f"counter_reuse: counter={body.counter} already used",
            }

        flagged = 0
        flag_reason = None
        if body.amount > cert["per_payment_limit"]:
            flagged = 1
            flag_reason = f"over_limit: {body.amount} > {cert['per_payment_limit']}"
        elif int(time.time()) > cert["expires_at"]:
            flagged = 1
            flag_reason = "expired_certificate"

        now = int(time.time())
        conn.execute(
            "INSERT INTO tokens(id, cert_id, payer_id, payee_id, amount, nonce, "
            "counter, issued_at, expires_at, signature, settled, flagged, flag_reason) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                token_id,
                body.certificate_id,
                body.payer_id,
                body.payee_id,
                body.amount,
                body.nonce,
                body.counter,
                body.issued_at,
                body.expires_at,
                body.signature,
                0,
                flagged,
                flag_reason,
            ),
        )

        if flagged:
            return {
                "status": "flagged",
                "token_id": token_id,
                "flag_reason": flag_reason,
            }

        reserved = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM reserves WHERE user_id=?",
            (body.payer_id,),
        ).fetchone()["s"]
        settled = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM tokens "
            "WHERE payer_id=? AND settled=1",
            (body.payer_id,),
        ).fetchone()["s"]

        if settled + body.amount > reserved:
            conn.execute(
                "UPDATE tokens SET flagged=1, flag_reason=? WHERE id=?",
                ("exceeds_reserve", token_id),
            )
            conn.execute(
                "UPDATE users SET flags = flags + 1 WHERE id=?",
                (body.payer_id,),
            )
            return {
                "status": "flagged",
                "token_id": token_id,
                "flag_reason": "exceeds_reserve",
            }

        conn.execute(
            "INSERT INTO ledger(user_id, delta, reason, ref, created_at) "
            "VALUES (?,?,?,?,?)",
            (body.payer_id, -body.amount, "settle_debit", token_id, now),
        )
        conn.execute(
            "INSERT INTO ledger(user_id, delta, reason, ref, created_at) "
            "VALUES (?,?,?,?,?)",
            (body.payee_id, body.amount, "settle_credit", token_id, now),
        )
        conn.execute("UPDATE tokens SET settled=1 WHERE id=?", (token_id,))

    return {"status": "settled", "token_id": token_id}


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------
@app.get("/api/receipts/{token_id}")
def get_receipt(token_id: str, user_id: str = Depends(require_user)):
    with tx() as conn:
        r = conn.execute(
            "SELECT * FROM receipts WHERE token_id=?", (token_id,)
        ).fetchone()
    if r is None:
        raise HTTPException(404, "no receipt")
    return dict(r)


# ---------------------------------------------------------------------------
# Disputes
# ---------------------------------------------------------------------------
@app.post("/api/disputes")
def open_dispute(body: DisputeIn, user_id: str = Depends(require_user)):
    with tx() as conn:
        tok = conn.execute(
            "SELECT id FROM tokens WHERE id=?", (body.token_id,)
        ).fetchone()
        if tok is None:
            raise HTTPException(404, "token not found")
        did = "dsp_" + uuid.uuid4().hex[:12]
        conn.execute(
            "INSERT INTO disputes(id, token_id, opened_by, reason, status, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (did, body.token_id, user_id, body.reason, "open", int(time.time())),
        )
    return {"dispute_id": did}


@app.get("/api/analyst/queue")
def analyst_queue(user_id: str = Depends(require_user)):
    with tx() as conn:
        require_role(conn, user_id, "analyst")
        flagged = conn.execute(
            "SELECT id, payer_id, payee_id, amount, counter, flag_reason, issued_at "
            "FROM tokens WHERE flagged=1 ORDER BY issued_at DESC"
        ).fetchall()
        disputes = conn.execute(
            "SELECT d.id, d.token_id, d.reason, d.status, d.created_at, "
            "t.amount, t.payer_id, t.payee_id, t.flag_reason, t.cert_id "
            "FROM disputes d JOIN tokens t ON t.id = d.token_id "
            "ORDER BY d.created_at DESC"
        ).fetchall()
    return {
        "flagged": [dict(r) for r in flagged],
        "disputes": [dict(r) for r in disputes],
    }


@app.post("/api/analyst/decision")
def analyst_decision(body: DecisionIn, user_id: str = Depends(require_user)):
    with tx() as conn:
        require_role(conn, user_id, "analyst")
        conn.execute(
            "UPDATE disputes SET status='decided', decision=?, decided_at=? WHERE id=?",
            (body.decision, int(time.time()), body.dispute_id),
        )
    return {"status": "decided"}