import time


def pick_tier(conn, user_id: str) -> str:
    row = conn.execute(
        "SELECT created_at, flags FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if row is None:
        return "new"

    age_days = (int(time.time()) - row["created_at"]) // 86400
    flags = row["flags"]

    if flags >= 2:
        return "new"
    if flags == 1 or age_days < 7:
        return "new"
    if age_days >= 30:
        return "trusted"
    return "standard"


def limits_for(conn, user_id: str):
    tier = pick_tier(conn, user_id)
    row = conn.execute(
        "SELECT max_per_payment, max_reserve FROM risk_rules WHERE tier=?",
        (tier,),
    ).fetchone()
    return tier, row["max_per_payment"], row["max_reserve"]