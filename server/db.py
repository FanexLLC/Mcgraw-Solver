"""Database layer — PostgreSQL with JSON file fallback for local dev."""

from __future__ import annotations
import os
import json
import logging
import secrets
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_use_db = bool(DATABASE_URL)

KEYS_FILE = os.path.join(os.path.dirname(__file__), "keys.json")
ORDERS_FILE = os.path.join(os.path.dirname(__file__), "orders.json")

PLAN_DURATIONS = {"weekly": 7, "monthly": 30, "semester": 120}


# ── Connection ────────────────────────────────────────────────────

def get_db():
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def init_db() -> None:
    """Create tables if needed, seed from JSON files."""
    if not _use_db:
        logger.info("No DATABASE_URL set, using JSON files")
        return

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key TEXT PRIMARY KEY,
            label TEXT,
            plan TEXT,
            created TIMESTAMP,
            expires TIMESTAMP,
            total_requests INTEGER DEFAULT 0,
            last_used TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT,
            venmo_username TEXT,
            transaction_id TEXT,
            plan TEXT,
            status TEXT DEFAULT 'pending',
            created TIMESTAMP,
            approved_at TIMESTAMP,
            key TEXT,
            referral TEXT
        )
    """)

    # Migration: Add referral column if it doesn't exist (for existing databases)
    cur.execute("""
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS referral TEXT
    """)

    # Seed from JSON if DB is empty
    _seed_keys(cur)
    _seed_orders(cur)

    cur.close()
    conn.close()
    logger.info("Database initialized")


def _seed_keys(cur) -> None:
    cur.execute("SELECT COUNT(*) FROM keys")
    if cur.fetchone()[0] > 0 or not os.path.exists(KEYS_FILE):
        return
    try:
        with open(KEYS_FILE) as f:
            data = json.load(f)
        for k in data.get("keys", []):
            created = _parse_iso(k.get("created"))
            expires = _parse_iso(k.get("expires"))
            cur.execute(
                "INSERT INTO keys (key, label, plan, created, expires, total_requests) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (key) DO NOTHING",
                (k["key"], k.get("label"), k.get("plan"), created, expires,
                 k.get("total_requests", 0)))
        logger.info(f"Seeded {len(data.get('keys', []))} keys from keys.json")
    except Exception as e:
        logger.error(f"Failed to seed keys: {e}")


def _seed_orders(cur) -> None:
    cur.execute("SELECT COUNT(*) FROM orders")
    if cur.fetchone()[0] > 0 or not os.path.exists(ORDERS_FILE):
        return
    try:
        with open(ORDERS_FILE) as f:
            data = json.load(f)
        for o in data.get("orders", []):
            created = _parse_iso(o.get("created"))
            approved_at = _parse_iso(o.get("approved_at"))
            cur.execute(
                "INSERT INTO orders (id, name, email, venmo_username, transaction_id, "
                "plan, status, created, approved_at, key) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (o["id"], o.get("name"), o.get("email"), o.get("venmo_username"),
                 o.get("transaction_id"), o.get("plan"), o.get("status", "pending"),
                 created, approved_at, o.get("key")))
        logger.info(f"Seeded {len(data.get('orders', []))} orders from orders.json")
    except Exception as e:
        logger.error(f"Failed to seed orders: {e}")


def _parse_iso(val: str | None) -> datetime | None:
    if not val:
        return None
    return datetime.fromisoformat(val.rstrip("Z"))


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() + "Z"


# ── JSON Fallback Helpers ─────────────────────────────────────────

def _load_keys_json() -> dict:
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE) as f:
            return json.load(f)
    return {"keys": []}


def _save_keys_json(data: dict) -> None:
    with open(KEYS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _load_orders_json() -> dict:
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE) as f:
            return json.load(f)
    return {"orders": []}


def _save_orders_json(data: dict) -> None:
    with open(ORDERS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Key Operations ────────────────────────────────────────────────

def find_key(access_key: str) -> dict | None:
    """Find a key entry. Returns dict or None."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT key, label, plan, created, expires, total_requests, last_used "
                     "FROM keys WHERE key = %s", (access_key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        return {
            "key": row[0], "label": row[1], "plan": row[2],
            "created": _to_iso(row[3]), "expires": _to_iso(row[4]),
            "total_requests": row[5] or 0, "last_used": row[6],
        }
    else:
        keys_data = _load_keys_json()
        return next((k for k in keys_data.get("keys", []) if k["key"] == access_key), None)


def update_key_usage(access_key: str) -> None:
    """Increment total_requests and update last_used."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE keys SET total_requests = total_requests + 1, last_used = %s WHERE key = %s",
            (datetime.utcnow(), access_key))
        cur.close()
        conn.close()
    else:
        keys_data = _load_keys_json()
        for k in keys_data.get("keys", []):
            if k["key"] == access_key:
                k["total_requests"] = k.get("total_requests", 0) + 1
                k["last_used"] = _to_iso(datetime.utcnow())
                break
        _save_keys_json(keys_data)


def create_key(key: str, label: str, plan: str, created: datetime, expires: datetime) -> None:
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO keys (key, label, plan, created, expires) VALUES (%s, %s, %s, %s, %s)",
            (key, label, plan, created, expires))
        cur.close()
        conn.close()
    else:
        keys_data = _load_keys_json()
        keys_data["keys"].append({
            "key": key, "label": label, "plan": plan,
            "created": _to_iso(created), "expires": _to_iso(expires),
        })
        _save_keys_json(keys_data)


def list_keys() -> list[dict]:
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT key, label, plan, expires, total_requests, last_used FROM keys")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{
            "key": r[0][:8] + "...", "label": r[1] or "", "plan": r[2] or "none",
            "expires": _to_iso(r[3]), "total_requests": r[4] or 0,
            "last_used": _to_iso(r[5]),
        } for r in rows]
    else:
        keys_data = _load_keys_json()
        return [{
            "key": k["key"][:8] + "...", "label": k.get("label", ""),
            "plan": k.get("plan", "none"), "expires": k.get("expires"),
            "total_requests": k.get("total_requests", 0),
            "last_used": k.get("last_used"),
        } for k in keys_data.get("keys", [])]


def revoke_key(key_prefix: str) -> int:
    """Delete keys matching prefix. Returns number deleted."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM keys WHERE key LIKE %s", (key_prefix + "%",))
        deleted = cur.rowcount
        cur.close()
        conn.close()
        return deleted
    else:
        keys_data = _load_keys_json()
        original = len(keys_data["keys"])
        keys_data["keys"] = [k for k in keys_data["keys"]
                              if not k["key"].startswith(key_prefix)]
        _save_keys_json(keys_data)
        return original - len(keys_data["keys"])


