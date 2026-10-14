from fastapi import Header, HTTPException


def require_user(x_user: str | None = Header(default=None)) -> str:
    if not x_user:
        raise HTTPException(status_code=401, detail="missing X-User")
    return x_user


def require_role(conn, user_id: str, role: str):
    row = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None or row["role"] != role:
        raise HTTPException(status_code=403, detail="forbidden")