import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "./payments.db")


def _connect():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def tx():
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    flags INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    public_key TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reserves (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    amount INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id),
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    ref TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS certificates (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    device_id TEXT NOT NULL REFERENCES devices(id),
    reserve_id TEXT NOT NULL REFERENCES reserves(id),
    amount INTEGER NOT NULL,
    per_payment_limit INTEGER NOT NULL,
    issued_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    signature TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tokens (
    id TEXT PRIMARY KEY,
    cert_id TEXT NOT NULL REFERENCES certificates(id),
    payer_id TEXT NOT NULL REFERENCES users(id),
    payee_id TEXT NOT NULL REFERENCES users(id),
    amount INTEGER NOT NULL,
    nonce TEXT NOT NULL,
    counter INTEGER NOT NULL,
    issued_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    signature TEXT NOT NULL,
    settled INTEGER NOT NULL DEFAULT 0,
    flagged INTEGER NOT NULL DEFAULT 0,
    flag_reason TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_device_counter
    ON tokens(payer_id, counter);
CREATE UNIQUE INDEX IF NOT EXISTS ux_nonce
    ON tokens(nonce);

CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY,
    token_id TEXT NOT NULL REFERENCES tokens(id),
    payee_id TEXT NOT NULL REFERENCES users(id),
    received_at INTEGER NOT NULL,
    signature TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS disputes (
    id TEXT PRIMARY KEY,
    token_id TEXT NOT NULL REFERENCES tokens(id),
    opened_by TEXT NOT NULL REFERENCES users(id),
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    decision TEXT,
    created_at INTEGER NOT NULL,
    decided_at INTEGER
);

CREATE TABLE IF NOT EXISTS risk_rules (
    tier TEXT PRIMARY KEY,
    max_per_payment INTEGER NOT NULL,
    max_reserve INTEGER NOT NULL
);
"""


def init_db():
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO risk_rules(tier, max_per_payment, max_reserve) "
            "VALUES (?,?,?)",
            ("new", 500, 2000),
        )
        conn.execute(
            "INSERT OR IGNORE INTO risk_rules(tier, max_per_payment, max_reserve) "
            "VALUES (?,?,?)",
            ("standard", 2000, 10000),
        )
        conn.execute(
            "INSERT OR IGNORE INTO risk_rules(tier, max_per_payment, max_reserve) "
            "VALUES (?,?,?)",
            ("trusted", 5000, 50000),
        )
    finally:
        conn.close()