def generate_key_with_expiry(label: str, plan: str) -> tuple[str, dict]:
    """Generate a new access key with expiration based on plan."""
    key = secrets.token_hex(16)
    now = datetime.utcnow()
    expires = now + timedelta(days=PLAN_DURATIONS[plan])
    create_key(key, label, plan, now, expires)
    return key, {"key": key, "expires": _to_iso(expires)}


# ── Order Operations ──────────────────────────────────────────────

def create_order(order: dict) -> str:
    """Create a new order. Returns the order ID."""
    if not order.get("id"):
        order["id"] = "order_" + secrets.token_hex(6)

    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (id, name, email, venmo_username, transaction_id, plan, status, created, referral, payment_method, stripe_session_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (order["id"], order["name"], order["email"], order.get("venmo_username", ""),
             order.get("transaction_id", ""), order["plan"], order.get("status", "pending"),
             _parse_iso(order.get("created")) or datetime.utcnow(),
             order.get("referral", ""), order.get("payment_method", "venmo"),
             order.get("stripe_session_id")))
        cur.close()
        conn.close()
    else:
        orders_data = _load_orders_json()
        orders_data["orders"].append(order)
        _save_orders_json(orders_data)

    return order["id"]


def list_orders(status_filter: str | None = None) -> list[dict]:
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        if status_filter:
            cur.execute(
                "SELECT id, name, email, venmo_username, transaction_id, plan, status, "
                "created, approved_at, key, referral, payment_method, stripe_session_id "
                "FROM orders WHERE status = %s ORDER BY created DESC",
                (status_filter,))
        else:
            cur.execute(
                "SELECT id, name, email, venmo_username, transaction_id, plan, status, "
                "created, approved_at, key, referral, payment_method, stripe_session_id "
                "FROM orders ORDER BY created DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{
            "id": r[0], "name": r[1], "email": r[2], "venmo_username": r[3] or "",
            "transaction_id": r[4] or "", "plan": r[5], "status": r[6],
            "created": _to_iso(r[7]), "approved_at": _to_iso(r[8]), "key": r[9],
            "referral": r[10] or "", "payment_method": r[11] if len(r) > 11 else "venmo",
            "stripe_session_id": r[12] if len(r) > 12 else None,
        } for r in rows]
    else:
        orders_data = _load_orders_json()
        orders = orders_data.get("orders", [])
        if status_filter:
            orders = [o for o in orders if o["status"] == status_filter]
        return orders


def find_order(order_id: str) -> dict | None:
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, email, venmo_username, transaction_id, plan, status, "
            "created, approved_at, key, referral, payment_method, stripe_session_id "
            "FROM orders WHERE id = %s", (order_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0], "name": row[1], "email": row[2], "venmo_username": row[3] or "",
            "transaction_id": row[4] or "", "plan": row[5], "status": row[6],
            "created": _to_iso(row[7]), "approved_at": _to_iso(row[8]), "key": row[9],
            "referral": row[10] or "", "payment_method": row[11] if len(row) > 11 else "venmo",
            "stripe_session_id": row[12] if len(row) > 12 else None,
        }
    else:
        orders_data = _load_orders_json()
        return next((o for o in orders_data["orders"] if o["id"] == order_id), None)


def update_order(order_id: str, status: str, key: str | None = None,
                 approved_at: datetime | None = None) -> None:
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE orders SET status = %s, key = %s, approved_at = %s WHERE id = %s",
            (status, key, approved_at, order_id))
        cur.close()
        conn.close()
    else:
        orders_data = _load_orders_json()
        for o in orders_data["orders"]:
            if o["id"] == order_id:
                o["status"] = status
                if key:
                    o["key"] = key
                if approved_at:
                    o["approved_at"] = _to_iso(approved_at)
                break
        _save_orders_json(orders_data)


# ── Stripe Helper Functions ───────────────────────────────────────

def find_order_by_stripe_session(session_id: str) -> dict | None:
    """Find order by Stripe session ID."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, email, venmo_username, transaction_id, plan, status, "
            "created, approved_at, key, referral, payment_method, stripe_session_id "
            "FROM orders WHERE stripe_session_id = %s", (session_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0], "name": row[1], "email": row[2], "venmo_username": row[3],
            "transaction_id": row[4], "plan": row[5], "status": row[6],
            "created": _to_iso(row[7]), "approved_at": _to_iso(row[8]), "key": row[9],
            "referral": row[10], "payment_method": row[11], "stripe_session_id": row[12],
        }
    else:
        orders_data = _load_orders_json()
        return next((o for o in orders_data["orders"]
                     if o.get("stripe_session_id") == session_id), None)


def update_order_stripe_session(order_id: str, stripe_session_id: str) -> None:
    """Update order with Stripe session ID."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE orders SET stripe_session_id = %s WHERE id = %s",
            (stripe_session_id, order_id))
        cur.close()
        conn.close()
    else:
        orders_data = _load_orders_json()
        for o in orders_data["orders"]:
            if o["id"] == order_id:
                o["stripe_session_id"] = stripe_session_id
                break
        _save_orders_json(orders_data)


def update_order_status(order_id: str, status: str, key: str | None = None) -> None:
    """Update order status and optionally set the key."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        if key:
            cur.execute(
                "UPDATE orders SET status = %s, key = %s, approved_at = %s WHERE id = %s",
                (status, key, datetime.utcnow(), order_id))
        else:
            cur.execute(
                "UPDATE orders SET status = %s WHERE id = %s",
                (status, order_id))
        cur.close()
        conn.close()
    else:
        orders_data = _load_orders_json()
        for o in orders_data["orders"]:
            if o["id"] == order_id:
                o["status"] = status
                if key:
                    o["key"] = key
                    o["approved_at"] = _to_iso(datetime.utcnow())
                break
        _save_orders_json(orders_data)


def update_key_preference(access_key: str, preferred_model: str) -> None:
    """Save user's preferred AI model."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE keys SET preferred_model = %s WHERE key = %s",
            (preferred_model, access_key))
        cur.close()
        conn.close()
    else:
        keys_data = _load_keys_json()
        for k in keys_data.get("keys", []):
            if k["key"] == access_key:
                k["preferred_model"] = preferred_model
                break
        _save_keys_json(keys_data)


def add_to_email_retry_queue(order_id: str, email_type: str,
                             recipient: str, template_params: dict) -> None:
    """Add failed email to retry queue."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO email_retry_queue (order_id, email_type, recipient, template_params, created)
               VALUES (%s, %s, %s, %s, NOW())""",
            (order_id, email_type, recipient, json.dumps(template_params)))
        cur.close()
        conn.close()
    else:
        logger.warning("Email retry queue only supported with database")


# ── Session Management Functions ──────────────────────────────────

def create_session(access_key: str, session_id: str) -> dict | None:
    """
    Create a new session for the given key.
    Returns previous session if one existed, None otherwise.
    """
    if not _use_db:
        logger.warning("Session management only supported with database")
        return None

    conn = get_db()
    cur = conn.cursor()

    # Check for existing active session
    cur.execute(
        "SELECT session_id, started_at FROM active_sessions WHERE access_key = %s",
        (access_key,)
    )
    existing = cur.fetchone()
    previous_session = None
    if existing:
        previous_session = {
            "session_id": existing[0],
            "started_at": _to_iso(existing[1])
        }
        # Delete the old session
        cur.execute("DELETE FROM active_sessions WHERE access_key = %s", (access_key,))

    # Create new session
    cur.execute(
        """INSERT INTO active_sessions (access_key, session_id, started_at, last_heartbeat)
           VALUES (%s, %s, NOW(), NOW())""",
        (access_key, session_id)
    )

    cur.close()
    conn.close()
    logger.info(f"Session created: {session_id[:8]}... for key {access_key[:8]}...")
    return previous_session


def update_session_heartbeat(session_id: str) -> bool:
    """Update the last heartbeat timestamp for a session. Returns True if session exists."""
    if not _use_db:
        return True  # No-op in JSON mode

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE active_sessions SET last_heartbeat = NOW() WHERE session_id = %s",
        (session_id,)
    )
    updated = cur.rowcount > 0
    cur.close()
    conn.close()
    return updated


def end_session(session_id: str) -> bool:
    """End a session. Returns True if session was found and deleted."""
    if not _use_db:
        return True  # No-op in JSON mode

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM active_sessions WHERE session_id = %s", (session_id,))
    deleted = cur.rowcount > 0
    cur.close()
    conn.close()
    if deleted:
        logger.info(f"Session ended: {session_id[:8]}...")
    return deleted


def cleanup_stale_sessions(timeout_seconds: int = 60) -> int:
    """
    Clean up sessions that haven't sent a heartbeat in timeout_seconds.
    Returns number of sessions deleted.
    """
    if not _use_db:
        return 0

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """DELETE FROM active_sessions
           WHERE last_heartbeat < NOW() - make_interval(secs => %s)""",
        (timeout_seconds,)
    )
    deleted = cur.rowcount
    cur.close()
    conn.close()
    if deleted > 0:
        logger.info(f"Cleaned up {deleted} stale session(s)")
    return deleted


def get_active_session(access_key: str) -> dict | None:
    """Get the active session for a given key, if any."""
    if not _use_db:
        return None

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT session_id, started_at, last_heartbeat FROM active_sessions WHERE access_key = %s",
        (access_key,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return None

    return {
        "session_id": row[0],
        "started_at": _to_iso(row[1]),
        "last_heartbeat": _to_iso(row[2])
    }
